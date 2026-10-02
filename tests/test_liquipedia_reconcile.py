"""The matcher: tiers, the known traps, and the rule that an ambiguous match is never linked on its own. Offline.

Every case builds Liquipedia records and FACEIT series by hand (tests/liquipedia_support.py), so each expected tier is
true by construction and written down before the matcher is asked.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from liquipedia_support import DB_CHAMPIONSHIP, DB_FACEIT_ID, EMEA_PAGE, NA_PAGE, T0, fs, lp, lp_row, resolver, write_map_file

from owcsmuse.liquipedia.matches import dedupe, faceit_id_of, parse_row, parse_rows, region_of
from owcsmuse.liquipedia.model import orient
from owcsmuse.liquipedia.pipeline import run_reconciliation, store_run
from owcsmuse.liquipedia.reconcile import AMBIGUOUS, EXACT, STRONG, UNMATCHED, reconcile
from owcsmuse.liquipedia.teams import TeamMap, entity_of_org_key, make_resolver, propose

FID = "1-7553f194-b7d7-4bc9-bda4-3484592e014f"
FID2 = "1-76fe2bd0-4ddd-4c66-be08-0d495a2bb364"
NAMES = {"Spacestation Gaming": "spacestation-gaming", "Team Liquid": "team-liquid", "Dallas Fuel": "dallas-fuel"}
MAP = resolver(NAMES)


def link_of(result, lp_match):
    return next(lk for lk in result.links if lk.lp.objectname == lp_match.objectname)


# ------------------------------------------------------------------------- parsing

def test_the_faceit_id_is_found_in_links_wherever_it_sits():
    assert faceit_id_of({"faceit": f"https://www.faceit.com/en/ow2/room/{FID}"}) == FID
    assert faceit_id_of([{"name": "faceit", "url": f"https://x/{FID}"}]) == FID
    assert faceit_id_of([]) is None and faceit_id_of({"vod": "https://youtube.com/x"}) is None
    assert faceit_id_of(None) is None


def test_the_region_comes_from_the_page_and_time_from_the_epoch():
    assert region_of("Overwatch_Champions_Series/2026/EMEA/Stage_1/Regular_Season") == "emea"
    assert region_of("Overwatch_Champions_Series/2026/Asia/Stage_2/Korea/Regular_Season") == "korea"
    assert region_of("Overwatch_Champions_Series/2026/China/Stage_2") == "china"
    # 2024 pages spell the region out; read as 'other', every 2024 NA record was rejected as cross-region
    assert region_of("Overwatch_Champions_Series/2024/North_America/Stage_1") == "na"
    assert region_of("Overwatch Champions Series/2024/North America/Stage 1/Group Stage") == "na"
    assert region_of("Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage") == "emea"
    assert region_of("Overwatch_Champions_Series/2024/Major") == "other"
    row = lp_row("A", "B", 3, 0)
    row["date"] = "2000-01-01 00:00:00"                        # the epoch is authoritative; `date` is the fallback
    assert parse_row(row, 1).played_at == T0
    del row["extradata"]
    assert parse_row(row, 1).played_at.year == 2000


def test_a_map_slot_marked_not_played_is_not_a_game_but_a_draw_is():
    # ROC Esports 3-0 Sheer Cold (127212_5BUO2jH7Ds_0003): five slots, the last two not played
    played = [{"map": m, "mode": "Control", "winner": "1", "scores": [2, 0]} for m in ("A", "B", "C")]
    unplayed = [{"map": m, "mode": "Escort", "winner": "", "scores": [], "resulttype": "np", "status": "notplayed"}
                for m in ("D", "E")]
    m = parse_row(lp_row("ROC Esports", "Sheer Cold", 3, 0, games=played + unplayed), 1)
    assert m.n_games == 3 and [g.map for g in m.games] == ["A", "B", "C"]
    # Team Falcons 3-0 ENCE at Dallas: a 3-3 Numbani is a map played and drawn
    draw = {"map": "Numbani", "mode": "Hybrid", "winner": "0", "scores": [3, 3], "resulttype": "draw", "status": ""}
    m = parse_row(lp_row("Team Falcons", "ENCE", 3, 0, games=played + [draw]), 1)
    assert m.n_games == 4 and m.games[-1].winner == 0


def test_a_tbd_or_bye_opponent_makes_a_placeholder_not_a_match():
    assert lp("TBD", "Team Liquid", None, None).placeholder
    assert lp("Team Liquid", "BYE", 1, 0).placeholder
    assert not lp("Dallas Fuel", "Team Liquid", 3, 0).placeholder
    res = reconcile([lp("TBD", "Team Liquid", None, None)], [], MAP)
    assert res.links == [] and len(res.placeholders) == 1


def test_a_record_repeated_under_one_bracket_and_match_is_dropped_and_a_shared_faceit_id_is_flagged():
    a, b = lp("A", "B", 3, 0, idx=1), lp("A", "B", 3, 0, idx=1, raw_id=2)
    kept, dups = dedupe([a, b])
    assert len(kept) == 1 and len(dups.same_match) == 1
    x, y = lp("A", "B", 3, 0, idx=1, faceit_id=FID), lp("C", "D", 3, 0, idx=2, faceit_id=FID)
    kept, dups = dedupe([x, y])
    assert len(kept) == 2 and len(dups.same_faceit_id) == 1            # kept: a conflict for a person, not a repeat
    assert parse_rows([lp_row("A", "B", 3, 0), {"match2opponents": [{"name": "solo"}]}], 1)[0].team1 == "A"


# ------------------------------------------------------------------------- tier 1: exact

def test_a_record_with_the_faceit_id_links_exactly_even_when_no_team_is_mapped():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1, faceit_id=FID)
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 3, 1)
    res = reconcile([m], [f], resolver({}))
    lk = link_of(res, m)
    assert (lk.tier, lk.faceit_id, lk.disagreements, lk.provisional) == (EXACT, FID, [], False)
    assert res.faceit_unlinked == []


def test_a_faceit_id_we_do_not_hold_is_a_finding_and_never_a_licence_to_link_something_else():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1, faceit_id=FID)          # names a FACEIT match we never crawled
    lookalike = fs(FID2, "SpaceStation Gaming", "Team Liquid", 3, 1)            # same teams, time, score: a tempting fit
    res = reconcile([m], [lookalike], MAP)
    lk = link_of(res, m)
    assert lk.tier == UNMATCHED and lk.faceit_id is None
    assert lk.evidence["kind"] == "faceit_missing_from_warehouse" and lk.evidence["faceit_match_id"] == FID
    assert res.faceit_unlinked == [lookalike]


def test_two_records_claiming_one_faceit_id_are_both_ambiguous():
    a = lp("A", "B", 3, 0, idx=1, faceit_id=FID)
    b = lp("A", "B", 3, 0, idx=2, faceit_id=FID)
    res = reconcile([a, b], [fs(FID, "A", "B", 3, 0)], resolver({}))
    assert [lk.tier for lk in res.links] == [AMBIGUOUS, AMBIGUOUS] and all(lk.faceit_id is None for lk in res.links)


def test_an_exact_pair_that_disagrees_is_ambiguous_and_says_where_and_which_source_is_implausible():
    """Stage 3: the id says one thing and the records another. A wrong id looks exactly like this and a wrong link
    silently gives one team another team's result, so the pair is never linked on the id alone."""
    m = lp("Spacestation Gaming", "Team Liquid", 3, 0, faceit_id=FID)
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 4, 0, maps=4)            # a 4-0 in a best-of-5 cannot have happened
    res = reconcile([m], [f], MAP)
    lk = link_of(res, m)
    assert lk.tier == AMBIGUOUS and lk.faceit_id is None
    assert lk.candidates == [{"faceit_id": FID, "disagrees_on": ["score"]}] and lk.evidence["kind"] == "exact_id_disagrees"
    assert [d["field"] for d in lk.disagreements] == ["score"]
    note = lk.disagreements[0]["note"]
    assert "4-0 is more wins than a best-of-5 allows" in note and "FACEIT has stats for 4 maps" in note
    assert res.faceit_unlinked == [f]                                        # the FACEIT series stays a series of its own


