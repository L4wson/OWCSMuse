"""End-to-end `ask()` against Postgres with the captured fixtures (skipped without OWCS_TEST_DATABASE_URL)."""

from __future__ import annotations

import os

import pytest

from owcsmuse.aggregates import refresh
from owcsmuse.nlq.pipeline import ask, render_text

# `agg_db` (tests/conftest.py) ingests 2 matches from 2024 and 1 from 2026 into a scratch schema.

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

KSAA = "92695183-d00e-4c31-9707-ff9d8500f52a"
TWISTED_MINDS = "2b9f2e7a-f91a-4597-b2fa-d413eaed605e"


def test_leaderboard_with_coverage(agg_db):
    a = ask(agg_db, "who had the most eliminations in 2024", debug=True)
    assert a.status == "ok", a.reason
    assert a.rows and a.rows[0]["maps_with_stat"] == a.rows[0]["maps_played"]
    assert a.coverage["coverage_pct"] == 100 and a.coverage["seasons_without_stat"] is None
    assert "stat_leaderboard(" in a.sql
    assert "coverage" in render_text(a)


def test_partial_coverage_is_stated_not_silent(agg_db):
    a = ask(agg_db, "who had the most final blows")
    assert a.status == "ok"
    assert a.coverage["seasons_without_stat"] == [2024] and float(a.coverage["coverage_pct"]) < 100
    assert any("seasons without it: 2024" in n for n in a.notes)
    assert all(r["seasons"] == [2026] for r in a.rows)
    text = render_text(a)
    assert "without: 2024" in text


def test_stat_missing_for_season_is_no_data_with_reason(agg_db):
    a = ask(agg_db, "who had the most final blows in 2024")
    assert a.status == "cannot_answer" and a.code == "no_data" and "2026" in a.reason


def test_a_leaderboard_the_map_floor_empties_says_so_and_offers_the_question_without_it(agg_db):
    # 2026 is one series here: nobody has 4 maps, so a K/D leaderboard (a rate: the floor applies) ranks nobody
    a = ask(agg_db, "highest kd in 2026")
    assert a.status == "cannot_answer" and a.code == "no_data"
    assert "at least 4 maps" in a.reason and "nothing in scope matches" not in a.reason
    assert a.alternatives == ["highest kd in 2026 with at least 1 map"]
    again = ask(agg_db, a.alternatives[0])
    assert again.status == "ok" and again.rows and "at least" not in again.sentence["text"]


def test_team_in_front_of_a_name_is_kept_and_dropped_only_when_it_names_nobody(agg_db):
    # "Team Liquid" is a name and is searched whole; "team twisted minds" is the word in front of one
    a = ask(agg_db, "team twisted minds record")
    assert a.status == "ok" and a.entities["subject"]["entity_id"] == TWISTED_MINDS, a.reason


def test_the_cli_table_never_prints_a_raw_team_id_beside_its_name(agg_db):
    a = ask(agg_db, "twisted minds record")
    assert a.status == "ok" and a.rows[0]["org_key"] == f"team:{TWISTED_MINDS}"     # in the row, for clients
    assert TWISTED_MINDS not in render_text(a)                                     # not in what a reader sees


def test_player_stat_resolves_entity_and_answers(agg_db):
    a = ask(agg_db, "how many eliminations did KSAA have in 2024")
    assert a.status == "ok" and a.entities["subject"]["entity_id"] == KSAA
    row = a.rows[0]
    assert row["maps_with_stat"] == 8 and row["maps_played"] == 8 and row["total"] > 0
    assert a.query["filters"] == {"player": "ksaa", "season": 2024}  # subject retargeted to player


def test_subject_that_is_a_team_becomes_a_team_record(agg_db):
    a = ask(agg_db, "Twisted Minds record in 2024")
    assert a.status == "ok" and a.query["intent"] == "team_record" and a.entities["subject"]["entity_id"] == TWISTED_MINDS
    r = a.rows[0]
    assert (r["matches"], r["wins"], r["losses"], r["map_wins"], r["map_losses"]) == (2, 2, 0, 6, 2)


