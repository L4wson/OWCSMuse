"""A tied map is nobody's win, and no series presents a score its best-of cannot hold."""

from __future__ import annotations

import os

import pytest

from owcsmuse.consistency import run_checks

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


@pytest.fixture
def complete_match(agg_db):
    """A complete series with map rows; restored afterwards by rollback."""
    row = _one(agg_db, """
        SELECT m.match_id, m.faction1_team_id AS t1, m.faction2_team_id AS t2, m.faction1_score AS s1, m.faction2_score AS s2,
               m.best_of, (SELECT count(*) FROM match_rounds r WHERE r.match_id = m.match_id) AS maps
          FROM matches m WHERE m.ingest_state = 'complete' ORDER BY maps DESC LIMIT 1""")
    yield row
    agg_db.rollback()


def test_faceits_draw_counted_as_a_win_is_corrected_from_the_map_results(agg_db, complete_match):
    m = complete_match
    before = _one(agg_db, "SELECT score1, score2, score_source, best_of_source FROM series WHERE match_id = %s", [m["match_id"]])
    assert before["score_source"] == "faceit" and before["best_of_source"] == "faceit"
    # make map 1 a 3-3 draw that FACEIT still credits to the series winner: the stored series score then counts the
    # draw as that side's win, exactly the production shape (4-0 with four maps, one of them 3-3)
    winner = m["t1"] if m["s1"] > m["s2"] else m["t2"]
    with agg_db.cursor() as cur:
        cur.execute("UPDATE match_rounds SET team1_score = 3, team2_score = 3, winner_team_id = %s WHERE match_id = %s AND round_number = 1",
                    [winner, m["match_id"]])
    maps = _one(agg_db, "SELECT bool_or(won) AS any_won, bool_and(drawn) AS all_drawn FROM fact_team_maps WHERE match_id = %s AND round_number = 1", [m["match_id"]])
    assert maps == {"any_won": False, "all_drawn": True}                           # a draw is a draw for both sides, whatever winner_team_id says
    after = _one(agg_db, "SELECT score1, score2, score_source, best_of, best_of_source FROM series WHERE match_id = %s", [m["match_id"]])
    assert after["score_source"] == "maps"                                         # FACEIT's draw-as-win is corrected
    assert (after["score1"], after["score2"]) == _expected_map_wins(agg_db, m)
    # the best-of is derived from actual map wins, not from the inflated stored score: a 3-0 with a 3-3 map stays a
    # best-of-5, never a best-of-7 (and never fewer maps than were recorded)
    wins = max(after["score1"], after["score2"])
    assert after["best_of"] == max(2 * wins - 1, m["maps"] + (m["maps"] % 2 == 0)) and after["best_of"] <= m["best_of"]
    assert after["best_of"] != 2 * (wins + 1) - 1
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["scores_corrected_from_maps"] == 1 and r.counts["drawn_maps"] == 1
    # the series-grain record follows the corrected score; the stored FACEIT columns are untouched
    stored = _one(agg_db, "SELECT faction1_score, faction2_score FROM matches WHERE match_id = %s", [m["match_id"]])
    assert stored["faction1_score"] + stored["faction2_score"] == after["score1"] + after["score2"] + 1
    rec = _one(agg_db, "SELECT map_wins, map_losses, score_source FROM fact_team_matches WHERE match_id = %s AND team_id = %s", [m["match_id"], m["t1"]])
    assert (rec["map_wins"], rec["map_losses"], rec["score_source"]) == (after["score1"], after["score2"], "maps")


def _expected_map_wins(conn, m):
    row = _one(conn, """
        SELECT count(*) FILTER (WHERE winner_team_id = %s AND NOT map_is_drawn(team1_score, team2_score, winner_team_id)) AS w1,
               count(*) FILTER (WHERE winner_team_id = %s AND NOT map_is_drawn(team1_score, team2_score, winner_team_id)) AS w2
          FROM match_rounds WHERE match_id = %s""", [m["t1"], m["t2"], m["match_id"]])
    return row["w1"], row["w2"]


def test_a_stored_best_of_of_one_is_junk_and_the_best_of_comes_from_the_played_map_wins(agg_db, complete_match):
    m = complete_match
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 1 WHERE match_id = %s", [m["match_id"]])   # Dreamhack Dallas's shape
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    w1, w2 = _expected_map_wins(agg_db, m)
    assert s["best_of"] == max(2 * max(w1, w2) - 1, m["maps"] + (m["maps"] % 2 == 0)) and s["best_of_source"] == "derived from map wins"
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["best_of_derived_from_map_wins"] == 1 and r.counts["best_of_raised"] == 1
    assert r.counts["best_of_corrections"][0]["stored"] == 1 and r.counts["best_of_corrections"][0]["series_id"] == "faceit:" + m["match_id"]