def test_a_wrong_faceit_id_shows_up_as_a_team_disagreement_and_never_links():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1, faceit_id=FID)
    f = fs(FID, "Dallas Fuel", "Team Liquid", 3, 1)                            # the id points at a different pairing
    lk = link_of(reconcile([m], [f], MAP), m)
    assert lk.tier == AMBIGUOUS and lk.faceit_id is None and "teams" in lk.candidates[0]["disagrees_on"]


def test_a_decision_may_name_the_faceit_id_instead_of_the_objectname():
    """The report shows FACEIT ids, not objectnames; a decision keyed faceit:<id> settles the one record naming it."""
    m = lp("Spacestation Gaming", "Team Liquid", 3, 0, faceit_id=FID)
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 4, 0, maps=4)
    lk = link_of(reconcile([m], [f], MAP, decisions={f"faceit:{FID}": {"faceit_match_id": FID, "note": "a drawn map"}}), m)
    assert (lk.tier, lk.decision, lk.faceit_id) == (AMBIGUOUS, "confirmed", FID)


def test_a_person_can_confirm_or_reject_a_disagreeing_id():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 0, faceit_id=FID)
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 4, 0, maps=4)
    lk = link_of(reconcile([m], [f], MAP, decisions={m.objectname: {"faceit_match_id": FID}}), m)
    assert (lk.tier, lk.decision, lk.faceit_id) == (AMBIGUOUS, "confirmed", FID)
    lk = link_of(reconcile([m], [f], MAP, decisions={m.objectname: {"faceit_match_id": None}}), m)
    assert (lk.tier, lk.decision, lk.faceit_id) == (AMBIGUOUS, "rejected", None)


