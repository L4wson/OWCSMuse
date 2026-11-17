# OWCS Grid: clue types, checked against the data

Checked 2026-11-17 on branch `grid/categories`, from read-only queries against production (last series in the
warehouse: 2026-11-01). Every count is what `scripts/grid/clues.py` returns on that data. Rerun before quoting one.

Default scope for every clue, unless its text says otherwise: **OWCS NA and EMEA main series (stages and playoffs),
from FACEIT map stats.** Relegation and international events are not counted. "A map" always means a map with
player stats on record: 344 players have at least one. There are no map stats for 2024 Stages 3-4, 2026 Stage 3,
or a number of playoff finals, and that gap is behind almost every "can't verify" below.

"Can't verify" in the tables is the number of players the clue cannot judge because the deciding data is missing.
They cost no guess. A player the clue plainly fails is "wrong", not "can't verify".

## Verdicts

| # | Clue type | Verdict | In the 30 puzzles | The short reason |
|---|---|---|---|---|
| 1 | Teammate of <player> | **Ship** | 45 uses, 33 anchors | Exact from map data; 47 anchors have 12+ teammates |
| 2 | Played for <org> | **Ship with limits** | 23 uses, 9 orgs | Mapped orgs only: 14 qualify. The best-known teams are unmapped |
| 3 | Won an OWCS stage | **Ship** | 22 uses, with 4 | All 20 winners agree across every record held; 6 stages have no playoff map data |
| 4 | Reached a stage grand final | **Ship** | (counted with 3) | Same |
| 5 | Won an award | **Ship with limits, after review** | 0 | 21 awards found and written, none reviewed, so none used; 12 players, usable only beside broad clues |
| 6 | Rostered at an international LAN | **Ship** | 29 uses | Liquipedia line-ups; labelled "Rostered at"; Dallas excluded |
| 7 | Played in both NA and EMEA | **Ship with limits** | 3 uses | 13 answers: it fits only beside broad clues |
| 8 | Played for 3+ orgs | **Not yet** | 0 | 15 answers and 283 can't-verify until teams are mapped |
| 9 | Experience (N+ maps) | **Ship** | 15 uses | 50 to 150+ work; 200+ has 4 answers |
| 10 | Stats (top 25% per 10, by role) | **Ship with limits** | 17 uses | 2025 and 2026 only; 2026 is thin (15 answers) |
| 11 | Hero specialist | **Not yet** | 0 | FACEIT's map stats have no hero field |
| 12 | Role, season, region, all 3 seasons | **Keep** | 29 uses | From the beta; now also usable beside any other clue |

Implemented and tested but not in any puzzle: awards (5), which enter the pool as entries are reviewed, and org
count (8), which is left out of the pool.

## 1. Teammate of <player>: Ship

**Definition.** Played 1+ map on the same team as the named player. Two players share a map when FACEIT's map
stats have both on the same match, the same map number and the same team identity at that time. The anchor is
never an answer.

**Data.** `fact_player_maps` only. No new data, no review file. It is symmetric by construction and correct across
a mid-stage roster change: a player who left before another joined shares no map with them.

**Coverage and can't-verify.** A player in the anchor's line-up for a series with no map stats, and with no map
together anywhere, is "can't verify": they may have played together or one may have sat out. 0 to 14 players per
anchor.

**Anchors.** The 60 players with the most maps were tried; 47 have 12 or more teammates and are in the pool.

| Example | Answers | Can't verify |
|---|---|---|
| Teammate of Tred | 27 | 1 |
| Teammate of zeruhh | 23 | 3 |
| Teammate of Kronik | 20 | 6 |
| Teammate of sugarfree | 17 | 2 |
| Teammate of FunnyAstro | 12 | 0 |

**Limits.** The pools are small (12 to 27), so a teammate clue sits beside broad clues. Two teammate clues in one
cell rarely reach 3 answers. An anchor is not reused within 14 days; 30 days of puzzles used 33 of the 47.

## 2. Played for <org>: Ship with limits

**Definition.** Played 1+ map for the organisation, where the organisation is Muse's reviewed org at the time of
each map (`team_identity_at`). A reused FACEIT team id therefore never links two orgs.

**Data.** Only orgs that are already mapped. `OrgClue` refuses a `team:<id>` key outright. 14 mapped orgs have 8
or more players with maps:

| Org | Answers | Can't verify |
|---|---|---|
| SpaceStation Gaming | 19 | 3 |
| Quick Esports | 18 | 4 |
| Team Peps | 18 | 5 |
| Al Qadsiah | 16 | 3 |
| NTMR | 15 | 3 |
| Extinction | 14 | 1 |
| Sheer Cold | 12 | 0 |
| Team Liquid, Gen.G Esports, Vision Esports, Dhillducks | 11 each | 0 to 1 |
| Virtus pro, Sakura | 9 each | 4, 0 |
| Ataraxia | 8 | 0 |

**Can't-verify.** A player in the org's line-up only in series with no map stats (a 2024 Stage 3-4 or 2026 Stage 3
roster).

