"""HTTP surface over the ask pipeline. Read-only, and it never writes SQL of its own.

    POST /ask            a question -> sentence, aggregate, evidence rows, coverage, limitations, query echo
    GET  /query/{slug}   the same answer from a shareable link
    GET  /suggestions    example questions built from entities that have data
    GET  /healthz        liveness plus a database round trip

The answer object is the same one the CLI prints, so there is exactly one
definition of what an answer is. Nothing is cached except the schema snapshot
and the suggestion list, both with a short TTL: an answer is always recomputed,
because the whole point of a shareable link is that it reflects current data.

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
from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .config import Settings, load_settings
from .db import connect
from .limitations import LIMITATIONS
from .logging import get_logger, log_event
from .nlq.evidence import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from .nlq.pipeline import Answer, ask
from .nlq.validate import SchemaInfo
from .web import load_question, remember_question, slug_for, suggestions

log = get_logger("owcsmuse.api")

SCHEMA_TTL_SECONDS = 300
SUGGESTIONS_TTL_SECONDS = 300
MAX_QUESTION_LENGTH = 500


# ------------------------------------------------------------------- resources

class ConnectionPool:
    """A few long-lived connections, handed out one per request.

    Small on purpose: the Supabase session pooler has a connection ceiling, and
    every query here is a short read.
    """

    def __init__(self, settings: Settings, size: int = 4) -> None:
        self.settings = settings
        self.size = size
        self._free: list[psycopg.Connection] = []
        self._created = 0
        self._lock = threading.Lock()

    def _new(self) -> psycopg.Connection:
        return connect(self.settings.database_url, schema=self.settings.db_schema)

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        with self._lock:
            conn = self._free.pop() if self._free else None
            if conn is None:
                self._created += 1
        if conn is None:
            conn = self._new()
        try:
            yield conn
        except Exception:
            # A connection that saw an error is not returned to the pool; an
            # aborted transaction would poison the next request.
            with self._lock:
                self._created -= 1
            try:
                conn.close()
            except Exception:
                pass
            raise
        else:
            with self._lock:
                if len(self._free) < self.size:
                    self._free.append(conn)
                    return
                self._created -= 1
            conn.close()

    def close(self) -> None:
        with self._lock:
            conns, self._free, self._created = self._free, [], 0
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
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows,
        },
        "evidence": answer.evidence,
        "coverage": answer.coverage,
        "limitations": answer.limitations,
        "notes": answer.notes,
        "entities": answer.entities,
        "candidates": answer.candidates,
        "query": answer.query,
        "code": answer.code,
        "reason": answer.reason,
        "suggestions": answer.suggestions,
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
    app.state.pool = pool
    app.state.settings = settings

    def get_pool() -> ConnectionPool:
        return app.state.pool

    def _schema(conn: psycopg.Connection) -> SchemaInfo:
        return schema_cache.get(lambda: SchemaInfo.from_db(conn))

    def _answer(conn: psycopg.Connection, question: str, parser: str, page: int, page_size: int,
                evidence_for: Optional[str], with_evidence: bool) -> dict[str, Any]:
        t0 = time.perf_counter()
        answer = ask(conn, question, parser=parser, info=_schema(conn), with_evidence=with_evidence,
                     evidence_for=evidence_for, evidence_page=page, evidence_page_size=page_size)
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
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    cur.fetchone()
                conn.commit()
        except Exception as exc:
            log_event(log, logging.ERROR, "healthz_failed", exc_info=True)
            raise HTTPException(status_code=503, detail=f"database unavailable: {type(exc).__name__}") from exc
        return {"ok": True, "version": __version__}

    @app.post("/ask", summary="ask a question")
    def post_ask(body: AskRequest, pool: ConnectionPool = Depends(get_pool)) -> dict[str, Any]:
        with pool.connection() as conn:
            return _answer(conn, body.question, body.parser, body.page, body.page_size,
                           body.evidence_for, body.with_evidence)

    @app.get("/query/{slug}", summary="a shared question, re-run against current data")
    def get_query(
        slug: str = Path(min_length=4, max_length=64),
        page: int = Query(default=1, ge=1, le=10_000),
        page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
        evidence_for: Optional[str] = Query(default=None, max_length=200),
        pool: ConnectionPool = Depends(get_pool),
    ) -> dict[str, Any]:
        with pool.connection() as conn:
            saved = load_question(conn, slug)
            if not saved:
                raise HTTPException(status_code=404, detail=f"no question is saved under '{slug}'")
            payload = _answer(conn, saved.question, saved.parser, page, page_size, evidence_for, True)
        payload["shared"] = {"times_asked": saved.times_asked, "parsed_when_saved": saved.structured_query}
        return payload

    @app.get("/suggestions", summary="example questions with data behind them")
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


__all__ = ["AskRequest", "ConnectionPool", "answer_payload", "app_factory", "create_app", "serve", "slug_for"]
