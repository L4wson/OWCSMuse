"""History-crawl writes against a real Postgres (skipped unless OWCS_TEST_DATABASE_URL is set).

Objects are created in a scratch schema (OWCS_TEST_SCHEMA + "_crawl"), dropped and recreated per test.
FACEIT is never contacted: a fake client serves captured history items.
"""

from __future__ import annotations

import copy
import os
from datetime import datetime, timezone

import pytest

from owcsmuse.config import Settings
from owcsmuse.crawl import Crawler, CrawlStats
from owcsmuse.db import RawPayloadStore, connect, migrate
from owcsmuse.faceit.client import FetchResult
from owcsmuse.scope import Decisions

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test") + "_crawl"
MIGRATIONS = os.path.join(os.path.dirname(__file__), "..", "migrations")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

NA_COMPETITION = "00000000-0000-4000-8000-00000000000a"


class HistoryClient:
    """Serves one fixed page of player history for every window the crawl asks about."""

    def __init__(self, items):
        self.items = items

    def player_history(self, player_id, game="ow2", from_ts=None, to_ts=None, offset=0, limit=100):
        return FetchResult(f"/players/{player_id}/history", {}, 200, {"items": list(self.items)}, None,
                           datetime.now(timezone.utc))


@pytest.fixture
def db():
    assert not SCHEMA.startswith("public"), "the scratch schema must never be public"
    admin = connect(DB_URL, autocommit=True, schema=SCHEMA)
    admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    admin.close()
    conn = connect(DB_URL, schema=SCHEMA)
    raw_conn = connect(DB_URL, autocommit=True, schema=SCHEMA)
    migrate(conn, MIGRATIONS, SCHEMA)
    yield conn, raw_conn
    conn.close()
    raw_conn.close()


def test_each_championship_is_created_from_its_own_classification(db, fx, tmp_path):
    """A player's history spans an EMEA and an NA competition, NA last. Each championship row takes its region from
    its own name: the crawl once handed the last item's classification to every championship it created."""
    conn, raw_conn = db
    emea = fx("history_item_first_map_result.json")            # S9 EMEA OWCS Central - Playoffs
    na = copy.deepcopy(emea)
    na.update(match_id="1-00000000-0000-4000-8000-0000000000aa", competition_id=NA_COMPETITION,
              competition_name="S9 NA OWCS Central - Playoffs")
    settings = Settings(_env_file=None, faceit_api_key="x", database_url=DB_URL)
    crawler = Crawler(conn, HistoryClient([emea, na]), settings, RawPayloadStore(raw_conn),
                      decisions=Decisions(tmp_path / "decisions.json"))

    out = crawler.crawl_player({"player_id": "p1", "nickname": "p1"}, generation=0, run_id=None, stats=CrawlStats())

    assert out["main"] == 2
    rows = conn.execute("SELECT championship_id, derived_region FROM championships").fetchall()
    main = conn.execute("SELECT count(*) AS n FROM history_matches WHERE main_series").fetchone()["n"]
    conn.commit()
    assert {r["championship_id"]: r["derived_region"] for r in rows} == {emea["competition_id"]: "EMEA",
                                                                        NA_COMPETITION: "NA"}
    assert main == 2
