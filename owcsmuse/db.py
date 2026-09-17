"""Postgres connection, plain-SQL migrations, and the raw payload store."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .logging import get_logger, log_event

log = get_logger("owcsmuse.db")

_MIGRATION_RE = re.compile(r"^(\d+)_.+\.sql$")


def connect(database_url: str, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row, autocommit=autocommit)


def migrate(conn: psycopg.Connection, migrations_dir: str | Path) -> list[str]:
    """Apply every migrations/NNN_*.sql not yet recorded, in order. Returns applied names."""
    path = Path(migrations_dir)
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("SELECT version FROM schema_migrations")
        done = {r["version"] for r in cur.fetchall()}
    conn.commit()

    files = sorted(p for p in path.iterdir() if _MIGRATION_RE.match(p.name)) if path.exists() else []
    applied: list[str] = []
    for f in files:
        if f.name in done:
            continue
        sql = f.read_text(encoding="utf-8")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
            conn.commit()
        except Exception:
            conn.rollback()
            log_event(log, logging.ERROR, "migration_failed", migration=f.name, exc_info=True)
            raise
        applied.append(f.name)
        log_event(log, logging.INFO, "migration_applied", migration=f.name)
    return applied


class RawPayloadStore:
    """Writes every FACEIT response to raw_payloads.

    Use a dedicated autocommit connection so the payload is durable even if the
    processing transaction that follows it fails.
    """

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def store(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        http_status: int,
        payload: Any,
        body_text: Optional[str],
        fetched_at: datetime,
        match_id: Optional[str] = None,
        championship_id: Optional[str] = None,
    ) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_payloads
                    (endpoint, params, http_status, payload, body_text, fetched_at, match_id, championship_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    endpoint,
                    Jsonb(params),
                    http_status,
                    Jsonb(payload) if payload is not None else None,
                    body_text,
                    fetched_at,
                    match_id,
                    championship_id,
                ),
            )
            row = cur.fetchone()
        if not self.conn.autocommit:
            self.conn.commit()
        return int(row["id"])

    def latest(self, endpoint: str, *, match_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Most recent successful payload for an endpoint (used by `reprocess`)."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, payload, fetched_at
                FROM raw_payloads
                WHERE endpoint = %s AND http_status = 200 AND (%s::text IS NULL OR match_id = %s)
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (endpoint, match_id, match_id),
            )
            return cur.fetchone()
