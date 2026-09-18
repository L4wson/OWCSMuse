"""Question -> structured query pairs for the deterministic parser. No database, no model."""

import pytest
from pydantic import ValidationError

from owcsmuse.nlq.parser import parse_question
from owcsmuse.nlq.schema import StructuredQuery, Unanswerable

# (question, expected subset of StructuredQuery.compact()) - filters compared exactly
SUPPORTED = [
    # ---- leaderboards
    ("Who had the most eliminations in 2024?",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"season": 2024}, "sort": "desc", "limit": 10}),
    ("top 5 healers by healing done",
     {"intent": "leaderboard", "entity": "player", "metric": "Healing Done", "filters": {}, "limit": 5}),
    ("Which player has the highest K/D ratio?",
     {"intent": "leaderboard", "entity": "player", "metric": "kd_ratio", "filters": {}}),
    ("Who has the lowest deaths per map in 2026?",
     {"intent": "leaderboard", "entity": "player", "metric": "Deaths", "filters": {"season": 2026}, "sort": "asc", "aggregation": "avg_per_map"}),
    ("Which team has the best win rate in EMEA?",
     {"intent": "leaderboard", "entity": "team", "metric": "win_rate", "filters": {"region": "emea"}}),
    ("Top 3 teams by map wins in stage 1",
     {"intent": "leaderboard", "entity": "team", "metric": "map_wins", "filters": {"championship": "stage 1"}, "limit": 3}),
    ("Who had the most final blows in the 2024 main event?",
     {"intent": "leaderboard", "entity": "player", "metric": "Final Blows", "filters": {"season": 2024, "championship": "main event"}}),
    ("who has the highest eliminations per 10 minutes",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations/10m", "filters": {}}),
    ("worst 5 players by deaths",
     {"intent": "leaderboard", "entity": "player", "metric": "Deaths", "filters": {}, "sort": "asc", "limit": 5}),
    ("who has the most healing on push maps with at least 10 maps",
     {"intent": "leaderboard", "entity": "player", "metric": "Healing Done", "filters": {"mode": "Push"}, "min_maps": 10}),
    ("Who had the most eliminations for Twisted Minds?",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"team": "twisted minds"}}),
    ("Top 10 by damage mitigated in NA",
     {"intent": "leaderboard", "entity": "player", "metric": "Damage Mitigated", "filters": {"region": "na"}, "limit": 10}),
    ("dreamhack dallas most eliminations",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"championship": "dreamhack dallas"}}),
    ("most assists on Lijiang Tower",
     {"intent": "leaderboard", "entity": "player", "metric": "Assists", "filters": {"map": "Lijiang Tower"}}),
    ("eliminations in 2024",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"season": 2024}}),
    ("which team has the most map wins",
     {"intent": "leaderboard", "entity": "team", "metric": "map_wins", "filters": {}}),
    # ---- a single entity's stat
    ("How many eliminations did KSAA have in 2024?",
     {"intent": "entity_stat", "entity": "player", "metric": "Eliminations", "filters": {"subject": "ksaa", "season": 2024}, "aggregation": "total"}),
    ("What was KSAA's average healing on control maps?",
     {"intent": "entity_stat", "entity": "player", "metric": "Healing Done", "filters": {"subject": "ksaa", "mode": "Control"}, "aggregation": "avg_per_map"}),
    ("KSAA damage dealt on Lijiang Tower",
     {"intent": "entity_stat", "entity": "player", "metric": "Damage Dealt", "filters": {"subject": "ksaa", "map": "Lijiang Tower"}}),
    ("average damage per map for Quartz03 in 2026",
     {"intent": "entity_stat", "entity": "player", "metric": "Damage Dealt", "filters": {"subject": "quartz03", "season": 2026}, "aggregation": "avg_per_map"}),
    ("what is player kellemanden's kd",
     {"intent": "entity_stat", "entity": "player", "metric": "kd_ratio", "filters": {"player": "kellemanden"}}),
    ("How much damage did team ENCE deal in stage 2?",
     {"intent": "entity_stat", "entity": "team", "metric": "Damage Dealt", "filters": {"team": "ence", "championship": "stage 2"}}),
    ("show me Vestola's deaths",
     {"intent": "entity_stat", "entity": "player", "metric": "Deaths", "filters": {"subject": "vestola"}}),
    # ---- team records
    ("What is Twisted Minds' record in 2024?",
     {"intent": "team_record", "entity": "team", "metric": "record", "filters": {"subject": "twisted minds", "season": 2024}}),
    ("Twisted Minds win rate",
     {"intent": "team_record", "entity": "team", "metric": "win_rate", "filters": {"subject": "twisted minds"}}),
    ("how many maps did Twisted Minds play in 2024",
     {"intent": "team_record", "entity": "team", "metric": "maps", "filters": {"subject": "twisted minds", "season": 2024}}),
    ("how many matches did ENCE win in 2024",
     {"intent": "team_record", "entity": "team", "metric": "wins", "filters": {"subject": "ence", "season": 2024}}),
    ("ENCE record on control",
     {"intent": "team_record", "entity": "team", "metric": "record", "filters": {"subject": "ence", "mode": "Control"}}),
    ("Twisted Minds standings",
     {"intent": "team_record", "entity": "team", "metric": "record", "filters": {"subject": "twisted minds"}}),
    # ---- head to head
    ("Twisted Minds vs ENCE",
     {"intent": "versus", "entity": "team", "metric": "map_win_rate", "filters": {"subject": "twisted minds", "opponent": "ence"}}),
    ("How did Twisted Minds do against ENCE in 2024?",
     {"intent": "versus", "entity": "team", "metric": "map_win_rate", "filters": {"subject": "twisted minds", "opponent": "ence", "season": 2024}}),
    ("Head to head between Spacestation and Ex Oblivione",
     {"intent": "versus", "entity": "team", "metric": "map_win_rate", "filters": {"subject": "spacestation", "opponent": "ex oblivione"}}),
    ("Twisted Minds series record against ENCE in stage 1",
     {"intent": "head_to_head", "entity": "team", "metric": "record", "filters": {"team": "twisted minds", "opponent": "ence", "championship": "stage 1"}}),
    # ---- map / mode rows
    ("Which map does Twisted Minds win the most?",
     {"intent": "map_stats", "entity": "map", "metric": "map_win_rate", "filters": {"subject": "twisted minds"}}),
    ("What are the most played maps in 2024?",
     {"intent": "map_stats", "entity": "map", "metric": "maps", "filters": {"season": 2024}}),
    ("Best mode for KSAA",
     {"intent": "map_stats", "entity": "mode", "metric": "map_win_rate", "filters": {"subject": "ksaa"}}),
    ("Best control map for ENCE",
     {"intent": "map_stats", "entity": "map", "metric": "map_win_rate", "filters": {"subject": "ence", "mode": "Control"}}),
    ("KSAA eliminations by map",
     {"intent": "map_stats", "entity": "map", "metric": "Eliminations", "filters": {"subject": "ksaa"}}),
    # ---- stat availability
    ("What stats are available?",
     {"intent": "stat_availability", "filters": {}}),
    ("Do you have final blows for 2024?",
     {"intent": "stat_availability", "metric": "Final Blows", "filters": {"season": 2024}}),
    ("Which seasons have healing data",
     {"intent": "stat_availability", "metric": "Healing Done", "filters": {}}),
    ("what stats do you have for 2026",
     {"intent": "stat_availability", "filters": {"season": 2026}}),
]

