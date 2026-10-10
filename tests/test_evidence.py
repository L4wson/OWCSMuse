"""Evidence SQL: what it selects, what it filters, how it pages. No database."""

import pytest

from owcsmuse.nlq.compile import Resolved
from owcsmuse.nlq.evidence import (DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, clamp_page, compile_evidence,
                                   compile_missing_series, expansion_target)
from owcsmuse.nlq.schema import Filters, StructuredQuery
from owcsmuse.nlq.validate import Validated


def _v(intent, entity="player", metric=None, **filters):
    q = StructuredQuery(intent=intent, entity=entity, metric=metric, filters=Filters(**filters))
    return Validated(query=q, championship_ids=[], map_name=filters.get("map"), mode_name=filters.get("mode"))


def _check(compiled):
    """Whatever the shape, placeholders and parameters must agree."""
    assert compiled is not None
    assert compiled.sql.count("%s") == len(compiled.params), (compiled.sql, compiled.params)
    assert " LIMIT %s OFFSET %s" in compiled.sql
    assert "ORDER BY played_at DESC" in compiled.sql
    return compiled


def test_player_versus_player_reads_the_subjects_own_maps():
    r = Resolved(player_id="p1", opponent_id="p2", subject_type="player", opponent_type="player")
    c = _check(compile_evidence(_v("versus"), r))
    assert "fact_player_maps s" in c.sql
    assert "o.player_id = %s" in c.sql and "o.team_id IS DISTINCT FROM s.team_id" in c.sql
    assert c.params[:2] == ["p1", "p2"]
    assert c.grain == "map"


def test_player_versus_org_filters_on_the_opponent_org_key():
    r = Resolved(player_id="p1", opponent_id="twisted-minds", subject_type="player", opponent_type="org")
    c = _check(compile_evidence(_v("versus"), r))
    assert "s.opponent_org_key = %s" in c.sql
    assert c.params[:2] == ["p1", "twisted-minds"]


def test_org_versus_org_uses_the_team_map_fact_and_org_keys():
    r = Resolved(team_id="t1", opponent_id="ence", subject_type="team", opponent_type="org")
    c = _check(compile_evidence(_v("versus", entity="team"), r))
    assert "fact_team_maps s" in c.sql
    assert c.params[:2] == ["team:t1", "ence"]     # an unmapped team id keys as itself


def test_a_team_record_is_series_grain_but_a_map_metric_is_map_grain():
    r = Resolved(team_id="t1", subject_type="org")
    series = _check(compile_evidence(_v("team_record", entity="team", metric="record"), r))
    assert series.grain == "series" and "fact_team_matches s" in series.sql
    assert "map_stats_recorded" in series.sql       # a result_only series is visible as such
    maps = _check(compile_evidence(_v("team_record", entity="team", metric="map_win_rate"), r))
    assert maps.grain == "map" and "fact_team_maps s" in maps.sql


def test_the_answers_filters_are_the_evidences_filters():
    r = Resolved(player_id="p1", subject_type="player")
    v = _v("entity_stat", metric="Eliminations", season=2026, map="Ilios", mode="Control", region="emea")
    v.championship_ids = ["c1", "c2"]
    c = _check(compile_evidence(v, r, stat_key="Eliminations"))
    for clause in ("s.season = %s", "s.championship_id = ANY(%s)", "s.map_name = %s",
                   "s.game_mode = %s", "s.region = %s"):
        assert clause in c.sql, clause
    assert ["Eliminations", "Eliminations", "p1", 2026, ["c1", "c2"], "Ilios", "Control", "emea"] == c.params[:8]


def test_a_stat_answer_carries_that_stats_value_per_row():
    r = Resolved(player_id="p1", subject_type="player")
    c = _check(compile_evidence(_v("entity_stat", metric="Final Blows"), r, stat_key="Final Blows"))
    assert "stat_num(s.stats ->> %s) AS stat_value" in c.sql
    assert c.params[0] == "Final Blows"


def test_paging_is_limit_offset_and_the_page_size_is_capped():
    r = Resolved(player_id="p1", subject_type="player")
    c = compile_evidence(_v("entity_stat", metric="Eliminations"), r, page=3, page_size=10)
    assert c.params[-2:] == [10, 20]
    assert clamp_page(0, 1) == (1, 1)                      # page 0 does not exist
    assert clamp_page(0, 0) == (1, DEFAULT_PAGE_SIZE)      # an unset size is the default, not zero rows
    assert clamp_page(None, None) == (1, DEFAULT_PAGE_SIZE)
    assert clamp_page(2, 10_000) == (2, MAX_PAGE_SIZE)


