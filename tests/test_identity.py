"""Cross-source identity, offline: page-name parsing, the match-level evidence rule, and the decision file."""

from __future__ import annotations

from liquipedia_support import lp_row

from owcsmuse.liquipedia.identity import (REVIEW, STRONG, UNMATCHED, PlayerDecisions, Sighting, accept_strong,
                                          propose_players, render_report)
from owcsmuse.liquipedia.matches import parse_player, parse_row
from owcsmuse.liquipedia.teams import TeamMap


def test_a_page_style_name_yields_handle_and_real_name_both():
    p = parse_player("HYEON_(Kim_Seong-hyeon)", "HYEON", "South Korea")
    assert (p.page, p.handle, p.real_name, p.nationality) == ("HYEON_(Kim_Seong-hyeon)", "HYEON", "Kim Seong-hyeon", "South Korea")
    p = parse_player("Quartz", "Quartz", "Saudi Arabia")
    assert (p.handle, p.real_name) == ("Quartz", None)
    assert parse_player("Some_Player_(Jane_Doe)", None).handle == "Some Player"     # no display name: the page's base
    assert parse_player("", "x") is None


def test_parse_row_keeps_line_ups_and_team_templates():
    row = lp_row("Dallas Fuel", "Team Liquid", 3, 1, players1=[("Hydron_(Ethan_Rose)", "Hydron", "United States")],
                 players2=[("Zeruhh", "Zeruhh", "Canada")], templates=("dallas fuel 2026", "team liquid 2026"))
    m = parse_row(row, 1)
    assert [p.handle for p in m.players1] == ["Hydron"] and m.players1[0].real_name == "Ethan Rose"
    assert [p.page for p in m.players2] == ["Zeruhh"]
    assert (m.team1_template, m.team2_template, m.team1_page) == ("dallas fuel 2026", "team liquid 2026", "Dallas_Fuel")


def _s(page, handle, match, roster, real=None, team="t1"):
    return Sighting(page, handle, real, None, match, team, roster)


def test_same_handle_same_side_same_series_is_strong_and_one_to_one():
    roster = [("g1", "Hydron", "Hydron#1234"), ("g2", "Coluge", None)]
    ps = {p.page: p for p in propose_players([_s("Hydron_(Ethan_Rose)", "Hydron", "m1", roster, "Ethan Rose"),
                                               _s("Hydron_(Ethan_Rose)", "Hydron", "m2", roster, "Ethan Rose"),
                                               _s("Coluge", "Coluge", "m1", roster)])}
    assert ps["Hydron_(Ethan_Rose)"].strength == STRONG and ps["Hydron_(Ethan_Rose)"].guid == "g1"
    assert ps["Hydron_(Ethan_Rose)"].series == 2 and "2 linked series" in ps["Hydron_(Ethan_Rose)"].evidence[-1]
    assert ps["Coluge"].strength == STRONG and ps["Coluge"].guid == "g2"


def test_a_handle_that_matches_nothing_is_listed_with_what_faceit_named_not_guessed():
    roster = [("g1", "sug2rfree", "Sugarfree#1"), ("g2", "Coluge", None)]
    [p] = propose_players([_s("Sugarfree", "Sugarfree", "m1", roster)])
    assert p.strength == UNMATCHED and not p.candidates
    assert "sug2rfree" in p.evidence[0]            # a person can see it is the same player; the code does not say so


def test_many_to_one_in_either_direction_needs_a_person():
    roster = [("g1", "Smurf", None)]
    ps = {p.page: p for p in propose_players([_s("Smurf_(A)", "Smurf", "m1", roster), _s("Smurf_(B)", "Smurf", "m2", roster)])}
    assert ps["Smurf_(A)"].strength == REVIEW and ps["Smurf_(B)"].strength == REVIEW
    roster2 = [("g1", "Twin", None), ("g2", "Twin", "Twin#2")]
    [p] = propose_players([_s("Twin", "Twin", "m1", roster2)])
    assert p.strength == REVIEW and set(p.candidates) == {"g1", "g2"}


def test_roster_overlap_across_different_series_is_not_evidence():
    """The same handle on a DIFFERENT series' roster never pairs: only the same side of the same linked series does."""
    [p] = propose_players([_s("Hydron", "Hydron", "m1", [("g9", "Someone", None)])])
    assert p.strength == UNMATCHED


def test_decisions_rejections_and_bulk_accept(tmp_path):
    roster = [("g1", "Hydron", None)]
    proposals = propose_players([_s("Hydron", "Hydron", "m1", roster)])
    d = PlayerDecisions(tmp_path / "d.json")
    d.reject("Hydron", "g1", "different person with the same handle")
    d.apply(proposals)
    assert proposals[0].strength == REVIEW and not proposals[0].candidates        # a rejected pairing is never strong
    assert accept_strong(d, proposals) == 0

    proposals = propose_players([_s("Hydron", "Hydron", "m1", roster)])
    d2 = PlayerDecisions(tmp_path / "d2.json")
    assert accept_strong(d2, d2.apply(proposals)) == 1 and proposals[0].decided["entity_id"] == "g1"
    d2.set("HYEON_(Kim_Seong-hyeon)", None, "HYEON", real_name="Kim Seong-hyeon")                 # Liquipedia-born
    d2.save()
    again = PlayerDecisions(tmp_path / "d2.json")
    assert again.data["Hydron"]["entity_id"] == "g1" and again.data["HYEON_(Kim_Seong-hyeon)"]["entity_id"] is None
    text = render_report(again.apply(propose_players([_s("Hydron", "Hydron", "m1", roster)])), TeamMap(tmp_path / "none.json"))
    assert "Already decided (1)" in text and "Proposed - strong" in text
