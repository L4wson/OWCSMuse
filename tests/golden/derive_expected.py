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
# G45 (owner, 2026-10-08): "TF" is Team Falcons, overriding TFW
CONFIRMED |= {"G45"}
# G46+ (owner, 2026-10-08, second batch): GK region-qualified; attribution; display names; relative time
CONFIRMED |= {"G46", "G47", "G48", "G49", "G50", "G51", "G52", "G53", "G54"}

# G55+ (owner, 2026-10-09, Stage 4): the owner's own values for the international events, known independently of the
# data; each is also derived below from the captured Liquipedia records. Only those that need no pending identity
# decision are confirmed; G57 waits on Al Qadsiah, and G61 and G63 on the event series loading (load_matches).
CONFIRMED |= {"G55", "G56", "G58", "G59", "G60", "G62"}
# G57 and G63 are the owner's own values; they waited only on identity decisions, all made 2026-10-09. G61 (a Korean
# team's record) is the assistant's case and stays proposed for the owner's review.
CONFIRMED |= {"G57", "G63"}

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

# Since Stage 4 (owner, 2026-10-09) a record also counts the identity's Liquipedia-only event series in the captured
# records (tests/golden/liquipedia_events.json), by the name Liquipedia gives it there; every team at those events is
# decided. FACEIT and the events are disjoint series.
tm_faceit = I.team_record(S, tm, liquipedia_overrides=LP_OVERRIDES)
tm_events = I.event_record(["Twisted Minds"])
tm_all = I.plus(tm_faceit, tm_events)
tm26 = I.team_record(S, tm, season=2026, liquipedia_overrides=LP_OVERRIDES)
ssg_id = team_id("SpaceStation Gaming")
ssg_2024 = team_id("SpaceStation")
# The owner decided (2026-10-02) that the 2024 EMEA 'SpaceStation' team and the 2025+ NA 'SpaceStation Gaming' team
# are one organisation (scope/org_decisions.json, org spacestation-gaming), reversing the 2026-09-19 unmerge: the
# org's record is both team ids' series.
ssg_faceit = I.team_record(S, [ssg_id, ssg_2024])
ssg_na = I.team_record(S, [ssg_id])
assert ssg_faceit["regions"] == ["emea", "na"] and ssg_faceit["matches"] == ssg_na["matches"] + 2
ssg_events = I.event_record(["Spacestation Gaming"])
ssg = I.plus(ssg_faceit, ssg_events)


def team_row(rec, name):
    return {"team": name, "matches": rec["matches"], "wins": rec["wins"], "losses": rec["losses"],
            "map_wins": rec["map_wins"], "map_losses": rec["map_losses"], "maps": rec["maps"]}


case("G08", "Twisted Minds' record, all seasons, byes excluded", "exact", "Twisted Minds record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": tm[0], "name": "Twisted Minds"},
      "rows": [team_row(tm_all, "Twisted Minds")]},
     f"Series where Twisted Minds is a faction and the opponent is a real team: {tm_faceit['matches']} on FACEIT "
     f"(the golden set also holds a TM-vs-'bye' bracket slot, which is not a series and must not be counted), plus "
     f"{tm_events['matches']} at the 2025 World Finals ({tm_events['wins']}-{tm_events['losses']}, Liquipedia only): "
     f"{tm_all['matches']}. "
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
      "rows": [team_row(ssg, "SpaceStation Gaming")], "evidence": {"regions_only": ["emea", "international", "na"]}},
     f"{ssg_na['matches']} NA series of team {ssg_id[:8]} plus the two 2024 EMEA series of 'SpaceStation' (team "
     f"{ssg_2024[:8]}): the owner decided on 2026-10-02 that these are one organisation (SSG played EMEA in 2024 and became "
     f"an NA partner team in 2025), each team id mapped over its own era. Until then the two were held apart as a wrong "
     f"cross-region merge; the region check now carries this org as an owner-decided exception. Since Stage 4, also "
     f"its {ssg_events['matches']} 2025 World Finals series ({ssg_events['wins']}-{ssg_events['losses']}), Liquipedia's "
     f"'Spacestation Gaming' anchored to the org.",
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
tl = I.plus(I.team_record(S, [tl_id]), I.event_record(["Team Liquid"]))
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
     {"status": "ok", "entity": {"role": "subject", "type": "org", "id": "team-liquid", "name": "Team Liquid"},   # org since 2026-10-09
      "rows": [{"team": "Team Liquid", "matches": tl["matches"], "wins": tl["wins"], "losses": tl["losses"]}]},
     f"Team Liquid: {tl['matches']} series, its 2025 World Finals series included (Liquipedia's 'Team Liquid', "
     "anchored to the org team-liquid since 2026-10-09).", regression="alias")

