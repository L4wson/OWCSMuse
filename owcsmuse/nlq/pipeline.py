"""ask(): question -> parse -> resolve -> validate -> compile -> execute -> Answer."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import psycopg

from ..liquipedia.attribution import answer_attribution, attribution_block, attribution_for
from ..liquipedia.attribution import render_lines as render_attribution
from ..aggregates import stat_coverage_summary
from ..limitations import applicable as applicable_limitations
from ..log import get_logger, log_event
from ..resolve import Candidate, resolve
from .columns import UNDESCRIBED
from .compile import Compiled, Resolved, compile_query
from .evidence import (DEFAULT_PAGE_SIZE, Evidence, answer_matches, entity_of, fetch_evidence, fetch_missing_series,
                       is_map_grain)
from .membership import history_matches, team_history
from .parser import parse_question
from .sentence import render_sentence, render_unanswerable
from .schema import StructuredQuery, Unanswerable
from .validate import SchemaInfo, resolve_period, validate

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
    # a versus or head-to-head answer's other grain, ready to run: {"grain": "series"|"map", "label", "question"}
    other_grain: Optional[dict] = None
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
    champ = q.filters.championship
    if champ and not left:
        # an event-wide question: where the teams finished (placings need no identity decision), then the same
        # event at series grain
        season = f"{q.filters.season} " if q.filters.season else ""
        out.append(f"{season}{champ} standings")
        out.append(f"team with the most series wins at the {season}{champ}")
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


def _pairing_sides(conn: psycopg.Connection, q: StructuredQuery, r: Resolved) -> dict[str, int]:
    """How a pairing's series split, by line-up for a player (042): {'opposed': on opposite sides, 'same_side': on one}.
    'same_side' is a player on the org's own side, or two players on one line-up - teammates, never opponents."""
    from .compile import side_clause
    left_id = r.player_id if r.subject_type == "player" else r.team_id
    if not (left_id and r.opponent_id):
        return {"opposed": 0, "same_side": 0}
    a_sql, a_params = side_clause(left_id, r.subject_type, r, "team_id", alias="f")
    opp_sql, opp_params = side_clause(r.opponent_id, r.opponent_type, r, "opponent_team_id", alias="f")
    same_sql, same_params = side_clause(r.opponent_id, r.opponent_type, r, "team_id", alias="f")
    season = "(%s::int IS NULL OR f.season = %s)"
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT (SELECT count(*) FROM fact_team_matches f WHERE {a_sql} AND {opp_sql} AND {season}) AS opposed,
                                   (SELECT count(*) FROM fact_team_matches f WHERE {a_sql} AND {same_sql} AND {season}) AS same_side""",
                        a_params + opp_params + [q.filters.season] * 2 + a_params + same_params + [q.filters.season] * 2)
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "pairing_sides_failed", exc_info=True)
        return {"opposed": 0, "same_side": 0}
    return {"opposed": int(row["opposed"] or 0), "same_side": int(row["same_side"] or 0)}


def _never_opposed_reason(q: StructuredQuery, r: Resolved, sides: dict[str, int]) -> Optional[str]:
    """A pairing that was only ever on one side: a player and his own team, or two teammates."""
    if sides["opposed"] or not sides["same_side"]:
        return None
    left = r.names.get("subject") or r.names.get("player") or r.names.get("team") or ""
    right = r.names.get("opponent") or ""
    where = f" in {q.filters.season}" if q.filters.season else ""
    n = sides["same_side"]
    if r.subject_type == "player" and r.opponent_type == "player":
        return f"{left} and {right} were teammates{where} ({n} series on the same side), never on opposite sides"
    player, team = (left, right) if r.subject_type == "player" else (right, left)
    return f"{player} played for {team}{where} ({n} series), never against them"


def _missing_team_maps_note(conn: psycopg.Connection, q: StructuredQuery, r: Resolved, rows: list[dict]) -> list[str]:
    """Team v team: the series between them with no map results from any source (neither FACEIT's rounds nor
    Liquipedia's games), by org key like the record itself. Since 041 a Liquipedia-only series has maps; only a
    FACEIT result_only series Liquipedia does not cover has none."""
    a, b = r.org_key(r.team_id, r.subject_type), r.org_key(r.opponent_id, r.opponent_type)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT count(*) AS matches, sum(coalesce(f.map_wins, 0) + coalesce(f.map_losses, 0)) AS maps,
                          array_agg(DISTINCT f.season ORDER BY f.season) AS seasons
                     FROM fact_team_matches f
                    WHERE f.org_key = %s AND f.opponent_org_key = %s AND (%s::int IS NULL OR f.season = %s)
                      AND NOT EXISTS (SELECT 1 FROM fact_team_maps m WHERE m.match_id = f.match_id)""",
                (a, b, q.filters.season, q.filters.season))
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "missing_maps_note_failed", exc_info=True)
        return []
    if not row or not row["matches"]:
        return []
    n, maps, seasons = row["matches"], row["maps"] or 0, ", ".join(map(str, row["seasons"] or []))
    if not rows or not (rows[0].get("maps") or 0):
        return [f"They did meet: {n} series in season {seasons} ({maps} maps by series score), but no source records "
                "their map results, so none can count toward a map record."]
    return [f"A further {n} series between them in season {seasons} ({maps} maps by series score) have no map results "
            "from any source and are excluded from the record above."]


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
    if left_type != "player" and r.opponent_type != "player":
        return _missing_team_maps_note(conn, q, r, rows)
    # a player on either side: the series the two were on opposite sides of (042's line-ups, so never his own team's)
    # that put no map into the record - since 045 every played map counts, stats or not, so these are the series with
    # no map result from any source
    from .compile import side_clause
    a_sql, a_params = side_clause(left_id, left_type, r, "team_id", alias="f")
    b_sql, b_params = side_clause(r.opponent_id, r.opponent_type, r, "opponent_team_id", alias="f")
    if left_type == "player" and r.opponent_type == "player":
        view = "fact_player_versus"
        pair, pair_params = "v.player_id = %s AND v.opponent_player_id = %s", [left_id, r.opponent_id]
    elif left_type == "player":
        view = "fact_player_map_results"
        pair, pair_params = "v.player_id = %s AND v.opponent_org_key = %s", [left_id, r.org_key(r.opponent_id, r.opponent_type)]
    else:
        view = "fact_player_map_results"
        pair, pair_params = "v.player_id = %s AND v.opponent_org_key = %s", [r.opponent_id, r.org_key(left_id, left_type)]
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT count(*) AS matches, sum(coalesce(f.map_wins, 0) + coalesce(f.map_losses, 0)) AS maps,
                           array_agg(DISTINCT f.season ORDER BY f.season) AS seasons
                      FROM fact_team_matches f
                     WHERE {a_sql} AND {b_sql} AND (%s::int IS NULL OR f.season = %s)
                       AND NOT EXISTS (SELECT 1 FROM {view} v WHERE v.match_id = f.match_id AND {pair})""",
                a_params + b_params + [q.filters.season, q.filters.season] + pair_params)
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "missing_maps_note_failed", exc_info=True)
        return []
    if not row or not row["matches"]:
        return []
    n, maps, seasons = row["matches"], row["maps"] or 0, ", ".join(map(str, row["seasons"] or []))
    if not rows or not (rows[0].get("maps") or 0):
        return [f"They were on opposite sides in {n} series in season {seasons} ({maps} maps by series score), but no "
                "source records those series' map results, so none can count toward a map record."]
    return [f"A further {n} series on opposite sides in season {seasons} ({maps} maps by series score) have no map "
            "results from any source and are excluded from the record above."]

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
               ["Loosen the season / tournament / map filter, or check `status` for what has been ingested."], [])
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
    # a stint's from/to dates are Liquipedia's where a series is linked and dated there
    _attribute(conn, a, lambda: answer_attribution(conn, history_matches(conn, r.player_id, q.filters.season), "map"))
    return a


def _placement_answer(conn: psycopg.Connection, question: str, q: StructuredQuery, r: Resolved, pre: Answer,
                      used: str, info: SchemaInfo) -> Answer:
    """Where teams finished at an event: Liquipedia's prize pool (`placements`), credited to its page.

    A team name no decision resolves is still shown as Liquipedia names it (`identity: undecided`): that is
    Liquipedia's own record of who finished where, not an identity claim, and nothing about it is merged.
    """
    v = validate(q, info)
    if isinstance(v, Unanswerable):
        return _cannot(question, v, q, used, pre.entities)
    f = q.filters
    clauses, params = ["championship_id = ANY(%s)"], [v.championship_ids]
    if f.place is not None:
        clauses.append("place_high <= %s AND %s <= place_low")
        params += [f.place, f.place]
    key = r.org_key(r.team_id, r.subject_type) if r.team_id else None
    if key:
        clauses.append("org_key = %s")
        params.append(key)
    rows = run_compiled(conn, Compiled(
        sql=f"""SELECT championship_name AS championship, season, placement, place_high, place_low, display_name AS team,
                       team_name AS liquipedia_name, CASE WHEN team_id IS NULL THEN 'undecided' ELSE 'decided' END AS identity,
                       qualifier, page_url
                  FROM placements WHERE {' AND '.join(clauses)}
                 ORDER BY season, championship_id, place_high, display_name""",
        params=params, description="event placings"))
    names = [info.championship_display.get(cid) or info.championships.get(cid) for cid in v.championship_ids]
    if not rows:
        who = r.names.get("subject") or r.names.get("team")
        reason = (f"{who} has no placing recorded at {', '.join(names)}" if who else
                  f"no placing recorded at {', '.join(names)}" + (f" for position {f.place}" if f.place else ""))
        u = Unanswerable(code="no_data", reason=reason,
                         suggestions=["Placings come from Liquipedia's prize pool for the international events "
                                      "(World Finals, Midseason Championships, Champions Clash, EWC 2024)."])
        alts = [f"{who} record at the {f.season or ''} {f.championship}".replace("  ", " ")] if who else []
        return _cannot(question, u, q, used, pre.entities, alts)
    a = Answer(status="ok", question=question, query=q.compact(), entities=pre.entities, rows=rows,
               description="event placings", parser=used, notes=list(v.notes))
    if f.event_read_as == "world champion":
        a.notes.insert(0, f"\"champion\" with no event named read as the world champion, the winner of {' and '.join(names)}")
    undecided = sorted({x["liquipedia_name"] for x in rows if x["identity"] == "undecided"})
    if undecided:
        a.notes.append("named as Liquipedia names them, with no identity decided yet: " + ", ".join(undecided))
    sentence = render_sentence(dict(a.query, championship_names=names), rows, pre.entities, a.description)
    a.sentence = sentence.as_dict() if sentence else None
    _attribute(conn, a, lambda: attribution_block(x["page_url"] for x in rows))
    return a


_REGION_LABEL = {"na": "NA", "emea": "EMEA", "korea": "Korea", "china": "China", "japan": "Japan", "pacific": "Pacific"}


def _group_members(conn: psycopg.Connection, group: str, seasons: Optional[list[int]] = None,
                   region: Optional[str] = None) -> list[dict]:
    clauses, params = ["group_key = %s"], [group]
    if seasons:
        clauses.append("season = ANY(%s)")
        params.append(seasons)
    if region:
        clauses.append("region = %s")
        params.append(region)
    return run_compiled(conn, Compiled(
        sql=f"""SELECT season, region, display_name AS team, liquipedia_name, org_key, page
                  FROM team_group_members WHERE {' AND '.join(clauses)} ORDER BY season, region, display_name""",
        params=params, description="group members"))


def _members_phrase(rows: list[dict]) -> str:
    """'2026 - NA: Dallas Fuel, ...; EMEA: ...' for every season in `rows`."""
    out = []
    for season in sorted({r["season"] for r in rows}):
        regions = {}
        for r in rows:
            if r["season"] == season:
                regions.setdefault(r["region"], []).append(r["team"])
        out.append(f"{season} - " + "; ".join(f"{_REGION_LABEL.get(reg, reg)}: {', '.join(t)}" for reg, t in regions.items()))
    return " | ".join(out)


def _group_pages(rows: list[dict]) -> list[str]:
    from ..liquipedia.attribution import page_url
    return [page_url(p) for p in sorted({r["page"] for r in rows})]


def _group_answer(conn: psycopg.Connection, question: str, q: StructuredQuery, pre: Answer, used: str,
                  info: SchemaInfo) -> Answer:
    """The members of a season-scoped group (the partner teams): a season's, the latest's when none is named."""
    v = validate(q, info)
    if isinstance(v, Unanswerable):
        return _cannot(question, v, q, used, pre.entities)
    f = q.filters
    season = f.season or max(info.group_seasons[f.group])
    rows = _group_members(conn, f.group, [season], f.region)
    if not rows:
        u = Unanswerable(code="no_data", reason=f"no {f.group} teams are recorded for {season}"
                                                + (f" in {_REGION_LABEL.get(f.region, f.region)}" if f.region else ""))
        return _cannot(question, u, q, used, pre.entities)
    a = Answer(status="ok", question=question, query=q.compact(), entities=pre.entities, rows=rows,
               description=f"{f.group} teams", parser=used, notes=[])
    if f.season is None:
        a.notes.append(f"read as {season}, the latest season with {f.group} teams")
    a.notes.append("Partner status is per season and region, from Liquipedia's Stage 1 prize pools (qualifier \"Partner "
                   "Team\"); Liquipedia tags no partners for China 2025, Japan or the Pacific.")
    text = f"The {season} {f.group} teams: " + _members_phrase(rows).split(" - ", 1)[1] + "."
    a.sentence = {"text": text, "spans": []}
    _attribute(conn, a, lambda: attribution_block(_group_pages(rows)))
    return a


ATTRIBUTION_UNKNOWN = ("Liquipedia attribution could not be determined for this answer: values in it may come from "
                       "Liquipedia (CC-BY-SA 3.0, https://liquipedia.net/overwatch) without their page named.")


def _attribute(conn: psycopg.Connection, a: Answer, compute) -> None:
    """Credit every Liquipedia page the answer drew on. A failure is said in the answer, never shipped silently."""
    try:
        a.attribution = compute()
    except Exception:
        conn.rollback()
        log_event(log, logging.ERROR, "attribution_failed", question=a.question, exc_info=True)
        a.notes = list(a.notes or []) + [ATTRIBUTION_UNKNOWN]


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
    """question -> Answer. A relative period ("this stage") is read against the data, and whatever the answer turns
    out to be, it says first what the period was read as."""
    period_notes: list[str] = []
    a = _ask(conn, question, parser, info, debug, with_evidence, evidence_for, evidence_page, evidence_page_size,
             period_notes)
    if period_notes:
        a.notes = period_notes + [n for n in (a.notes or []) if n not in period_notes]
    a.other_grain = other_grain(a)
    return a


def other_grain(a: Answer) -> Optional[dict]:
    """A versus answer's series record, a series record's map record: the same two sides, season and event, the other
    grain, ready to ask. Not for a comparison across seasons ("2024 X vs 2026 X"), which has no series reading."""
    q = a.query or {}
    intent, f = q.get("intent"), q.get("filters") or {}
    if a.status not in ("ok", "cannot_answer") or intent not in ("versus", "head_to_head"):
        return None
    if f.get("subject_season") or f.get("opponent_season"):
        return None
    ents = a.entities or {}
    left = next((ents[k] for k in ("subject", "player", "team") if k in ents), None)
    right = ents.get("opponent")
    if not (left and right):
        return None
    name = lambda e: e.get("current_name") or e.get("matched_name")  # noqa: E731
    season, champ = f.get("season"), f.get("championship")
    where = (f" at the {season} {champ}" if season else f" at the {champ}") if champ else (f" in {season}" if season else "")
    if intent == "versus":
        return {"grain": "series", "label": "Series record", "question": f"{name(left)} series record against {name(right)}{where}"}
    return {"grain": "map", "label": "Map record", "question": f"{name(left)} map record against {name(right)}{where}"}


def _ask(conn: psycopg.Connection, question: str, parser: str, info: Optional[SchemaInfo], debug: bool,
         with_evidence: bool, evidence_for: Optional[str], evidence_page: int, evidence_page_size: int,
         period_notes: list[str]) -> Answer:
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

    # "this stage", "last year": read against what is in scope, before anything filters on a season
    info = info or SchemaInfo.from_db(conn)
    period = resolve_period(q, info)
    if isinstance(period, Unanswerable):
        return _cannot(question, period, q, used, pre.entities)
    q, note = period
    if note:
        period_notes.append(note)

    if q.intent == "team_membership":
        return _membership_answer(conn, question, q, r, pre, used)
    if q.intent == "placement":
        return _placement_answer(conn, question, q, r, pre, used, info)
    if q.intent == "team_group":
        return _group_answer(conn, question, q, pre, used, info)

    # 3. validate against the live schema
    v = validate(q, info)
    if isinstance(v, Unanswerable):
        # A stat that exists in other seasons is a question away from working.
        seasons_with = sorted(info.stat_keys.get(q.metric or "", set()) or [])
        swapped = None
        # (not for a results-only slice: another season does not give an event player stats it never had)
        if v.code != "results_only" and q.filters.season and seasons_with and q.filters.season not in seasons_with:
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
            never = _never_opposed_reason(q, r, _pairing_sides(conn, q, r)) if "player" in (r.subject_type, r.opponent_type) else None
            if never:
                reason = never
                tips = ["A record against someone counts only the series they were on opposite sides of."]
                notes = []
            elif notes:
                # since 045 a map counts whether or not it has player stats, so the only empty case is a series no
                # source has map results for - the same for a player as for an org
                reason = (f"{left} and {right} met{where}, but none of those series has map results from any source"
                          if r.subject_type != "player" and r.opponent_type != "player" else
                          f"{left} and {right} were on opposite sides{where}, but none of those series has map results "
                          "from any source")
                tips = ["The series results are known; only the per-map breakdown is missing."]
            else:
                reason = f"{left} and {right} never faced each other{where} in the competitions in scope"
                tips = ["Check the spelling, or widen the season; scope is OWCS NA + EMEA main competition."]
            u = Unanswerable(code="no_data", reason=reason, suggestions=tips)
            a = _cannot(question, u, q, used, pre.entities,
                        _alternatives(question, q, r, coverage, met_but_no_maps=bool(notes)))
            a.notes, a.limitations = notes, limitations
            if notes:
                # the note counts the missing series' maps by their score, which may be Liquipedia's
                _attribute(conn, a, lambda: attribution_for(conn, answer_matches(conn, v, r, [], missing_series=True)))
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
    if not rows and q.intent == "head_to_head":
        # a series record with nothing in it: say why - teammates, a player and his own team, or never opposed
        sides = _pairing_sides(conn, q, r)
        left = r.names.get("subject") or r.names.get("player") or r.names.get("team") or ""
        where = f" in {q.filters.season}" if q.filters.season else ""
        reason = _never_opposed_reason(q, r, sides) or (
            f"{left} and {r.names.get('opponent') or ''} were never on opposite sides of a series{where} in scope")
        u = Unanswerable(code="no_data", reason=reason,
                         suggestions=["A series record against someone counts the series they were on opposite sides of."])
        a = _cannot(question, u, q, used, pre.entities, _alternatives(question, q, r, coverage))
        a.coverage, a.notes, a.limitations = coverage, notes, limitations
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
    if q.filters.group:
        # name every team the restriction included, season by season: a group answer that hides its members is a
        # ranking of an unknown set
        members = _group_members(conn, q.filters.group, [q.filters.season] if q.filters.season else None)
        a.notes = [f"{q.filters.group.capitalize()} teams only, each counted in a season it was one: "
                   + _members_phrase(members) + "."] + list(a.notes)
    if q.intent == "head_to_head" and "player" in (r.subject_type, r.opponent_type):
        who = r.names.get("player") or r.names.get("subject") or r.names.get("team") or "the first-named"
        a.notes = [f"Players do not win series, their teams do: this counts the series the two were on opposite sides "
                   f"of (declared line-ups), each scored from {who}'s team's side."] + list(a.notes)
    # the floor is the compiler's, not the question's: handed to the sentence so it can say who was left out
    sentence = render_sentence(dict(a.query, min_maps_floor=c.min_maps_floor,
                                    championship_names=[info.championship_display.get(cid) or info.championships.get(cid)
                                                        for cid in v.championship_ids]),
                               rows, pre.entities, c.description)
    a.sentence = sentence.as_dict() if sentence else None
    if with_evidence:
        # The aggregate is the claim; these are the rows that produce it.
        try:
            a.evidence = fetch_evidence(conn, v, r, rows, evidence_for, evidence_page, evidence_page_size,
                                        c.coverage_stat).as_dict()
        except Exception:
            log_event(log, logging.ERROR, "evidence_failed", intent=q.intent, exc_info=True)
            a.evidence = Evidence(reason="the evidence rows could not be loaded for this answer").as_dict()
    # Every match behind the answer, not the evidence page shown, and with or without evidence asked for: the values
    # were presented either way.
    _attribute(conn, a, lambda: attribution_for(conn, answer_matches(conn, v, r, rows, c.coverage_stat,
                                                                      missing_series=q.intent == "versus")))
    if q.filters.group:
        # the membership is Liquipedia's too: its Stage 1 prize pools are owed alongside the matches'
        members = _group_members(conn, q.filters.group, [q.filters.season] if q.filters.season else None)
        _attribute(conn, a, lambda: attribution_block(list((a.attribution or {}).get("pages") or []) + _group_pages(members)))
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
