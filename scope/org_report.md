# Org identity proposals

Generated 2026-09-19T00:50:52+00:00. 12 candidate pairs: 6 strong, 3 needing review, 9 already merged, 3 reviewed and rejected.

A pair is proposed only with evidence. Names that merely look alike are never merged: a pair whose names differ must be carried by roster overlap and is marked **review required**. Nothing merges until it is in `scope/org_decisions.json`.

Roster overlap is the weakest of the three signals, not the strongest. Whole rosters move between organisations, so a squad that transferred looks exactly like a rename: the one real rename here (Al qadsiah / qadsiah) shared 1 of 8 players, while four pairs at 80-100% overlap are distinct orgs. Name identity is what merges a pair; overlap only corroborates it.

Apply or turn down one with:

```
python -m owcsmuse orgs decide <team_id> --org <org-id> --org-name "<Display Name>" --note "..."
python -m owcsmuse orgs reject <team_id_a> <team_id_b> --reason "..."   # decided: not the same org
python -m owcsmuse orgs load      # write decisions into orgs / team_orgs
```

## Strong proposals (identical names, corroborated)

| decided | org | overlap | shared | names | seasons | matches | team ids | evidence |
|---|---|---|---|---|---|---|---|---|
| YES | Who Is Goldfish | 100% | 5/5 | Who Is Goldfish / Who is Goldfish | 2024 | 6 | `1552cd57-967b-4d4e-b5ec-87b1a8318ee4`<br>`6468b0e3-30d7-42e2-bc89-d71dd875eeb2` | names fold identically ('who is goldfish')<br>roster overlap 100%: 5 of the smaller 5-player roster shared<br>match windows overlap, so these may be two teams that coexisted<br>seasons 2024; 2 + 4 matches **note:** merged on name identity: names fold identically ('who is goldfish') |
| YES | Dhillducks | 57% | 4/7 | DhillDucks / Dhillducks | 2024, 2025, 2026 | 19 | `c6248ff8-64ff-47ad-8602-7eec0eeda9b0`<br>`db345f31-2da8-4212-b3f5-5c5442e17f68` | names fold identically ('dhillducks')<br>roster overlap 57%: 4 of the smaller 7-player roster shared<br>match windows do not overlap, 225 day gap (2024-04-12..2025-10-12 then 2026-05-26..2026-05-27)<br>seasons 2024, 2025, 2026; 17 + 2 matches **note:** merged on name identity: names fold identically ('dhillducks') |
| YES | Team Peps | 33% | 4/12 | Team Peps / Team Peps | 2024, 2025, 2026 | 56 | `9870dc60-9607-4fde-8e81-c729349f4087`<br>`e85cb266-39cc-4840-ac56-c22c942bd093` | names fold identically ('team peps')<br>roster overlap 33%: 4 of the smaller 12-player roster shared<br>match windows do not overlap, 276 day gap (2024-03-08..2024-04-29 then 2025-01-31..2026-05-27)<br>seasons 2024, 2025, 2026; 40 + 16 matches **note:** merged on name identity: names fold identically ('team peps') |
| YES | NTMR | 15% | 2/13 | NTMR / NTMR | 2024, 2025 | 65 | `c5116cb3-1e5d-457f-9c4a-52a5dd75ab6e`<br>`cefc3f72-5641-43f4-ae4f-bb5eee3b564d` | names fold identically ('ntmr')<br>roster overlap 15%: 2 of the smaller 13-player roster shared<br>match windows overlap, so these may be two teams that coexisted<br>seasons 2024, 2025; 45 + 20 matches **note:** merged on name identity: names fold identically ('ntmr') |
| YES | Vision Esports | 14% | 1/7 | Vision Esports / Vision Esports | 2025 | 17 | `0fb417ca-dbf3-4fa7-a4b7-538f73234069`<br>`fca26779-47e9-4270-ad26-a3564812c1c6` | names fold identically ('vision esports')<br>roster overlap 14%: 1 of the smaller 7-player roster shared<br>match windows do not overlap, 195 day gap (2025-02-01..2025-02-23 then 2025-09-06..2025-10-19)<br>seasons 2025; 7 + 10 matches **note:** merged on name identity: names fold identically ('vision esports') |
| YES | Sheer Cold | 0% | 0/6 | Sheer Cold / Sheer Cold | 2024 | 8 | `13576d6f-57ae-4b08-9755-89c14455667e`<br>`23527e20-26a5-4798-a832-088749c4bde1` | names fold identically ('sheer cold')<br>roster overlap 0%: 0 of the smaller 6-player roster shared<br>match windows do not overlap, 21 day gap (2024-03-08..2024-03-21 then 2024-04-12..2024-04-14)<br>seasons 2024; 2 + 6 matches **note:** merged on name identity: names fold identically ('sheer cold') |

