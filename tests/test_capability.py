"""Capability (Stage 3 step 4): a slice with results but no player stats refuses a player-stat question
with reason code results_only, and a mixed slice names the part it could not rank. Pure: SchemaInfo by hand."""

from owcsmuse.nlq.parser import parse_question
from owcsmuse.nlq.schema import StructuredQuery, Unanswerable
from owcsmuse.nlq.validate import SchemaInfo, Validated, capability, needs, validate

INFO = SchemaInfo(
    stat_keys={"Eliminations": {2025, 2026}}, stat_kinds={"Eliminations": "countable"},
    maps={"Ilios"}, modes={"Control"}, seasons={2025, 2026},
    championships={"na26": "S9 NA OWCS Central - Playoffs", "na25": "S7 NA OWCS Central - Playoffs", "dallas": "Dreamhack Dallas 2025", "emea26": "S9 EMEA OWCS Central - Playoffs"},
    championship_display={"na26": "OWCS 2026 NA Stage 2 Playoffs", "na25": "OWCS 2025 NA Stage 2 Playoffs", "dallas": "Dreamhack Dallas 2025", "emea26": "OWCS 2026 EMEA Stage 2 Playoffs"},
    championship_season={"na26": 2026, "na25": 2025, "dallas": 2025, "emea26": 2026},
    championship_region={"na26": "na", "na25": "na", "dallas": "international", "emea26": "emea"},
    regions={"na", "emea", "international"},
    capabilities={"na26": {"map_results": True, "player_stats": True, "series": 10},
                  "na25": {"map_results": True, "player_stats": True, "series": 10},
                  "dallas": {"map_results": True, "player_stats": False, "series": 14},
                  "emea26": {"map_results": True, "player_stats": True, "series": 10}},
    region_player_stats={"na": True, "emea": True, "international": True, "korea": False},
)


def _q(text: str) -> StructuredQuery:
    q = parse_question(text)
    assert isinstance(q, StructuredQuery), q
    return q


def test_what_a_question_needs():
    assert needs(_q("who had the most eliminations"), INFO) == "player_stats"
    assert needs(_q("who has the best K/D"), INFO) == "player_stats"
    assert needs(_q("Twisted Minds record"), INFO) == "series"
    assert needs(_q("Twisted Minds map record against Geekay Esports"), INFO) == "maps"


def test_korea_is_refused_as_results_only_not_as_missing_data():
    v = validate(_q("who had the most eliminations in korea"), INFO)
    assert isinstance(v, Unanswerable) and v.code == "results_only", v
    assert "KOREA" in v.reason and "player stats" in v.reason
    assert v.suggestions and "Records" in v.suggestions[0]


def test_a_korean_team_record_is_not_refused_by_the_capability_rule():
    """Results are answerable in a results-only region; the region check itself may still say no data for it today."""
    cap, parts = capability(_q("Crazy Raccoons record in korea"), INFO, [])
    assert (cap, parts) == ("full", [])


def test_a_results_only_competition_refuses_a_player_stat_question():
    v = validate(_q("who had the most eliminations in Dreamhack Dallas 2025"), INFO)
    assert isinstance(v, Unanswerable) and v.code == "results_only", v
    assert "Dreamhack Dallas 2025" in v.reason


def test_a_results_only_competition_still_answers_records():
    v = validate(_q("Twisted Minds record in Dreamhack Dallas 2025"), INFO)
    assert isinstance(v, Validated) and not v.results_only_parts and not v.notes


def test_a_mixed_slice_names_the_part_it_cannot_rank():
    v = validate(_q("who had the most eliminations in 2025"), INFO)
    assert isinstance(v, Validated), v
    assert v.results_only_parts == ["Dreamhack Dallas 2025"]
    assert any("results only for Dreamhack Dallas 2025" in n for n in v.notes)


def test_a_slice_with_stats_everywhere_carries_no_note():
    v = validate(_q("who had the most eliminations in 2026"), INFO)
    assert isinstance(v, Validated) and not v.results_only_parts and not v.notes


def test_an_empty_championship_is_not_results_only():
    """No series at all is 'no data', never 'results only': the capability rule must not claim it."""
    info = SchemaInfo(**{**INFO.__dict__, "capabilities": {**INFO.capabilities,
                                                            "emea26": {"map_results": False, "player_stats": False, "series": 0}}})
    cap, parts = capability(_q("who had the most eliminations in 2026"), info, [])
    assert (cap, parts) == ("full", [])


def test_an_unknown_region_without_a_declaration_is_still_no_data():
    info = SchemaInfo(**{**INFO.__dict__, "region_player_stats": {}})
    v = validate(_q("who had the most eliminations in korea"), info)
    assert isinstance(v, Unanswerable) and v.code == "no_data"
