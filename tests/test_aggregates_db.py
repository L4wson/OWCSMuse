"""Aggregation layer tests against a real Postgres (skipped without OWCS_TEST_DATABASE_URL).

Ingests three captured matches through the collector with a fake client:
  * two OWCS 2024 EMEA Stage 1 Main Event matches (Twisted Minds 3-1 Ex Oblivione, twice)
  * one OWCS 2026 OQ EMEA match (richer stats, "Time Played" present)
then refreshes the materialized views and checks every aggregate, the
coverage machinery, map durations, scope filtering and entity resolution.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from owcsmuse.aggregates import MATERIALIZED_VIEWS, refresh, stat_coverage_summary, stat_leaderboard
from owcsmuse.collector import Collector
from owcsmuse.config import Settings
from owcsmuse.db import RawPayloadStore, connect, migrate
from owcsmuse.faceit.client import FetchResult, ListResult
from owcsmuse.parsers.matches import parse_match_detail
from owcsmuse.parsers.stats import parse_match_stats
from owcsmuse.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures"
DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test")
MIGRATIONS = os.path.join(os.path.dirname(__file__), "..", "migrations")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

CH_2024 = "f57f9c5f-7840-4a49-8c32-24682dece3fc"
CH_2026 = "05eef1be-c479-45d7-b5c7-d07c5875bb6e"
FLIP = "1-76fe2bd0-4ddd-4c66-be08-0d495a2bb364"
PLAIN = "1-7553f194-b7d7-4bc9-bda4-3484592e014f"
M2026 = "1-c2fc412d-fe01-4bce-ada5-99b5a6dc9e67"
TWISTED_MINDS = "2b9f2e7a-f91a-4597-b2fa-d413eaed605e"
EX_OBLIVIONE = "bb5dd404-213c-430f-8d12-8687fc3ff747"
KSAA = "92695183-d00e-4c31-9707-ff9d8500f52a"


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
        # the detail payload has the same shape as a listing item
        items = [d for d in self.details.values() if d["competition_id"] == championship_id]
        self._fetch(f"/championships/{championship_id}/matches", {"items": items}, championship_id=championship_id)
        return ListResult(items=items, pages=1, truncated=False)

    def get_match(self, match_id):
        return self._fetch(f"/matches/{match_id}", self.details[match_id], match_id=match_id)

    def get_match_stats(self, match_id):
        return self._fetch(f"/matches/{match_id}/stats", self.stats[match_id], match_id=match_id)


def _settings():
    return Settings(_env_file=None, faceit_api_key="x", database_url=DB_URL)


def q(conn, sql, *params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.commit()
    return rows


def one(conn, sql, *params):
    rows = q(conn, sql, *params)
    return rows[0] if rows else None


@pytest.fixture(scope="module")
def db():
    """Module-scoped: ingest once, refresh once, run all aggregate assertions."""
    assert SCHEMA != "public"
    admin = connect(DB_URL, autocommit=True, schema=SCHEMA)
    admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    admin.close()
    conn = connect(DB_URL, schema=SCHEMA)
    raw_conn = connect(DB_URL, autocommit=True, schema=SCHEMA)
    migrate(conn, MIGRATIONS, SCHEMA)
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
    col = Collector(conn, FakeClient(sink), _settings(), sink)
    col.run_list()
    ds = col.run_detail()
    assert ds.complete == 3, ds
    refresh(conn)
    yield conn
    conn.close()
    raw_conn.close()


def expected_player_rounds(player_id, *fixture_pairs):
    """Sum a stat directly from the fixtures, independent of the SQL."""
    rows = []
    for detail_name, stats_name in fixture_pairs:
        detail = parse_match_detail(load_fixture(detail_name))
        for rnd in parse_match_stats(load_fixture(stats_name), detail.map_names, detail.match_id):
            for p in rnd.players:
                if p.player_id == player_id:
                    rows.append((rnd, p))
    return rows


# ---------------------------------------------------------------- player aggregates

def test_player_season_totals_and_averages_match_fixtures(db):
    rows = expected_player_rounds(KSAA, ("match_detail_bo5_flip.json", "match_stats_bo5_flip.json"),
                                  ("match_detail_bo5_4rounds.json", "match_stats_bo5_4rounds.json"))
    assert len(rows) == 8
    exp_elims = sum(p.eliminations for _, p in rows)
    exp_deaths = sum(p.deaths for _, p in rows)
    exp_wins = sum(1 for r, p in rows if r.winner_team_id == p.team_id)

    s = one(db, "SELECT * FROM agg_player_season WHERE player_id = %s AND season = 2024", KSAA)
    assert (s["maps"], s["matches"], s["maps_won"]) == (8, 2, exp_wins) == (8, 2, 6)
    assert s["sum_eliminations"] == exp_elims and s["maps_with_eliminations"] == 8
    assert float(s["avg_eliminations"]) == pytest.approx(exp_elims / 8)
    assert s["sum_deaths"] == exp_deaths
    assert float(s["kd_ratio"]) == pytest.approx(round(exp_elims / exp_deaths, 2))
    # 2024 payloads have no Final Blows: coverage says so instead of pretending zero
    assert s["sum_final_blows"] is None and s["maps_with_final_blows"] == 0 and s["avg_final_blows"] is None
    assert s["first_map_at"] < s["last_map_at"]


def test_fine_grain_player_stats_slice_by_map_and_mode_and_sum_to_season(db):
    fine = q(db, "SELECT * FROM agg_player_stats WHERE player_id = %s AND season = 2024", KSAA)
    assert all(r["team_id"] == TWISTED_MINDS and r["championship_id"] == CH_2024 and r["region"] == "emea" for r in fine)
    assert sum(r["maps"] for r in fine) == 8
    assert sum(r["sum_eliminations"] for r in fine) == one(db, "SELECT sum_eliminations FROM agg_player_season WHERE player_id=%s AND season=2024", KSAA)["sum_eliminations"]
    exp = expected_player_rounds(KSAA, ("match_detail_bo5_flip.json", "match_stats_bo5_flip.json"),
                                 ("match_detail_bo5_4rounds.json", "match_stats_bo5_4rounds.json"))
    exp_lijiang = [r for r, _ in exp if r.map_name == "Lijiang Tower"]
    lijiang = [r for r in fine if r["map_name"] == "Lijiang Tower"]
    assert len(lijiang) == 1 and lijiang[0]["game_mode"] == "Control"
    assert lijiang[0]["maps"] == len(exp_lijiang) == lijiang[0]["matches"] == 1
    assert lijiang[0]["sum_eliminations"] == sum(p.eliminations for r, p in exp if r.map_name == "Lijiang Tower")
    modes = {r["game_mode"] for r in fine}
    assert modes == {"Control", "Hybrid", "Push", "Flashpoint"}


def test_long_format_stats_carry_coverage_per_key(db):
    r = one(db, "SELECT * FROM agg_player_stat_long WHERE player_id=%s AND season=2024 AND stat_key='Eliminations'", KSAA)
    assert r["maps_with_stat"] == 8 and r["total"] == one(db, "SELECT sum_eliminations FROM agg_player_season WHERE player_id=%s AND season=2024", KSAA)["sum_eliminations"]
    assert one(db, "SELECT count(*) AS n FROM agg_player_stat_long WHERE player_id=%s AND stat_key='Final Blows'", KSAA)["n"] == 0
    assert one(db, "SELECT count(*) AS n FROM agg_player_stat_long WHERE stat_key='Role'")["n"] == 0  # text stats excluded
    r2026 = q(db, "SELECT DISTINCT stat_key FROM agg_player_stat_long WHERE season=2026")
    assert {"Final Blows", "Time Played", "Eliminations/10m"} <= {r["stat_key"] for r in r2026}


# ---------------------------------------------------------------- stat availability

def test_stat_coverage_reports_which_stats_exist_per_season(db):
    cov = {(r["season"], r["stat_key"]): r for r in q(db, "SELECT * FROM stat_coverage_season")}
    assert cov[(2024, "Eliminations")]["coverage_pct"] == 100 and cov[(2026, "Eliminations")]["coverage_pct"] == 100
    assert (2024, "Final Blows") not in cov and cov[(2026, "Final Blows")]["coverage_pct"] == 100
    assert cov[(2024, "Eliminations")]["rows_total"] == 80 and cov[(2026, "Eliminations")]["rows_total"] == 30
    keys_2024 = {k for (s, k) in cov if s == 2024}
    keys_2026 = {k for (s, k) in cov if s == 2026}
    assert len(keys_2024) == 9 and len(keys_2026) >= 45 and keys_2024 < keys_2026
    per_champ = one(db, "SELECT * FROM stat_coverage WHERE championship_id=%s AND stat_key='Healing Done'", CH_2024)
    assert per_champ["rows_with_stat"] == 80 and per_champ["is_numeric"] is True


def test_missing_stat_in_2024_does_not_produce_a_misleading_all_seasons_leaderboard(db):
    board = stat_leaderboard(db, "Final Blows")  # no season filter: "all seasons"
    cov = board["coverage"]
    assert cov["seasons_with_stat"] == [2026] and cov["seasons_without_stat"] == [2024]
    assert cov["maps_total"] == 110 and cov["maps_with_stat"] == 30
    assert float(cov["coverage_pct"]) == pytest.approx(27.3, abs=0.05)
    assert cov["first_at"].year == 2026
    ids = {r["player_id"] for r in board["rows"]}
    assert KSAA not in ids and len(ids) == 10                 # only players with the stat appear
    assert all(r["seasons"] == [2026] and r["coverage_pct"] == 100 for r in board["rows"])

    # A stat present everywhere gives a complete window
    board = stat_leaderboard(db, "Eliminations")
    assert board["coverage"]["seasons_without_stat"] is None and board["coverage"]["coverage_pct"] == 100
    ksaa = next(r for r in board["rows"] if r["player_id"] == KSAA)
    assert ksaa["maps_with_stat"] == ksaa["maps_played"] == 8 and ksaa["seasons"] == [2024]

    # Slicing to the season where the stat exists restores full coverage
    assert stat_coverage_summary(db, "Final Blows", season=2026)["coverage_pct"] == 100
    assert stat_coverage_summary(db, "Final Blows", season=2024)["maps_with_stat"] == 0
    assert stat_leaderboard(db, "Final Blows", season=2024)["rows"] == []


# ---------------------------------------------------------------- map duration

def test_map_duration_only_where_time_played_exists(db):
    d = q(db, "SELECT * FROM map_durations ORDER BY match_id, round_number")
    assert {r["match_id"] for r in d} == {M2026}
    assert len(d) == 3 and all(r["duration_seconds"] > 0 and r["duration_source"] == "player_time_played" for r in d)
    mm = {(r["season"], r["map_name"]): r for r in q(db, "SELECT * FROM agg_map_modes")}
    assert all(r["maps_with_duration"] == 0 and r["avg_duration_seconds"] is None for (s, _), r in mm.items() if s == 2024)
    assert all(r["maps_with_duration"] == 1 for (s, _), r in mm.items() if s == 2026)


# ---------------------------------------------------------------- team aggregates

def test_team_match_and_map_records(db):
    tm = one(db, "SELECT * FROM agg_team_matches WHERE team_id=%s AND championship_id=%s", TWISTED_MINDS, CH_2024)
    assert (tm["matches"], tm["wins"], tm["losses"], tm["map_wins"], tm["map_losses"], tm["maps"]) == (2, 2, 0, 6, 2, 8)
    assert tm["win_pct"] == 100 and tm["season"] == 2024 and tm["region"] == "emea"
    ex = one(db, "SELECT * FROM agg_team_matches WHERE team_id=%s AND championship_id=%s", EX_OBLIVIONE, CH_2024)
    assert (ex["matches"], ex["wins"], ex["losses"], ex["map_wins"], ex["map_losses"]) == (2, 0, 2, 2, 6)

    maps = q(db, "SELECT * FROM agg_team_maps WHERE team_id=%s AND season=2024 ORDER BY map_name", TWISTED_MINDS)
    assert sum(r["maps"] for r in maps) == 8 and sum(r["wins"] for r in maps) == 6 and sum(r["losses"] for r in maps) == 2
    lij = next(r for r in maps if r["map_name"] == "Lijiang Tower")
    assert lij["game_mode"] == "Control" and lij["maps"] == 1 and lij["matches"] == 1 and lij["wins"] == 1
    control = [r for r in maps if r["game_mode"] == "Control"]
    assert sum(r["maps"] for r in control) == 2  # both matches opened on a Control map
    # both teams' map rows add up to the round count, twice (one row per side)
    assert one(db, "SELECT sum(maps) AS n FROM agg_team_maps WHERE season=2024")["n"] == 16


def test_head_to_head(db):
    h = one(db, "SELECT * FROM agg_head_to_head WHERE championship_id=%s", CH_2024)
    assert (h["team_a"], h["team_b"]) == (TWISTED_MINDS, EX_OBLIVIONE)  # team_a < team_b
    assert (h["matches"], h["a_wins"], h["b_wins"], h["a_map_wins"], h["b_map_wins"], h["maps"]) == (2, 2, 0, 6, 2, 8)
    assert one(db, "SELECT count(*) AS n FROM agg_head_to_head")["n"] == 2  # one pairing per championship


def test_map_and_mode_win_rates_carry_sample_sizes(db):
    r = one(db, "SELECT * FROM agg_map_modes WHERE map_name='Lijiang Tower' AND season=2024")
    assert (r["game_mode"], r["maps"], r["matches"], r["team1_wins"] + r["team2_wins"] + r["draws"]) == ("Control", 1, 1, 1)
    control = one(db, "SELECT sum(maps) AS maps, sum(matches) AS matches FROM agg_map_modes WHERE game_mode='Control' AND season=2024")
    assert (control["maps"], control["matches"]) == (2, 2)
    assert one(db, "SELECT sum(maps) AS n FROM agg_map_modes")["n"] == 11


# ---------------------------------------------------------------- scope filter

def test_aggregates_only_cover_included_championships(db):
    with db.cursor() as cur:
        cur.execute("UPDATE championships SET include = false WHERE championship_id = %s", (CH_2026,))
    db.commit()
    try:
        refresh(db)
        assert one(db, "SELECT count(*) AS n FROM agg_player_stats WHERE season=2026")["n"] == 0
        assert stat_coverage_summary(db, "Final Blows")["maps_with_stat"] == 0
        assert one(db, "SELECT count(*) AS n FROM stat_coverage_season WHERE season=2026")["n"] == 0
    finally:
        with db.cursor() as cur:
            cur.execute("UPDATE championships SET include = true WHERE championship_id = %s", (CH_2026,))
        db.commit()
        refresh(db)
    assert one(db, "SELECT count(*) AS n FROM agg_player_stats WHERE season=2026")["n"] > 0


# ---------------------------------------------------------------- entity resolution

def test_fold_name_sql_matches_python_fold(db):
    from owcsmuse.resolve import fold
    for s in ("Esperança", "Café Ñandú", "ÀÉÎÕÜ Šž Łódź", "KSAA0"):
        assert one(db, "SELECT fold_name(%s) AS f", s)["f"] == fold(s)


def test_resolver_finds_players_and_teams_from_all_name_kinds(db):
    with db.cursor() as cur:
        cur.execute("INSERT INTO player_nicknames (player_id, nickname, first_seen_at, last_seen_at) VALUES (%s, 'KSAA_oldname', now() - interval '400 days', now() - interval '399 days')", (KSAA,))
        cur.execute("INSERT INTO team_names (team_id, name, first_seen_at, last_seen_at) VALUES (%s, 'Twisted Café', now() - interval '400 days', now() - interval '399 days')", (TWISTED_MINDS,))
    db.commit()
    refresh(db, ["entity_names"])

    kinds = {r["name_kind"] for r in q(db, "SELECT name_kind FROM entity_names WHERE entity_id=%s", KSAA)}
    assert {"current_nickname", "game_name", "historical_nickname"} <= kinds

    c = resolve(db, "ksaa", "player")
    assert c[0].entity_id == KSAA and c[0].score == 1.0 and c[0].current_name == "KSAA0"
    c = resolve(db, "ksaa_oldname", "player")
    assert c[0].entity_id == KSAA and c[0].name_kind == "historical_nickname"
    c = resolve(db, "TWISTED", "team")
    assert c[0].entity_id == TWISTED_MINDS and c[0].current_name == "Twisted Minds"
    c = resolve(db, "twisted cafe", "team")  # accent-insensitive historical team name
    assert c[0].entity_id == TWISTED_MINDS and c[0].name_kind == "historical_name"
    c = resolve(db, "ex oblivione")
    assert c[0].entity_type == "team" and c[0].entity_id == EX_OBLIVIONE
    assert resolve(db, "zzzzqqq") == []


def test_refresh_covers_every_materialized_view(db):
    mvs = {r["matviewname"] for r in q(db, "SELECT matviewname FROM pg_matviews WHERE schemaname = %s", SCHEMA)}
    assert mvs == set(MATERIALIZED_VIEWS)
    timings = refresh(db)
    assert set(timings) == set(MATERIALIZED_VIEWS)
