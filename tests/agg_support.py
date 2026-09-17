"""Shared helpers: ingest the captured fixtures into a scratch schema and refresh the aggregates."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from owcsmuse.aggregates import refresh
from owcsmuse.collector import Collector
from owcsmuse.config import Settings
from owcsmuse.db import RawPayloadStore, connect, migrate
from owcsmuse.faceit.client import FetchResult, ListResult

FIXTURES = Path(__file__).parent / "fixtures"
MIGRATIONS = os.path.join(os.path.dirname(__file__), "..", "migrations")

CH_2024 = "f57f9c5f-7840-4a49-8c32-24682dece3fc"
CH_2026 = "05eef1be-c479-45d7-b5c7-d07c5875bb6e"
FLIP = "1-76fe2bd0-4ddd-4c66-be08-0d495a2bb364"
PLAIN = "1-7553f194-b7d7-4bc9-bda4-3484592e014f"
M2026 = "1-c2fc412d-fe01-4bce-ada5-99b5a6dc9e67"


def load_fixture(name: str):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


class FakeClient:
    def __init__(self, sink):
        self.sink = sink
        self.details = {
            FLIP: load_fixture("match_detail_bo5_flip.json"),
            PLAIN: load_fixture("match_detail_bo5_4rounds.json"),
            M2026: load_fixture("match_detail_2026.json"),
        }
        self.stats = {
            FLIP: load_fixture("match_stats_bo5_flip.json"),
            PLAIN: load_fixture("match_stats_bo5_4rounds.json"),
            M2026: load_fixture("match_stats_2026.json"),
        }

    def _fetch(self, endpoint, payload, match_id=None, championship_id=None):
        now = datetime.now(timezone.utc)
        raw_id = self.sink.store(endpoint=endpoint, params={}, http_status=200, payload=payload, body_text=None,
                                 fetched_at=now, match_id=match_id, championship_id=championship_id)
        return FetchResult(endpoint, {}, 200, payload, raw_id, now)

    def list_championship_matches(self, championship_id, match_type="all"):
        items = [d for d in self.details.values() if d["competition_id"] == championship_id]
        self._fetch(f"/championships/{championship_id}/matches", {"items": items}, championship_id=championship_id)
        return ListResult(items=items, pages=1, truncated=False)

    def get_match(self, match_id):
        return self._fetch(f"/matches/{match_id}", self.details[match_id], match_id=match_id)

    def get_match_stats(self, match_id):
        return self._fetch(f"/matches/{match_id}/stats", self.stats[match_id], match_id=match_id)


def build_scratch_db(db_url: str, schema: str):
    """Drop + recreate `schema`, migrate, ingest the three fixture matches, refresh. Returns (conn, raw_conn)."""
    assert schema != "public"
    admin = connect(db_url, autocommit=True, schema=schema)
    admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    admin.close()
    conn = connect(db_url, schema=schema)
    raw_conn = connect(db_url, autocommit=True, schema=schema)
    migrate(conn, MIGRATIONS, schema)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizers (organizer_id, name) VALUES ('org1', 'OWCS'), ('org2', 'FACEIT League')")
        cur.execute(
            """INSERT INTO championships (championship_id, organizer_id, name, include, scope_region, tier, season, classification_source)
               VALUES (%s, 'org1', 'OWCS 2024: EMEA Stage 1 - Main Event', true, 'emea', 'main', 2024, 'manual'),
                      (%s, 'org2', 'OWCS 2026 OQ - EMEA', true, 'emea', 'qualifier', 2026, 'manual')""",
            (CH_2024, CH_2026),
        )
    conn.commit()
    sink = RawPayloadStore(raw_conn)
    settings = Settings(_env_file=None, faceit_api_key="x", database_url=db_url)
    col = Collector(conn, FakeClient(sink), settings, sink)
    col.run_list()
    ds = col.run_detail()
    assert ds.complete == 3, ds
    refresh(conn)
    return conn, raw_conn
