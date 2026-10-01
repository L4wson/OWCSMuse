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
    assert maps == {"any_won": False, "all_drawn": True}                           # a draw is a draw for both sides
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


def test_a_best_of_the_score_cannot_fit_is_derived_from_the_score_and_said_so(agg_db, complete_match):
    m = complete_match
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 1 WHERE match_id = %s", [m["match_id"]])   # Dreamhack Dallas's shape
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    assert s["best_of"] == 2 * max(s["score1"], s["score2"]) - 1 and s["best_of_source"] == "derived from score"
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["best_of_derived_from_score"] == 1 and r.counts["best_of_raised"] == 1
    assert r.counts["best_of_corrections"][0]["stored"] == 1 and r.counts["best_of_corrections"][0]["series_id"] == "faceit:" + m["match_id"]


def test_four_map_wins_is_a_best_of_seven_whatever_faceit_stored(agg_db, complete_match):
    """Al Qadsiah 1-4 Twisted Minds (2025-10-26): FACEIT stored bo5, Liquipedia bo7. The rule is general."""
    m = complete_match
    w1, w2 = _expected_map_wins(agg_db, m)
    s1, s2 = (4, 1) if w1 >= w2 else (1, 4)                      # the side that won the recorded maps wins the series
    with agg_db.cursor() as cur:
        cur.execute("UPDATE matches SET best_of = 5, faction1_score = %s, faction2_score = %s WHERE match_id = %s", [s1, s2, m["match_id"]])
    s = _one(agg_db, "SELECT best_of, best_of_source, score1, score2 FROM series WHERE match_id = %s", [m["match_id"]])
    assert (s["best_of"], s["best_of_source"], s["score1"], s["score2"]) == (7, "derived from score", s1, s2)
    r = {c.name: c for c in run_checks(agg_db, ["score_plausibility"])}["score_plausibility"]
    assert r.ok and r.counts["best_of_raised"] == 1 and r.counts["best_of_lowered"] == 0
    assert r.counts["best_of_corrections"] == [{"series_id": "faceit:" + m["match_id"], "stored": 5, "derived": 7, "score": f"{s1}-{s2}",
                                               "source": "derived from score", "state": "complete"}]


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
