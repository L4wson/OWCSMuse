"""The Phase 0 cell counter's condition semantics, on a hand-built warehouse. No database, no network.

Every expected set below is written by hand from the rows in `warehouse()`, never read back from the counter.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "grid"))

from cell_counter import distinct_solution, parse_condition  # noqa: E402
from conditions import (  # noqa: E402
    MinOrgs, Org, Per10, PlacedTop, Region, Role, Season, TopPer10, cell_answers, check_entity, stats_coverage,
)
from data import Appearance, Championship, MapRow, Placement, TeamSeries, Warehouse  # noqa: E402


def at(year: int) -> datetime:
    return datetime(year, 6, 1, tzinfo=timezone.utc)


def appearance(player: str, series: str, season: int, org: str, region: str = "na") -> Appearance:
    return Appearance(player, series, at(season), season, region, f"c{season}", org, "faceit")


def maps(player: str, season: int, org: str, role: str, n: int, *, elims: int = 10, seconds: float | None = 600.0,
         start: int = 0) -> list[MapRow]:
    return [MapRow(player, f"m-{player}-{season}-{role}", start + i, at(season), season, "na", f"c{season}", org, role,
                   elims, 5, 1000.0, 0.0, 0.0, seconds) for i in range(n)]


def warehouse() -> Warehouse:
    appearances = [
        # p1: Alpha in 2024, Beta in 2025. p2: Alpha in both seasons. p3: Beta in 2024 only.
        appearance("p1", "s1", 2024, "alpha"), appearance("p1", "s2", 2025, "beta"),
        appearance("p2", "s1", 2024, "alpha"), appearance("p2", "s3", 2025, "alpha"),
        appearance("p3", "s4", 2024, "beta"),
        # one FACEIT team id recycled: its 2024 series key as org "old", its 2025 series as org "new"
        appearance("p4", "s5", 2024, "old"), appearance("p5", "s6", 2025, "new"),
    ]
    map_rows = (
        maps("p1", 2024, "alpha", "Tank", 5)                              # a Tank in 2024 ...
        + maps("p1", 2025, "beta", "Support", 12, elims=6)                # ... and a Support in 2025
        + maps("p2", 2024, "alpha", "Tank", 3)                            # under a floor of 4
        + maps("p2", 2025, "alpha", "Tank", 12, elims=20)
        + maps("p3", 2024, "beta", "Damage", 6, seconds=None)             # 2024: no Time Played
        + maps("p5", 2025, "new", "Tank", 12, elims=10)
    )
    team_series = [
        TeamSeries("alpha", "beta", "s1", at(2024), 2024, "na", "c2024", True),
        TeamSeries("beta", "alpha", "s1", at(2024), 2024, "na", "c2024", False),
        TeamSeries("alpha", "gamma", "s7", at(2025), 2025, "international", "cintl", False),
        TeamSeries("gamma", "alpha", "s7", at(2025), 2025, "international", "cintl", True),
    ]
    placements = [Placement("gamma", "cintl", 2025, 1, 1), Placement("alpha", "cintl", 2025, 3, 4)]
    championships = {
        "c2024": Championship("c2024", "Stage 2024", 2024, "na", "main", True),
        "c2024b": Championship("c2024b", "Stage 2024 LAN", 2024, "na", "main", False),
        "c2025": Championship("c2025", "Stage 2025", 2025, "na", "main", True),
        "cintl": Championship("cintl", "World Finals 2025", 2025, "international", "main", False),
    }
    names = {p: p.upper() for p in ("p1", "p2", "p3", "p4", "p5")}
    orgs = {k: k.title() for k in ("alpha", "beta", "gamma", "old", "new")}
    return Warehouse(appearances, map_rows, team_series, placements, championships, names, orgs)


def ids(wh, entity, row, col, min_maps=4):
    return set(cell_answers(wh, entity, row, col, min_maps, 1).ids)


def test_role_and_season_must_hold_on_the_same_maps():
    wh = warehouse()
    # p1 was a Tank in 2024 and competed in 2025, but as a Support: not a 2025 Tank
    assert ids(wh, "player", Role("Tank"), Season(2025)) == {"p2", "p5"}
    assert ids(wh, "player", Role("Tank"), Season(2024)) == {"p1"}
    assert cell_answers(wh, "player", Role("Tank"), Season(2024), 4, 1).correlated


def test_min_maps_floor_applies_to_a_role_cell():
    wh = warehouse()
    assert ids(wh, "player", Role("Tank"), Season(2024), min_maps=3) == {"p1", "p2"}   # p2 has exactly 3
    assert ids(wh, "player", Role("Tank"), Season(2024), min_maps=6) == set()


def test_org_and_season_use_the_team_at_the_time():
    wh = warehouse()
    # p1 played for Alpha and competed in 2025, but was on Beta by then
    assert ids(wh, "player", Org("alpha", "Alpha"), Season(2025)) == {"p2"}
    assert ids(wh, "player", Org("alpha", "Alpha"), Season(2024)) == {"p1", "p2"}


def test_played_for_both_is_each_org_on_its_own_series():
    wh = warehouse()
    cell = cell_answers(wh, "player", Org("alpha", "Alpha"), Org("beta", "Beta"), 4, 1)
    assert set(cell.ids) == {"p1"}
    assert not cell.correlated


def test_a_recycled_team_id_is_two_identities():
    wh = warehouse()
    assert ids(wh, "player", Org("old", "Old"), Season(2024)) == {"p4"}
    assert ids(wh, "player", Org("old", "Old"), Org("new", "New")) == set()
    assert ids(wh, "player", Org("new", "New"), Season(2025)) == {"p5"}


def test_per_10_is_recomputed_from_components_and_takes_the_floor():
    wh = warehouse()
    # 2025 Tanks: p2 240 eliminations in 7200 s = 20.0 per 10; p5 120 in 7200 s = 10.0 per 10
    assert Per10("eliminations", ">=", 15.0, 2025, "Tank").answers(wh, 10, 1) == {"p2"}
    assert Per10("eliminations", "<=", 15.0, 2025, "Tank").answers(wh, 10, 1) == {"p5"}
    assert TopPer10("eliminations", 1, 2025, "Tank").answers(wh, 10, 1) == {"p2"}
    assert TopPer10("eliminations", 1, 2025, "Tank").answers(wh, 13, 1) == set()       # nobody has 13 maps


def test_per_10_refuses_a_season_with_no_time_played():
    with pytest.raises(ValueError, match="2024 has no maps"):
        Per10("eliminations", ">=", 1.0, 2024, "Damage").answers(warehouse(), 1, 1)


def test_coverage_names_the_competitions_without_player_stats():
    wh = warehouse()
    line = stats_coverage(wh, Role("Tank"), Season(2024))
    assert line.startswith("player stats in 1 of 2 competitions") and "Stage 2024 LAN" in line
    assert stats_coverage(wh, Org("alpha", "Alpha"), Season(2024)) is None             # not a map-grain cell


def test_team_answers_region_season_and_placement():
    wh = warehouse()
    assert ids(wh, "team", Region("international"), Season(2025)) == {"alpha", "gamma"}
    assert ids(wh, "team", Region("international"), Season(2024)) == set()
    assert ids(wh, "team", Region("na"), PlacedTop(1)) == set()                         # gamma won, never played in NA
    assert ids(wh, "team", Region("na"), PlacedTop(4)) == {"alpha"}                     # "3-4" is top 4
    assert PlacedTop(3).answers(wh, 4, 1) == {"gamma"}                                  # ... and not top 3


def test_a_condition_for_the_wrong_entity_is_refused():
    with pytest.raises(ValueError):
        check_entity("team", Role("Tank"))
    with pytest.raises(ValueError):
        check_entity("player", PlacedTop(4))


def test_an_org_is_named_by_key_never_by_display_name():
    wh = warehouse()
    assert parse_condition(wh, "org:alpha") == Org("alpha", "Alpha")
    with pytest.raises(ValueError, match="never a name"):
        parse_condition(wh, "org:Alpha")
    assert parse_condition(wh, "min_orgs:2") == MinOrgs(2)
    assert MinOrgs(2).answers(wh, 4, 1) == {"p1"}


def test_distinct_solution_counts_cells_fillable_without_reuse():
    assert distinct_solution([frozenset({"a"}), frozenset({"a"})]) == 1
    assert distinct_solution([frozenset({"a", "b"}), frozenset({"a"})]) == 2
    assert distinct_solution([frozenset(), frozenset({"a"})]) == 1
