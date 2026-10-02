# Liquipedia <-> FACEIT reconciliation

Built from 3 stored Liquipedia response(s) (raw_payloads id 4215, 4218, 4219); no request was made to build this report. 451 Liquipedia records (0 placeholder rows excluded) against 473 FACEIT series in the same 29 competitions.

Nothing here links into an answer. Exact and strong links are proposed; ambiguous matches and team-name mappings wait for review, and the disagreements section says where either source may be wrong.

## Timezones

Liquipedia's `date` is UTC (it equals `extradata.timestamp`, an epoch, exactly on every row). FACEIT's times are epoch seconds, so also UTC. Across the id-linked pairs FACEIT's start minus Liquipedia's scheduled time is: median 45 min, 5th-95th percentile 24 to 105, extremes -6 to 11478; 396 of 407 inside the matching window (-60 to +360 min).

## Summary by competition

| competition | Liquipedia | FACEIT | exact | strong | ambiguous | Liquipedia only | FACEIT only | disagreements |
|---|---|---|---|---|---|---|---|---|
| Dreamhack Dallas | 15 | 14 | 0 | 0 | 14 | 1 | 14 | 0 |
| OWCS 2024: EMEA Stage 1 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 4 | 0 |
| OWCS 2024: EMEA Stage 1 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 1 - Group D | 20 | 6 | 17 | 0 | 3 | 0 | 1 | 1 |
| OWCS 2024: EMEA Stage 1 - Main Event | 14 | 14 | 10 | 0 | 4 | 0 | 3 | 0 |
| OWCS 2024: EMEA Stage 2 - Group A | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 2 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 2 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: EMEA Stage 2 - Group D | 20 | 6 | 19 | 0 | 0 | 1 | 2 | 0 |
| OWCS 2024: EMEA Stage 2 - Main Event | 14 | 14 | 14 | 0 | 0 | 0 | 0 | 0 |
| OWCS 2024: NA Stage 1 - Group A | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Group D | 20 | 6 | 20 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 1 - Main Event | 14 | 14 | 0 | 11 | 1 | 2 | 2 | 0 |
| OWCS 2024: NA Stage 2 - Group A | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Group B | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Group C | 0 | 6 | 0 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Group D | 20 | 6 | 20 | 0 | 0 | 0 | 1 | 0 |
| OWCS 2024: NA Stage 2 - Main Event | 14 | 14 | 14 | 0 | 0 | 0 | 0 | 0 |
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
| **total** | **451** | **473** | **407** | **11** | **25** | **8** | **50** | **11** |

## Needs review: ambiguous matches (20)

### 2024-03-08 18:30Z  Vanir Quick 0-3 LeftRightGnight  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-885d9b61-87bb-4abc-8388-ec6f6cca19dc:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 127212_iGL40xdPP4_0002 --faceit-id <id>` or `--none`

### 2024-03-10 19:00Z  EF Flexodiax 0-3 Vanir Quick  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-eba2680d-c444-4d68-99fa-858fef7b254c:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 127212_iGL40xdPP4_0004 --faceit-id <id>` or `--none`

### 2024-03-17 16:00Z  LeftRightGnight 0-3 Vanir Quick  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1/Group_Stage
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-b83b71e5-a19b-496d-9b13-ff62cf83a025:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 127212_iGL40xdPP4_0005 --faceit-id <id>` or `--none`

### 2024-03-21 16:30Z  Twisted Minds 3-0 Vanir Quick  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-9180da8a-080e-40bf-bd58-6213bce4b0d6:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 127216_1Sxcy6HVqj_R01-M001 --faceit-id <id>` or `--none`

### 2024-03-21 17:30Z  Vanir Quick 3-0 ROC Esports  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-71ee0038-4fa9-465d-8742-529b259c8612:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 127216_1Sxcy6HVqj_R01-M005 --faceit-id <id>` or `--none`

### 2024-03-22 17:30Z  Spacestation Gaming 3-0 Vanir Quick  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1
- why it is ambiguous: the page's FACEIT id disagrees with the FACEIT record on teams
  - candidate 1-40296472-ccfe-45f1-9f44-0d58a318219a:  - disagrees_on=['teams']
