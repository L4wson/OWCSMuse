"""ask(): question -> parse -> resolve -> validate -> compile -> execute -> Answer."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import psycopg

from ..liquipedia.attribution import answer_attribution
from ..liquipedia.attribution import render_lines as render_attribution
from ..aggregates import stat_coverage_summary
from ..limitations import applicable as applicable_limitations, entity_match_filter
from ..log import get_logger, log_event
from ..resolve import Candidate, resolve
from .columns import UNDESCRIBED
from .compile import Compiled, Resolved, compile_query
from .evidence import (DEFAULT_PAGE_SIZE, Evidence, entity_of, fetch_evidence, fetch_missing_series,
                       is_map_grain)
from .membership import team_history
from .parser import parse_question
from .sentence import render_sentence, render_unanswerable
from .schema import StructuredQuery, Unanswerable
from .validate import SchemaInfo, validate

log = get_logger("owcsmuse.nlq")

# Resolution policy: accept the top candidate when it is a strong match and
# clearly ahead of any different entity; otherwise ask.
ACCEPT_SCORE = 0.9
CLEAR_MARGIN = 0.15


@dataclass
class Answer:
    status: str                     # ok | clarify | cannot_answer
    question: str
    query: Optional[dict] = None
    code: Optional[str] = None
    reason: Optional[str] = None
    suggestions: list[str] = field(default_factory=list)          # advice, when advice is the answer
    alternatives: list[str] = field(default_factory=list)         # questions that do work, ready to run
    candidates: dict[str, list[dict]] = field(default_factory=dict)   # role -> candidate dicts (clarify)
    entities: dict[str, dict] = field(default_factory=dict)           # role -> resolved entity
    rows: list[dict] = field(default_factory=list)
    sentence: Optional[dict] = None     # the one-sentence claim, from a template
    evidence: Optional[dict] = None     # the rows that produce the aggregate
    coverage: Optional[dict] = None
    notes: list[str] = field(default_factory=list)
    limitations: list[dict] = field(default_factory=list)   # known gaps this slice lands in
    attribution: Optional[dict] = None   # CC-BY-SA credit + page URLs, whenever any Liquipedia value fed the answer (else None)
    description: Optional[str] = None
    sql: Optional[str] = None
    params: Optional[list] = None
    parser: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cannot(question: str, u: Unanswerable, query: Optional[StructuredQuery] = None, parser: Optional[str] = None,
            entities: Optional[dict[str, dict]] = None, alternatives: Optional[list[str]] = None) -> Answer:
    a = Answer(status="cannot_answer", question=question, query=query.compact() if query else None, code=u.code,
               reason=u.reason, suggestions=list(u.suggestions), parser=parser, entities=dict(entities or {}),
               alternatives=list(alternatives or []))
    # A refusal gets a sentence too: it is what the UI shows, and its entities
    # are marked so a name in it stays clickable.
    a.sentence = render_unanswerable(u.reason, a.entities).as_dict()
    return a


def question_hint(name: str, entity_id: str) -> str:
    """How to re-ask using an id instead of an ambiguous name."""
    return entity_id


def _decide(cands: list[Candidate]) -> tuple[Optional[Candidate], bool]:
    """(chosen, ambiguous). A genuine tie between entities is ambiguous.

    An entity with no matches in scope is not a real alternative: when several
    candidates score equally and only one of them has data, that one is the
    answer. The empty namesake stays addressable by its id.
    """
    if not cands:
        return None, False
    top_score = cands[0].score
    tied = [c for c in cands if c.score == top_score]
    tied_with_data = [c for c in tied if c.matches]
    if len(tied) > 1 and len(tied_with_data) == 1:
        return tied_with_data[0], False
    top = cands[0]
    others = [c for c in cands[1:] if (c.entity_type, c.entity_id) != (top.entity_type, top.entity_id)]
    if top.score >= ACCEPT_SCORE and (not others or others[0].score <= top.score - CLEAR_MARGIN or others[0].score < ACCEPT_SCORE):
        return top, False
    if top.score >= ACCEPT_SCORE and others and others[0].score >= ACCEPT_SCORE:
        return None, True
    if top.score < ACCEPT_SCORE:
        return None, True
    return top, False


def candidate_question(question: str, typed: Optional[str], candidate: Candidate) -> str:
    """A question that resolves to exactly this candidate.

    The id goes in where the ambiguous name was, so the rest of the question -
    season, map, opponent - survives. Substituting a *name* is what fails when two
    entities share one, which is the only time this is needed, so the token is
    always the id. If the name cannot be found in the text the question falls back
    to that entity's record, which still answers about the right entity.
    """
    token = candidate.token()
    text = question or ""
    for name in (typed, candidate.matched_name, candidate.current_name):
        if not name:
            continue
        at = text.lower().find(str(name).lower())
        if at >= 0:
            return text[:at] + token + text[at + len(str(name)):]
    return f"{token} record"


def resolve_entities(conn: psycopg.Connection, q: StructuredQuery,
                     question: str = "") -> tuple[Optional[Resolved], Optional[Answer]]:
    """Resolve every name in the filters. Returns (resolved, None) or (None, clarify/cannot answer)."""
    r = Resolved()
    entities: dict[str, dict] = {}
    for role, name in q.filters.names():
        # an org is a team-shaped entity; None lets a bare name resolve to either kind
        etype = {"player": "player", "team": None, "opponent": None, "subject": None}[role]
        cands = resolve(conn, name, etype, limit=6)
        chosen, ambiguous = _decide(cands)
        if chosen is None:
            if not cands:
                return None, Answer(status="cannot_answer", question="", code="unknown_entity",
                                    reason=f"no {etype or 'player or team'} matches '{name}'",
                                    suggestions=["Check the spelling, or try the FACEIT nickname or in-game name."])
            # two or more entities answering to the name exactly is the whole ambiguity: a fuzzy namesake ("Rad Esports"
            # for "Geekay Esports", on the shared word) is noise next to them, not a third choice
            exact = [c for c in cands if c.score >= 1.0]
            if len(exact) >= 2:
                cands = exact
            identical = sum(1 for c in cands if (c.current_name or "").lower() == (cands[0].current_name or "").lower())
            if identical > 1:
                tip = ("These are different FACEIT entities with the same name, so no spelling tells them apart. "
                       f"Re-ask with the id, e.g. \"{question_hint(name, cands[0].entity_id)}\".")
            else:
                tip = "Re-ask with the exact name, or with the id shown in brackets."
            for c in cands:
                c.question = candidate_question(question, name, c)
            return None, Answer(status="clarify", question="", code="ambiguous_entity",
                                reason=f"'{name}' could be several {etype or 'player/team'}s; which one?",
                                suggestions=[tip],
                                candidates={role: [c.as_dict() for c in cands]})
        entities[role] = chosen.as_dict()
        r.names[role] = chosen.current_name or chosen.matched_name
        if role == "opponent":
            r.opponent_id, r.opponent_type = chosen.entity_id, chosen.entity_type
        elif chosen.entity_type == "player":
            r.player_id = chosen.entity_id
            r.subject_type = "player"
        else:
            r.team_id, r.subject_type = chosen.entity_id, chosen.entity_type
    ans = Answer(status="ok", question="", entities=entities)
    return r, ans


_PLAYER_EQUIVALENT = {"record": "map_win_rate", "win_rate": "map_win_rate", "wins": "map_wins", "losses": "map_losses",
                      "matches": "matches", "maps": "maps", "map_wins": "map_wins", "map_losses": "map_losses", "map_win_rate": "map_win_rate"}


def _retarget(q: StructuredQuery, r: Resolved) -> StructuredQuery:
    """An untyped subject has now been resolved: aim the query at the kind of entity it turned out to be."""
    if not q.filters.subject:
        return q
    if r.team_id and not r.player_id:
        f = q.filters.model_copy(update={"team": q.filters.subject, "subject": None})
        intent = "team_record" if q.intent == "entity_stat" and q.metric in _PLAYER_EQUIVALENT else q.intent
        return q.model_copy(update={"entity": "team" if q.intent != "map_stats" else q.entity, "filters": f, "intent": intent})
    if r.player_id and not r.team_id:
        f = q.filters.model_copy(update={"player": q.filters.subject, "subject": None})
        if q.intent == "team_record":
            return q.model_copy(update={"intent": "entity_stat", "entity": "player", "filters": f,
                                        "metric": _PLAYER_EQUIVALENT.get(q.metric, q.metric)})
        return q.model_copy(update={"entity": "player" if q.intent != "map_stats" else q.entity, "filters": f})
    return q


def _entities_for_limitations(r: Resolved) -> list[tuple[str, Optional[str]]]:
    """The resolved entities, as (id, kind) pairs, for narrowing a limitation to this slice."""
    out: list[tuple[str, Optional[str]]] = []
    left = r.player_id if r.subject_type == "player" else r.team_id
    if left:
        out.append((left, r.subject_type))
    if r.opponent_id:
        out.append((r.opponent_id, r.opponent_type))
    return out


def _results_only_alternatives(question: str, q: StructuredQuery, r: Resolved) -> list[str]:
    """What a results-only slice CAN answer: the same entities at series grain, and the question without the region."""
    out: list[str] = []
    left = r.names.get("subject") or r.names.get("player") or r.names.get("team")
    right = r.names.get("opponent")
    if left and right:
        out.append(f"{left} series record against {right}")
    for name in (left, right):
        if name:
            out.append(f"{name} record")
    region = q.filters.region
    if region:
        import re as _re
        stripped = _re.sub(r"\b(in|for)\s+(the\s+)?(korea|south korea|korean|na|emea|eu|europe|north america|international)\b",
                           "", question or "", flags=_re.I).strip()
        stripped = _re.sub(r"\s{2,}", " ", stripped)
        if stripped and stripped != question:
            out.append(stripped)
    return [a for i, a in enumerate(out) if a not in out[:i]]


def _alternatives(question: str, q: StructuredQuery, r: Resolved,
                  coverage: Optional[dict] = None, met_but_no_maps: bool = False) -> list[str]:
    """Questions that would have worked, for a question that did not.

    Advice ("check the spelling") is the right answer to a typo and the wrong
    answer to everything else: when the entities resolved and the data simply is
    not in the slice that was asked for, the useful reply is a question that is.
    """
    left = r.names.get("subject") or r.names.get("player") or r.names.get("team")
    right = r.names.get("opponent")
    out: list[str] = []

    if q.intent == "versus" and left and right and met_but_no_maps:
        # The series exist even though the maps do not, and series grain counts them.
        out.append(f"{left} series record against {right}")
    if q.intent == "season_compare" and left:
        out.append(f"{left} record")

    # The same question, in a season that has the stat.
    with_stat = sorted(coverage.get("seasons_with_stat") or []) if coverage else []
    season = q.filters.season
    if season and with_stat and season not in with_stat:
        other = with_stat[-1]
        swapped = (question or "").replace(str(season), str(other))
        if swapped and swapped != question:
            out.append(swapped)

    for name in (left, right):
        if name:
            out.append(f"{name} record")

    # Never offer the question that just failed.
    asked = (question or "").strip().lower()
    seen: list[str] = []
    for candidate in out:
        if candidate.strip().lower() != asked and candidate not in seen:
            seen.append(candidate)
    return seen[:4]


def _missing_maps_note(conn: psycopg.Connection, q: StructuredQuery, r: Resolved, rows: list[dict]) -> list[str]:
    """Series both sides played that carry no map stats.

    A versus record is map grain, so a `result_only` series contributes nothing.
    Saying so is the difference between "0-0" meaning "never met" and meaning
    "met, but FACEIT recorded no maps".
    """
    left_id = r.player_id if r.subject_type == "player" else r.team_id
    left_type = r.subject_type
    if not (left_id and r.opponent_id):
        return []
    a_sql, a_params = entity_match_filter(left_id, left_type)
    b_sql, b_params = entity_match_filter(r.opponent_id, r.opponent_type)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(*) AS matches,
                       sum(coalesce(m.faction1_score, 0) + coalesce(m.faction2_score, 0)) AS maps,
                       array_agg(DISTINCT c.season ORDER BY c.season) AS seasons
                FROM matches m JOIN championships c USING (championship_id)
                WHERE c.include AND m.ingest_state = 'result_only' AND {a_sql} AND {b_sql}
                  AND (%s::int IS NULL OR c.season = %s)
                """,
                a_params + b_params + [q.filters.season, q.filters.season],
            )
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "missing_maps_note_failed", exc_info=True)
        return []
    if not row or not row["matches"]:
        return []
    seasons = ", ".join(map(str, row["seasons"] or []))
    n = row["matches"]
    plural = "series" if n == 1 else "series"
    maps = row["maps"] or 0
    if not rows or not (rows[0].get("maps") or 0):
        return [f"They did meet: {n} {plural} in season {seasons} ({maps} maps by series score), "
                "but FACEIT recorded no map stats for them, so none can count toward a map record."]
    return [f"A further {n} {plural} between them in season {seasons} ({maps} maps by series score) "
            "carry no map stats on FACEIT and are excluded from the record above."]