**Limits.** Twisted Minds (15 players), Shikigami (12), Citrus Nation (10), M80, The Ultimates, Timeless, Toronto
Defiant and ENCE are unmapped, so they cannot be clues. `proposed_org_mappings.md` has a proposal for each of the
49 unmapped team ids, with evidence and a confidence level. **Nothing in it is applied.** Several mapped orgs that
qualify are obscure (Sheer Cold, Dhillducks); the 30 puzzles used 9 of the 14.

## 3 and 4. Won an OWCS stage / Reached a stage grand final: Ship

**Definition.** Played 1+ playoff map for the team that won a stage's playoffs (3), or for either team in its
grand final (4). Variants: any stage, an NA stage, an EMEA stage.

**Data.** Stage results are not a column in Muse, so they are derived once into `scope/grid_stages.json` by
`scripts/grid/build_facts.py`, with a Liquipedia source link on every entry. A stage's grand final is the last
series of its playoff bracket.

**Cross-check.** Every one of the 20 stages (2024 Stages 1-4, 2025 Stages 1-3, 2026 Stages 1-3, NA and EMEA)
agrees across every record held:

| Record | Stages it covers | Agrees |
|---|---|---|
| Liquipedia's own match record of the final, and that it is the bracket's last match | 20 | 20 |
| FACEIT's result for the same series | 12 | 12 |
| Liquipedia's placement table (1st and 2nd) | 10 | 10 |

The placement tables were already stored for the six 2025 stages and 2026 Stages 1-2. The other ten were **not
fetched**: Muse's Liquipedia client stores every response in the database, and this session could not write there.
For 2024 Stages 3-4 and 2026 Stage 3 the only record is Liquipedia's match record. All 20 are listed in
`VERIFY.md` for review.

**Coverage and can't-verify.** A player counts only with a playoff map on record. Playoff map stats exist for 14
of the 20 stages (fully for 6, partly for 8) and for none of 2024 Stages 3-4 or 2026 Stage 3. A player on a
winner's playoff roster with no map on record is "can't verify".

| Example | Answers | Can't verify |
|---|---|---|
| Won an OWCS stage | 41 | 3 |
| Stage grand finalist | 61 | 19 |
| Won an NA stage | 18 | 0 |
| Won an EMEA stage | 23 | 4 |
| NA / EMEA stage finalist | 31 / 30 | 8 / 12 |

**Limits.** Toronto Defiant won four NA stages in 2024, but only two have map data, so its Stage 3-4-only players
are "can't verify". A stage's winner is an identity, which for Twisted Minds, Toronto Defiant and ENCE is an
unmapped team id; the clue never names the team, so that does not block it.

## 5. Won an award: Ship with limits, after review