# ----------------------------------------------------------------- clarify
# the NA team since Stage 4 also holds the 2025 World Finals series: 'geekay esports|international' gives the 2025
# events to the NA id (owner, 2026-10-09, from the qualifier)
r_na = I.plus(I.team_record(S, [gk_na]), I.event_record(["Geekay Esports"], season=2025))
r_em = I.team_record(S, [gk_em], liquipedia_overrides=LP_OVERRIDES)
case("G16", "Two teams named Geekay Esports ask, never guess", "invariant", "Geekay Esports record",
     {"status": "clarify", "code": "ambiguous_entity", "candidate_ids": sorted([gk_na, gk_em])},
     "Two unrelated teams share the name (NA and EMEA, 0% roster overlap, merge rejected in scope/org_decisions.json). "
     "The answer is a question back with exactly these two candidates.",
     regression="the wrong Geekay merge; clarify")
case("G17", "Clarify candidate (NA Geekay) answered verbatim", "exact", "Geekay Esports record",
     {"status": "clarify", "answer_candidate": {"id": gk_na, "expect": {
         "status": "ok", "entity": {"role": "subject", "id": gk_na},
         "rows": [team_row(r_na, "Geekay Esports")], "evidence": {"regions_only": ["international", "na"]}}}},
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
tm25_events = I.event_record(["Twisted Minds"], season=2025)
case("G25", "Twisted Minds in 2025: the bye is still not a series", "invariant", "Twisted Minds record in 2025",
     {"status": "ok", "rows": [team_row(I.plus(tm25, tm25_events), "Twisted Minds")]},
     "The only 2025 Twisted Minds fixture on FACEIT in the golden set is the bracket bye, which is not a series. Until "
     "Stage 4 the answer was no_data; since then the 2025 World Finals (Liquipedia only) gives Twisted Minds "
     f"{tm25_events['matches']} series in 2025 ({tm25_events['wins']}-{tm25_events['losses']}), and the record must be "
     f"exactly those {tm25_events['matches']}: the bye still not counted as a {tm25_events['matches'] + 1}th.",
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
     {"status": "ok", "entity": {"role": "team", "type": "org", "id": "dallas-fuel", "name": "Dallas Fuel"},   # org since 2026-10-09
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
     {"status": "ok", "entity": {"role": "opponent", "id": "team-liquid", "name": "Team Liquid"},   # org since 2026-10-09
      "sentence_contains": [f"{I.display_name(S, SUGF)} is {vw}-{vl} in maps against Team Liquid in 2026"]},
     f"sugarfree's 2026 maps against Team Liquid's team id: {len(vs_tl)} maps, {vw} won, {vl} lost. The parser once "
     "dropped 'team' as a stopword and searched 'liquid'.",
     regression="'Team' eaten as a keyword (README open list, owner 2026-10-08)")

case("G44", "An aliased team's answer prints its name, never its id", "invariant", "TL record in 2026",
     {"status": "ok", "entity": {"role": "subject", "name": "Team Liquid"}, "no_raw_ids": True},
     "Team Liquid is an unmapped team id, so its rows carry org_key 'team:<uuid>'; the CLI printed that column beside the "
     "name. Nothing a reader sees (sentence, reason, rendered answer) may hold a raw id where a display name exists.",
     regression="'SSG vs TL' printed a UUID (owner, 2026-10-08)")

FAL = "2ab92d33-4c33-46e1-a13f-743a95291d0e"
assert FAL in {s_.team[k] for s_ in S for k in s_.team if s_.name[k] == "Team Falcons"}
case("G45", "'TF' is Team Falcons by the owner's decision, not TFW", "invariant", "TF record",
     {"status": "ok", "entity": {"role": "subject", "type": "org", "id": "team-falcons", "name": "Team Falcons"},
      "sentence_contains": ["Team Falcons is"]},
     "Owner decision 2026-10-08 (scope/alias_decisions.json 'tf'): community usage gives TF to Team Falcons, the team id "
     "with its Dreamhack Dallas series. Before it, 'tf' reached the team TFW (0 series) by prefix. The collision is "
     "settled by usage, not evidence strength; TFW fitting the initials is no reason to undo it. Since the owner's "
     "Stage 4 decision (2026-10-09) the Dallas id belongs to the org team-falcons for its whole life, and the alias "
     "follows its team into the org: Team Falcons the org, not the bare team id.",
     regression="'TF' resolved to TFW (owner, 2026-10-08)")

GK_NA, GK_EMEA = team_id("Geekay Esports", "na"), team_id("Geekay Esports", "emea")
case("G46", "A bare 'GK' asks which Geekay: the alias is region-qualified", "invariant", "GK record",
     {"status": "clarify", "candidate_ids": [GK_NA, GK_EMEA],
      "answer_candidate": {"id": GK_NA, "expect": {"status": "ok", "entity": {"role": "subject", "id": GK_NA}}}},
     "Geekay Esports is two team ids, NA and EMEA. The owner's aliases are 'GK NA' and 'GK EMEA' (2026-10-08), so a bare "
     "'gk' prefix-matches both and must ask, never pick a region silently.",
     regression="one alias for a region-split name would pick a region (owner, 2026-10-08)")
case("G47", "'GK EMEA' is the EMEA Geekay", "invariant", "GK EMEA record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": GK_EMEA, "name": "Geekay Esports"}},
     "Owner alias 'GK EMEA' -> the EMEA Geekay team id (2026-10-08).",
     regression="one alias for a region-split name would pick a region (owner, 2026-10-08)")

