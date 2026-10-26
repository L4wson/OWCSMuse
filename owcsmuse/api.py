"""HTTP surface over the ask pipeline. Read-only, and it never writes SQL of its own.

    POST /ask            a question -> sentence, aggregate, evidence rows, coverage, limitations, query echo
    GET  /query/{slug}   the same answer from a shareable link
    GET  /suggestions    example questions built from entities that have data
    GET  /healthz        liveness plus a database round trip

The answer object is the same one the CLI prints, so there is exactly one
definition of what an answer is. Nothing is cached except the schema snapshot
and the suggestion list, both with a short TTL: an answer is always recomputed,
because the whole point of a shareable link is that it reflects current data.

Every answer, refusal and failure writes one query_log row (`querylog.py`): the
question and how it was read, never who asked. `owcsmuse queries` reports on it.

Requires the optional `api` extra (`pip install -e ".[api]"`).
"""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Iterator, Literal, Optional

import psycopg
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__, querylog
from .config import Settings, load_settings
from .db import connect
from .limitations import LIMITATIONS
from .log import get_logger, log_event
from .nlq.columns import describe as describe_columns
from .nlq.evidence import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from .nlq.pipeline import Answer, ask
from .nlq.validate import SchemaInfo
from .throttle import BUSY_MESSAGE, Throttle, client_key, rate_limited_message
from .web import describe_parse_change, load_question, remember_question, slug_for, suggestions

log = get_logger("owcsmuse.api")

SCHEMA_TTL_SECONDS = 300
SUGGESTIONS_TTL_SECONDS = 300
MAX_QUESTION_LENGTH = 500


# ------------------------------------------------------------------- resources

class PoolBusy(Exception):
    """Every connection the API may open is in use, and none came free in time."""


class ConnectionPool:
    """A few long-lived connections, handed out one per request, and a cap on how many are open at once.

    Small on purpose: the Supabase session pooler has a connection ceiling, and
    every query here is a short read. Without the cap every request beyond the
    idle ones opened a new connection, up to the server's 40 worker threads, so
    one looping client could exhaust the pooler for the site and the ingest.
    """

    def __init__(self, settings: Settings, size: int = 4, max_open: Optional[int] = None,
                 wait_seconds: Optional[float] = None) -> None:
        self.settings = settings
        self.size = size                      # idle connections kept
        self.max_open = max_open if max_open is not None else settings.api_db_max_connections
        self.wait_seconds = wait_seconds if wait_seconds is not None else settings.api_db_wait_seconds
        self._slots = threading.BoundedSemaphore(self.max_open)
        self._free: list[psycopg.Connection] = []
        self._lock = threading.Lock()

    def _new(self) -> psycopg.Connection:
        return connect(self.settings.database_url, schema=self.settings.db_schema)

    @contextmanager
    def connection(self, wait_seconds: Optional[float] = None) -> Iterator[psycopg.Connection]:
        if not self._slots.acquire(timeout=self.wait_seconds if wait_seconds is None else wait_seconds):
            raise PoolBusy()
        try:
            with self._lock:
                conn = self._free.pop() if self._free else None
            conn = conn or self._new()
        except BaseException:
            self._slots.release()
            raise
        try:
            yield conn
        except Exception:
            # A connection that saw an error is not returned to the pool; an
            # aborted transaction would poison the next request.
            try:
                conn.close()
            except Exception:
                pass
            self._slots.release()
            raise
        else:
            with self._lock:
                keep = len(self._free) < self.size
                if keep:
                    self._free.append(conn)
            if not keep:
                conn.close()
            self._slots.release()

    def close(self) -> None:
        with self._lock:
            conns, self._free = self._free, []
        for c in conns:
            try:
                c.close()
            except Exception:
                pass


class _Cached:
    """One value with a TTL, recomputed on demand. Not a cache of answers."""

    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._value: Any = None
        self._at = 0.0
        self._lock = threading.Lock()

    def get(self, build) -> Any:
        now = time.monotonic()
        with self._lock:
            if self._value is not None and now - self._at < self.ttl:
                return self._value
        value = build()
        with self._lock:
            self._value, self._at = value, now
        return value

    def clear(self) -> None:
        with self._lock:
            self._value, self._at = None, 0.0


# ---------------------------------------------------------------- request model

class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    parser: Literal["rules", "llm", "auto"] = "rules"
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    evidence_for: Optional[str] = Field(default=None, max_length=200)
    with_evidence: bool = True