- decide: `python -m owcsmuse liquipedia links decide 127216_1Sxcy6HVqj_R02-M003 --faceit-id <id>` or `--none`

### 2024-05-31 20:45Z  Spacestation Gaming 3-0 NRG Shock  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-c06bfd6e-cf5d-4e36-aa19-0810aee38b36: SpaceStation 3-0 SOG - faceit_time=2024-05-31T21:55+00:00, minutes_from_liquipedia=71, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R01-M001 --faceit-id <id>` or `--none`

### 2024-05-31 20:45Z  Team Falcons 3-0 ENCE  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-43d289c0-bb18-416b-b639-b7e076b41e7f: Team Falcons 3-0 ENCE - faceit_time=2024-05-31T22:43+00:00, minutes_from_liquipedia=118, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R01-M002 --faceit-id <id>` or `--none`

### 2024-05-31 22:30Z  Toronto Defiant 3-0 Twisted Minds  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-d19f72eb-9c6c-4c03-9332-8b91601bb716: Toronto Defiant 3-0 Twisted Minds - faceit_time=2024-06-01T00:01+00:00, minutes_from_liquipedia=92, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R01-M004 --faceit-id <id>` or `--none`

### 2024-05-31 23:00Z  Crazy Raccoon 3-0 M80  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-fb369fac-63cb-4243-98a9-bb3aceec02e7: M80 0-3 Crazy Raccoons - faceit_time=2024-06-01T00:34+00:00, minutes_from_liquipedia=95, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R01-M003 --faceit-id <id>` or `--none`

### 2024-06-01 00:30Z  NRG Shock 1-3 ENCE  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-cd5e474e-a6d4-49c2-ba0e-f238abfa5986: ENCE 3-1 SOG - faceit_time=2024-06-01T02:59+00:00, minutes_from_liquipedia=150, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R01-M005 --faceit-id <id>` or `--none`

### 2024-06-01 03:00Z  M80 3-0 Twisted Minds  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-e812c8d0-ceb7-42eb-9245-6f691b9c542d: M80 3-0 Twisted Minds - faceit_time=2024-06-01T03:33+00:00, minutes_from_liquipedia=34, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R01-M006 --faceit-id <id>` or `--none`

### 2024-06-01 18:00Z  Spacestation Gaming 0-3 Team Falcons  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-e7bbb44a-5ebd-4a09-aad8-8273439fb572: SpaceStation 0-3 Team Falcons - faceit_time=2024-06-01T19:24+00:00, minutes_from_liquipedia=84, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R02-M001 --faceit-id <id>` or `--none`

### 2024-06-01 20:00Z  Crazy Raccoon 3-0 Toronto Defiant  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-e9927ed8-0f77-46fc-bfd5-62f3706bb706: Toronto Defiant 0-3 Crazy Raccoons - faceit_time=2024-06-02T13:15+00:00, minutes_from_liquipedia=1036, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R02-M002 --faceit-id <id>` or `--none`

### 2024-06-01 22:00Z  Spacestation Gaming 3-2 M80  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-74e38b28-8000-4ad9-8448-475d3f329664: SpaceStation 3-2 M80 - faceit_time=2024-06-02T13:16+00:00, minutes_from_liquipedia=916, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R02-M004 --faceit-id <id>` or `--none`

### 2024-06-02 00:00Z  Toronto Defiant 1-3 ENCE  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-fe23288e-3419-4bcb-81b7-76526722d170: Toronto Defiant 1-3 ENCE - faceit_time=2024-06-02T13:16+00:00, minutes_from_liquipedia=797, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R02-M003 --faceit-id <id>` or `--none`

### 2024-06-02 16:00Z  ENCE 1-3 Spacestation Gaming  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-d3d9b436-5fc2-4082-b99f-16f810fcfcd0: SpaceStation 3-1 ENCE - faceit_time=2024-06-02T17:29+00:00, minutes_from_liquipedia=89, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R03-M001 --faceit-id <id>` or `--none`