def test_a_result_only_series_with_no_start_time_is_flagged_when_its_time_is_days_off():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 0, faceit_id=FID)
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 3, 0, when=T0 + timedelta(days=4), state="result_only", reliable=False)
    lk = link_of(reconcile([m], [f], MAP), m)
    d = lk.disagreements
    assert [x["field"] for x in d] == ["date"] and "when the result was entered" in d[0]["note"]
    assert lk.tier == EXACT and lk.faceit_id == FID                           # a date gap alone never downgrades


def test_a_best_of_disagreement_is_reported_with_the_reason_when_the_score_settles_it():
    m = lp("Spacestation Gaming", "Team Liquid", 4, 1, faceit_id=FID, bo=7)
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 4, 1, bo=5)
    lk = link_of(reconcile([m], [f], MAP), m)
    d = lk.disagreements
    assert [x["field"] for x in d] == ["best_of"] and "best-of-7" in d[0]["note"]
    assert lk.tier == AMBIGUOUS                                               # and it is a person's call


# ------------------------------------------------------------------------- tier 2: strong

def test_no_id_but_teams_region_time_best_of_and_score_agree_is_a_strong_link():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1)
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", 3, 1)
    res = reconcile([m], [f], MAP)
    lk = link_of(res, m)
    assert (lk.tier, lk.faceit_id, lk.provisional, lk.disagreements) == (STRONG, "F1", False, [])
    assert res.faceit_unlinked == []


def test_the_link_is_oriented_by_the_orgs_not_by_the_order_the_pages_list_them():
    m = lp("Team Liquid", "Spacestation Gaming", 1, 3)                          # Liquipedia lists them the other way round
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", 3, 1)
    lk = link_of(reconcile([m], [f], MAP), m)
    assert lk.tier == STRONG and lk.disagreements == []


def test_a_link_resting_on_an_unreviewed_team_name_mapping_is_provisional():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1)
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", 3, 1)
    lk = link_of(reconcile([m], [f], resolver({"Spacestation Gaming": ("spacestation-gaming", "proposed"),
                                               "Team Liquid": "team-liquid"})), m)
    assert lk.tier == STRONG and lk.provisional


