"""Mixed-clue Grid: each clue type, each generator rule, and both puzzle formats through the routes. No database.

Clue tests build a few fact rows by hand and state the expected sets from those rows. Rule tests use fixed answer
sets, one failing grid per rule, so a rule is tested by itself and not by whatever data happens to trip it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "grid"))

import build_facts  # noqa: E402
import clues as C  # noqa: E402
import generate_puzzles as gen  # noqa: E402
import mixed as M  # noqa: E402
from data import Appearance, Championship, MapRow, Warehouse  # noqa: E402

from owcsmuse.grid.store import GridStore, muse_link  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

CHAMPS = {
    "na24": Championship("na24", "OWCS 2024 NA Stage 1 Group A", 2024, "na", "main", True),
    "na24late": Championship("na24late", "OWCS 2024 NA Stage 4 Main Event", 2024, "na", "main", False),
    "na25": Championship("na25", "OWCS 2025 NA Stage 1 Regular Season", 2025, "na", "main", True),
    "na25po": Championship("na25po", "OWCS 2025 NA Stage 1 Playoffs", 2025, "na", "main", True),
    "emea25": Championship("emea25", "OWCS 2025 EMEA Stage 1 Regular Season", 2025, "emea", "main", True),
    "na26": Championship("na26", "OWCS 2026 NA Stage 1 Regular Season", 2026, "na", "main", True),
    "worlds": Championship("worlds", "OWCS 2025 World Finals", 2025, "international", "main", False),
    "dallas": Championship("dallas", C.DALLAS, 2024, "international", "main", False),
    "releg": Championship("releg", "OWCS 2026 NA Stage 2 Relegation", 2026, "na", "relegation", True),
}


def when(champ: str) -> datetime:
    return datetime(CHAMPS[champ].season, 6, 1, tzinfo=timezone.utc)


def lineup(player: str, series: str, champ: str, org: str) -> Appearance:
    c = CHAMPS[champ]
    return Appearance(player, f"faceit:{series}", when(champ), c.season, c.region, champ, org, "faceit")


def played(player: str, series: str, champ: str, org: str, n: int = 3, role: str = "Damage", elims: int = 10,
           seconds: float = 600.0, first: int = 1) -> list[MapRow]:
    """`n` maps of one series, numbered from `first`. Two players share a map when series, number and org match."""
    c = CHAMPS[champ]
    return [MapRow(player, series, first + i, when(champ), c.season, c.region, champ, org, role, elims, 5, 1000.0, 0.0,
                   0.0, seconds) for i in range(n)]


def facts(maps: list[MapRow], lineups: list[Appearance] = (), stages=(), awards=(), orgs=None) -> C.Facts:
    """Every map also puts its player in that series' line-up, as FACEIT's line-ups do."""
    rows = list(lineups) + [lineup(p, s, ch, org) for p, s, ch, org in {(m.player_id, m.match_id, m.championship_id, m.org_key) for m in maps}]
    players = {a.player_id for a in rows}
    names = {p: p.upper() for p in players}
    org_names = {a.org_key: a.org_key.replace("team:", "").title() for a in rows} | (orgs or {})
    return C.Facts(Warehouse(rows, list(maps), [], [], dict(CHAMPS), names, org_names), list(stages), list(awards))


# ---- teammate ---------------------------------------------------------------------------------------------------

def roster_change() -> C.Facts:
    """Alpha, 2025 NA Stage 1: ace plays every map. cat plays series s1 and leaves; dan replaces her in s2.
    eve is in Alpha's line-up for s3, a series with no map stats, beside ace."""
    maps = (played("ace", "s1", "na25", "alpha") + played("bob", "s1", "na25", "alpha") + played("cat", "s1", "na25", "alpha")
            + played("ace", "s2", "na25", "alpha") + played("bob", "s2", "na25", "alpha") + played("dan", "s2", "na25", "alpha")
            + played("zed", "s1", "na25", "omega"))        # the opponent in s1: same maps, the other team
    return facts(maps, [lineup("ace", "s3", "na25", "alpha"), lineup("eve", "s3", "na25", "alpha")])


def teammates(f: C.Facts, player: str) -> set[str]:
    return set(C.TeammateClue(player, player).outcome(f).answers)


def test_teammates_are_those_who_shared_a_map_on_the_same_team_never_the_anchor():
    f = roster_change()
    assert teammates(f, "ace") == {"bob", "cat", "dan"}
    assert "ace" not in teammates(f, "ace")
    assert "zed" not in teammates(f, "ace")            # an opponent played the same maps for the other side
    out = C.TeammateClue("ace", "Ace").outcome(f)
    assert out.answers["bob"] == "6 maps together on Alpha, 2025 NA Stage 1"
    assert out.answers["cat"] == "3 maps together on Alpha, 2025 NA Stage 1"


def test_teammate_is_symmetric():
    f = roster_change()
    everyone = {m.player_id for m in f.maps}
    for a in everyone:
        for b in everyone:
            assert (b in teammates(f, a)) == (a in teammates(f, b)), (a, b)


def test_a_mid_stage_roster_change_does_not_make_the_two_players_teammates():
    f = roster_change()
    assert "dan" not in teammates(f, "cat") and "cat" not in teammates(f, "dan")     # same team, same stage, never together
    assert teammates(f, "cat") == {"ace", "bob"} and teammates(f, "dan") == {"ace", "bob"}


def test_rostered_together_only_where_there_are_no_map_stats_is_unverifiable():
    out = C.TeammateClue("ace", "Ace").outcome(roster_change())
    assert out.unverifiable == {"eve"}                 # beside ace in s3's line-up; no map on record for either there
    assert "ace" not in out.unverifiable


# ---- orgs -------------------------------------------------------------------------------------------------------

def test_played_for_an_org_is_by_the_org_at_the_time_so_a_reused_team_id_never_links_two():
    # one FACEIT team id, reused: its 2024 maps key as org "old", its 2025 maps as org "new" (team_identity_at)
    f = facts(played("o1", "a", "na24", "old") + played("o2", "a", "na24", "old")
              + played("n1", "b", "na25", "new") + played("n2", "b", "na25", "new"))
    assert set(C.OrgClue("old", "Old").outcome(f).answers) == {"o1", "o2"}
    assert set(C.OrgClue("new", "New").outcome(f).answers) == {"n1", "n2"}
    assert teammates(f, "o1") == {"o2"} and teammates(f, "n1") == {"n2"}
    assert C.OrgClue("old", "Old").outcome(f).answers["o1"] == "3 maps for Old, 2024"


