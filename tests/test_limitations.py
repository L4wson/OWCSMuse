"""Known-limitation rules: which gap applies to which slice, and that the README says so too."""

from pathlib import Path

import pytest

from owcsmuse.limitations import BY_ID, LIMITATIONS, applicable, render_text

README = Path(__file__).resolve().parent.parent / "README.md"


def ids(result):
    return [r["id"] for r in result]


def test_every_limitation_has_an_id_a_title_and_a_detail():
    assert LIMITATIONS
    for lim in LIMITATIONS:
        assert lim.id and lim.id == lim.id.lower().replace(" ", "_")
        assert lim.title and not lim.title.endswith(".")
        assert len(lim.detail) > 80, lim.id


def test_the_readme_documents_every_limitation():
    """The module is the source of truth; a limitation that is not documented is a drift bug."""
    text = README.read_text(encoding="utf-8")
    missing = [lim.id for lim in LIMITATIONS if lim.id not in text]
    assert not missing, f"README.md does not document: {', '.join(missing)}"
    assert "## Known limitations" in text


def test_a_2025_only_stat_is_flagged_on_an_all_season_leaderboard():
    out = applicable(None, "leaderboard", "Final Blows")
    assert "stats_2024" in ids(out)
    note = [r for r in out if r["id"] == "stats_2024"][0]["note"]
    assert "2024" in note and "Final Blows" in note


def test_a_stat_2024_has_is_not_flagged():
    assert "stats_2024" not in ids(applicable(None, "leaderboard", "Eliminations"))
    assert "stats_2024" not in ids(applicable(None, "leaderboard", "Healing Done"))


def test_a_2025_only_stat_is_not_flagged_when_the_question_asks_for_2026():
    assert "stats_2024" not in ids(applicable(None, "leaderboard", "Final Blows", season=2026))


def test_map_duration_is_flagged_only_where_2024_is_in_the_slice():
    assert "map_duration" in ids(applicable(None, "leaderboard", "Time Played", season=2024))
    assert "map_duration" in ids(applicable(None, "leaderboard", "Time Played"))
    assert "map_duration" not in ids(applicable(None, "leaderboard", "Time Played", season=2025))


def test_region_scope_is_surfaced_on_an_unfiltered_leaderboard_only():
    assert "scope_na_emea" in ids(applicable(None, "leaderboard", "Eliminations"))
    assert "scope_na_emea" not in ids(applicable(None, "leaderboard", "Eliminations", region="emea"))
    assert "scope_na_emea" not in ids(applicable(None, "entity_stat", "Eliminations"))


def test_the_crawled_seasons_are_declared():
    assert "main_series_2025_2026" in ids(applicable(None, "entity_stat", "Eliminations", season=2025))
    assert "main_series_2025_2026" in ids(applicable(None, "entity_stat", "Eliminations", season=2026))
    assert "main_series_2025_2026" not in ids(applicable(None, "entity_stat", "Eliminations", season=2024))


def test_nothing_needs_a_database_to_be_reported():
    """Every non-offline rule works without a connection, so a CLI or a doc can ask."""
    out = applicable(None, "leaderboard", "Final Blows")
    assert out and "offline_map_stats" not in ids(out)


def test_render_text_lists_them_all():
    text = render_text()
    for lim in LIMITATIONS:
        assert lim.id in text and lim.title in text


# ------------------------------------------------------------------ with a DB

def test_offline_series_are_counted_for_the_slice(agg_db):
    """The 2026 fixture championship has no result_only series, so nothing is claimed."""
    out = applicable(agg_db, "leaderboard", "Eliminations")
    offline = [r for r in out if r["id"] == "offline_map_stats"]
    assert not offline or "series in this slice" in offline[0]["note"]


def test_a_result_only_series_raises_the_offline_limitation(agg_db):
    try:
        with agg_db.cursor() as cur:
            cur.execute("SELECT match_id FROM matches WHERE ingest_state = 'complete' LIMIT 1")
            match_id = cur.fetchone()["match_id"]
            cur.execute("UPDATE matches SET ingest_state = 'result_only' WHERE match_id = %s", (match_id,))
            # a real result_only match has no match_rounds at all; Stage 2 only fills them in from Liquipedia,
            # so a genuinely-missing one (this simulated one included) must still have none here
            cur.execute("DELETE FROM match_players WHERE match_id = %s", (match_id,))
            cur.execute("DELETE FROM match_rounds WHERE match_id = %s", (match_id,))
        out = applicable(agg_db, "leaderboard", "Eliminations")
        offline = [r for r in out if r["id"] == "offline_map_stats"]
        assert offline, ids(out)
        assert "1 series in this slice" in offline[0]["note"]
    finally:
        agg_db.rollback()


def test_the_ask_layer_carries_the_limitations_into_the_answer(agg_db):
    from owcsmuse.nlq.pipeline import ask, render_text as render_answer

    a = ask(agg_db, "who had the most eliminations?")
    assert a.status == "ok"
    assert "scope_na_emea" in ids(a.limitations)
    assert "known limitation" in render_answer(a)


def test_an_unknown_limitation_id_is_a_programming_error():
    with pytest.raises(KeyError):
        BY_ID["not_a_limitation"]
