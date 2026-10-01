"""Column descriptors: the schema saying what a column is, so no client has to guess."""

from datetime import datetime, timezone
from decimal import Decimal

from owcsmuse.nlq.columns import Column, describe, label_for, type_for

MAP_ROWS = [
    {"match_id": "1-abc", "round_number": 1, "played_at": datetime(2026, 7, 4, tzinfo=timezone.utc),
     "season": 2026, "championship_id": "c1", "competition": "S9 EMEA OWCS Central - Playoffs",
     "team": "Twisted Minds", "opponent": "qadsiah", "map_name": "Ilios", "game_mode": "Control",
     "score": 2, "opponent_score": 1, "result": "won", "role": "Damage",
     "eliminations": 20, "damage_dealt": Decimal("9730"), "kd_ratio": Decimal("2.5"),
     "match_url": "https://www.faceit.com/en/ow2/room/1-abc"},
]

SERIES_ROWS = [
    {"match_id": "1-abc", "round_number": None, "played_at": datetime(2024, 6, 2, tzinfo=timezone.utc),
     "season": 2024, "competition": "Dreamhack Dallas", "team": "Team Falcons", "opponent": "Crazy Raccoons",
     "best_of": 1, "score": 2, "opponent_score": 4, "result": "lost", "map_stats_recorded": False,
     "match_url": "https://www.faceit.com/en/ow2/room/1-abc"},
]


def by_key(rows):
    return {c["key"]: c for c in describe(rows)}


def test_a_column_carries_a_key_a_label_and_a_type():
    for column in describe(MAP_ROWS):
        assert set(column) <= {"key", "label", "type", "pair_key"}
        assert column["key"] and column["label"] and column["type"]


def test_labels_are_words_a_reader_expects():
    columns = by_key(MAP_ROWS)
    assert columns["played_at"]["label"] == "Date"
    assert columns["map_name"]["label"] == "Map"
    assert columns["damage_dealt"]["label"] == "Damage"
    assert label_for("some_new_column") == "Some new column"   # a new column still arrives readable


def test_types_drive_formatting_not_the_name_of_a_key():
    columns = by_key(MAP_ROWS)
    assert columns["played_at"]["type"] == "date"
    assert columns["eliminations"]["type"] == "integer"
    assert columns["kd_ratio"]["type"] == "decimal"
    assert columns["result"]["type"] == "result"
    assert columns["match_url"]["type"] == "link"
    assert by_key(SERIES_ROWS)["map_stats_recorded"]["type"] == "flag"


def test_a_whole_number_column_is_an_integer_even_when_postgres_says_numeric():
    """Decimal('9730') must not print as 9730.00."""
    assert by_key(MAP_ROWS)["damage_dealt"]["type"] == "integer"
    assert type_for("anything", [Decimal("1.5"), Decimal("2")]) == "decimal"
    assert type_for("anything", [Decimal("1"), Decimal("2")]) == "integer"


def test_a_percentage_is_a_percentage_wherever_it_appears():
    assert type_for("coverage_pct", [100]) == "percent"
    assert type_for("some_rate_pct", [12.5]) == "percent"


def test_a_score_and_its_opposite_number_are_one_column():
    columns = describe(MAP_ROWS)
    score = next(c for c in columns if c["key"] == "score")
    assert score == {"key": "score", "label": "Score", "type": "score", "pair_key": "opponent_score"}
    assert "opponent_score" not in {c["key"] for c in columns}


def test_ids_are_carried_on_the_row_but_never_described_as_columns():
    keys = {c["key"] for c in describe(MAP_ROWS)}
    assert "match_id" not in keys and "championship_id" not in keys
    assert "match_id" in MAP_ROWS[0]           # still there for keying and linking


def test_a_column_empty_at_this_grain_is_left_out():
    assert "round_number" not in {c["key"] for c in describe(SERIES_ROWS)}
    assert "round_number" in {c["key"] for c in describe(MAP_ROWS)}


def test_the_source_link_comes_last_whatever_order_it_arrived_in():
    assert describe(MAP_ROWS)[-1]["key"] == "match_url"
    reordered = [{"match_url": "u", "team": "T", "season": 2026}]
    assert [c["key"] for c in describe(reordered)] == ["team", "season", "match_url"]


def test_an_entity_object_on_a_ranked_row_is_not_a_column():
    ranked = [{"player_id": "p1", "nickname": "kevsteer", "total": 1109,
               "entity": {"id": "p1", "type": "player", "name": "kevsteer", "column": "player_id"}}]
    keys = {c["key"] for c in describe(ranked)}
    assert keys == {"nickname", "total"}


def test_no_rows_no_columns():
    assert describe([]) == []
    assert Column("k", "K", "text").as_dict() == {"key": "k", "label": "K", "type": "text"}


def test_a_season_is_an_identifier_not_a_quantity():
    """'2,026' is how a count reads; a season or a year names something and is never separated."""
    assert type_for("season", [2026]) == "identifier"
    assert type_for("year", [2025]) == "identifier"
    assert type_for("first_season", [2024]) == "identifier"
    assert type_for("last_year", [2026]) == "identifier"
    assert by_key(MAP_ROWS)["season"]["type"] == "identifier"
    assert by_key(SERIES_ROWS)["season"]["type"] == "identifier"
    # a genuine quantity keeps its type, and so its separators
    assert type_for("damage_dealt", [Decimal("9730")]) == "integer"
    assert type_for("maps", [1482]) == "integer"


def test_no_numeric_key_that_names_a_season_or_year_is_typed_as_a_quantity():
    from owcsmuse.nlq.columns import TYPES

    for key, kind in TYPES.items():
        if "season" in key.split("_") or "year" in key.split("_"):
            assert kind in ("identifier", "list"), f"{key} is typed {kind}"