# Liquipedia attribution. The page URL is the site plus the record's own page name (CC-BY-SA credit names the page).
def lp_page(match_id):
    return "https://liquipedia.net/overwatch/" + I.LIQUIPEDIA[match_id]["pagename"].replace(" ", "_")


case("G48", "A series record whose score came from Liquipedia credits the page", "invariant", "Toronto Defiant record",
     {"status": "ok", "attribution_pages": [lp_page(NA_FINAL)]},
     f"Toronto Defiant's grand final presents Liquipedia's {gf_for}-{gf_against} (FACEIT stores 5-0), and a linked series "
     "takes its score, result and best-of from Liquipedia (migration 034). Its maps and date are FACEIT's, so the old "
     "rule (credit only Liquipedia maps or dates) named no page: 397 of 445 linked series on production.",
     regression="a Liquipedia score carried no CC-BY-SA attribution (owner, 2026-10-08)")

lp24 = sorted({lp_page(x.match_id) for x in S if x.season == 2024 and x.counts_as_series and x.match_id in I.LIQUIPEDIA})
teams24 = {x.team[k] for x in S if x.season == 2024 and x.counts_as_series for k in x.team}
assert len(teams24) <= 10, "every 2024 team must be a shown row, so every linked 2024 series is behind the answer"
case("G49", "A leaderboard credits the pages behind every row, not only the expanded one", "invariant",
     "which team has the most wins in 2024",
     {"status": "ok", "attribution_pages": lp24},
     f"All {len(teams24)} 2024 teams are ranked rows, so every linked 2024 series is behind the answer: "
     + ", ".join(lp24) + ". Attribution once read only the evidence page of the expanded top row.",
     regression="attribution read one evidence page, not the answer (owner, 2026-10-08)")

icrimzo = pid("iCrimzo")
case("G50", "A team history dated by Liquipedia credits the page", "invariant", "what team is iCrimzo on",
     {"status": "ok", "attribution_pages": [lp_page(DALLAS)]},
     "iCrimzo's stint is dated by the Dreamhack Dallas series, which FACEIT left without a real time and Liquipedia "
     f"dates ({I.LIQUIPEDIA[DALLAS]['pagename']}). A team history once skipped attribution entirely.",
     regression="a team history carried no attribution (owner, 2026-10-08)")

assert pname(ZSS) == "ZZZ", "the owner's display name for z_ow / zss (player_identity_decisions.json)"
case("G51", "The name an answer shows is a name it can be asked by", "exact", "ZZZ record",
     {"status": "ok", "entity": {"role": "subject", "type": "player", "id": pid(ZSS), "name": "ZZZ"},
      "rows": [{**player_rows(zss, "ZZZ"), "eliminations": zss["eliminations"], "deaths": zss["deaths"]}]},
     f"G03's player asked by the owner's display name, which every answer shows: {zss['maps']} maps over "
     f"{zss['matches']} series. 'ZZZ' was searchable by nothing (035 left search untouched); 'zss' worked.",
     regression="a display name was shown but not searchable (owner, 2026-10-08)")

# Relative periods. A stage is every championship whose OWCS name (the owner's competition names, scope/) says
# "Stage N" in a season; the current one is the latest (season, N) with series, the last one the one before.
import re as _re  # noqa: E402
_names = json.loads((Path(__file__).parents[2] / "scope" / "competition_names.json").read_text(encoding="utf-8"))["decisions"]
def stage_of(champ_id):
    m = _re.search(r"\bStage (\d+)\b", (_names.get(champ_id) or {}).get("display_name") or "")
    return (CHAMPS[champ_id]["season"], int(m.group(1))) if m else None
stage_keys = sorted({stage_of(x.champ) for x in S if x.counts_as_series and stage_of(x.champ)})
this_stage, last_stage = stage_keys[-1], stage_keys[-2]
in_stage = lambda key: [x for x in S if x.counts_as_series and stage_of(x.champ) == key]  # noqa: E731
regions_of = lambda key: " and ".join(sorted({x.region.upper() for x in in_stage(key)}))  # noqa: E731