### 2024-06-02 18:00Z  Team Falcons 3-2 Crazy Raccoon  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-cd3ccc44-1b18-463d-a4de-2d400ef020e9: Crazy Raccoons 2-3 Team Falcons - faceit_time=2024-06-02T19:30+00:00, minutes_from_liquipedia=91, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
  - candidate 1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b: Crazy Raccoons 4-2 Team Falcons - faceit_time=2024-06-02T23:59+00:00, minutes_from_liquipedia=359, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of', 'score']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R04-M001 --faceit-id <id>` or `--none`

### 2024-06-02 20:00Z  Crazy Raccoon 3-0 Spacestation Gaming  (bo5)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-88eb587c-0af4-480a-ae5a-4cb0ee9174e8: SpaceStation 0-3 Crazy Raccoons - faceit_time=2024-06-02T22:19+00:00, minutes_from_liquipedia=140, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R04-M002 --faceit-id <id>` or `--none`

### 2024-06-02 21:20Z  Team Falcons 2-4 Crazy Raccoon  (bo7)
- page: https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major
- why it is ambiguous: the same two teams within a day, but the records disagree
  - candidate 1-cd3ccc44-1b18-463d-a4de-2d400ef020e9: Crazy Raccoons 2-3 Team Falcons - faceit_time=2024-06-02T19:30+00:00, minutes_from_liquipedia=-109, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of', 'score']
  - candidate 1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b: Crazy Raccoons 4-2 Team Falcons - faceit_time=2024-06-02T23:59+00:00, minutes_from_liquipedia=159, disagrees_on=['time (FACEIT has no start time: its time is when the result was entered)', 'best_of']
- decide: `python -m owcsmuse liquipedia links decide 127124_zooRkLJB0v_R05-M001 --faceit-id <id>` or `--none`


## Ambiguous matches already decided (5)