def test_a_name_that_is_not_mapped_is_never_guessed_at():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1)
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", 3, 1)                   # the names are one edit apart; that is not evidence
    lk = link_of(reconcile([m], [f], resolver({"Team Liquid": "team-liquid"})), m)
    assert lk.tier == UNMATCHED and lk.evidence["names"] == ["Spacestation Gaming"] and "not mapped" in lk.basis


# ------------------------------------------------------------------------- the same-day rematch

def test_the_same_teams_twice_in_a_day_are_separated_by_series_score():
    first_lp, second_lp = lp("Dallas Fuel", "Team Liquid", 3, 0, idx=1), \
        lp("Dallas Fuel", "Team Liquid", 3, 2, T0 + timedelta(hours=3), idx=2)
    first_f = fs("F-bracket", "Dallas Fuel", "Team Liquid", 3, 0)
    second_f = fs("F-final", "Dallas Fuel", "Team Liquid", 3, 2, T0 + timedelta(hours=3, minutes=40))
    res = reconcile([first_lp, second_lp], [second_f, first_f], MAP)
    a, b = link_of(res, first_lp), link_of(res, second_lp)
    assert (a.tier, a.faceit_id, b.tier, b.faceit_id) == (STRONG, "F-bracket", STRONG, "F-final")
    assert "separated by series score" in a.basis and "met 2 times within a day" in a.basis


def test_a_rematch_that_score_cannot_separate_is_ambiguous_and_order_is_only_a_suggestion():
    m = lp("Dallas Fuel", "Team Liquid", 3, 0)
    early = fs("F-early", "Dallas Fuel", "Team Liquid", 3, 0)
    late = fs("F-late", "Dallas Fuel", "Team Liquid", 3, 0, T0 + timedelta(hours=3))     # same score, still in the window
    res = reconcile([m], [late, early], MAP)
    lk = link_of(res, m)
    assert lk.tier == AMBIGUOUS and lk.faceit_id is None
    assert {c["faceit_id"] for c in lk.candidates} == {"F-early", "F-late"}
    assert "F-early -> F-late" in lk.evidence["suggestion"]
    assert {f.match_id for f in res.faceit_unlinked} == {"F-early", "F-late"}          # nothing was consumed


def test_two_records_that_fit_one_faceit_match_are_both_ambiguous():
    # both must land inside the -60..+360 min window around F1's time (T0+45) to both be strict candidates
    a, b = lp("Dallas Fuel", "Team Liquid", 3, 0, idx=1), lp("Dallas Fuel", "Team Liquid", 3, 0, T0 + timedelta(minutes=90), idx=2)
    res = reconcile([a, b], [fs("F1", "Dallas Fuel", "Team Liquid", 3, 0)], MAP)
    assert [lk.tier for lk in res.links] == [AMBIGUOUS, AMBIGUOUS] and all(not lk.faceit_id for lk in res.links)


# ------------------------------------------------------------------------- tier 3: ambiguous

@pytest.mark.parametrize("what,record,series", [
    ("the score differs", dict(s1=3, s2=1), dict(s1=3, s2=2)),
    ("the best-of differs", dict(s1=3, s2=1, bo=7), dict(s1=3, s2=1, bo=5)),
    ("the time is outside the window", dict(s1=3, s2=1), dict(s1=3, s2=1, when=T0 + timedelta(hours=10))),
    ("FACEIT's time is only when the result was entered", dict(s1=3, s2=1),
     dict(s1=3, s2=1, when=T0 + timedelta(days=3), state="result_only", reliable=False)),
])
def test_the_pair_matches_but_something_disagrees_goes_to_review_not_to_a_link(what, record, series):
    m = lp("Spacestation Gaming", "Team Liquid", record["s1"], record["s2"], bo=record.get("bo", 5))
    kw = {k: v for k, v in series.items() if k not in ("s1", "s2")}
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", series["s1"], series["s2"], **kw)
    res = reconcile([m], [f], MAP)
    lk = link_of(res, m)
    assert lk.tier == AMBIGUOUS and lk.faceit_id is None, what
    assert lk.candidates[0]["disagrees_on"], what
    assert res.faceit_unlinked == [f]


