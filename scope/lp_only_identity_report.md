# Liquipedia-only player pages with no reviewed identity

164 Liquipedia player pages appear on a line-up of a Liquipedia-only series and have no decision in `scope/player_identity_decisions.json`. Until one is decided, that player is on no side of those series (`series_lineups`, migration 042): their series and map records leave those series out.

Generated read-only from production on 2026-10-23. Nothing is applied. A **FACEIT namesake** is a FACEIT player whose nickname, in-game name or a past nickname folds to the page's handle. **Same org** means the namesake played FACEIT series for an org that this page's Liquipedia team also resolves to. Most 2024 Stage 3/4 teams are Liquipedia-only orgs (owner, 2026-10-17), so a real match there can never show same org: class C is weaker evidence than it looks, not evidence against.

| class | pages | proposal |
|---|---|---|
| A: one FACEIT namesake who played for the same org | 2 | `identity decide <page> --player <guid>` |
| C: a FACEIT namesake, never on the same org | 12 | needs a person: the namesake, or `--new` |
| D: no FACEIT namesake (proposed: Liquipedia-born, --new) | 150 | `identity decide <page> --new` (Liquipedia-born) |

Class D by where the page plays: international 74, NA 2024 42, EMEA 2024 34. International-only pages are mostly Korea and China, which have no FACEIT competition. The 2024 NA/EMEA ones played no in-scope FACEIT series, but may have FACEIT accounts this warehouse never fetched. A `--new` identity for one of them would need merging if they later appear on FACEIT.

## A: one FACEIT namesake who played for the same org (2)

