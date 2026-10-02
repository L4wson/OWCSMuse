# Team-id windows: review

Source: `scope/team_name_history_2026-10-01.json`. 18 team ids carry more than one FACEIT name. Three signals per name change: the handle (a new name that contains or extends the old one is a rename by the same organisation), the stage boundary (a wholly different name first seen in a new stage is a roster pickup by another organisation; in OWCS a pickup lands on a stage boundary) and the registration placeholder (a `team_` name, or one that lived only in the opening days of a stage, replaced inside that stage once the roster signed up: the same organisation). One proposal per id. The tool decides nothing: a window is applied only through `scope/org_decisions.json` (`orgs decide --from-name ... --to-name ...`, `--add` for a further era on one id); the owner's verdicts are in `scope/org_window_decisions.json` and shown under each id.

3 id(s) where the signals disagree, listed first; 9 with a clear pickup; 6 rename-only or placeholder (one organisation, no window); 18 decided.

## `0464a373` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | UNC inc | 2024-04-12 | 2024-04-21 | 2024 Stage 2 / 2024 Stage 2 |
| 2 | Rad | 2025-02-01 | 2025-05-10 | 2025 Stage 1 / 2025 Stage 2 |
| 3 | Sakura | 2025-05-17 | 2025-09-21 | 2025 Stage 2 / 2025 Stage 3 |
| 4 | Sakura Esports | 2025-09-27 | 2025-10-25 | 2025 Stage 3 / 2025 Stage 3 |
| 5 | LuneX | 2026-03-21 | 2026-07-04 | 2026 Stage 1 / 2026 Stage 2 |

- **PICKUP**: UNC inc -> Rad: 'Rad' is a wholly different name first seen in 2025 Stage 1 after 'UNC inc' last played in 2024 Stage 2: a roster pickup
- **DISAGREE**: Rad -> Sakura: 'Sakura' is a wholly different name but appears inside the same stage as 'Rad' (2025 Stage 2): not a stage-boundary pickup and not a rename
- **rename**: Sakura -> Sakura Esports: 'Sakura Esports' keeps the handle of 'Sakura': a rename by the same organisation
- **PICKUP**: Sakura Esports -> LuneX: 'LuneX' is a wholly different name first seen in 2026 Stage 1 after 'Sakura Esports' last played in 2025 Stage 3: a roster pickup

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [UNC inc] from the first sighting of 'UNC inc' (2024-04-12) to 2024-04-21; [Rad / Sakura (?) / Sakura Esports] from the first sighting of 'Rad' (2025-02-01) to 2025-10-25; [LuneX] from the first sighting of 'LuneX' (2026-03-21) to 2026-07-04