roles26 = collections.defaultdict(collections.Counter)
for x in S:
    if x.season == 2026:
        for rnd in x.rounds:
            for pl in rnd["players"]:
                if pl["stats"].get("Role"):
                    roles26[pl["player_id"]][pl["stats"]["Role"]] += 1
dm = collections.defaultdict(lambda: [0, 0])
for x in in_stage(this_stage):
    for rnd in x.rounds:
        for pl in rnd["players"]:
            c = roles26[pl["player_id"]]
            v = I.num(pl["stats"], "Damage Mitigated")
            if pl["stats"].get("Role") == "Tank" and c and c["Tank"] == max(c.values()) and v is not None:
                dm[pl["player_id"]][0] += v; dm[pl["player_id"]][1] += 1
dm_rank = sorted(((t, m, p_) for p_, (t, m) in dm.items()), key=lambda t: (-t[0], -t[1]))
assert len(dm_rank) > 1 and dm_rank[1][0] < dm_rank[0][0]
stage_note = f"read as OWCS {this_stage[0]} Stage {this_stage[1]} ({regions_of(this_stage)}), the most recent stage in scope"
case("G52", "'this stage' is the most recent stage in scope, and the answer says so", "exact",
     "which tanks have the most damage mitigated this stage",
     {"status": "ok", "rows": [{"nickname": I.display_name(S, dm_rank[0][2]), "total": int(dm_rank[0][0])}],
      "notes_contain": [stage_note]},
     f"The latest (season, stage) with series is {this_stage} ({len(in_stage(this_stage))} golden series, "
     f"{regions_of(this_stage)}). Damage Mitigated over its Tank maps by primary 2026 tanks: "
     f"{I.display_name(S, dm_rank[0][2])} {int(dm_rank[0][0])} over {dm_rank[0][1]} maps. It once returned 2024-2025 "
     "data: 'this stage' was stripped and ignored.",
     regression="'this stage' did not resolve (owner, 2026-10-08)")

latest_season = max(x.season for x in S if x.counts_as_series)
tm_now = I.team_record(S, [TM], season=latest_season)
case("G53", "'this year' is the most recent season in scope", "exact", "Twisted Minds record this year",
     {"status": "ok", "rows": [{"team": "Twisted Minds", "matches": tm_now["matches"], "wins": tm_now["wins"],
                                "losses": tm_now["losses"]}],
      "notes_contain": [f"read as the {latest_season} season, the most recent season in scope"]},
     f"The latest season with series is {latest_season}; Twisted Minds there: {tm_now['wins']}-{tm_now['losses']} over "
     f"{tm_now['matches']} series. 'this year' once answered across every season.",
     regression="'this year' did not resolve (owner, 2026-10-08)")

ssg_ids = {x.team[k] for x in S for k in x.team if x.name[k] in ("SpaceStation Gaming", "SpaceStation")}
ssg_last = I.team_record(in_stage(last_stage), ssg_ids)
assert ssg_last["matches"] > 0
case("G54", "'last stage' is the stage before the most recent", "exact", "SSG record last stage",
     {"status": "ok", "rows": [{"team": "SpaceStation Gaming", "matches": ssg_last["matches"], "wins": ssg_last["wins"],
                                "losses": ssg_last["losses"]}],
      "notes_contain": [f"read as OWCS {last_stage[0]} Stage {last_stage[1]} ({regions_of(last_stage)}), the stage before "
                        "the most recent in scope"]},
     f"Stages with series, in order: {stage_keys}; the one before the latest is {last_stage}. SpaceStation Gaming "
     f"(the org) there: {ssg_last['wins']}-{ssg_last['losses']} over {ssg_last['matches']} series.",
     regression="'last stage' did not resolve (owner, 2026-10-08)")

# ------------------------------------------------------------------- Stage 4: Liquipedia-only international events
WF25 = "Overwatch_Champions_Series/2025/World_Finals"
MSC25 = "Overwatch_Champions_Series/2025/Midseason_Championship"
CC25 = "Overwatch_Champions_Series/2025/Champions_Clash"
LP = "https://liquipedia.net/overwatch/"

wf_first, wf_second, wf_seventh = I.placed(WF25, 1), I.placed(WF25, 2), I.placed(WF25, 7)
assert wf_first == ["Twisted Minds"] and I.last_series_winner(WF25) == "Twisted Minds"          # the owner's value
case("G55", "Who won the 2025 World Finals", "exact", "who won the 2025 world finals",
     {"status": "ok", "rows": [{"team": "Twisted Minds", "placement": "1"}],
      "sentence_contains": ["Twisted Minds won OWCS 2025 World Finals"], "attribution_pages": [LP + WF25]},
     f"Liquipedia's prize pool for {WF25} places {wf_first} 1st, and the event's last series was won by "
     f"{I.last_series_winner(WF25)}. Owner's value: Twisted Minds won the 2025 World Finals.",
     regression="'who won the 2025 world finals' could not be answered (first beta tester, 2026-10-09)")