def test_an_unmapped_team_cannot_be_a_played_for_clue():
    with pytest.raises(ValueError, match="no org decision covers"):
        C.OrgClue("team:2b9f2e7a", "Twisted Minds")


def test_rostered_for_an_org_without_map_data_is_unverifiable_not_an_answer():
    f = facts(played("a", "s", "na25", "alpha"), [lineup("b", "t", "na24late", "alpha")])
    out = C.OrgClue("alpha", "Alpha").outcome(f)
    assert set(out.answers) == {"a"} and out.unverifiable == {"b"}


def test_three_orgs_counts_mapped_orgs_and_an_unmapped_stint_is_unverifiable():
    f = facts(
        played("vic", "a", "na24", "alpha") + played("vic", "b", "na25", "beta") + played("vic", "c", "na26", "gamma")
        + played("uma", "a", "na24", "alpha") + played("uma", "b", "na25", "beta") + played("uma", "d", "na26", "team:x")
        + played("two", "a", "na24", "alpha") + played("two", "b", "na25", "beta")
        + played("big", "a", "na24", "alpha") + played("big", "b", "na25", "beta") + played("big", "c", "na26", "gamma")
        + played("big", "e", "emea25", "team:y"))
    out = C.OrgCountClue(3).outcome(f)
    assert set(out.answers) == {"vic", "big"}          # three mapped orgs each; big's unmapped stint changes nothing
    assert out.answers["vic"] == "3 orgs: Alpha, Beta, Gamma"
    assert out.unverifiable == {"uma"}                 # two mapped orgs and a team nobody has mapped: could be a third
    assert "two" not in out.answers and "two" not in out.unverifiable      # two mapped orgs, nothing unknown: wrong


# ---- stages -----------------------------------------------------------------------------------------------------

STAGE = C.Stage("2025-na-1", "OWCS 2025 NA Stage 1", 2025, "na", frozenset({"na25po"}), "alpha", "beta", "https://example/stage")


def stage_facts() -> C.Facts:
    maps = (played("star", "final", "na25po", "alpha", 4) + played("sub", "final", "na25po", "alpha", 1, first=4)
            + played("reg", "week1", "na25", "alpha", 3)                  # Alpha in the regular season only
            + played("fay", "final", "na25po", "beta", 4)                 # the losing finalist
            + played("out", "semi", "na25po", "gamma", 3))                # another playoff team
    return facts(maps, [lineup("ben", "final", "na25po", "alpha")], stages=[STAGE])       # benched: line-up only


def test_a_substitute_with_one_playoff_map_won_the_stage_and_a_benched_player_did_not():
    out = C.StageWinClue().outcome(stage_facts())
    assert set(out.answers) == {"star", "sub"}
    assert out.answers["sub"] == "Won 2025 NA Stage 1 with Alpha (1 playoff maps)"
    assert "ben" not in out.answers and out.unverifiable == {"ben"}      # on the roster, no map on record
    assert "reg" not in out.answers and "reg" not in out.unverifiable    # never in the playoffs: plainly not
    assert "fay" not in out.answers


def test_stage_finalists_are_both_teams_of_the_final():
    out = C.StageFinalClue().outcome(stage_facts())
    assert set(out.answers) == {"star", "sub", "fay"}
    assert out.answers["fay"] == "Runner-up in 2025 NA Stage 1 with Beta (4 playoff maps)"
    assert "out" not in out.answers
    assert set(C.StageFinalClue("emea").outcome(stage_facts()).answers) == set()       # an NA stage is not an EMEA one
    assert set(C.StageWinClue("na").outcome(stage_facts()).answers) == {"star", "sub"}


def test_only_stages_whose_records_agree_are_loaded(tmp_path):
    entry = {"key": "k", "name": "OWCS 2025 NA Stage 1", "season": 2025, "region": "na", "playoff_championships": ["x"],
             "winner": {"org_key": "a"}, "runner_up": {"org_key": "b"}, "source": "https://example", "agree": True}
    path = tmp_path / "stages.json"
    path.write_text(json.dumps({"stages": [entry, {**entry, "key": "bad", "agree": False}]}), encoding="utf-8")
    assert [s.key for s in C.load_stages(path)] == ["k"]


# ---- awards -----------------------------------------------------------------------------------------------------

def test_unreviewed_and_unresolved_awards_are_left_out(tmp_path):
    def award(player_id, reviewed):
        return {"player_id": player_id, "award": "MVP", "event": "OWCS 2025 World Finals", "date": "2025-11-30",
                "source_url": "https://liquipedia.net/overwatch/x", "reviewed": reviewed}
    path = tmp_path / "awards.json"
    path.write_text(json.dumps({"awards": [award("yes", True), award("no", False), award(None, True)]}), encoding="utf-8")
    assert [a.player_id for a in C.load_awards(path)] == ["yes"]
    assert [a.player_id for a in C.load_awards(path, include_unreviewed=True)] == ["yes", "no"]     # never the unresolved one
    f = facts(played("yes", "s", "na25", "alpha"), awards=C.load_awards(path))
    assert C.AwardClue().outcome(f).answers == {"yes": "MVP, OWCS 2025 World Finals"}


def test_the_committed_awards_and_stages_are_sourced_and_only_reviewed_awards_are_usable():
    awards = json.loads((REPO / "scope" / "grid_awards.json").read_text(encoding="utf-8"))["awards"]
    assert awards and all(a["source_url"].startswith("https://liquipedia.net/overwatch/") for a in awards)
    # what the generator would use is exactly the reviewed, resolved entries: none until a person reviews one
    usable = {a["player_id"] for a in awards if a["reviewed"] and a["player_id"]}
    assert {a.player_id for a in C.load_awards(REPO / "scope" / "grid_awards.json")} == usable
    stages = json.loads((REPO / "scope" / "grid_stages.json").read_text(encoding="utf-8"))["stages"]
    assert len(stages) >= 20 and all(s["source"].startswith("https://liquipedia.net/") and s["agree"] for s in stages)


# ---- stats ------------------------------------------------------------------------------------------------------

