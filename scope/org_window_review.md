# Team-id windows: review

Source: `scope/team_name_history_2026-10-01.json`. 18 team ids carry more than one FACEIT name. Two signals per name change: the handle (a new name that contains or extends the old one is a rename by the same organisation) and the stage boundary (a wholly different name first seen in a new stage is a roster pickup by another organisation; in OWCS a pickup lands on a stage boundary). One proposal per id. Nothing here is decided: a window is applied only through `scope/org_decisions.json` (`orgs decide --from-name ... --to-name ...`).

7 id(s) where the signals disagree, listed first; 7 with a clear pickup; 4 rename-only (one organisation, no window).

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

## `d20d1868` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | team_chiime | 2024-03-08 | 2024-03-10 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Dreamland | 2024-03-17 | 2024-03-17 | 2024 Stage 1 / 2024 Stage 1 |
| 3 | Supernova | 2025-05-11 | 2025-06-14 | 2025 Stage 2 / 2025 Stage 2 |
| 4 | Team Z | 2025-09-07 | 2025-10-19 | 2025 Stage 3 / 2025 Stage 3 |

- **DISAGREE**: team_chiime -> Dreamland: 'Dreamland' is a wholly different name but appears inside the same stage as 'team_chiime' (2024 Stage 1): not a stage-boundary pickup and not a rename
- **PICKUP**: Dreamland -> Supernova: 'Supernova' is a wholly different name first seen in 2025 Stage 2 after 'Dreamland' last played in 2024 Stage 1: a roster pickup
- **PICKUP**: Supernova -> Team Z: 'Team Z' is a wholly different name first seen in 2025 Stage 3 after 'Supernova' last played in 2025 Stage 2: a roster pickup

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [team_chiime / Dreamland (?)] from the first sighting of 'team_chiime' (2024-03-08) to 2024-03-17; [Supernova] from the first sighting of 'Supernova' (2025-05-11) to 2025-06-14; [Team Z] from the first sighting of 'Team Z' (2025-09-07) to 2025-10-19

## `03869857` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | ROC ESPORT | 2024-03-08 | 2024-03-21 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Umbrellaacademy | 2024-04-12 | 2024-04-12 | 2024 Stage 2 / 2024 Stage 2 |
| 3 | ROCstars | 2024-04-20 | 2024-04-21 | 2024 Stage 2 / 2024 Stage 2 |

- **PICKUP**: ROC ESPORT -> Umbrellaacademy: 'Umbrellaacademy' is a wholly different name first seen in 2024 Stage 2 after 'ROC ESPORT' last played in 2024 Stage 1: a roster pickup
- **DISAGREE**: Umbrellaacademy -> ROCstars: 'ROCstars' is a wholly different name but appears inside the same stage as 'Umbrellaacademy' (2024 Stage 2): not a stage-boundary pickup and not a rename

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [ROC ESPORT] from the first sighting of 'ROC ESPORT' (2024-03-08) to 2024-03-21; [Umbrellaacademy / ROCstars (?)] from the first sighting of 'Umbrellaacademy' (2024-04-12) to 2024-04-21

## `0c629c99` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | team_Rakattack__ | 2024-03-08 | 2024-03-10 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Students of the Game | 2024-03-17 | 2024-03-17 | 2024 Stage 1 / 2024 Stage 1 |

- **DISAGREE**: team_Rakattack__ -> Students of the Game: 'Students of the Game' is a wholly different name but appears inside the same stage as 'team_Rakattack__' (2024 Stage 1): not a stage-boundary pickup and not a rename

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [team_Rakattack__ / Students of the Game (?)] from the first sighting of 'team_Rakattack__' (2024-03-08) to 2024-03-17

## `62f7752b` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | BuboSprayCheck | 2024-03-08 | 2024-03-21 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | ENCE | 2024-03-22 | 2024-06-02 | 2024 Stage 1 / 2024 Dreamhack Dallas |

- **DISAGREE**: BuboSprayCheck -> ENCE: 'ENCE' is a wholly different name but appears inside the same stage as 'BuboSprayCheck' (2024 Stage 1): not a stage-boundary pickup and not a rename

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [BuboSprayCheck / ENCE (?)] from the first sighting of 'BuboSprayCheck' (2024-03-08) to 2024-06-02