def _slice_phrase(q: StructuredQuery) -> str:
    f = q.filters
    parts = []
    if f.season:
        parts.append(f"in {f.season}")
    if f.championship:
        parts.append(f"in {f.championship}")
    if f.map:
        parts.append(f"on {f.map}")
    if f.mode:
        parts.append(f"on {f.mode} maps")
    if f.region:
        parts.append(f"in {f.region.upper()}")
    return " ".join(parts)


def _entity_footprint(conn: psycopg.Connection, r: Resolved) -> Optional[dict]:
    """What the resolved entity has anywhere in scope: its seasons and how much, ignoring the question's filters."""
    if r.player_id and r.subject_type in (None, "player"):
        sql = ("SELECT array_agg(DISTINCT season ORDER BY season) AS seasons, count(DISTINCT match_id) AS matches, "
               "count(*) AS maps FROM fact_player_maps WHERE player_id = %s")
        params, unit = [r.player_id], "maps with stats"
    elif r.team_id:
        key = r.org_key(r.team_id, r.subject_type)
        sql = ("SELECT array_agg(DISTINCT season ORDER BY season) AS seasons, count(DISTINCT match_id) AS matches, "
               "count(DISTINCT match_id) AS maps FROM fact_team_matches WHERE org_key = %s")
        params, unit = [key], "series"
    else:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "entity_footprint_failed", exc_info=True)
        return None
    seasons = [x for x in (row["seasons"] or []) if x is not None] if row else []
    return {"seasons": seasons, "matches": row["matches"] if row else 0, "count": row["maps"] if row else 0, "unit": unit}


