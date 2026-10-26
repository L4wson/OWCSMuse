"""The query log: one row per answered question, and the report that reads it.

What a beta needs to know is which questions fail and why. Every answer the
API serves - ok, clarify, refusal, or an exception - writes a row to
query_log. The row holds the question text and how it was read, and nothing
about who asked: no IP, no user agent, no session.

Writing a row must never cost the asker their answer, so `record` swallows
every failure (a missing table, a dropped connection, a full disk) and reports
it in the service log instead.

The report groups the rows the way a person fixing the parser wants them:
refusals by reason code, questions that parsed to nothing or found no rows,
the most-asked overall and failing, and clusters of phrasings that share a
shape once their names and seasons are taken out.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

import psycopg
from psycopg.types.json import Jsonb

from .log import get_logger, log_event
from .web import normalize_question

log = get_logger("owcsmuse.querylog")

# The pipeline says cannot_answer; the log says refusal, the word the report uses.
_STATUS = {"ok": "ok", "clarify": "clarify", "cannot_answer": "refusal"}

# A failed answer: anything but ok. An error is a failure too, and the worst kind.
FAILED = ("clarify", "refusal", "error")


# ------------------------------------------------------------------- writing

def _entity(e: dict) -> dict:
    return {"type": e.get("entity_type"), "id": e.get("entity_id"), "name": e.get("current_name")}


def entities_of(answer: Any) -> Optional[dict]:
    """role -> {type, id, name}, or role -> {candidates: [...]} on a clarify.

    The full candidate dicts carry seasons, match counts and a rewritten
    question each; the log needs only which entity it was.
    """
    out: dict[str, Any] = {role: _entity(e) for role, e in (answer.entities or {}).items()}
    for role, cands in (answer.candidates or {}).items():
        out[role] = {"candidates": [_entity(c) for c in cands]}
    return out or None


def row_for(question: str, source: str, latency_ms: int, answer: Any = None,
            error: Optional[BaseException] = None) -> dict[str, Any]:
    """The query_log row for one answer, or for the exception that replaced it."""
    if answer is None:
        return {"source": source, "question": question, "parser": None, "status": "error",
                "reason_code": type(error).__name__ if error else None, "structured_query": None,
                "entities": None, "row_count": None, "latency_ms": latency_ms}
    status = _STATUS.get(answer.status, answer.status)
    return {"source": source, "question": question, "parser": answer.parser, "status": status,
            "reason_code": answer.code, "structured_query": answer.query, "entities": entities_of(answer),
            "row_count": len(answer.rows or []) if status == "ok" else None, "latency_ms": latency_ms}


# Retention (docs/api-and-frontend.md, "Size and retention"): failures are what the log is for, so they are kept
# longer than answers that went well.
KEEP_OK_DAYS = 90
KEEP_ALL_DAYS = 365


def prune(conn: psycopg.Connection, keep_ok_days: int = KEEP_OK_DAYS, keep_all_days: int = KEEP_ALL_DAYS) -> dict[str, int]:
    """Delete answered questions older than `keep_ok_days`, and every row older than `keep_all_days`. Commits."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM query_log WHERE status = 'ok' AND asked_at < now() - make_interval(days => %s)",
                    (keep_ok_days,))
        ok = cur.rowcount
        cur.execute("DELETE FROM query_log WHERE asked_at < now() - make_interval(days => %s)", (keep_all_days,))
        old = cur.rowcount
    conn.commit()
    return {"ok_older_than_days": keep_ok_days, "ok_deleted": ok, "all_older_than_days": keep_all_days,
            "older_deleted": old}


def record(conn: psycopg.Connection, row: dict[str, Any]) -> bool:
    """Insert one row. Never raises: a log that cannot be written is not the asker's problem."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_log (source, question, parser, status, reason_code,
                                       structured_query, entities, row_count, latency_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (row["source"], row["question"].strip(), row["parser"], row["status"], row["reason_code"],
                 Jsonb(row["structured_query"]) if row["structured_query"] else None,
                 Jsonb(row["entities"]) if row["entities"] else None,
                 row["row_count"], row["latency_ms"]),
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        log_event(log, logging.WARNING, "query_log_not_written", status=row.get("status"), exc_info=True)
        return False


# ------------------------------------------------------------------- reading

@dataclass
class Logged:
    """One asked question, from query_log or from a replay of saved_queries."""
    question: str
    status: str
    reason_code: Optional[str] = None
    structured_query: Optional[dict] = None
    row_count: Optional[int] = None
    asks: int = 1                       # a replayed saved query stands for times_asked asks
    asked_at: Optional[datetime] = None
    latency_ms: Optional[int] = None

    @property
    def failed(self) -> bool:
        return self.status in FAILED

    @property
    def unparsed(self) -> bool:
        return self.structured_query is None and self.status != "ok"

    @property
    def no_rows(self) -> bool:
        return self.reason_code == "no_data" or (self.status == "ok" and self.row_count == 0)


def load(conn: psycopg.Connection, since: Optional[datetime] = None,
         source: Optional[str] = None) -> list[Logged]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT question, status, reason_code, structured_query, row_count, asked_at, latency_ms
              FROM query_log
             WHERE (%s::timestamptz IS NULL OR asked_at >= %s)
               AND (%s::text IS NULL OR source = %s)
             ORDER BY asked_at
            """,
            (since, since, source, source),
        )
        rows = cur.fetchall()
    conn.commit()
    return [Logged(question=r["question"], status=r["status"], reason_code=r["reason_code"],
                   structured_query=r["structured_query"], row_count=r["row_count"],
                   asked_at=r["asked_at"], latency_ms=r["latency_ms"]) for r in rows]