assert wf_second == ["Al Qadsiah"]
case("G56", "Al Qadsiah placed second at the 2025 World Finals", "exact", "who placed second at the 2025 world finals",
     {"status": "ok", "rows": [{"team": "Al Qadsiah", "placement": "2"}],
      "sentence_contains": ["Al Qadsiah placed 2nd at OWCS 2025 World Finals"]},
     f"The prize pool places {wf_second} 2nd. Owner's value: Al Qadsiah placed second. Liquipedia's name is shown as "
     "Liquipedia names it while the name has no identity decision.")

gf = I.event_series(WF25, "Twisted Minds", "Al Qadsiah")
assert gf[-1]["a"] == 4 and gf[-1]["b"] == 1                                                    # the owner's 4-1
case("G57", "Twisted Minds beat Al Qadsiah 4-1 in the 2025 World Finals grand final", "exact",
     "twisted minds series record against al qadsiah at the 2025 world finals",
     {"status": "ok", "rows": [{"matches": len(gf), "wins": sum(x["a"] > x["b"] for x in gf),
                                "losses": sum(x["a"] < x["b"] for x in gf)}]},
     f"The records hold {len(gf)} series between them at the event: " + "; ".join(f"{x['date']} {x['a']}-{x['b']}" for x in gf)
     + ". The grand final (the later) is Twisted Minds 4-1 (owner's value); the upper final went to Al Qadsiah 3-1. "
       "Proposed: Al Qadsiah has no identity decision, so the series between them reach no answer yet.")

assert wf_seventh == ["Spacestation Gaming", "Team Liquid"] and {I.placing_text(WF25, t) for t in wf_seventh} == {"7-8"}
case("G58", "SSG and Team Liquid shared 7th-8th at the 2025 World Finals", "exact", "who placed 7th at the 2025 world finals",
     {"status": "ok", "rows": [{"team": "SpaceStation Gaming", "placement": "7-8"}, {"team": "Team Liquid", "placement": "7-8"}],
      "sentence_contains": ["SpaceStation Gaming and Team Liquid placed 7th-8th at OWCS 2025 World Finals"]},
     f"The prize pool places {wf_seventh} at 7-8. Owner's value: SSG and Team Liquid both placed 7-8th. "
     "'Spacestation Gaming' is anchored to the org spacestation-gaming (scope/liquipedia_team_map.json), shown by its "
     "org name; Team Liquid is shown by Liquipedia's name while undecided.")

assert I.placed(MSC25, 1) == ["Team Falcons"] and I.last_series_winner(MSC25) == "Team Falcons"
case("G59", "Team Falcons won the 2025 Midseason Championship", "exact", "who won the 2025 midseason championship",
     {"status": "ok", "rows": [{"team": "Team Falcons", "placement": "1"}],
      "sentence_contains": ["Team Falcons won OWCS 2025 Midseason Championship"], "attribution_pages": [LP + MSC25]},
     f"The prize pool places {I.placed(MSC25, 1)} 1st; the grand final was won by {I.last_series_winner(MSC25)}. "
     "Owner's value: Team Falcons won the 2025 Midseason Championship.")

assert I.placed(CC25, 1) == ["Crazy Raccoon"] and I.last_series_winner(CC25) == "Crazy Raccoon"
case("G60", "Crazy Raccoon won the 2025 Champions Clash", "exact", "who won the 2025 champions clash",
     {"status": "ok", "rows": [{"team": "Crazy Raccoon", "placement": "1"}],
      "sentence_contains": ["Crazy Raccoon won OWCS 2025 Champions Clash"]},
     f"The prize pool places {I.placed(CC25, 1)} 1st; the grand final was won by {I.last_series_winner(CC25)}. "
     "Owner's value: Crazy Raccoon won the 2025 Champions Clash. Was a known bug until the owner's decision of "
     "2026-10-09 (one continuous org, Dallas included): the name had resolved to the Dallas FACEIT id, whose name "
     "is 'Crazy Raccoons'.")

t1 = I.team_series_record(WF25, "T1")
case("G61", "A Korean team's record at an international event", "exact", "T1 record at the 2025 world finals",
     {"status": "ok", "rows": [{"matches": t1["matches"], "wins": t1["wins"], "losses": t1["losses"]}],
      "attribution_pages": [LP + WF25]},
     f"T1's series at {WF25} in the records: {t1['wins']}-{t1['losses']} over {t1['matches']}. T1 has no FACEIT "
     "counterpart; proposed until the owner decides it as a Liquipedia-only org.")