def _empty_slice(conn: psycopg.Connection, question: str, q: StructuredQuery, r: Resolved) -> tuple[str, list[str], list[str]]:
    """Why an entity that resolved has no rows here, and what it does have.

    "The query is valid but nothing matches" is true and says nothing. When the name resolved, the useful
    answer is what is actually the case: they have no rows in this slice, and these are the seasons they do have.
    """
    generic = ("the query is valid but nothing in scope matches these filters",
               ["Loosen the season / championship / map filter, or check `status` for what has been ingested."], [])
    name = r.names.get("subject") or r.names.get("player") or r.names.get("team")
    foot = _entity_footprint(conn, r) if name else None
    if not foot:
        return generic
    where = _slice_phrase(q)
    seasons = foot["seasons"]
    if not foot["count"]:
        return (f"{name} is in the warehouse but has no {foot['unit']} in scope",
                ["FACEIT recorded nothing for them in the OWCS NA + EMEA main competition."], [])
    have = ", ".join(map(str, seasons))
    if q.filters.season and q.filters.season not in seasons:
        reason = f"{name} has no {foot['unit']} in {q.filters.season}; the seasons they do have are {have}"
        swaps = [question.replace(str(q.filters.season), str(y)) for y in reversed(seasons)]
    else:
        reason = (f"{name} has no {foot['unit']} {where}; across all filters they have {foot['count']} {foot['unit']} "
                  f"in {have}")
        swaps = []
    tips = [f"{name} appears in {have}. Drop or change the filter to see them."]
    return reason, tips, [s for s in swaps if s != question][:3]


