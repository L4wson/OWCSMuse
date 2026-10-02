# Liquipedia <-> FACEIT reconciliation

Built from 2 stored Liquipedia response(s) (raw_payloads id 4215, 4218); no request was made to build this report. 315 Liquipedia records (0 placeholder rows excluded) against 322 FACEIT series in the same 21 competitions.

Nothing here links into an answer. Exact and strong links are proposed; ambiguous matches and team-name mappings wait for review, and the disagreements section says where either source may be wrong.

## Timezones

Liquipedia's `date` is UTC (it equals `extradata.timestamp`, an epoch, exactly on every row). FACEIT's times are epoch seconds, so also UTC. Across the id-linked pairs FACEIT's start minus Liquipedia's scheduled time is: median 46 min, 5th-95th percentile 25 to 129, extremes 10 to 6025; 266 of 276 inside the matching window (-60 to +360 min).

## Summary by competition

| competition | Liquipedia | FACEIT | exact | strong | ambiguous | Liquipedia only | FACEIT only | disagreements |
|---|---|---|---|---|---|---|---|---|
| Dreamhack Dallas | 15 | 14 | 0 | 0 | 0 | 15 | 14 | 0 |
| S4 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S4 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S4 NA OWCS Central - Playoffs | 8 | 10 | 5 | 0 | 3 | 0 | 5 | 0 |
| S4 NA OWCS Central - Regular Season | 28 | 28 | 20 | 0 | 8 | 0 | 8 | 0 |
| S5 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S5 EMEA OWCS Central - Regular Season | 28 | 28 | 27 | 0 | 1 | 0 | 1 | 0 |
| S5 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S5 NA OWCS Central - Regular Season | 28 | 28 | 26 | 0 | 2 | 0 | 2 | 0 |
| S6 EMEA OWCS Central - Playoffs | 8 | 10 | 7 | 0 | 1 | 0 | 2 | 0 |
| S6 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S6 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S6 NA OWCS Central - Regular Season | 28 | 28 | 27 | 0 | 1 | 0 | 1 | 0 |
| S8 EMEA OWCS Central - Playoffs | 6 | 4 | 4 | 0 | 0 | 2 | 0 | 0 |
| S8 EMEA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 0 |
| S8 NA OWCS Central - Playoffs | 6 | 4 | 3 | 0 | 1 | 2 | 0 | 0 |
| S8 NA OWCS Central - Regular Season | 15 | 15 | 13 | 0 | 2 | 0 | 1 | 0 |
| S9 EMEA OWCS Central - Playoffs | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| S9 EMEA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 5 |
| S9 NA OWCS Central - Playoffs | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| S9 NA OWCS Central - Regular Season | 15 | 15 | 14 | 0 | 1 | 0 | 1 | 5 |
| **total** | **315** | **322** | **276** | **0** | **20** | **19** | **43** | **10** |

## Needs review: ambiguous matches (20)

### 2025-01-31 22:40Z  Team Liquid 0-3 Timeless  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-d373bb83-efe8-4287-a42c-b3c963a02964:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_SWziBqkyMb_0001 --faceit-id <id>` or `--none`

### 2025-02-01 23:10Z  Rad Esports 3-0 Shikigami  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-dd4f3b33-7ff1-4a5e-8662-d3993e44c2d3:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_SWziBqkyMb_0004 --faceit-id <id>` or `--none`

### 2025-02-02 00:10Z  Timeless 2-3 NTMR  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-62e27a17-a9de-4805-991c-5d294de327d2:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_SWziBqkyMb_0005 --faceit-id <id>` or `--none`

### 2025-02-07 22:00Z  Shikigami 0-3 Timeless  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-18e81203-ca29-4811-b987-a34faf55de1d:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_ZiTj8ScREw_0001 --faceit-id <id>` or `--none`

### 2025-02-15 00:00Z  Timeless 3-1 Amplify  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-a766a513-511c-4486-b354-6e926eb1cc31:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_suX4SNOIvz_0002 --faceit-id <id>` or `--none`

### 2025-02-15 22:05Z  Timeless 3-0 Rad Esports  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-f721f872-7aa2-4a0c-a0de-3c76833769d2:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_suX4SNOIvz_0005 --faceit-id <id>` or `--none`

### 2025-02-21 22:30Z  Timeless 3-1 Avidity  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-4d1c087c-af42-46c9-9b5a-b35367032200:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_koCcO2qQx6_0001 --faceit-id <id>` or `--none`

### 2025-02-23 21:30Z  Spacestation Gaming 3-1 Timeless  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-101507eb-327b-4665-9e42-d7c33dcbbba3:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132402_koCcO2qQx6_0007 --faceit-id <id>` or `--none`

