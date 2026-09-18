"""ask(): question -> parse -> resolve -> validate -> compile -> execute -> Answer."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import psycopg

from ..aggregates import stat_coverage_summary
from ..limitations import applicable as applicable_limitations, entity_match_filter
from ..logging import get_logger, log_event
from ..resolve import Candidate, resolve
from .compile import Compiled, Resolved, compile_query
from .evidence import DEFAULT_PAGE_SIZE, Evidence, fetch_evidence, fetch_missing_series, is_map_grain
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
    suggestions: list[str] = field(default_factory=list)
    candidates: dict[str, list[dict]] = field(default_factory=dict)   # role -> candidate dicts (clarify)
    entities: dict[str, dict] = field(default_factory=dict)           # role -> resolved entity
    rows: list[dict] = field(default_factory=list)
    sentence: Optional[dict] = None     # the one-sentence claim, from a template
    evidence: Optional[dict] = None     # the rows that produce the aggregate
    coverage: Optional[dict] = None
    notes: list[str] = field(default_factory=list)
    limitations: list[dict] = field(default_factory=list)   # known gaps this slice lands in
    description: Optional[str] = None
    sql: Optional[str] = None
    params: Optional[list] = None
    parser: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cannot(question: str, u: Unanswerable, query: Optional[StructuredQuery] = None, parser: Optional[str] = None,
            entities: Optional[dict[str, dict]] = None) -> Answer:
    a = Answer(status="cannot_answer", question=question, query=query.compact() if query else None, code=u.code,
               reason=u.reason, suggestions=list(u.suggestions), parser=parser, entities=dict(entities or {}))
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


def resolve_entities(conn: psycopg.Connection, q: StructuredQuery) -> tuple[Optional[Resolved], Optional[Answer]]:
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
            identical = sum(1 for c in cands if (c.current_name or "").lower() == (cands[0].current_name or "").lower())
            if identical > 1:
                tip = ("These are different FACEIT entities with the same name, so no spelling tells them apart. "
                       f"Re-ask with the id, e.g. \"{question_hint(name, cands[0].entity_id)}\".")
            else:
                tip = "Re-ask with the exact name, or with the id shown in brackets."
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
    r, pre = resolve_entities(conn, q)
    if r is None:
        pre.question = question
        pre.query = q.compact()
        pre.parser = used
        return pre
    q = _retarget(q, r)

    # 3. validate against the live schema
    info = info or SchemaInfo.from_db(conn)
    v = validate(q, info)
    if isinstance(v, Unanswerable):
        return _cannot(question, v, q, used)

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
        grain="series" if series_grain else "map")
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
            a = _cannot(question, u, q, used, pre.entities)
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
        a = _cannot(question, u, q, used, pre.entities)
        a.limitations = limitations
        if debug:
            a.sql, a.params = c.sql, c.params
        return a
    if not rows:
        u = Unanswerable(code="no_data", reason="the query is valid but nothing in scope matches these filters",
                         suggestions=["Loosen the season / championship / map filter, or check `status` for what has been ingested."])
        a = _cannot(question, u, q, used, pre.entities)
        a.coverage = coverage
        a.notes = notes
        a.limitations = limitations
        if debug:
            a.sql, a.params = c.sql, c.params
        return a
    a = Answer(status="ok", question=question, query=q.compact(), entities=pre.entities, rows=rows, coverage=coverage,
               notes=notes, limitations=limitations, description=c.description, parser=used)
    sentence = render_sentence(a.query, rows, pre.entities, c.description)
    a.sentence = sentence.as_dict() if sentence else None
    if with_evidence:
        # The aggregate is the claim; these are the rows that produce it.
        try:
            a.evidence = fetch_evidence(conn, v, r, rows, evidence_for, evidence_page, evidence_page_size,
                                        c.coverage_stat).as_dict()
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
        lines += _evidence_lines(a, evidence_rows)
        for n in a.notes:
            lines.append(f"  note: {n}")
        for lim in a.limitations:
            lines.append(f"  known limitation ({lim['id']}): {lim['note']}")
        return "\n".join(lines)
    if a.status == "clarify":
        lines.append(f"Need a clarification: {a.reason}")
        for cands in a.candidates.values():
            for c in cands:
                lines.append(f"  - {c['current_name']}  [{c['entity_type']} {c['entity_id']}] matched '{c['matched_name']}' ({c['name_kind']}, score {c['score']})")
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
        cols = [c for c in rows[0].keys() if not c.endswith("_id")]
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
    return "\n".join(lines)