- [confirmed] 2025-10-26 18:20Z  Al Qadsiah 1-4 Twisted Minds  (bo7)  -> FACEIT 1-3e78e269-28b7-481c-9ccc-46c173314ab9  (the page's FACEIT id disagrees with the FACEIT record on best_of)
- [confirmed] 2026-03-29 22:15Z  Disguised 3-0 Team Liquid  (bo5)  -> FACEIT 1-472cc9eb-d7a3-4811-b633-397a99d6a502  (the page's FACEIT id disagrees with the FACEIT record on score)
- [confirmed] 2026-04-11 21:00Z  Dallas Fuel 3-1 Spacestation Gaming  (bo5)  -> FACEIT 1-28ea62bc-16c1-4686-b41b-479d5275d151  (the page's FACEIT id disagrees with the FACEIT record on score)
- [confirmed] 2024-03-24 18:30Z  ENCE 1-4 Twisted Minds  (bo7)  -> FACEIT 1-c5823143-d7e8-4efe-a957-6d54cfee1a8e  (the page's FACEIT id disagrees with the FACEIT record on score)
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

- links: 0 exact, 0 strong, 14 ambiguous; 1 Liquipedia-only; 14 FACEIT-only
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
  - 2024-06-01 21:30Z  Team Hydron 0-1 Team Danteh  (bo1)  (team name not mapped: Team Hydron, Team Danteh)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major

### OWCS 2024: EMEA Stage 1 - Group B

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 4 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-08 19:02Z  Quick esports 0-3 LeftRightGnight  (bo5, complete)  1-885d9b61-87bb-4abc-8388-ec6f6cca19dc
  - 2024-03-10 19:38Z  Quick esports 3-0 EF Flexodiax  (bo5, complete)  1-eba2680d-c444-4d68-99fa-858fef7b254c
  - 2024-03-17 16:46Z  LeftRightGnight 0-3 Quick esports  (bo5, complete)  1-b83b71e5-a19b-496d-9b13-ff62cf83a025
  - 2024-03-17 17:41Z  BuboSprayCheck 3-0 Quick esports  (bo5, result_only)  1-964cbe16-4ff1-4d04-854b-9ad9235a1b4f

### OWCS 2024: EMEA Stage 1 - Group C

- links: 0 exact, 0 strong, 0 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-09 20:37Z  ROC ESPORT 3-0 Sheer Cold  (bo5, complete)  1-52e63c62-6b41-4582-9f0b-31dbf92a2c0c

### OWCS 2024: EMEA Stage 1 - Group D

- links: 17 exact, 0 strong, 3 ambiguous; 0 Liquipedia-only; 1 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-18 02:01Z  SpaceStation 3-0 Ex Oblivione  (bo5, result_only)  1-3003f4e4-9805-45e7-8096-4ad0d776999b

### OWCS 2024: EMEA Stage 1 - Main Event

- links: 10 exact, 0 strong, 4 ambiguous; 0 Liquipedia-only; 3 FACEIT-only
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-21 17:13Z  Twisted Minds 3-0 Quick esports  (bo5, complete)  1-9180da8a-080e-40bf-bd58-6213bce4b0d6
  - 2024-03-21 18:23Z  ROC ESPORT 0-3 Quick esports  (bo5, complete)  1-71ee0038-4fa9-465d-8742-529b259c8612
  - 2024-03-22 18:13Z  SpaceStation 3-0 Quick esports  (bo5, complete)  1-40296472-ccfe-45f1-9f44-0d58a318219a

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

- links: 0 exact, 11 strong, 1 ambiguous; 2 Liquipedia-only; 2 FACEIT-only
  - strong: 2024-03-21 21:00Z  Toronto Defiant 3-1 LFO  (bo5) -> 1-82515b5c-13b5-468a-8fe3-7244af1d42fd - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 21:00Z  Timeless 3-2 Pirates in Pyjamas  (bo5) -> 1-8241bf51-9906-4e8d-9705-23870d2d6932 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 21:00Z  Students of the Game 0-3 M80  (bo5) -> 1-f1ba158c-daf9-4463-9a05-52f44da840e6 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 22:30Z  LFO 2-3 Pirates in Pyjamas  (bo5) -> 1-39d83a78-e8a4-4f20-92d2-6dc72f9979e2 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-21 23:30Z  Toronto Defiant 3-2 Timeless  (bo5) -> 1-4b984ffd-9868-45fa-92c5-c6a290bfe68a - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-22 20:00Z  Luminosity Gaming 0-3 M80  (bo5) -> 1-a52030d9-a7d4-4256-b55c-352b1c018e43 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-22 21:30Z  Luminosity Gaming 3-0 Pirates in Pyjamas  (bo5) -> 1-8629048b-1981-4175-91ea-6e9b6787aa2f - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-22 22:30Z  Timeless 3-1 Students of the Game  (bo5) -> 1-66cdc159-710a-4c5c-b710-e6ad39a4ccae - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-23 20:30Z  Toronto Defiant 3-0 M80  (bo5) -> 1-1d1c6149-1d38-4e62-9c7b-c2ac82ef8036 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-23 22:00Z  Luminosity Gaming 0-3 Timeless  (bo5) -> 1-2974d920-c4b7-42aa-8c8f-1d55f425a4b8 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
  - strong: 2024-03-24 21:00Z  M80 1-3 Timeless  (bo5) -> 1-dd63f190-1b64-4763-915c-e54c83d6ab56 - teams, region, time, best-of and series score agree; the only FACEIT match that fits
- FACEIT matches with no Liquipedia counterpart:
  - 2024-03-21 21:39Z  Luminosity 3-0 Shikigami  (bo5, complete)  1-3ed67b74-6ada-4f85-9244-8d7cd634e243
  - 2024-03-21 22:59Z  SOG 3-0 Shikigami  (bo5, complete)  1-ce861626-84a0-489f-9cec-624fd732663d
- Liquipedia matches with no FACEIT counterpart:
  - 2024-03-21 21:00Z  Luminosity Gaming 3-0 Shikigami  (bo5)  (team name not mapped: Shikigami)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/North_America/Stage_1
  - 2024-03-21 22:30Z  Shikigami 0-3 Students of the Game  (bo5)  (team name not mapped: Shikigami)  https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/North_America/Stage_1

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