## Review required (names differ, merge only on roster evidence)

| decided | org | overlap | shared | names | seasons | matches | team ids | evidence |
|---|---|---|---|---|---|---|---|---|
| YES | Students of the Game | 100% | 5/5 | Students of the Game / SOG | 2024 | 16 | `0c629c99-0333-47f6-96c9-87c0617a9d21`<br>`d566d889-7885-4e74-a9dc-d29c111d2c1e` | names differ ('Students of the Game' vs 'SOG') and neither contains the other - requires review<br>roster overlap 100%: 5 of the smaller 5-player roster shared<br>match windows do not overlap, 3 day gap (2024-03-08..2024-03-17 then 2024-03-21..2024-06-01)<br>seasons 2024; 3 + 13 matches **note:** reviewed merge: same org, 100% roster overlap across a 3 day gap in 2024; SOG is the abbreviation the org played under later that season |
| YES | Virtus pro | 60% | 3/5 | Virtuspro / Virtus pro | 2024, 2025, 2026 | 60 | `bb5dd404-213c-430f-8d12-8687fc3ff747`<br>`c02a9899-1ab2-46fb-a87d-8e7dcecb0cba` | names differ ('Virtuspro' vs 'Virtus pro') and neither contains the other - requires review<br>roster overlap 60%: 3 of the smaller 5-player roster shared<br>match windows do not overlap, 152 day gap (2024-03-08..2025-10-19 then 2026-03-21..2026-07-05)<br>seasons 2024, 2025, 2026; 45 + 15 matches **note:** reviewed merge: same org, one FACEIT name with a space and one without |
| YES | qadsiah | 12% | 1/8 | Al qadsiah / qadsiah | 2025, 2026 | 48 | `10fdda79-bf26-4b61-8823-48d9d531c027`<br>`97ef2653-81b3-45e4-b57f-4df4c27d3ea0` | names differ but one name's tokens are inside the other (qadsiah in al qadsiah) - requires review<br>roster overlap 12%: 1 of the smaller 8-player roster shared<br>match windows do not overlap, 145 day gap (2025-01-31..2025-10-26 then 2026-03-21..2026-07-04)<br>seasons 2025, 2026; 34 + 14 matches **note:** merged on name identity: names differ but one name's tokens are inside the other (qadsiah in al qadsiah) - requires review |

## Reviewed and rejected (3)

Decided: these are different organisations. They are not proposed again.

| names | overlap | shared | seasons | reason | team ids |
|---|---|---|---|---|---|
| Geekay Esports / NTMR | 100% | 5/5 | 2024, 2025 | reviewed rejection: distinct organisations. The roster overlap is a squad that transferred, not a rename; the names share no tokens. | `590b7d3b-a200-47b9-a967-f02274c1977b`<br>`cefc3f72-5641-43f4-ae4f-bb5eee3b564d` |
| NTMR / Dallas Fuel | 80% | 4/5 | 2024, 2025, 2026 | reviewed rejection: distinct organisations. The roster overlap is a squad that transferred, not a rename; the names share no tokens. | `c5116cb3-1e5d-457f-9c4a-52a5dd75ab6e`<br>`cd157523-5c58-41bc-b62d-e1a635ea61b8` |
| Al qadsiah / Geekay Esports | 67% | 4/6 | 2025, 2026 | reviewed rejection: distinct organisations. The roster overlap is a squad that transferred, not a rename; the names share no tokens. | `10fdda79-bf26-4b61-8823-48d9d531c027`<br>`46f8e560-76fe-4b5f-85e7-397957e0dc74` |