| page | handle | real name | nationality | Liquipedia team (series) | events | dates | FACEIT namesake(s): guid, nickname / in-game, FACEIT series, orgs, same org | proposal |
|---|---|---|---|---|---|---|---|---|
| Spectra | Spectra |  | South Korea | M80 (4) | EWC 2024 | 2024-07-24..2024-07-26 | `f0f0cae1-c527-42bc-8568-214b9a23cef2` owSpectra / Spectra, 8 series (na), team:3aca5abd-ee5d-4542-92e9-392b6f5d0dbc, **same org** | `--player f0f0cae1-c527-42bc-8568-214b9a23cef2` |
| Niann03 | Niann03 |  | Puerto Rico | Vice (North American team) (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-24 | `b5fe588f-39bc-439a-bf83-ddfe2e22f0e0` Niann03 / Niann03, 2 series (na), team:3a72be04-0086-4831-8e2b-eb85a00cacc5, **same org** | `--player b5fe588f-39bc-439a-bf83-ddfe2e22f0e0` |

## C: a FACEIT namesake, never on the same org (12)

| page | handle | real name | nationality | Liquipedia team (series) | events | dates | FACEIT namesake(s): guid, nickname / in-game, FACEIT series, orgs, same org | proposal |
|---|---|---|---|---|---|---|---|---|
| Proper | Proper |  | South Korea | Team Falcons (24), ZETA DIVISION (9) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +4 | 2024-07-24..2026-08-02 | `ef80a7e0-27ad-4c55-a2d7-52b687ba3b23` kevsteer / kevster, 63 series (emea), team:3eaeefbc-6abf-4d54-aeb2-2790e3e21752, team:62f7752b-0b79-4fa8-9a23-78800e2b4539, virtus-pro | decide |
| Smurf | smurf |  | South Korea | Team Falcons (10) | EWC 2024, OWCS 2024/World Finals | 2024-07-24..2024-11-24 | `1b8fd753-75b3-4049-9efe-561d23cc1955` myeonghwan / smurf, 1 series (na), disguised | decide |
| CaptainPrash | CaptainPrash |  | United Kingdom | Hypnos (6), Ex Oblivione (3) | OWCS 2024/EMEA/Stage 3, OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-10-06 | `d4b904ea-88e3-4c2f-9a4a-5690d00ae26a` CaptainPrash / CaptainPrash, 2 series (emea), team:6c39d9d5-c34d-462c-b753-d520d48a6b45 | decide |
| Aniyun | Aniyun |  | United States | Shikigami (5), Fries In The Bag (2) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-11 | `dd08333b-550b-4217-922d-cf06b0910c03` Aniyun / Aniyun, 8 series (na), team:d20d1868-8937-4a85-8706-bf936d265392, team:f4401a61-5010-484b-8429-ad09e524b097 | decide |
| Luka | luka |  | United States | YFP (3) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 | `252f8397-165f-4f3b-8274-472e48b45c95` TheLukaShow / LUKA, 3 series (na), team:fee18be3-c43c-4f24-85ce-7471248dc4ed | decide |
| Xypher | Xypher |  | Austria | Ex Oblivione (3) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-06 | `d1604794-0a7b-4188-806f-fe79771d570f` xypher_ow / Xypher, 2 series (emea), team:444668eb-3722-42e6-8e1e-ed7e1134c522 | decide |
| Ailiseu | Ailiseu |  | Ireland | Ex Oblivione (2) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-24 | `b24a4011-c009-4fe2-8c28-01d96c604981` ailiseu- / Ailiseu, 4 series (emea), team:d8cd2ece-fe1e-46f1-bf8d-00fcd5ab71ab | decide |
| JesperSwag | JesperSwag |  | Norway | Hypnos (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 | `0a883bd4-f574-4d34-aba7-b366f2f054c2` JesperSwag / JesperSwag, 9 series (emea), team:b50813d6-3c84-4d07-adf4-bc9df069e13a | decide |
| Kayeose | Kayeose |  | Saudi Arabia | Al Qadsiah (2) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-24 | `fea20357-269f-41ee-a49f-4fc00cf99b3a` Kayeose / Kayeose, 10 series (emea), vision-esports | decide |
| Lich | Lich |  | United States | Tanuki (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 | `3f7128f9-a043-4f6f-81b5-e252cfc2c1a2` LxicH / ĿƗƇĦ, 10 series (na), lunex, team:a791e2fa-32bd-418f-b7c8-e924e30da4e7 | decide |
| Pingu | Pingu |  | Germany | Hypnos (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 | `c9431330-aaf9-4f18-9153-0bae7a38ec8c` Pingu_ow / Pingu, 9 series (emea), team:b50813d6-3c84-4d07-adf4-bc9df069e13a | decide |
| Shaq | GoldFish |  | United States | Fries In The Bag (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-24 | `650277c6-4225-40e1-9030-2838a98da30a` ShaqinOff / Shaq, 2 series (na), team:ed04d97f-9a2d-4da2-abf3-de55ad19054d<br>`c5b8eea3-d4ec-4182-bed7-464e8aa2283e` g2ldfish / goldfish, 6 series (na), who-is-goldfish | decide |

## D: no FACEIT namesake (proposed: Liquipedia-born, --new) (150)

### international (74)

| page | handle | real name | nationality | Liquipedia team (series) | events | dates |
|---|---|---|---|---|---|---|
| Ackyyy | Ackyyy |  | Australia | Mkers (3), The Gatos Guapos (2) | EWC 2024, OWCS 2025/Midseason Championship | 2024-07-24..2025-08-01 |
| Neuu | Neuu |  | Australia | Mkers (3) | EWC 2024 | 2024-07-24..2024-07-25 |
| Punk | Punk |  | Australia | Mkers (3), The Gatos Guapos (2) | EWC 2024, OWCS 2025/Midseason Championship | 2024-07-24..2025-08-01 |
| Froakie | Froakie |  | Brazil | ROC Esports (3) | EWC 2024 | 2024-07-24..2024-07-25 |
| Kani | Kani |  | Brazil | ROC Esports (3), ZoKorp Esports (2) | EWC 2024, OWCS 2025/Midseason Championship | 2024-07-24..2025-08-01 |
| Lucas42g | Lucas42g |  | Brazil | ROC Esports (3) | EWC 2024 | 2024-07-24..2024-07-25 |
| Mocha | Scarione |  | Brazil | ROC Esports (3) | EWC 2024 | 2024-07-24..2024-07-25 |
| Nitro | Nitrao |  | Brazil | ROC Esports (3) | EWC 2024 | 2024-07-24..2024-07-25 |
| LCŠ | LCS |  | Chile | 9z Team (2) | OWCS 2026/Midseason Championship | 2026-07-29..2026-07-30 |
| Cao_Jiale | Farway2025 |  | China | Team CC (Chinese orgless team) (7) | OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship, OWCS 2025/World Finals | 2025-04-18..2025-11-28 |
| Chen_Cheng | BILIDENG, Sunzo |  | China | Weibo Gaming (8), Team CC (Chinese orgless team) (5) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Champions Clash +1 | 2025-07-31..2026-08-02 |
| Chen_Jingyi | Lengsa |  | China | LGD.OA (4), ROC Esports (2), All Gamers Global (2), All Gamers (2) | EWC 2024, OWCS 2025/Midseason Championship, OWCS 2026/Champions Clash +1 | 2024-07-24..2026-07-30 |
| He_Chengzhi | chamomile |  | China | ROC Esports (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Hua_Yankai | Alphari |  | China | All Gamers Global (2), All Gamers (2) | OWCS 2026/Champions Clash, OWCS 2026/Midseason Championship | 2026-05-22..2026-07-30 |
| Huang_Xin | Leave |  | China | Weibo Gaming (15), LGD.OA (4), Once Again (4) | EWC 2024, OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship +3 | 2024-07-24..2026-08-02 |
| Jia_Chengjie | LiGe |  | China | Once Again (4), Weibo Gaming (3), All Gamers Global (2), All Gamers (2) | OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship, OWCS 2026/Champions Clash +1 | 2025-04-18..2026-07-30 |
| Li_Xianyao | Mew, Mewtwo |  | China | Weibo Gaming (7), Once Again (4), JD Gaming (3) | OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship, OWCS 2025/World Finals +1 | 2025-04-18..2026-07-31 |
| Li_Zhuo | Pineapple |  | China | Team CC (Chinese orgless team) (7), JD Gaming (3) | OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship, OWCS 2025/World Finals +1 | 2025-04-18..2026-07-31 |
| Liu_Nian | Kaneki |  | China | Team CC (Chinese orgless team) (7), JD Gaming (3) | OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship, OWCS 2025/World Finals +1 | 2025-04-18..2026-07-31 |
| Lu_Weida | Diya |  | China | ROC Esports (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Qiu_Jiaxin | GAGA |  | China | Team CC (Chinese orgless team) (5) | OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship | 2025-04-18..2025-08-01 |
| Ren_Yanchao | Unkn0w |  | China | Team CC (Chinese orgless team) (3) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Song_Chunhui | Insane |  | China | Team CC (Chinese orgless team) (2), All Gamers (2) | OWCS 2025/Champions Clash, OWCS 2026/Champions Clash | 2025-04-18..2026-05-22 |
| Wu_Gengtuo | HaoYoQian |  | China | Team CC (Chinese orgless team) (4) | OWCS 2025/Champions Clash, OWCS 2025/World Finals | 2025-04-18..2025-11-28 |
| Xu_Qiulin | Guxue |  | China | Weibo Gaming (12), LGD.OA (4), Once Again (4) | EWC 2024, OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship +2 | 2024-07-24..2026-08-02 |
| Yi_Hu | JinMu |  | China | ROC Esports (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Zhang_Jingkun | Recall |  | China | All Gamers Global (2), All Gamers (2) | OWCS 2026/Champions Clash, OWCS 2026/Midseason Championship | 2026-05-22..2026-07-30 |
| Zheng_Yangjie | Shy, shy |  | China | Weibo Gaming (15), LGD.OA (4), Once Again (4) | EWC 2024, OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship +3 | 2024-07-24..2026-08-02 |
| Zhou_Xiang | Mmonk |  | China | Weibo Gaming (7), LGD.OA (4), Once Again (4), JD Gaming (3) | EWC 2024, OWCS 2025/Champions Clash, OWCS 2025/Midseason Championship +2 | 2024-07-24..2026-07-31 |
| Wed | Wed |  | Costa Rica | 9z Team (2) | OWCS 2026/Midseason Championship | 2026-07-29..2026-07-30 |
| WilmaFistFit | WilmaFistFit |  | Ecuador | ZoKorp Esports (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| StillKIWI | StillKIWI |  | El Salvador | ZoKorp Esports (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| KSG | KSG |  | Japan | VARREL (8) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-07-31 |
| Nico | Nico |  | Japan | VARREL (8) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-07-31 |
| Qki | qki |  | Japan | VARREL (3) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Qloud | Qloud |  | Japan | VARREL (8) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-07-31 |
| Colourhex | Colourhex |  | New Zealand | Mkers (3), The Gatos Guapos (2) | EWC 2024, OWCS 2025/Midseason Championship | 2024-07-24..2025-08-01 |
| Kame | wntr |  | Singapore | Team Secret (2) | OWCS 2026/Midseason Championship | 2026-07-29..2026-07-30 |
| Sgy | sgy |  | Singapore | Team Secret (2) | OWCS 2026/Midseason Championship | 2026-07-29..2026-07-30 |
| Belosrea | Belosrea |  | South Korea | JD Gaming (3), ROC Esports (2) | OWCS 2025/Midseason Championship, OWCS 2026/Midseason Championship | 2025-07-31..2026-07-31 |
| Bernar | BERNAR, Bernar |  | South Korea | ZETA DIVISION (14) | EWC 2024, OWCS 2026/Champions Clash, OWCS 2026/Midseason Championship | 2024-07-24..2026-08-02 |
| CH0R0NG | CH0R0NG |  | South Korea | Crazy Raccoon (32) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +4 | 2024-07-24..2026-08-01 |
| ChiYo | ChiYo |  | South Korea | Team Falcons (27) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +3 | 2024-07-24..2026-07-31 |
| DONGHAK | D0NGHAK, DONGHAK |  | South Korea | T1 (16), Fnatic (4) | EWC 2024, OWCS 2025/Midseason Championship, OWCS 2025/World Finals +1 | 2024-07-24..2026-08-02 |
| Ezhan | Ezhan |  | South Korea | All Gamers Global (2), All Gamers (2) | OWCS 2026/Champions Clash, OWCS 2026/Midseason Championship | 2026-05-22..2026-07-30 |
| Fearless | Fearless |  | South Korea | ZETA DIVISION (5) | EWC 2024 | 2024-07-24..2024-07-28 |
| Fielder | Fielder |  | South Korea | Team Falcons (27) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +3 | 2024-07-24..2026-07-31 |
| Flora | Flora |  | South Korea | ZETA DIVISION (5) | EWC 2024 | 2024-07-24..2024-07-28 |
| Hanbin | Hanbin |  | South Korea | Team Falcons (24) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +2 | 2024-07-24..2025-11-29 |
| HeeSang | HeeSang |  | South Korea | Crazy Raccoon (32) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +4 | 2024-07-24..2026-08-01 |
| Jasm1ne | Jasm1ne |  | South Korea | T1 (5), All Gamers Global (2) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals | 2025-07-31..2025-11-29 |
| JunBin | JunBin, Junbin |  | South Korea | Crazy Raccoon (32) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +4 | 2024-07-24..2026-08-01 |
| LeeJaeGon | LeeJaeGon |  | South Korea | Fnatic (4) | EWC 2024 | 2024-07-24..2024-07-26 |
| LeeSooMin | LeeSooMin |  | South Korea | Weibo Gaming (8), All Gamers Global (2) | OWCS 2025/Midseason Championship, OWCS 2026/Champions Clash, OWCS 2026/Midseason Championship | 2025-07-31..2026-08-02 |
| LIP | LIP |  | South Korea | Crazy Raccoon (28) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +3 | 2024-07-24..2026-08-01 |
| MAKA | MAKA |  | South Korea | Weibo Gaming (8), All Gamers Global (2) | OWCS 2025/Midseason Championship, OWCS 2026/Champions Clash, OWCS 2026/Midseason Championship | 2025-07-31..2026-08-02 |
| MAX | MAX |  | South Korea | Crazy Raccoon (32) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +4 | 2024-07-24..2026-08-01 |
| Mealgaru | Mealgaru |  | South Korea | ZETA DIVISION (4), All Gamers Global (2) | OWCS 2025/Midseason Championship, OWCS 2026/Champions Clash | 2025-07-31..2026-05-24 |
| Nyang | Nyang |  | South Korea | The Gatos Guapos (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Proud | Proud |  | South Korea | T1 (16) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-08-02 |
| Roxy | Roxy |  | South Korea | JD Gaming (3) | OWCS 2026/Midseason Championship | 2026-07-29..2026-07-31 |
| Shu | Shu |  | South Korea | Crazy Raccoon (25), ZETA DIVISION (9) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +4 | 2024-07-24..2026-08-02 |
| Skewed | skewed |  | South Korea | T1 (16) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-08-02 |
| Sley | Sley |  | South Korea | VARREL (8) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-07-31 |
| SP1NT | SP1NT |  | South Korea | Crazy Raccoon (5), Team Falcons (3) | OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-11-27..2026-07-31 |
| Stalk3r | Stalk3r |  | South Korea | Team Falcons (14), Crazy Raccoon (7) | EWC 2024, OWCS 2024/World Finals, OWCS 2025/Champions Clash +2 | 2024-07-24..2026-08-01 |
| Viper | Viper |  | South Korea | T1 (10), Fnatic (4) | EWC 2024, OWCS 2025/Midseason Championship, OWCS 2025/World Finals | 2024-07-24..2025-11-29 |
| ZEST | ZEST |  | South Korea | T1 (16) | OWCS 2025/Midseason Championship, OWCS 2025/World Finals, OWCS 2026/Midseason Championship | 2025-07-31..2026-08-02 |
| Love | Love |  | Sweden | ZoKorp Esports (2) | OWCS 2025/Midseason Championship | 2025-07-31..2025-08-01 |
| Lightt | Lightt |  | Taiwan | The Gatos Guapos (2), 9z Team (2) | OWCS 2025/Midseason Championship, OWCS 2026/Midseason Championship | 2025-07-31..2026-07-30 |
| Ace_(Thai_player) | Ace |  | Thailand | Bleed Esports (3) | EWC 2024 | 2024-07-24..2024-07-25 |
| HyVision | HVS, hyvisi0n |  | Thailand | Bleed Esports (3), Team Secret (2) | EWC 2024, OWCS 2026/Midseason Championship | 2024-07-24..2026-07-30 |
| PaLee | PaLee |  | Thailand | Bleed Esports (3), Team Secret (2) | EWC 2024, OWCS 2026/Midseason Championship | 2024-07-24..2026-07-30 |
| Yoshinori2k | Yoshinori2k |  | Thailand | Bleed Esports (3) | EWC 2024 | 2024-07-24..2024-07-25 |

### NA 2024 (42)

| page | handle | real name | nationality | Liquipedia team (series) | events | dates |
|---|---|---|---|---|---|---|
| Azurae | Azurae |  | Canada | Ramattra Punch (3) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-06 |
| Havoc | Havoc |  | Canada | Absolution (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Soulsay | Soulsay |  | Canada | Absolution (4) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-05 |
| Aurora | Aurora |  | Egypt | Arizona State University (3), Tanuki Tapire (2) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| UnluckyMain | UnluckyMain |  | Germany | Absolution (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Otters | Otters |  | Greece | O3 Splash (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| K41 | K41 |  | Mexico | O3 Splash (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| MonkeyHappy | MonkeyHappy |  | Mexico, United States | Absolution (4) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-05 |
| Senna | senna |  | Netherlands | Timeless Ethereal (5), Ramattra Punch (3) | OWCS 2024/North America/Stage 3, OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-06 |
| Anderp | Anderp |  | Puerto Rico | Absolution (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Aresona | Aresona |  | Puerto Rico | Tanuki (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Talisman_(Puerto_Rican_player) | Talisman |  | Puerto Rico | Team Z (6) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-06 |
| Elva | elva |  | South Korea | O3 Splash (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Khd | khd |  | South Korea | O3 Splash (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| ACETKILLER | ACETKILLER |  | United States | EXN Zenith (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Anghell1c | Anghell1c |  | United States | Arizona State University (3), Ramattra Punch (3) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-06 |
| Anhoo | Anhoo |  | United States | Arizona State University (3), Tanuki Tapire (2) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| Cyber | Cyber |  | United States | EXN Zenith (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Day_(American_player) | Day |  | United States | Tanuki (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Doomed | Doomed |  | United States | Timeless (7), Citrus Nation (4) | OWCS 2024/North America/Stage 3, OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4 +1 | 2024-08-16..2024-10-10 |
| Dreepy | Dreepy |  | United States | Rad x Avidity (6), Avidity (3) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-11 |
| Excal | Excal |  | United States | Team Z (6) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-06 |
| Fidel | Fidel |  | United States | EXN Zenith (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Fiery | fiery |  | United States | Tanuki Tapire (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Jeremy87 | jeremy87 |  | United States | Tanuki Tapire (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Jman | Jman |  | United States | Arizona State University (3), Tanuki Tapire (2) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| Karova | Karova |  | United States | Vice (North American team) (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-24 |
| Kashir | Kashir |  | United States | Ramattra Punch (3) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-06 |
| Lenn | lenn |  | United States | Team Z (6) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-06 |
| Loathen | ross |  | United States | Absolution (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Moncholo | Moncholo |  | United States | Tanuki (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Narwhal | Narwhal |  | United States | EXN Zenith (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Salmon | Salmon |  | United States | Ramattra Punch (3), Vice (North American team) (2) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-06 |
| Scylla | Scylla |  | United States | Arizona State University (3) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-25 |
| Social | Social |  | United States | Tanuki (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Sugureru | Sugureru |  | United States | O3 Splash (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| T3MP | T3MP |  | United States | Tanuki (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Wolfie | Wolfie |  | United States | EXN Zenith (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Wsps | wsps |  | United States | FLUFFY AIMERS (6), Avidity (3) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-10-13 |
| Yimitra | Yimitra |  | United States | Fries In The Bag (2) | OWCS 2024/North America/Stage 3/Group Stage | 2024-08-16..2024-08-24 |
| Z4CH | Z4CH |  | United States | Absolution (2) | OWCS 2024/North America/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| ZPanthr | zPanthr |  | United States | Arizona State University (3), Tanuki Tapire (2) | OWCS 2024/North America/Stage 3/Group Stage, OWCS 2024/North America/Stage 4/Group Stage | 2024-08-16..2024-09-29 |

### EMEA 2024 (34)

| page | handle | real name | nationality | Liquipedia team (series) | events | dates |
|---|---|---|---|---|---|---|
| Chaba | Chaba |  | Belgium | Ohana Aloha (2), Wasp X Ohhhh No (2) | OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| Redmoosegoat | Redmoosegoat |  | Canada | Wasp X Ohhhh No (3) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-25 |
| Deme | Deme |  | Cyprus | Ohana Aloha (2) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| TommeX | TommeX |  | Estonia | Negative Mental Attitude (3) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-06 |
| LhCloudy | LhCloudy |  | Finland | SrPeakCheck (9) | OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-10-12 |
| Mickji | Mickji |  | Finland | SrPeakCheck (6) | OWCS 2024/EMEA/Stage 4, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-12 |
| Prep | Prep |  | Finland | SrPeakCheck (6) | OWCS 2024/EMEA/Stage 4, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-12 |
| Eden | eden |  | France | Wasp X Ohhhh No (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| KDM | KDM |  | France | Wasp X Ohhhh No (5) | OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| Matriera | Matriera |  | France | Hypnos (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Ostrix | Ostrix |  | France | Wasp X Ohhhh No (5) | OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| SLEEK | SLEEK |  | Germany | Hypnos (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Dawson | Dawson |  | Ireland | Ohana Aloha (2) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| Katekomi | Katekomi |  | Italy | Metaboiz (2) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-18 |
| AoD | DarkLordAoD |  | Kazakhstan | Vanir Quick (3) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Bonkey | Bonkey |  | Netherlands | A One Man Army (6) | OWCS 2024/EMEA/Stage 3, OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-31 |
| Reinschdyret | Reinsch |  | Norway | Team G4mbit (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Szymondki | Szymondki |  | Poland | Team G4mbit (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Facator | Facator |  | Saudi Arabia | Al Qadsiah (2) | OWCS 2024/EMEA/Stage 3/Group Stage | 2024-08-16..2024-08-24 |
| Mesopos | Mesopos |  | Saudi Arabia | Negative Mental Attitude (3) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-06 |
| Miraculous | Miraculous |  | Saudi Arabia | Negative Mental Attitude (3) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-06 |
| PoroPlays | PoroPlays |  | Saudi Arabia | Metaboiz (4) | OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| D0nghun | D0nghun |  | South Korea | A One Man Army (11) | OWCS 2024/EMEA/Stage 3, OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4 +1 | 2024-08-16..2024-10-10 |
| Vigilante | vigilante |  | South Korea | Twisted Minds (10), T1 (10), Crazy Raccoon (7) | EWC 2024, OWCS 2024/EMEA/Stage 3, OWCS 2024/EMEA/Stage 3/Group Stage +4 | 2024-07-24..2026-08-01 |
| Bones | Bones |  | Spain | Hypnos (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Centralapan | Centralapan |  | Sweden | Metaboiz (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-09-29 |
| Gurkmeister | Gurkmeister |  | Sweden | AWW YEAH (5), Wasp X Ohhhh No (2) | OWCS 2024/EMEA/Stage 3, OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| Yukej | Yukej |  | Sweden | Team G4mbit (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Hêv | Hêv |  | Switzerland | Wasp X Ohhhh No (5) | OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4/Group Stage | 2024-08-16..2024-09-29 |
| Alpha_(British_player) | Alpha |  | United Kingdom | A One Man Army (11) | OWCS 2024/EMEA/Stage 3, OWCS 2024/EMEA/Stage 3/Group Stage, OWCS 2024/EMEA/Stage 4 +1 | 2024-08-16..2024-10-10 |
| Fate_(British_player) | fate |  | United Kingdom | Team G4mbit (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Santyx | Santyx |  | United Kingdom | Team G4mbit (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| VoltsA | VoltsA |  | United Kingdom | Hypnos (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
| Sonder | sonder |  | Åland | Team G4mbit (2) | OWCS 2024/EMEA/Stage 4/Group Stage | 2024-09-27..2024-10-05 |