case("G62", "A player-stat question about a results-only event refuses, and says what works", "invariant",
     "most eliminations at the 2025 world finals",
     {"status": "cannot_answer", "code": "results_only",
      "alternative": {"question_template": "2025 world finals standings", "seasons_with_stat": [None],
                      "then_rows": [{"team": "Twisted Minds", "placement": "1"}, {"team": "Al Qadsiah", "placement": "2"}]}},
     "OWCS 2025 World Finals is Liquipedia-only: no source records player stats there, so the answer is the "
     "results_only refusal, not an empty leaderboard and not 'not recorded for 2025', and the alternative it offers "
     f"(the event's standings) answers, led by the prize pool's {wf_first} and {wf_second}.")

cr_dallas = [x for x in S if x.match_id == "1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b"]
assert len(cr_dallas) == 1
cr_lp = [I.team_series_record(p, "Crazy Raccoon") for p in (WF25, CC25)]
cr_total = {k: 1 + sum(r[k] for r in cr_lp) if k == "matches" else sum(r[k] for r in cr_lp) for k in ("matches", "wins", "losses")}
cr_total["wins"] += 1          # Dallas grand final: Crazy Raccoons 4-2 Team Falcons
case("G63", "A cross-source team counted once across FACEIT and Liquipedia", "exact", "crazy raccoons record",
     {"status": "ok", "rows": [cr_total]},
     f"Crazy Raccoon: the Dallas grand final on FACEIT (won 4-2) plus its Liquipedia-only series in the captured "
     f"records ({WF25}: {cr_lp[0]}, {CC25}: {cr_lp[1]}), each once: {cr_total}. Proposed: the count depends on the "
     "owner's held decision (an org spanning Dallas and the later events counts all of them; a window ending after "
     "Dallas leaves the later ones undecided).")

# ----------------------------------------------- Liquipedia-only series at map grain (041) and how people ask who won
# (owner, 2026-10-09). The winners are the owner's values; each is also the captured prize pool's first place.
CONFIRMED |= {f"G{n}" for n in range(64, 82)}

tm_aq = I.event_maps("Twisted Minds", "Al Qadsiah", WF25)
case("G64", "A Liquipedia-only event answers at map grain", "exact",
     "Twisted Minds vs Al Qadsiah at the 2025 world finals",
     {"status": "ok", "rows": [{"maps": tm_aq["maps"], "map_wins": tm_aq["map_wins"], "map_losses": tm_aq["map_losses"]}],
      "attribution_pages": [LP + WF25]},
     f"Liquipedia's games for their {tm_aq['series']} series at {WF25}: {tm_aq['map_wins']}-{tm_aq['map_losses']} over "
     f"{tm_aq['maps']} maps. Before 041 the map grain read FACEIT rounds only and refused 'no map stats on FACEIT'.",
     regression="map grain ignored Liquipedia-only series: 95 pairings refused, 15 silently incomplete (2026-10-09)")

cr_tf = I.event_maps("Crazy Raccoon", "Team Falcons")
case("G65", "A pairing with Liquipedia-only and map-less series counts every map and says what it left out", "exact",
     "Crazy Raccoon vs Team Falcons",
     {"status": "ok", "rows": [{"maps": cr_tf["maps"], "map_wins": cr_tf["map_wins"], "map_losses": cr_tf["map_losses"]}],
      "notes_contain": ["have no map results from any source"]},
     f"Every captured Liquipedia game between them ({cr_tf['series']} series): {cr_tf['map_wins']}-{cr_tf['map_losses']} "
     f"over {cr_tf['maps']} maps. The Dreamhack Dallas final (FACEIT result_only, no Liquipedia record in this set) has "
     "no map results from any source: excluded, and said so. Before 041 the answer counted only map rows and said "
     "nothing of the Liquipedia series it left out.",
     regression="map grain silently incomplete for 15 pairings (2026-10-09)")

case("G66", "No map results from any source: the refusal says that, not 'no map stats on FACEIT'", "invariant",
     "Crazy Raccoon vs Team Falcons in 2024",
     {"status": "cannot_answer", "code": "no_data",
      "sentence_contains": ["none of those series has map results from any source"]},
     "In 2024 the only series between them is the Dreamhack Dallas final, FACEIT result_only with no Liquipedia "
     "record in this set: no source has its maps. FACEIT having none is no longer the same as no source having any.")

