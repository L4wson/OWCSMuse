"""Anchors and Liquipedia name history on real Postgres: a decided page makes its handle and real name searchable,
a Liquipedia-born player exists as itself, and a decided team name gives the org its Liquipedia names."""

from __future__ import annotations

import os

import pytest
from liquipedia_support import DB_TEAM1, DB_TEAM2, build_liquipedia_scratch_db, write_map_file

from owcsmuse.liquipedia import identity as ident
from owcsmuse.liquipedia import pipeline
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.resolve import resolve

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test") + "_identity"
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

G_HYDRON, G_COLUGE, G_ZERUHH = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "33333333-cccc-4ccc-8ccc-cccccccccccc"


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    conn, raw = build_liquipedia_scratch_db(
        DB_URL, SCHEMA,
        rosters={DB_TEAM1: [(G_HYDRON, "Hydron", "Hydron#1234"), (G_COLUGE, "Coluge", None)],
                 DB_TEAM2: [(G_ZERUHH, "zeruhh", "Zeruhh#5678")]},
        lp_players=([("Hydron_(Ethan_Rose)", "Hydron", "United States"), ("Coluge", "Coluge", "United States")],
                    [("Zeruhh", "Zeruhh", "Canada"), ("HYEON_(Kim_Seong-hyeon)", "HYEON", "South Korea")]))
    d = tmp_path_factory.mktemp("maps")
    map_path = write_map_file(d / "map.json")
    team_map = TeamMap(d / "team_map.json")
    team_map.decide("Dallas Fuel", "team", DB_TEAM1, "test")
    team_map.save()
    run = pipeline.run_reconciliation(conn, team_map_path=str(team_map.path), decisions_path=str(d / "links.json"),
                                      map_path=str(map_path))
    pipeline.store_run(conn, run)
    yield conn, run, team_map, d
    conn.close()
    raw.close()


def test_line_ups_are_stored_as_a_parsed_copy_with_name_history(warehouse):
    conn, *_ = warehouse
    with conn.cursor() as cur:
        cur.execute("SELECT side, page, handle, real_name FROM liquipedia_match_players ORDER BY side, page")
        rows = [tuple(r.values()) for r in cur.fetchall()]
        cur.execute("SELECT page, name, kind FROM lp_player_names WHERE page = 'HYEON_(Kim_Seong-hyeon)' ORDER BY kind")
        names = [tuple(r.values()) for r in cur.fetchall()]
        cur.execute("SELECT template, name FROM lp_team_names ORDER BY template")
        teams = [tuple(r.values()) for r in cur.fetchall()]
    conn.commit()
    assert (1, "Hydron_(Ethan_Rose)", "Hydron", "Ethan Rose") in rows and (2, "HYEON_(Kim_Seong-hyeon)", "HYEON", "Kim Seong-hyeon") in rows
    assert names == [("HYEON_(Kim_Seong-hyeon)", "HYEON", "lp_handle"), ("HYEON_(Kim_Seong-hyeon)", "Kim Seong-hyeon", "lp_real_name")]
    assert ("dallas fuel 2026", "Dallas Fuel") in teams and ("team liquid 2026", "Team Liquid") in teams


def test_proposals_come_from_the_linked_series_and_only_the_one_to_one_ones_are_strong(warehouse):
    conn, run, team_map, _ = warehouse
    ps = {p.page: p for p in ident.propose_players(ident.sightings(conn, run, str(team_map.path)))}
    assert ps["Hydron_(Ethan_Rose)"].strength == "strong" and ps["Hydron_(Ethan_Rose)"].guid == G_HYDRON
    assert ps["Coluge"].guid == G_COLUGE and ps["Zeruhh"].guid == G_ZERUHH          # case-folded against the FACEIT nickname
    assert ps["HYEON_(Kim_Seong-hyeon)"].strength == "unmatched"                   # nobody on FACEIT's side was HYEON


def test_load_makes_decided_names_searchable_and_a_born_player_real(warehouse):
    conn, run, team_map, d = warehouse
    decisions = ident.PlayerDecisions(d / "players.json")
    proposals = decisions.apply(ident.propose_players(ident.sightings(conn, run, str(team_map.path))))
    assert ident.accept_strong(decisions, proposals) == 3
    decisions.set("HYEON_(Kim_Seong-hyeon)", None, "HYEON", "Korean player, no FACEIT id", real_name="Kim Seong-hyeon")
    out = ident.load_identity(conn, decisions, team_map)
    assert out == {"team_anchors": 1, "liquipedia_born_teams_mapped": 0, "player_anchors": 4, "liquipedia_born_players": 1,
                   "unknown_faceit_ids_skipped": 0, "ghost_players_removed": 0}
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW entity_names")
    conn.commit()

    # the real name from the page is searchable and resolves to the FACEIT player
    cands = resolve(conn, "Ethan Rose", "player")
    assert cands and cands[0].entity_id == G_HYDRON and cands[0].name_kind == "lp_real_name"
    # the Liquipedia-born player exists as itself, under both the handle and the real name
    assert resolve(conn, "HYEON", "player")[0].entity_id == ident.BORN_PREFIX + "HYEON_(Kim_Seong-hyeon)"
    assert resolve(conn, "Kim Seong-hyeon", "player")[0].entity_id == ident.BORN_PREFIX + "HYEON_(Kim_Seong-hyeon)"
    # the decided team name gives the team its Liquipedia name(s) as searchable history
    with conn.cursor() as cur:
        cur.execute("SELECT name, name_kind FROM entity_names WHERE entity_type = 'team' AND entity_id = %s ORDER BY name_kind", [DB_TEAM1])
        rows = {tuple(r.values()) for r in cur.fetchall()}
    conn.commit()
    assert ("Dallas Fuel", "current_name") in rows and not any(k == "lp_team_name" for _, k in rows)   # same name: no duplicate row

    # withdrawing the born decision removes the ghost
    decisions.unset("HYEON_(Kim_Seong-hyeon)")
    assert ident.load_identity(conn, decisions, team_map)["ghost_players_removed"] == 1
