"""Validator and compiler tests with a hand-built SchemaInfo: no database, no model."""


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
    # series counted once each, from the fact view: summing agg_team_maps' per-map `matches` gave Virtus pro 57 for 15
    assert "fact_team_maps" in c.sql and "count(DISTINCT t.match_id) AS matches" in c.sql and "game_mode = %s" in c.sql


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
    assert "fact_team_maps" in c.sql and "count(DISTINCT match_id) AS matches" in c.sql
    assert "GROUP BY map_name" in c.sql and "ORDER BY win_pct" in c.sql
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


# --------------------------------------------------------------------- role

def test_role_alone_reuses_the_leaderboard_function_with_p_role():
    """The bug: "tank with the most kills" used to drop "tank" silently and rank everyone."""
    c = _sql(val("tank with the most kills"), Resolved())
    assert "stat_leaderboard(" in c.sql
    assert c.params == ["Eliminations", None, None, 1, 10, "total", "Tank"]


def test_role_combined_with_a_slice_reads_fact_player_maps_not_the_aggregate():
    # agg_player_stats has no role column; role always reads the raw per-map rows.
    c = _sql(val("tank with the most kills on Lijiang Tower"), Resolved())
    assert "fact_player_maps fp" in c.sql and "agg_player_stats" not in c.sql
    assert "fp.role = %s" in c.sql and "fp.map_name = %s" in c.sql
    assert c.params == ["Lijiang Tower", "Tank", 1, 10]


def test_a_players_own_role_filtered_stat_also_reads_fact_player_maps():
    c = _sql(val("KSAA eliminations as tank"), R_PLAYER)
    assert "fact_player_maps fp" in c.sql and "fp.player_id = %s" in c.sql and "fp.role = %s" in c.sql
    assert c.params == ["p1", "Tank"]


def test_role_is_scoped_to_player_leaderboards_and_player_stats():
    # role is per player per map; a team-grain question has no clean meaning for it
    u = validate(parse("Twisted Minds record as tank"), INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_question" and "Tank" in u.reason


def test_role_requires_a_typed_stat_same_rule_as_map_and_mode():
    q = StructuredQuery(intent="leaderboard", entity="player", metric="K/D Ratio", filters=Filters(role="Tank"))
    u = validate(q, INFO)
    assert isinstance(u, Unanswerable) and u.code == "unsupported_metric" and "role" in u.reason


def test_every_param_is_bound_never_interpolated():
    for q, r in [("most eliminations on Lijiang Tower in 2024", Resolved()), ("KSAA damage dealt on Lijiang Tower", R_PLAYER),
                 ("Twisted Minds record on control", R_TEAM), ("Twisted Minds vs ENCE", R_H2H)]:
        c = _sql(val(q), r)
        assert "Lijiang" not in c.sql and "2024" not in c.sql and "t1" not in c.sql and "p1" not in c.sql


# ------------------------------------------------- a competition answers to its FACEIT name and its displayed name

def _competitions():
    info = SchemaInfo()
    rows = {  # id: (FACEIT's stored name, the displayed OWCS name, season, region)
        "s8na": ("S8 NA OWCS Central - Regular Season", "OWCS 2026 NA Stage 1 Regular Season", 2026, "na"),
        "s9na_rs": ("S9 NA OWCS Central - Regular Season", "OWCS 2026 NA Stage 2 Regular Season", 2026, "na"),
        "s9na_po": ("S9 NA OWCS Central - Playoffs", "OWCS 2026 NA Stage 2 Playoffs", 2026, "na"),
        "s9emea_po": ("S9 EMEA OWCS Central - Playoffs", "OWCS 2026 EMEA Stage 2 Playoffs", 2026, "emea"),
        "s5na_po": ("S5 NA OWCS Central - Playoffs", "OWCS 2025 NA Stage 2 Playoffs", 2025, "na"),
        "g24": ("OWCS 2024: NA Stage 1 - Group A", "OWCS 2024: NA Stage 1 - Group A", 2024, "na"),
    }
    for cid, (stored, shown, season, region) in rows.items():
        info.championships[cid], info.championship_display[cid] = stored, shown
        info.championship_season[cid], info.championship_region[cid] = season, region
    return info


def _ids(info, text, season=None, region=None):
    return [cid for cid, _ in info.match_championships(text, season, region)]


def test_the_displayed_owcs_name_is_searchable():
    info = _competitions()
    assert _ids(info, "stage 2 playoffs", 2026, "na") == ["s9na_po"]
    assert _ids(info, "stage 2 regular season", 2026, "na") == ["s9na_rs"]
    assert _ids(info, "stage 2", 2025, "na") == ["s5na_po"]


def test_the_stored_faceit_name_stays_searchable_too():
    info = _competitions()
    assert _ids(info, "central playoffs", 2026, "na") == ["s9na_po"]
    assert sorted(_ids(info, "OWCS Central", 2026, "na")) == ["s8na", "s9na_po", "s9na_rs"]


def test_a_stage_number_is_not_read_out_of_a_year():
    """'2' is in '2026': 'stage 2' must not match Stage 1 of 2026."""
    info = _competitions()
    assert "s8na" not in _ids(info, "stage 2", 2026, "na")
    assert _ids(info, "stage 1", 2026, "na") == ["s8na"]


def test_season_and_region_come_from_the_championship_not_its_name():
    """FACEIT League names carry no year; the 2026 filter must still find them."""
    info = _competitions()
    assert _ids(info, "playoffs", 2026, "na") == ["s9na_po"]
    assert _ids(info, "playoffs", 2026, "emea") == ["s9emea_po"]


def test_words_cannot_be_assembled_from_two_different_names():
    info = _competitions()
    # 'regular season' is in the stored name of s9na_rs and 'playoffs' in the stored name of s9na_po: no one name has both
    assert _ids(info, "regular season playoffs", 2026, "na") == []