def test_a_reviewers_decision_settles_an_ambiguous_match_and_only_an_ambiguous_one():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1)
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", 3, 2)
    yes = link_of(reconcile([m], [f], MAP, decisions={m.objectname: {"faceit_match_id": "F1"}}), m)
    assert (yes.tier, yes.decision, yes.faceit_id) == (AMBIGUOUS, "confirmed", "F1")
    no = link_of(reconcile([m], [f], MAP, decisions={m.objectname: {"faceit_match_id": None}}), m)
    assert (no.tier, no.decision, no.faceit_id) == (AMBIGUOUS, "rejected", None)
    exact = lp("Spacestation Gaming", "Team Liquid", 3, 1, faceit_id=FID)      # a decision cannot override an exact link
    lk = link_of(reconcile([exact], [fs(FID, "SpaceStation Gaming", "Team Liquid", 3, 1)], MAP,
                           decisions={exact.objectname: {"faceit_match_id": None}}), exact)
    assert lk.tier == EXACT and lk.decision is None


# ------------------------------------------------------------------------- tier 4 and region

def test_nothing_on_the_other_side_is_unmatched_on_both_sides():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1)
    orphan = fs("F9", "Dallas Fuel", "Team Liquid", 3, 0)
    res = reconcile([m], [orphan], MAP)
    assert link_of(res, m).tier == UNMATCHED and res.faceit_unlinked == [orphan]


def test_a_candidate_in_the_other_region_is_a_mismatch_not_a_match():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1, page=NA_PAGE)
    across = fs("F-emea", "SpaceStation Gaming", "Team Liquid", 3, 1, region="emea", comp="c-emea")
    res = reconcile([m], [across], MAP)
    assert link_of(res, m).tier == UNMATCHED and link_of(res, m).faceit_id is None
    assert res.region_rejections == [{"lp": m.objectname, "lp_time": "2026-06-13 18:00Z", "faceit_id": "F-emea",
                                      "lp_region": "na", "faceit_region": "emea",
                                      "teams": "Spacestation Gaming / Team Liquid"}]
    intl = fs("F-intl", "SpaceStation Gaming", "Team Liquid", 3, 1, region="international")   # any region may attend
    assert link_of(reconcile([m], [intl], MAP), m).tier == STRONG


def test_a_2024_north_america_page_matches_faceit_na_rather_than_being_rejected():
    m = lp("Spacestation Gaming", "Team Liquid", 3, 1, page="Overwatch_Champions_Series/2024/North_America/Stage_1")
    res = reconcile([m], [fs("F-na", "SpaceStation Gaming", "Team Liquid", 3, 1, region="na")], MAP)
    assert link_of(res, m).tier == STRONG and link_of(res, m).faceit_id == "F-na"
    assert res.region_rejections == []


def test_two_unrelated_teams_with_one_name_are_told_apart_by_the_region_of_the_page():
    names = resolver({("geekay esports", "na"): "geekay-na", ("geekay esports", "emea"): "geekay-emea",
                      "Team Liquid": "team-liquid"})
    m_emea = lp("Geekay Esports", "Team Liquid", 3, 1, page=EMEA_PAGE)
    na = fs("F-na", "Geekay Esports", "Team Liquid", 3, 1, org1="geekay-na", region="na")
    emea = fs("F-emea", "Geekay Esports", "Team Liquid", 3, 1, org1="geekay-emea", region="emea", comp="c-emea")
    lk = link_of(reconcile([m_emea], [na, emea], names), m_emea)
    assert (lk.tier, lk.faceit_id) == (STRONG, "F-emea")


def test_a_match_known_to_both_sources_is_one_match():
    a = lp("Spacestation Gaming", "Team Liquid", 3, 1, faceit_id=FID, idx=1)
    b = lp("Spacestation Gaming", "Team Liquid", 3, 1, idx=2)                   # the same match, listed again with no id
    f = fs(FID, "SpaceStation Gaming", "Team Liquid", 3, 1)
    res = reconcile([a, b], [f], MAP)
    linked = [lk for lk in res.links if lk.faceit_id]
    assert [lk.faceit_id for lk in linked] == [FID] and link_of(res, b).tier == UNMATCHED   # never twice


