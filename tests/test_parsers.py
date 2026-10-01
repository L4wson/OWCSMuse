"""Parser tests on captured FACEIT payloads (tests/fixtures, fetched 2026-09-17).

Fixture inventory
  match_detail_bo5_4rounds / match_stats_bo5_4rounds / list_item_bo5_4rounds
      OWCS 2024 EMEA Stage 1 Main Event, Twisted Minds 3-1 Ex Oblivione: 5 picks, 4 maps played.
  match_detail_bo7_5rounds / match_stats_bo7_5rounds
      Grand final bo7, 7 picks, 5 maps played.
  list_item_bo5_first_map_result / match_detail_bo5_flip / match_stats_bo5_flip
      Twisted Minds 3-1 Ex Oblivione where Ex Oblivione won map 1 (2-0). The list item's
      `results` was replaced with that first-map result to reproduce the documented quirk.
  match_detail_2026 / match_stats_2026
      OWCS 2026 OQ EMEA: richer player_stats keys and a non-GLOBAL region.
"""

from datetime import datetime, timezone

from owcsmuse.parsers.championships import derive_region, is_owcs, parse_championship
from owcsmuse.parsers.common import ts_from_epoch
from owcsmuse.parsers.matches import (
    parse_match_detail,
    parse_match_stub,
    parse_results,
    results_differ,
    winner_flipped,
)
from owcsmuse.parsers.stats import parse_match_stats, parse_round

TWISTED_MINDS = "2b9f2e7a-f91a-4597-b2fa-d413eaed605e"
EX_OBLIVIONE = "bb5dd404-213c-430f-8d12-8687fc3ff747"


# --------------------------------------------------------------- rounds < picks

def test_rounds_are_maps_played_not_picks_bo5(fx):
    detail = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    rounds = parse_match_stats(fx("match_stats_bo5_4rounds.json"), detail.map_names, detail.match_id)

    assert detail.best_of == 5
    assert len(detail.picks) == 5          # maps picked/vetoed into the pool
    assert len(rounds) == 4                # maps actually played: series ended 3-1
    assert [r.round_number for r in rounds] == [1, 2, 3, 4]
    assert len(rounds) < len(detail.picks)


def test_rounds_are_maps_played_not_picks_bo7(fx):
    detail = parse_match_detail(fx("match_detail_bo7_5rounds.json"))
    rounds = parse_match_stats(fx("match_stats_bo7_5rounds.json"), detail.map_names, detail.match_id)

    assert detail.best_of == 7
    assert len(detail.picks) == 7
    assert len(rounds) == 5
    # detailed_results on this match has 6 entries: another reason to count rounds[] only
    assert len(detail.detailed_results) == 6


def test_rounds_equal_picks_when_series_goes_full_pool(fx):
    detail = parse_match_detail(fx("match_detail_2026.json"))
    rounds = parse_match_stats(fx("match_stats_2026.json"), detail.map_names)
    assert len(detail.picks) == 3
    assert len(rounds) == 3


# --------------------------------------------------------- mode / map handling

def test_game_mode_comes_from_round_stats_not_map_name(fx):
    detail = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    rounds = parse_match_stats(fx("match_stats_bo5_4rounds.json"), detail.map_names)
    assert [r.game_mode for r in rounds] == ["Control", "Hybrid", "Push", "Flashpoint"]

    # Even if the map name would suggest Control, the payload's OW2 Mode wins.
    synthetic = {
        "match_round": "1",
        "round_stats": {"Map": "Lijiang Tower", "OW2 Mode": "Escort", "Winner": TWISTED_MINDS},
        "teams": [],
    }
    assert parse_round(synthetic).game_mode == "Escort"
    assert parse_round(synthetic).map_name == "Lijiang Tower"

    # Missing mode stays None rather than being inferred.
    synthetic["round_stats"].pop("OW2 Mode")
    assert parse_round(synthetic).game_mode is None


def test_map_guid_resolved_to_name_via_detail_voting_entities(fx):
    detail = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    rounds = parse_match_stats(fx("match_stats_bo5_4rounds.json"), detail.map_names)
    assert [r.map_name for r in rounds] == ["Lijiang Tower", "Blizzard World", "Esperança", "Suravasa"]
    assert all(r.map_guid.startswith("0x") for r in rounds)
    assert [p.map_name for p in detail.picks][-1] == "Shambali Monastery"  # picked, never played

    # Without the detail's entity table the GUID is kept and the name is unknown.
    bare = parse_match_stats(fx("match_stats_bo5_4rounds.json"))
    assert bare[0].map_guid == "0x0800000000000662"
    assert bare[0].map_name is None