def replay_saved(conn: psycopg.Connection, since: Optional[datetime] = None) -> list[Logged]:
    """saved_queries re-asked through today's pipeline, for the weeks before query_log existed.

    saved_queries never recorded how an answer turned out, so the only way to
    know is to ask again. That gives today's outcome, not the one the asker
    saw: a question the parser has since learned shows as ok. Nothing is
    written - `ask` only reads, and neither saved_queries nor query_log is touched.
    """
    from .nlq.pipeline import ask
    from .nlq.validate import SchemaInfo

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT question, parser, times_asked, created_at FROM saved_queries
             WHERE (%s::timestamptz IS NULL OR last_asked_at >= %s) ORDER BY created_at
            """,
            (since, since),
        )
        saved = cur.fetchall()
    conn.commit()
    info = SchemaInfo.from_db(conn)
    out: list[Logged] = []
    for s in saved:
        try:
            a = ask(conn, s["question"], parser=s["parser"], info=info, with_evidence=False)
            r = row_for(s["question"], "ask", 0, a)
        except Exception as exc:
            r = row_for(s["question"], "ask", 0, error=exc)
        out.append(Logged(question=s["question"], status=r["status"], reason_code=r["reason_code"],
                          structured_query=r["structured_query"], row_count=r["row_count"],
                          asks=s["times_asked"], asked_at=s["created_at"]))
    return out


# ------------------------------------------------------------------ clustering

_ID_TOKEN = re.compile(r"\b(player|team|org):[0-9a-z-]+", re.I)
_SEASON = re.compile(r"\b20\d\d\b")
_WORD = re.compile(r"[a-z0-9/<>-]+")
_STOP = frozenset("the a an in of on is was are to for did does do".split())
_NAME_ROLES = ("player", "team", "opponent", "subject")


def template(item: Logged) -> str:
    """The question with its names and seasons taken out: its shape.

    Names come from the parse, which knows which words were names; an id
    token from a clarify follow-up is a name too. A question that parsed to
    nothing keeps its words, so only its seasons and ids are masked.
    """
    text = normalize_question(item.question)
    text = _ID_TOKEN.sub(lambda m: f"<{m.group(1).lower()}>", text)
    filters = (item.structured_query or {}).get("filters") or {}
    names = sorted(((filters[r], r) for r in _NAME_ROLES if filters.get(r)), key=lambda x: -len(x[0]))
    for name, role in names:
        if _ID_TOKEN.fullmatch(name):
            continue
        text = re.sub(re.escape(normalize_question(name)), f"<{role}>", text)
    return _SEASON.sub("<season>", text).rstrip(" ?.!")


def _tokens(t: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(t) if w not in _STOP)


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a or b else 1.0


@dataclass
class Cluster:
    status: str
    reason_code: Optional[str]
    shape: str                                  # the most-asked template in it
    asks: int = 0
    questions: Counter = field(default_factory=Counter)   # normalized question -> asks
    templates: Counter = field(default_factory=Counter)

    def as_dict(self, examples: int = 5) -> dict[str, Any]:
        return {"status": self.status, "reason_code": self.reason_code, "shape": self.shape, "asks": self.asks,
                "distinct_questions": len(self.questions),
                "examples": [q for q, _ in self.questions.most_common(examples)]}


def cluster(items: Iterable[Logged], threshold: float = 0.5) -> list[Cluster]:
    """Failing questions grouped by outcome and shape, biggest first.

    Two questions share a cluster when they failed the same way (status and
    reason code) and their templates are equal or overlap by `threshold`
    (Jaccard on words). Greedy, so it is a reading aid, not a classifier:
    twenty variants of one bug should land together, and a stray pairing is
    visible in the examples.
    """
    by_outcome: dict[tuple, Counter] = defaultdict(Counter)
    by_template: dict[tuple, Counter] = defaultdict(Counter)
    for it in items:
        if not it.failed:
            continue
        key = (it.status, it.reason_code)
        t = template(it)
        by_outcome[key][t] += it.asks
        by_template[key + (t,)][normalize_question(it.question)] += it.asks

    out: list[Cluster] = []
    for (status, code), templates in by_outcome.items():
        groups: list[tuple[frozenset, Cluster]] = []
        for t, asks in templates.most_common():
            tok = _tokens(t)
            home = next((c for seed, c in groups if _jaccard(seed, tok) >= threshold), None)
            if home is None:
                home = Cluster(status=status, reason_code=code, shape=t)
                groups.append((tok, home))
            home.asks += asks
            home.templates[t] += asks
            home.questions.update(by_template[(status, code, t)])
        out += [c for _, c in groups]
    return sorted(out, key=lambda c: (-c.asks, -len(c.questions), c.shape))


# --------------------------------------------------------------------- report

def _top(counter: Counter, n: int) -> list[dict[str, Any]]:
    return [{"question": q, "asks": k} for q, k in counter.most_common(n)]


def build_report(items: list[Logged], top: int = 15) -> dict[str, Any]:
    asks = sum(i.asks for i in items)
    status = Counter()
    for i in items:
        status[i.status] += i.asks

    refusals: dict[str, dict[str, Any]] = {}
    for i in items:
        if i.status == "ok":
            continue
        code = i.reason_code or "(none)"
        r = refusals.setdefault(code, {"reason_code": code, "status": i.status, "asks": 0, "questions": Counter()})
        r["asks"] += i.asks
        r["questions"][normalize_question(i.question)] += i.asks
    by_code = sorted(refusals.values(), key=lambda r: (-r["asks"], r["reason_code"]))

    overall, failed, unparsed, no_rows = Counter(), Counter(), Counter(), Counter()
    for i in items:
        q = normalize_question(i.question)
        overall[q] += i.asks
        if i.failed:
            failed[q] += i.asks
        if i.unparsed:
            unparsed[q] += i.asks
        if i.no_rows:
            no_rows[q] += i.asks

    latencies = sorted(i.latency_ms for i in items if i.latency_ms)
    return {
        "asks": asks,
        "distinct_questions": len(overall),
        "first": min((i.asked_at for i in items if i.asked_at), default=None),
        "last": max((i.asked_at for i in items if i.asked_at), default=None),
        "by_status": dict(status.most_common()),
        "latency_ms_p50": latencies[len(latencies) // 2] if latencies else None,
        "latency_ms_p95": latencies[int(len(latencies) * 0.95)] if latencies else None,
        "failures_by_code": [{"reason_code": r["reason_code"], "status": r["status"], "asks": r["asks"],
                              "distinct_questions": len(r["questions"]),
                              "examples": [q for q, _ in r["questions"].most_common(5)]} for r in by_code],
        "parsed_to_nothing": _top(unparsed, top),
        "no_rows": _top(no_rows, top),
        "most_asked": _top(overall, top),
        "most_asked_failed": _top(failed, top),
        "clusters": [c.as_dict() for c in cluster(items) if len(c.questions) > 1][:top],
    }


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "-"


def render_report(r: dict[str, Any]) -> str:
    asks = r["asks"]
    if not asks:
        return "no questions logged in this window"
    when = ""
    if r["first"] and r["last"]:
        when = f", {r['first']:%Y-%m-%d} to {r['last']:%Y-%m-%d}"
    lines = [f"{asks} asks, {r['distinct_questions']} distinct questions{when}"]
    lines.append("  " + "  ".join(f"{s} {n} ({_pct(n, asks)})" for s, n in r["by_status"].items()))
    if r["latency_ms_p50"] is not None:
        lines.append(f"  latency p50 {r['latency_ms_p50']} ms, p95 {r['latency_ms_p95']} ms")

    lines.append("\nFailures by reason code")
    for f in r["failures_by_code"]:
        lines.append(f"  {f['asks']:5}  {f['reason_code']:22} {f['status']:8} {f['distinct_questions']} distinct")
        for q in f["examples"][:3]:
            lines.append(f"           e.g. {q}")

    for title, key in (("Parsed to nothing", "parsed_to_nothing"), ("Found no rows (no_data)", "no_rows"),
                       ("Most asked", "most_asked"), ("Most asked that failed", "most_asked_failed")):
        lines.append(f"\n{title}")
        if not r[key]:
            lines.append("  (none)")
        for q in r[key]:
            lines.append(f"  {q['asks']:5}  {q['question']}")

    lines.append("\nClusters of failing phrasings (2+ distinct questions)")
    if not r["clusters"]:
        lines.append("  (none)")
    for c in r["clusters"]:
        lines.append(f"  {c['asks']:5}  [{c['status']}/{c['reason_code']}] {c['shape']}"
                     f"  ({c['distinct_questions']} variants)")
        for q in c["examples"][:4]:
            lines.append(f"           {q}")
    return "\n".join(lines)