def test_a_stat_rank_needs_twenty_maps_and_recomputes_the_rate_from_totals():
    # four Tanks with 20 maps in 2025, so the top 25% is one player.
    #   steady: 20 maps x 8 eliminations in 600 s            -> 160 in 12,000 s = 8.00 per 10
    #   spiky:  19 maps x 10 in 600 s, one 6,000 s map x 0   -> 190 in 17,400 s = 6.55 per 10
    #           (the mean of spiky's per-map rates is 9.5, which would wrongly put spiky first)
    #   two more at 5 per 10; and short: 19 maps x 30 in 600 s = 30 per 10, one map under the floor
    maps = (played("steady", "a", "na25", "alpha", 20, "Tank", 8)
            + played("spiky", "b", "na25", "alpha", 19, "Tank", 10) + played("spiky", "b2", "na25", "alpha", 1, "Tank", 0, 6000.0)
            + played("low1", "c", "na25", "alpha", 20, "Tank", 5) + played("low2", "d", "na25", "alpha", 20, "Tank", 5)
            + played("short", "e", "na25", "alpha", 19, "Tank", 30))
    clue = C.StatClue("eliminations", 2025)
    ranked = clue.ranked(facts(maps), "Tank")
    assert [p for p, _, _ in ranked] == ["steady", "spiky", "low1", "low2"]      # short is not ranked at all
    assert round(ranked[0][1], 2) == 8.00 and round(ranked[1][1], 2) == 6.55
    out = clue.outcome(facts(maps))
    assert out.answers == {"steady": "8.0 elims/10 as Tank in 2025, #1 of 4"}
    assert "short" not in out.answers and "short" not in out.unverifiable        # all his series are on record


def test_fewest_deaths_ranks_the_lowest_rate_first_and_states_its_scope():
    maps = (played("safe", "a", "na25", "alpha", 20, "Support") + played("x", "b", "na25", "alpha", 20, "Support")
            + played("y", "c", "na25", "alpha", 20, "Support") + played("z", "d", "na25", "alpha", 20, "Support"))
    maps = [m if m.player_id != "safe" else MapRow(*{**m.__dict__, "deaths": 1}.values()) for m in maps]
    clue = C.StatClue("deaths", 2025)
    assert set(clue.outcome(facts(maps)).answers) == {"safe"}
    assert "NA/EMEA" in clue.label and "2025" in clue.label
    with pytest.raises(ValueError):
        C.StatClue("vibes", 2025)
    with pytest.raises(ValueError, match="cannot be stated"):
        C.StatClue("deaths", 2024).outcome(facts(maps))               # no Time Played in 2024: refused, not empty


def test_too_few_maps_with_unrecorded_series_in_the_season_is_unverifiable():
    maps = [m for p in ("a", "b", "c", "d") for m in played(p, f"s{p}", "na25", "alpha", 20, "Tank")]
    maps += played("thin", "t", "na25", "alpha", 5, "Tank")
    out = C.StatClue("eliminations", 2025).outcome(facts(maps, [lineup("thin", "nostats", "na25", "alpha")]))
    assert "thin" in out.unverifiable


# ---- the rest ---------------------------------------------------------------------------------------------------

def test_experience_counts_recorded_maps_and_bounds_what_unrecorded_series_could_add():
    maps = played("vet", "a", "na25", "alpha", 50) + played("near", "b", "na25", "alpha", 45) + played("far", "c", "na25", "alpha", 10)
    f = facts(maps, [lineup("near", "u1", "na24late", "alpha"), lineup("far", "u2", "na24late", "alpha")])
    out = C.ExperienceClue(50).outcome(f)
    assert out.answers == {"vet": "50 OWCS maps"}
    assert out.unverifiable == {"near"}                # 45 + one unrecorded series of up to 7 maps could reach 50
    assert "far" not in out.unverifiable               # 10 + 7 cannot


def test_both_regions_needs_a_map_in_each():
    f = facts(played("both", "a", "na25", "alpha") + played("both", "b", "emea25", "beta") + played("one", "a", "na25", "alpha"),
              [lineup("maybe", "a2", "na24late", "alpha")] + [lineup(p, "b", "emea25", "beta") for p in ("maybe",)])
    out = C.BothRegionsClue().outcome(f)
    assert out.answers == {"both": "3 maps in NA, 3 in EMEA"}
    assert out.unverifiable == {"maybe"}               # in line-ups in both, with no map on record in either


def test_rostered_at_an_international_event_is_by_line_up_and_dallas_is_not_counted():
    f = facts(played("home", "a", "na25", "alpha"),
              [lineup("home", "w", "worlds", "alpha"), lineup("guest", "w", "worlds", "t1"), lineup("dal", "d", "dallas", "alpha")])
    out = C.LanClue("worlds", "2025 World Finals").outcome(f)
    assert out.answers == {"home": "On Alpha's roster at 2025 World Finals", "guest": "On T1's roster at 2025 World Finals"}
    anywhere = C.LanClue().outcome(f)
    assert set(anywhere.answers) == {"home", "guest"} and anywhere.unverifiable == {"dal"}
    assert C.LanClue("worlds", "2025 World Finals").label.startswith("Rostered at")
    with pytest.raises(ValueError):
        C.LanClue("dallas", "Dreamhack Dallas").outcome(f)


def test_relegation_and_international_maps_are_out_of_scope():
    f = facts(played("r", "a", "releg", "alpha", 20, "Tank") + played("ok", "b", "na26", "alpha", 20, "Tank"))
    assert set(C.RoleClue("Tank").outcome(f).answers) == {"ok"}
    assert set(C.SeasonClue(2026).outcome(f).answers) == {"ok"}


def test_a_role_beside_a_season_means_the_role_in_that_season():
    f = facts(played("p", "a", "na24", "alpha", 12, "Tank") + played("p", "b", "na25", "alpha", 12, "Support")
              + played("q", "c", "na25", "alpha", 12, "Tank"), [lineup("late", "x", "na24late", "alpha")])
    tank_2025 = C.cell(f, C.RoleClue("Tank"), C.SeasonClue(2025))
    assert tank_2025.answers == {"q": "12 Tank maps in 2025"}       # p was a Tank in 2024 and a Support in 2025
    tank_2024 = C.cell(f, C.SeasonClue(2024), C.RoleClue("Tank"))
    assert set(tank_2024.answers) == {"p"} and tank_2024.unverifiable == {"late": "col"}


def test_a_cell_is_both_clues_and_is_unverifiable_only_when_neither_rules_the_player_out():
    f = roster_change()
    out = C.cell(f, C.TeammateClue("ace", "Ace"), C.SeasonClue(2025))
    assert set(out.answers) == {"bob", "cat", "dan"}
    assert out.answers["dan"] == "3 maps together on Alpha, 2025 NA Stage 1. 3 maps in 2025"
    assert out.unverifiable == {"eve": "row"}          # the teammate clue cannot judge her; 2025 cannot either
    none = C.cell(f, C.TeammateClue("ace", "Ace"), C.SeasonClue(2024))
    assert none.answers == {} and none.unverifiable == {}             # nobody here played in 2024: that is checkable


