"""FACEIT fabricates a map when a sweep closes a series early (a default win for the winner on the next map in the
rotation). `liquipedia phantoms` must find such a row from stored data: as a linked series where FACEIT exceeds
Liquipedia, as a placeholder-shaped map row, and name the map Liquipedia does not have."""

from __future__ import annotations

import os

import pytest

from owcsmuse.liquipedia import phantoms
from owcsmuse.liquipedia.pipeline import run_reconciliation

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


def _run(conn, tmp_path):
    from liquipedia_support import write_map_file
    return run_reconciliation(conn, map_path=str(write_map_file(tmp_path / "map.json")), team_map_path=str(tmp_path / "tm.json"),
                              decisions_path=str(tmp_path / "ld.json"))


def test_a_clean_linked_series_is_not_reported(lp_db, tmp_path):
    rep = phantoms.find(lp_db, _run(lp_db, tmp_path), str(tmp_path / "tm.json"))
    assert rep.linked_checked == 1 and rep.excess == [] and rep.rows == []


def test_a_phantom_map_is_found_by_both_signals_and_named(lp_db, tmp_path):
    """The fixture: FACEIT 3-1 over four maps, Liquipedia 3-1 over four games. Plant FACEIT's artifact: a fifth map,
    Dorado, a default Control-shaped 1-0 win for the winner with no player rows, and the stored score bumped to 4-1."""
    from liquipedia_support import DB_FACEIT_ID, DB_TEAM1, DB_TEAM2
    with lp_db.cursor() as cur:
        # give the real maps player rows, so a map without any stands out
        cur.execute("INSERT INTO players (player_id, nickname) VALUES ('p-x', 'x') ON CONFLICT DO NOTHING")
        for i in range(1, 5):
            cur.execute("""INSERT INTO match_players (match_id, round_number, player_id, team_id, nickname_at_match, stats)
                           VALUES (%s, %s, 'p-x', %s, 'x', '{}'::jsonb)""", (DB_FACEIT_ID, i, DB_TEAM1))
        cur.execute("""INSERT INTO match_rounds (match_id, round_number, map_name, game_mode, team1_team_id, team1_score,
                                                  team2_team_id, team2_score, winner_team_id)
                       VALUES (%s, 5, 'Dorado', 'Control', %s, 1, %s, 0, %s)""", (DB_FACEIT_ID, DB_TEAM1, DB_TEAM2, DB_TEAM1))
        cur.execute("UPDATE matches SET faction1_score = 4 WHERE match_id = %s", (DB_FACEIT_ID,))
    lp_db.commit()
    try:
        rep = phantoms.find(lp_db, _run(lp_db, tmp_path), str(tmp_path / "tm.json"))
        assert len(rep.excess) == 1
        e = rep.excess[0]
        assert (e.faceit_score, e.lp_score, e.faceit_maps, e.lp_games, e.extra_maps) == ("4-1", "3-1", 5, 4, ["Dorado"])
        assert e.stored_best_of == 5 and not e.sweep
        assert e.link_tier == "ambiguous"            # the inflated score makes the exact id disagree: held, not linked
        assert [r.round_number for r in rep.rows] == [5]
        r = rep.rows[0]
        assert r.map_name == "Dorado" and r.last_map and r.linked and r.beyond_liquipedia and r.player_rows == 0
        assert any("no player rows" in x for x in r.reasons) and any("Control scored 1-0" in x for x in r.reasons)
        text = phantoms.render(rep)
        assert "Dorado" in text and "| 4-1 / 5 | 3-1 / 4 |" in text
        assert rep.clustering()["extra_map_names"] == ["Dorado"] and rep.clustering()["excess_held_ambiguous"] == 1
    finally:
        with lp_db.cursor() as cur:
            cur.execute("DELETE FROM match_rounds WHERE match_id = %s AND round_number = 5", (DB_FACEIT_ID,))
            cur.execute("DELETE FROM match_players WHERE match_id = %s", (DB_FACEIT_ID,))
            cur.execute("UPDATE matches SET faction1_score = 3 WHERE match_id = %s", (DB_FACEIT_ID,))
        lp_db.commit()
