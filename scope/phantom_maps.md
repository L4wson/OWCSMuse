# Phantom maps: FACEIT map rows for maps that were never played

FACEIT keeps a fixed number of map slots per series format and, when a sweep closes a series early, logs a default win for the winner on the next map in the rotation. Nothing here is applied: this is the extent, from stored data only, for a person to read before the precedence rule changes.

Linked series compared against Liquipedia: 430. FACEIT map rows examined: 1482 over every in-scope series (280 of those series are sweeps by FACEIT's stored score).

## 1. Linked series where FACEIT exceeds Liquipedia

| FACEIT match | link | competition | teams | FACEIT score / maps | Liquipedia score / games | FACEIT maps Liquipedia lacks | stored bo | LP bo | sweep | oriented by |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-472cc9eb-d7a3-4811-b633-397a99d6a502 | confirmed | S8 NA OWCS Central - Regular Season | Disguised vs Team Liquid | 4-0 / 4 | 3-0 / 4 | - | 5 | 5 | yes | orgs |
| 1-28ea62bc-16c1-4686-b41b-479d5275d151 | confirmed | S8 NA OWCS Central - Playoffs | Dallas Fuel vs SpaceStation Gaming | 4-1 / 0 | 3-1 / 5 | - | 5 | 5 | no | orgs |
| 1-c5823143-d7e8-4efe-a957-6d54cfee1a8e | confirmed | OWCS 2024: EMEA Stage 1 - Main Event | Twisted Minds vs ENCE | 5-1 / 5 | 4-1 / 5 | - | 7 | 7 | no | orgs |
| 1-70cff415-3817-4144-9eca-e917f89cb6e7 | confirmed | OWCS 2024: NA Stage 1 - Main Event | Toronto Defiant vs Timeless | 5-0 / 4 | 4-0 / 4 | - | 7 | 7 | yes | orgs |

`ambiguous` here is an exact FACEIT id whose two records disagree on the score: with a phantom map that is the expected shape, and the stricter link rule (Stage 3) withholds the link until a person confirms it.

- 1-472cc9eb-d7a3-4811-b633-397a99d6a502: FACEIT maps ['Lijiang Tower', 'Blizzard World', 'Havana', 'Esperança']; Liquipedia games ['Lijiang Tower', 'Blizzard World', 'Havana', 'Esperança']; https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1/Regular_Season
- 1-28ea62bc-16c1-4686-b41b-479d5275d151: FACEIT maps []; Liquipedia games ['Busan', 'Numbani', 'Watchpoint: Gibraltar', 'Aatlis', 'Esperança']; https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_1
- 1-c5823143-d7e8-4efe-a957-6d54cfee1a8e: FACEIT maps ['Nepal', 'Hollywood', 'Colosseo', 'Suravasa', 'Shambali Monastery']; Liquipedia games ['Nepal', 'Hollywood', 'Colosseo', 'Suravasa', 'Shambali Monastery']; https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/EMEA/Stage_1
- 1-70cff415-3817-4144-9eca-e917f89cb6e7: FACEIT maps ['Nepal', 'Hollywood', 'Esperança', 'New Junk City']; Liquipedia games ['Nepal', 'Hollywood', 'Esperança', 'New Junk City']; https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/North_America/Stage_1

## 2. FACEIT map rows with a placeholder shape

| FACEIT match | map # | map | mode | score | player rows | last map | sweep | stored bo | linked | beyond LP games | why |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1-3e78e269-28b7-481c-9ccc-46c173314ab9 | 5 | Suravasa | Flashpoint | 0-3 | 10 | yes | no | 5 | yes | no | Flashpoint scored 0-3: a played Flashpoint map ends 3-x with x <= 2 |

## 3. Clustering

- placeholder-shaped rows: 1; on sweeps: 0; on the series' last map: 1; beyond Liquipedia's game count: 0
- series where FACEIT exceeds Liquipedia: 4; of those, sweeps: 2
- the extra maps' names: -

A phantom map by the mechanism is: on a sweep, the series' last map, beyond Liquipedia's game count, a win with no player rows (or player rows FACEIT fabricated along with it). Rows matching all of that are the systematic case; the rest need a look.
