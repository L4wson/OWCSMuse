"""The Liquipedia store on real Postgres: budget window, exact-match cache, 429 memory and the coverage ledger.

Skipped unless OWCS_TEST_DATABASE_URL is set; runs in a scratch schema, never public.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from liquipedia_support import Clock, Wire, rows_response

from owcsmuse.db import RawPayloadStore, connect, migrate
from owcsmuse.liquipedia import LiquipediaClient, PgStore, plan_requests, run_plan

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test") + "_lp"
MIGRATIONS = os.path.join(os.path.dirname(__file__), "..", "migrations")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("OWCS_LIQUIPEDIA_ENABLED", "1")
    admin = connect(DB_URL, autocommit=True, schema=SCHEMA)
    admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    admin.close()
    conn = connect(DB_URL, schema=SCHEMA)
    migrate(conn, MIGRATIONS, SCHEMA)
    conn.close()
    raw = connect(DB_URL, autocommit=True, schema=SCHEMA)
    yield PgStore(raw)
    raw.close()


def test_a_stored_answer_is_found_by_exactly_its_request_and_an_error_never_is(store):
    params = {"wiki": "overwatch", "conditions": "[[date::>2026-01-01]]", "limit": 5}
    store.save("match", params, 200, {"error": ["bad"]}, None, {}, T0)
    assert store.cached("match", params) is None                       # a stored error is not data
    rid = store.save("match", params, 200, {"result": [{"a": 1}]}, None, {"x-ratelimit-remaining": "7"}, T0)
    got = store.cached("match", {"limit": 5, "conditions": "[[date::>2026-01-01]]", "wiki": "overwatch"})
    assert got["id"] == rid and got["headers"] == {"x-ratelimit-remaining": "7"}   # key order does not matter; headers kept
    assert store.cached("match", {**params, "limit": 6}) is None
    assert store.cached("team", params) is None


def test_the_budget_counts_liquipedia_rows_only_and_only_inside_the_window(store):
    store.save("match", {"n": 1}, 200, {"result": []}, None, {}, T0 - timedelta(minutes=61))
    store.save("match", {"n": 2}, 200, {"result": []}, None, {}, T0 - timedelta(minutes=30))
    store.save("match", {"n": 3}, 500, None, "oops", {}, T0 - timedelta(minutes=5))           # failures count: they cost a request
    RawPayloadStore(store.conn).store(endpoint="/matches/x", params={}, http_status=200, payload={}, body_text=None,
                                      fetched_at=T0)                                            # FACEIT: not ours to count
    used, oldest = store.used_in_window(T0, timedelta(hours=1))
    assert used == 2 and oldest == T0 - timedelta(minutes=30)


def test_existing_faceit_rows_are_faceit_and_reprocess_never_sees_liquipedia(store):
    RawPayloadStore(store.conn).store(endpoint="/matches/x", params={}, http_status=200, payload={"a": 1}, body_text=None,
                                      fetched_at=T0, match_id="x")
    store.save("match", {"n": 1}, 200, {"result": []}, None, {}, T0)
    with store.conn.cursor() as cur:
        cur.execute("SELECT source, count(*) AS n FROM raw_payloads GROUP BY 1 ORDER BY 1")
        assert {r["source"]: r["n"] for r in cur.fetchall()} == {"faceit": 1, "liquipedia": 1}
    assert RawPayloadStore(store.conn).latest("/matches/x", match_id="x")["payload"] == {"a": 1}


def test_the_last_429_and_its_retry_after_are_remembered(store):
    assert store.last_rate_limit() is None
    store.save("match", {"n": 1}, 429, {"error": "x"}, None, {"retry-after": "90"}, T0)
    assert store.last_rate_limit() == (T0, 90.0)


def test_coverage_holds_a_page_url_and_cannot_hold_a_row_without_one(store):
    store.mark_covered("match", "parent", [{"value": "Overwatch_Champions_Series/2026/EMEA/Stage_2", "rows_seen": 44}], [1, 2])
    got = store.covered("match", "parent", ["Overwatch_Champions_Series/2026/EMEA/Stage_2", "Other"])
    assert list(got) == ["Overwatch_Champions_Series/2026/EMEA/Stage_2"]
    row = got["Overwatch_Champions_Series/2026/EMEA/Stage_2"]
    assert row["page_url"] == "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2"
    assert row["rows_seen"] == 44 and row["raw_ids"] == [1, 2]
    with pytest.raises(psycopg.errors.CheckViolation):                    # the database refuses an unattributed row too
        store.conn.execute("INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, raw_ids) "
                           "VALUES ('match', 'parent', 'x', 'https://example.com/x', '{}')")


def test_a_whole_run_through_postgres_stops_on_429_and_a_rerun_repeats_nothing(store):
    clock = Clock(T0)
    served = iter([rows_response(1, parent="A"), httpx.Response(429, json={}, headers={"retry-after": "60"})])
    wire = Wire(lambda req: next(served))
    client = LiquipediaClient("k", store, hourly_budget=60, min_interval=0, http=wire.client(), clock=clock, sleep=clock.sleep)
    plan = plan_requests(store, endpoint="match", field_name="parent", wants={"A": 1, "B": 1}, limit=10, max_condition_chars=30)
    res = run_plan(client, plan)
    assert res.outcome == "rate_limited" and len(wire.requests) == 2
    assert list(store.covered("match", "parent", ["A", "B"])) == ["A"]     # only the batch that came back whole
    clock.advance(seconds=61)
    wire.respond = lambda req: rows_response(1, parent="B")
    plan2 = plan_requests(store, endpoint="match", field_name="parent", wants={"A": 1, "B": 1}, limit=10, max_condition_chars=30)
    assert plan2.held == ["A"] and plan2.projected_requests == 1
    assert run_plan(client, plan2).outcome == "complete" and len(wire.requests) == 3
    # and the 429 itself is stored, with its headers
    with store.conn.cursor() as cur:
        cur.execute("SELECT headers FROM raw_payloads WHERE http_status = 429")
        assert cur.fetchone()["headers"]["retry-after"] == "60"