def test_head_to_head_series_grain(agg_db):
    a = ask(agg_db, "Twisted Minds series record against Ex Oblivione")
    assert a.status == "ok", a.reason
    r = a.rows[0]
    assert (r["team"], r["wins"], r["losses"], r["matches"]) == ("Twisted Minds", 2, 0, 2)
    b = ask(agg_db, "Ex Oblivione series record against Twisted Minds")
    assert (b.rows[0]["team"], b.rows[0]["wins"], b.rows[0]["losses"]) == ("Ex Oblivione", 0, 2)


def test_versus_map_grain(agg_db):
    a = ask(agg_db, "Twisted Minds vs Ex Oblivione")
    assert a.status == "ok", a.reason
    r = a.rows[0]
    # two series of 4 maps each: map grain, not series grain
    assert r["maps"] == 8 and r["matches"] == 2
    assert r["map_wins"] == 6 and r["map_losses"] == 2
    b = ask(agg_db, "Ex Oblivione vs Twisted Minds")
    assert b.rows[0]["map_wins"] == 2 and b.rows[0]["map_losses"] == 6


def test_unknown_entity_and_ambiguous_entity(agg_db):
    a = ask(agg_db, "how many eliminations did Zorblax have")
    assert a.status == "cannot_answer" and a.code == "unknown_entity"
    # two different players both matching exactly the same folded name -> clarify, never a guess
    with agg_db.cursor() as cur:
        cur.execute("INSERT INTO players (player_id, nickname) VALUES ('dupe-1', 'Twin'), ('dupe-2', 'twin')")
    agg_db.commit()
    refresh(agg_db, ["entity_names"])
    a = ask(agg_db, "how many eliminations did Twin have")
    assert a.status == "clarify" and a.code == "ambiguous_entity"
    assert {c["entity_id"] for c in a.candidates["subject"]} >= {"dupe-1", "dupe-2"}
    assert "clarification" in render_text(a)


def test_map_stats_and_mode_stats(agg_db):
    a = ask(agg_db, "what are the most played maps in 2024")
    assert a.status == "ok" and a.rows[0]["maps"] >= 1 and sum(r["maps"] for r in a.rows) == 8
    a = ask(agg_db, "best mode for KSAA")
    assert a.status == "ok" and {r["game_mode"] for r in a.rows} == {"Control", "Hybrid", "Push", "Flashpoint"}


def test_availability(agg_db):
    a = ask(agg_db, "what stats are available")
    assert a.status == "ok" and {r["season"] for r in a.rows} == {2024, 2026}
    a = ask(agg_db, "do you have final blows for 2024")
    assert a.status == "cannot_answer" and a.code == "no_data"


def test_out_of_scope_and_unsupported_paths_are_clean(agg_db):
    for q, code in [("who has the best hero pool", "unsupported_question"), ("best team in china", "out_of_scope"),
                    ("most eliminations in korea", "results_only"),
                    ("most eliminations in 2023", "no_data"), ("most eliminations on Numbani", "no_data")]:
        a = ask(agg_db, q)
        assert a.status == "cannot_answer" and a.code == code, (q, a.code, a.reason)
        assert render_text(a).startswith("Can't answer that")


def test_no_rows_is_reported_as_no_data(agg_db):
    a = ask(agg_db, "KSAA eliminations on Suravasa in 2026")  # KSAA did not play in 2026
    assert a.status == "cannot_answer" and a.code == "no_data"


def _player_in_one_season_only(conn):
    """A resolvable nickname whose maps all fall in a single season, with the warehouse's other season."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.nickname, min(f.season) AS season,
                   (SELECT array_agg(DISTINCT season) FROM fact_player_maps) AS all_seasons
              FROM fact_player_maps f JOIN players p ON p.player_id = f.player_id
             GROUP BY p.nickname HAVING count(DISTINCT f.season) = 1 ORDER BY count(*) DESC LIMIT 1""")
        row = cur.fetchone()
    conn.commit()
    return row


