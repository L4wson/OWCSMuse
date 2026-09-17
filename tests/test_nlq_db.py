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


def test_head_to_head(agg_db):
    a = ask(agg_db, "Twisted Minds vs Ex Oblivione")
    assert a.status == "ok"
    r = a.rows[0]
    assert (r["team"], r["wins"], r["losses"], r["matches"]) == ("Twisted Minds", 2, 0, 2)
    b = ask(agg_db, "Ex Oblivione vs Twisted Minds")
    assert (b.rows[0]["team"], b.rows[0]["wins"], b.rows[0]["losses"]) == ("Ex Oblivione", 0, 2)


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
    for q, code in [("who has the best hero pool", "unsupported_metric"), ("best team in korea", "out_of_scope"),
                    ("most eliminations in 2023", "no_data"), ("most eliminations on Numbani", "no_data")]:
        a = ask(agg_db, q)
        assert a.status == "cannot_answer" and a.code == code, (q, a.code, a.reason)
        assert render_text(a).startswith("Can't answer that")


def test_no_rows_is_reported_as_no_data(agg_db):
    a = ask(agg_db, "KSAA eliminations on Suravasa in 2026")  # KSAA did not play in 2026
    assert a.status == "cannot_answer" and a.code == "no_data"