def test_every_row_carries_a_link_to_its_source_match():
    r = Resolved(player_id="p1", subject_type="player")
    c = _check(compile_evidence(_v("entity_stat", metric="Eliminations"), r))
    assert "faceit.com/en/ow2/room/" in c.sql and "AS match_url" in c.sql
    assert "count(*) OVER () AS total_rows" in c.sql       # the page and the whole size, in one query


def test_the_competition_column_reads_a_display_name_not_the_stored_one():
    """championships.name stays FACEIT's own text; only what a reader sees is remapped."""
    r = Resolved(player_id="p1", subject_type="player")
    c = _check(compile_evidence(_v("entity_stat", metric="Eliminations"), r))
    assert "championship_display_name(c.name) AS competition" in c.sql


def test_a_breakdown_with_no_subject_gets_one_row_per_map_not_one_per_side():
    c = _check(compile_evidence(_v("map_stats", entity="map"), Resolved(),
                                expand={"id": "Ilios", "type": "map", "column": "map_name"}))
    assert "DISTINCT ON (s.match_id, s.round_number)" in c.sql
    assert "s.map_name = %s" in c.sql and "Ilios" in c.params
    assert "AS winner" in c.sql                            # no single side owns the row


def test_stat_availability_has_no_rows_behind_it():
    assert compile_evidence(_v("stat_availability"), Resolved()) is None


def test_an_answer_with_nothing_resolved_has_no_evidence():
    assert compile_evidence(_v("entity_stat", metric="Eliminations"), Resolved()) is None
    assert compile_evidence(_v("versus"), Resolved(player_id="p1", subject_type="player")) is None


def test_the_expansion_target_is_the_top_row_unless_one_is_named():
    rows = [{"player_id": "a", "nickname": "A"}, {"player_id": "b", "nickname": "B"}]
    assert expansion_target(rows, None)["id"] == "a"
    assert expansion_target(rows, "b") == {"id": "b", "type": "player", "name": "B", "column": "player_id"}
    org_rows = [{"org_key": "team:1", "team": "Team One"}]
    assert expansion_target(org_rows, None)["type"] == "org"
    map_rows = [{"map_name": "Ilios", "maps": 10}]
    assert expansion_target(map_rows, None) == {"id": "Ilios", "type": "map", "name": "Ilios", "column": "map_name"}
    assert expansion_target([], None) is None


def test_an_id_that_is_not_on_this_page_can_still_be_expanded():
    """A UI may hold a row from page 2 of a ranking it no longer has."""
    target = expansion_target([{"player_id": "a", "nickname": "A"}], "9c9a8bc0-0000-0000-0000-000000000000")
    assert target["id"] == "9c9a8bc0-0000-0000-0000-000000000000" and target["type"] == "player"


def test_missing_series_evidence_is_the_result_only_series_between_two_sides():
    r = Resolved(player_id="p1", opponent_id="ence", subject_type="player", opponent_type="org")
    c = _check(compile_missing_series(_v("versus"), r, 1, DEFAULT_PAGE_SIZE))
    assert "s.ingest_state = 'result_only'" in c.sql
    assert "series_lineups l" in c.sql and "s.opponent_org_key = %s" in c.sql      # a player's side: his line-up (042)
    assert c.grain == "series"
    assert compile_missing_series(_v("versus"), Resolved(), 1, 10) is None


@pytest.mark.parametrize("intent,entity,metric", [
    ("versus", "player", "map_win_rate"),
    ("head_to_head", "team", "record"),
    ("season_compare", "team", "map_win_rate"),
    ("team_record", "team", "record"),
    ("entity_stat", "player", "Eliminations"),
    ("leaderboard", "player", "Eliminations"),
    ("map_stats", "map", "map_win_rate"),
])
def test_every_row_bearing_intent_compiles_to_balanced_sql(intent, entity, metric):
    r = Resolved(player_id="p1", team_id="t1", opponent_id="o1", subject_type="player", opponent_type="org")
    v = _v(intent, entity=entity, metric=metric)
    if intent == "season_compare":
        v.query.filters.subject_season, v.query.filters.opponent_season = 2024, 2026
    _check(compile_evidence(v, r, stat_key=metric if metric[0].isupper() else None))