def test_an_entity_with_no_rows_in_the_slice_is_told_what_it_does_have(agg_db):
    """'valid but nothing matches' says nothing; the useful answer is which seasons the player does have."""
    row = _player_in_one_season_only(agg_db)
    others = [s for s in row["all_seasons"] if s != row["season"]]
    if not others:
        pytest.skip("the fixtures hold a single season")
    empty_season = others[0]

    a = ask(agg_db, f"{row['nickname']} record in {empty_season}")
    assert a.status == "cannot_answer" and a.code == "no_data"
    assert "valid but nothing" not in a.reason
    assert f"no maps with stats in {empty_season}" in a.reason
    assert str(row["season"]) in a.reason                       # names the season they do have
    assert str(empty_season) not in a.reason.split("they do have")[-1]
    swap = f"{row['nickname']} record in {row['season']}"
    assert swap in a.alternatives                              # a runnable question that works, offered by name
    again = ask(agg_db, swap)
    assert again.status == "ok"



def test_team_membership_current_team_and_history_with_date_ranges(agg_db):
    """A transfer is two stints in date order: the newest is the current team, each with its own range."""
    with agg_db.cursor() as cur:
        cur.execute("""
            SELECT r.player_id, p.nickname, array_agg(r.match_id ORDER BY m.started_at) AS matches, min(r.team_id) AS team
              FROM match_rosters r JOIN matches m USING (match_id) JOIN players p USING (player_id)
              JOIN championships c ON c.championship_id = m.championship_id
             WHERE c.include AND m.status = 'FINISHED' AND m.ingest_state IN ('complete', 'result_only')
             GROUP BY r.player_id, p.nickname HAVING count(DISTINCT m.match_id) >= 2
             ORDER BY count(*) DESC LIMIT 1""")
        who = cur.fetchone()
        cur.execute("SELECT team_id FROM team_identity WHERE team_id <> %s LIMIT 1", [who["team"]])
        other = cur.fetchone()["team_id"]
    agg_db.commit()
    first_match = who["matches"][0]

    def set_team(team_id):
        with agg_db.cursor() as cur:
            cur.execute("UPDATE match_rosters SET team_id = %s WHERE match_id = %s AND player_id = %s",
                        [team_id, first_match, who["player_id"]])
        agg_db.commit()

    from owcsmuse.nlq.membership import team_history

    try:
        set_team(other)                                   # they played their first series for someone else
        stints = team_history(agg_db, who["player_id"])
    finally:
        set_team(who["team"])
    assert [s["status"] for s in stints] == ["current", "former"]
    now, before = stints
    assert now["team_id"] == who["team"] and before["team_id"] == other
    assert before["to_at"] <= now["from_at"]               # date ranges do not overlap, newest first
    assert before["from_at"] <= before["to_at"] and now["from_at"] <= now["to_at"]

    a = ask(agg_db, f"what team is {who['nickname']} on")
    assert a.status == "ok" and a.query["intent"] == "team_membership"
    shown = a.entities["subject"]["current_name"]              # the display name, which can differ from the nickname
    assert a.sentence["text"].startswith(f"{shown} last played for ")
    assert any("no roster feed" in n for n in a.notes)


def test_team_membership_for_a_team_name_says_so(agg_db):
    a = ask(agg_db, "what team is Twisted Minds on")
    assert a.status == "cannot_answer" and "is a team, not a player" in a.reason


def test_a_korean_player_stat_question_is_refused_as_results_only_with_a_working_alternative(agg_db):
    """Korea is declared results-only before any of its data exists: the refusal says why, never 'no data',
    and offers the same question where player stats exist. It never returns an empty or partial leaderboard."""
    a = ask(agg_db, "who had the most eliminations in korea")
    assert a.status == "cannot_answer" and a.code == "results_only", (a.code, a.reason)
    assert "results-only region" in a.reason and not a.rows
    assert "who had the most eliminations" in a.alternatives
    b = ask(agg_db, "who had the most eliminations")
    assert b.status == "ok" and b.rows
    text = render_text(a)
    assert text.startswith("Can't answer that") and "who had the most eliminations" in text