## `75516399` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Anyones Legend | 2026-03-22 | 2026-05-25 | 2026 Stage 1 / 2026 Stage 1 |
| 2 | 1234 | 2026-05-25 | 2026-07-01 | 2026 Stage 1 / 2026 Stage 2 |

- **DISAGREE**: Anyones Legend -> 1234: '1234' (2026-05-25..2026-07-01) sits inside 'Anyones Legend''s range (2026-03-22..2026-05-25): the id alternated between the names, which neither signal explains

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [Anyones Legend / 1234 (?)] from the first sighting of 'Anyones Legend' (2026-03-22) to 2026-07-01

## `cb90edf6` - SIGNALS DISAGREE

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Quick Esports | 2025-05-11 | 2025-10-12 | 2025 Stage 2 / 2025 Stage 3 |
| 2 | 1DIPv100GORILLA | 2025-06-01 | 2025-06-15 | 2025 Stage 2 / 2025 Stage 2 |

- **DISAGREE**: Quick Esports -> 1DIPv100GORILLA: '1DIPv100GORILLA' (2025-06-01..2025-06-15) sits inside 'Quick Esports''s range (2025-05-11..2025-10-12): the id alternated between the names, which neither signal explains

**Proposal:** no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, or a pickup inside a stage). Eras as the signals read them: [Quick Esports / 1DIPv100GORILLA (?)] from the first sighting of 'Quick Esports' (2025-05-11) to 2025-10-12

## `2b7f8ef6` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Avidity | 2025-02-01 | 2025-03-02 | 2025 Stage 1 / 2025 Stage 1 |
| 2 | Extinction | 2025-05-11 | 2025-10-12 | 2025 Stage 2 / 2025 Stage 3 |

- **PICKUP**: Avidity -> Extinction: 'Extinction' is a wholly different name first seen in 2025 Stage 2 after 'Avidity' last played in 2025 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Avidity] from the first sighting of 'Avidity' (2025-02-01) to 2025-03-02; [Extinction] from the first sighting of 'Extinction' (2025-05-11) to 2025-10-12

_Already decided: Extinction from its first 'Extinction' sighting (decided); Avidity is the id's own era._

## `a35f8d47` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Extinction | 2026-03-22 | 2026-05-29 | 2026 Stage 1 / 2026 Stage 1 |
| 2 | The Kafe | 2026-06-13 | 2026-07-01 | 2026 Stage 2 / 2026 Stage 2 |

- **PICKUP**: Extinction -> The Kafe: 'The Kafe' is a wholly different name first seen in 2026 Stage 2 after 'Extinction' last played in 2026 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Extinction] from the first sighting of 'Extinction' (2026-03-22) to 2026-05-29; [The Kafe] from the first sighting of 'The Kafe' (2026-06-13) to 2026-07-01

_Already decided: Extinction from its first 'Extinction' sighting until the first 'The Kafe' sighting (decided); The Kafe is the id's own era._

## `bb5dd404` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Ex Oblivione | 2024-03-08 | 2024-04-20 | 2024 Stage 1 / 2024 Stage 2 |
| 2 | Virtuspro | 2025-01-31 | 2025-10-19 | 2025 Stage 1 / 2025 Stage 3 |

- **PICKUP**: Ex Oblivione -> Virtuspro: 'Virtuspro' is a wholly different name first seen in 2025 Stage 1 after 'Ex Oblivione' last played in 2024 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Ex Oblivione] from the first sighting of 'Ex Oblivione' (2024-03-08) to 2024-04-20; [Virtuspro] from the first sighting of 'Virtuspro' (2025-01-31) to 2025-10-19

_Already decided: Virtus pro from 2025-01-31T19:17:07Z (decided; the first 'Virtuspro' sighting)._

## `c5116cb3` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Timeless | 2024-03-08 | 2025-03-08 | 2024 Stage 1 / 2025 Stage 1 |
| 2 | NTMR | 2025-05-10 | 2025-10-19 | 2025 Stage 2 / 2025 Stage 3 |

- **PICKUP**: Timeless -> NTMR: 'NTMR' is a wholly different name first seen in 2025 Stage 2 after 'Timeless' last played in 2025 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Timeless] from the first sighting of 'Timeless' (2024-03-08) to 2025-03-08; [NTMR] from the first sighting of 'NTMR' (2025-05-10) to 2025-10-19

