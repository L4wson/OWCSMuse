"""Validator and compiler tests with a hand-built SchemaInfo: no database, no model."""

import pytest

from owcsmuse.nlq.compile import Compiled, Resolved, compile_query
from owcsmuse.nlq.parser import parse_question
from owcsmuse.nlq.schema import Filters, StructuredQuery, Unanswerable
from owcsmuse.nlq.validate import SchemaInfo, Validated, validate

INFO = SchemaInfo(
    stat_keys={
        "Eliminations": {2024, 2026}, "Deaths": {2024, 2026}, "Assists": {2024, 2026}, "Damage Dealt": {2024, 2026},
        "Healing Done": {2024, 2026}, "Damage Mitigated": {2024, 2026}, "K/D Ratio": {2024, 2026}, "Result": {2024, 2026},
        "Final Blows": {2026}, "Time Played": {2026}, "Eliminations/10m": {2026}, "Solo Kills": {2026},
    },
    maps={"Lijiang Tower", "Blizzard World", "Esperança", "Suravasa", "Colosseo", "Midtown"},
    modes={"Control", "Hybrid", "Push", "Flashpoint"},
    seasons={2024, 2026},
    championships={
        "f57f9c5f": "OWCS 2024: EMEA Stage 1 - Main Event",
        "7af2d2fa": "OWCS 2024: NA Stage 1 - Main Event",
        "9c926cbf": "OWCS 2024: EMEA Stage 1 - Group A",
        "05eef1be": "OWCS 2026 OQ - EMEA",
    },
    regions={"emea", "na"},
)
R_PLAYER = Resolved(player_id="p1", names={"player": "KSAA0"})
R_TEAM = Resolved(team_id="t1", names={"team": "Twisted Minds"})
R_H2H = Resolved(team_id="t1", opponent_id="t2", names={"team": "Twisted Minds", "opponent": "ENCE"})


def parse(q: str) -> StructuredQuery:
    r = parse_question(q)
    assert isinstance(r, StructuredQuery), r
    return r


def val(q: str) -> Validated:
    v = validate(parse(q), INFO)
    assert isinstance(v, Validated), v
    return v


# ------------------------------------------------------------------- validation

def test_valid_leaderboard_passes_and_keeps_query():
    v = val("who had the most eliminations in 2024")
    assert v.query.metric == "Eliminations" and v.championship_ids == [] and v.notes == []


