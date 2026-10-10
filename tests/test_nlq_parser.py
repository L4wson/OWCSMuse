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
    # "healers" is a real role filter now (Support), not just a synonym for "players":
    # a flex player's tank/DPS maps correctly drop out of this ranking.
    ("top 5 healers by healing done",
     {"intent": "leaderboard", "entity": "player", "metric": "Healing Done", "filters": {"role": "Support"}, "limit": 5}),
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
    # a team named in front of the player or role noun is a filter, however it is written (owner, 2026-10-08)
    ("which DF player had the most deaths in 2026",
     {"intent": "leaderboard", "entity": "player", "metric": "Deaths", "filters": {"team": "df", "season": 2026}}),
    ("which twisted minds tank had the most deaths in 2026",
     {"intent": "leaderboard", "entity": "player", "filters": {"team": "twisted minds", "season": 2026, "role": "Tank"}}),
    ("which spacestation gaming dps had the most deaths in 2026",
     {"intent": "leaderboard", "entity": "player", "filters": {"team": "spacestation gaming", "season": 2026, "role": "Damage"}}),
    ("most deaths by a twisted minds tank in 2026",
     {"intent": "leaderboard", "entity": "player", "filters": {"team": "twisted minds", "season": 2026, "role": "Tank"}}),
    ("which team liquid player had the most eliminations",
     {"intent": "leaderboard", "entity": "player", "filters": {"team": "team liquid"}}),
    ("which na support had the least deaths in 2024",          # a region in front of the noun names no team
     {"intent": "leaderboard", "entity": "player", "filters": {"season": 2024, "region": "na", "role": "Support"}}),
    ("top 5 healers by healing done",                           # nor does a limit
     {"intent": "leaderboard", "entity": "player", "filters": {"role": "Support"}, "limit": 5}),
    ("cjay vs team liquid in 2026",
     {"intent": "versus", "filters": {"subject": "cjay", "opponent": "team liquid", "season": 2026}}),
    ("team z record",
     {"intent": "team_record", "filters": {"subject": "team z"}}),
    # relative periods are read against the data later; the parser only names them (owner, 2026-10-08)
    ("which tanks have the most damage mitigated this stage",
     {"intent": "leaderboard", "filters": {"role": "Tank", "period": "this_stage"}}),
    ("Twisted Minds record this year", {"intent": "team_record", "filters": {"subject": "twisted minds", "period": "this_season"}}),
    ("who had the most eliminations last year", {"intent": "leaderboard", "filters": {"period": "last_season"}}),
    ("SSG record in the previous stage", {"intent": "team_record", "filters": {"subject": "ssg", "period": "last_stage"}}),
    ("what team is cjay on this year", {"intent": "team_membership", "filters": {"subject": "cjay", "period": "this_season"}}),
    ("who has the most healing on push maps with at least 10 maps",
     {"intent": "leaderboard", "entity": "player", "metric": "Healing Done", "filters": {"mode": "Push"}, "min_maps": 10}),
    ("Who had the most eliminations for Twisted Minds?",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"team": "twisted minds"}}),
    ("Top 10 by damage mitigated in NA",
     {"intent": "leaderboard", "entity": "player", "metric": "Damage Mitigated", "filters": {"region": "na"}, "limit": 10}),
    ("who had the most eliminations in Korea",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"region": "korea"}}),
    ("Crazy Raccoons record in South Korea",
     {"intent": "team_record", "entity": "team", "metric": "record", "filters": {"region": "korea", "subject": "crazy raccoons"}}),
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
     # "team" stays in the name ("Team Liquid" is one); resolve() falls back to "ence" when "team ence" names nobody
     {"intent": "entity_stat", "entity": "team", "metric": "Damage Dealt", "filters": {"team": "team ence", "championship": "stage 2"}}),
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
    # ---- role: the bug ("tank with the most kills" returned unfiltered DPS players)
    ("tank with the most kills",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"role": "Tank"}}),
    ("tanks with the most deaths in 2024",
     {"intent": "leaderboard", "entity": "player", "metric": "Deaths", "filters": {"season": 2024, "role": "Tank"}}),
    ("dps with the most eliminations",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"role": "Damage"}}),
    ("support with the most healing done",
     {"intent": "leaderboard", "entity": "player", "metric": "Healing Done", "filters": {"role": "Support"}}),
    ("who had the most kills as tank",
     {"intent": "leaderboard", "entity": "player", "metric": "Eliminations", "filters": {"role": "Tank"}}),
    ("KSAA eliminations as tank",
     {"intent": "entity_stat", "entity": "player", "metric": "Eliminations", "filters": {"subject": "ksaa", "role": "Tank"}}),
    ("KSAA kills playing support",
     {"intent": "entity_stat", "entity": "player", "metric": "Eliminations", "filters": {"subject": "ksaa", "role": "Support"}}),
    # "damage" alone stays the metric (Damage Dealt), never the role - only the
    # unambiguous shorthand "dps" names the role, so this must NOT carry a role filter
    ("who had the most damage",
     {"intent": "leaderboard", "entity": "player", "metric": "Damage Dealt", "filters": {}}),
]