# ------------------------------------------------------------------------- orientation and team names

def test_orientation_prefers_orgs_then_names_then_score_then_winner():
    f = fs("F1", "SpaceStation Gaming", "Team Liquid", 3, 1)
    assert orient(lp("Team Liquid", "Spacestation Gaming", 1, 3), f, MAP) == (True, "orgs")
    assert orient(lp("Team Liquid", "Spacestation Gaming", 1, 3), f, resolver({})) [1] in ("names", "score")
    assert orient(lp("Alpha", "Beta", 3, 1), f) == (False, "score")
    assert orient(lp("Alpha", "Beta", 1, 3), f) == (True, "score")
    level = fs("F2", "X", "Y", 2, 2)
    assert orient(lp("Alpha", "Beta", 2, 2, ), level)[0] is None


def _pair(name1, name2, o1, o2, s1=3, s2=1, region_page=NA_PAGE, when=T0, fid="F"):
    return (lp(name1, name2, s1, s2, when, page=region_page, faceit_id=fid),
            fs(fid, name1 + "_", name2 + "_", s1, s2, org1=o1, org2=o2))


def test_a_name_with_consistent_evidence_across_matches_is_proposed_strong():
    pairs = [_pair("Rad Esports", "Dallas Fuel", "rad", "dallas", fid=f"F{i}", when=T0 + timedelta(days=i)) for i in range(3)]
    props = {p.lp_name: p for p in propose(pairs, ["Rad Esports", "Dallas Fuel"], TeamMap("nope.json"), {}, {})}
    assert (props["Rad Esports"].org_key, props["Rad Esports"].strength, props["Rad Esports"].pairs) == ("rad", "strong", 3)


def test_two_names_for_one_faceit_team_are_review_because_a_rename_is_not_an_org_merge():
    pairs = [_pair("Team Z", "Dallas Fuel", "z-id", "dallas", fid=f"F{i}", when=T0 + timedelta(days=i)) for i in range(2)]
    pairs += [_pair("Supernova", "Dallas Fuel", "z-id", "dallas", fid=f"G{i}", when=T0 + timedelta(days=9 + i)) for i in range(2)]
    props = {p.lp_name: p for p in propose(pairs, ["Team Z", "Supernova", "Dallas Fuel"], TeamMap("nope.json"), {}, {})}
    assert props["Team Z"].strength == props["Supernova"].strength == "review"
    assert "SHARED" in " ".join(props["Team Z"].evidence) and "do not merge their histories" in " ".join(props["Team Z"].evidence)
    assert props["Dallas Fuel"].strength == "strong"


def test_one_name_that_is_two_teams_in_two_regions_is_proposed_per_region():
    pairs = [_pair("Geekay Esports", "Team Liquid", "geekay-na", "tl", fid=f"N{i}", region_page=NA_PAGE, when=T0 + timedelta(days=i))
             for i in range(2)]
    pairs += [_pair("Geekay Esports", "Twisted Minds", "geekay-emea", "tm", fid=f"E{i}", region_page=EMEA_PAGE,
                    when=T0 + timedelta(days=5 + i)) for i in range(2)]
    props = [p for p in propose(pairs, ["Geekay Esports"], TeamMap("nope.json"), {}, {}) if p.lp_name == "Geekay Esports"]
    assert {(p.region, p.org_key, p.strength) for p in props} == {("na", "geekay-na", "strong"), ("emea", "geekay-emea", "strong")}
    resolve = make_resolver(TeamMap("nope.json"), {p.key: p for p in props})
    assert resolve("Geekay Esports", "na") == ("geekay-na", "proposed") and resolve("Geekay Esports", "emea") == ("geekay-emea", "proposed")