def _replace_maps(conn, m, winners):
    """Replace the fixture match's maps with Control maps won by the given sides (1 or 2), no player rows."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM match_players WHERE match_id = %s", [m["match_id"]])
        cur.execute("DELETE FROM match_rounds WHERE match_id = %s", [m["match_id"]])
        for i, w in enumerate(winners, 1):
            cur.execute("""INSERT INTO match_rounds (match_id, round_number, map_name, game_mode, team1_team_id, team1_score,
                                                      team2_team_id, team2_score, winner_team_id)
                           VALUES (%s, %s, %s, 'Control', %s, %s, %s, %s, %s)""",
                        [m["match_id"], i, f"Map {i}", m["t1"], 2 if w == 1 else 0, m["t2"], 2 if w == 2 else 0, m["t1"] if w == 1 else m["t2"]])


def test_four_played_map_wins_is_a_best_of_seven_whatever_faceit_stored(agg_db, complete_match):
    """Al Qadsiah 1-4 Twisted Minds (2025-10-26): five real maps, four won by one side, FACEIT stored bo5."""
    m = complete_match
    _replace_maps(agg_db, m, [2, 2, 1, 2, 2])
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 5, faction1_score = 1, faction2_score = 4 WHERE match_id = %s", [m["match_id"]])
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    assert (s["best_of"], s["best_of_source"], s["score1"], s["score2"]) == (7, "derived from map wins", 1, 4)
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["best_of_raised"] == 1 and r.counts["best_of_lowered"] == 0
    assert r.counts["best_of_corrections"] == [{"series_id": "faceit:" + m["match_id"], "stored": 5, "derived": 7, "score": "1-4",
                                               "source": "derived from map wins", "state": "complete"}]


def test_more_map_wins_than_any_owcs_format_holds_is_implausible_not_invented(agg_db, complete_match):
    """The 2024 Stage 1 grand finals shape before their Liquipedia records are fetched: five wins (a phantom among
    them) in a stored bo7. No format holds five wins, so the best-of is unknown, counted, and nothing is presented."""
    m = complete_match
    _replace_maps(agg_db, m, [1, 1, 1, 1, 1])
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 7, faction1_score = 5, faction2_score = 0 WHERE match_id = %s", [m["match_id"]])
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    assert (s["best_of"], s["best_of_source"], s["score1"], s["score2"]) == (None, "implausible", 5, 0)
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["best_of_implausible"] == 1


def test_the_map_winner_is_derived_from_the_scores_and_a_contradiction_is_listed(agg_db, complete_match):
    """1-3e78e269 map 5: scored 0-3 for one team, winner_team_id the other. The scores decide everywhere."""
    m = complete_match
    _replace_maps(agg_db, m, [2, 2, 1, 2, 2])
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 5, faction1_score = 1, faction2_score = 4 WHERE match_id = %s", [m["match_id"]])
        cur.execute("UPDATE match_rounds SET winner_team_id = %s WHERE match_id = %s AND round_number = 5", [m["t1"], m["match_id"]])   # the lie
    won = _one(agg_db, "SELECT bool_or(won) FILTER (WHERE team_id = %s) AS t1_won, bool_or(won) FILTER (WHERE team_id = %s) AS t2_won "
                       "FROM fact_team_maps WHERE match_id = %s AND round_number = 5", [m["t1"], m["t2"], m["match_id"]])
    assert won == {"t1_won": False, "t2_won": True}
    s = _one(agg_db, "SELECT score1, score2, best_of FROM series WHERE match_id = %s", [m["match_id"]])
    assert (s["score1"], s["score2"], s["best_of"]) == (1, 4, 7)
    r = {c.name: c for c in run_checks(agg_db, ["map_winner_consistency", "score_plausibility"])}
    assert r["score_plausibility"].ok                                      # no 'map wins exceed the series score' from the lie
    mw = r["map_winner_consistency"]
    assert mw.ok and mw.counts["winner_contradicts_scores"] == 1
    c = mw.counts["contradictions"][0]
    assert (c["round_number"], c["team1_score"], c["team2_score"]) == (5, 0, 2) and c["stored_winner"] != c["derived_winner"]


def test_a_stored_best_of_larger_than_the_score_needs_is_lowered_and_counted_as_such(agg_db, complete_match):
    """FACEIT's best-of is not trusted either way; a lowered one is listed so a person can look at it."""
    m = complete_match
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 7 WHERE match_id = %s", [m["match_id"]])
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    assert s["best_of"] == max(2 * max(s["score1"], s["score2"]) - 1, m["maps"] + (m["maps"] % 2 == 0)) < 7
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["best_of_lowered"] == 1 and r.counts["best_of_raised"] == 0


def test_a_stored_best_of_the_score_agrees_with_is_reported_as_faceits(agg_db, complete_match):
    m = complete_match
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    assert s["best_of"] == m["best_of"] == 2 * max(s["score1"], s["score2"]) - 1 and s["best_of_source"] == "faceit"


def test_an_unplayed_series_keeps_the_stored_best_of(agg_db, complete_match):
    m = complete_match
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET faction1_score = 0, faction2_score = 0 WHERE match_id = %s", [m["match_id"]])
        cur.execute("DELETE FROM match_rounds WHERE match_id = %s", [m["match_id"]])
        cur.execute("DELETE FROM match_players WHERE match_id = %s", [m["match_id"]])
    s = _one(agg_db, "SELECT best_of, best_of_source FROM series WHERE match_id = %s", [m["match_id"]])
    assert (s["best_of"], s["best_of_source"]) == (m["best_of"], "faceit")


def test_a_drawn_map_is_not_a_player_map_win_either(agg_db, complete_match):
    m = complete_match
    with agg_db.cursor() as cur:
        cur.execute("UPDATE match_rounds SET team1_score = 2, team2_score = 2, winner_team_id = %s WHERE match_id = %s AND round_number = 1",
                    [m["t1"], m["match_id"]])
    row = _one(agg_db, "SELECT bool_or(map_won) AS won, bool_and(map_drawn) AS drawn FROM fact_player_maps WHERE match_id = %s AND round_number = 1", [m["match_id"]])
    assert row == {"won": False, "drawn": True}