UNANSWERABLE = [
    ("Who has the best hero pool?", {"unsupported_metric"}),
    ("What's Korea's best team?", {"unsupported_metric"}),   # Korea is a region now, not out of scope; "best team" still needs a stat
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


@pytest.mark.parametrize("question,name,season", [
    ("what team is cjay on", "cjay", None),
    ("What team is Cjay on?", "cjay", None),
    ("which team does ksaa play on now", "ksaa", None),
    ("who does sugarfree play for", "sugarfree", None),
    ("who is hadi on", "hadi", None),
    ("Sugarfree's team", "sugarfree", None),
    ("ksaa's previous teams", "ksaa", None),
    ("cjay team history", "cjay", None),
    ("team history of ksaa", "ksaa", None),
    ("what team was ksaa on in 2024", "ksaa", 2024),
])
def test_team_membership_phrasings(question, name, season):
    """A player's team now and before used to land on 'which stat for cjay?'."""
    parsed = parse_question(question)
    assert isinstance(parsed, StructuredQuery), parsed
    assert parsed.intent == "team_membership"
    assert parsed.filters.subject == name
    assert parsed.filters.season == season


@pytest.mark.parametrize("question", [
    "Twisted Minds record", "who had the most eliminations on team Liquid", "ksaa eliminations",
    "which team has the best record in 2024", "Twisted Minds vs ENCE",
])
def test_membership_cues_do_not_swallow_other_questions(question):
    parsed = parse_question(question)
    assert not (isinstance(parsed, StructuredQuery) and parsed.intent == "team_membership")


@pytest.mark.parametrize("question,championship,season,region", [
    ("who had the most eliminations in OWCS 2026 NA Stage 2 Playoffs", "stage 2 playoffs", 2026, "na"),
    ("SpaceStation Gaming record in OWCS 2026 NA Stage 2 Regular Season", "stage 2 regular season", 2026, "na"),
    ("Twisted Minds record in OWCS 2025 EMEA Stage 3 Playoffs", "stage 3 playoffs", 2025, "emea"),
    ("most eliminations at dreamhack dallas", "dreamhack dallas", None, None),
])
def test_a_competition_phrase_is_kept_whole(question, championship, season, region):
    """Keeping only the longest term turned 'Stage 2 Playoffs' into 'playoffs': both stages' playoffs, silently."""
    parsed = parse_question(question)
    assert isinstance(parsed, StructuredQuery), parsed
    assert (parsed.filters.championship, parsed.filters.season, parsed.filters.region) == (championship, season, region)


def test_the_brand_word_is_not_part_of_a_team_name():
    parsed = parse_question("SpaceStation Gaming record in OWCS 2026 NA Stage 2 Regular Season")
    assert parsed.filters.subject == "spacestation gaming"


# ---- Stage 4: placings, and the international events' names



@pytest.mark.parametrize("question, place, subject", [
    ("who won the 2025 world finals", 1, None),
    ("Who won the 2025 Champions Clash?", 1, None),
    ("who won ewc 2024", 1, None),
    ("who placed second at the 2025 world finals", 2, None),
    ("who was runner up at the 2025 world finals", 2, None),
    ("who placed 7th at the 2025 world finals", 7, None),
    ("where did spacestation place at the 2025 world finals", None, "spacestation"),
    ("crazy raccoon placement at the 2025 world finals", None, "crazy raccoon"),
    ("2025 world finals standings", None, None),
])
def test_a_placing_question_names_its_event(question, place, subject):
    q = parse_question(question)
    assert q.intent == "placement" and q.filters.place == place and q.filters.subject == subject
    assert q.filters.championship and q.filters.mode is None


def test_who_won_the_most_series_is_still_a_leaderboard():
    assert parse_question("who won the most series at the 2025 world finals").intent == "leaderboard"


def test_who_won_without_an_event_is_not_a_placing():
    assert getattr(parse_question("who won in 2025"), "intent", None) != "placement"


def test_champions_clash_is_an_event_not_the_clash_mode_and_ewc_is_the_esports_world_cup():
    q = parse_question("crazy raccoon record at the 2025 champions clash")
    assert q.filters.subject == "crazy raccoon" and q.filters.mode is None and q.filters.championship == "champions clash"
    q = parse_question("crazy raccoon record at ewc 2024")
    assert q.filters.subject == "crazy raccoon" and q.filters.championship == "esports world cup"
    assert parse_question("twisted minds record on clash maps in 2025").filters.mode == "Clash"



# ---- partner teams (043): the group itself, or a team question restricted to it

@pytest.mark.parametrize("question, season, region", [
    ("which teams are the partner teams", None, None),
    ("who were the 2025 partner teams", 2025, None),
    ("partner teams in 2026", 2026, None),
    ("list the NA partner teams", None, "na"),
])
def test_asking_for_the_partner_teams_is_the_group(question, season, region):
    q = parse_question(question)
    assert (q.intent, q.filters.group, q.filters.season, q.filters.region) == ("team_group", "partner", season, region)


def test_a_partner_ranking_keeps_its_intent_and_restricts_it():
    q = parse_question("which partner team won the most series in 2026")
    assert (q.intent, q.entity, q.metric, q.filters.group, q.filters.season) == ("leaderboard", "team", "wins", "partner", 2026)
    assert parse_question("twisted minds record in 2026").filters.group is None