def test_every_clue_round_trips_through_its_stored_params_and_has_a_label_and_definition():
    f = stage_facts()
    samples = [C.RoleClue("Tank"), C.SeasonClue(2025), C.AllSeasonsClue(), C.RegionClue("na"), C.BothRegionsClue(),
               C.TeammateClue("star", "STAR"), C.OrgClue("alpha", "Alpha"), C.OrgCountClue(3), C.StageWinClue("na"),
               C.StageFinalClue(), C.AwardClue(), C.LanClue("worlds", "2025 World Finals"), C.LanClue(),
               C.ExperienceClue(100), C.StatClue("damage_dealt", 2025)]
    assert len({c.key for c in samples}) == len(samples)
    for clue in samples:
        again = C.from_params(f, clue.params())
        assert again.key == clue.key and again.label == clue.label
        assert clue.label and len(clue.label) <= 40 and clue.definition.endswith(".") and clue.cannot_verify
        json.dumps(M.clue_entry(clue))


# ---- the generator's rules, one failing grid each ---------------------------------------------------------------

@dataclass(frozen=True)
class Fixed:
    """A clue with a given answer set: a rule is tested on exactly the sets written here."""
    key: str
    family: str
    players: frozenset
    anchor: str | None = None
    name: str = ""
    cannot_verify = "n/a"
    definition = "A fixed set."

    @property
    def label(self) -> str:
        return self.key

    def params(self) -> dict:
        return {"type": "fixed"}

    def outcome(self, f) -> C.Outcome:
        return C.Outcome({p: "why" for p in self.players})


def grid(cells: dict[tuple[int, int], set[str]], families=("a", "b", "c", "d", "e", "f"), extra_rows=(), extra_cols=()):
    """Six fixed clues whose pairwise intersections are exactly `cells`; `extra_*` pad a clue's own answers."""
    rows = [Fixed(f"R{r}", families[r], frozenset(set().union(*(cells[(r, c)] for c in range(3)))
                                                  | (extra_rows[r] if extra_rows else set()))) for r in range(3)]
    cols = [Fixed(f"C{c}", families[3 + c], frozenset(set().union(*(cells[(r, c)] for r in range(3)))
                                                      | (extra_cols[c] if extra_cols else set()))) for c in range(3)]
    return rows, cols


def good_cells(n: int = 6) -> dict[tuple[int, int], set[str]]:
    """Nine cells of `n` players each, nobody in two cells: passes every rule."""
    return {(r, c): {f"p{r}{c}{i}" for i in range(n)} for r in range(3) for c in range(3)}


def reasons(cells, **kw) -> list[str]:
    rows, cols = grid(cells, **kw)
    return M.Judge(facts([])).judge(rows, cols).reasons


def test_a_sound_grid_passes_every_rule():
    assert reasons(good_cells()) == []


def test_rule_an_empty_cell_and_same_family_clues_that_cannot_overlap():
    cells = good_cells()
    cells[(0, 0)] = set()
    assert any("R0 x C0 is empty" in r for r in reasons(cells))
    # the same grid with that row and column in one family, as Tank x Support or 2024-only x 2026-only would be
    same = reasons(cells, families=("role", "b", "c", "role", "e", "f"))
    assert "R0 x C0 is empty (same family: they cannot overlap)" in same


def test_rule_a_cell_under_three_answers():
    cells = good_cells()
    cells[(1, 2)] = {"x", "y"}
    assert "R1 x C2 has 2 answers (needs 3)" in reasons(cells)


def test_rule_more_than_two_thin_cells():
    cells = good_cells()
    for at in ((0, 0), (1, 1)):
        cells[at] = set(list(cells[at])[:4])
    assert reasons(cells) == []                                        # two cells of four: allowed
    cells[(2, 2)] = set(list(cells[(2, 2)])[:3])
    assert reasons(cells) == ["3 cells have only 3-4 answers (at most 2)"]


def test_rule_one_clue_implying_the_other():
    # row 0's own answers are 20 players; 18 of them (90%) sit in its first cell: "Won NA Stage 1" x "Played in NA"
    cells = good_cells()
    cells[(0, 0)] = {f"big{i}" for i in range(18)}
    cells[(0, 1)] = {"u", "v", "w"}
    cells[(0, 2)] = {"x", "y", "z"}                                     # 24 answers in the row, 18 in one cell = 75%
    assert not any("implies" in r for r in reasons(cells))
    cells[(0, 1)], cells[(0, 2)] = {"u"}, {"x"}                         # now 18 of 20 = 90%
    found = reasons(cells)
    assert "R0 x C0 holds 18 of the 20 'R0' answers: one clue all but implies the other" in found
    # padding the row's own answers (players who fit the row and none of these columns) brings it back under
    cells[(0, 1)], cells[(0, 2)] = {"u", "v", "w"}, {"x", "y", "z"}
    assert not any("implies" in r for r in reasons(cells, extra_rows=({"lonely"}, set(), set())))


def test_rule_one_player_fitting_more_than_five_cells():
    # a player who fits two rows and two columns fits their four cells; a third column makes it six
    cells = good_cells()
    for at in ((0, 0), (0, 1), (1, 0), (1, 1)):
        cells[at] = cells[at] | {"everywhere"}
    assert reasons(cells) == []
    for at in ((0, 2), (1, 2)):
        cells[at] = cells[at] | {"everywhere"}
    assert reasons(cells) == ["(no name) fits 6 cells (at most 5)"]


def test_rule_nine_different_players_must_be_able_to_fill_it():
    # every cell holds the same four players plus nobody else: 4 answers a cell, but 9 cells and 4 people.
    cells = {(r, c): {"a", "b", "c", "d", f"own{r}{c}"} for r in range(3) for c in range(3)}
    assert not any("can be filled" in r for r in reasons(cells))        # each cell has a player of its own
    cells = {(r, c): {"a", "b", "c", "d", "e", "f", "g", "h"} for r in range(3) for c in range(3)}
    assert "only 8 of 9 cells can be filled with different players" in reasons(cells)