def _membership_answer(conn: psycopg.Connection, question: str, q: StructuredQuery, r: Resolved, pre: Answer,
                       used: str) -> Answer:
    """Which team a player is on, and the teams before it. Stints come from declared line-ups, not map stats."""
    name = r.names.get("subject") or ""
    if not r.player_id:
        u = Unanswerable(code="unsupported_question",
                         reason=f"{name} is a team, not a player, so there is no team for them to be on",
                         suggestions=["Ask about a player, e.g. `what team is <player> on`, or ask the team's record."])
        return _cannot(question, u, q, used, pre.entities, [f"{name} record"])
    rows = team_history(conn, r.player_id, q.filters.season)
    if not rows:
        where = f" in {q.filters.season}" if q.filters.season else ""
        foot = _entity_footprint(conn, r) if q.filters.season else None
        have = ", ".join(map(str, foot["seasons"])) if foot and foot["seasons"] else ""
        reason = (f"{name} has no series{where} with a declared line-up in scope"
                  + (f"; the seasons they do appear in are {have}" if have else ""))
        u = Unanswerable(code="no_data", reason=reason,
                         suggestions=["FACEIT line-ups exist only for the OWCS NA + EMEA main competition in scope."])
        alts = [f"what team is {name} on"] if have else []
        return _cannot(question, u, q, used, pre.entities, alts)
    a = Answer(status="ok", question=question, query=q.compact(), entities=pre.entities, rows=rows,
               description=f"{name}: team now and team history", parser=used)
    a.notes = ["There is no roster feed: \"current\" is the team in this player's most recent series in scope "
               f"({str(rows[0]['to_at'])[:10]}), and a team change after that is not visible here."]
    a.limitations = applicable_limitations(conn, q.intent, None, season=q.filters.season, entities=_entities_for_limitations(r),
                                           grain="series")
    sentence = render_sentence(a.query, rows, pre.entities, a.description)
    a.sentence = sentence.as_dict() if sentence else None
    return a


