"""End-to-end collector tests against a real Postgres.

Skipped unless OWCS_TEST_DATABASE_URL is set. The URL should point at a scratch
schema, e.g.

    postgresql://owcs:owcs@localhost:5432/owcsmuse?options=-c%20search_path%3Downcs_test

The test drops and recreates that schema, so never point it at production.
FACEIT is never contacted: a fake client serves the captured fixtures.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from owcsmuse.collector import Collector
from owcsmuse.config import Settings
from owcsmuse.db import RawPayloadStore, connect, migrate
from owcsmuse.faceit.client import FaceitNotFound, FetchResult, ListResult

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

CHAMP = "f57f9c5f-7840-4a49-8c32-24682dece3fc"
FLIP = "1-76fe2bd0-4ddd-4c66-be08-0d495a2bb364"      # list says faction2 2-0, detail says faction1 3-1
PLAIN = "1-7553f194-b7d7-4bc9-bda4-3484592e014f"     # list and detail agree
TWISTED_MINDS = "2b9f2e7a-f91a-4597-b2fa-d413eaed605e"


class FakeClient:
    """Serves fixtures through the same interface as FaceitClient, storing raw payloads like the real one."""

    def __init__(self, sink: RawPayloadStore, stats_404: set[str] | None = None):
        self.sink = sink
        self.stats_404 = stats_404 or set()
        self.calls: list[str] = []
        self.list_items = [load_fixture("list_item_bo5_first_map_result.json"), load_fixture("list_item_bo5_4rounds.json")]
        self.details = {FLIP: load_fixture("match_detail_bo5_flip.json"), PLAIN: load_fixture("match_detail_bo5_4rounds.json")}
        self.stats = {FLIP: load_fixture("match_stats_bo5_flip.json"), PLAIN: load_fixture("match_stats_bo5_4rounds.json")}

    def _fetch(self, endpoint, payload, match_id=None, championship_id=None, status=200):
        self.calls.append(endpoint)
        now = datetime.now(timezone.utc)
        raw_id = self.sink.store(endpoint=endpoint, params={}, http_status=status, payload=payload, body_text=None,
                                 fetched_at=now, match_id=match_id, championship_id=championship_id)
        return FetchResult(endpoint, {}, status, payload, raw_id, now)

    def list_championship_matches(self, championship_id, match_type="all"):
        res = self._fetch(f"/championships/{championship_id}/matches", {"items": self.list_items}, championship_id=championship_id)
        return ListResult(items=list(self.list_items), pages=1, truncated=False, raw_ids=[res.raw_id])

    def get_match(self, match_id):
        return self._fetch(f"/matches/{match_id}", self.details[match_id], match_id=match_id)

    def get_match_stats(self, match_id):
        if match_id in self.stats_404:
            self._fetch(f"/matches/{match_id}/stats", {"errors": [{"message": "not found"}]}, match_id=match_id, status=404)
            raise FaceitNotFound(404, f"/matches/{match_id}/stats")
        return self._fetch(f"/matches/{match_id}/stats", self.stats[match_id], match_id=match_id)


def _schema_from_url(url: str) -> str:
    m = re.search(r"search_path(?:%3D|=)([A-Za-z0-9_]+)", url)
    return m.group(1) if m else "public"


@pytest.fixture
def db():
    schema = _schema_from_url(DB_URL)
    assert schema != "public", "point OWCS_TEST_DATABASE_URL at a scratch schema via ?options=-c search_path=..."
    admin = connect(DB_URL, autocommit=True)
    admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    admin.execute(f"CREATE SCHEMA {schema}")
    admin.close()

    conn = connect(DB_URL)
    raw_conn = connect(DB_URL, autocommit=True)
    migrate(conn, os.path.join(os.path.dirname(__file__), "..", "migrations"))
    yield conn, raw_conn
    conn.close()
    raw_conn.close()


def _settings() -> Settings:
    return Settings(_env_file=None, faceit_api_key="x", database_url=DB_URL)


def _seed_championship(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizers (organizer_id, name) VALUES ('org1', 'OWCS')")
        cur.execute(
            "INSERT INTO championships (championship_id, organizer_id, name, include) VALUES (%s, 'org1', 'EMEA S1 Main', true)",
            (CHAMP,),
        )
    conn.commit()


def _one(conn, sql, *params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    conn.commit()
    return row


def _counts(conn):
    return {
        t: _one(conn, f"SELECT count(*) AS n FROM {t}")["n"]
        for t in ("matches", "match_rounds", "match_players", "match_rosters", "match_map_picks", "players",
                  "player_nicknames", "teams", "team_names")
    }


def test_migrations_apply_once(db):
    conn, _ = db
    assert migrate(conn, os.path.join(os.path.dirname(__file__), "..", "migrations")) == []
    assert _one(conn, "SELECT count(*) AS n FROM schema_migrations")["n"] == 1


def test_list_then_detail_overwrites_first_map_result_and_is_idempotent(db):
    conn, raw_conn = db
    _seed_championship(conn)
    sink = RawPayloadStore(raw_conn)
    client = FakeClient(sink)
    col = Collector(conn, client, _settings(), sink)

    # ---- LIST
    ls = col.run_list()
    assert ls.matches_inserted == 2 and ls.matches_updated == 0
    row = _one(conn, "SELECT * FROM matches WHERE match_id = %s", FLIP)
    assert row["ingest_state"] == "stub" and row["result_source"] == "list"
    assert (row["winner_faction"], row["faction1_score"], row["faction2_score"]) == ("faction2", 0, 2)
    assert row["list_winner_faction"] == "faction2"
    assert _one(conn, "SELECT list_completed_at, list_truncated FROM championships WHERE championship_id=%s", CHAMP)["list_completed_at"]

    # ---- DETAIL
    ds = col.run_detail()
    assert ds.selected == 2 and ds.complete == 2 and ds.failed == 0
    assert ds.result_flips == 1

    row = _one(conn, "SELECT * FROM matches WHERE match_id = %s", FLIP)
    assert row["ingest_state"] == "complete" and row["result_source"] == "detail"
    assert (row["winner_faction"], row["faction1_score"], row["faction2_score"]) == ("faction1", 3, 1)
    assert row["winner_team_id"] == TWISTED_MINDS
    assert row["result_flipped"] is True
    assert (row["list_winner_faction"], row["list_faction1_score"], row["list_faction2_score"]) == ("faction2", 0, 2)
    assert row["maps_picked"] == 5 and row["maps_played"] == 4
    assert row["detail_raw_id"] and row["stats_raw_id"]

    plain = _one(conn, "SELECT result_flipped, maps_played, maps_picked FROM matches WHERE match_id = %s", PLAIN)
    assert plain["result_flipped"] is False and (plain["maps_played"], plain["maps_picked"]) == (4, 5)

    rounds = _one(conn, "SELECT count(*) AS n FROM match_rounds WHERE match_id = %s", FLIP)["n"]
    assert rounds == 4
    modes = [r["game_mode"] for r in conn.execute(
        "SELECT game_mode FROM match_rounds WHERE match_id=%s ORDER BY round_number", (FLIP,)).fetchall()]
    conn.commit()
    assert modes == ["Control", "Hybrid", "Push", "Flashpoint"]
    assert _one(conn, "SELECT count(*) AS n FROM match_players WHERE match_id = %s", FLIP)["n"] == 40
    joined = _one(conn, """
        SELECT count(*) AS n FROM match_players mp
        JOIN match_rounds r ON (r.match_id, r.round_number) = (mp.match_id, mp.round_number)
        WHERE mp.match_id = %s AND mp.team_id IN (r.team1_team_id, r.team2_team_id)""", FLIP)["n"]
    assert joined == 40
    totals = _one(conn, "SELECT maps_played, maps_won FROM match_player_totals WHERE match_id=%s AND player_id=%s",
                  FLIP, "92695183-d00e-4c31-9707-ff9d8500f52a")
    assert (totals["maps_played"], totals["maps_won"]) == (4, 3)

    before = _counts(conn)
    raw_before = _one(conn, "SELECT count(*) AS n FROM raw_payloads")["n"]

    # ---- re-run everything: no duplicates, detail result survives a fresh LIST that still says first-map
    col.run_list()
    row = _one(conn, "SELECT winner_faction, result_source, ingest_state FROM matches WHERE match_id = %s", FLIP)
    assert row["winner_faction"] == "faction1" and row["result_source"] == "detail"
    assert row["ingest_state"] == "complete"  # status unchanged => not re-queued
    assert col.run_detail().selected == 0     # nothing pending: resumable state honoured
    col.run_detail(refresh=True)
    assert _counts(conn) == before
    assert _one(conn, "SELECT count(*) AS n FROM raw_payloads")["n"] > raw_before  # every request still stored


def test_resume_processes_only_pending_and_respects_limit(db):
    conn, raw_conn = db
    _seed_championship(conn)
    sink = RawPayloadStore(raw_conn)
    client = FakeClient(sink)
    col = Collector(conn, client, _settings(), sink)
    col.run_list()

    first = col.run_detail(limit=1)
    assert first.selected == 1
    states = {r["match_id"]: r["ingest_state"] for r in conn.execute("SELECT match_id, ingest_state FROM matches").fetchall()}
    conn.commit()
    assert sorted(states.values()) == ["complete", "stub"]

    client.calls.clear()
    second = col.run_detail()
    assert second.selected == 1 and second.complete == 1
    assert not any(c.startswith(f"/matches/{next(m for m, s in states.items() if s == 'complete')}") for c in client.calls)


def test_stats_404_marks_failed_and_retry_flag_reprocesses(db):
    conn, raw_conn = db
    _seed_championship(conn)
    sink = RawPayloadStore(raw_conn)
    client = FakeClient(sink, stats_404={PLAIN})
    col = Collector(conn, client, _settings(), sink)
    col.run_list()
    ds = col.run_detail()
    assert ds.complete == 1 and ds.failed == 1
    row = _one(conn, "SELECT ingest_state, ingest_error, winner_faction, result_source FROM matches WHERE match_id=%s", PLAIN)
    assert row["ingest_state"] == "failed" and "404" in row["ingest_error"]
    assert row["result_source"] == "detail" and row["winner_faction"] == "faction1"  # detail still applied
    assert _one(conn, "SELECT count(*) AS n FROM match_rounds WHERE match_id=%s", PLAIN)["n"] == 0

    assert col.run_detail().selected == 0
    client.stats_404.clear()
    ds = col.run_detail(include_failed=True)
    assert ds.selected == 1 and ds.complete == 1
    assert _one(conn, "SELECT count(*) AS n FROM match_rounds WHERE match_id=%s", PLAIN)["n"] == 4


def test_reprocess_from_raw_payloads_without_client(db):
    conn, raw_conn = db
    _seed_championship(conn)
    sink = RawPayloadStore(raw_conn)
    col = Collector(conn, FakeClient(sink), _settings(), sink)
    col.run_list()
    col.run_detail()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM match_rounds")
        cur.execute("UPDATE matches SET winner_faction = NULL, maps_played = NULL")
    conn.commit()

    offline = Collector(conn, None, _settings(), sink)
    rs = offline.reprocess()
    assert rs.selected == 2 and rs.complete == 2
    row = _one(conn, "SELECT winner_faction, maps_played FROM matches WHERE match_id=%s", FLIP)
    assert (row["winner_faction"], row["maps_played"]) == ("faction1", 4)
    assert _one(conn, "SELECT count(*) AS n FROM match_rounds")["n"] == 8


def test_player_identity_is_guid_with_nickname_history(db):
    conn, raw_conn = db
    _seed_championship(conn)
    sink = RawPayloadStore(raw_conn)
    client = FakeClient(sink)
    # Same GUID, later match, new nickname
    later = load_fixture("match_detail_bo5_4rounds.json")
    later["started_at"] = later["started_at"] + 86400 * 30
    later["teams"]["faction1"]["roster"][0]["nickname"] = "KSAA_renamed"
    client.details[PLAIN] = later
    col = Collector(conn, client, _settings(), sink)
    col.run_list()
    col.run_detail()

    pid = "92695183-d00e-4c31-9707-ff9d8500f52a"
    p = _one(conn, "SELECT nickname, first_seen_at, last_seen_at FROM players WHERE player_id=%s", pid)
    assert p["nickname"] == "KSAA_renamed"
    assert p["first_seen_at"] < p["last_seen_at"]
    hist = conn.execute("SELECT nickname FROM player_nicknames WHERE player_id=%s ORDER BY first_seen_at", (pid,)).fetchall()
    conn.commit()
    assert [h["nickname"] for h in hist] == ["KSAA0", "KSAA_renamed"]
    assert _one(conn, "SELECT count(*) AS n FROM players WHERE player_id=%s", pid)["n"] == 1
    assert _one(conn, "SELECT count(*) AS n FROM match_rosters WHERE player_id=%s", pid)["n"] == 2


def test_status_changed_in_list_requeues_match(db):
    conn, raw_conn = db
    _seed_championship(conn)
    sink = RawPayloadStore(raw_conn)
    client = FakeClient(sink)
    col = Collector(conn, client, _settings(), sink)
    col.run_list()
    col.run_detail()
    client.list_items[1] = dict(client.list_items[1], status="ONGOING")
    col.run_list()
    assert _one(conn, "SELECT ingest_state FROM matches WHERE match_id=%s", PLAIN)["ingest_state"] == "stub"
    assert _one(conn, "SELECT ingest_state FROM matches WHERE match_id=%s", FLIP)["ingest_state"] == "complete"