### 2025-03-01 20:40Z  Spacestation Gaming 3-0 Timeless  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-6838bec3-83ab-48ce-b6ae-83a44c221607:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132169_gyaa2X6Fe6_R01-M001 --faceit-id <id>` or `--none`

### 2025-03-02 20:45Z  Timeless 3-1 Avidity  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-d720e1ed-beea-45a5-ba35-4a326a355ff9:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132169_gyaa2X6Fe6_R01-M003 --faceit-id <id>` or `--none`

### 2025-03-08 21:15Z  Timeless 1-3 NTMR  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-a8bf8269-a354-4fa6-8b3e-190e5e9677b0:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 132169_gyaa2X6Fe6_R02-M001 --faceit-id <id>` or `--none`

### 2025-05-11 22:00Z  Geekay Esports 3-0 Supernova (American team)  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_2/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-974ff8d1-a8e8-4226-847c-29e4acf35f62:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 133394_ok3PnKtPA2_0004 --faceit-id <id>` or `--none`

### 2025-05-17 20:35Z  Sakura Esports 3-0 DhillDucks  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_2/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-1eb97a82-8842-45f2-9b65-bb63843f0d1c:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 133394_FXaPDnm2mN_0001 --faceit-id <id>` or `--none`

### 2025-06-01 17:00Z  Al Qadsiah 3-0 1DIPVS100GORILLAS  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/EMEA/Stage_2/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-fc725f79-331f-4495-8b1d-e8f39a7ea438:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 133391_E9wTaxXBNy_0003 --faceit-id <id>` or `--none`

### 2025-09-07 21:10Z  Geekay Esports 3-0 Team Z  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/NA/Stage_3/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-aeed53bb-a9e6-48be-8180-3b17ef227b7c:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 134506_AOQW3S7ZVT_0004 --faceit-id <id>` or `--none`

### 2025-10-26 18:20Z  Al Qadsiah 1-4 Twisted Minds  (bo7)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/EMEA/Stage_3
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on best_of (confirmed)
  - candidate 1-3e78e269-28b7-481c-9ccc-46c173314ab9:  - disagrees_on=['best_of']
- decide: `python -m owcsmuse liquipedia links decide 134369_wrNNtfK3Cl_R04-M001 --faceit-id <id>` or `--none`

### 2026-03-21 21:45Z  Spacestation Gaming 3-0 LuneX Gaming  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-1b0a2618-4962-4123-9847-bb08b5c2f9d4:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 136895_M79joy0VgF_0002 --faceit-id <id>` or `--none`

### 2026-03-29 22:15Z  Disguised 3-0 Team Liquid  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on score (confirmed)
  - candidate 1-472cc9eb-d7a3-4811-b633-397a99d6a502:  - disagrees_on=['score']
- decide: `python -m owcsmuse liquipedia links decide 136895_ltWetnCOzc_0005 --faceit-id <id>` or `--none`

### 2026-04-11 21:00Z  Dallas Fuel 3-1 Spacestation Gaming  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on score (confirmed)
  - candidate 1-28ea62bc-16c1-4686-b41b-479d5275d151:  - disagrees_on=['score']
- decide: `python -m owcsmuse liquipedia links decide 136256_j4vauw9a8D_R02-M001 --faceit-id <id>` or `--none`

### 2026-06-13 22:30Z  LuneX Gaming 3-0 The Kafe  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-581d94d1-7ff1-4e7f-bce8-d28dd1b91055:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 137927_RGRA8G2xWk_0003 --faceit-id <id>` or `--none`

## Linked pairs where the two sources disagree (13)

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

## Liquipedia records a FACEIT id we do not hold (2)

These are FACEIT matches that exist (Liquipedia names them) but our history crawl never found.

- 2026-04-12 17:00Z  Geekay Esports 1-3 Virtus.pro  (bo5)  FACEIT id 1-534bdff7-baf4-40ff-8d1d-fac64ee30ce3  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_1
- 2026-04-12 20:30Z  Spacestation Gaming 3-0 Team Liquid  (bo5)  FACEIT id 1-fcd2bd41-967c-450b-abac-f2137bfe308b  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1

## Duplicates

None: every record had a distinct (bracket, match2id), and no FACEIT id appears twice.

## Completeness by competition

### Dreamhack Dallas