UNANSWERABLE = [
    ("Who has the best hero pool?", {"unsupported_metric"}),
    ("What's Korea's best team?", {"out_of_scope"}),
    ("When is the next match for Twisted Minds?", {"out_of_scope"}),
    ("Who will win OWCS 2026?", {"out_of_scope"}),
    ("How much prize money did Twisted Minds earn?", {"unsupported_metric"}),
    ("Who had the most accuracy?", {"unsupported_metric"}),
    ("Show me the open qualifier results", {"out_of_scope"}),
    ("What is KSAA's rating?", {"unsupported_metric"}),
    ("Tell me about the weather", {"unsupported_metric", "unsupported_question"}),
    ("", {"invalid_query"}),
    ("   ", {"invalid_query"}),
    ("Who is the best?", {"unsupported_metric"}),
    ("KSAA stats", {"unsupported_metric"}),
    ("record", {"unsupported_question"}),
    ("what is the meaning of life", {"unsupported_metric", "unsupported_question"}),
    ("Who had the most ultimates in 2024?", {"unsupported_metric"}),
    ("What was the FACEIT elo of KSAA", {"out_of_scope"}),
]


@pytest.mark.parametrize("question,expected", SUPPORTED, ids=[q for q, _ in SUPPORTED])
def test_supported_question_parses_to_expected_query(question, expected):
    result = parse_question(question)
    assert isinstance(result, StructuredQuery), getattr(result, "reason", result)
    got = result.compact()
    for key, value in expected.items():
        assert got.get(key) == value, f"{key}: expected {value!r}, got {got.get(key)!r}; full={got}"


@pytest.mark.parametrize("question,codes", UNANSWERABLE, ids=[q or "<empty>" for q, _ in UNANSWERABLE])
def test_unanswerable_questions_return_a_specific_reason(question, codes):
    result = parse_question(question)
    assert isinstance(result, Unanswerable), result
    assert result.code in codes, (result.code, result.reason)
    assert result.reason and len(result.reason) > 10


def test_parsed_object_is_validated_by_pydantic():
    q = parse_question("top 500 players by eliminations")
    assert isinstance(q, StructuredQuery) and q.limit == 100  # clamped to the schema max
    with pytest.raises(ValidationError):
        StructuredQuery(intent="leaderboard", entity="player", metric="Eliminations", limit=0)
    with pytest.raises(ValidationError):
        StructuredQuery(intent="teleport", entity="player")


def test_suite_size():
    assert len(SUPPORTED) + len(UNANSWERABLE) >= 40
