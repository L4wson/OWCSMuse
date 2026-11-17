# OWCS Grid: candidate grids and cell counts

Run 2026-11-16 with `scripts/grid/cell_counter.py`, read-only, against production. The full output of every run,
with ten sample ids and names per cell, is in [runs/](runs/). Grid definitions are in `scripts/grid/grids/`.

How to read a count: [scripts/grid/README.md](../../scripts/grid/README.md). In short, every answer is a canonical
id; a team id becomes an identity at the series' own time; a role or stat cell is counted over maps with FACEIT
stats and takes a min-maps floor (4 unless stated, Muse's leaderboard floor); every other player cell is counted
over series line-ups. A cell under 5 answers is marked **(!)**.

## Verdicts

| Grid | Smallest cell | Verdict |
|---|---|---|
| a. Role x season | 21 (14 at a 10-map floor) | **Viable. Recommended first format.** Easy, and blind to players with no role data |
| b. Org x org, top 6 by players | 0 | **Not viable.** 8 of 9 cells under 5; no 3x3 of any teams clears 2 |
| c1. Org x role | 3 | **Not viable at 5.** No team has 5 Tanks; one Tank per roster |
| c2. Org x season (Peps, SSG, Al Qadsiah) | 4 | One cell short |
| c3. Org x season (Peps, SSG, Twisted Minds) | 7 | **Viable**, but only 8 teams span three seasons, so few distinct puzzles |
| d1. Teams: region x season | 10 | **Viable**, easy |
| d2. Teams: region x international event | 5 | Viable on paper; one team fits all nine cells |
| d3. Teams: season x international results | 7 | Viable on paper; three teams fit all nine cells |
| e. Performance 2025 (extra) | 7 | Viable only with "top 15", which is too loose to mean much |
| f. Role x NA / EMEA / 3+ seasons (extra) | 19 at a 10-map floor | **Viable.** A second puzzle in the recommended format |

## a. Role x season (player answers)

`grids/role_x_season.json`. Both conditions on the same maps: a player with at least N maps played in that role in
that season.

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| **Tank** | 54 | 34 | 21 |
| **DPS** | 100 | 57 | 32 |
| **Support** | 96 | 54 | 34 |

The same grid at other floors:

| Floor | Tank 2024 / 2025 / 2026 | DPS | Support |
|---|---|---|---|
| 1 map | 59 / 39 / 23 | 119 / 67 / 34 | 102 / 54 / 37 |
| 4 maps | 54 / 34 / 21 | 100 / 57 / 32 | 96 / 54 / 34 |
| 10 maps | 33 / 31 / 14 | 66 / 55 / 29 | 65 / 52 / 31 |
| 20 maps | 19 / 28 / 12 | 39 / 50 / 24 | 40 / 48 / 25 |

Sample answers (first ten by name; full lists in `runs/role_x_season.txt`):

| Cell | Samples |
|---|---|
| Tank x 2024 | Ailiseu, ariel2, aspect, Astro, Axure, Baz, BenBest, bogur, Chase, chazm |
| Tank x 2025 | Astro, Baz, Chase, CLEAR, cuFFa, eisgnom, False, GAP, Hadi, Hawk |
| Tank x 2026 | amdp, Attack, cartifan22, Coluge, eisgnom, GoldenPants, Hawk, Hitori, Infekted, Kellan |
| DPS x 2024 | Amadien, Arclite, Avo, azruf, Backbone, Bastionmain, Bizz, Bun, CheckMate, chime |
| DPS x 2025 | Backbone, CheckMate, China, ChoiSehwan, Chopper, cookie084, Danny, Dip, Drunk, Evil |
| DPS x 2026 | Ade, AlphaYi, Dip, icav, JaeWoo, JUTSU, Kai, karmez, kevster, KORZ |
| Support x 2024 | abheek, Abyss, Admiral, ajmr, Aniyun, ANJ, AOY, BallerSteve, Buddie, cal |
| Support x 2025 | Admiral, alba, AOY, Bliss, cinnabar, cjay, CrazyCat, Crispy, EGS, Ewan |
| Support x 2026 | Admiral, cjay, Crispy, escanor, FDGod, FiNN, FiXa, FrothyFilly7, FunnyAstro, Galaa |

**Coverage**, as the counter prints it on every cell: player stats exist in 20 of 31 competitions in 2024 (none for
Stages 3-4, Dreamhack Dallas, EWC, World Finals), 12 of 15 in 2025 (none for the three international events) and
10 of 16 in 2026 (none for Stage 3 or the international events).

**Cross-check.** The same nine counts come out of a separate SQL query straight over `match_players` (not the
`fact_player_maps` view the counter reads): 54 / 34 / 21, 100 / 57 / 32, 96 / 54 / 34. That checks the counter's
logic. It does not check the data; the golden section below is for that.

**Overlap.** 326 distinct answers at a 4-map floor; 217 fit one cell, 62 fit two, 47 fit three. All nine cells can
be filled without reusing a player. 10 Tanks, 16 DPS and 18 Supports fit a whole row (the same role in all three
seasons). No one fits a whole column at 4 maps.

**Verdict: viable, and the most viable grid found.** Concerns:

- It is easy. Any fan who can name one current Tank, DPS and Support per era fills it. That is acceptable for a
  first puzzle and is what makes the format safe to launch with.
- It is one puzzle. Role x season has exactly one instance, so it cannot be the daily format by itself. It works
  as the template: role x (season | region | team | event) gives the variety.
- It cannot see 115 players from 2024 Stages 3-4 and 8 from 2026 Stage 3 (AUDIT.md, issue 1). Either the columns
  are labelled with what they cover, or those players get a "cannot verify" result instead of "wrong".
- At a 4-map floor a one-series fill-in counts: Simple (104 Support maps in 2025) is a Tank x 2025 answer on 4
  maps. A 10-map floor still leaves 14 in the smallest cell.

## b. Org x org, "played for both"

`grids/org_x_org_top6.json`. The six team identities with the most distinct players in their line-ups: Team Peps
(23), Quick Esports (22), SpaceStation Gaming (22), Shikigami (20), Al Qadsiah (19), Ex Oblivione (19). Each
condition is satisfied on its own series.

| | Shikigami | Al Qadsiah | Ex Oblivione |
|---|---|---|---|
| **Team Peps** | 0 (!) | 1 (!) | 4 (!) |
| **Quick Esports** | 0 (!) | 0 (!) | 5 |
| **SpaceStation Gaming** | 0 (!) | 2 (!) | 0 (!) |

Answers: Peps x Al Qadsiah: Tred. Peps x Ex Oblivione: cookie084, eisgnom, Xerion, Zorrow. Quick x Ex Oblivione:
abheek, Daan, Loren, skytorr, Twolzz. SSG x Al Qadsiah: Galaa, Landon.

Only 4 of 9 cells can be filled at all. Roster size does not predict shared players: Shikigami is NA and four of
the other five are EMEA, and OWCS is region-locked.

A search over every identity with 8 or more players found that only 8 pairs of teams share 5 or more players (the
largest: NTMR and SpaceStation Gaming, 9), and 34 share 3 or more. The best 3x3 that exists has a smallest cell
of 2:

| | NTMR | SpaceStation Gaming | M80 |
|---|---|---|---|
| **Team Liquid** | 3 | 2 | 3 |
| **Students of the Game** | 2 | 4 | 2 |
| **TSM** | 4 | 2 | 3 |

**Verdict: not viable** as a standard grid. Three seasons is not enough movement. It could work as a deliberately
hard format at a floor of 2, or as single "played for both" cells mixed into another grid.

## c. Org x role and org x season

### c1. Org x role

`grids/org_x_role.json`. A player with 4 or more maps in that role for that team.

| | Tank | DPS | Support |
|---|---|---|---|
| **Team Peps** | 5 | 9 | 4 (!) |
| **SpaceStation Gaming** | 3 (!) | 7 | 8 |
| **Al Qadsiah** | 4 (!) | 5 | 6 |

Samples: Peps Tanks: BenBest, eisgnom, Hybrid, Tred, Willys. SSG Tanks: Hadi, Hawk, Kellan. Al Qadsiah Tanks:
Chase, Tred, Vestola, ZIYAD. SSG Supports: Admiral, Bliss, cjay, FunnyAstro, Landon, Le7, squid, UltraViolet.

No team identity has 5 or more players in all three roles. The best are Team Peps (5 / 9 / 4), Al Qadsiah
(4 / 5 / 6) and Twisted Minds (4 / 4 / 7). A roster carries one Tank, so the Tank column caps it.

**Verdict: not viable at 5.** Viable at a floor of 3 for about six teams, and fair as a hard grid: 48 distinct
answers, only three of which fit two cells.

### c2 and c3. Org x season

A player in a line-up of that team in that season.

`grids/org_x_season.json`:

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| **Team Peps** | 15 | 11 | 8 |
| **SpaceStation Gaming** | 7 | 10 | 7 |
| **Al Qadsiah** | 4 (!) | 9 | 7 |

`grids/org_x_season_best.json`, with Twisted Minds in place of Al Qadsiah:

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| **Team Peps** | 15 | 11 | 8 |
| **SpaceStation Gaming** | 7 | 10 | 7 |
| **Twisted Minds** | 12 | 9 | 7 |

Samples: Peps 2026: Dip, FDGod, KroxZ, Rav, Willys, Xerion, xzodyal, Zorrow. SSG 2024: Backbone, FunnyAstro, Hadi,
KSAA, Landon, Seicoe, SparkR. Twisted Minds 2026: FunnyAstro, JaeWoo, KSAA, Quartz, Simple, TVNT, Youbi.

Eight identities have a line-up in all three seasons, with players per season:

| Team | 2024 | 2025 | 2026 |
|---|---|---|---|
| Team Peps | 15 | 11 | 8 |
| Twisted Minds | 12 | 9 | 7 |
| Crazy Raccoon | 8 | 7 | 7 |
| Team Falcons | 8 | 6 | 6 |
| SpaceStation Gaming | 7 | 10 | 7 |
| Virtus pro | 6 | 7 | 5 |
| Dhillducks | 6 | 9 | 5 |
| Al Qadsiah | 4 | 9 | 7 |

**Verdict: c3 is viable**, 57 distinct answers, and it is a real test of knowledge. Caveats: KSAA fits four cells
and seven players fit three; Crazy Raccoon and Team Falcons are international-only teams whose players are all
Liquipedia-born (no Muse stats to link to); Twisted Minds is an unmapped team id (AUDIT.md, issue 8); and SSG's
2024 line-up is its EMEA roster plus Dreamhack Dallas, where line-ups are incomplete (issue 3), so that cell is
probably undercounted. Seven choose three is not many puzzles.

## d. Team-answer grids (answer = a team identity)

### d1. Region x season

`grids/team_region_x_season.json`. A team with a series in a competition of that region in that season.

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| **Played in NA** | 39 | 14 | 11 |
| **Played in EMEA** | 34 | 11 | 10 |
| **Played in an international event** | 17 | 19 | 16 |

Samples: NA 2026: Dallas Fuel, Dhillducks, Disguised, Extinction, KAFE, Kintsugi, LuneX, NTMR (`ntmr-2026`),
SpaceStation Gaming, Team Liquid. EMEA 2026: 1234, Al Qadsiah, Anyones Legend, Geekay Esports, Star Bits x Hypnos,
Team Peps, Team Risk, Telacy, Twisted Minds, Virtus pro. International 2025: Al Qadsiah, All Gamers Global, Crazy
Raccoon, Geekay Esports, NTMR, Once Again, ROC Esports, SpaceStation Gaming, T1, Team CC.

118 distinct answers; 88 fit one cell. SpaceStation Gaming, Twisted Minds and Virtus pro each fit six.

**Verdict: viable and easy.** The 2024 cells are padded by open-bracket teams nobody remembers, which makes them
trivially easy to fill with a famous name and impossible to be "rare" in. Three display names are shared by two
identities each (Geekay Esports, NTMR, Sakura), so the input must disambiguate (AUDIT.md, issue 7). "Played in NA"
is the region of a competition, not a home region: SpaceStation Gaming counts for EMEA through its 2024 roster.

### d2. Region x international event and placement

`grids/team_region_x_event.json`. A region and an event are each satisfied on their own series ("an NA team that
went to the World Finals").

| | Competed at World Finals | Competed at Midseason Championship | Top 8 at an international event |
|---|---|---|---|
| **Played in NA** | 6 | 5 | 7 |
| **Played in EMEA** | 5 | 5 | 6 |
| **Played in an international event** | 16 | 23 | 19 |

NA x World Finals: Geekay Esports (NA), NTMR, SpaceStation Gaming, Students of the Game, Team Liquid, Toronto
Defiant. EMEA x World Finals: Al Qadsiah, ENCE, SpaceStation Gaming, Team Peps, Twisted Minds. EMEA x Midseason:
Al Qadsiah, Geekay Esports (EMEA), SpaceStation Gaming, Twisted Minds, Virtus pro.

**Verdict: passes the count, fails the feel.** 28 distinct answers. SpaceStation Gaming fits all nine cells, five
more teams fit six, and the third row is a superset of the other two. Four cells sit at 5 or 6, so one identity
correction puts a cell under the floor.

### d3. Season x international results

`grids/team_season_x_placement.json`. The season is the team's own; the placing is at any event in any season.

| | Played in an international event | Top 8 at an international event | Top 4 at an international event |
|---|---|---|---|
| **Competed in 2024** | 17 | 11 | 8 |
| **Competed in 2025** | 19 | 13 | 8 |
| **Competed in 2026** | 16 | 12 | 7 |

Top 4 x 2026: Al Qadsiah, Crazy Raccoon, T1, Team Falcons, Twisted Minds, Weibo Gaming, ZETA DIVISION.

**Verdict: too easy and too samey.** Crazy Raccoon, Team Falcons and Twisted Minds each fit all nine cells. The
columns nest (top 4 is inside top 8 is inside played). Placings cover 6 events only, so "top 8" silently excludes
Dreamhack Dallas and the 2026 Champions Clash.

### What a team-answer grid needs

The pool is about 30 teams that matter. A fair team grid needs conditions that cut across each other rather than
nest: region x "beat X" x "banned hero Y" x "won on map Z". The data supports all three (AUDIT.md, 4C and 4D), and
only `beat` is in the counter so far.

## e. Performance grid, 2025 (extra, to exercise the stat conditions)

`grids/performance_2025.json`, 10-map floor. Rates are total stat over total Time Played, by role.

| | Played in NA | Played in EMEA | Competed in 3+ seasons |
|---|---|---|---|
| **Top 15 eliminations per 10, DPS, 2025** | 9 | 7 | 11 |
| **Top 15 healing per 10, Support, 2025** | 8 | 9 | 7 |
| **Top 15 mitigation per 10, Tank, 2025** | 8 | 11 | 12 |

**Verdict: not yet.** It clears 5 only because "top 15" is loose: 15 of 31 eligible Tanks. A top 10 would put
cells near 5. Performance clues belong as single rows in a mixed grid, scoped to 2025 or 2026, never 2024: the
counter refuses a per-10 condition for 2024 ("2024 has no maps with both Eliminations and Time Played").

## f. Role x region and longevity (extra, a second puzzle in the recommended format)

`grids/role_x_region.json`, 10-map floor. Role and region hold on the same maps ("10 or more maps as Tank in NA
competitions"). "3+ seasons" is counted over line-ups and intersected.

| | Played in NA | Played in EMEA | Competed in 3+ seasons |
|---|---|---|---|
| **Tank** | 29 | 28 | 19 |
| **DPS** | 46 | 51 | 30 |
| **Support** | 47 | 53 | 25 |

247 distinct answers; 172 fit one cell and only 6 fit three (Admiral, Hitori, KiWii, Scyle, Tred, WMaimone, each of
whom played in both regions). **Verdict: viable**, and harder than grid a because NA and EMEA split the player
pool. The same role-data gap applies. Full output: `runs/role_x_region_min10.txt`.

## Golden-answer checks (proposed, not confirmed)

Three cells from grid a, at the 4-map floor, with their full answer sets. These are **proposed**: they are what the
counter returns, cross-checked only against a second SQL path over the same tables. Under this project's rule they
do not become assertions until a person confirms them from an independent source, and the right independent
derivation for Phase 1 is a function in the style of `tests/golden/independent.py` that reads `Role` out of the
raw FACEIT `/stats` payloads.

What Liquipedia can and cannot confirm: a player's team in that season and their usual role, yes. A fill-in on a
role for one series, no; Liquipedia lists a primary role. So for each entry check (1) this is the right person,
(2) they played for that team in that season, (3) their role there. An entry marked **yes** has a specific reason
to look. "Spot check" means nothing stood out; sample a few.

The reasons, and what each would reveal:

- **near the floor**: under 10 maps in the role. Would be dropped by a 10-map floor. Tests the floor decision.
- **also played**: another role the same season. A fill-in or a genuine flex.
- **more than one team**: tests that each map was attributed to the team at the time.
- **renamed** / other names on record: tests that one person has one id.

### G-A1: Played Tank x Competed in 2026 (21 answers)

| # | Player | player_id | Maps as Tank | Team(s) at the time | Region | Other names on record | Verify |
|---|---|---|---|---|---|---|---|
| 1 | amdp | `f3083b81-66f3-4ea5-a509-f2d92f299624` | 20 | 1234, Anyones Legend | EMEA | - | **yes**: more than one team |
| 2 | Attack | `232fdb58-fe04-4a4d-bae1-31671cd371b8` | 9 | Team Liquid | NA | Atttack | **yes**: near the floor (9 maps) |
| 3 | cartifan22 | `d1227d2c-f885-4729-b4de-77e20f08511d` | 4 | LuneX | NA | cartifan22_ | **yes**: near the floor (4 maps) |
| 4 | Coluge | `27fd0cfe-b845-410a-a69e-797f14b4c8cd` | 6 | Team Liquid | NA | - | **yes**: near the floor (6 maps) |
| 5 | eisgnom | `37aeeb7b-b183-4fae-b25d-d1de03a58191` | 46 | Virtus pro | EMEA | eis, eisgnom9 | spot check |
| 6 | GoldenPants | `0c88427e-d146-4fea-a383-431ddd8ee3e2` | 5 | 1234 | EMEA | goldenpants2 | **yes**: near the floor (5 maps) |
| 7 | Hawk | `a940981f-c750-40b9-bb55-bd3e8e6ef986` | 41 | SpaceStation Gaming | NA | TheeHawk | spot check |
| 8 | Hitori | `60ad5972-64e6-434b-ad31-648f43d30735` | 11 | Kintsugi | NA | Hitoriow, Reiner | **yes**: renamed |
| 9 | Infekted | `3d7e3522-9ef9-4c31-abe2-e10dd1c14270` | 29 | Team Liquid | NA | Infektedow | spot check |
| 10 | Kellan | `19298c75-9d48-4dc5-9970-75509c11246c` | 45 | Dallas Fuel | NA | Kellannn | spot check |
| 11 | Krawi | `d7952438-251e-4ad0-aa66-4b4a13200146` | 8 | Dhillducks | NA | Kraw1 | **yes**: near the floor (8 maps) |
| 12 | KSAA | `92695183-d00e-4c31-9707-ff9d8500f52a` | 4 | Twisted Minds | EMEA | KSAA0 | **yes**: near the floor (4 maps) |
| 13 | Lars | `2f42ce49-7f74-41ef-9867-998f0e714735` | 16 | Telacy | EMEA | IaFish | spot check |
| 14 | sniper | `b529dff3-f4c1-485d-b070-32fda58883db` | 35 | Extinction, The Kafe | NA | Esc_DeadShot | **yes**: more than one team |
| 15 | Tama | `f74933e7-58c9-4efe-81b5-899079a64109` | 8 | Anyones Legend | EMEA | Tummer, tamaow | **yes**: near the floor (8 maps); renamed |
| 16 | Tred | `2acfb6df-f298-4b92-8ab8-2141635f28e4` | 32 | Disguised | NA | TRED2474 | **yes**: renamed |
| 17 | TVNT | `b371a120-4be1-4677-aeee-81f5ebc80731` | 37 | Twisted Minds | EMEA | TVNT_ | spot check |
| 18 | Vestola | `1661fa93-eee8-4cd5-98a8-f7478bbe87e2` | 40 | Al Qadsiah | EMEA | - | spot check |
| 19 | Willys | `39cada54-4c21-4421-8bc5-baca66c525dc` | 25 | Team Peps | EMEA | Willys07 | spot check |
| 20 | Zeb | `eb37ecfe-626d-4280-9d9c-316a449eddcf` | 31 | LuneX | NA | Zeb_ow | spot check |
| 21 | ZIYAD | `c2c17617-77ac-4f70-8529-59a2a910cb35` | 55 | Geekay Esports | EMEA | ZIYAD-OW | spot check |

Flagged for hand verification: 11 of 21.

### G-A2: Played Tank x Competed in 2025 (34 answers)

| # | Player | player_id | Maps as Tank | Team(s) at the time | Region | Other names on record | Verify |
|---|---|---|---|---|---|---|---|
| 1 | Astro | `e78965e3-6fdc-437d-ab8f-b859e283dfdf` | 39 | Supernova, Team Z | NA | Astronexz | **yes**: also played Damage (2); more than one team |
| 2 | Baz | `029bf891-4c0b-4153-a386-b7ff9f3ad2f8` | 30 | Dhillducks | NA | BazOdub | spot check |
| 3 | Chase | `23c11b19-5748-4890-87da-7d41db6a46cd` | 22 | Al Qadsiah, The Ultimates | EMEA | Chaseeeeeee_, Chasetorch | **yes**: more than one team; renamed |
| 4 | CLEAR | `a50e5d9c-e00c-476d-86a9-04ab1403d09d` | 27 | NTMR, Sakura | NA | CLEAROW | **yes**: more than one team |
| 5 | cuFFa | `e6fc96f5-c5a1-4d76-9086-17a0b9743d83` | 124 | Geekay Esports, NTMR | NA | cuFFah | **yes**: more than one team |
| 6 | eisgnom | `37aeeb7b-b183-4fae-b25d-d1de03a58191` | 68 | Team Peps, Virtus pro | EMEA | eis, eisgnom9 | **yes**: more than one team |
| 7 | False | `babf94ba-ab1f-45cd-ada2-10fe89b16bc0` | 7 | Supernova | NA | Fal2e | **yes**: near the floor (7 maps); also played Damage (1) |
| 8 | GAP | `925028a0-be74-4f09-87d1-d62a6aa2bc7b` | 25 | Amplify | NA | gap_ow | spot check |
| 9 | Hadi | `5f60ca5b-92be-4673-b2c6-06623b111467` | 12 | Twisted Minds | EMEA | HadiOW2 | spot check |
| 10 | Hawk | `a940981f-c750-40b9-bb55-bd3e8e6ef986` | 45 | SpaceStation Gaming | NA | TheeHawk | spot check |
| 11 | HEESUNG | `eeb4e46f-723d-4a37-ae68-685c237627c8` | 36 | The Ultimates | EMEA | - | spot check |
| 12 | Hitori | `60ad5972-64e6-434b-ad31-648f43d30735` | 74 | Extinction, Sakura | EMEA/NA | Hitoriow, Reiner | **yes**: more than one team; renamed |
| 13 | iMOH97 | `f5ceb061-150c-44ad-b723-2bbad0fb3d93` | 20 | Vision Esports | EMEA | - | spot check |
| 14 | Infekted | `3d7e3522-9ef9-4c31-abe2-e10dd1c14270` | 108 | Team Liquid | NA | Infektedow | spot check |
| 15 | Kellan | `19298c75-9d48-4dc5-9970-75509c11246c` | 74 | SpaceStation Gaming | NA | Kellannn | spot check |
| 16 | KroxZ | `06481b72-092d-43c3-a686-13c92f03616f` | 21 | Goud Guys ANM | EMEA | - | spot check |
| 17 | KSAA | `92695183-d00e-4c31-9707-ff9d8500f52a` | 76 | The Ultimates, Twisted Minds | EMEA | KSAA0 | **yes**: more than one team |
| 18 | Mag | `65d1a22d-63a6-48c6-9fc9-bf26c0209018` | 61 | Gen.G Esports | EMEA | MAG200 | spot check |
| 19 | Majīn | `dd6c03b0-7c8b-4004-b11d-ccb439d65cb5` | 23 | Frost Tails | EMEA | MajinOW | spot check |
| 20 | Painkiller | `23e964b7-0899-48c5-b13b-8e7c4686e817` | 79 | NTMR, Rad | NA | Painkilllr | **yes**: more than one team |
| 21 | pela | `7ec3e4c6-6af0-4d3c-b08c-3b05ec1b1271` | 12 | Avidity | NA | pela_OW | spot check |
| 22 | RAIKKER | `5e9557ef-b5be-4ebd-a42a-c27c1c009c65` | 37 | Timeless | NA | JulianBubble | **yes**: renamed |
| 23 | RhynO | `e2ab56e6-ca09-4d4c-8254-73a5cbe818e6` | 9 | NTMR | NA | RhynO_OW | **yes**: near the floor (9 maps); also played Damage (1) |
| 24 | Simple | `635737a5-3456-43c5-aa74-d7ccb1a30da1` | 4 | Vision Esports | EMEA | SimpleOW | **yes**: near the floor (4 maps); also played Support (104) |
| 25 | skytorr | `41d949e5-16eb-4ee1-ba62-c8906118c616` | 22 | Quick Esports | EMEA | - | spot check |
| 26 | Solo | `20749c49-35ad-42c4-a0c3-79efffdc321d` | 22 | Shikigami | NA | owSolo | spot check |
| 27 | Tama | `f74933e7-58c9-4efe-81b5-899079a64109` | 24 | Vision Esports | EMEA | Tummer, tamaow | **yes**: renamed |
| 28 | Tred | `2acfb6df-f298-4b92-8ab8-2141635f28e4` | 67 | Al Qadsiah, Gen.G Esports, Team Peps | EMEA | TRED2474 | **yes**: more than one team; renamed |
| 29 | TVNT | `b371a120-4be1-4677-aeee-81f5ebc80731` | 47 | Twisted Minds | EMEA | TVNT_ | spot check |
| 30 | Twolzz | `243f8468-6f3a-4607-b151-53da202fdd22` | 15 | Avidity | NA | - | spot check |
| 31 | Vestola | `1661fa93-eee8-4cd5-98a8-f7478bbe87e2` | 74 | Virtus pro | EMEA | - | spot check |
| 32 | Willys | `39cada54-4c21-4421-8bc5-baca66c525dc` | 58 | Quick Esports, Team Peps | EMEA | Willys07 | **yes**: more than one team |
| 33 | Zeb | `eb37ecfe-626d-4280-9d9c-316a449eddcf` | 29 | Rad, Sakura | NA | Zeb_ow | **yes**: more than one team |
| 34 | ZIYAD | `c2c17617-77ac-4f70-8529-59a2a910cb35` | 93 | Al Qadsiah | EMEA | ZIYAD-OW | spot check |

Flagged for hand verification: 16 of 34.

### G-A3: Played Support x Competed in 2026 (34 answers)

| # | Player | player_id | Maps as Support | Team(s) at the time | Region | Other names on record | Verify |
|---|---|---|---|---|---|---|---|
| 1 | Admiral | `41c50d1a-3a08-40ad-9746-ecd52ff9e5c6` | 41 | SpaceStation Gaming | NA | AdmiralRaptr | spot check |
| 2 | cjay | `2ede0b37-1352-47d2-9547-7d0f9f07abaa` | 45 | Dallas Fuel | NA | cjay4 | spot check |
| 3 | Crispy | `9da88fbd-ebcb-4f7b-88ce-a79d6d55386d` | 33 | 1234, Anyones Legend | EMEA | zzcrispy | **yes**: more than one team |
| 4 | escanor | `2e4db6df-0964-4e01-8b6d-20b29f8544dd` | 25 | Team Liquid | NA | escanor1161 | spot check |
| 5 | FDGod | `1ab8c25f-15f0-4707-acc9-4718c88157da` | 25 | Team Peps | EMEA | FDGod_OW | spot check |
| 6 | FiNN | `fece55bf-88e9-4234-bcbb-bef43740b491` | 55 | Geekay Esports | EMEA | SEjFiNN | spot check |
| 7 | FiXa | `e422414a-72ec-4e83-8264-6a54b39414b8` | 46 | Virtus pro | EMEA | _FiXa | spot check |
| 8 | FrothyFilly7 | `083989e0-81a4-4f83-8dc3-e5222f0df695` | 8 | Dhillducks | NA | - | **yes**: near the floor (8 maps) |
| 9 | FunnyAstro | `423b8943-30c9-4436-8a22-51ca77aa7fca` | 41 | Twisted Minds | EMEA | FunnyAstro1 | spot check |
| 10 | Galaa | `04d8399b-8ae4-4142-92dd-512021980e5f` | 40 | Al Qadsiah | EMEA | Galaavv | spot check |
| 11 | Grapes | `7d81b5d2-eef0-4341-961f-f203d45f65df` | 35 | Extinction, The Kafe | NA | GrappesOW | **yes**: more than one team |
| 12 | Haku | `7928a18c-bbe9-403b-936a-d5df7355b6e3` | 28 | Geekay Esports | EMEA | iHAKUi | spot check |
| 13 | Johnowich | `e2d9ec68-0041-45e2-b354-5bad9c2e028b` | 11 | Telacy | EMEA | - | spot check |
| 14 | Juno | `0f021b35-8f85-4be1-a324-5086a7a5f36a` | 11 | Kintsugi | NA | zzJuno | spot check |
| 15 | kellex | `b273a710-800f-4638-9858-461d81ac55b9` | 27 | Geekay Esports | EMEA | kellemanden | spot check |
| 16 | Khenail | `9d58d137-dd65-43c8-9f84-1ae3d063a11d` | 33 | 1234, Anyones Legend | EMEA | - | **yes**: more than one team |
| 17 | KIVIS | `1ea17648-a903-4269-a4d7-aca78c3a7d56` | 19 | Team Liquid | NA | KIVIS04 | spot check |
| 18 | KiWii | `31417126-50e7-486e-b00d-15e61a110ab8` | 15 | Disguised, Kintsugi | NA | KiWii__ | **yes**: more than one team |
| 19 | Landon | `a332d27e-fe19-4077-89f8-27391a581460` | 46 | Virtus pro | EMEA | LandonOW | spot check |
| 20 | Le7 | `f2359218-1265-472c-8fbc-9c91183766f0` | 29 | Disguised | NA | Lep, Leptx, Wybietx, joseph_- | **yes**: renamed |
| 21 | Lukemino | `482cb7a6-687c-47a4-bb07-6fd02e604ed3` | 45 | Dallas Fuel | NA | - | spot check |
| 22 | NenWhy | `1f27cd97-1764-475c-9a30-eb95b4a8fbdf` | 35 | LuneX | NA | - | spot check |
| 23 | Pingu | `c9431330-aaf9-4f18-9153-0bae7a38ec8c` | 5 | Telacy | EMEA | Pingu_ow | **yes**: near the floor (5 maps) |
| 24 | redex | `bf69c0b9-f068-41bf-a0b9-c88aa083edbb` | 8 | Dhillducks | NA | RedexLCO | **yes**: near the floor (8 maps) |
| 25 | scuffed | `1d7c1096-c876-426b-a89a-8be16b8c9092` | 33 | Extinction, The Kafe | NA | scuffedhaha | **yes**: more than one team |
| 26 | Scyle | `ad12d7b8-4843-4a95-a468-97e28901ce2b` | 33 | Disguised | NA | - | spot check |
| 27 | Simple | `635737a5-3456-43c5-aa74-d7ccb1a30da1` | 41 | Twisted Minds | EMEA | SimpleOW | spot check |
| 28 | SirMajed | `51bd468c-463e-43c9-be25-3d23803c3ee9` | 26 | Al Qadsiah | EMEA | sirmajed9 | spot check |
| 29 | teksol | `e5581905-11cb-4c88-9b2b-3ac80fe21097` | 16 | Telacy | EMEA | - | spot check |
| 30 | UltraViolet | `43d39898-d853-4e75-b249-9b41d638a2b0` | 41 | SpaceStation Gaming | NA | ultraviol3t | spot check |
| 31 | Vega | `80fd30f8-18d4-4aa9-a94b-644f155a50e4` | 44 | Team Liquid | NA | VegaOW | spot check |
| 32 | Xerion | `e01e90ce-eb0a-4a94-a797-9a1e8d5539ed` | 25 | Team Peps | EMEA | Xerion_gdh, Xeriongdh | **yes**: renamed |
| 33 | zox | `a1fb03ff-9977-4d0b-b4bd-82fa6085f0ed` | 14 | Al Qadsiah | EMEA | zox1509, zox_ow | **yes**: renamed |
| 34 | ZZZ | `0a7555bc-8cd2-44bd-b1d5-df0c528dddea` | 35 | LuneX | NA | z_ow, zman, zss | **yes**: renamed |

Flagged for hand verification: 12 of 34.

Players with Tank maps in 2026 but under the 4-map floor, so not answers: Majīn (3), RAIKKER (1)

The same for Tank in 2025: AOY (2), Axure (3), pdk (1), Reyzr (2), sniper (1)

The same for Support in 2026: CNYXC (3), Dockiy (3), Gorilla (2)

Entries I would look at first, because each is a decision as much as a fact:

1. **Simple, Tank x 2025** (4 Tank maps for Vision Esports, 104 Support maps). Is a one-series fill-in a "Tank"?
2. **KSAA, Tank x 2026** (exactly 4 maps, Twisted Minds). On the floor; one map fewer and he is out.
3. **cartifan22, Tank x 2026** (exactly 4 maps, LuneX). Same.
4. **Hitori, Tank x 2025** (Extinction and Sakura, EMEA and NA). The one answer spanning both regions in a season;
   Sakura is a name two identities share.
5. **Tred, Tank x 2025** (Al Qadsiah, Gen.G Esports, Team Peps). Three teams in one season.
6. **Astro, Tank x 2025** (Supernova, Team Z). Both are eras of the recycled team id d20d1868.
7. **sniper, Tank x 2026** (Extinction, The Kafe). A roster pickup on one team id.
8. **ZZZ, Support x 2026** (LuneX). Owner display name over FACEIT `z_ow` and in-game `zss`.
9. **Le7, Support x 2026** (Disguised). Four other names on record.

Also worth confirming from Liquipedia as *absent*: any 2026 Tank you know of who is not in G-A1. The likeliest
cause is Stage 3, where there is no role data.