- links: 0 exact, 0 strong, 0 ambiguous; 15 Liquipedia-only; 14 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-05-31 21:55Z  SpaceStation 3-0 SOG  (bo1, result_only)  1-c06bfd6e-cf5d-4e36-aa19-0810aee38b36
  - 2024-05-31 22:43Z  Team Falcons 3-0 ENCE  (bo1, result_only)  1-43d289c0-bb18-416b-b639-b7e076b41e7f
  - 2024-06-01 00:01Z  Toronto Defiant 3-0 Twisted Minds  (bo1, result_only)  1-d19f72eb-9c6c-4c03-9332-8b91601bb716
  - 2024-06-01 00:34Z  M80 0-3 Crazy Raccoons  (bo1, result_only)  1-fb369fac-63cb-4243-98a9-bb3aceec02e7
  - 2024-06-01 02:59Z  ENCE 3-1 SOG  (bo1, result_only)  1-cd5e474e-a6d4-49c2-ba0e-f238abfa5986
  - 2024-06-01 03:33Z  M80 3-0 Twisted Minds  (bo1, result_only)  1-e812c8d0-ceb7-42eb-9245-6f691b9c542d
  - 2024-06-01 19:24Z  SpaceStation 0-3 Team Falcons  (bo1, result_only)  1-e7bbb44a-5ebd-4a09-aad8-8273439fb572
  - 2024-06-02 13:15Z  Toronto Defiant 0-3 Crazy Raccoons  (bo1, result_only)  1-e9927ed8-0f77-46fc-bfd5-62f3706bb706
  - 2024-06-02 13:16Z  SpaceStation 3-2 M80  (bo1, result_only)  1-74e38b28-8000-4ad9-8448-475d3f329664
  - 2024-06-02 13:16Z  Toronto Defiant 1-3 ENCE  (bo1, result_only)  1-fe23288e-3419-4bcb-81b7-76526722d170
  - 2024-06-02 17:29Z  SpaceStation 3-1 ENCE  (bo1, result_only)  1-d3d9b436-5fc2-4082-b99f-16f810fcfcd0
  - 2024-06-02 19:30Z  Crazy Raccoons 2-3 Team Falcons  (bo1, result_only)  1-cd3ccc44-1b18-463d-a4de-2d400ef020e9
  - 2024-06-02 22:19Z  SpaceStation 0-3 Crazy Raccoons  (bo1, result_only)  1-88eb587c-0af4-480a-ae5a-4cb0ee9174e8
  - 2024-06-02 23:59Z  Crazy Raccoons 4-2 Team Falcons  (bo1, result_only)  1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b
- Liquipedia matches with no FACEIT counterpart:
  - 2024-05-31 20:45Z  Spacestation Gaming 3-0 NRG Shock  (bo5)  (team name not mapped: NRG Shock)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-05-31 20:45Z  Team Falcons 3-0 ENCE  (bo5)  (team name not mapped: Team Falcons, ENCE)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-05-31 22:30Z  Toronto Defiant 3-0 Twisted Minds  (bo5)  (team name not mapped: Toronto Defiant)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-05-31 23:00Z  Crazy Raccoon 3-0 M80  (bo5)  (team name not mapped: Crazy Raccoon, M80)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-01 00:30Z  NRG Shock 1-3 ENCE  (bo5)  (team name not mapped: NRG Shock, ENCE)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-01 03:00Z  M80 3-0 Twisted Minds  (bo5)  (team name not mapped: M80)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-01 18:00Z  Spacestation Gaming 0-3 Team Falcons  (bo5)  (team name not mapped: Team Falcons)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-01 20:00Z  Crazy Raccoon 3-0 Toronto Defiant  (bo5)  (team name not mapped: Crazy Raccoon, Toronto Defiant)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-01 21:30Z  Team Hydron 0-1 Team Danteh  (bo1)  (team name not mapped: Team Hydron, Team Danteh)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-01 22:00Z  Spacestation Gaming 3-2 M80  (bo5)  (team name not mapped: M80)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-02 00:00Z  Toronto Defiant 1-3 ENCE  (bo5)  (team name not mapped: Toronto Defiant, ENCE)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-02 16:00Z  ENCE 1-3 Spacestation Gaming  (bo5)  (team name not mapped: ENCE)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-02 18:00Z  Team Falcons 3-2 Crazy Raccoon  (bo5)  (team name not mapped: Team Falcons, Crazy Raccoon)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-02 20:00Z  Crazy Raccoon 3-0 Spacestation Gaming  (bo5)  (team name not mapped: Crazy Raccoon)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
  - 2024-06-02 21:20Z  Team Falcons 2-4 Crazy Raccoon  (bo7)  (team name not mapped: Team Falcons, Crazy Raccoon)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major

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