def run_compiled(conn: psycopg.Connection, c: Compiled) -> list[dict]:
    try:
        with conn.cursor() as cur:
            cur.execute(c.sql, c.params)
            rows = [dict(x) for x in cur.fetchall()]
        conn.commit()
    except Exception:
        conn.rollback()  # never leave the connection in an aborted transaction
        log_event(log, logging.ERROR, "nlq_sql_failed", sql=c.sql, params=c.params, exc_info=True)
        raise
    return rows


def ask(conn: psycopg.Connection, question: str, parser: str = "rules", info: Optional[SchemaInfo] = None,
        debug: bool = False, with_evidence: bool = True, evidence_for: Optional[str] = None,
        evidence_page: int = 1, evidence_page_size: int = DEFAULT_PAGE_SIZE) -> Answer:
    # 1. parse
    used = "rules"
    parsed = None
    if parser in ("llm", "auto"):
        try:
            from .llm_parser import parse_with_claude
            parsed = parse_with_claude(question)
            used = "llm"
        except Exception as exc:  # missing SDK / key / network: fall back to rules in auto mode
            if parser == "llm":
                raise
            log_event(log, logging.WARNING, "llm_parser_unavailable", error=str(exc)[:200])
    if parsed is None:
        parsed = parse_question(question)
    if isinstance(parsed, Unanswerable):
        return _cannot(question, parsed, parser=used)
    q: StructuredQuery = parsed

    # 2. resolve entities before anything else
    r, pre = resolve_entities(conn, q, question)
    if r is None:
        pre.question = question
        pre.query = q.compact()
        pre.parser = used
        return pre
    q = _retarget(q, r)

    if q.intent == "team_membership":
        return _membership_answer(conn, question, q, r, pre, used)

    # 3. validate against the live schema
    info = info or SchemaInfo.from_db(conn)
    v = validate(q, info)
    if isinstance(v, Unanswerable):
        # A stat that exists in other seasons is a question away from working.
        seasons_with = sorted(info.stat_keys.get(q.metric or "", set()) or [])
        swapped = None
        if q.filters.season and seasons_with and q.filters.season not in seasons_with:
            swapped = question.replace(str(q.filters.season), str(seasons_with[-1]))
        alts = [swapped] if swapped and swapped != question else []
        if v.code == "results_only":
            alts += _results_only_alternatives(question, q, r)
        return _cannot(question, v, q, used, pre.entities if r else None, alts)

    # 4. compile
    c = compile_query(v, r)
    if isinstance(c, Unanswerable):
        return _cannot(question, c, q, used)

    # 5. execute + coverage
    rows = run_compiled(conn, c)
    coverage = None
    notes = list(v.notes)
    if c.coverage_stat:
        # Coverage must describe the slice actually queried, not the warehouse.
        coverage = stat_coverage_summary(
            conn, c.coverage_stat, c.coverage_season, c.coverage_championship,
            player_id=r.player_id, team_id=r.team_id, map_name=v.map_name, game_mode=v.mode_name,
            region=q.filters.region,
        )
        cov_pct = float(coverage.get("coverage_pct") or 0)
        without = coverage.get("seasons_without_stat") or []
        if coverage.get("maps_total", 0) == 0:
            notes.append(f"no maps in this slice carry '{c.coverage_stat}'")
        elif cov_pct < 100:
            notes.append(
                f"'{c.coverage_stat}' exists for {cov_pct:g}% of maps in this slice"
                + (f"; seasons without it: {', '.join(map(str, without))}" if without else "")
                + f"; seasons with it: {', '.join(map(str, coverage.get('seasons_with_stat') or []))}. "
                "Rankings cover only the maps that have the stat."
            )
    # Which documented gaps this slice lands in. A versus answer already reports
    # its missing series precisely, so the general offline note is dropped there
    # rather than said twice.
    series_grain = (q.entity == "team" or q.intent in ("team_record", "head_to_head")) and not is_map_grain(v)
    limitations = applicable_limitations(
        conn, q.intent, q.metric, season=q.filters.season, championship_id=c.coverage_championship,
        region=q.filters.region, entities=_entities_for_limitations(r),
        grain="series" if series_grain else "map", results_only_parts=v.results_only_parts)
    if q.intent == "versus":
        limitations = [lim for lim in limitations if lim["id"] != "offline_map_stats"]
        notes += _missing_maps_note(conn, q, r, rows)
        if rows and not (rows[0].get("maps") or 0):
            left = r.names.get("subject") or r.names.get("player") or r.names.get("team") or ""
            right = r.names.get("opponent") or ""
            where = f" in {q.filters.season}" if q.filters.season else ""
            if notes:
                reason = f"{left} and {right} met{where}, but none of those series has map stats on FACEIT"
                tips = ["The series results are known; only the per-map breakdown is missing."]
            else:
                reason = f"{left} and {right} never faced each other{where} in the competitions in scope"
                tips = ["Check the spelling, or widen the season; scope is OWCS NA + EMEA main competition."]
            u = Unanswerable(code="no_data", reason=reason, suggestions=tips)
            a = _cannot(question, u, q, used, pre.entities,
                        _alternatives(question, q, r, coverage, met_but_no_maps=bool(notes)))
            a.notes, a.limitations = notes, limitations
            if with_evidence and notes:
                # they did meet: the series with no map stats are the evidence
                # for why the map record is empty
                try:
                    a.evidence = fetch_missing_series(conn, v, r, evidence_page, evidence_page_size).as_dict()
                except Exception:
                    log_event(log, logging.WARNING, "missing_series_evidence_failed", exc_info=True)
            if debug:
                a.sql, a.params = c.sql, c.params
            return a
    if not rows and q.intent == "season_compare":
        name = r.names.get("subject") or r.names.get("team") or ""
        yrs = [y for y in (q.filters.subject_season, q.filters.opponent_season) if y]
        u = Unanswerable(
            code="no_data",
            reason=f"{name} has no maps with stats in {' or '.join(map(str, yrs))}, so there is nothing to compare",
            suggestions=["The entity may have played only series whose maps FACEIT never recorded, "
                         "or not played in those seasons at all. `ask \"<name> record\"` shows what is known."])
        a = _cannot(question, u, q, used, pre.entities, _alternatives(question, q, r, coverage))
        a.limitations = limitations
        if debug:
            a.sql, a.params = c.sql, c.params
        return a
    if not rows and c.min_maps_floor:
        # the floor, not the slice, may be what emptied it: say so rather than "nothing matches", and offer the question
        # without it
        unfloored = compile_query(replace(v, query=v.query.model_copy(update={"min_maps": 1})), r)
        if isinstance(unfloored, Compiled) and run_compiled(conn, unfloored):
            u = Unanswerable(code="no_data",
                             reason=f"no player in this slice has played at least {c.min_maps_floor} maps, the fewest this "
                                    "leaderboard ranks, so a one-series appearance cannot lead it",
                             suggestions=["Ask with \"with at least 1 map\" to rank everyone, or widen the season."])
            a = _cannot(question, u, q, used, pre.entities, [f"{question} with at least 1 map"])
            a.coverage, a.notes, a.limitations = coverage, notes, limitations
            if debug:
                a.sql, a.params = c.sql, c.params
            return a
    if not rows:
        reason, tips, swaps = _empty_slice(conn, question, q, r)
        u = Unanswerable(code="no_data", reason=reason, suggestions=tips)
        alts = _alternatives(question, q, r, coverage)
        alts += [x for x in swaps if x not in alts]       # the seasons they do have, after the established offer
        a = _cannot(question, u, q, used, pre.entities, alts)
        a.coverage = coverage
        a.notes = notes
        a.limitations = limitations
        if debug:
            a.sql, a.params = c.sql, c.params
        return a
    if q.intent in ("leaderboard", "map_stats"):
        # Expansion is then mechanical: the row names its own entity.
        for row in rows:
            entity = entity_of(row)
            if entity:
                row["entity"] = entity
    a = Answer(status="ok", question=question, query=q.compact(), entities=pre.entities, rows=rows, coverage=coverage,
               notes=notes, limitations=limitations, description=c.description, parser=used)
    # the floor is the compiler's, not the question's: handed to the sentence so it can say who was left out
    sentence = render_sentence(dict(a.query, min_maps_floor=c.min_maps_floor), rows, pre.entities, c.description)
    a.sentence = sentence.as_dict() if sentence else None
    if with_evidence:
        # The aggregate is the claim; these are the rows that produce it.
        try:
            a.evidence = fetch_evidence(conn, v, r, rows, evidence_for, evidence_page, evidence_page_size,
                                        c.coverage_stat).as_dict()
            match_ids = [row.get("match_id") for row in (a.evidence.get("rows") or [])]
            try:
                a.attribution = answer_attribution(conn, match_ids)
            except Exception:
                log_event(log, logging.WARNING, "attribution_failed", intent=q.intent, exc_info=True)
        except Exception:
            log_event(log, logging.ERROR, "evidence_failed", intent=q.intent, exc_info=True)
            a.evidence = Evidence(reason="the evidence rows could not be loaded for this answer").as_dict()
    if debug:
        a.sql, a.params = c.sql, c.params
    return a