# ------------------------------------------------------ players <-> teams join

def test_players_join_rounds_through_team_id(fx):
    detail = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    rounds = parse_match_stats(fx("match_stats_bo5_4rounds.json"), detail.map_names)
    faction_ids = {detail.faction1.team_id, detail.faction2.team_id}
    assert faction_ids == {TWISTED_MINDS, EX_OBLIVIONE}

    for r in rounds:
        assert {t.team_id for t in r.teams} == faction_ids
        assert len(r.players) == 10
        for p in r.players:
            assert p.team_id in faction_ids
        per_team = {tid: sum(1 for p in r.players if p.team_id == tid) for tid in faction_ids}
        assert per_team == {TWISTED_MINDS: 5, EX_OBLIVIONE: 5}


def test_round_winner_and_team_scores(fx):
    detail = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    rounds = parse_match_stats(fx("match_stats_bo5_4rounds.json"), detail.map_names)
    r1, r2, r3, r4 = rounds
    assert (r1.winner_team_id, r1.team1.score, r1.team2.score, r1.score_summary) == (TWISTED_MINDS, 2, 1, "2 / 1")
    assert r3.winner_team_id == EX_OBLIVIONE and (r3.team1.score, r3.team2.score) == (0, 1)
    assert r1.team1.win is True and r1.team2.win is False
    assert r1.team1.name == "Twisted Minds"
    # series tally from rounds agrees with the detail result
    wins = sum(1 for r in rounds if r.winner_team_id == TWISTED_MINDS)
    assert wins == detail.result.faction1_score == 3


def test_player_stats_typed_columns_and_raw_dict(fx):
    rounds = parse_match_stats(fx("match_stats_bo5_4rounds.json"))
    p = next(p for p in rounds[0].players if p.nickname == "kellemanden")
    assert p.player_id == "b273a710-800f-4638-9858-461d81ac55b9"
    assert (p.eliminations, p.deaths, p.assists) == (18, 5, 16)
    assert p.healing_done == 9739.0 and p.damage_dealt == 8801.0 and p.damage_mitigated == 3032.0
    assert p.role == "Support" and p.result == 1
    assert p.final_blows is None  # key absent on 2024 payloads
    assert p.stats["K/D Ratio"] == "3.6"  # raw strings preserved


def test_2026_payload_has_extended_stats(fx):
    detail = parse_match_detail(fx("match_detail_2026.json"))
    rounds = parse_match_stats(fx("match_stats_2026.json"), detail.map_names)
    p = rounds[0].players[0]
    assert p.final_blows is not None and p.time_played is not None and p.objective_time is not None
    assert detail.region == "EMEA"
    assert rounds[0].game_mode == "Control"


# ------------------------------------------------ first map vs series result

def test_list_result_is_first_map_and_detail_overrides(fx):
    stub = parse_match_stub(fx("list_item_bo5_first_map_result.json"))
    detail = parse_match_detail(fx("match_detail_bo5_flip.json"))
    assert stub.match_id == detail.match_id

    # LIST says Ex Oblivione (faction2) won 2-0: that is map 1, not the series.
    assert (stub.result.winner_faction, stub.result.faction1_score, stub.result.faction2_score) == ("faction2", 0, 2)
    # DETAIL says Twisted Minds (faction1) won the series 3-1.
    assert (detail.result.winner_faction, detail.result.faction1_score, detail.result.faction2_score) == ("faction1", 3, 1)
    assert detail.winner_team_id == TWISTED_MINDS

    assert winner_flipped(stub.result, detail.result) is True
    assert results_differ(stub.result, detail.result) is True

    # the rounds confirm the detail, and again rounds (4) < picks (5)
    rounds = parse_match_stats(fx("match_stats_bo5_flip.json"), detail.map_names)
    assert [r.winner_team_id for r in rounds] == [EX_OBLIVIONE, TWISTED_MINDS, TWISTED_MINDS, TWISTED_MINDS]
    assert len(rounds) == 4 and len(detail.picks) == 5


def test_no_flip_when_list_and_detail_agree(fx):
    stub = parse_match_stub(fx("list_item_bo5_4rounds.json"))
    detail = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    assert winner_flipped(stub.result, detail.result) is False
    assert results_differ(stub.result, detail.result) is False


def test_parse_results_tolerates_missing_or_odd_values():
    assert parse_results(None).is_known is False
    assert parse_results({"winner": "", "score": {}}).winner_faction is None
    r = parse_results({"winner": "faction2", "score": {"faction2": "3", "faction1": "2"}})
    assert (r.winner_faction, r.faction1_score, r.faction2_score) == ("faction2", 2, 3)