def test_rule_at_least_four_families():
    assert reasons(good_cells(), families=("a", "a", "a", "b", "c", "d")) == []        # a role grid: four families
    assert reasons(good_cells(), families=("a", "a", "a", "b", "b", "c")) == [
        "only 3 clue families (a, b, c); needs 4"]


def test_rule_a_clue_used_in_the_last_seven_days_and_an_anchor_in_the_last_fourteen():
    day = date(2026, 12, 10)
    clue = Fixed("stage_win:any", "stage", frozenset())
    mate = Fixed("teammate:hawk", "teammate", frozenset(), anchor="hawk", name="Hawk")
    other = Fixed("teammate:other", "teammate", frozenset(), anchor="other", name="Other")

    def blocked(used_days_ago=None, anchor_days_ago=None, clues=(clue, mate)):
        used = {} if used_days_ago is None else {"stage_win:any": day - timedelta(days=used_days_ago)}
        anchors = {} if anchor_days_ago is None else {"hawk": day - timedelta(days=anchor_days_ago)}
        return M.recency_reasons(list(clues), [], day, used, anchors)

    assert blocked() == []
    assert blocked(used_days_ago=7) == ["'stage_win:any' was used on 2026-12-03, within 7 days"]
    assert blocked(used_days_ago=1) and blocked(used_days_ago=8) == []
    assert blocked(anchor_days_ago=14) == ["Hawk was an anchor on 2026-11-26, within 14 days"]
    assert blocked(anchor_days_ago=15) == [] and blocked(anchor_days_ago=14, clues=(clue, other)) == []


def test_difficulty_needs_the_smallest_cell_as_well_as_the_median():
    assert M.difficulty([5, 5, 9, 9, 9, 9, 9, 20, 30]) == "Easy"        # median 9, smallest 5
    assert M.difficulty([4, 5, 9, 9, 9, 9, 9, 20, 30]) == "Medium"      # the same grid with one cell of 4: not Easy
    assert M.difficulty([4, 4, 7, 7, 7, 8, 8, 8, 30]) == "Medium"       # median 7, smallest 4
    assert M.difficulty([3, 4, 7, 7, 7, 8, 8, 8, 30]) == "Hard"         # the same grid with one cell of 3: not Medium
    assert M.difficulty([3, 5, 9, 9, 9, 9, 9, 20, 30]) == "Hard"        # an easy median does not excuse a 3-answer cell
    assert M.difficulty([4, 4, 5, 6, 6, 6, 9, 9, 40]) == "Hard"         # median 6
    assert M.difficulty([3, 3, 3, 3, 3, 3, 3, 3, 3]) == "Hard"          # the floor every cell already has
    assert M.WEEKDAY_TARGET[0] == "Easy" and M.WEEKDAY_TARGET[5] == M.WEEKDAY_TARGET[6] == "Hard"


def test_a_grid_that_misses_its_day_is_relabelled_never_mislabelled():
    # the label stored with a puzzle is computed from its nine counts, whatever day it was wanted for
    f = mixed_facts()
    rows = [C.OrgClue("alpha", "Alpha"), C.OrgClue("beta", "Beta"), C.OrgClue("gamma", "Gamma")]
    cols = [C.RoleClue("Tank"), C.RoleClue("Damage"), C.TeammateClue("a0", "A0")]
    verdict = M.Judge(f).judge(rows, cols)
    monday = date(2026, 11, 23)                                         # a Monday wants Easy
    assert M.WEEKDAY_TARGET[monday.weekday()] == "Easy"
    entry = M.puzzle_entry(f, verdict, rows, cols, 1, monday, "x", "y", 1)
    assert entry["difficulty"] == M.difficulty(verdict.flat) != "Easy"   # cells of 2: it is what it is


def shape(rows_families, cols_families) -> list[str]:
    rows = [Fixed(f"R{i}", fam, frozenset()) for i, fam in enumerate(rows_families)]
    cols = [Fixed(f"C{i}", fam, frozenset()) for i, fam in enumerate(cols_families)]
    return M.shape_reasons(rows, cols)


def test_rule_at_most_one_n_plus_maps_clue():
    assert shape(("experience", "org", "stage"), ("lan", "teammate", "season")) == []
    assert shape(("experience", "org", "stage"), ("experience", "teammate", "season")) == ["2 'N+ maps' clues (at most 1)"]
    assert shape(("experience", "experience", "stage"), ("lan", "teammate", "season")) == ["2 'N+ maps' clues (at most 1)"]


def test_rule_at_most_two_teammate_clues():
    assert shape(("teammate", "org", "stage"), ("teammate", "lan", "season")) == []
    assert shape(("teammate", "teammate", "stage"), ("teammate", "lan", "season")) == ["3 'Teammate of' clues (at most 2)"]


def test_rule_at_most_one_stat_clue_on_an_axis():
    assert shape(("stats", "org", "stage"), ("stats", "lan", "season")) == []                 # one a side is allowed
    assert shape(("stats", "stats", "stage"), ("org", "lan", "season")) == ["2 stat clues among the rows (at most 1)"]
    assert shape(("org", "lan", "stage"), ("stats", "season", "stats")) == ["2 stat clues among the columns (at most 1)"]


def test_the_shape_rules_reject_an_otherwise_sound_grid():
    # the grid that passes every other rule, with two of its clues made 'N+ maps' clues
    found = reasons(good_cells(), families=("experience", "b", "c", "experience", "e", "f"))
    assert found == ["2 'N+ maps' clues (at most 1)"]


def test_rule_three_clues_shared_with_a_puzzle_of_the_last_21_days():
    day = date(2026, 12, 20)
    mine = [Fixed(k, "x", frozenset()) for k in ("a", "b", "c", "d", "e", "f")]
    rows, cols = mine[:3], mine[3:]

    def past(days_ago, keys):
        return [(day - timedelta(days=days_ago), frozenset(keys))]

    assert M.overlap_reasons(rows, cols, day, past(10, "abxyzw")) == []                 # two shared: allowed
    assert M.overlap_reasons(rows, cols, day, past(10, "abcxyz")) == [
        "shares 3 of its 6 clues with the puzzle of 2026-12-10, within 21 days (at most 2)"]
    assert M.overlap_reasons(rows, cols, day, past(21, "abcdef"))                       # the 21st day back still counts
    assert M.overlap_reasons(rows, cols, day, past(22, "abcdef")) == []                 # the 22nd does not
    # it is three clues of one earlier puzzle, not three clues seen across several
    spread = past(9, "axyzwv") + past(10, "bxyzwv") + past(11, "cxyzwv")
    assert M.overlap_reasons(rows, cols, day, spread) == []
    # and it reaches the generator's verdict through recency_reasons
    assert M.recency_reasons(rows, cols, day, {}, {}, past(10, "abcxyz"))
    assert M.recency_reasons(rows, cols, day, {}, {}) == []


