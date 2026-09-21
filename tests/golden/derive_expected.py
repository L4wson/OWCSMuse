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
tm_all = I.team_record(S, tm)
tm26 = I.team_record(S, tm, season=2026)
ssg_id = team_id("SpaceStation Gaming")
ssg = I.team_record(S, [ssg_id])
assert ssg["regions"] == ["na"]


def team_row(rec, name):
    return {"team": name, "matches": rec["matches"], "wins": rec["wins"], "losses": rec["losses"],
            "map_wins": rec["map_wins"], "map_losses": rec["map_losses"], "maps": rec["maps"]}


case("G08", "Twisted Minds' record, all seasons, byes excluded", "exact", "Twisted Minds record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": tm[0], "name": "Twisted Minds"},
      "rows": [team_row(tm_all, "Twisted Minds")]},
     f"Series where Twisted Minds is a faction and the opponent is a real team: {tm_all['matches']} "
     f"(the golden set also holds a TM-vs-'bye' bracket slot, which is not a series and must not be counted as a 5th). "
     f"map_wins/losses are series scores; 'maps' counts rounds that have stats, {tm_all['maps']}; "
     f"{tm_all['result_only_series']} of the series has no stats payload.",
     regression="bye: a bracket bye counted as a 1-0 win")

case("G09", "Twisted Minds 2026, with a series that has no map stats", "exact", "Twisted Minds record in 2026",
     {"status": "ok", "rows": [team_row(tm26, "Twisted Minds")], "limitations": ["offline_map_stats", "main_series_2025_2026"]},
     f"{tm26['matches']} series in 2026, one of them ({tm26['result_only_series']}) with no stats payload: it counts at series "
     "grain (wins and map_wins/losses from the series score) and contributes no rows to 'maps'. The answer must say so via "
     "the offline_map_stats limitation.", regression="result-only series counted at series grain only")

case("G10", "SpaceStation Gaming's record (NA only)", "exact", "SpaceStation Gaming record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": ssg_id, "name": "SpaceStation Gaming"},
      "rows": [team_row(ssg, "SpaceStation Gaming")], "evidence": {"regions_only": ["na"]}},
     f"{ssg['matches']} NA series. The golden set also holds two 2024 EMEA series of 'SpaceStation' (team "
     f"{team_id('SpaceStation')[:8]}), which are a different team and must not be added.",
     regression="region bug: SpaceStation Gaming merged with the EMEA SpaceStation")

h2h = I.team_record(S, tm, opponent_ids=[team_id("Ex Oblivione")])
case("G11", "Twisted Minds vs Ex Oblivione, series grain", "exact", "Twisted Minds series record against Ex Oblivione",
     {"status": "ok", "rows": [{"matches": h2h["matches"], "wins": h2h["wins"], "losses": h2h["losses"]}]},
     f"{h2h['matches']} series between the two team ids in the golden set (both 3-1 to Twisted Minds). Team id bb5dd404 was "
     "'Ex Oblivione' in 2024 and was later acquired into Virtus pro. The name must be searchable and find those 2024 "
     "series, which are Ex Oblivione's, not Virtus pro's.",
     known_bug="'Ex Oblivione' matches nothing: an org's searchable history holds each team id's current name only, "
               "not its earlier ones (team_names), so the name is unsearchable. Its search must work, but a search hit must "
               "not put its pre-rename series into Virtus pro's record: that needs date-bounded team-to-org mapping (Stage 3)")

# ----------------------------------------------------------------- resolution
dsg_id = team_id("Disguised")
dsg = I.team_record(S, [dsg_id])
vp_ids = [team_id("Virtus pro"), team_id("Virtuspro")]
vp = I.team_record(S, vp_ids, exclude_names={"Ex Oblivione"})
tl_id = team_id("Team Liquid")
tl = I.team_record(S, [tl_id])
case("G12", "'SSG' resolves to SpaceStation Gaming", "exact", "SSG record",
     {"status": "ok", "entity": {"role": "subject", "type": "team", "id": ssg_id, "name": "SpaceStation Gaming"},
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
     regression="alias/org: VP resolves to the merged Virtus pro org",
     known_bug="team-to-org mapping is not date-bounded: bb5dd404 maps to Virtus pro for all time, so the org's record "
               "includes 3 series from its Ex Oblivione era (5 series, not 2). Fix is date-bounded team-to-org mapping "
               "(Stage 3); the alias half of this case is G26")

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
gk_na, gk_em = team_id("Geekay Esports", "na"), team_id("Geekay Esports", "emea")
r_na, r_em = I.team_record(S, [gk_na]), I.team_record(S, [gk_em])
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
     f"The EMEA candidate: {r_em['matches']} series ({r_em['wins']}-{r_em['losses']}), one with no stats payload.",
     regression="clarify: a candidate must be answerable verbatim")

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

tm25 = I.team_record(S, tm, season=2025)
assert tm25["matches"] == 0
case("G25", "Twisted Minds in 2025: only a bye, so no data", "invariant", "Twisted Minds record in 2025",
     {"status": "cannot_answer", "code": "no_data",
      "alternative": {"question_template": "Twisted Minds record", "seasons_with_stat": [None],
                      "top1_by_season": {}, "then_rows": [team_row(tm_all, "Twisted Minds")]}},
     "The only 2025 Twisted Minds fixture is the bracket bye, which is not a series: the answer is no_data, not '1-0'. "
     "The offered alternative (the all-seasons record) must answer with G08's numbers.",
     regression="bye: a 2025 bye showed as a 1-0 win")

json.dump({"note": "Golden cases. status 'proposed' is NOT asserted; only 'confirmed' cases run. Expected values are derived "
                   "by tests/golden/derive_expected.py from raw payloads via independent.py, never from ask() output.",
           "cases": CASES}, open(Path(__file__).parent / "cases.json", "w", encoding="utf-8"), indent=1)
print(f"wrote {len(CASES)} cases ({sum(c['status'] == 'confirmed' for c in CASES)} confirmed); exact={sum(c['kind'] == 'exact' for c in CASES)} "
      f"invariant={sum(c['kind'] == 'invariant' for c in CASES)}")