placement_phrasings = [
    ("G67", "who won the 2025 finals", "Twisted Minds", "OWCS 2025 World Finals", WF25, None),
    ("G68", "who was the 2025 champion", "Twisted Minds", "OWCS 2025 World Finals", WF25,
     '"champion" with no event named read as the world champion'),
    ("G69", "2025 world champion", "Twisted Minds", "OWCS 2025 World Finals", WF25,
     '"champion" with no event named read as the world champion'),
    ("G70", "who won worlds in 2025", "Twisted Minds", "OWCS 2025 World Finals", WF25, None),
    ("G71", "2025 world finals winner", "Twisted Minds", "OWCS 2025 World Finals", WF25, None),
    ("G72", "who was the 2025 midseason champion", "Team Falcons", "OWCS 2025 Midseason Championship", MSC25, None),
    ("G73", "who won msc 2025", "Team Falcons", "OWCS 2025 Midseason Championship", MSC25, None),
    ("G74", "2025 midseason winner", "Team Falcons", "OWCS 2025 Midseason Championship", MSC25, None),
    ("G75", "who won the 2025 mid-season championship", "Team Falcons", "OWCS 2025 Midseason Championship", MSC25, None),
    ("G76", "2025 champions clash winner", "Crazy Raccoon", "OWCS 2025 Champions Clash", CC25, None),
    ("G77", "who was the champion of the 2025 champions clash", "Crazy Raccoon", "OWCS 2025 Champions Clash", CC25, None),
]
for gid, question, winner, event, page, note in placement_phrasings:
    assert I.placed(page, 1) == [winner if winner != "Crazy Raccoon" else "Crazy Raccoon"], (page, I.placed(page, 1))
    expect = {"status": "ok", "rows": [{"team": winner, "placement": "1"}], "sentence_contains": [f"{winner} won {event}"]}
    if note:
        expect["notes_contain"] = [note]
    case(gid, f"'{question}' is the {event} winner", "exact", question, expect,
         f"The prize pool for {page} places {I.placed(page, 1)} 1st. Owner's value: {winner}."
         + (" No event named: a champion reads as the world champion, and the answer says so." if note else ""),
         regression="natural phrasings of who won returned nothing on production (2026-10-09)")

wf_wins = sorted(((I.team_series_record(WF25, t)["wins"], t) for t in
                  {o["name"] for m in I.load_events()["matches"] if m["pagename"] == WF25 for o in m["match2opponents"]}),
                 key=lambda x: (-x[0], x[1]))
case("G78", "'who won the most series at ...' stays a leaderboard, not the event's winner", "exact",
     "who won the most series at the 2025 world finals",
     {"status": "ok", "rows": [{"wins": wf_wins[0][0]}]},
     f"Series wins at {WF25} from the records: the most is {wf_wins[0][0]} ({[t for w, t in wf_wins if w == wf_wins[0][0]]}).")

case("G79", "'clash' alone is still the Clash mode, not the Champions Clash", "invariant",
     "Twisted Minds record on clash maps",
     {"status": "cannot_answer", "code": "no_data", "sentence_contains": ["game mode 'Clash'"],
      "sentence_lacks": ["Champions Clash"]},
     "Only 'champions clash' names the event; the game mode keeps its word. The golden set holds no Clash map, so the "
     "answer is the mode's own no-data refusal - which is the proof it was read as the mode.")

case("G80", "'champions clash' is the event even with 'champion' in it", "exact",
     "champions clash 2025 standings",
     {"status": "ok", "rows": [{"team": "Crazy Raccoon", "placement": "1"}], "sentence_lacks": ["world champion"]},
     f"The 2025 Champions Clash prize pool, led by {I.placed(CC25, 1)}; 'champions' inside the event's name is not a champion.")

case("G81", "A bare 'finals' with a stage word stays that stage", "invariant",
     "who won the 2026 NA stage 2 finals",
     {"status": "cannot_answer", "sentence_lacks": ["World Finals"]},
     "'NA Stage 2 finals' is the stage's own final, not the World Finals; the stages have no prize-pool placings here.")

# ------------------------------------------------------- every versus combination, both grains (owner, 2026-10-10)
CONFIRMED |= {f"G{n}" for n in range(82, 88)}
CJ, SG = pid("cjay4"), pid(SUG)
DF_IDS, SSG_IDS = {team_id("Dallas Fuel")}, {x.team[k] for x in S for k in x.team if x.name[k] in ("SpaceStation Gaming", "SpaceStation")}

pvp = I.opposed_record(S, ("player", {CJ}), ("player", {SG}))
assert pvp["matches"] == 4
case("G82", "A player's series record against a player: the series they were on opposite sides of", "exact",
     f"{pname('cjay4')} series record against {pname(SUG)}",
     {"status": "ok", "rows": [{"matches": pvp["matches"], "wins": pvp["wins"], "losses": pvp["losses"]}],
      "notes_contain": ["Players do not win series, their teams do"],
      "other_grain": f"{pname('cjay4')} map record against {pname(SUG)}"},
     f"Series with {pname('cjay4')} on one declared line-up and {pname(SUG)} on the other: {pvp['matches']} "
     f"({', '.join(m[:10] for m in pvp['match_ids'])}), {pvp['wins']}-{pvp['losses']} from {pname('cjay4')}'s side. "
     "Before: 'head-to-head needs two resolved teams'.",
     regression="series-grain player v player demanded two teams (2026-10-10)")