def test_unknown_stat_key_is_rejected_with_suggestion():
    q = StructuredQuery(intent="leaderboard", entity="player", metric="Elimination Count")
    u = validate(q, INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_metric"
    assert any("Eliminations" in s for s in u.suggestions)


def test_stat_missing_in_requested_season_is_no_data():
    u = validate(parse("who had the most final blows in 2024"), INFO)
    assert isinstance(u, Unanswerable) and u.code == "no_data"
    assert "2026" in u.reason and "Final Blows" in u.reason


def test_per_10_minute_stat_only_where_faceit_provides_it():
    assert isinstance(val("who has the highest eliminations per 10 minutes"), Validated)  # exists in 2026
    q = StructuredQuery(intent="leaderboard", entity="player", metric="Healing Done/10m")
    u = validate(q, INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_metric" and "per-10-minute" in u.reason


def test_unknown_season_map_mode_region():
    u = validate(parse("most eliminations in 2023"), INFO)
    assert u.code == "no_data" and "2024, 2026" in u.reason
    u = validate(parse("most eliminations on Numbani"), INFO)
    assert u.code == "no_data" and "Numbani" in u.reason
    u = validate(StructuredQuery(intent="leaderboard", entity="player", metric="Eliminations", filters=Filters(mode="Clash")), INFO)
    assert u.code == "no_data" and "Clash" in u.reason
    u = validate(StructuredQuery(intent="leaderboard", entity="player", metric="Eliminations", filters=Filters(region="international")), INFO)
    assert u.code == "no_data"


def test_championship_text_resolves_to_ids_and_notes_multiples():
    v = val("most eliminations in the 2024 main event")
    assert set(v.championship_ids) == {"f57f9c5f", "7af2d2fa"} and any("2 championships" in n for n in v.notes)
    v = val("most eliminations in the EMEA main event")
    assert v.championship_ids == ["f57f9c5f"] and v.notes == []
    u = validate(parse("most eliminations in the world finals"), INFO)
    assert isinstance(u, Unanswerable) and u.code == "no_data" and "world finals" in u.reason


def test_slicing_a_non_typed_stat_by_map_is_rejected_specifically():
    q = StructuredQuery(intent="leaderboard", entity="player", metric="K/D Ratio", filters=Filters(map="Lijiang Tower"))
    u = validate(q, INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_metric" and "K/D Ratio" in u.reason
    # typed stats are fine
    assert isinstance(validate(q.model_copy(update={"metric": "Eliminations"}), INFO), Validated)


def test_team_metric_asked_of_a_player_is_rejected():
    q = StructuredQuery(intent="leaderboard", entity="player", metric="record")
    u = validate(q, INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_metric"


def test_map_filter_is_allowed_on_versus_but_not_on_a_series_record():
    # "X vs Y" is answered at map grain now, so filtering to one map is meaningful
    assert isinstance(validate(parse("Twisted Minds vs ENCE on Lijiang Tower"), INFO), Validated)
    # the series-grain record has no map dimension to filter on
    u = validate(parse("Twisted Minds series record against ENCE on Lijiang Tower"), INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_question"


# ------------------------------------------------------------------- compilation

def _sql(v: Validated, r: Resolved) -> Compiled:
    c = compile_query(v, r)
    assert isinstance(c, Compiled), c
    assert c.sql.count("%s") == len(c.params), (c.sql, c.params)
    return c


def test_leaderboard_reuses_stat_leaderboard_function():
    c = _sql(val("top 5 by eliminations in 2024"), Resolved())
    assert "stat_leaderboard(" in c.sql
    assert c.params == ["Eliminations", 2024, None, 1, 5, "total"]
    assert c.coverage_stat == "Eliminations" and c.coverage_season == 2024


def test_leaderboard_ascending_wraps_the_function():
    c = _sql(val("worst 5 players by deaths"), Resolved())
    assert "stat_leaderboard(" in c.sql and "ORDER BY total ASC" in c.sql and c.params[-1] == 5


def test_leaderboard_average_orders_by_avg():
    c = _sql(val("highest average healing per map"), Resolved())
    assert c.params[-1] == "avg"


def test_leaderboard_sliced_by_map_uses_typed_columns_only():
    c = _sql(val("most eliminations on Lijiang Tower"), Resolved())
    assert "agg_player_stats" in c.sql and "sum_eliminations" in c.sql and "map_name = %s" in c.sql
    assert "Lijiang Tower" in c.params and "stat_leaderboard" not in c.sql


def test_leaderboard_over_several_championships_uses_any():
    c = _sql(val("most healing in the 2024 main event"), Resolved())
    lists = [p for p in c.params if isinstance(p, list)]
    assert "= ANY(%s)" in c.sql and sorted(lists[0]) == ["7af2d2fa", "f57f9c5f"]
    assert c.coverage_championship is None  # more than one championship: coverage by season only


def test_entity_stat_uses_long_format_with_coverage():
    c = _sql(val("how many eliminations did player KSAA have in 2024"), R_PLAYER)
    assert "agg_player_stat_long" in c.sql and "maps_played" in c.sql and c.params[:1] == ["p1"] and "Eliminations" in c.params
    assert c.sample_columns == ("maps_with_stat", "maps_played")


def test_entity_stat_sliced_by_mode_uses_typed_table():
    c = _sql(val("what was player KSAA's average healing on control maps"), R_PLAYER)
    assert "agg_player_stats" in c.sql and "game_mode = %s" in c.sql and "sum_healing_done" in c.sql


def test_kd_ratio_compiles_from_sums():
    c = _sql(val("which player has the highest kd"), Resolved())
    assert "sum(a.sum_eliminations)::numeric / nullif(sum(a.sum_deaths), 0)" in c.sql and "ORDER BY kd_ratio DESC" in c.sql


def test_team_record_and_map_record():
    v = validate(StructuredQuery(intent="team_record", entity="team", metric="record", filters=Filters(team="tm", season=2024)), INFO)
    c = _sql(v, R_TEAM)
    # team-level aggregates key on org_key; an unmapped team id keys as team:<id>
    assert "agg_team_matches" in c.sql and c.params == ["team:t1", 2024]
    v = validate(StructuredQuery(intent="team_record", entity="team", metric="record", filters=Filters(team="tm", mode="Control")), INFO)
    c = _sql(v, R_TEAM)
    assert "agg_team_maps" in c.sql and "game_mode = %s" in c.sql


def test_team_leaderboard_by_win_rate():
    c = _sql(val("which team has the best win rate in EMEA"), Resolved())
    assert "agg_team_matches" in c.sql and "region = %s" in c.sql and "ORDER BY win_pct DESC" in c.sql


def test_head_to_head_orders_pair_and_presents_from_first_team():
    v = validate(parse("Twisted Minds series record against ENCE in 2024"), INFO)
    c = _sql(v, Resolved(team_id="t2", opponent_id="t1", names={"team": "Twisted Minds", "opponent": "ENCE"}))
    assert "agg_head_to_head" in c.sql and c.params[2:4] == ["t1", "t2"]
    assert "sum(b_wins) AS wins" in c.sql  # first-named team is team_b
    u = compile_query(v, Resolved(team_id="t1"))
    assert isinstance(u, Unanswerable) and u.code == "invalid_query"


def test_map_stats_for_team_player_and_global():
    c = _sql(val("which map does Twisted Minds win the most"), R_TEAM)
    assert "agg_team_maps" in c.sql and "GROUP BY map_name" in c.sql and "ORDER BY win_pct" in c.sql
    c = _sql(val("KSAA eliminations by map"), R_PLAYER)
    assert "agg_player_stats" in c.sql and "eliminations_total" in c.sql
    c = _sql(val("what are the most played maps in 2024"), Resolved())
    assert "agg_map_modes" in c.sql and "avg_duration_seconds" in c.sql and "ORDER BY maps DESC" in c.sql
    c = _sql(val("best mode for KSAA"), R_PLAYER)
    assert "GROUP BY game_mode" in c.sql


def test_stat_availability_sql():
    c = _sql(val("do you have final blows for 2026"), Resolved())
    assert "stat_coverage_season" in c.sql and c.params == ["Final Blows", 2026]
    c = _sql(val("what stats are available"), Resolved())
    assert c.params == [] and "WHERE" not in c.sql


def test_every_param_is_bound_never_interpolated():
    for q, r in [("most eliminations on Lijiang Tower in 2024", Resolved()), ("KSAA damage dealt on Lijiang Tower", R_PLAYER),
                 ("Twisted Minds record on control", R_TEAM), ("Twisted Minds vs ENCE", R_H2H)]:
        c = _sql(val(q), r)
        assert "Lijiang" not in c.sql and "2024" not in c.sql and "t1" not in c.sql and "p1" not in c.sql
