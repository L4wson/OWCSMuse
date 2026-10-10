# Partner teams: what Liquipedia records, and what needs a decision

Proposals only; nothing is applied. Fetched 2026-10-10 (3 requests, Stage 4 budget now 7 of 15):

1. `/datapoint` on `Overwatch_Champions_Series/Partner_Teams` (raw_payloads 4224): **no rows**. The page stores no
   structured data, and the API may not read rendered pages, so its tables are not a source.
2. `/placement` on the 2025 and 2026 NA and EMEA stage pages (raw_payloads 4225): each stage's prize pool names how
   each team qualified, and a partner team's row says **`qualifier: Partner Team`** - on the season's Stage 1 page
   only (later stages list teams by their previous stage's result).
3. `/placement` with `[[qualifier::Partner Team]]` across the whole wiki (raw_payloads 4226): **23 rows, every
   partner placing Liquipedia records**, in 7 season-and-region groups. This is the source proposed below: per season,
   per region, and read from Liquipedia's own records, never inferred.

## The groups

| season | region | Liquipedia page (Stage 1) | partner teams (Liquipedia's names) |
|---|---|---|---|
| 2025 | Korea | `2025/Asia/Stage_1/Korea` | T1, Team Falcons, Crazy Raccoon, ZETA DIVISION |
| 2025 | EMEA | `2025/EMEA/Stage_1` | Gen.G Esports, Twisted Minds, Virtus.pro |
| 2025 | NA | `2025/NA/Stage_1` | Team Liquid, Spacestation Gaming |
| 2026 | Korea | `2026/Asia/Stage_1/Korea` | Crazy Raccoon, T1, Team Falcons, ZETA DIVISION |
| 2026 | China | `2026/China/Stage_1` | All Gamers, JD Gaming, Weibo Gaming |
| 2026 | EMEA | `2026/EMEA/Stage_1` | Team Peps, Twisted Minds, Virtus.pro |
| 2026 | NA | `2026/NA/Stage_1` | Disguised, Dallas Fuel, Spacestation Gaming, Team Liquid |

**No Partner Team rows** for China 2025, Japan or the Pacific in either season. That says Liquipedia tagged none;
whether those regions had no partners is for the owner to confirm, not to assume.

## Mapped to the warehouse's entities (the team map, at each placing's date)

20 of 23 resolve through decisions already made: T1, Team Falcons, Crazy Raccoon, ZETA DIVISION, JD Gaming, Weibo
Gaming (orgs); Virtus.pro, Team Liquid, Spacestation Gaming, Team Peps, Dallas Fuel (orgs); Twisted Minds (its FACEIT
team id `2b9f2e7a`, unwindowed: correct at these dates; the window proposed in `stage4_anchor_windows.md` was never
decided).

**Needs a decision (3):**

| Liquipedia name | group | evidence | proposal |
|---|---|---|---|
| Gen.G Esports | 2025 EMEA | `liquipedia teams propose`: stood opposite FACEIT team `bc8a3617` ("GenG", "GenG Esports") in 26 of 26 id-linked matches; the alias decisions already route "Gen.G" there (alias `gen g`) | an org (`gen-g`), not the bare id, as with Team Liquid and Dallas Fuel |
| Disguised | 2026 NA | stood opposite FACEIT team `968066cc` ("Disguised") in 10 of 10 id-linked matches | an org (`disguised`), same reasoning |
| All Gamers | 2026 China | Liquipedia's 2026 name; the 2025 Midseason and 2026 Midseason list "All Gamers Global" (template `ag.al international 2025`), decided as the Liquipedia-only org `all-gamers-global` | the same org, if the owner confirms it is the same team |

## What building it would take (no further requests)

- `scope/partner_teams.json`: the reviewed groups, `{season: {region: [{liquipedia_name, entity, source raw id}]}}`,
  written from this report once the three are decided; `decisions_loaded` compares it with the table.
- A migration: `team_groups (group_key, season, region, org_key, liquipedia_name, raw_id)`, loaded by a `groups load`
  command; nothing else writes it.
- Questions: "which teams are the partner teams" (the latest season, or the one named: listed by region),
  "which partner team won the most series in 2026" (a team leaderboard restricted to the season's partners, a team
  counted only in a season it was a partner). Every answer names the teams it included. "Games" is series.
- Golden cases from raw_payloads 4226: one list question per season, one leaderboard restricted to partners, one
  question naming a season with no partner group.
- Keeping it current: one `/placement [[qualifier::Partner Team]]` request a season (a new Stage 1), proposals
  reviewed like any other decision; the daily ingest can carry it as a plan step that spends nothing when nothing new.
