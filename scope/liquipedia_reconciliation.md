# Liquipedia <-> FACEIT reconciliation

Built from 4 stored Liquipedia response(s) (raw_payloads id 4215, 4218, 4219, 4222); no request was made to build this report. 592 Liquipedia records (0 placeholder rows excluded) against 473 FACEIT series in the same 38 competitions.

Nothing here links into an answer. Exact and strong links are proposed; ambiguous matches and team-name mappings wait for review, and the disagreements section says where either source may be wrong.

## Timezones

Liquipedia's `date` is UTC (it equals `extradata.timestamp`, an epoch, exactly on every row). FACEIT's times are epoch seconds, so also UTC. Across the id-linked pairs FACEIT's start minus Liquipedia's scheduled time is: median 45 min, 5th-95th percentile 24 to 105, extremes -6 to 11478; 402 of 413 inside the matching window (-60 to +360 min).

## Summary by competition

| competition | Liquipedia | FACEIT | exact | strong | ambiguous | Liquipedia only | FACEIT only | disagreements |
|---|---|---|---|---|---|---|---|---|
| Dreamhack Dallas | 15 | 14 | 0 | 0 | 14 | 1 | 0 | 0 |
| Esports World Cup 2024 | 35 | 0 | 0 | 0 | 0 | 35 | 0 | 0 |
| OWCS 2024 World Finals | 14 | 0 | 0 | 0 | 0 | 14 | 0 | 0 |
| OWCS 2024: EMEA Stage 1 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 1 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 1 - Group D | 20 | 6 | 20 | 0 | 0 | 0 | 1 | 1 |
| OWCS 2024: EMEA Stage 1 - Main Event | 14 | 14 | 13 | 0 | 1 | 0 | 0 | 0 |
| OWCS 2024: EMEA Stage 2 - Group A | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 2 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 2 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 2 - Group D | 20 | 6 | 19 | 0 | 0 | 1 | 2 | 0 |
| OWCS 2024: EMEA Stage 2 - Main Event | 14 | 14 | 14 | 0 | 0 | 0 | 0 | 0 |
| OWCS 2024: NA Stage 1 - Group A | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Group D | 20 | 6 | 20 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Main Event | 14 | 14 | 0 | 13 | 1 | 0 | 0 | 0 |
| OWCS 2024: NA Stage 2 - Group A | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Group D | 20 | 6 | 20 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Main Event | 14 | 14 | 14 | 0 | 0 | 0 | 0 | 0 |
| OWCS 2025 Champions Clash | 14 | 0 | 0 | 0 | 0 | 14 | 0 | 0 |
| OWCS 2025 Midseason Championship | 28 | 0 | 0 | 0 | 0 | 28 | 0 | 0 |
| OWCS 2025 World Finals | 22 | 0 | 0 | 0 | 0 | 22 | 0 | 0 |
| OWCS 2026 Midseason Championship | 28 | 0 | 0 | 0 | 0 | 28 | 0 | 0 |
| S4 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S4 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S4 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S4 NA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S5 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S5 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S5 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S5 NA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S6 EMEA OWCS Central - Playoffs | 8 | 10 | 7 | 0 | 1 | 0 | 2 | 0 |
| S6 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S6 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S6 NA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S8 EMEA OWCS Central - Playoffs | 6 | 4 | 4 | 0 | 0 | 2 | 0 | 0 |
| S8 EMEA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 0 |
| S8 NA OWCS Central - Playoffs | 6 | 4 | 3 | 0 | 1 | 2 | 0 | 0 |
| S8 NA OWCS Central - Regular Season | 15 | 15 | 14 | 0 | 1 | 0 | 0 | 0 |
| S9 EMEA OWCS Central - Playoffs | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| S9 EMEA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 5 |
| S9 NA OWCS Central - Playoffs | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| S9 NA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 5 |
| **total** | **592** | **473** | **413** | **13** | **19** | **147** | **28** | **11** |

## Needs review: ambiguous matches (0)

None.


## Ambiguous matches already decided (19)