## Unmapped team ids (62)

These stay queryable as themselves; nothing is assumed about them.

| team | matches | seasons | team_id |
|---|---|---|---|
| Twisted Minds | 66 | 2024, 2025, 2026 | `2b9f2e7a-f91a-4597-b2fa-d413eaed605e` |
| SpaceStation Gaming | 50 | 2025, 2026 | `6ddc0431-0e9c-4b95-8658-e3e5b181d0bf` |
| Team Liquid | 48 | 2025, 2026 | `a58dedff-8045-46be-a13e-2402495b6a9d` |
| LuneX | 48 | 2024, 2025, 2026 | `0464a373-df2f-4d23-93f5-80cbaa07802f` |
| GenG Esports | 31 | 2025 | `bc8a3617-c6e6-4fbf-9283-c7d9dd2180ff` |
| Extinction | 27 | 2025 | `2b7f8ef6-bb71-4d2f-a66c-5d2a571138ae` |
| bye | 26 | 2025 | `bye` |
| Geekay Esports | 23 | 2025 | `590b7d3b-a200-47b9-a967-f02274c1977b` |
| The Ultimates | 23 | 2025 | `3eaeefbc-6abf-4d54-aeb2-2790e3e21752` |
| Team Z | 20 | 2024, 2025 | `d20d1868-8937-4a85-8706-bf936d265392` |
| ENCE | 19 | 2024 | `62f7752b-0b79-4fa8-9a23-78800e2b4539` |
| SpaceStation | 19 | 2024 | `a359db61-26e2-44e0-8961-e0b373f4db21` |
| Toronto Defiant | 18 | 2024 | `8f632648-b26f-4554-bae4-40f9aee1773b` |
| M80 | 18 | 2024 | `3aca5abd-ee5d-4542-92e9-392b6f5d0dbc` |
| Geekay Esports | 16 | 2026 | `46f8e560-76fe-4b5f-85e7-397957e0dc74` |
| Dallas Fuel | 16 | 2026 | `cd157523-5c58-41bc-b62d-e1a635ea61b8` |
| Shikigami | 15 | 2024, 2025 | `ec69a520-047f-4754-b36e-b0c95e2066ff` |
| Quick Esports | 14 | 2025 | `cb90edf6-60cb-4f73-8172-bf944729a114` |
| The Kafe | 14 | 2026 | `a35f8d47-7487-4249-a3fb-94aefa2ac8d0` |
| 1234 | 13 | 2026 | `75516399-4c1d-40fc-bb46-a887edadc5a2` |
| PxG PiP | 13 | 2024 | `f4401a61-5010-484b-8429-ad09e524b097` |
| Luminosity | 13 | 2024 | `d4ec89d7-7d41-4c0e-9834-fbf87a199347` |
| Frost Tails | 13 | 2024, 2025 | `c82570d6-ded9-4678-8d32-398db37faa98` |
| Disguised | 13 | 2026 | `968066cc-6255-4fcd-8d9b-bc455ca9d998` |
| Citrus Nation | 11 | 2024 | `35fd77ed-a916-4f76-aafd-af3d57ad84cb` |
| Ataraxia | 10 | 2024 | `ebfd8060-fcbd-467b-9701-0801b2260a9c` |
| AWW YEAH | 9 | 2024 | `90b2fd83-bb47-4286-8f62-a16eb6ce650b` |
| Telacy | 9 | 2026 | `b50813d6-3c84-4d07-adf4-bc9df069e13a` |
| ROCstars | 8 | 2024 | `03869857-7f73-4176-a27d-dafcc8d469ae` |
| Peace and Love | 7 | 2024 | `d8cd2ece-fe1e-46f1-bf8d-00fcd5ab71ab` |
| Goud Guys ANM | 7 | 2025 | `602d3c11-ccee-404d-858e-b03267c83d47` |
| SupershyOW | 7 | 2024 | `98798472-6b02-4707-8827-0b7f5f3075b9` |
| Sakura | 7 | 2025 | `b6e7f5e3-cfed-4d10-9a58-fa7a0e3812f0` |
| Amplify | 7 | 2025 | `c34ba98e-8985-4140-903a-82ecacdf1485` |
| LFO | 6 | 2024 | `a24592c1-8b7f-414b-a751-0e43b6da1522` |
| Daybreak | 5 | 2024 | `cce69e3f-b11e-4635-8370-8ddd371f690a` |
| Crazy Raccoons | 5 | 2024 | `4cbafe8a-486c-41f9-82e3-b7b84f1855d7` |
| A One Man Army | 5 | 2024 | `6c39d9d5-c34d-462c-b753-d520d48a6b45` |
| EF Flexodiax | 4 | 2024 | `241bb1a3-7e39-46ba-8ff0-672a7a7796d6` |
| Team Falcons | 4 | 2024 | `2ab92d33-4c33-46e1-a13f-743a95291d0e` |
| nuage | 3 | 2024 | `b696c66d-dc53-4a60-8e50-2009b03c110d` |
| LeftRightGnight | 3 | 2024 | `3c56dcad-8041-4214-86bd-ac75db1d610f` |
| Vice | 3 | 2024 | `3a72be04-0086-4831-8e2b-eb85a00cacc5` |
| Obsidian | 3 | 2024 | `fee18be3-c43c-4f24-85ce-7471248dc4ed` |
| Celtas | 3 | 2024 | `0dcea68d-6624-4ae8-bbbb-a63c3e6546a1` |
| Kintsugi | 3 | 2026 | `a791e2fa-32bd-418f-b7c8-e924e30da4e7` |
| team_sawhill | 2 | 2024 | `ed04d97f-9a2d-4da2-abf3-de55ad19054d` |
| Metaboiz | 2 | 2024 | `6c2f5887-e6e6-44a8-8f9c-3bb3bcfb9b83` |
| Visored | 2 | 2024 | `626ee9e6-1bb4-4a77-8660-a220fcf7a178` |
| nah id win | 2 | 2024 | `61a69c78-3207-4687-b249-68475fc85a20` |
| team_POUNDTOWNBOW | 2 | 2024 | `59999af9-9b5c-44f1-b794-5fbf8326801e` |
| Star Bits x Hypnos | 2 | 2026 | `444668eb-3722-42e6-8e1e-ed7e1134c522` |
| Bingus | 2 | 2024 | `d2e11bea-41a3-43ea-91df-b6f05e4bde93` |
| TML Nightmare | 2 | 2024 | `dc443c37-abc3-4e69-9e4c-56f966f64d8b` |
| A-Square Tengu | 2 | 2024 | `ed0289e5-5c95-4da2-a966-e7ae72040595` |
| SCHMUNGUS | 2 | 2024 | `865c189c-702d-4896-bd99-56fae201451e` |
| Final Gambit | 2 | 2024 | `6ec39b17-1e07-41df-b720-5a0588b5fcae` |
| ZETA DIVISION | 1 |  | `1b59c609-be0a-4ae8-b33d-306b3d299081` |
| ZoneX | 1 |  | `2bd549d9-3fa1-4510-bf60-9633e827fbfd` |
| Team Falcons | 1 |  | `c2ea6494-ee89-4be1-b059-abe1576c12cf` |
| TFW | 1 |  | `683736a2-4991-4e40-9802-cc1edb4fb287` |
| Zenith | 1 |  | `ba95dda0-f69d-4337-b9cf-d22191dc4faf` |