def test_deciding_one_region_of_a_split_name_does_not_swallow_the_other_regions_evidence(tmp_path):
    pairs = [_pair("Geekay Esports", "Team Liquid", "geekay-na", "tl", fid=f"N{i}", region_page=NA_PAGE, when=T0 + timedelta(days=i))
             for i in range(2)]
    pairs += [_pair("Geekay Esports", "Twisted Minds", "geekay-emea", "tm", fid=f"E{i}", region_page=EMEA_PAGE,
                    when=T0 + timedelta(days=5 + i)) for i in range(2)]
    tm = TeamMap(tmp_path / "map.json")
    tm.decide("Geekay Esports", "team", "geekay-na-id", region="na")     # only NA decided; EMEA still has to be proposed
    props = [p for p in propose(pairs, ["Geekay Esports"], tm, {}, {}) if p.lp_name == "Geekay Esports"]
    by_region = {p.region: p for p in props}
    assert by_region["na"].decided and by_region["na"].org_key == "team:geekay-na-id"
    assert by_region["emea"].strength == "strong" and by_region["emea"].org_key == "geekay-emea" and not by_region["emea"].decided


def test_a_decided_mapping_is_trusted_without_a_provisional_flag_and_regions_are_kept(tmp_path):
    tm = TeamMap(tmp_path / "map.json")
    tm.decide("Spacestation Gaming", "org", "spacestation-gaming")
    tm.decide("Geekay Esports", "team", "590b7d3b", region="na")
    tm.decide("Geekay Esports", "team", "46f8e560", region="emea")
    tm.save()
    again = TeamMap(tmp_path / "map.json")
    assert again.org_key("Spacestation Gaming", "na") == "spacestation-gaming"
    assert again.org_key("Geekay Esports", "na") == "team:590b7d3b" and again.org_key("Geekay Esports", "emea") == "team:46f8e560"
    assert again.org_key("Geekay Esports") is None                             # no region, no guess
    assert make_resolver(again)("Spacestation Gaming") == ("spacestation-gaming", "decided")
    assert entity_of_org_key("team:590b7d3b") == ("team", "590b7d3b") and entity_of_org_key("qadsiah") == ("org", "qadsiah")


# ------------------------------------------------------------------------- DB round trip

def test_a_run_reads_the_stored_response_and_writes_back_a_link_that_survives_a_reread(lp_db, tmp_path):
    conn = lp_db
    map_path = write_map_file(tmp_path / "liquipedia_map.json")
    team_map_path = tmp_path / "team_map.json"
    TeamMap(team_map_path).save()
    decisions_path = tmp_path / "link_decisions.json"

    run = run_reconciliation(conn, team_map_path=str(team_map_path), decisions_path=str(decisions_path),
                             map_path=str(map_path))
    assert len(run.lps) == 1 and run.lps[0].faceit_match_id == DB_FACEIT_ID
    lk = run.result.links[0]
    assert (lk.tier, lk.faceit_id, lk.disagreements) == (EXACT, DB_FACEIT_ID, [])

    counts = store_run(conn, run)
    assert counts == {"liquipedia_matches": 1, "liquipedia_links": 1}

    with conn.cursor() as cur:
        cur.execute("SELECT objectname, faceit_match_id, championship_id, team1_name, team2_name FROM liquipedia_matches")
        m = cur.fetchone()
        cur.execute("SELECT lp_objectname, faceit_match_id, tier, provisional, disagreements FROM liquipedia_links")
        lk_row = cur.fetchone()
    assert m["faceit_match_id"] == DB_FACEIT_ID and m["championship_id"] == DB_CHAMPIONSHIP
    assert (m["team1_name"], m["team2_name"]) == ("Dallas Fuel", "Team Liquid")
    assert (lk_row["faceit_match_id"], lk_row["tier"], lk_row["provisional"], lk_row["disagreements"]) == (DB_FACEIT_ID, EXACT, False, [])
    assert lk_row["lp_objectname"] == m["objectname"]

    # storing again (a re-run) replaces rather than duplicates
    counts_again = store_run(conn, run)
    assert counts_again == counts
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM liquipedia_matches")
        assert cur.fetchone()["n"] == 1