def test_clue_sets_reads_both_formats_in_the_same_keys():
    old = {"date": "2026-11-18", "rows": [{"key": k} for k in ("tank", "dps", "support")],
           "cols": [{"key": k} for k in ("emea", "all3", "2026")]}
    new = {"format": 2, "date": "2026-11-19", "rows": [{"key": "role:tank"}, {"key": "org:x"}, {"key": "maps:100"}],
           "cols": [{"key": "season:2026"}, {"key": "lan:any"}, {"key": "stage_win:any"}]}
    (d1, k1), (d2, k2) = M.clue_sets([old, new])
    assert k1 == {"role:tank", "role:dps", "role:support", "region:emea", "season:all3", "season:2026"}
    assert len(k1 & k2) == 2 and (d1, d2) == (date(2026, 11, 18), date(2026, 11, 19))


# ---- anchors ----------------------------------------------------------------------------------------------------

def test_an_anchor_starts_approved_with_two_seasons_and_a_final_or_a_lan():
    assert build_facts.anchor_approved(seasons=2, finals=1, lans=0)
    assert build_facts.anchor_approved(seasons=3, finals=0, lans=2)
    assert not build_facts.anchor_approved(seasons=1, finals=3, lans=4)     # one season, however decorated
    assert not build_facts.anchor_approved(seasons=3, finals=0, lans=0)     # three seasons and nothing else


def test_anchor_candidates_are_ranked_with_a_reason_and_the_starting_approval():
    stage = C.Stage("2025-na-1", "OWCS 2025 NA Stage 1", 2025, "na", frozenset({"na25po"}), "alpha", "beta", "https://example")
    maps = (played("vet", "a", "na24", "alpha", 30) + played("vet", "final", "na25po", "alpha", 5)
            + played("vet", "c", "na26", "alpha", 30)
            + played("mate", "a", "na24", "alpha", 30)                       # one season, no final, no LAN
            + played("lan", "b", "na25", "beta", 20) + played("lan", "d", "na26", "beta", 20))
    f = facts(maps, [lineup("lan", "w", "worlds", "beta")], stages=[stage])
    by_id = {a["player_id"]: a for a in build_facts.anchor_candidates(f)}
    assert [a["player_id"] for a in build_facts.anchor_candidates(f)][0] == "vet"
    assert by_id["vet"]["reason"] == "3 seasons, 65 maps, 1 stage final (1 won)"
    assert by_id["vet"]["approved"] is True and by_id["vet"]["stage_finals"] == 1
    assert by_id["lan"]["reason"] == "2 seasons, 40 maps, 1 LAN incl. 2025 World Finals" and by_id["lan"]["approved"] is True
    assert by_id["mate"]["approved"] is False and by_id["mate"]["reason"] == "1 season, 30 maps"
    assert [a["rank"] for a in build_facts.anchor_candidates(f)] == [1, 2, 3]


def test_a_rebuild_keeps_the_owners_approvals(tmp_path):
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps({"anchors": [{"key": "p", "approved": False, "note": "not well known"}]}), encoding="utf-8")
    rebuilt = build_facts.keep_reviews([{"key": "p", "approved": True, "note": ""}, {"key": "new", "approved": True, "note": ""}],
                                       path, "anchors", flag="approved")
    assert rebuilt[0] == {"key": "p", "approved": False, "note": "not well known"}      # the owner said no: still no
    assert rebuilt[1]["approved"] is True                                                # new to the list: the rule's value


def test_the_pool_names_only_approved_anchors(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "TEAMMATE_MIN_ANSWERS", 3)                  # these fixture teams have six players each
    f = mixed_facts()
    everyone = {c.player_id for c in M.build_pool(f) if c.family == "teammate"}
    assert len(everyone) > 2                                           # with no list, the players with the most maps
    only = {c.player_id for c in M.build_pool(f, anchors=["a0", "b1"]) if c.family == "teammate"}
    assert only == {"a0", "b1"}
    assert {c.player_id for c in M.build_pool(f, anchors=[]) if c.family == "teammate"} == set()
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps({"anchors": [{"player_id": "a0", "approved": True}, {"player_id": "a1", "approved": False},
                                            {"player_id": "b1", "approved": True}]}), encoding="utf-8")
    assert gen.approved_anchors(path) == ["a0", "b1"]
    with pytest.raises(FileNotFoundError, match="build_facts"):
        gen.approved_anchors(tmp_path / "missing.json")


def test_the_committed_anchor_file_follows_the_rule_it_states():
    anchors = json.loads((REPO / "scope" / "grid_anchors.json").read_text(encoding="utf-8"))["anchors"]
    assert 50 <= len(anchors) <= 70 and [a["rank"] for a in anchors] == list(range(1, len(anchors) + 1))
    assert len({a["player_id"] for a in anchors}) == len(anchors)
    for a in anchors:
        assert a["reason"] and isinstance(a["approved"], bool)
        if not a["note"]:       # an entry the owner has not touched still carries the starting value
            assert a["approved"] == build_facts.anchor_approved(len(a["seasons"]), a["stage_finals"], len(a["lans"])), a["name"]


# ---- links to Muse ----------------------------------------------------------------------------------------------

def test_a_muse_link_is_a_prefilled_question_by_id_and_only_for_a_faceit_id():
    assert muse_link("58239fd5-cf2f-4894-a2ec-30fd026c262a") == "/?q=player%3A58239fd5-cf2f-4894-a2ec-30fd026c262a%20record"
    assert muse_link("lp:player:Shu") is None           # Muse's parser does not take a Liquipedia-born id in a question
    assert muse_link("t0") is None and muse_link("") is None
    # the question is one Muse's parser reads as a record for exactly that id
    from urllib.parse import unquote
    from owcsmuse.nlq.parser import is_entity_token, parse_question
    question = unquote(muse_link("58239fd5-cf2f-4894-a2ec-30fd026c262a").removeprefix("/?q="))
    parsed = parse_question(question).compact()
    assert parsed["intent"] == "team_record" and parsed["filters"]["subject"] == "player:58239fd5-cf2f-4894-a2ec-30fd026c262a"
    assert is_entity_token(parsed["filters"]["subject"]) and not is_entity_token("player:lp:player:Shu")