# ------------------------------------------------------------------ rendering

def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (float, Decimal)):
        # Postgres numeric arrives as Decimal; quantize both so an average does not
        # print 22.6326530612244898.
        q = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(q.normalize(), "f")
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    return str(v)


def _evidence_lines(a: Answer, evidence_rows: int) -> list[str]:
    """The rows behind the claim, a few of them, however the answer turned out."""
    ev = a.evidence or {}
    lines: list[str] = []
    if ev.get("available"):
        expanded = ev.get("expanded_for") or {}
        who = f" for {expanded.get('name') or expanded.get('id')}" if expanded else ""
        lines.append(f"  evidence{who}: {ev['total_rows']} {ev['grain']} row(s), "
                     f"page {ev['page']} of {max(ev['total_pages'], 1)} - {ev['description']}")
        for row in ev["rows"][:evidence_rows]:
            when = _fmt(row.get("played_at"))
            score = f"{_fmt(row.get('score'))}-{_fmt(row.get('opponent_score'))}"
            where = row.get("map_name") or row.get("competition") or ""
            lines.append(f"    {when}  {(row.get('result') or row.get('winner') or ''):5}  {score:7}  "
                         f"{where[:22]:22}  vs {(row.get('opponent') or '')[:22]}")
        if len(ev["rows"]) > evidence_rows:
            lines.append(f"    ... {len(ev['rows']) - evidence_rows} more on this page")
    elif ev.get("reason"):
        lines.append(f"  evidence: none ({ev['reason']})")
    return lines