**What exists.** Liquipedia's API does return awards: they are the individual rows of each event's prize pool, in
`/placement` responses Muse had already stored (Muse's own placements parser leaves them out). 21 rows: MVPs and
role MVPs at EWC 2024, both World Finals, Champions Clash 2025 and both Midseason Championships, and a "Super Star"
for each of the four 2025 Stage 1-2 regional stages.

**What was done.** `scope/grid_awards.json` holds all 21, each with the player id (where resolved), award, event,
date, source URL and `"reviewed": false`. The generator uses reviewed entries only; `--include-unreviewed` exists
for dry runs and is refused otherwise.

**Why it is in no puzzle.** None is reviewed, and that is the rule. It is otherwise ready: a 7-day dry run with
unreviewed awards allowed chose the clue once, as a row beside an international roster, a stats clue and a team,
with cells of 9, 3 and 3 answers.

**Limits once reviewed.**

- 3 of the 21 (all Proper) did not resolve to a player id and cannot be used until one is filled in.
- 12 distinct players, 7 of them with any NA/EMEA map data. It reaches 3 answers only beside a broad clue, and
  those cells are thin.
- Regional awards were only in the responses for four stages. Awards for other stages, if any, were not fetched.

## 6. Rostered at an international LAN: Ship

**Definition.** On a team's roster at the named international event, per Liquipedia's line-ups. The label says
"Rostered at", and the definition says "not necessarily played", because a Liquipedia line-up lists a roster.

**Data.** `series_lineups` for the seven international events Muse holds from Liquipedia, through reviewed player
identities. Dreamhack Dallas 2024 is excluded: its line-ups hold 4 players a series.

| Example | Answers | Of those, with NA/EMEA map data |
|---|---|---|
| Rostered at an international LAN | 162 | not measured |
| Esports World Cup 2024 | 89 | 53 |
| 2025 Midseason Championship | 90 | 40 |
| 2026 Midseason Championship | 84 | 40 |
| 2025 World Finals | 65 | 34 |
| 2024 World Finals / 2025 Champions Clash / 2026 Champions Clash | 41 / 43 / 44 | 31 / 21 / 24 |

**Can't-verify.** None for a named event. For "an international LAN", the 6 players seen only at Dallas.

**Limits.** This clue's answers include Korean, Chinese and other players who have no data for any map-based clue,
so beside one they are simply wrong, and a cell's real pool is the right-hand column. 12 Liquipedia player pages
are still undecided in Muse and are in no line-up.

## 7. Played in both NA and EMEA: Ship with limits

**Definition.** 1+ map in an OWCS NA competition and 1+ in an EMEA one.

**Counts.** 13 answers, 9 can't-verify (line-ups in both regions, maps missing in one). It passed the rules in 3
of the 30 puzzles, always beside broad clues. It is a good hard clue and a poor default one.

## 8. Played for 3+ orgs: Not yet

**Counts.** 15 answers (57 for 2+, 3 for 4+) and **283 can't-verify**. A player with any stint on an unmapped team
could have one more org than counted, and 49 team ids are unmapped, so most of the player base cannot be judged.
A clue where four guesses in five come back "can't verify" is not a clue.

Implemented and tested (`OrgCountClue`); not in the pool. It becomes usable as the proposals in
`proposed_org_mappings.md` are reviewed.

## 9. Experience: Ship

**Definition.** N or more maps in OWCS NA/EMEA main series, 2024-2026.

| Example | Answers | Can't verify |
|---|---|---|
| 50+ OWCS maps | 85 | 99 |
| 100+ OWCS maps | 46 | 65 |
| 150+ OWCS maps | 25 | 45 |
| 200+ OWCS maps | 4 | 52 |

The pool uses 50, 75, 100, 125 and 150. 200+ has four answers (cjay, Landon, sugarfree, UltraViolet) and is left
out.

**Can't-verify.** A player under N on record who was in line-ups for series with no map stats, when those series
could take them past N at 7 maps each (the most a best-of-7 holds). That bound is loose on purpose: the real map
count of an unrecorded series is known to Muse but not loaded here, so the clue assumes the most it could be. A
tighter bound is a small follow-up.

## 10. Stats: Ship with limits

**Definition.** In the top 25% for their role in a per-10-minute stat for a season, with 20+ maps in that role
that season. "Their role" means each role is ranked separately and the clue is the union. The rate is total stat
over total time played, never an average of per-map rates. The label says "NA/EMEA".

**Stats offered.** Eliminations, damage, and fewest deaths (the lowest quarter). All three have full coverage in
2025 and 2026 Stages 1-2. Healing and mitigation were left out: ranked "for their role" they are near zero for
two of the three roles and read oddly.

| Season | Eligible (Tank / DPS / Support) | Answers | Can't verify |
|---|---|---|---|
| 2025 | 28 / 50 / 48 | 32 (7 / 13 / 12) | 8 |
| 2026 | 10 / 22 / 23 | 15 (3 / 6 / 6) | 29 |

**Limits.** No 2024: FACEIT recorded no time played that year, and the clue refuses it. 2026 is thin (3 Tanks),
because Stage 3 has no map stats; the 29 can't-verify are players with under 20 maps on record and Stage 3 series
unrecorded. Patch is not recorded anywhere, so a season is the finest comparable period.

## 11. Hero specialist: Not yet

FACEIT's per-player map stats carry 47 keys in 2026 (eliminations, damage, healing, per-10 rates, role, result,
time played). **None is a hero.** Liquipedia records hero bans per map, not picks. No source holds which hero a
player played, so the clue cannot be built. Nothing was implemented.

## 12. Role, season, region, all 3 seasons: Keep

Unchanged in meaning from the beta, with one addition: each can now sit beside any other clue.

- A role beside a season or a region is still **that role in that season or region**: 10+ maps, on the same maps.
- A role beside anything else is 10+ maps in the role over the whole scope.
- A season or region beside a non-role clue is 1+ map there.

| Clue | Answers | Can't verify |
|---|---|---|
| Tank / DPS / Support | 53 / 94 / 95 | 167 each |
| Played in 2024 / 2025 / 2026 | 268 / 151 / 78 | 115 / 1 / 10 |
| Played all 3 seasons | 41 | 17 |
| Played in NA / EMEA | 181 / 176 | 54 / 44 |

The beta's "Played all 3 seasons" counted line-ups; the new one counts maps, with line-up-only players as can't
verify. Puzzle 1 (2026-11-18), already generated under the beta's rule, is unchanged.

## What the 30 puzzles used

77 distinct clues across 30 puzzles (27 mixed, 3 role grids). Clue uses by family: teammate 45, LAN roster 29,
org 23, stage 22, stats 17, experience 15, season 13, role 9, region 7. Answers per cell: 3 to 35, median 7. Can't
verify per cell: median 3, largest 82.

## Gaps that produce can't-verify, in one place

| Gap | Clues affected |
|---|---|
| No map stats for 2024 Stages 3-4 (136 series) | every map-based clue for players active only then; stage clues for 4 stages |
| No map stats for 2026 Stage 3 (42 series) | the same, for 2026; stats for 2026 |
| Result-only playoff series (finals played offline) | stage clues; teammate |
| 49 unmapped team ids | "Played for" (cannot be clues), "3+ orgs" (not shipped) |
| Liquipedia line-ups list the roster | "Rostered at" says so; they also decide who is "seen" for can't-verify |
| Dreamhack Dallas line-ups incomplete | excluded from LAN clues |
| 12 undecided Liquipedia player pages | missing from LAN clues |
| No hero data | hero clues impossible |