# ------------------------------------------------------------- match detail

def test_parse_match_detail_fields(fx):
    d = parse_match_detail(fx("match_detail_bo5_4rounds.json"))
    assert d.match_id == "1-7553f194-b7d7-4bc9-bda4-3484592e014f"
    assert d.championship_id == "f57f9c5f-7840-4a49-8c32-24682dece3fc"
    assert d.status == "FINISHED" and d.game_id == "ow2"
    assert d.faction1.name == "Twisted Minds" and d.faction2.name == "Ex Oblivione"
    assert d.started_at == datetime(2024, 3, 24, 18, 9, 36, tzinfo=timezone.utc)
    assert d.started_at.tzinfo is not None
    assert d.faceit_url.startswith("https://www.faceit.com/en/")

    assert len(d.roster) == 14
    subs = [e for e in d.roster if e.is_substitute]
    assert len(subs) == 4  # 3 on faction1, 1 on faction2
    starters_f1 = [e for e in d.roster if e.faction == "faction1" and not e.is_substitute]
    assert len(starters_f1) == 5 and all(e.team_id == TWISTED_MINDS for e in starters_f1)
    ksaa = next(e for e in d.roster if e.player_id == "92695183-d00e-4c31-9707-ff9d8500f52a")
    assert ksaa.nickname == "KSAA0" and ksaa.game_player_name == "KSAA"


# ------------------------------------------------------------- championships

def test_parse_championship_and_region(fx):
    page = fx("organizer_championships_page.json")
    c = parse_championship(page["items"][0])
    assert c.championship_id == "d3d61baf-1ce8-4fb7-a2dd-6e9d70e61397"
    assert c.name == "OWCS 2024: EMEA Stage 1 - Open Qualifiers"
    assert c.region == "GLOBAL" and c.derived_region == "EMEA"
    assert c.championship_start == datetime(2024, 3, 1, 17, 20, tzinfo=timezone.utc)  # ms epoch
    assert c.type == "swiss" and c.status == "finished"
    assert c.faceit_url and "{lang}" not in c.faceit_url


def test_is_owcs_and_derive_region():
    assert is_owcs("OWCS 2024: NA Stage 2 - Main Event")
    assert is_owcs("Overwatch Champions Series Asia")
    assert is_owcs("OWCS 2026 OQ - NA")
    assert not is_owcs("Dreamhack Dallas")
    assert not is_owcs("FACEIT League Season 6 - Expert Qualifier (EMEA)")
    assert not is_owcs("S5 NA OWCSX")  # no word boundary match
    assert derive_region("OWCS 2026 OQ - NA") == "NA"
    assert derive_region("OWCS 2024: EMEA Stage 1 - Group A") == "EMEA"
    assert derive_region("OWCS 2025 Korea Stage 1") == "KR"
    assert derive_region("Dreamhack Dallas") is None


def test_ts_from_epoch_seconds_and_millis():
    assert ts_from_epoch(1711303776) == datetime(2024, 3, 24, 18, 9, 36, tzinfo=timezone.utc)
    assert ts_from_epoch(1709313600000) == datetime(2024, 3, 1, 17, 20, tzinfo=timezone.utc)
    assert ts_from_epoch(None) is None and ts_from_epoch(0) is None and ts_from_epoch("x") is None


# ------------------------------------------------------------------ bracket byes

def _with_bye(item):
    item = dict(item, teams=dict(item["teams"]))
    item["teams"]["faction2"] = dict(item["teams"]["faction2"], faction_id="bye", name="bye")
    return item


def test_a_bracket_bye_is_recognised_as_not_a_series(fx):
    """FACEIT scores the real team 1-0 against a placeholder faction called 'bye'; that is not a match."""
    real = parse_match_stub(fx("list_item_bo5_4rounds.json"))
    assert not real.involves_bye
    bye = parse_match_stub(_with_bye(fx("list_item_bo5_4rounds.json")))
    assert bye.involves_bye and bye.faction2.is_bye and not bye.faction1.is_bye


def test_a_team_merely_named_like_bye_is_matched_on_the_whole_name(fx):
    item = fx("list_item_bo5_4rounds.json")
    item = dict(item, teams=dict(item["teams"]))
    item["teams"]["faction2"] = dict(item["teams"]["faction2"], name="Byelorussia Esports")
    assert not parse_match_stub(item).involves_bye