- links: 5 exact, 0 strong, 3 ambiguous; 0 Liquipedia-only; 5 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-02-27 17:55Z  Avidity 0-3 Timeless  (bo5, result_only)  1-166ea0ac-98bc-400a-89e5-71ce4a6382c3
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-02-27 17:55Z  Team Liquid 3-0 Rad  (bo5, result_only)  1-b2c78c16-02ac-4f33-b330-5f50afce955b
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-03-01 21:08Z  SpaceStation 3-0 Timeless  (bo5, complete)  1-6838bec3-83ab-48ce-b6ae-83a44c221607
  - 2025-03-02 21:21Z  Timeless 3-1 Avidity  (bo5, complete)  1-d720e1ed-beea-45a5-ba35-4a326a355ff9
  - 2025-03-08 22:05Z  NTMR 3-1 Timeless  (bo5, complete)  1-a8bf8269-a354-4fa6-8b3e-190e5e9677b0

### S4 NA OWCS Central - Regular Season

- links: 20 exact, 0 strong, 8 ambiguous; 0 Liquipedia-only; 8 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-01-31 23:22Z  Team Liquid 0-3 Timeless  (bo5, complete)  1-d373bb83-efe8-4287-a42c-b3c963a02964
  - 2025-02-01 23:41Z  Shikigami 0-3 Rad  (bo5, complete)  1-dd4f3b33-7ff1-4a5e-8662-d3993e44c2d3
  - 2025-02-02 01:29Z  Timeless 2-3 NTMR  (bo5, complete)  1-62e27a17-a9de-4805-991c-5d294de327d2
  - 2025-02-07 22:34Z  Shikigami 0-3 Timeless  (bo5, complete)  1-18e81203-ca29-4811-b987-a34faf55de1d
  - 2025-02-15 00:31Z  Timeless 3-1 Amplify  (bo5, complete)  1-a766a513-511c-4486-b354-6e926eb1cc31
  - 2025-02-15 22:39Z  Timeless 3-0 Rad  (bo5, complete)  1-f721f872-7aa2-4a0c-a0de-3c76833769d2
  - 2025-02-21 23:25Z  Timeless 3-1 Avidity  (bo5, complete)  1-4d1c087c-af42-46c9-9b5a-b35367032200
  - 2025-02-23 22:19Z  SpaceStation 3-1 Timeless  (bo5, complete)  1-101507eb-327b-4665-9e42-d7c33dcbbba3

### S5 EMEA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-06-20 22:41Z  GenG 2-3 The Ultimates  (bo5, result_only)  1-968ea5c1-265a-447a-a246-de0b376f2de7
    - suspect: no map stats, and scored within 11 s of a bracket bye
  - 2025-06-20 22:42Z  Virtuspro 3-2 Team Peps  (bo5, result_only)  1-1a645dea-e8ae-4f13-81a2-6aac72ee234a
    - suspect: no map stats, and scored within 0 s of a bracket bye

### S5 EMEA OWCS Central - Regular Season

- links: 27 exact, 0 strong, 1 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-06-01 17:40Z  1DIPv100GORILLA 0-3 Al qadsiah  (bo5, complete)  1-fc725f79-331f-4495-8b1d-e8f39a7ea438

### S5 NA OWCS Central - Playoffs

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-06-20 23:27Z  Team Liquid 3-2 Extinction  (bo5, result_only)  1-7ea45877-f025-47ad-9a8b-9f97d0ff50cf
    - suspect: no map stats, and scored within 8 s of a bracket bye
  - 2025-06-20 23:27Z  Sakura 2-3 SpaceStation  (bo5, result_only)  1-4ebc5645-079e-488b-b152-aebde924ebe9
    - suspect: no map stats, and scored within 9 s of a bracket bye

### S5 NA OWCS Central - Regular Season

- links: 26 exact, 0 strong, 2 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-05-11 22:33Z  Supernova 0-3 Geekay Esports  (bo5, complete)  1-974ff8d1-a8e8-4226-847c-29e4acf35f62
  - 2025-05-17 21:03Z  DhillDucks 0-3 Sakura  (bo5, complete)  1-1eb97a82-8842-45f2-9b65-bb63843f0d1c

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

- links: 27 exact, 0 strong, 1 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2025-09-07 21:38Z  Geekay Esports 3-0 Team Z  (bo5, result_only)  1-aeed53bb-a9e6-48be-8180-3b17ef227b7c

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

- links: 13 exact, 0 strong, 2 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2026-03-21 22:30Z  LuneX 0-3 SpaceStation Gaming  (bo5, complete)  1-1b0a2618-4962-4123-9847-bb08b5c2f9d4

### S9 EMEA OWCS Central - Playoffs

- links: 6 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 EMEA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 NA OWCS Central - Playoffs

- links: 6 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 NA OWCS Central - Regular Season

- links: 14 exact, 0 strong, 1 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2026-06-13 23:09Z  The Kafe 0-3 LuneX  (bo5, complete)  1-581d94d1-7ff1-4e7f-bce8-d28dd1b91055