**Decided (org_changes):** UNC inc (the id's own era); Rad from 2025 Stage 1 (pickup); Rad -> Sakura is an organisation change (windowed); Sakura Esports a rename inside the Sakura era; LuneX from 2026 Stage 1 (pickup).

- applied: rad [first 'Rad' sighting .. first 'Sakura' sighting)
- applied: sakura [first 'Sakura' sighting .. first 'LuneX' sighting)
- applied: lunex [first 'LuneX' sighting .. open)

_The signals read this id differently (see above); the owner's decision stands._

## `75516399` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Anyones Legend | 2026-03-22 | 2026-05-25 | 2026 Stage 1 / 2026 Stage 1 |
| 2 | 1234 | 2026-05-25 | 2026-07-01 | 2026 Stage 1 / 2026 Stage 2 |

- **DISAGREE**: Anyones Legend -> 1234: '1234' (2026-05-25..2026-07-01) sits inside 'Anyones Legend''s range (2026-03-22..2026-05-25): the id alternated between the names, which neither signal explains

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [Anyones Legend / 1234 (?)] from the first sighting of 'Anyones Legend' (2026-03-22) to 2026-07-01

**Decided (roster_drop):** Anyones Legend dropped the roster, which continued as 1234: a pickup, windowed at the 1234 era. The overlapping dates are a FACEIT artifact, not an alias.

- applied: 1234 [first '1234' sighting .. open)

_The signals read this id differently (see above); the owner's decision stands._

## `cb90edf6` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Quick Esports | 2025-05-11 | 2025-10-12 | 2025 Stage 2 / 2025 Stage 3 |
| 2 | 1DIPv100GORILLA | 2025-06-01 | 2025-06-15 | 2025 Stage 2 / 2025 Stage 2 |

- **DISAGREE**: Quick Esports -> 1DIPv100GORILLA: '1DIPv100GORILLA' (2025-06-01..2025-06-15) sits inside 'Quick Esports''s range (2025-05-11..2025-10-12): the id alternated between the names, which neither signal explains

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [Quick Esports / 1DIPv100GORILLA (?)] from the first sighting of 'Quick Esports' (2025-05-11) to 2025-10-12

**Decided (roster_drop):** Quick Esports' roster played as 1DIPv100GORILLA: a pickup, windowed at that era. The overlapping dates are a FACEIT artifact, not an alias.

- applied: 1dipv100gorilla [first '1DIPv100GORILLA' sighting .. open)

_The signals read this id differently (see above); the owner's decision stands._

## `d20d1868` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | team_chiime | 2024-03-08 | 2024-03-10 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Dreamland | 2024-03-17 | 2024-03-17 | 2024 Stage 1 / 2024 Stage 1 |
| 3 | Supernova | 2025-05-11 | 2025-06-14 | 2025 Stage 2 / 2025 Stage 2 |
| 4 | Team Z | 2025-09-07 | 2025-10-19 | 2025 Stage 3 / 2025 Stage 3 |

- **placeholder**: team_chiime -> Dreamland: 'team_chiime' is a FACEIT registration placeholder ('team_' prefix) replaced by 'Dreamland' inside 2024 Stage 1
- **PICKUP**: Dreamland -> Supernova: 'Supernova' is a wholly different name first seen in 2025 Stage 2 after 'Dreamland' last played in 2024 Stage 1: a roster pickup
- **PICKUP**: Supernova -> Team Z: 'Team Z' is a wholly different name first seen in 2025 Stage 3 after 'Supernova' last played in 2025 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [team_chiime / Dreamland] from the first sighting of 'team_chiime' (2024-03-08) to 2024-03-17; [Supernova] from the first sighting of 'Supernova' (2025-05-11) to 2025-06-14; [Team Z] from the first sighting of 'Team Z' (2025-09-07) to 2025-10-19

**Decided (placeholder_then_pickups):** team_chiime -> Dreamland is a registration placeholder (one era, the id's own); Supernova (2025 Stage 2) and Team Z (2025 Stage 3) are pickups, each its own org over its own window.

- applied: supernova [first 'Supernova' sighting .. first 'Team Z' sighting)
- applied: team-z [first 'Team Z' sighting .. open)

## `03869857` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | ROC ESPORT | 2024-03-08 | 2024-03-21 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Umbrellaacademy | 2024-04-12 | 2024-04-12 | 2024 Stage 2 / 2024 Stage 2 |
| 3 | ROCstars | 2024-04-20 | 2024-04-21 | 2024 Stage 2 / 2024 Stage 2 |

- **PICKUP**: ROC ESPORT -> Umbrellaacademy: 'Umbrellaacademy' is a wholly different name first seen in 2024 Stage 2 after 'ROC ESPORT' last played in 2024 Stage 1: a roster pickup
- **placeholder**: Umbrellaacademy -> ROCstars: 'Umbrellaacademy' lived only in the opening 1 day(s) of 2024 Stage 2 and 'ROCstars' replaced it inside the same stage: a registration placeholder

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [ROC ESPORT] from the first sighting of 'ROC ESPORT' (2024-03-08) to 2024-03-21; [Umbrellaacademy / ROCstars] from the first sighting of 'Umbrellaacademy' (2024-04-12) to 2024-04-21

**Decided (org_changes):** ROC ESPORT (the id's own era); Umbrellaacademy from 2024 Stage 2 (pickup); Umbrellaacademy -> ROCstars is an organisation change (windowed). The placeholder signal also fires on Umbrellaacademy (one day at the start of the stage); the owner's decision stands.

- applied: umbrellaacademy [first 'Umbrellaacademy' sighting .. first 'ROCstars' sighting)
- applied: rocstars [first 'ROCstars' sighting .. open)

_The signals read this id differently (see above); the owner's decision stands._

## `2b7f8ef6` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Avidity | 2025-02-01 | 2025-03-02 | 2025 Stage 1 / 2025 Stage 1 |
| 2 | Extinction | 2025-05-11 | 2025-10-12 | 2025 Stage 2 / 2025 Stage 3 |

- **PICKUP**: Avidity -> Extinction: 'Extinction' is a wholly different name first seen in 2025 Stage 2 after 'Avidity' last played in 2025 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Avidity] from the first sighting of 'Avidity' (2025-02-01) to 2025-03-02; [Extinction] from the first sighting of 'Extinction' (2025-05-11) to 2025-10-12

**Decided (pickup):** Avidity (the id's own era) then Extinction from 2025 Stage 2 (decided in the identity batch).

- applied: extinction [first 'Extinction' sighting .. open)

## `a35f8d47` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Extinction | 2026-03-22 | 2026-05-29 | 2026 Stage 1 / 2026 Stage 1 |
| 2 | The Kafe | 2026-06-13 | 2026-07-01 | 2026 Stage 2 / 2026 Stage 2 |

- **PICKUP**: Extinction -> The Kafe: 'The Kafe' is a wholly different name first seen in 2026 Stage 2 after 'Extinction' last played in 2026 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Extinction] from the first sighting of 'Extinction' (2026-03-22) to 2026-05-29; [The Kafe] from the first sighting of 'The Kafe' (2026-06-13) to 2026-07-01

**Decided (pickup):** Extinction (windowed to the first The Kafe sighting) then The Kafe (the id's own era) (decided in the identity batch).

- applied: extinction [first 'Extinction' sighting .. first 'The Kafe' sighting)

## `bb5dd404` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Ex Oblivione | 2024-03-08 | 2024-04-20 | 2024 Stage 1 / 2024 Stage 2 |
| 2 | Virtuspro | 2025-01-31 | 2025-10-19 | 2025 Stage 1 / 2025 Stage 3 |

- **PICKUP**: Ex Oblivione -> Virtuspro: 'Virtuspro' is a wholly different name first seen in 2025 Stage 1 after 'Ex Oblivione' last played in 2024 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Ex Oblivione] from the first sighting of 'Ex Oblivione' (2024-03-08) to 2024-04-20; [Virtuspro] from the first sighting of 'Virtuspro' (2025-01-31) to 2025-10-19

**Decided (pickup):** Ex Oblivione (the id's own era) then Virtus pro from 2025-01-31T19:17:07Z (decided in the identity batch).

- applied: virtus-pro [2025-01-31T19:17:07+00:00 .. open)

## `c5116cb3` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Timeless | 2024-03-08 | 2025-03-08 | 2024 Stage 1 / 2025 Stage 1 |
| 2 | NTMR | 2025-05-10 | 2025-10-19 | 2025 Stage 2 / 2025 Stage 3 |

- **PICKUP**: Timeless -> NTMR: 'NTMR' is a wholly different name first seen in 2025 Stage 2 after 'Timeless' last played in 2025 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Timeless] from the first sighting of 'Timeless' (2024-03-08) to 2025-03-08; [NTMR] from the first sighting of 'NTMR' (2025-05-10) to 2025-10-19

**Decided (pickup):** Timeless (the id's own era) then NTMR from 2025 Stage 2; NTMR is one organisation with cefc3f72's NTMR era, each team id mapped only over its own NTMR window.

- applied: ntmr [first 'NTMR' sighting .. open)

## `c82570d6` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Deimpero | 2024-04-12 | 2024-04-29 | 2024 Stage 2 / 2024 Stage 2 |
| 2 | Frost Tails | 2025-05-11 | 2025-06-15 | 2025 Stage 2 / 2025 Stage 2 |

- **PICKUP**: Deimpero -> Frost Tails: 'Frost Tails' is a wholly different name first seen in 2025 Stage 2 after 'Deimpero' last played in 2024 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Deimpero] from the first sighting of 'Deimpero' (2024-04-12) to 2024-04-29; [Frost Tails] from the first sighting of 'Frost Tails' (2025-05-11) to 2025-06-15

**Decided (pickup):** Deimpero (the id's own era) then Frost Tails from 2025 Stage 2.

- applied: frost-tails [first 'Frost Tails' sighting .. open)

## `cefc3f72` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | FMCL | 2024-04-12 | 2024-04-29 | 2024 Stage 2 / 2024 Stage 2 |
| 2 | NTMR | 2025-02-01 | 2025-03-10 | 2025 Stage 1 / 2025 Stage 1 |

- **PICKUP**: FMCL -> NTMR: 'NTMR' is a wholly different name first seen in 2025 Stage 1 after 'FMCL' last played in 2024 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [FMCL] from the first sighting of 'FMCL' (2024-04-12) to 2024-04-29; [NTMR] from the first sighting of 'NTMR' (2025-02-01) to 2025-03-10

**Decided (pickup):** FMCL (the id's own era) then NTMR from 2025 Stage 1; NTMR is one organisation with c5116cb3's NTMR era.

- applied: ntmr [first 'NTMR' sighting .. open)

## `ebfd8060` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Quick esports | 2024-03-08 | 2024-03-22 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Ataraxia | 2024-04-12 | 2024-04-21 | 2024 Stage 2 / 2024 Stage 2 |

- **PICKUP**: Quick esports -> Ataraxia: 'Ataraxia' is a wholly different name first seen in 2024 Stage 2 after 'Quick esports' last played in 2024 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Quick esports] from the first sighting of 'Quick esports' (2024-03-08) to 2024-03-22; [Ataraxia] from the first sighting of 'Ataraxia' (2024-04-12) to 2024-04-21

**Decided (pickup):** Quick esports (the id's own era) then Ataraxia from 2024 Stage 2.

- applied: ataraxia [first 'Ataraxia' sighting .. open)

## `0c629c99` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | team_Rakattack__ | 2024-03-08 | 2024-03-10 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Students of the Game | 2024-03-17 | 2024-03-17 | 2024 Stage 1 / 2024 Stage 1 |

- **placeholder**: team_Rakattack__ -> Students of the Game: 'team_Rakattack__' is a FACEIT registration placeholder ('team_' prefix) replaced by 'Students of the Game' inside 2024 Stage 1

**Proposal:** one organisation, no window: [team_Rakattack__ / Students of the Game] from the first sighting of 'team_Rakattack__' (2024-03-08) to 2024-03-17

**Decided (placeholder):** team_Rakattack__ -> Students of the Game: a FACEIT registration placeholder replaced once the roster signed up (first days of 2024 Stage 1). Same organisation, no window; the id stays mapped to students-of-the-game for all time.

- applied: students-of-the-game [always .. open)

## `602d3c11` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Goud Guys | 2025-09-07 | 2025-09-27 | 2025 Stage 3 / 2025 Stage 3 |
| 2 | Goud Guys ANM | 2025-09-28 | 2025-10-12 | 2025 Stage 3 / 2025 Stage 3 |

- **rename**: Goud Guys -> Goud Guys ANM: 'Goud Guys ANM' keeps the handle of 'Goud Guys': a rename by the same organisation

**Proposal:** one organisation, no window: [Goud Guys / Goud Guys ANM] from the first sighting of 'Goud Guys' (2025-09-07) to 2025-10-12

**Decided (rename_only):** Goud Guys -> Goud Guys ANM: one organisation, no window.

## `62f7752b` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | BuboSprayCheck | 2024-03-08 | 2024-03-21 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | ENCE | 2024-03-22 | 2024-06-02 | 2024 Stage 1 / 2024 Dreamhack Dallas |

- **placeholder**: BuboSprayCheck -> ENCE: 'BuboSprayCheck' lived only in the opening 14 day(s) of 2024 Stage 1 and 'ENCE' replaced it inside the same stage: a registration placeholder

**Proposal:** one organisation, no window: [BuboSprayCheck / ENCE] from the first sighting of 'BuboSprayCheck' (2024-03-08) to 2024-06-02

**Decided (placeholder):** BuboSprayCheck -> ENCE: a registration placeholder replaced inside the opening days of 2024 Stage 1. Same organisation, no window.

## `6ddc0431` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | SpaceStation | 2025-02-01 | 2025-09-21 | 2025 Stage 1 / 2025 Stage 3 |
| 2 | SpaceStation Gaming | 2025-09-28 | 2026-07-06 | 2025 Stage 3 / 2026 Stage 2 |

- **rename**: SpaceStation -> SpaceStation Gaming: 'SpaceStation Gaming' keeps the handle of 'SpaceStation': a rename by the same organisation

**Proposal:** one organisation, no window: [SpaceStation / SpaceStation Gaming] from the first sighting of 'SpaceStation' (2025-02-01) to 2026-07-06

**Decided (rename_only):** SpaceStation -> SpaceStation Gaming: one organisation, no window.

## `bc8a3617` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | GenG | 2025-01-31 | 2025-09-27 | 2025 Stage 1 / 2025 Stage 3 |
| 2 | GenG Esports | 2025-10-05 | 2025-10-25 | 2025 Stage 3 / 2025 Stage 3 |

- **rename**: GenG -> GenG Esports: 'GenG Esports' keeps the handle of 'GenG': a rename by the same organisation

**Proposal:** one organisation, no window: [GenG / GenG Esports] from the first sighting of 'GenG' (2025-01-31) to 2025-10-25

**Decided (rename_only):** GenG -> GenG Esports: one organisation, no window.

## `f4401a61` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | PIP | 2024-03-08 | 2024-04-12 | 2024 Stage 1 / 2024 Stage 2 |
| 2 | PxG PiP | 2024-04-14 | 2024-04-29 | 2024 Stage 2 / 2024 Stage 2 |

- **rename**: PIP -> PxG PiP: 'PxG PiP' keeps the handle of 'PIP': a rename by the same organisation

**Proposal:** one organisation, no window: [PIP / PxG PiP] from the first sighting of 'PIP' (2024-03-08) to 2024-04-29

**Decided (rename_only):** PIP -> PxG PiP: one organisation, no window.

