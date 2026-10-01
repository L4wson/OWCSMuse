"""Stage 2: map-level enrichment of result_only series. Offline logic plus one DB round trip.

The DB case is the one that matters most: it proves the three guarantees together - FACEIT wins for map stats (by
never touching a match that already has rounds), Liquipedia wins for the date on a result_only series, and no
player row is ever created from a Liquipedia-sourced map.
"""

from __future__ import annotations

from liquipedia_support import DB_FACEIT_ID_RO, DB_TEAM1, DB_TEAM2, GAMES_RO, T0, write_map_file

from owcsmuse.liquipedia.enrich import Candidate, EnrichResult, _round_scores, enrich, plan
from owcsmuse.liquipedia.matches import LPGame
from owcsmuse.liquipedia.pipeline import run_reconciliation
from owcsmuse.liquipedia.teams import TeamMap


def game(mode, winner, scores):
    return LPGame(map="Map", mode=mode, winner=winner, scores=tuple(scores))


def test_every_mode_but_push_keeps_its_own_round_count():
    assert _round_scores(game("Control", 1, [2, 1])) == (2, 1)
    assert _round_scores(game("Escort", 2, [1, 3])) == (1, 3)


def test_push_is_normalised_to_the_win_indicator_faceit_itself_uses():
    # FACEIT's own round_stats never carries the push distance, only a 1/0 win indicator (see collector data);
    # Liquipedia's literal score would not fit that column's existing semantics.
    assert _round_scores(game("Push", 1, [64.2, 88.9])) == (1, 0)
    assert _round_scores(game("Push", 2, [130.77, 54.91])) == (0, 1)
    assert _round_scores(game("Push", 0, [10, 10])) == (0, 0)


def test_by_action_groups_candidates():
    r = EnrichResult([Candidate("m1", "o1", "https://liquipedia.net/x", "enriched", games=3),
                      Candidate("m2", "o2", "https://liquipedia.net/x", "already_has_rounds")])
    grouped = r.by_action()
    assert {k: len(v) for k, v in grouped.items()} == {"enriched": 1, "already_has_rounds": 1}


# ------------------------------------------------------------------------- DB round trip

def test_enrich_inserts_maps_corrects_the_date_and_never_touches_player_rows(lp_ro_db, tmp_path):
    conn = lp_ro_db
    map_path = write_map_file(tmp_path / "liquipedia_map.json")
    team_map_path = tmp_path / "team_map.json"
    TeamMap(team_map_path).save()

    run = run_reconciliation(conn, team_map_path=str(team_map_path),
                             decisions_path=str(tmp_path / "link_decisions.json"), map_path=str(map_path))
    lk = next(x for x in run.result.links if x.faceit_id == DB_FACEIT_ID_RO)
    assert lk.tier == "exact"

    planned = plan(run)
    assert [c.action for c in planned.candidates] == ["enriched"]
    assert planned.candidates[0].games == len(GAMES_RO)

    result = enrich(conn, run, str(team_map_path))
    cand = result.candidates[0]
    assert cand.action == "enriched" and cand.games == 3

    with conn.cursor() as cur:
        cur.execute("""SELECT round_number, map_name, game_mode, team1_score, team2_score, winner_team_id, source
                        FROM match_rounds WHERE match_id = %s ORDER BY round_number""", (DB_FACEIT_ID_RO,))
        rounds = cur.fetchall()
    assert [r["source"] for r in rounds] == ["liquipedia"] * 3
    assert [r["map_name"] for r in rounds] == ["Lijiang Tower", "Colosseo", "Dorado"]
    # game 1: Control, LP winner=1 (Dallas Fuel), no flip -> team1 (Dallas Fuel) wins 2-1
    assert (rounds[0]["team1_score"], rounds[0]["team2_score"], rounds[0]["winner_team_id"]) == (2, 1, DB_TEAM1)
    # game 2: Push, LP winner=2 (Team Liquid) -> normalised to the 1/0 indicator, not the literal distance
    assert (rounds[1]["team1_score"], rounds[1]["team2_score"], rounds[1]["winner_team_id"]) == (0, 1, DB_TEAM2)
    # game 3: Escort, LP winner=1 -> 3-1
    assert (rounds[2]["team1_score"], rounds[2]["team2_score"], rounds[2]["winner_team_id"]) == (3, 1, DB_TEAM1)

    with conn.cursor() as cur:
        cur.execute("SELECT maps_played, liquipedia_played_at, date_source FROM matches WHERE match_id = %s",
                    (DB_FACEIT_ID_RO,))
        m = cur.fetchone()
        cur.execute("SELECT count(*) AS n FROM match_players WHERE match_id = %s", (DB_FACEIT_ID_RO,))
        n_players = cur.fetchone()["n"]
    assert m["maps_played"] == 3 and m["date_source"] == "liquipedia"
    assert m["liquipedia_played_at"] == T0        # Liquipedia's own time, not FACEIT's configured_at (90+ h off)
    assert n_players == 0                          # Stage 2 must never create a player row

    # a second run is a no-op: FACEIT (now) "has" rounds, so nothing is touched or duplicated
    again = enrich(conn, run, str(team_map_path))
    assert again.candidates[0].action == "already_has_rounds"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM match_rounds WHERE match_id = %s", (DB_FACEIT_ID_RO,))
        assert cur.fetchone()["n"] == 3
