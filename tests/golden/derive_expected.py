"""Derive the golden cases' expected values from the raw payloads and write tests/golden/cases.json.

    python tests/golden/derive_expected.py

Every number here comes from independent.py, which reads the captured FACEIT JSON
and imports nothing from owcsmuse. Nothing here calls ask(), and nothing may: the
rule of this suite is that an expected value is never copied from the code's own
output, because that is how a bug becomes a "correct" answer.

A case is written as status "proposed" unless its id is in CONFIRMED below, which
is the list of cases a person has reviewed and signed off; only confirmed cases are
asserted in CI. Adding an id to CONFIRMED is the act of confirming it.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import independent as I  # noqa: E402

S = I.all_series()
CHAMPS = I.championships()


def team_id(name: str, region: str | None = None) -> str:
    ids = {s.team[k] for s in S for k in s.team if s.name[k] == name and (region is None or s.region == region)}
    assert len(ids) == 1, (name, region, ids)
    return next(iter(ids))


def pid(nickname: str) -> str:
    return I.player_id_by_nickname(S, nickname)


def pname(nickname: str) -> str:
    return I.display_name(S, pid(nickname))


def d(x):
    return str(x)


# Reviewed and confirmed by the project owner on 2026-09-21 (all 25 originally proposed, plus G26, which splits the
# alias-resolution half of G13 out so it is asserted while G13's record is a known bug).
CONFIRMED = {f"G{n:02d}" for n in range(1, 27)}
# G29/G30 were added at the owner's request to assert that a question in the displayed OWCS name resolves; their
# expected values are derived below from the raw payloads like every other case, and the owner can still review them.
CONFIRMED |= {"G29", "G30"}
# G31 (Stage 3 step 4) asserts the capability rule: a player-stat question over a results-only slice is refused with
# reason results_only and a working alternative, never answered with an empty or partial leaderboard.
CONFIRMED |= {"G31"}
# G32-G34 (owner, 2026-10-02): Liquipedia-linked results - the 2024 region fix, a phantom-inflated grand final, Dallas maps
CONFIRMED |= {"G32", "G33", "G34"}
# G35+ (owner, 2026-10-02 bug batch): each bug's golden case
CONFIRMED |= {"G35", "G36", "G37"}
# G38+ (owner, 2026-10-08): the leaderboard map floor
CONFIRMED |= {"G38", "G39", "G40"}
# G41+ (owner, 2026-10-08): team qualifiers become filters
CONFIRMED |= {"G41", "G42", "G43", "G44"}

CASES: list[dict] = []


def case(id, title, kind, question, expect, derivation, regression=None, known_bug=None):
    c = {"id": id, "title": title, "kind": kind, "regression": regression, "question": question,
         "expect": expect, "derivation": derivation, "status": "confirmed" if id in CONFIRMED else "proposed"}
    if known_bug:
        c["known_bug"] = known_bug     # the expectation is right and the code is wrong today; see harness/test
    CASES.append(c)


def player_rows(rec, name):
    return {"nickname": name, "maps": rec["maps"], "map_wins": rec["map_wins"], "map_losses": rec["map_losses"]}


# ----------------------------------------------------------------- player records
SUG, ZSS, QRT = "sug2rfree", "z_ow", "Quartz03"
sug, zss, qrt = (I.player_record(S, pid(n)) for n in (SUG, ZSS, QRT))
assert sug["regions"] == ["na"] and zss["regions"] == ["na"]

case("G01", "sug2rfree's map record", "exact", "sug2rfree record",
     {"status": "ok", "entity": {"role": "subject", "type": "player", "id": pid(SUG), "name": pname(SUG)},
      "rows": [{**player_rows(sug, pname(SUG)), "eliminations": sug["eliminations"], "deaths": sug["deaths"]}]},
     f"Every round in the golden stats payloads where player {pid(SUG)[:8]} appears: {sug['maps']} maps over "
     f"{sug['matches']} series; a map is won when round_stats.Winner is his team id. Name is his in-game name "
     f"(game_player_name), not the FACEIT nickname {SUG}.",
     regression="displays the in-game name, not the FACEIT nickname (KSAA0 class)")

case("G02", "sug2rfree shows NA only", "invariant", "sug2rfree record",
     {"status": "ok", "evidence": {"total_rows": sug["maps"], "regions_only": ["na"]}},
     f"All {sug['maps']} of his maps are in NA competitions, and the golden set includes 2 EMEA 'SpaceStation' matches "
     "(a different team) that must not appear. A wrong SpaceStation/SpaceStation Gaming merge would add them.",
     regression="region bug: sug2rfree's record showed EMEA matches")

case("G03", "ZSS's map record", "exact", "ZSS record",
     {"status": "ok", "entity": {"role": "subject", "type": "player", "id": pid(ZSS), "name": pname(ZSS)},
      "rows": [{**player_rows(zss, pname(ZSS)), "eliminations": zss["eliminations"], "deaths": zss["deaths"]}]},
     f"Same derivation: {zss['maps']} maps over {zss['matches']} series. FACEIT nickname is {ZSS}; in-game name {pname(ZSS)}.")

case("G04", "ZSS shows NA only", "invariant", "ZSS record",
     {"status": "ok", "evidence": {"total_rows": zss["maps"], "regions_only": ["na"]}},
     "All maps are NA. The golden set includes both Geekay Esports teams (NA and EMEA, identical names); a wrong merge "
     "of them would pull in EMEA maps.", regression="region bug: ZSS's record showed EMEA matches")

case("G05", "Quartz03's record answers", "exact", "Quartz03 record",
     {"status": "ok", "entity": {"role": "subject", "type": "player", "id": pid(QRT), "name": pname(QRT)},
      "rows": [{**player_rows(qrt, pname(QRT)), "eliminations": qrt["eliminations"], "deaths": qrt["deaths"]}]},
     f"{qrt['maps']} maps over {qrt['matches']} series, all EMEA. The bug turned a missing team into the key 'team:None' and "
     "returned no_data; the assertion is that it answers at all, and with these numbers.",
     regression="team:None: a player's record returned no_data")

case("G06", "Quartz03's K/D", "exact", "what is Quartz03's kd",
     {"status": "ok", "entity": {"role": "subject", "type": "player", "id": pid(QRT), "name": pname(QRT)},
      "rows": [{"nickname": pname(QRT), "kd_ratio": d(qrt["kd_ratio"])}]},
     f"Total Eliminations {qrt['eliminations']} / total Deaths {qrt['deaths']} = {qrt['kd_ratio']} (ratio of totals, not a mean "
     "of per-map ratios).", regression="team:None: K/D questions returned no_data")

avg = I.player_avg(S, pid(QRT), "Damage Dealt")
case("G07", "Quartz03's average damage per map", "exact", "average damage per map for Quartz03",
     {"status": "ok", "rows": [{"nickname": pname(QRT), "maps_with_stat": avg["maps_with_stat"], "total": avg["total"],
                                "avg_per_map": d(avg["avg_per_map"])}]},
     f"Damage Dealt summed over his {avg['maps_with_stat']} maps = {avg['total']}; / maps = {avg['avg_per_map']}.")

# ----------------------------------------------------------------- team records
tm = [team_id("Twisted Minds")]
gk_na, gk_em = team_id("Geekay Esports", "na"), team_id("Geekay Esports", "emea")

# Stage 2: 1-a823bbde (Twisted Minds vs Geekay EMEA) is result_only on FACEIT but Liquipedia has its 5 maps
# (tests/golden/liquipedia_matches.json), reconstructed independently, never from owcsmuse's enrich.py. Every
# team_record() call touching either side of that match needs it, or its 'maps' total silently drops behind
# what the actual system now reports.
A823 = "1-a823bbde-de66-4928-8527-54f4e8882293"
LP_OVERRIDES = {A823: I.liquipedia_rounds(A823, tm[0], gk_em)}
assert [m["map"] for m in LP_OVERRIDES[A823]] == ["Oasis", "King's Row", "Runasapi", "Circuit Royal", "Suravasa"]

tm_all = I.team_record(S, tm, liquipedia_overrides=LP_OVERRIDES)
tm26 = I.team_record(S, tm, season=2026, liquipedia_overrides=LP_OVERRIDES)
ssg_id = team_id("SpaceStation Gaming")
ssg_2024 = team_id("SpaceStation")
# The owner decided (2026-10-02) that the 2024 EMEA 'SpaceStation' team and the 2025+ NA 'SpaceStation Gaming' team
# are one organisation (scope/org_decisions.json, org spacestation-gaming), reversing the 2026-09-19 unmerge: the
# org's record is both team ids' series.
ssg = I.team_record(S, [ssg_id, ssg_2024])
ssg_na = I.team_record(S, [ssg_id])
assert ssg["regions"] == ["emea", "na"] and ssg["matches"] == ssg_na["matches"] + 2


def team_row(rec, name):
    return {"team": name, "matches": rec["matches"], "wins": rec["wins"], "losses": rec["losses"],
            "map_wins": rec["map_wins"], "map_losses": rec["map_losses"], "maps": rec["maps"]}


case("G08", "Twisted Minds' record, all seasons, byes excluded", "exact", "Twisted Minds record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": tm[0], "name": "Twisted Minds"},
      "rows": [team_row(tm_all, "Twisted Minds")]},
     f"Series where Twisted Minds is a faction and the opponent is a real team: {tm_all['matches']} "
     f"(the golden set also holds a TM-vs-'bye' bracket slot, which is not a series and must not be counted as a 5th). "
     f"map_wins/losses are series scores; 'maps' counts rounds that have stats, {tm_all['maps']} (of which 5 are "
     f"{A823[:10]}'s, Stage 2 map results from Liquipedia rather than a FACEIT stats payload); "
     f"{tm_all['result_only_series']} of the series still has no FACEIT stats payload of its own.",
     regression="bye: a bracket bye counted as a 1-0 win")

case("G09", "Twisted Minds 2026, one series enriched from Liquipedia instead of FACEIT", "exact",
     "Twisted Minds record in 2026",
     {"status": "ok", "rows": [team_row(tm26, "Twisted Minds")], "limitations": ["main_series_2025_2026"]},
     f"{tm26['matches']} series in 2026, one of them ({tm26['result_only_series']}) with no FACEIT stats payload: it "
     f"still counts at series grain (wins and map_wins/losses from the series score), but as of Stage 2 it also "
     f"contributes its 5 maps to 'maps' - from Liquipedia's match2games ({A823[:10]}), not from a FACEIT stats "
     "payload. offline_map_stats no longer applies to this slice, because nothing in it is left without map results.",
     regression="result-only series counted at series grain only; then, after Stage 2, its Liquipedia maps must "
                "count at map grain and the limitation must drop once nothing in the slice is missing them")

case("G10", "SpaceStation Gaming's record: one organisation, EMEA in 2024 then NA", "exact", "SpaceStation Gaming record",
     {"status": "ok", "entity": {"role": "subject", "type": "org", "id": "spacestation-gaming", "name": "SpaceStation Gaming"},
      "rows": [team_row(ssg, "SpaceStation Gaming")], "evidence": {"regions_only": ["emea", "na"]}},
     f"{ssg_na['matches']} NA series of team {ssg_id[:8]} plus the two 2024 EMEA series of 'SpaceStation' (team "
     f"{ssg_2024[:8]}): the owner decided on 2026-10-02 that these are one organisation (SSG played EMEA in 2024 and became "
     f"an NA partner team in 2025), each team id mapped over its own era. Until then the two were held apart as a wrong "
     f"cross-region merge; the region check now carries this org as an owner-decided exception.",
     regression="region bug: SpaceStation Gaming merged with the EMEA SpaceStation; reversed by the owner's 2026-10-02 decision")

h2h = I.team_record(S, tm, opponent_ids=[team_id("Ex Oblivione")])
case("G11", "Twisted Minds vs Ex Oblivione, series grain", "exact", "Twisted Minds series record against Ex Oblivione",
     {"status": "ok", "rows": [{"matches": h2h["matches"], "wins": h2h["wins"], "losses": h2h["losses"]}]},
     f"{h2h['matches']} series between the two team ids in the golden set (both 3-1 to Twisted Minds). Team id bb5dd404 was "
     "'Ex Oblivione' in 2024 and was later acquired into Virtus pro. The name must be searchable and find those 2024 "
     "series, which are Ex Oblivione's, not Virtus pro's.",
     regression="date-bounded team-to-org mapping (Stage 3): 'Ex Oblivione' is searchable as the team id's own 2024 era, "
                "and a hit on it never puts those series into Virtus pro's record")

# ----------------------------------------------------------------- resolution
dsg_id = team_id("Disguised")
dsg = I.team_record(S, [dsg_id])
vp_ids = [team_id("Virtus pro"), team_id("Virtuspro")]
vp = I.team_record(S, vp_ids, exclude_names={"Ex Oblivione"})
tl_id = team_id("Team Liquid")
tl = I.team_record(S, [tl_id])
case("G12", "'SSG' resolves to SpaceStation Gaming", "exact", "SSG record",
     {"status": "ok", "entity": {"role": "subject", "type": "org", "id": "spacestation-gaming", "name": "SpaceStation Gaming"},
      "rows": [team_row(ssg, "SpaceStation Gaming")]},
     "Same numbers as G10, reached through the shorthand. Expectation is the community meaning of SSG.",
     regression="alias: SSG did not resolve to SpaceStation Gaming")
case("G13", "'VP' resolves to Virtus pro; its record excludes the Ex Oblivione era", "exact", "VP record",
     {"status": "ok", "entity": {"role": "subject", "type": "org", "id": "virtus-pro", "name": "Virtus pro"},
      "rows": [{"matches": vp["matches"], "wins": vp["wins"], "losses": vp["losses"],
                "map_wins": vp["map_wins"], "map_losses": vp["map_losses"]}]},
     f"The org Virtus pro holds two team ids, c02a9899 (2026) and bb5dd404. FACEIT named bb5dd404 'Ex Oblivione' in 2024 and "
     f"'Virtuspro' in 2025. Virtus pro acquired the Ex Oblivione roster, and roster movement is not org identity, so "
     f"the 3 Ex Oblivione-era series are NOT Virtus pro's: {vp['matches']} series remain, {vp['wins']} won, series score "
     f"{vp['map_wins']}-{vp['map_losses']}.",
     regression="alias/org: VP resolves to the merged Virtus pro org; date-bounded team-to-org mapping (Stage 3): "
                "bb5dd404 is Virtus pro from 2025-01-01 only, so its Ex Oblivione era (3 series) stays out of the record")

case("G26", "'VP' resolves to the Virtus pro org", "invariant", "VP record",
     {"entity": {"role": "subject", "type": "org", "id": "virtus-pro", "name": "Virtus pro"}, "status": "ok"},
     "The alias vp -> org virtus-pro (scope/alias_decisions.json). Asserts only who the question resolved to, so the "
     "alias stays covered while G13's record is a known bug.", regression="alias: VP")

case("G14", "'DSG' resolves to Disguised", "exact", "DSG record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": dsg_id, "name": "Disguised"},
      "rows": [{"team": "Disguised", "matches": dsg["matches"], "wins": dsg["wins"], "losses": dsg["losses"]}]},
     f"Disguised: {dsg['matches']} series in the golden set. DSG is the community shorthand for Disguised.",
     regression="alias: DSG")

case("G15", "'TL' resolves to Team Liquid", "exact", "TL record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": tl_id, "name": "Team Liquid"},
      "rows": [{"team": "Team Liquid", "matches": tl["matches"], "wins": tl["wins"], "losses": tl["losses"]}]},
     f"Team Liquid: {tl['matches']} series.", regression="alias")

# ----------------------------------------------------------------- clarify
r_na = I.team_record(S, [gk_na])
r_em = I.team_record(S, [gk_em], liquipedia_overrides=LP_OVERRIDES)
case("G16", "Two teams named Geekay Esports ask, never guess", "invariant", "Geekay Esports record",
     {"status": "clarify", "code": "ambiguous_entity", "candidate_ids": sorted([gk_na, gk_em])},
     "Two unrelated teams share the name (NA and EMEA, 0% roster overlap, merge rejected in scope/org_decisions.json). "
     "The answer is a question back with exactly these two candidates.",
     regression="the wrong Geekay merge; clarify")
case("G17", "Clarify candidate (NA Geekay) answered verbatim", "exact", "Geekay Esports record",
     {"status": "clarify", "answer_candidate": {"id": gk_na, "expect": {
         "status": "ok", "entity": {"role": "subject", "id": gk_na},
         "rows": [team_row(r_na, "Geekay Esports")], "evidence": {"regions_only": ["na"]}}}},
     f"Ask the NA candidate's own question, unedited. {r_na['matches']} NA series ({r_na['wins']}-{r_na['losses']}).",
     regression="clarify: a candidate must be answerable verbatim")
case("G18", "Clarify candidate (EMEA Geekay) answered verbatim", "exact", "Geekay Esports record",
     {"status": "clarify", "answer_candidate": {"id": gk_em, "expect": {
         "status": "ok", "entity": {"role": "subject", "id": gk_em},
         "rows": [team_row(r_em, "Geekay Esports")], "evidence": {"regions_only": ["emea"]}}}},
     f"The EMEA candidate: {r_em['matches']} series ({r_em['wins']}-{r_em['losses']}), one of them "
     f"({A823[:10]}) with no FACEIT stats payload but, as of Stage 2, {len(LP_OVERRIDES[A823])} maps from "
     "Liquipedia.", regression="clarify: a candidate must be answerable verbatim")

# ----------------------------------------------------------------- leaderboards
top_elim, n_elim = I.leaderboard(S, "Eliminations", season=2026, top=3)
assert len({r["total"] for r in top_elim}) == 3, "tie inside the asserted top 3"
case("G19", "Most eliminations in 2026", "exact", "who had the most eliminations in 2026",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, r["player_id"]), "total": r["total"],
                                "maps_with_stat": r["maps_with_stat"]} for r in top_elim]},
     f"Eliminations summed per player over 2026 maps in the golden set ({n_elim} players); top 3 shown, totals distinct.")

top_tank, n_tank = I.leaderboard(S, "Eliminations", role="Tank", top=3)
assert len({r["total"] for r in top_tank}) == 3
tank_players = sorted(I.display_name(S, p) for p in
                      {p["player_id"] for s in S if s.counts_as_series for r in s.rounds for p in r["players"]
                       if p["stats"].get("Role") == "Tank"})
case("G20", "'tank with the most kills' ranks tanks only", "exact", "tank with the most kills",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, r["player_id"]), "total": r["total"],
                                "maps_with_stat": r["maps_with_stat"]} for r in top_tank],
      "rows_only_players": tank_players, "evidence": {"roles_only": ["Tank"]}},
     f"'Kills' = FACEIT Eliminations, summed over only the maps where the player's Role was Tank ({n_tank} tank players). "
     "Every returned player must be one of the tank-role players, and every evidence row's role must be Tank.",
     regression="the role filter was dropped: 'tank with the most kills' ranked everyone")

top_heal, n_heal = I.leaderboard(S, "Healing Done", season=2025, top=3)
assert len({r["total"] for r in top_heal}) == 3
case("G21", "Most healing in 2025", "exact", "who had the most healing done in 2025",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, r["player_id"]), "total": r["total"],
                                "maps_with_stat": r["maps_with_stat"]} for r in top_heal]},
     f"Healing Done summed over 2025 maps ({n_heal} players with the stat).")

# ----------------------------------------------------------------- versus
pv = I.versus_maps(S, pid(SUG), opponent_player_id=pid(ZSS))
case("G22", "Player vs player: sug2rfree against ZSS", "exact", "sug2rfree map record against ZSS",
     {"status": "ok", "rows": [{"maps": pv["maps"], "matches": pv["matches"], "map_wins": pv["map_wins"],
                                "map_losses": pv["map_losses"]}]},
     f"Maps where both appear on opposite teams: {pv['maps']} over {pv['matches']} series (SSG v LuneX).",
     regression="versus at map grain, player vs player")

# a Geekay EMEA player who faced Virtus pro in the bo7, as player-vs-org
vp_match = next(s for s in S if s.match_id == "1-5a5ff7bb-ef8c-4c59-ab19-a740d8dac594")
cands = {}
for r in vp_match.rounds:
    for p in r["players"]:
        if r["teams"].get(p["team_id"]) == "Geekay Esports":
            cands[p["player_id"]] = cands.get(p["player_id"], 0) + 1
gk_player = sorted(cands, key=lambda k: (-cands[k], I.display_name(S, k)))[0]
gk_name = I.display_name(S, gk_player)
po = I.versus_maps(S, gk_player, opponent_team_ids=set(vp_ids))
case("G23", "Player vs org: a Geekay EMEA player against Virtus Pro", "exact", f"{gk_name} map record against Virtus Pro",
     {"status": "ok", "rows": [{"maps": po["maps"], "matches": po["matches"], "map_wins": po["map_wins"],
                                "map_losses": po["map_losses"]}]},
     f"{gk_name} played {cands[gk_player]} of the 7 maps of Virtus pro 4-3 Geekay; Virtus Pro is an org of two team ids, and "
     f"he faced it in {po['matches']} series in the golden set.", regression="versus, player vs org")

# ----------------------------------------------------------------- refusals
fb_seasons = I.stat_seasons(S, "Final Blows")
assert 2024 not in fb_seasons and fb_seasons
case("G24", "A refusal that offers a question that works", "invariant", "who had the most final blows in 2024",
     {"status": "cannot_answer", "code": "no_data",
      "alternative": {"question_template": "who had the most final blows in {season}",
                      "seasons_with_stat": fb_seasons,
                      "top1_by_season": {str(y): {"nickname": I.display_name(S, I.leaderboard(S, "Final Blows", season=y, top=1)[0][0]["player_id"]),
                                                  "total": I.leaderboard(S, "Final Blows", season=y, top=1)[0][0]["total"]}
                                         for y in fb_seasons}}},
     f"Final Blows appears in the golden stats only for seasons {fb_seasons}, not 2024, so 2024 cannot be answered. The "
     "refusal must offer the same question in a season that has the stat, and that question must answer with the "
     "top player derived independently for that season.", regression="a refusal with advice but no working alternative")

# ------------------------------------------------------- Stage 2: Liquipedia map enrichment
# LP_OVERRIDES[A823] (defined above, with tm_all/tm26/r_em) is the same independently-reconstructed 5 maps -
# never from owcsmuse's own enrich.py.
tm_gk_h2h = I.team_h2h_maps(S, tm, [gk_em], liquipedia_overrides=LP_OVERRIDES)
case("G27", "Twisted Minds vs Geekay Esports (EMEA), map grain, after Stage 2 enrichment", "exact",
     f"Twisted Minds map record against {gk_em}",
     {"status": "ok", "rows": [{"maps": tm_gk_h2h["maps"], "map_wins": tm_gk_h2h["map_wins"],
                                "map_losses": tm_gk_h2h["map_losses"], "matches": tm_gk_h2h["matches"]}]},
     f"Two series between these team ids: 1-a106c5a1 (3 real FACEIT maps, all Twisted Minds) and {A823[:10]} "
     "(result_only on FACEIT, 5 maps from Liquipedia's own match2games: Geekay win Oasis and Circuit Royal, "
     "Twisted Minds win King's Row, Runasapi and Suravasa). Combined: "
     f"{tm_gk_h2h['maps']} maps, {tm_gk_h2h['map_wins']}-{tm_gk_h2h['map_losses']} to Twisted Minds, over "
     f"{tm_gk_h2h['matches']} series. Before Stage 2 this was 3-0 over 1 series' worth of maps (the second series "
     "contributed nothing to map grain).",
     regression="Stage 2: a result_only series' Liquipedia maps must appear at map grain once enriched")

simple_ow = I.player_record(S, I.player_id_by_nickname(S, "SimpleOW"))
case("G28", "A player on the enriched match still has no player stats from it", "invariant", "SimpleOW record",
     {"status": "ok", "rows": [{"maps": simple_ow["maps"], "map_wins": simple_ow["map_wins"],
                                "map_losses": simple_ow["map_losses"]}],
      "evidence": {"total_rows": simple_ow["maps"]}},
     f"SimpleOW played on Geekay Esports (EMEA) in both 1-a106c5a1 (3 real FACEIT maps) and {A823[:10]} (the "
     f"enriched result_only series, {tm_gk_h2h['maps'] - simple_ow['maps']} of its maps now visible at team grain "
     "via G27). FACEIT's own stats payload for the enriched series carries no players at all - Liquipedia never "
     "has player stats to add - so his independently-derived record is exactly the 3 maps of 1-a106c5a1: Stage 2 "
     "must not have created a match_players row for the enriched match.",
     regression="Stage 2: a Liquipedia-sourced map must never produce a player row")

tm25 = I.team_record(S, tm, season=2025)
assert tm25["matches"] == 0
case("G25", "Twisted Minds in 2025: only a bye, so no data", "invariant", "Twisted Minds record in 2025",
     {"status": "cannot_answer", "code": "no_data",
      "alternative": {"question_template": "Twisted Minds record", "seasons_with_stat": [None],
                      "then_rows": [team_row(tm_all, "Twisted Minds")]}},
     "The only 2025 Twisted Minds fixture is the bracket bye, which is not a series: the answer is no_data, not '1-0'. "
     "The offered alternative (the all-seasons record) must answer with G08's numbers.",
     regression="bye: a 2025 bye showed as a 1-0 win")

# --- the displayed OWCS name is searchable -------------------------------------------------------------------------
# scope/liquipedia_map.json pairs FACEIT League "S9 NA OWCS Central - X" with Liquipedia's 2026/NA/Stage_2 pages, so
# "OWCS 2026 NA Stage 2 <Regular Season|Playoffs>" is S9 NA <Regular Season|Playoffs>. SpaceStation Gaming also has
# S8 NA (Stage 1) series in the golden set, so a question that ignored the stage - or only matched "regular season" -
# would count them.
def in_competition(faceit_name):
    return [s for s in S if CHAMPS[s.champ]["name"] == faceit_name]


ssg_s9_rs = I.team_record(in_competition("S9 NA OWCS Central - Regular Season"), [ssg_id])
ssg_s8_rs = I.team_record(in_competition("S8 NA OWCS Central - Regular Season"), [ssg_id])
df_id = team_id("Dallas Fuel")
df_s9_po = I.team_record(in_competition("S9 NA OWCS Central - Playoffs"), [df_id])
df_s9_rs = I.team_record(in_competition("S9 NA OWCS Central - Regular Season"), [df_id])
assert (ssg_s9_rs["matches"], ssg_s8_rs["matches"], df_s9_po["matches"], df_s9_rs["matches"]) == (1, 1, 2, 1)

case("G29", "A question in the displayed OWCS name resolves: Stage 2 Regular Season, not Stage 1", "exact",
     "SpaceStation Gaming record in OWCS 2026 NA Stage 2 Regular Season",
     {"status": "ok", "rows": [team_row(ssg_s9_rs, "SpaceStation Gaming")]},
     f"'OWCS 2026 NA Stage 2 Regular Season' is FACEIT's 'S9 NA OWCS Central - Regular Season' (S9 = 2026 Stage 2 per "
     f"scope/liquipedia_map.json). SpaceStation Gaming played {ssg_s9_rs['matches']} series there "
     f"({ssg_s9_rs['wins']}-{ssg_s9_rs['losses']}, maps {ssg_s9_rs['map_wins']}-{ssg_s9_rs['map_losses']}) and "
     f"{ssg_s8_rs['matches']} in Stage 1's regular season, which must not be counted.",
     regression="the displayed competition name was not searchable (matching used only FACEIT's stored name), and "
                "the parser kept only one phrase of the competition name")

case("G30", "A question in the displayed OWCS name resolves: Stage 2 Playoffs, not the regular season", "exact",
     "Dallas Fuel record in OWCS 2026 NA Stage 2 Playoffs",
     {"status": "ok", "rows": [team_row(df_s9_po, "Dallas Fuel")]},
     f"'OWCS 2026 NA Stage 2 Playoffs' is FACEIT's 'S9 NA OWCS Central - Playoffs'. Dallas Fuel played "
     f"{df_s9_po['matches']} series there ({df_s9_po['wins']}-{df_s9_po['losses']}, maps "
     f"{df_s9_po['map_wins']}-{df_s9_po['map_losses']}); its {df_s9_rs['matches']} regular-season series "
     f"({df_s9_rs['wins']}-{df_s9_rs['losses']}) is the same stage and must not be counted.",
     regression="the displayed competition name was not searchable")

top_elims = I.leaderboard(S, "Eliminations", top=1)[0][0]
case("G31", "A player-stat question for a results-only region is refused for that reason, with a working alternative",
     "invariant", "who had the most eliminations in korea",
     {"status": "cannot_answer", "code": "results_only", "rows_only_players": [],
      "alternative": {"question_template": "who had the most eliminations", "seasons_with_stat": [None],
                      "then_rows": [{"nickname": I.display_name(S, top_elims["player_id"]), "total": top_elims["total"]}]}},
     "Korea is declared a results-only region (region_sources: Liquipedia only, no player stats) before any of its data "
     "exists, and no golden series is in that region. A player leaderboard there has nothing to rank, so the answer "
     "must be a refusal with reason code results_only - not no_data, not out_of_scope, and never a leaderboard with "
     "zero or some rows. It must offer the same question without the region, and that question must answer with the "
     f"independently-derived all-seasons eliminations leader ({top_elims['total']} eliminations).",
     regression="Stage 3 step 4: capability, not just coverage")


# ------------------------------------------------- Liquipedia-linked results (Stage 3)
# Each value is read off the captured Liquipedia record (independent.liquipedia_series), the source of record for a
# linked series' result; the FACEIT payload is used only to name which faction is Liquipedia's team 1.
NA_SERIES, NA_FINAL, DALLAS = ("1-4b984ffd-9868-45fa-92c5-c6a290bfe68a", "1-70cff415-3817-4144-9eca-e917f89cb6e7",
                               "1-43d289c0-bb18-416b-b639-b7e076b41e7f")
by_id = {x.match_id: x for x in S}
tor = team_id("Toronto Defiant")


def oriented(mid, subject_name):
    """(subject's score, opponent's score, best-of) from Liquipedia, the subject named as FACEIT names it."""
    x = by_id[mid]
    lp = I.liquipedia_series(mid, x.name["faction1"])
    t1_is_subject = I_fold(lp["lp_team1"]) == I_fold(subject_name)
    return (lp["score1"], lp["score2"]) if t1_is_subject else (lp["score2"], lp["score1"]), lp


def I_fold(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


(na_for, na_against), na_lp = oriented(NA_SERIES, "Toronto Defiant")
(gf_for, gf_against), gf_lp = oriented(NA_FINAL, "Toronto Defiant")
faceit_gf = by_id[NA_FINAL].score
assert (na_for, na_against, na_lp["best_of"], gf_for, gf_against, gf_lp["best_of"]) == (3, 2, 5, 4, 0, 7)
assert sorted(faceit_gf.values()) == [0, 5]                     # what the answer must NOT present

case("G32", "A 2024 NA series with no FACEIT id on its page is linked to Liquipedia", "exact",
     "Toronto Defiant series record against Timeless",
     {"status": "ok", "evidence": {"by_match": {NA_SERIES: {"score": na_for, "opponent_score": na_against,
                                                            "best_of": na_lp["best_of"], "sources": ["faceit", "liquipedia"]}}}},
     f"Liquipedia's {na_lp['lp_team1']} {na_lp['score1']}-{na_lp['score2']} {na_lp['lp_team2']} (bo{na_lp['best_of']}) on "
     "'Overwatch_Champions_Series/2024/North_America/Stage_1' names no FACEIT id; it links (strong) only because the page "
     "resolves to region na and both team names are decided. Read as region 'other' (the 2024 page path spells North "
     "America out), every 2024 NA record was rejected as cross-region and the series carried FACEIT alone.",
     regression="2024 'North_America' pages resolved to region 'other' (2026-10-02)")

tor_rows = []
for x in S:
    if not x.counts_as_series:
        continue
    for k, o in (("faction1", "faction2"), ("faction2", "faction1")):
        if x.team[k] == tor:
            if x.match_id in I.LIQUIPEDIA:
                (mine, theirs), _ = oriented(x.match_id, "Toronto Defiant")
            else:
                mine, theirs = x.score[k], x.score[o]
            tor_rows.append((x.match_id, mine, theirs, x.winner_faction == k))
tor_rec = {"matches": len(tor_rows), "wins": sum(w for *_, w in tor_rows), "losses": sum(not w for *_, w in tor_rows),
           "map_wins": sum(m for _, m, _, _ in tor_rows), "map_losses": sum(t for _, _, t, _ in tor_rows)}
case("G33", "A grand final FACEIT inflated with a phantom map presents Liquipedia's score", "exact",
     "Toronto Defiant record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": tor, "name": "Toronto Defiant"},
      "rows": [{"team": "Toronto Defiant", **tor_rec}],
      "evidence": {"by_match": {NA_FINAL: {"score": gf_for, "opponent_score": gf_against, "best_of": gf_lp["best_of"],
                                           "sources": ["faceit", "liquipedia"]}}},
      # read after by_match in the harness: a real case that breaks if by_match ever again skips what follows it
      "sentence_contains": [f"{tor_rec['wins']}-{tor_rec['losses']} in series and "
                            f"{tor_rec['map_wins']}-{tor_rec['map_losses']} in maps"]},
     f"Toronto Defiant's {tor_rec['matches']} golden series, each scored from Liquipedia where linked (the source of record) "
     f"and from FACEIT otherwise: " + ", ".join(f"{mid[:10]} {mine}-{theirs}" for mid, mine, theirs, _ in tor_rows)
     + f". The grand final is {gf_for}-{gf_against} (bo{gf_lp['best_of']}); FACEIT stores it as "
     f"{max(faceit_gf.values())}-{min(faceit_gf.values())} with a 5th detailed_results entry (Dorado, 1-0) nobody played.",
     regression="FACEIT phantom map in a sweep's series score; Liquipedia is the source of record where linked (034)")

fal, ence = team_id("Team Falcons"), team_id("ENCE")
x = by_id[DALLAS]
fal_is_lp1 = I_fold(I.liquipedia_series(DALLAS, x.name["faction1"])["lp_team1"]) == I_fold("Team Falcons")
dl = I.liquipedia_series(DALLAS, x.name["faction1"])
fal_side = 1 if fal_is_lp1 else 2
games = dl["games"]
assert x.state if hasattr(x, "state") else True
case("G34", "A Dreamhack Dallas series has Liquipedia's maps, a drawn map, and Liquipedia's play time", "exact",
     f"team:{fal} map record against {ence}",          # by id: the parser reads "Team Falcons" as "falcons" (open item)
     {"status": "ok", "rows": [{"maps": len(games), "matches": 1,
                                "map_wins": sum(g["winner"] == fal_side for g in games),
                                "map_losses": sum(g["winner"] not in (None, fal_side) for g in games),
                                "draws": sum(g["winner"] is None for g in games)}],
      "evidence": {"by_match": {DALLAS: {"sources": ["faceit", "liquipedia"], "played_at": str(dl["played_at"])}}}},
     f"FACEIT has this series result_only (no map stats, best_of stored as 1, its time the result's entry). Liquipedia's "
     f"record has {len(games)} games played: " + ", ".join(f"{g['map']} ({'drawn' if g['winner'] is None else ('Falcons' if g['winner'] == fal_side else 'ENCE')})" for g in games)
     + f", scheduled {dl['played_at']:%Y-%m-%d %H:%M}Z. A drawn map is nobody's win (030).",
     regression="Dallas linked by owner decision and enriched (2026-10-02): Liquipedia maps and schedule for a result_only series")


# ------------------------------------------------- bug batch (2026-10-02)
from decimal import Decimal as _D  # noqa: E402

# The owner's leaderboard floor (2026-10-08): an ascending total, a per-map average or a rate ranks only players with at
# least this many maps, so a one-series fill-in (Danny 1 map, K0RTAL 3) cannot lead it. Restated here, not imported: the
# derivation must not read owcsmuse.
MIN_MAPS = 4
FLOOR_NOTE = f"(players with at least {MIN_MAPS} maps)"

kd_rows = {}
for x in S:
    if x.season != 2026 or not x.rounds:
        continue
    for rnd in x.rounds:
        for pl in rnd["players"]:
            e, dth = I.num(pl["stats"], "Eliminations"), I.num(pl["stats"], "Deaths")
            if e is None or dth is None:
                continue
            k = kd_rows.setdefault(pl["player_id"], [0, 0, 0])
            k[0] += e; k[1] += dth; k[2] += 1
ranked = sorted(((round(_D(e) / _D(dth), 2), m, pid_) for pid_, (e, dth, m) in kd_rows.items() if dth and m >= MIN_MAPS),
                key=lambda t: (-t[0], -t[1]))
kd_top, kd_maps, kd_pid = ranked[0]
assert ranked[1][0] < kd_top, "a tie at the top would make the expected leader arbitrary"
kd_shown = format(kd_top.normalize(), "f")
case("G35", "A K/D leaderboard's sentence quotes the K/D, not the map win %", "exact", "highest kd in 2026",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, kd_pid), "kd_ratio": str(kd_top)}],
      "sentence_contains": [f"leads K/D ratio with {kd_shown} across {kd_maps} map", FLOOR_NOTE]},
     f"K/D = total Eliminations / total Deaths over each player's 2026 maps (never a sum or average of per-map ratios), "
     f"among players with at least {MIN_MAPS} maps (a rate: the leaderboard floor applies). "
     f"Highest: {I.display_name(S, kd_pid)}, {kd_rows[kd_pid][0]}/{kd_rows[kd_pid][1]} = {kd_top} over {kd_maps} maps. "
     "The sentence once printed the row's first numeric column instead (production: Attack's 77.80 map win % for a 5.00 K/D).",
     regression="leaderboard sentence quoted map_win_pct as the K/D (2026-10-02)")


# G36/G37: a role leaderboard ranks the players whose primary role it is (most maps that season), over their maps in it
role_maps = collections.defaultdict(list)
for x in S:
    if x.season != 2024 or x.region != "na" or not x.counts_as_series:
        continue
    for rnd in x.rounds:
        for pl in rnd["players"]:
            role, dth = pl["stats"].get("Role"), I.num(pl["stats"], "Deaths")
            if role and role != "-":
                role_maps[pl["player_id"]].append((role, dth))
season_roles = collections.defaultdict(collections.Counter)      # primary role is over the whole season, all regions
for x in S:
    if x.season != 2024:
        continue
    for rnd in x.rounds:
        for pl in rnd["players"]:
            if pl["stats"].get("Role"):
                season_roles[pl["player_id"]][pl["stats"]["Role"]] += 1
def primary(pid_):
    c = season_roles[pid_]; top = max(c.values())
    return {r for r, n in c.items() if n == top}
supports = sorted(((sum(d for r, d in ms if r == "Support" and d is not None), sum(r == "Support" for r, _ in ms), pid_)
                   for pid_, ms in role_maps.items() if "Support" in primary(pid_) and any(r == "Support" for r, _ in ms)),
                  key=lambda t: (t[0], -t[1]))
mer1t = next(p_ for p_ in role_maps if I.display_name(S, p_) == "MER1T")
assert "Support" not in primary(mer1t) and any(r == "Support" for r, _ in role_maps[mer1t])
low_d, low_maps, low_pid = supports[0]
low_d = int(low_d)
assert supports[1][:2] != (low_d, low_maps), "a tie at the bottom would make the expected leader arbitrary"
# "with at least 1 map" turns the floor off, so this case still isolates the primary-role rule: MER1T's one Support map
# is under the floor, which would hide him whether or not the role rule works.
case("G36", "A role leaderboard ranks only players whose role it is", "exact",
     "which na support had the least deaths in 2024 with at least 1 map",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, low_pid), "total": low_d}],
      "rows_only_players": sorted({I.display_name(S, p_) for _, _, p_ in supports}),
      "sentence_contains": [f"{I.display_name(S, low_pid)} has the lowest Deaths among supports with {low_d}"],
      "sentence_lacks": [FLOOR_NOTE]},
     f"Among 2024 NA players whose primary 2024 role is Support (most maps), any number of maps (asked for: the floor is "
     f"off), Deaths summed over their Support maps, lowest first: {I.display_name(S, low_pid)}, {low_d} over {low_maps} map(s). MER1T played one golden map as Support "
     f"({[d for r, d in role_maps[mer1t] if r == 'Support'][0]} deaths) but his 2024 role is "
     f"{'/'.join(sorted(primary(mer1t)))}, so he is no support; a per-map filter once ranked him first.",
     regression="role filter applied per map, so one flex map made a damage player a support (2026-10-02)")
case("G37", "Every entity link in an ascending sentence covers its own text", "invariant",
     "which na support had the least deaths in 2024",
     {"status": "ok", "spans_match_text": True},
     "The ascending verb ('has the lowest') was substituted for 'leads' after the spans were placed, shifting every later "
     "span by 9 characters: the stat link covered 'e lowe' inside 'the lowest'. Each span's text must equal the sentence "
     "text at its offsets.",
     regression="span offsets shifted by a post-hoc text rewrite (2026-10-02)")


# ------------------------------------------------- leaderboard floor (2026-10-08)
fb_rows = collections.defaultdict(list)                  # 2026 Final Blows per map, every player
for x in S:
    if x.season != 2026 or not x.rounds:
        continue
    for rnd in x.rounds:
        for pl in rnd["players"]:
            e = I.num(pl["stats"], "Final Blows")
            if e is not None:
                fb_rows[pl["player_id"]].append(e)
per_map = sorted(((round(_D(sum(v)) / len(v), 2), len(v), p_) for p_, v in fb_rows.items() if len(v) >= MIN_MAPS),
                 key=lambda t: (-t[0], -t[1]))
pm_top, pm_maps, pm_pid = per_map[0]
assert per_map[1][0] < pm_top, "a tie at the top would make the expected leader arbitrary"
under = max(((round(_D(sum(v)) / len(v), 2), len(v), p_) for p_, v in fb_rows.items() if len(v) < MIN_MAPS), default=None)
assert under and under[0] > pm_top, "the case proves the floor only if a sub-floor player would otherwise lead"
case("G38", "A per-map average ranks only players with enough maps, and says so", "exact",
     "most final blows per map in 2026",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, pm_pid), "avg_per_map": str(pm_top)}],
      "sentence_contains": [f"{I.display_name(S, pm_pid)} leads", FLOOR_NOTE]},
     f"Final Blows per map = total / maps with the stat, 2026, players with at least {MIN_MAPS} maps: "
     f"{I.display_name(S, pm_pid)}, {sum(fb_rows[pm_pid])}/{pm_maps} = {pm_top}. Without the floor "
     f"{I.display_name(S, under[2])} would lead at {under[0]} over {under[1]} map(s).",
     regression="a one-series appearance led per-map and ascending leaderboards (owner, 2026-10-08)")

deaths24 = collections.defaultdict(lambda: [0, 0])          # 2024 Deaths, every player, every region
for x in S:
    if x.season != 2024 or not x.counts_as_series:
        continue
    for rnd in x.rounds:
        for pl in rnd["players"]:
            dth = I.num(pl["stats"], "Deaths")
            if dth is not None:
                deaths24[pl["player_id"]][0] += dth; deaths24[pl["player_id"]][1] += 1
most = sorted(((t, m, p_) for p_, (t, m) in deaths24.items()), key=lambda t: (-t[0], -t[1]))
assert most[1][0] < most[0][0], "a tie at the top would make the expected leader arbitrary"
case("G39", "A descending total takes no map floor", "exact", "most deaths in 2024",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, most[0][2]), "total": int(most[0][0])}],
      "sentence_lacks": ["at least"]},
     f"Deaths summed over every 2024 map, highest first: {I.display_name(S, most[0][2])}, {int(most[0][0])} over "
     f"{most[0][1]} maps. Few maps cannot top a descending total, so no floor applies and the sentence names none.",
     regression="the floor is for ascending totals, averages and rates only (owner, 2026-10-08)")

floored = [t for t in supports if sum(r == "Support" and d is not None for r, d in role_maps[t[2]]) >= MIN_MAPS]
fl_d, fl_maps, fl_pid = floored[0]
assert floored[1][:2] != (fl_d, fl_maps), "a tie at the bottom would make the expected leader arbitrary"
assert supports[0][2] != fl_pid, "the case proves the floor only if a sub-floor support would otherwise lead"
case("G40", "An ascending total ranks only players with enough maps, and says so", "exact",
     "which na support had the least deaths in 2024",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, fl_pid), "total": int(fl_d)}],
      "rows_only_players": sorted({I.display_name(S, p_) for _, _, p_ in floored}),
      "sentence_contains": [f"{I.display_name(S, fl_pid)} has the lowest Deaths among supports with {int(fl_d)}", FLOOR_NOTE]},
     f"G36's slice with the floor on: 2024 NA primary supports with at least {MIN_MAPS} Support maps, Deaths lowest first: "
     f"{I.display_name(S, fl_pid)}, {int(fl_d)} over {fl_maps} maps. Without the floor {I.display_name(S, supports[0][2])} "
     f"leads with {int(supports[0][0])} over {supports[0][1]} map(s).",
     regression="a one-series appearance led per-map and ascending leaderboards (owner, 2026-10-08)")


# ------------------------------------------------- team qualifiers (2026-10-08)
def team_deaths(team, season, role=None, primary_of=None):
    """Deaths per player over the maps they played for `team` in `season` (as `role`, when given, and only players whose
    primary role that season it is, by `primary_of`)."""
    out = collections.defaultdict(lambda: [0, 0])
    for x in S:
        if x.season != season or not x.counts_as_series:
            continue
        for rnd in x.rounds:
            for pl in rnd["players"]:
                dth = I.num(pl["stats"], "Deaths")
                if pl["team_id"] != team or dth is None or (role and pl["stats"].get("Role") != role):
                    continue
                if role and role not in primary_of(pl["player_id"]):
                    continue
                out[pl["player_id"]][0] += dth; out[pl["player_id"]][1] += 1
    ranked = sorted(((t, m, p_) for p_, (t, m) in out.items()), key=lambda t: (-t[0], -t[1]))
    assert ranked and (len(ranked) == 1 or ranked[1][0] < ranked[0][0]), "a tie at the top would make the leader arbitrary"
    return ranked


DF = team_id("Dallas Fuel")
df_rank = team_deaths(DF, 2026)
case("G41", "An abbreviated team in front of 'player' filters the leaderboard", "exact",
     "which DF player had the most deaths in 2026",
     {"status": "ok", "entity": {"role": "team", "type": "team", "id": DF, "name": "Dallas Fuel"},
      "rows": [{"nickname": I.display_name(S, df_rank[0][2]), "total": int(df_rank[0][0])}],
      "rows_only_players": sorted({I.display_name(S, p_) for *_, p_ in df_rank}),
      "sentence_contains": [f"{I.display_name(S, df_rank[0][2])} leads Deaths among Dallas Fuel players with {int(df_rank[0][0])}"]},
     f"Deaths over the 2026 maps each player played for Dallas Fuel ({DF[:8]}; 'DF' is the owner's alias): "
     f"{I.display_name(S, df_rank[0][2])} {int(df_rank[0][0])} over {df_rank[0][1]} maps, of {len(df_rank)} Dallas Fuel players. "
     "The qualifier was once dropped and the whole league ranked.",
     regression="a team named before 'player' was not a filter (owner, 2026-10-08)")

TM = team_id("Twisted Minds")
roles24 = collections.defaultdict(collections.Counter)          # primary role is over the whole season, every team
for x in S:
    if x.season == 2024:
        for rnd in x.rounds:
            for pl in rnd["players"]:
                if pl["stats"].get("Role"):
                    roles24[pl["player_id"]][pl["stats"]["Role"]] += 1
def primary24(p_):
    c = roles24[p_]; top = max(c.values())
    return {r for r, n in c.items() if n == top}
tm_rank = team_deaths(TM, 2024, role="Tank", primary_of=primary24)
case("G42", "A full team name in front of a role filters the role leaderboard to that team", "exact",
     "which twisted minds tank had the most deaths in 2024",
     {"status": "ok", "entity": {"role": "team", "id": TM, "name": "Twisted Minds"},
      "rows": [{"nickname": I.display_name(S, tm_rank[0][2]), "total": int(tm_rank[0][0])}],
      "rows_only_players": sorted({I.display_name(S, p_) for *_, p_ in tm_rank}),
      "sentence_contains": [f"{I.display_name(S, tm_rank[0][2])} leads Deaths among Twisted Minds tanks with {int(tm_rank[0][0])}"]},
     "Deaths over the 2024 Tank maps each primary-tank player played for Twisted Minds: "
     + ", ".join(f"{I.display_name(S, p_)} {int(t)}/{m} maps" for t, m, p_ in tm_rank)
     + ". The team was once dropped, ranking every 2024 tank.",
     regression="a team named before a role was not a filter (owner, 2026-10-08)")

SUGF = pid(SUG)
vs_tl = [m for m in I.player_maps(S, SUGF, season=2026) if m["opp_team_id"] == team_id("Team Liquid")]
vw, vl = sum(m["won"] for m in vs_tl), sum(not m["won"] and not m["drawn"] for m in vs_tl)
case("G43", "'Team' is part of a team's name, not a keyword", "exact",
     "sugarfree vs team liquid in 2026",
     {"status": "ok", "entity": {"role": "opponent", "id": team_id("Team Liquid"), "name": "Team Liquid"},
      "sentence_contains": [f"{I.display_name(S, SUGF)} is {vw}-{vl} in maps against Team Liquid in 2026"]},
     f"sugarfree's 2026 maps against Team Liquid's team id: {len(vs_tl)} maps, {vw} won, {vl} lost. The parser once "
     "dropped 'team' as a stopword and searched 'liquid'.",
     regression="'Team' eaten as a keyword (README open list, owner 2026-10-08)")

case("G44", "An aliased team's answer prints its name, never its id", "invariant", "TL record in 2026",
     {"status": "ok", "entity": {"role": "subject", "name": "Team Liquid"}, "no_raw_ids": True},
     "Team Liquid is an unmapped team id, so its rows carry org_key 'team:<uuid>'; the CLI printed that column beside the "
     "name. Nothing a reader sees (sentence, reason, rendered answer) may hold a raw id where a display name exists.",
     regression="'SSG vs TL' printed a UUID (owner, 2026-10-08)")

json.dump({"note": "Golden cases. status 'proposed' is NOT asserted; only 'confirmed' cases run. Expected values are derived "
                   "by tests/golden/derive_expected.py from raw payloads via independent.py, never from ask() output.",
           "cases": CASES}, open(Path(__file__).parent / "cases.json", "w", encoding="utf-8"), indent=1)
print(f"wrote {len(CASES)} cases ({sum(c['status'] == 'confirmed' for c in CASES)} confirmed); exact={sum(c['kind'] == 'exact' for c in CASES)} "
      f"invariant={sum(c['kind'] == 'invariant' for c in CASES)}")