## `c82570d6` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Deimpero | 2024-04-12 | 2024-04-29 | 2024 Stage 2 / 2024 Stage 2 |
| 2 | Frost Tails | 2025-05-11 | 2025-06-15 | 2025 Stage 2 / 2025 Stage 2 |

- **PICKUP**: Deimpero -> Frost Tails: 'Frost Tails' is a wholly different name first seen in 2025 Stage 2 after 'Deimpero' last played in 2024 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Deimpero] from the first sighting of 'Deimpero' (2024-04-12) to 2024-04-29; [Frost Tails] from the first sighting of 'Frost Tails' (2025-05-11) to 2025-06-15

## `cefc3f72` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | FMCL | 2024-04-12 | 2024-04-29 | 2024 Stage 2 / 2024 Stage 2 |
| 2 | NTMR | 2025-02-01 | 2025-03-10 | 2025 Stage 1 / 2025 Stage 1 |

- **PICKUP**: FMCL -> NTMR: 'NTMR' is a wholly different name first seen in 2025 Stage 1 after 'FMCL' last played in 2024 Stage 2: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [FMCL] from the first sighting of 'FMCL' (2024-04-12) to 2024-04-29; [NTMR] from the first sighting of 'NTMR' (2025-02-01) to 2025-03-10

## `ebfd8060` - PICKUP

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Quick esports | 2024-03-08 | 2024-03-22 | 2024 Stage 1 / 2024 Stage 1 |
| 2 | Ataraxia | 2024-04-12 | 2024-04-21 | 2024 Stage 2 / 2024 Stage 2 |

- **PICKUP**: Quick esports -> Ataraxia: 'Ataraxia' is a wholly different name first seen in 2024 Stage 2 after 'Quick esports' last played in 2024 Stage 1: a roster pickup

**Proposal:** one era per pickup, each the team id's own unless an org is decided for it: [Quick esports] from the first sighting of 'Quick esports' (2024-03-08) to 2024-03-22; [Ataraxia] from the first sighting of 'Ataraxia' (2024-04-12) to 2024-04-21

## `602d3c11` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | Goud Guys | 2025-09-07 | 2025-09-27 | 2025 Stage 3 / 2025 Stage 3 |
| 2 | Goud Guys ANM | 2025-09-28 | 2025-10-12 | 2025 Stage 3 / 2025 Stage 3 |

- **rename**: Goud Guys -> Goud Guys ANM: 'Goud Guys ANM' keeps the handle of 'Goud Guys': a rename by the same organisation

**Proposal:** one organisation, no window: [Goud Guys / Goud Guys ANM] from the first sighting of 'Goud Guys' (2025-09-07) to 2025-10-12

## `6ddc0431` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | SpaceStation | 2025-02-01 | 2025-09-21 | 2025 Stage 1 / 2025 Stage 3 |
| 2 | SpaceStation Gaming | 2025-09-28 | 2026-07-06 | 2025 Stage 3 / 2026 Stage 2 |

- **rename**: SpaceStation -> SpaceStation Gaming: 'SpaceStation Gaming' keeps the handle of 'SpaceStation': a rename by the same organisation

**Proposal:** one organisation, no window: [SpaceStation / SpaceStation Gaming] from the first sighting of 'SpaceStation' (2025-02-01) to 2026-07-06

## `bc8a3617` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | GenG | 2025-01-31 | 2025-09-27 | 2025 Stage 1 / 2025 Stage 3 |
| 2 | GenG Esports | 2025-10-05 | 2025-10-25 | 2025 Stage 3 / 2025 Stage 3 |

- **rename**: GenG -> GenG Esports: 'GenG Esports' keeps the handle of 'GenG': a rename by the same organisation

**Proposal:** one organisation, no window: [GenG / GenG Esports] from the first sighting of 'GenG' (2025-01-31) to 2025-10-25

## `f4401a61` - RENAME ONLY

| # | name | first seen | last seen | stage at first / last |
|---|---|---|---|---|
| 1 | PIP | 2024-03-08 | 2024-04-12 | 2024 Stage 1 / 2024 Stage 2 |
| 2 | PxG PiP | 2024-04-14 | 2024-04-29 | 2024 Stage 2 / 2024 Stage 2 |

- **rename**: PIP -> PxG PiP: 'PxG PiP' keeps the handle of 'PIP': a rename by the same organisation

**Proposal:** one organisation, no window: [PIP / PxG PiP] from the first sighting of 'PIP' (2024-03-08) to 2024-04-29

