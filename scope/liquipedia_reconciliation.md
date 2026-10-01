# Liquipedia <-> FACEIT reconciliation

Built from 1 stored Liquipedia response(s) (raw_payloads id 4215); no request was made to build this report. 300 Liquipedia records (0 placeholder rows excluded) against 308 FACEIT series in the same 20 competitions.

Nothing here links into an answer. Exact and strong links are proposed; ambiguous matches and team-name mappings wait for review, and the disagreements section says where either source may be wrong.

## Timezones

Liquipedia's `date` is UTC (it equals `extradata.timestamp`, an epoch, exactly on every row). FACEIT's times are epoch seconds, so also UTC. Across the id-linked pairs FACEIT's start minus Liquipedia's scheduled time is: median 45 min, 5th-95th percentile 25 to 129, extremes 10 to 6025; 286 of 296 inside the matching window (-60 to +360 min).

## Summary by competition

| competition | Liquipedia | FACEIT | exact | strong | ambiguous | Liquipedia only | FACEIT only | disagreements |
|---|---|---|---|---|---|---|---|---|
| S4 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S4 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S4 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S4 NA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S5 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S5 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S5 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S5 NA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S6 EMEA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 1 |
| S6 EMEA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S6 NA OWCS Central - Playoffs | 8 | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| S6 NA OWCS Central - Regular Season | 28 | 28 | 28 | 0 | 0 | 0 | 0 | 0 |
| S8 EMEA OWCS Central - Playoffs | 6 | 4 | 4 | 0 | 0 | 2 | 0 | 0 |
| S8 EMEA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 0 |
| S8 NA OWCS Central - Playoffs | 6 | 4 | 4 | 0 | 0 | 2 | 0 | 1 |
| S8 NA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 6 |
| S9 EMEA OWCS Central - Playoffs | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| S9 EMEA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 5 |
| S9 NA OWCS Central - Playoffs | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| S9 NA OWCS Central - Regular Season | 15 | 15 | 15 | 0 | 0 | 0 | 0 | 5 |
| **total** | **300** | **308** | **296** | **0** | **0** | **4** | **12** | **18** |

## Needs review: ambiguous matches (0)

None.

## Linked pairs where the two sources disagree (18)

Either source can be wrong. `maps` tells which is more likely: FACEIT's own stats count the maps played.

- [exact] 2025-10-26 18:20Z  Al Qadsiah 1-4 Twisted Minds  (bo7)
  FACEIT: 2025-10-26 19:29Z  Al qadsiah 1-4 Twisted Minds  (bo5, complete)  1-3e78e269-28b7-481c-9ccc-46c173314ab9
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2025/EMEA/Stage_3
  - **best_of**: Liquipedia 7, FACEIT 5 - a series won 4-x needs at least a best-of-7
- [exact] 2026-03-21 23:05Z  Team Liquid 3-2 Extinction  (bo5)
  FACEIT: 2026-03-22 00:18Z  Team Liquid 3-2 Extinction  (bo5, complete)  1-7a01d70f-9b52-4bc7-a010-7c15ee2fcbf3
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **teams**: Liquipedia 'Team Liquid / Extinction', FACEIT 'Team Liquid / Extinction' - the two records name different teams: the page's FACEIT id may be wrong
- [exact] 2026-03-22 22:50Z  LuneX Gaming 3-0 Extinction  (bo5)
  FACEIT: 2026-03-22 23:25Z  Extinction 0-3 LuneX  (bo5, complete)  1-4e12d13d-1bac-4aca-9155-15a27401eb57
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **teams**: Liquipedia 'LuneX Gaming / Extinction', FACEIT 'Extinction / LuneX' - the two records name different teams: the page's FACEIT id may be wrong
- [exact] 2026-03-28 22:40Z  Disguised 0-3 Extinction  (bo5)
  FACEIT: 2026-03-28 23:23Z  Extinction 3-0 Disguised  (bo5, complete)  1-c8dc6f85-9897-4dd3-bb4a-1d9783e341a6
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **teams**: Liquipedia 'Disguised / Extinction', FACEIT 'Extinction / Disguised' - the two records name different teams: the page's FACEIT id may be wrong
- [exact] 2026-03-29 21:30Z  Spacestation Gaming 3-0 Extinction  (bo5)
  FACEIT: 2026-03-29 21:39Z  SpaceStation Gaming 3-0 Extinction  (bo5, complete)  1-a6992792-70df-4dfd-a4da-7416628d9873
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **teams**: Liquipedia 'Spacestation Gaming / Extinction', FACEIT 'SpaceStation Gaming / Extinction' - the two records name different teams: the page's FACEIT id may be wrong
- [exact] 2026-03-29 22:15Z  Disguised 3-0 Team Liquid  (bo5)
  FACEIT: 2026-03-29 23:26Z  Disguised 4-0 Team Liquid  (bo5, complete)  1-472cc9eb-d7a3-4811-b633-397a99d6a502
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **score**: Liquipedia '3-0', FACEIT '4-0' - FACEIT has stats for 4 maps; Liquipedia lists 4 games; FACEIT's 4-0 is more wins than a best-of-5 allows
- [exact] 2026-04-05 21:50Z  Dallas Fuel 3-0 Extinction  (bo5)
  FACEIT: 2026-04-05 22:25Z  Dallas Fuel 3-0 Extinction  (bo5, complete)  1-f616bbb7-4e4e-411e-a212-e45339e39f26
  page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
  - **teams**: Liquipedia 'Dallas Fuel / Extinction', FACEIT 'Dallas Fuel / Extinction' - the two records name different teams: the page's FACEIT id may be wrong
- [exact] 2026-04-11 21:00Z  Dallas Fuel 3-1 Spacestation Gaming  (bo5)
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

- links: 8 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 2 FACEIT-only
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

- links: 4 exact, 0 strong, 0 ambiguous; 2 Liquipedia-only; 0 FACEIT-only
- Liquipedia matches with no FACEIT counterpart:
  - 2026-04-12 20:30Z  Spacestation Gaming 3-0 Team Liquid  (bo5)  (its FACEIT match id is not in our warehouse)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1
  - 2026-04-12 21:45Z  Dallas Fuel 4-1 Spacestation Gaming  (bo7)  (no FACEIT match with these two teams within 24 h in the same region)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1

### S8 NA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 EMEA OWCS Central - Playoffs

- links: 6 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 EMEA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 NA OWCS Central - Playoffs

- links: 6 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

### S9 NA OWCS Central - Regular Season

- links: 15 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 0 FACEIT-only