def render_text(a: Answer, max_rows: int = 25, evidence_rows: int = 5) -> str:
    lines: list[str] = []
    if a.status == "cannot_answer":
        lines.append(f"Can't answer that ({a.code}): {a.reason}")
        for s in a.suggestions:
            lines.append(f"  - {s}")
        for alt in a.alternatives:
            lines.append(f"  try: {alt}")
        lines += _evidence_lines(a, evidence_rows)
        for n in a.notes:
            lines.append(f"  note: {n}")
        for lim in a.limitations:
            lines.append(f"  known limitation ({lim['id']}): {lim['note']}")
        lines += render_attribution(a.attribution)
        return "\n".join(lines)
    if a.status == "clarify":
        lines.append(f"Need a clarification: {a.reason}")
        for cands in a.candidates.values():
            for c in cands:
                era = f", seasons {', '.join(map(str, c['seasons']))}" if c.get("seasons") else ""
                lines.append(f"  - {c['current_name']}  [{c['entity_type']}] {c['matches']} matches{era}")
                # the actionable part: a question that resolves to exactly this one
                lines.append(f"      ask: {c['question']}" if c.get("question") else
                             f"      id: {c['entity_id']}")
        for tip in (a.suggestions or ["Re-ask with the exact name, or with the id shown in brackets."]):
            lines.append(tip)
        return "\n".join(lines)

    if a.sentence:
        lines.append(a.sentence["text"])
    lines.append(f"{a.description}" + (f"  [{a.parser} parser]" if a.parser else ""))
    if a.entities:
        lines.append("  for: " + ", ".join(f"{role}={e['current_name']}" for role, e in a.entities.items()))
    rows = a.rows[:max_rows]
    if rows:
        # the columns a reader can use, as the API describes them: org_key printed "team:<uuid>" beside the team's name
        cols = [c for c in rows[0].keys() if c not in UNDESCRIBED and not c.endswith("_id")]
        widths = {c: max(len(c), *(len(_fmt(r.get(c))) for r in rows)) for c in cols}
        lines.append("  " + "  ".join(c.ljust(widths[c]) for c in cols))
        for r in rows:
            lines.append("  " + "  ".join(_fmt(r.get(c)).ljust(widths[c]) for c in cols))
        if len(a.rows) > max_rows:
            lines.append(f"  ... {len(a.rows) - max_rows} more rows")
    if a.coverage:
        cov = a.coverage
        lines.append(f"  coverage: {cov.get('stat_key')} on {cov.get('maps_with_stat')}/{cov.get('maps_total')} maps "
                     f"({_fmt(float(cov.get('coverage_pct') or 0))}%), seasons with it: {_fmt(cov.get('seasons_with_stat'))}"
                     + (f", without: {_fmt(cov.get('seasons_without_stat'))}" if cov.get("seasons_without_stat") else ""))
    lines += _evidence_lines(a, evidence_rows)
    for n in a.notes:
        lines.append(f"  note: {n}")
    for lim in a.limitations:
        lines.append(f"  known limitation ({lim['id']}): {lim['note']}")
    lines += render_attribution(a.attribution)
    return "\n".join(lines)
