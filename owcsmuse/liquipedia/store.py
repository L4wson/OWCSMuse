"""Where Liquipedia responses live: raw_payloads (source='liquipedia') and the coverage ledger.

The client and planner talk to a `Store`, so the cache, the budget window and the
coverage ledger are all answered from one durable place. `PgStore` is that place.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Optional, Protocol

import psycopg
from psycopg.types.json import Jsonb

from ..db import RawPayloadStore
from .attribution import page_url


class Store(Protocol):
    def cached(self, endpoint: str, params: dict[str, Any]) -> Optional[dict[str, Any]]: ...
    def save(self, endpoint: str, params: dict[str, Any], status: int, payload: Any, body_text: Optional[str],
             headers: dict[str, str], fetched_at: datetime) -> int: ...
    def used_in_window(self, now: datetime, window: timedelta) -> tuple[int, Optional[datetime]]: ...
    def last_rate_limit(self) -> Optional[tuple[datetime, Optional[float]]]: ...
    def covered(self, endpoint: str, field: str, values: Iterable[str]) -> dict[str, dict[str, Any]]: ...
    def mark_covered(self, endpoint: str, field: str, entries: list[dict[str, Any]], raw_ids: list[int]) -> None: ...
    def unfinished(self, endpoint: str, field: str, values: Iterable[str]) -> set[str]: ...


class PgStore:
    """`conn` must be autocommit, like the FACEIT raw store's: a response must be durable before anything else runs."""

    def __init__(self, conn: psycopg.Connection, wiki: str = "overwatch") -> None:
        assert conn.autocommit, "PgStore needs an autocommit connection so every response is durable immediately"
        self.conn = conn
        self.wiki = wiki
        self._raw = RawPayloadStore(conn)

    def _endpoint(self, endpoint: str) -> str:
        return f"liquipedia:{endpoint}"

    def cached(self, endpoint: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        """A successful stored answer to exactly this request. An answer that carried an error is never reused."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, payload, headers, fetched_at FROM raw_payloads
                WHERE source = 'liquipedia' AND endpoint = %s AND params = %s AND http_status = 200
                  AND payload IS NOT NULL AND NOT (payload ? 'error')
                ORDER BY fetched_at DESC, id DESC LIMIT 1
                """,
                (self._endpoint(endpoint), Jsonb(params)),
            )
            return cur.fetchone()

    def save(self, endpoint: str, params: dict[str, Any], status: int, payload: Any, body_text: Optional[str],
             headers: dict[str, str], fetched_at: datetime) -> int:
        return self._raw.store(endpoint=self._endpoint(endpoint), params=params, http_status=status, payload=payload,
                               body_text=body_text, fetched_at=fetched_at, headers=headers, source="liquipedia")

    def used_in_window(self, now: datetime, window: timedelta) -> tuple[int, Optional[datetime]]:
        """Requests this source has actually sent inside the window (cache hits leave no row), and the oldest of them."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n, min(fetched_at) AS oldest FROM raw_payloads "
                        "WHERE source = 'liquipedia' AND fetched_at > %s", (now - window,))
            row = cur.fetchone()
        return int(row["n"]), row["oldest"]

    def last_rate_limit(self) -> Optional[tuple[datetime, Optional[float]]]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT fetched_at, headers FROM raw_payloads WHERE source = 'liquipedia' AND http_status = 429 "
                        "ORDER BY fetched_at DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            return None
        try:
            retry_after = float((row["headers"] or {}).get("retry-after"))
        except (TypeError, ValueError):
            retry_after = None
        return row["fetched_at"], retry_after

    def covered(self, endpoint: str, field: str, values: Iterable[str]) -> dict[str, dict[str, Any]]:
        values = list(values)
        if not values:
            return {}
        with self.conn.cursor() as cur:
            cur.execute("SELECT value, page_url, rows_seen, raw_ids, fetched_at FROM liquipedia_coverage "
                        "WHERE endpoint = %s AND field = %s AND value = ANY(%s)", (endpoint, field, values))
            return {r["value"]: dict(r) for r in cur.fetchall()}

    def unfinished(self, endpoint: str, field: str, values: Iterable[str]) -> set[str]:
        """The covered values whose held answer still has an unfinished record on them: a stage being played, a bracket
        whose later slots are still to be decided. Only a record that carries `finished` (a match) can be unfinished;
        a placement never is. These are re-requested every run until Liquipedia shows every record on them finished."""
        values = list(values)
        if not values:
            return set()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.value FROM liquipedia_coverage c
                 WHERE c.endpoint = %s AND c.field = %s AND c.value = ANY(%s)
                   AND EXISTS (
                       SELECT 1 FROM raw_payloads r
                        CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(r.payload -> 'result') = 'array'
                                                                     THEN r.payload -> 'result' ELSE '[]'::jsonb END) x
                        WHERE r.id = ANY(c.raw_ids) AND replace(x ->> %s, ' ', '_') = c.value
                          AND x ? 'finished' AND (x ->> 'finished') NOT IN ('1', 'true'))
                """,
                (endpoint, field, values, field),
            )
            return {r["value"] for r in cur.fetchall()}

    def mark_covered(self, endpoint: str, field: str, entries: list[dict[str, Any]], raw_ids: list[int]) -> None:
        """`entries`: [{"value", "rows_seen"}]. The page URL is derived here, so no row can exist without one."""
        with self.conn.cursor() as cur:
            for e in entries:
                cur.execute(
                    """
                    INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (endpoint, field, value) DO UPDATE
                       SET page_url = EXCLUDED.page_url, rows_seen = EXCLUDED.rows_seen,
                           raw_ids = EXCLUDED.raw_ids, fetched_at = now()
                    """,
                    (endpoint, field, e["value"], page_url(e["value"], self.wiki), e.get("rows_seen"), raw_ids),
                )