def json_safe(value: Any) -> Any:
    """Numbers as numbers.

    Postgres numeric arrives as Decimal, which JSON-serializes to a string; a
    client that has to parse "9730" before it can add it up is being handed
    something it cannot plot.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def answer_payload(answer: Answer, slug: str) -> dict[str, Any]:
    """One JSON shape for every answer, whatever its status.

    The aggregate is the claim, `evidence` holds the rows that produce it, and
    `query` echoes the structured object the question parsed to - so a client can
    show what was understood without guessing.
    """
    rows = json_safe(answer.rows or [])
    return json_safe({
        "slug": slug,
        "url": f"/query/{slug}",
        "status": answer.status,
        "question": answer.question,
        "sentence": answer.sentence,
        "aggregate": {
            "description": answer.description,
            # {key, label, type} per column: the schema says what a column is, so
            # no client has to infer it from the name of a key.
            "columns": describe_columns(rows),
            "rows": rows,
        },
        "evidence": answer.evidence,
        "coverage": answer.coverage,
        "limitations": answer.limitations,
        "attribution": answer.attribution,
        "notes": answer.notes,
        "entities": answer.entities,
        "candidates": answer.candidates,
        "query": answer.query,
        "code": answer.code,
        "reason": answer.reason,
        "suggestions": answer.suggestions,
        "alternatives": answer.alternatives,
        "other_grain": answer.other_grain,
        "parser": answer.parser,
    })


def create_app(settings: Optional[Settings] = None, pool: Optional[ConnectionPool] = None) -> FastAPI:
    settings = settings or load_settings()
    pool = pool or ConnectionPool(settings)
    schema_cache = _Cached(SCHEMA_TTL_SECONDS)
    suggestion_cache = _Cached(SUGGESTIONS_TTL_SECONDS)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        _app.state.pool.close()

    app = FastAPI(
        lifespan=lifespan,
        title="OWCS Muse",
        version=__version__,
        summary="Overwatch Champions Series stats: questions in, a sentence, an aggregate and the rows behind it out.",
    )
    # A browser client is the point of this layer; the API is read-only and
    # carries no credentials or cookies, so an open origin policy costs nothing.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.exception_handler(psycopg.OperationalError)
    @app.exception_handler(psycopg.InterfaceError)
    async def _database_down(request: Request, exc: Exception) -> JSONResponse:
        """503, not 500: the service is up, its warehouse is not, and nothing was refused."""
        log_event(log, logging.ERROR, "database_unavailable", path=request.url.path,
                  error=f"{type(exc).__name__}: {str(exc)[:200]}")
        return JSONResponse(
            status_code=503,
            content={"detail": f"database unavailable: {type(exc).__name__}"},
        )
    @app.exception_handler(PoolBusy)
    async def _busy(request: Request, exc: Exception) -> JSONResponse:
        """503 with a message a person can act on: the service is up and will answer, just not this instant."""
        log_event(log, logging.WARNING, "api_busy", path=request.url.path)
        return JSONResponse(status_code=503, headers={"Retry-After": "5"},
                            content={"detail": BUSY_MESSAGE, "reason": "busy", "retry_after": 5})

    app.state.pool = pool
    app.state.settings = settings
    throttle = Throttle(settings.api_rate_burst, settings.api_rate_per_minute)
    app.state.throttle = throttle

    def per_client(request: Request) -> None:
        """Questions and their links are throttled per client; /, /healthz and the docs are not."""
        client = client_key({k.lower(): v for k, v in request.headers.items()}, request.client.host if request.client else None)
        verdict = app.state.throttle.check(client)
        if not verdict.allowed:
            log_event(log, logging.WARNING, "rate_limited", path=request.url.path, retry_after=verdict.retry_after)
            raise HTTPException(status_code=429, headers={"Retry-After": str(verdict.retry_after)},
                                detail=rate_limited_message(verdict.retry_after))

    def get_pool() -> ConnectionPool:
        return app.state.pool

    def _schema(conn: psycopg.Connection) -> SchemaInfo:
        return schema_cache.get(lambda: SchemaInfo.from_db(conn))

    def _log_query(row: dict[str, Any]) -> None:
        """Write one query_log row on its own connection. Never raises."""
        try:
            with app.state.pool.connection() as conn:
                querylog.record(conn, row)
        except Exception:
            log_event(log, logging.WARNING, "query_log_not_written", status=row.get("status"), exc_info=True)

    def _answer(conn: psycopg.Connection, question: str, parser: str, page: int, page_size: int,
                evidence_for: Optional[str], with_evidence: bool,
                tasks: BackgroundTasks, source: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            answer = ask(conn, question, parser=parser, info=_schema(conn), with_evidence=with_evidence,
                         evidence_for=evidence_for, evidence_page=page, evidence_page_size=page_size)
        except Exception as exc:
            # Background tasks do not run when the handler raises, so a failure
            # is logged here, before the error response - and an error is the
            # row most worth having. Not when the connection itself broke: the
            # database is down, and a fresh connect would only delay the 503.
            if not (conn.closed or conn.broken):
                _log_query(querylog.row_for(question, source, round((time.perf_counter() - t0) * 1000), error=exc))
            raise
        latency_ms = round((time.perf_counter() - t0) * 1000)
        # After the response is sent: the log write costs the asker no time, and
        # cannot fail their answer.
        tasks.add_task(_log_query, querylog.row_for(question, source, latency_ms, answer))
        slug = remember_question(conn, question, parser, answer.query)
        log_event(log, logging.INFO, "ask",
                  question=question[:200], parser=answer.parser, status=answer.status, code=answer.code,
                  rows=len(answer.rows), evidence_rows=len((answer.evidence or {}).get("rows") or []),
                  slug=slug, seconds=round(time.perf_counter() - t0, 3))
        return answer_payload(answer, slug)

    @app.get("/", summary="what this service is")
    def root() -> dict[str, Any]:
        return {
            "service": "owcsmuse",
            "version": __version__,
            "scope": "OWCS NA + EMEA main competition, 2024-2026",
            "endpoints": {
                "POST /ask": "ask a question",
                "GET /query/{slug}": "re-run a shared question against current data",
                "GET /suggestions": "example questions that have data behind them",
                "GET /healthz": "liveness and a database round trip",
            },
            "limitations": [{"id": lim.id, "title": lim.title} for lim in LIMITATIONS],
        }

    @app.get("/healthz", summary="liveness")
    def healthz(pool: ConnectionPool = Depends(get_pool)) -> dict[str, Any]:
        try:
            # Fly restarts a machine that fails this check: a service that is only busy must not fail it, or a burst
            # of questions becomes an outage. So it never queues for a connection; all in use means up, and busy.
            with pool.connection(wait_seconds=0) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    cur.fetchone()
                conn.commit()
        except PoolBusy:
            return {"ok": True, "version": __version__, "busy": True}
        except Exception as exc:
            log_event(log, logging.ERROR, "healthz_failed", exc_info=True)
            raise HTTPException(status_code=503, detail=f"database unavailable: {type(exc).__name__}") from exc
        return {"ok": True, "version": __version__}

    @app.post("/ask", summary="ask a question", dependencies=[Depends(per_client)])
    def post_ask(body: AskRequest, tasks: BackgroundTasks, pool: ConnectionPool = Depends(get_pool)) -> dict[str, Any]:
        with pool.connection() as conn:
            return _answer(conn, body.question, body.parser, body.page, body.page_size,
                           body.evidence_for, body.with_evidence, tasks, "ask")

    @app.get("/query/{slug}", summary="a shared question, re-run against current data", dependencies=[Depends(per_client)])
    def get_query(
        slug: str = Path(min_length=4, max_length=64),
        page: int = Query(default=1, ge=1, le=10_000),
        page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
        evidence_for: Optional[str] = Query(default=None, max_length=200),
        *,
        tasks: BackgroundTasks,
        pool: ConnectionPool = Depends(get_pool),
    ) -> dict[str, Any]:
        with pool.connection() as conn:
            saved = load_question(conn, slug)
            if not saved:
                raise HTTPException(status_code=404, detail=f"no question is saved under '{slug}'")
            payload = _answer(conn, saved.question, saved.parser, page, page_size, evidence_for, True, tasks, "shared")
        changes = describe_parse_change(saved.structured_query, payload.get("query"))
        payload["shared"] = {
            "times_asked": saved.times_asked,
            "parsed_when_saved": saved.structured_query,
            "parse_changed": bool(changes),
            "parse_change": changes,
        }
        return payload

    @app.get("/suggestions", summary="example questions with data behind them", dependencies=[Depends(per_client)])
    def get_suggestions(pool: ConnectionPool = Depends(get_pool)) -> dict[str, Any]:
        with pool.connection() as conn:
            return suggestion_cache.get(lambda: suggestions(conn).as_dict())

    return app


def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    import uvicorn

    if reload:
        uvicorn.run("owcsmuse.api:app_factory", host=host, port=port, reload=True, factory=True)
    else:
        uvicorn.run(create_app(), host=host, port=port)


def app_factory() -> FastAPI:
    return create_app()


__all__ = ["AskRequest", "ConnectionPool", "PoolBusy", "answer_payload", "app_factory", "create_app", "serve", "slug_for"]
