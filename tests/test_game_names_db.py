"""The in-game name is the one answers display and it changes: every value is kept (player_game_names), the backfill
reads earlier values out of the stored match payloads, an owner's display name overrides what is shown without
touching what is searchable, and leaderboards carry a deterministic last key."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from owcsmuse.aggregates import refresh
from owcsmuse.collector import Collector

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def test_every_in_game_name_is_kept_and_the_old_one_stays_searchable(agg_db):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        with agg_db.cursor() as cur:
            Collector._upsert_players_batch(cur, [{"id": "p-ren", "nick": "renamer", "nickname": "renamer", "gpid": None,
                                                  "gpname": "OldName", "avatar": None, "seen": t0}])
            Collector._upsert_players_batch(cur, [{"id": "p-ren", "nick": "renamer", "nickname": "renamer", "gpid": None,
                                                  "gpname": "NewName", "avatar": None, "seen": t0 + timedelta(days=30)}])
            cur.execute("SELECT game_player_name, first_seen_at FROM player_game_names WHERE player_id = 'p-ren' ORDER BY first_seen_at")
            rows = [(r["game_player_name"], r["first_seen_at"]) for r in cur.fetchall()]
        assert rows == [("OldName", t0), ("NewName", t0 + timedelta(days=30))]
        assert _one(agg_db, "SELECT game_player_name FROM players WHERE player_id = 'p-ren'")["game_player_name"] == "NewName"
        refresh(agg_db, ["entity_names"])
        with agg_db.cursor() as cur:
            cur.execute("SELECT name, name_kind, current_name FROM entity_names WHERE entity_id = 'p-ren' ORDER BY name_kind")
            got = {(r["name"], r["name_kind"]): r["current_name"] for r in cur.fetchall()}
        assert got[("OldName", "historical_game_name")] == "NewName" and got[("NewName", "game_name")] == "NewName"
    finally:
        with agg_db.cursor() as cur:
            cur.execute("DELETE FROM player_game_names WHERE player_id = 'p-ren'")
            cur.execute("DELETE FROM player_nicknames WHERE player_id = 'p-ren'")
            cur.execute("DELETE FROM players WHERE player_id = 'p-ren'")
        agg_db.commit()
        refresh(agg_db, ["entity_names"])


def test_the_backfill_reads_earlier_names_out_of_the_stored_match_payloads(agg_db):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from backfill_game_names import backfill
    before = _one(agg_db, "SELECT count(*) AS n FROM player_game_names")["n"]
    # pretend a player's stored payload named him differently at the time: the backfill must recover that name
    row = _one(agg_db, """SELECT r.player_id, r.game_player_name, r.match_id FROM match_rosters r
                           WHERE r.game_player_name IS NOT NULL LIMIT 1""")
    try:
        with agg_db.cursor() as cur:
            cur.execute("UPDATE players SET game_player_name = %s WHERE player_id = %s", (row["game_player_name"] + "_v2", row["player_id"]))
            cur.execute("DELETE FROM player_game_names WHERE player_id = %s", (row["player_id"],))
        agg_db.commit()
        out = backfill(agg_db)
        assert out["payloads_read"] > 0 and out["sightings_recorded"] > 0
        with agg_db.cursor() as cur:
            cur.execute("SELECT game_player_name FROM player_game_names WHERE player_id = %s", (row["player_id"],))
            names = {r["game_player_name"] for r in cur.fetchall()}
        assert row["game_player_name"] in names                      # the name the payload carried, back in history
        assert _one(agg_db, "SELECT count(*) AS n FROM player_game_names")["n"] >= before - 1
    finally:
        with agg_db.cursor() as cur:
            cur.execute("UPDATE players SET game_player_name = %s WHERE player_id = %s", (row["game_player_name"], row["player_id"]))
        agg_db.commit()


def test_an_owners_display_name_is_shown_but_changes_nothing_searchable(agg_db):
    p = _one(agg_db, "SELECT player_id, nickname, game_player_name FROM players WHERE game_player_name IS NOT NULL LIMIT 1")
    try:
        with agg_db.cursor() as cur:
            cur.execute("UPDATE players SET display_name = 'ZZZ' WHERE player_id = %s", (p["player_id"],))
        agg_db.commit()
        refresh(agg_db, ["entity_names"])
        with agg_db.cursor() as cur:
            cur.execute("SELECT name, name_kind, current_name FROM entity_names WHERE entity_id = %s", (p["player_id"],))
            rows = cur.fetchall()
        assert {r["current_name"] for r in rows} == {"ZZZ"}
        assert {r["name"] for r in rows} >= {p["nickname"], p["game_player_name"]}       # still searchable by both
        lb = _one(agg_db, "SELECT nickname FROM stat_leaderboard('Eliminations') WHERE player_id = %s", (p["player_id"],))
        assert lb is None or lb["nickname"] == "ZZZ"
        assert _one(agg_db, "SELECT player_display_name(NULL, 'nick', 'game') AS n")["n"] == "game"
        assert _one(agg_db, "SELECT player_display_name('Shown', 'nick', 'game') AS n")["n"] == "Shown"
    finally:
        with agg_db.cursor() as cur:
            cur.execute("UPDATE players SET display_name = NULL WHERE player_id = %s", (p["player_id"],))
        agg_db.commit()
        refresh(agg_db, ["entity_names"])


def test_identity_load_sets_the_display_name_from_the_decision(agg_db, tmp_path):
    from owcsmuse.liquipedia import identity as ident
    from owcsmuse.liquipedia.teams import TeamMap
    p = _one(agg_db, "SELECT player_id FROM players LIMIT 1")
    d = ident.PlayerDecisions(tmp_path / "p.json")
    d.set("Some_Page", p["player_id"], "some", "test", display="Shown Name")
    try:
        out = ident.load_identity(agg_db, d, TeamMap(tmp_path / "tm.json"))
        assert out["display_names_set"] == 1
        assert _one(agg_db, "SELECT display_name FROM players WHERE player_id = %s", (p["player_id"],))["display_name"] == "Shown Name"
        out = ident.load_identity(agg_db, ident.PlayerDecisions(tmp_path / "empty.json"), TeamMap(tmp_path / "tm.json"))
        assert out["display_names_set"] == 0
        assert _one(agg_db, "SELECT display_name FROM players WHERE player_id = %s", (p["player_id"],))["display_name"] is None
    finally:
        agg_db.commit()


def test_leaderboards_order_ties_deterministically(agg_db):
    with agg_db.cursor() as cur:
        cur.execute("SELECT prosrc FROM pg_proc WHERE proname = 'stat_leaderboard'")
        assert "maps_with_stat DESC, b.player_id" in cur.fetchone()["prosrc"]


def test_an_owner_decided_cross_region_org_is_reported_not_failed(agg_db):
    """The region check guards against wrong cross-region merges; one the owner decided carries the token in every
    window's evidence and is listed under decided_cross_region_orgs instead of failing."""
    from psycopg.types.json import Jsonb

    from owcsmuse.consistency import run_checks
    rows = []
    with agg_db.cursor() as cur:
        cur.execute("""SELECT m.championship_id, m.faction1_team_id AS team_id FROM matches m
                        WHERE m.ingest_state = 'complete' AND m.faction1_team_id IS NOT NULL ORDER BY m.championship_id""")
        for r in cur.fetchall():
            if r["championship_id"] not in {x["championship_id"] for x in rows} and r["team_id"] not in {x["team_id"] for x in rows}:
                rows.append(r)
            if len(rows) == 2:
                break
    if len(rows) < 2:
        pytest.skip("the fixture has one championship only")
    try:
        with agg_db.cursor() as cur:
            cur.execute("UPDATE championships SET scope_region = 'na' WHERE championship_id = %s", (rows[0]["championship_id"],))
            cur.execute("UPDATE championships SET scope_region = 'emea' WHERE championship_id = %s", (rows[1]["championship_id"],))
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('x-org', 'X') ON CONFLICT DO NOTHING")
            for r in rows:
                cur.execute("INSERT INTO team_orgs (team_id, org_id, source, evidence) VALUES (%s, 'x-org', 'manual', %s)",
                            (r["team_id"], Jsonb(["cross_region_ok: decided by the owner in this test"])))
        res = {c.name: c for c in run_checks(agg_db, ["region_consistency"])}["region_consistency"]
        assert res.ok and res.counts["decided_cross_region_orgs"] == ["x-org"]
        # a Liquipedia-born team id `identity load` maps to the org is derived from the team map, not a merge decision:
        # it carries no token and must not take the owner's exception away (SpaceStation Gaming, 2026-10-02)
        with agg_db.cursor() as cur:
            cur.execute("INSERT INTO teams (team_id, name) VALUES ('lp:team:x', 'X')")
            cur.execute("""INSERT INTO team_orgs (team_id, org_id, source, evidence)
                           VALUES ('lp:team:x', 'x-org', 'manual', '["Liquipedia team name anchored to this org"]')""")
        res = {c.name: c for c in run_checks(agg_db, ["region_consistency"])}["region_consistency"]
        assert res.ok and res.counts["decided_cross_region_orgs"] == ["x-org"]
        with agg_db.cursor() as cur:
            cur.execute("UPDATE team_orgs SET evidence = '[]'::jsonb WHERE org_id = 'x-org'")
        res = {c.name: c for c in run_checks(agg_db, ["region_consistency"])}["region_consistency"]
        assert not res.ok and any(d["kind"] == "org_spans_regions" and d["key"] == "x-org" for d in res.discrepancies)
    finally:
        agg_db.rollback()