- [confirmed] 2025-10-26 18:20Z  Al Qadsiah 1-4 Twisted Minds  (bo7)  -> FACEIT 1-3e78e269-28b7-481c-9ccc-46c173314ab9  (the page's FACEIT id disagrees with the FACEIT record on best_of)
- [confirmed] 2026-03-29 22:15Z  Disguised 3-0 Team Liquid  (bo5)  -> FACEIT 1-472cc9eb-d7a3-4811-b633-397a99d6a502  (the page's FACEIT id disagrees with the FACEIT record on score)
- [confirmed] 2026-04-11 21:00Z  Dallas Fuel 3-1 Spacestation Gaming  (bo5)  -> FACEIT 1-28ea62bc-16c1-4686-b41b-479d5275d151  (the page's FACEIT id disagrees with the FACEIT record on score)
- [confirmed] 2024-03-24 18:30Z  ENCE 1-4 Twisted Minds  (bo7)  -> FACEIT 1-c5823143-d7e8-4efe-a957-6d54cfee1a8e  (the page's FACEIT id disagrees with the FACEIT record on score)
- [confirmed] 2024-05-31 20:45Z  Spacestation Gaming 3-0 NRG Shock  (bo5)  -> FACEIT 1-c06bfd6e-cf5d-4e36-aa19-0810aee38b36  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-05-31 20:45Z  Team Falcons 3-0 ENCE  (bo5)  -> FACEIT 1-43d289c0-bb18-416b-b639-b7e076b41e7f  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-05-31 22:30Z  Toronto Defiant 3-0 Twisted Minds  (bo5)  -> FACEIT 1-d19f72eb-9c6c-4c03-9332-8b91601bb716  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-05-31 23:00Z  Crazy Raccoon 3-0 M80  (bo5)  -> FACEIT 1-fb369fac-63cb-4243-98a9-bb3aceec02e7  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-01 00:30Z  NRG Shock 1-3 ENCE  (bo5)  -> FACEIT 1-cd5e474e-a6d4-49c2-ba0e-f238abfa5986  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-01 03:00Z  M80 3-0 Twisted Minds  (bo5)  -> FACEIT 1-e812c8d0-ceb7-42eb-9245-6f691b9c542d  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-01 18:00Z  Spacestation Gaming 0-3 Team Falcons  (bo5)  -> FACEIT 1-e7bbb44a-5ebd-4a09-aad8-8273439fb572  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-01 20:00Z  Crazy Raccoon 3-0 Toronto Defiant  (bo5)  -> FACEIT 1-e9927ed8-0f77-46fc-bfd5-62f3706bb706  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-01 22:00Z  Spacestation Gaming 3-2 M80  (bo5)  -> FACEIT 1-74e38b28-8000-4ad9-8448-475d3f329664  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-02 00:00Z  Toronto Defiant 1-3 ENCE  (bo5)  -> FACEIT 1-fe23288e-3419-4bcb-81b7-76526722d170  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-02 16:00Z  ENCE 1-3 Spacestation Gaming  (bo5)  -> FACEIT 1-d3d9b436-5fc2-4082-b99f-16f810fcfcd0  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-02 18:00Z  Team Falcons 3-2 Crazy Raccoon  (bo5)  -> FACEIT 1-cd3ccc44-1b18-463d-a4de-2d400ef020e9  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-02 20:00Z  Crazy Raccoon 3-0 Spacestation Gaming  (bo5)  -> FACEIT 1-88eb587c-0af4-480a-ae5a-4cb0ee9174e8  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-06-02 21:20Z  Team Falcons 2-4 Crazy Raccoon  (bo7)  -> FACEIT 1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b  (the same two teams within a day, but the records disagree)
- [confirmed] 2024-03-24 22:30Z  Toronto Defiant 4-0 Timeless  (bo7)  -> FACEIT 1-70cff415-3817-4144-9eca-e917f89cb6e7  (the same two teams within a day, but the records disagree)

## Linked pairs where the two sources disagree (15)

Either source can be wrong. `maps` tells which is more likely: FACEIT's own stats count the maps played.

- [ambiguous] 2025-10-26 18:20Z  Al Qadsiah 1-4 Twisted Minds  (bo7)
  FACEIT: 2025-10-26 19:29Z  Al qadsiah 1-4 Twisted Minds  (bo5, complete)  1-3e78e269-28b7-481c-9ccc-46c173314ab9
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/EMEA/Stage_3
  - **best_of**: Liquipedia 7, FACEIT 5 - a series won 4-x needs at least a best-of-7
- [ambiguous] 2026-03-29 22:15Z  Disguised 3-0 Team Liquid  (bo5)
  FACEIT: 2026-03-29 23:26Z  Disguised 4-0 Team Liquid  (bo5, complete)  1-472cc9eb-d7a3-4811-b633-397a99d6a502
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **score**: Liquipedia '3-0', FACEIT '4-0' - FACEIT has stats for 4 maps; Liquipedia lists 4 games; FACEIT's 4-0 is more wins than a best-of-5 allows
- [ambiguous] 2026-04-11 21:00Z  Dallas Fuel 3-1 Spacestation Gaming  (bo5)
  FACEIT: 2026-04-11 23:46Z  Dallas Fuel 4-1 SpaceStation Gaming  (bo5, result_only)  1-28ea62bc-16c1-4686-b41b-479d5275d151
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1
  - **score**: Liquipedia '3-1', FACEIT '4-1' - FACEIT has stats for 5 maps; Liquipedia lists 5 games; FACEIT's 4-1 is more wins than a best-of-5 allows
- [exact] 2026-06-27 17:00Z  Al Qadsiah 3-1 Telacy  (bo5)
  FACEIT: 2026-07-01 21:24Z  qadsiah 3-1 Telacy  (bo5, result_only)  1-e4092c46-924e-497d-8f7d-01fba28313d4
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-27T17:00+00:00', FACEIT '2026-07-01T21:24+00:00' - FACEIT is +100.4 h from Liquipedia's time
- [exact] 2026-06-27 18:40Z  Virtus.pro 3-0 1234  (bo5)
  FACEIT: 2026-07-01 21:26Z  Virtus pro 3-0 1234  (bo5, result_only)  1-22e3b160-b21a-4da1-937c-56a1bdbb849d
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-27T18:40+00:00', FACEIT '2026-07-01T21:26+00:00' - FACEIT is +98.8 h from Liquipedia's time
- [exact] 2026-06-27 19:30Z  Twisted Minds 3-2 Geekay Esports  (bo5)
  FACEIT: 2026-07-01 21:26Z  Twisted Minds 3-2 Geekay Esports  (bo5, result_only)  1-a823bbde-de66-4928-8527-54f4e8882293
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-27T19:30+00:00', FACEIT '2026-07-01T21:26+00:00' - FACEIT is +97.9 h from Liquipedia's time
- [exact] 2026-06-27 21:35Z  Spacestation Gaming 3-0 Team Liquid  (bo5)
  FACEIT: 2026-07-01 21:25Z  Team Liquid 0-3 SpaceStation Gaming  (bo5, result_only)  1-f152ab88-bd95-418f-9c37-f0aeadf8ab40
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-27T21:35+00:00', FACEIT '2026-07-01T21:25+00:00' - FACEIT is +95.8 h from Liquipedia's time
- [exact] 2026-06-27 22:50Z  Dallas Fuel 3-0 Disguised  (bo5)
  FACEIT: 2026-07-01 21:25Z  Dallas Fuel 3-0 Disguised  (bo5, result_only)  1-3fee5ae2-ce4b-4619-9c5f-a7eb9dda4ebe
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-27T22:50+00:00', FACEIT '2026-07-01T21:25+00:00' - FACEIT is +94.6 h from Liquipedia's time
- [exact] 2026-06-28 17:00Z  1234 3-1 Telacy  (bo5)
  FACEIT: 2026-07-01 21:15Z  Telacy 1-3 1234  (bo5, result_only)  1-4a23665a-ff32-4469-bb7e-701927b85dc8
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-28T17:00+00:00', FACEIT '2026-07-01T21:15+00:00' - FACEIT is +76.3 h from Liquipedia's time
- [exact] 2026-06-28 18:40Z  Twisted Minds 3-2 Al Qadsiah  (bo5)
  FACEIT: 2026-07-01 21:16Z  Twisted Minds 3-2 qadsiah  (bo5, result_only)  1-db6b93d1-9239-4e3f-a82a-89faec7847aa
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-28T18:40+00:00', FACEIT '2026-07-01T21:16+00:00' - FACEIT is +74.6 h from Liquipedia's time
- [exact] 2026-06-28 20:40Z  Team Liquid 3-0 The Kafe  (bo5)
  FACEIT: 2026-07-01 21:14Z  Team Liquid 3-0 The Kafe  (bo5, result_only)  1-09a2e313-ac2d-4299-8134-5cf7b78cd7be
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-28T20:40+00:00', FACEIT '2026-07-01T21:14+00:00' - FACEIT is +72.6 h from Liquipedia's time
- [exact] 2026-06-28 21:45Z  Spacestation Gaming 3-1 Disguised  (bo5)
  FACEIT: 2026-07-01 21:14Z  Disguised 1-3 SpaceStation Gaming  (bo5, result_only)  1-a6b2845d-d249-4b11-831c-d67f66eeb11b
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-28T21:45+00:00', FACEIT '2026-07-01T21:14+00:00' - FACEIT is +71.5 h from Liquipedia's time
- [exact] 2026-06-28 23:30Z  Dallas Fuel 3-1 LuneX Gaming  (bo5)
  FACEIT: 2026-07-01 21:15Z  LuneX 1-3 Dallas Fuel  (bo5, result_only)  1-01f4fb4b-10e0-47ae-af07-4fc7ab49d38c
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season
  - **date**: Liquipedia '2026-06-28T23:30+00:00', FACEIT '2026-07-01T21:15+00:00' - FACEIT is +69.8 h from Liquipedia's time
- [exact] 2024-03-09 20:00Z  ROC Esports 3-0 Sheer Cold  (bo5)
  FACEIT: 2024-03-17 19:18Z  ROC ESPORT 3-0 Sheer Cold  (bo5, result_only)  1-2e64f1ab-7cc5-43a6-8ac1-e3d8301bcb40
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage
  - **date**: Liquipedia '2024-03-09T20:00+00:00', FACEIT '2024-03-17T19:18+00:00' - FACEIT is +191.3 h from Liquipedia's time; FACEIT has no start time for this series, so its time is when the result was entered, and Liquipedia's is more likely the play time
- [ambiguous] 2024-03-24 18:30Z  ENCE 1-4 Twisted Minds  (bo7)
  FACEIT: 2024-03-24 20:15Z  Twisted Minds 5-1 ENCE  (bo7, complete)  1-c5823143-d7e8-4efe-a957-6d54cfee1a8e
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1
  - **score**: Liquipedia '1-4', FACEIT '1-5 (as LP orders them)' - FACEIT has stats for 5 maps; Liquipedia lists 5 games; FACEIT's 5-1 is more wins than a best-of-7 allows

## Liquipedia records a FACEIT id we do not hold (3)

These are FACEIT matches that exist (Liquipedia names them) but our history crawl never found.

- 2026-04-12 17:00Z  Geekay Esports 1-3 Virtus.pro  (bo5)  FACEIT id 1-534bdff7-baf4-40ff-8d1d-fac64ee30ce3  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_1
- 2026-04-12 20:30Z  Spacestation Gaming 3-0 Team Liquid  (bo5)  FACEIT id 1-fcd2bd41-967c-450b-abac-f2137bfe308b  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1
- 2024-04-12 17:30Z  Ataraxia 3-0 Metaboiz  (bo5)  FACEIT id 1-c351f92e-7422-4e9e-83ee-0a4158e1e4d1  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_2/Group_Stage

## Duplicates

None: every record had a distinct (bracket, match2id), and no FACEIT id appears twice.

## Completeness by competition

### Dreamhack Dallas

- links: 0 exact, 0 strong, 14 ambiguous; 1 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2024-06-01 21:30Z  Team Hydron 0-1 Team Danteh  (bo1)  (team name not mapped: Team Hydron, Team Danteh)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major

### Esports World Cup 2024

- links: 0 exact, 0 strong, 0 ambiguous; 35 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2024-07-24 12:00Z  Toronto Ultra 3-1 Gaimin Gladiators  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 12:00Z  Crazy Raccoon 3-0 ROC Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 13:30Z  Team Falcons 3-0 Mkers  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 13:30Z  LGD.OA 0-3 Twisted Minds  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 15:00Z  ENCE 3-0 M80  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 15:00Z  ZETA DIVISION 3-1 Bleed Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 16:30Z  Spacestation Gaming 3-1 NTMR  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 16:30Z  Fnatic 1-3 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 18:00Z  ENCE 3-1 Bleed Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 19:45Z  ZETA DIVISION 3-1 M80  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 20:00Z  Fnatic 2-3 NTMR  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-24 21:30Z  Spacestation Gaming 1-3 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 12:00Z  Toronto Ultra 3-0 ROC Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 12:00Z  Crazy Raccoon 3-0 Gaimin Gladiators  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 13:15Z  LGD.OA 3-0 Mkers  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 13:20Z  Team Falcons 3-1 Twisted Minds  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 14:30Z  Gaimin Gladiators 3-0 ROC Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 15:45Z  Twisted Minds 3-2 Mkers  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 15:45Z  Crazy Raccoon 3-0 Toronto Ultra  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 17:00Z  Team Falcons 1-3 LGD.OA  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 18:00Z  M80 3-1 Bleed Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 19:00Z  ZETA DIVISION 3-0 ENCE  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 19:45Z  Virtus.pro 3-2 NTMR  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-25 20:45Z  Spacestation Gaming 2-3 Fnatic  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024/Group_Stage
  - 2024-07-26 13:00Z  Spacestation Gaming 4-0 Gaimin Gladiators  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-26 15:00Z  ENCE 4-2 Fnatic  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-26 18:15Z  Team Falcons 4-0 M80  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-26 19:45Z  Toronto Ultra 4-1 LGD.OA  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-27 13:00Z  Crazy Raccoon 4-0 ENCE  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-27 14:50Z  ZETA DIVISION 4-2 Spacestation Gaming  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-27 18:15Z  Twisted Minds 0-4 Toronto Ultra  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-27 20:00Z  Virtus.pro 1-4 Team Falcons  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-28 15:00Z  Crazy Raccoon 4-1 Team Falcons  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-28 17:00Z  ZETA DIVISION 3-4 Toronto Ultra  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024
  - 2024-07-28 19:00Z  Crazy Raccoon 4-1 Toronto Ultra  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Esports_World_Cup/2024

### OWCS 2024 World Finals

- links: 0 exact, 0 strong, 0 ambiguous; 14 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2024-11-22 10:00Z  Team Falcons 2-1 Twisted Minds  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-22 11:30Z  Crazy Raccoon 2-0 NRG Shock  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-22 12:25Z  Spacestation Gaming 0-2 NTMR  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-22 13:30Z  Toronto Defiant 2-0 ENCE  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-22 15:25Z  Twisted Minds 3-1 Spacestation Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-22 17:15Z  NRG Shock 3-0 ENCE  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-23 10:05Z  Team Falcons 3-0 NTMR  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-23 11:20Z  Crazy Raccoon 3-0 Toronto Defiant  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-23 12:30Z  NTMR 0-3 NRG Shock  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-23 13:45Z  Toronto Defiant 3-2 Twisted Minds  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-23 15:50Z  Toronto Defiant 3-0 NRG Shock  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-24 11:20Z  Team Falcons 3-0 Crazy Raccoon  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-24 12:30Z  Crazy Raccoon 3-0 Toronto Defiant  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals
  - 2024-11-24 14:15Z  Team Falcons 4-1 Crazy Raccoon  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/World_Finals

### OWCS 2024: EMEA Stage 1 - Group B

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-17 17:41Z  BuboSprayCheck 3-0 Quick esports  (bo5, result_only)  1-964cbe16-4ff1-4d04-854b-9ad9235a1b4f

### OWCS 2024: EMEA Stage 1 - Group C

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-09 20:37Z  ROC ESPORT 3-0 Sheer Cold  (bo5, complete)  1-52e63c62-6b41-4582-9f0b-31dbf92a2c0c

### OWCS 2024: EMEA Stage 1 - Group D

- links: 20 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-18 02:01Z  SpaceStation 3-0 Ex Oblivione  (bo5, result_only)  1-3003f4e4-9805-45e7-8096-4ad0d776999b

### OWCS 2024: EMEA Stage 1 - Main Event

- links: 13 exact, 0 strong, 1 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### OWCS 2024: EMEA Stage 2 - Group A

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:31Z  SupershyOW 2-3 SpaceStation  (bo5, result_only)  1-62e84792-3827-45f0-9f3a-60976c7bda0c

### OWCS 2024: EMEA Stage 2 - Group B

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:32Z  ENCE 3-2 Team Peps  (bo5, result_only)  1-c2bdeff4-f176-4df6-9f42-70d17b9a7f9c

### OWCS 2024: EMEA Stage 2 - Group C

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:30Z  Twisted Minds 3-2 Deimpero  (bo5, result_only)  1-4e0b7e8d-4c83-4077-86cd-ba5b69e8feda

### OWCS 2024: EMEA Stage 2 - Group D

- links: 19 exact, 0 strong, 0 ambiguous; 1 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-12 17:37Z  Ataraxia 3-0 Metaboiz  (bo5, complete)  1-a7df2332-14f9-44cd-9a6d-295e1f948eb6
  - 2024-04-29 20:31Z  Peace and Love 3-2 AWW YEAH  (bo5, result_only)  1-6ff15ed2-2a89-4ac2-8363-505d1468598c
- Liquipedia matches with no FACEIT counterpart:
  - 2024-04-12 17:30Z  Ataraxia 3-0 Metaboiz  (bo5)  (its FACEIT match id is not in our warehouse)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_2/Group_Stage

### OWCS 2024: EMEA Stage 2 - Main Event

- links: 14 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### OWCS 2024: NA Stage 1 - Group A

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-17 17:42Z  Toronto Defiant 3-0 Shikigami  (bo5, result_only)  1-cb0f15e7-122e-4c9f-8d06-425a95b8af60

### OWCS 2024: NA Stage 1 - Group B

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-17 22:11Z  LFO 0-3 Luminosity  (bo5, result_only)  1-5162963a-2def-4a5a-8b4c-a5738f3dcd71

### OWCS 2024: NA Stage 1 - Group C

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-17 23:11Z  Timeless 3-0 M80  (bo5, result_only)  1-87d12de9-5668-485d-b23d-db1cf7d38c90

### OWCS 2024: NA Stage 1 - Group D

- links: 20 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-17 23:45Z  Students of the Game 0-3 PIP  (bo5, result_only)  1-388f8a13-28fb-4597-884d-70c82bc17d52

### OWCS 2024: NA Stage 1 - Main Event

- links: 0 exact, 13 strong, 1 ambiguous; 0 Liquipedia-only; 0 FACEIT-only
  - strong: 2024-03-21 21:00Z  Toronto Defiant 3-1 LFO  (bo5) -> 1-82515b5c-13b5-468a-8fe3-7244af1d42fd - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 21:00Z  Timeless 3-2 Pirates in Pyjamas  (bo5) -> 1-8241bf51-9906-4e8d-9705-23870d2d6932 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 21:00Z  Luminosity Gaming 3-0 Shikigami  (bo5) -> 1-3ed67b74-6ada-4f85-9244-8d7cd634e243 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 21:00Z  Students of the Game 0-3 M80  (bo5) -> 1-f1ba158c-daf9-4463-9a05-52f44da840e6 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 22:30Z  LFO 2-3 Pirates in Pyjamas  (bo5) -> 1-39d83a78-e8a4-4f20-92d2-6dc72f9979e2 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 22:30Z  Shikigami 0-3 Students of the Game  (bo5) -> 1-ce861626-84a0-489f-9cec-624fd732663d - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 23:30Z  Toronto Defiant 3-2 Timeless  (bo5) -> 1-4b984ffd-9868-45fa-92c5-c6a290bfe68a - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-22 20:00Z  Luminosity Gaming 0-3 M80  (bo5) -> 1-a52030d9-a7d4-4256-b55c-352b1c018e43 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-22 21:30Z  Luminosity Gaming 3-0 Pirates in Pyjamas  (bo5) -> 1-8629048b-1981-4175-91ea-6e9b6787aa2f - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-22 22:30Z  Timeless 3-1 Students of the Game  (bo5) -> 1-66cdc159-710a-4c5c-b710-e6ad39a4ccae - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-23 20:30Z  Toronto Defiant 3-0 M80  (bo5) -> 1-1d1c6149-1d38-4e62-9c7b-c2ac82ef8036 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-23 22:00Z  Luminosity Gaming 0-3 Timeless  (bo5) -> 1-2974d920-c4b7-42aa-8c8f-1d55f425a4b8 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-24 21:00Z  M80 1-3 Timeless  (bo5) -> 1-dd63f190-1b64-4763-915c-e54c83d6ab56 - teams, region, time, best-of and series score agree; the only FACEIT match that fits

### OWCS 2024: NA Stage 2 - Group A

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:33Z  Toronto Defiant 3-2 Who is Goldfish  (bo5, result_only)  1-6314a203-e15a-4ad7-bb1c-0e4186a202e3

### OWCS 2024: NA Stage 2 - Group B

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:33Z  Luminosity 3-2 Citrus Nation  (bo5, result_only)  1-98b1c86f-dfa4-44f2-9358-5fb5fb0674a9

### OWCS 2024: NA Stage 2 - Group C

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:33Z  M80 3-2 PxG PiP  (bo5, result_only)  1-3fdc92e9-e0d7-45fb-9f81-6cfd84acfa1f

### OWCS 2024: NA Stage 2 - Group D

- links: 20 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-04-29 20:32Z  FMCL 2-3 SOG  (bo5, result_only)  1-48b33003-484d-4af2-9038-8a742131edbf

### OWCS 2024: NA Stage 2 - Main Event

- links: 14 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### OWCS 2025 Champions Clash

- links: 0 exact, 0 strong, 0 ambiguous; 14 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2025-04-18 05:10Z  Team Falcons 2-1 Al Qadsiah  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-18 07:00Z  Virtus.pro 0-2 Once Again  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-18 08:10Z  NTMR 2-0 Team CC (Chinese orgless team)  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-18 09:45Z  Crazy Raccoon 2-0 Spacestation Gaming  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-18 10:30Z  Al Qadsiah 0-3 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-18 11:35Z  Team CC (Chinese orgless team) 0-3 Spacestation Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-19 05:00Z  NTMR 3-1 Crazy Raccoon  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-19 06:55Z  Team Falcons 3-2 Once Again  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-19 09:00Z  Crazy Raccoon 3-1 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-19 10:35Z  Once Again 3-1 Spacestation Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-19 12:10Z  Crazy Raccoon 3-0 Once Again  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-20 06:15Z  Team Falcons 3-0 NTMR  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-20 07:50Z  NTMR 0-3 Crazy Raccoon  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash
  - 2025-04-20 09:30Z  Team Falcons 2-4 Crazy Raccoon  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Champions_Clash

### OWCS 2025 Midseason Championship

- links: 0 exact, 0 strong, 0 ambiguous; 28 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2025-07-31 13:20Z  All Gamers Global 0-2 Team Falcons  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 13:30Z  Weibo Gaming 2-1 Virtus.pro  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 14:25Z  Crazy Raccoon 2-0 VARREL  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 15:10Z  Team Liquid 2-0 ROC Esports  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 15:45Z  Al Qadsiah 2-0 Team CC (Chinese orgless team)  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 16:15Z  Geekay Esports 2-0 ZoKorp Esports  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 16:40Z  Twisted Minds 1-2 Sign Esports  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 17:05Z  T1 2-0 The Gatos Guapos  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 18:05Z  Crazy Raccoon 3-2 Team Liquid  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 18:10Z  Team Falcons 3-2 Weibo Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 20:10Z  Sign Esports 0-3 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-07-31 20:10Z  Al Qadsiah 3-2 Geekay Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 13:05Z  All Gamers Global 0-3 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 13:10Z  Team CC (Chinese orgless team) 3-0 ZoKorp Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 14:35Z  Twisted Minds 3-0 The Gatos Guapos  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 14:45Z  VARREL 3-2 ROC Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 16:30Z  Geekay Esports 3-2 Team CC (Chinese orgless team)  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 17:10Z  Weibo Gaming 2-3 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 19:25Z  Team Liquid 3-0 VARREL  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-01 20:55Z  Sign Esports 0-3 Twisted Minds  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship/Group_Stage
  - 2025-08-02 13:15Z  Crazy Raccoon 2-3 Twisted Minds  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-02 15:30Z  Al Qadsiah 3-0 Virtus.pro  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-02 17:00Z  T1 3-0 Team Liquid  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-02 18:35Z  Team Falcons 3-2 Geekay Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-03 13:00Z  Twisted Minds 2-3 Al Qadsiah  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-03 15:25Z  T1 1-3 Team Falcons  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-03 17:30Z  Twisted Minds 3-1 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship
  - 2025-08-03 19:20Z  Al Qadsiah 0-4 Team Falcons  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/Midseason_Championship

### OWCS 2025 World Finals

- links: 0 exact, 0 strong, 0 ambiguous; 22 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2025-11-26 11:05Z  Team CC (Chinese orgless team) 1-2 T1  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-26 12:40Z  Team Falcons 2-1 VARREL  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-26 14:00Z  Al Qadsiah 2-0 Geekay Esports  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-26 15:05Z  Spacestation Gaming 2-1 Team Peps  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-27 11:15Z  Crazy Raccoon 3-0 Spacestation Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-27 12:30Z  Weibo Gaming 0-3 Al Qadsiah  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-27 13:50Z  Twisted Minds 3-2 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-27 16:10Z  Team Liquid 1-3 Team Falcons  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-28 11:30Z  Weibo Gaming 2-0 Team CC (Chinese orgless team)  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-28 12:45Z  Spacestation Gaming 2-0 VARREL  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-28 13:40Z  T1 2-1 Geekay Esports  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-28 15:00Z  Team Liquid 2-0 Team Peps  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-28 16:05Z  Weibo Gaming 3-0 Spacestation Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-28 17:30Z  Team Liquid 0-3 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-29 10:05Z  Crazy Raccoon 1-3 Al Qadsiah  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-29 11:55Z  Twisted Minds 3-0 Team Falcons  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-29 13:25Z  Crazy Raccoon 3-0 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-29 14:50Z  Team Falcons 3-0 Weibo Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-29 16:50Z  Crazy Raccoon 3-2 Team Falcons  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-30 10:15Z  Al Qadsiah 3-1 Twisted Minds  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-30 12:10Z  Twisted Minds 3-1 Crazy Raccoon  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals
  - 2025-11-30 15:30Z  Al Qadsiah 1-4 Twisted Minds  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/World_Finals

### OWCS 2026 Midseason Championship

- links: 0 exact, 0 strong, 0 ambiguous; 28 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2026-07-29 10:15Z  ZETA DIVISION 2-0 VARREL  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 11:15Z  Crazy Raccoon 2-0 Team Secret  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 12:45Z  Geekay Esports 2-0 All Gamers Global  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 14:00Z  Spacestation Gaming 2-1 JD Gaming  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 15:30Z  T1 1-2 Twisted Minds  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 17:20Z  Weibo Gaming 2-1 Team Liquid  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 18:50Z  Virtus.pro 2-0 9z Team  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-29 19:45Z  Dallas Fuel 0-2 Team Falcons  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-30 10:05Z  Crazy Raccoon 2-0 Spacestation Gaming  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-30 10:55Z  Weibo Gaming 2-1 Team Falcons  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-30 12:25Z  All Gamers Global 1-2 VARREL  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-30 13:45Z  Team Secret 0-2 JD Gaming  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-30 14:35Z  9z Team 0-2 T1  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-30 15:25Z  Team Liquid 0-2 Dallas Fuel  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-31 10:10Z  Virtus.pro 0-2 Twisted Minds  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-31 11:00Z  Geekay Esports 1-2 ZETA DIVISION  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-31 12:15Z  Team Falcons 0-2 T1  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-31 13:10Z  Spacestation Gaming 2-1 VARREL  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-31 14:25Z  Virtus.pro 0-2 Dallas Fuel  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-07-31 15:15Z  Geekay Esports 2-0 JD Gaming  (bo3)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship/Group_Stage
  - 2026-08-01 10:00Z  Crazy Raccoon 0-3 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-01 11:40Z  ZETA DIVISION 3-0 Dallas Fuel  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-01 13:00Z  Weibo Gaming 3-1 Spacestation Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-01 14:50Z  Twisted Minds 3-1 Geekay Esports  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-02 10:00Z  ZETA DIVISION 3-0 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-02 11:20Z  Twisted Minds 3-2 Weibo Gaming  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-02 13:45Z  Weibo Gaming 0-3 T1  (bo5)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship
  - 2026-08-02 15:30Z  Twisted Minds 2-4 ZETA DIVISION  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/Midseason_Championship

### S4 EMEA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-02-27 17:35Z  Twisted Minds 0-3 GenG  (bo5, result_only)  1-4f48f8a3-03cf-4017-8103-49cbae26efac
    - suspect: no map stats, and scored within 12 s of a bracket bye
  - 2025-02-27 17:35Z  Al qadsiah 3-0 The Ultimates  (bo5, result_only)  1-9b9b0b80-c697-482a-a514-bdd2dfeaf2ec
    - suspect: no map stats, and scored within 11 s of a bracket bye

### S4 EMEA OWCS Central - Regular Season

- links: 28 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S4 NA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-02-27 17:55Z  Avidity 0-3 Timeless  (bo5, result_only)  1-166ea0ac-98bc-400a-89e5-71ce4a6382c3
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-02-27 17:55Z  Team Liquid 3-0 Rad  (bo5, result_only)  1-b2c78c16-02ac-4f33-b330-5f50afce955b
    - suspect: no map stats, and scored within 11 s of a bracket bye

### S4 NA OWCS Central - Regular Season

- links: 28 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S5 EMEA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-06-20 22:41Z  GenG 2-3 The Ultimates  (bo5, result_only)  1-968ea5c1-265a-447a-a246-de0b376f2de7
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-06-20 22:42Z  Virtuspro 3-2 Team Peps  (bo5, result_only)  1-1a645dea-e8ae-4f13-81a2-6aac72ee234a
    - suspect: no map stats, and scored within 0 s of a bracket bye

### S5 EMEA OWCS Central - Regular Season

- links: 28 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S5 NA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-06-20 23:27Z  Team Liquid 3-2 Extinction  (bo5, result_only)  1-7ea45877-f025-47ad-9a8b-9f97d0ff50cf
    - suspect: no map stats, and scored within 8 s of a bracket bye
  - 2025-06-20 23:27Z  Sakura 2-3 SpaceStation  (bo5, result_only)  1-4ebc5645-079e-488b-b152-aebde924ebe9
    - suspect: no map stats, and scored within 9 s of a bracket bye

### S5 NA OWCS Central - Regular Season

- links: 28 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S6 EMEA OWCS Central - Playoffs

- links: 7 exact, 0 strong, 1 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-10-18 14:58Z  Vision Esports 3-0 Team Peps  (bo5, result_only)  1-5381cfcd-4f64-47dc-b30d-b9a9da831192
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-10-18 14:58Z  Twisted Minds 3-0 GenG Esports  (bo5, result_only)  1-fbdec08a-24cb-42ae-8dd6-b39ba9caddc7
    - suspect: no map stats, and scored within 11 s of a bracket bye

### S6 EMEA OWCS Central - Regular Season

- links: 28 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S6 NA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-10-18 15:09Z  NTMR 3-0 Sakura Esports  (bo5, result_only)  1-e55d25fb-3a7d-4b31-91b4-6985eb88a15c
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-10-18 15:09Z  Geekay Esports 3-0 Team Z  (bo5, result_only)  1-1d9fdb85-b479-4cf5-abb6-11f77e9870f0
    - suspect: no map stats, and scored within 1 s of a bracket bye

### S6 NA OWCS Central - Regular Season

- links: 28 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S8 EMEA OWCS Central - Playoffs

- links: 4 exact, 0 strong, 0 ambiguous; 2 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2026-04-12 17:00Z  Geekay Esports 1-3 Virtus.pro  (bo5)  (its FACEIT match id is not in our warehouse)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_1
  - 2026-04-12 18:35Z  Twisted Minds 4-1 Virtus.pro  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_1

### S8 EMEA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S8 NA OWCS Central - Playoffs

- links: 3 exact, 0 strong, 1 ambiguous; 2 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2026-04-12 20:30Z  Spacestation Gaming 3-0 Team Liquid  (bo5)  (its FACEIT match id is not in our warehouse)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1
  - 2026-04-12 21:45Z  Dallas Fuel 4-1 Spacestation Gaming  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1

### S8 NA OWCS Central - Regular Season

- links: 14 exact, 0 strong, 1 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 EMEA OWCS Central - Playoffs

- links: 6 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 EMEA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 NA OWCS Central - Playoffs

- links: 6 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 NA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