def test_a_correct_guess_and_the_reveal_carry_the_link(tmp_path):
    guid, born = "58239fd5-cf2f-4894-a2ec-30fd026c262a", "lp:player:Shu"
    clue = {"key": "k", "family": "lan", "label": "L", "help": "h.", "cannot_verify": "c.", "params": {"type": "lan"}}
    cells = [{"row": i // 3, "col": i % 3, "count": 2, "unverifiable": {},
              "answers": {guid: {"name": "sugarfree", "why": "a reason"}, born: {"name": "Shu", "why": "another"}}} for i in range(9)]
    puzzle = {"format": 2, "number": 1, "date": "2026-11-17", "kind": "mixed", "difficulty": "Hard", "rows": [clue] * 3,
              "cols": [clue] * 3, "rules": {"min_answers": 3, "guesses": 9}, "cells": cells}
    (tmp_path / "p.json").write_text(json.dumps({"puzzles": [puzzle]}), encoding="utf-8")
    players = [{"id": guid, "name": "sugarfree", "names": [], "team": "T", "seasons": [2025]},
               {"id": born, "name": "Shu", "names": [], "team": "T", "seasons": [2025]}]
    (tmp_path / "pl.json").write_text(json.dumps({"players": players}), encoding="utf-8")
    store = GridStore(tmp_path / "p.json", tmp_path / "pl.json")
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    assert store.guess(1, 0, guid, now)["link"] == muse_link(guid)
    assert store.guess(1, 0, born, now)["link"] is None                # correct, with no link: never a dead one
    links = {e["name"]: e["link"] for e in store.reveal(1, now)["cells"][0]["examples"]}
    assert links == {"sugarfree": muse_link(guid), "Shu": None}


def test_history_reads_both_formats_and_knows_a_role_grid():
    old = {"number": 1, "date": "2026-11-18", "rows": [{"key": k} for k in ("tank", "dps", "support")],
           "cols": [{"key": k} for k in ("emea", "all3", "2026")]}
    new = {"format": 2, "number": 2, "date": "2026-11-19", "rows": [{"key": "teammate:hawk"}, {"key": "org:x"}, {"key": "maps:100"}],
           "cols": [{"key": "season:2025"}, {"key": "lan:any"}, {"key": "stage_win:any"}]}
    used, anchors, last_role = M.history([new, old])
    assert used["role:tank"] == used["season:all3"] == used["region:emea"] == date(2026, 11, 18)
    assert used["teammate:hawk"] == date(2026, 11, 19) and anchors == {"hawk": date(2026, 11, 19)}
    assert last_role == date(2026, 11, 18)


# ---- both formats through the routes ----------------------------------------------------------------------------

fastapi = pytest.importorskip("fastapi", reason="the api extra is not installed")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from owcsmuse.grid.router import build_router  # noqa: E402


def mixed_facts() -> C.Facts:
    """Three teams of six in 2025 NA, everyone with 12 maps in one role; two of each team also played in 2024."""
    maps, extra = [], []
    for team in ("alpha", "beta", "gamma"):
        for i in range(6):
            player = f"{team[0]}{i}"
            maps += played(player, f"s-{team}", "na25", team, 12, C.ROLES[i % 3])
            if i < 2:
                maps += played(player, f"old-{team}", "na24", team, 12, C.ROLES[i % 3])
        extra.append(lineup(f"{team[0]}x", f"nostats-{team}", "na24late", team))       # rostered, no map data
    return facts(maps, extra)


@pytest.fixture()
def served(tmp_path):
    """A beta puzzle (17 Nov) and a mixed one (18 Nov) in one file, as the generator leaves them."""
    import test_beta
    old = test_beta.build(test_beta.warehouse(), number=1, day=date(2026, 11, 17)).entry
    f = mixed_facts()
    rows = [C.OrgClue("alpha", "Alpha"), C.OrgClue("beta", "Beta"), C.OrgClue("gamma", "Gamma")]
    cols = [C.RoleClue("Tank"), C.RoleClue("Damage"), C.TeammateClue("a0", "A0")]
    verdict = M.Judge(f).judge(rows, cols)
    new = M.puzzle_entry(f, verdict, rows, cols, 2, date(2026, 11, 18), "2026-11-01T00:00:00Z", "test", 1)
    gen.write_json(tmp_path / "puzzles.json", {"version": 1, "puzzles": [old, new]})
    names = dict(test_beta.warehouse().player_names) | f.full.player_names
    players = [{"id": p, "name": n, "names": [], "team": "Team", "seasons": [2025]} for p, n in names.items()]
    gen.write_json(tmp_path / "players.json", {"players": players})
    app = FastAPI()
    clock = test_beta.Clock(datetime(2026, 11, 18, 12, tzinfo=timezone.utc))
    app.include_router(build_router(GridStore(tmp_path / "puzzles.json", tmp_path / "players.json"), clock=clock))
    with TestClient(app) as client:
        yield client, old, new


def test_an_old_beta_puzzle_still_loads_and_plays_beside_a_mixed_one(served):
    client, old, _ = served
    view = client.get("/api/grid/1").json()
    assert [r["label"] for r in view["rows"]] == ["Tank", "DPS", "Support"] and view["min_maps"] == 10
    assert view["difficulty"] is None and view["kind"] == "role"
    assert view["rows"][0]["help"].startswith("10+ maps in this role")
    right = client.post("/api/grid/1/guess", json={"cell": 1, "player_id": "t0"}).json()
    assert right["result"] == "correct" and right["explanation"] == "12 Tank maps in 2025 (FACEIT map stats)"
    assert client.post("/api/grid/1/guess", json={"cell": 0, "player_id": "late"}).json()["result"] == "cannot_verify"
    assert client.post("/api/grid/1/guess", json={"cell": 1, "player_id": "d0"}).json()["result"] == "wrong"
    reveal = client.get("/api/grid/1/reveal").json()
    assert reveal["cells"][1]["count"] == 7 and len(reveal["cells"][1]["examples"]) == 5
    assert "maps" in reveal["cells"][1]["examples"][0]