pvo = I.opposed_record(S, ("player", {SG}), ("team", DF_IDS))
case("G83", "A player's series record against an org", "exact", f"{pname(SUG)} series record against Dallas Fuel",
     {"status": "ok", "rows": [{"matches": pvo["matches"], "wins": pvo["wins"], "losses": pvo["losses"]}],
      "other_grain": f"{pname(SUG)} map record against Dallas Fuel"},
     f"Series with {pname(SUG)} on one line-up and Dallas Fuel on the other side: {pvo['matches']}, "
     f"{pvo['wins']}-{pvo['losses']} from his team's side.",
     regression="series-grain player v org demanded two teams (2026-10-10)")

ovp = I.opposed_record(S, ("team", DF_IDS), ("player", {SG}))
assert (ovp["wins"], ovp["losses"]) == (pvo["losses"], pvo["wins"])
case("G84", "An org's series record against a player", "exact", f"Dallas Fuel series record against {pname(SUG)}",
     {"status": "ok", "rows": [{"matches": ovp["matches"], "wins": ovp["wins"], "losses": ovp["losses"]}],
      "other_grain": f"Dallas Fuel map record against {pname(SUG)}"},
     f"The same {ovp['matches']} series from Dallas Fuel's side: {ovp['wins']}-{ovp['losses']}. Before: 'Dallas Fuel has no "
     "series' (the player was keyed as an org).",
     regression="series-grain org v player answered no data (2026-10-10)")

tmp = I.team_maps_against_player(S, DF_IDS, SG)
case("G85", "An org's map record against a player is the org's, not the player's", "exact",
     f"Dallas Fuel map record against {pname(SUG)}",
     {"status": "ok", "rows": [{"maps": tmp["maps"], "map_wins": tmp["map_wins"], "map_losses": tmp["map_losses"]}],
      "other_grain": f"Dallas Fuel series record against {pname(SUG)}"},
     f"Rounds {pname(SUG)} played against Dallas Fuel: {tmp['maps']}, Dallas Fuel won {tmp['map_wins']}, lost "
     f"{tmp['map_losses']}. The answer read the player's own rows unflipped and gave his record as the org's.",
     regression="org v player map record presented the player's wins as the org's (2026-10-10)")

own = I.same_side_series(S, ("player", {SG}), ("team", SSG_IDS), season=2026)
assert own > 0 and I.opposed_record(S, ("player", {SG}), ("team", SSG_IDS), season=2026)["matches"] == 0
case("G86", "A player against his own team is refused as that, not as 'they met'", "invariant",
     f"{pname(SUG)} map record against SpaceStation Gaming in 2026",
     {"status": "cannot_answer", "code": "no_data",
      "sentence_contains": [f"played for SpaceStation Gaming in 2026 ({own} series), never against them"]},
     f"In 2026 {pname(SUG)} was on SpaceStation Gaming's line-up in {own} series and never opposite it. The note "
     "once counted any series both appeared in, his own team's among them ('they did meet').",
     regression="a player and his own team were said to have met (2026-10-10)")

h2h = I.opposed_record(S, ("team", SSG_IDS), ("team", DF_IDS))
case("G87", "An org v org series record's evidence holds every series behind it", "exact",
     "SpaceStation Gaming series record against Dallas Fuel",
     {"status": "ok", "rows": [{"matches": h2h["matches"], "wins": h2h["wins"], "losses": h2h["losses"]}],
      "evidence": {"total_rows": h2h["matches"]},
      "other_grain": "SpaceStation Gaming map record against Dallas Fuel"},
     f"SpaceStation Gaming (both team ids, one org) v Dallas Fuel: {h2h['matches']} series, {h2h['wins']}-{h2h['losses']}. "
     "The evidence filtered raw team ids, so with an org on either side the record answered and its evidence was empty.",
     regression="head-to-head evidence empty for an org (2026-10-10)")

json.dump({"note": "Golden cases. status 'proposed' is NOT asserted; only 'confirmed' cases run. Expected values are derived "
                   "by tests/golden/derive_expected.py from raw payloads via independent.py, never from ask() output.",
           "cases": CASES}, open(Path(__file__).parent / "cases.json", "w", encoding="utf-8"), indent=1)
print(f"wrote {len(CASES)} cases ({sum(c['status'] == 'confirmed' for c in CASES)} confirmed); exact={sum(c['kind'] == 'exact' for c in CASES)} "
      f"invariant={sum(c['kind'] == 'invariant' for c in CASES)}")
