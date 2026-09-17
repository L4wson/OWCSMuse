"""ask(): question -> parse -> resolve -> validate -> compile -> execute -> Answer."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import psycopg

from ..aggregates import stat_coverage_summary
from ..logging import get_logger, log_event
from ..resolve import Candidate, resolve
from .compile import Compiled, Resolved, compile_query
from .parser import parse_question
from .schema import StructuredQuery, Unanswerable
from .validate import SchemaInfo, Validated, validate

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
    coverage: Optional[dict] = None
    notes: list[str] = field(default_factory=list)
    description: Optional[str] = None
    sql: Optional[str] = None
    params: Optional[list] = None
    parser: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cannot(question: str, u: Unanswerable, query: Optional[StructuredQuery] = None, parser: Optional[str] = None) -> Answer:
    return Answer(status="cannot_answer", question=question, query=query.compact() if query else None, code=u.code,
                  reason=u.reason, suggestions=list(u.suggestions), parser=parser)


def question_hint(name: str, entity_id: str) -> str:
    """How to re-ask using an id instead of an ambiguous name."""
    return entity_id


def _decide(cands: list[Candidate]) -> tuple[Optional[Candidate], bool]:
    """(chosen, ambiguous). A tie between different entities is ambiguous."""
    if not cands:
        return None, False
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
        etype = {"player": "player", "team": "team", "opponent": "team", "subject": None}[role]
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
        if role == "player" or (role == "subject" and chosen.entity_type == "player"):
            r.player_id = chosen.entity_id
        elif role == "opponent":
            r.opponent_id = chosen.entity_id
        else:
            r.team_id = chosen.entity_id
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
        debug: bool = False) -> Answer:
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
    if not rows:
        u = Unanswerable(code="no_data", reason="the query is valid but nothing in scope matches these filters",
                         suggestions=["Loosen the season / championship / map filter, or check `status` for what has been ingested."])
        a = _cannot(question, u, q, used)
        a.entities = pre.entities
        a.coverage = coverage
        a.notes = notes
        if debug:
            a.sql, a.params = c.sql, c.params
        return a
    a = Answer(status="ok", question=question, query=q.compact(), entities=pre.entities, rows=rows, coverage=coverage,
               notes=notes, description=c.description, parser=used)
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


def render_text(a: Answer, max_rows: int = 25) -> str:
    lines: list[str] = []
    if a.status == "cannot_answer":
        lines.append(f"Can't answer that ({a.code}): {a.reason}")
        for s in a.suggestions:
            lines.append(f"  - {s}")
        for n in a.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)
    if a.status == "clarify":
        lines.append(f"Need a clarification: {a.reason}")
        for role, cands in a.candidates.items():
            for c in cands:
                lines.append(f"  - {c['current_name']}  [{c['entity_type']} {c['entity_id']}] matched '{c['matched_name']}' ({c['name_kind']}, score {c['score']})")
        for tip in (a.suggestions or ["Re-ask with the exact name, or with the id shown in brackets."]):
            lines.append(tip)
        return "\n".join(lines)

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
    for n in a.notes:
        lines.append(f"  note: {n}")
    return "\n".join(lines)