def test_a_mixed_puzzle_serves_its_clues_with_definitions_and_no_ids(served):
    client, _, new = served
    today = client.get("/api/grid/today")
    view = today.json()
    assert view["number"] == 2 and view["kind"] == "mixed" and view["difficulty"] in ("Easy", "Medium", "Hard")
    assert [c["label"] for c in view["cols"]] == ["Tank", "DPS", "Teammate of A0"]
    assert [c["key"] for c in view["cols"]] == ["col0", "col1", "col2"] and view["cols"][2]["family"] == "teammate"
    assert view["cols"][2]["help"].startswith("Played 1+ map on the same team as A0")
    assert "Tap a clue" in view["coverage"] and view["min_maps"] is None
    secret = {p for c in new["cells"] for p in list(c["answers"]) + list(c["unverifiable"])} | {"a0"}
    for path in ("/api/grid/today", "/api/grid/2", "/api/grid/archive"):
        text = client.get(path).text
        assert not any(f'"{p}"' in text or f":{p}" in text for p in secret), path     # nor the anchor's id in a key
        assert all(word not in text for word in ('"answers"', '"unverifiable"', '"params"', "cannot_verify", '"why"', '"count"'))
    listed = client.get("/api/grid/archive").json()["puzzles"]
    assert [(p["number"], p["kind"], p["difficulty"]) for p in listed] == [(2, "mixed", view["difficulty"]), (1, "role", None)]


def test_a_mixed_guess_takes_its_reason_and_its_cannot_verify_message_from_the_clue(served):
    client, _, _ = served

    def guess(cell_index, player):
        return client.post("/api/grid/2/guess", json={"cell": cell_index, "player_id": player}).json()

    right = guess(0, "a0")                              # Alpha x Tank: a0 is Alpha's first Tank
    assert right["result"] == "correct" and right["uses_guess"] is True
    assert right["explanation"] == "24 maps for Alpha, 2024-2025. 24 Tank maps"
    assert guess(0, "b0")["result"] == "wrong"         # a Tank, for Beta
    assert guess(1, "a0")["result"] == "wrong"         # Alpha, not a DPS: plainly wrong, however little else is known
    unknown = guess(0, "ax")                            # on Alpha's roster only in a stage with no map data
    assert unknown["result"] == "cannot_verify" and unknown["uses_guess"] is False
    assert unknown["explanation"] == ("They were rostered for Alpha only in series we have no map data for. "
                                      "It didn't use a guess.")
    assert unknown["clue"] == "Played for Alpha"
    assert guess(2, "a0")["result"] == "wrong"         # the anchor is never his own teammate
    mate = guess(2, "a1")
    assert mate["result"] == "correct"
    assert mate["explanation"] == "24 maps for Alpha, 2024-2025. 24 maps together, most on Alpha in 2025 NA Stage 1"


def test_a_mixed_reveal_gives_the_answer_count_and_at_most_five_examples(served):
    client, _, new = served
    reveal = client.get("/api/grid/2/reveal").json()
    assert [c["count"] for c in reveal["cells"]] == [c["count"] for c in new["cells"]]
    assert all(len(c["examples"]) <= 5 and len(c["examples"]) <= c["count"] for c in reveal["cells"])
    assert all("why" in e and "name" in e for c in reveal["cells"] for e in c["examples"])


# ---- the committed puzzles obey every rule ----------------------------------------------------------------------

def test_every_committed_mixed_puzzle_obeys_the_generator_rules():
    puzzles = json.loads((REPO / "scope" / "grid_puzzles.json").read_text(encoding="utf-8"))["puzzles"]
    mixed = [p for p in puzzles if p.get("format") == 2]
    if not mixed:
        pytest.skip("no mixed puzzles have been generated")
    assert [p["number"] for p in puzzles] == list(range(1, len(puzzles) + 1))
    assert [p["date"] for p in puzzles] == sorted({p["date"] for p in puzzles})
    used, anchors, _ = M.history([p for p in puzzles if p.get("format") != 2])
    sets = M.clue_sets(puzzles)
    approved = set(gen.approved_anchors(REPO / "scope" / "grid_anchors.json"))
    for p in sorted(mixed, key=lambda p: p["date"]):
        day, where = date.fromisoformat(p["date"]), f"puzzle {p['number']}"
        clues = p["rows"] + p["cols"]
        assert len({c["key"] for c in clues}) == 6 and len({c["family"] for c in clues}) >= M.MIN_FAMILIES, where
        assert all(c["label"] and c["help"] and c["cannot_verify"] and c["params"]["type"] for c in clues), where
        counts = [c["count"] for c in p["cells"]]
        assert all(c["count"] == len(c["answers"]) for c in p["cells"]), where
        assert min(counts) >= M.MIN_CELL and sum(1 for n in counts if n <= M.THIN_CELL) <= M.MAX_THIN_CELLS, where
        assert p["difficulty"] == M.difficulty(counts), where
        fits: dict[str, int] = {}
        for c in p["cells"]:
            assert not set(c["answers"]) & set(c["unverifiable"]), where
            assert set(c["unverifiable"].values()) <= {"row", "col"}, where
            for player in c["answers"]:
                fits[player] = fits.get(player, 0) + 1
        assert max(fits.values()) <= M.MAX_CELLS_ONE_PLAYER, where
        families = [c["family"] for c in clues]
        assert families.count("experience") <= M.MAX_EXPERIENCE_CLUES, where
        assert families.count("teammate") <= M.MAX_TEAMMATE_CLUES, where
        for axis in (p["rows"], p["cols"]):
            assert sum(1 for c in axis if c["family"] == "stats") <= M.MAX_STAT_CLUES_AN_AXIS, where
        mine = {c["key"] for c in clues}
        for when, keys in sets:
            if 0 < (day - when).days <= M.OVERLAP_DAYS:
                assert len(mine & keys) <= M.MAX_SHARED_CLUES, f"{where} shares {len(mine & keys)} clues with {when}"
        if "teammate" in families:
            assert {c["key"].split(":", 1)[1] for c in clues if c["family"] == "teammate"} <= approved, where
        assert gen.distinct_solution([frozenset(c["answers"]) for c in p["cells"]]) == 9, where
        for c in clues:
            last = used.get(c["key"])
            assert last is None or (day - last).days > M.CLUE_GAP_DAYS, f"{where}: {c['label']} repeats within 7 days"
            if c["key"].startswith("teammate:"):
                anchor = c["key"].split(":", 1)[1]
                assert anchor not in anchors or (day - anchors[anchor]).days > M.ANCHOR_GAP_DAYS, where
                assert all(anchor not in cell["answers"] for cell in p["cells"]
                           if c in (p["rows"][cell["row"]], p["cols"][cell["col"]])), where
        for c in clues:
            used[c["key"]] = day
            if c["key"].startswith("teammate:"):
                anchors[c["key"].split(":", 1)[1]] = day
