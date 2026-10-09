# Stage 4: anchor windows to decide before any event record is loaded

Proposals only; nothing here is applied. Evidence read from production on 2026-10-09 (read-only): FACEIT series per
team id in included championships, `team_names` sightings, `team_orgs` windows.

## Decided by the owner (2026-10-09), applied to scope/liquipedia_team_map.json

Toronto Defiant, M80 and ENCE "played in 2024 and did not return in later seasons": each window is the 2024 season,
`2024-01-01` to `2025-01-01`. That is wider than the FACEIT-activity windows proposed below (to 2024-06-03), on
purpose: Liquipedia shows all three playing later in 2024 - EWC 2024 in July (ENCE 5-8th, M80 9-12th) and the 2024
World Finals in November (Toronto Defiant 3rd, ENCE 7-8th) - which FACEIT does not hold, and "their 2024 activity"
includes those. Crazy Raccoon and Team Falcons are held until the owner reads the fetch (`scope/stage4_team_report.md`).

## Why

A Liquipedia team name in `scope/liquipedia_team_map.json` resolves **at the series' own time**, and an entry with no
window holds at every time. 15 of the 27 entries are a bare FACEIT team id with no window. Every Stage 4 event
(EWC 2024 July 2024, World Finals November 2024 and 2025, Midseason Championships 2025 and 2026) falls after or
outside the FACEIT activity of most of those ids, so a Stage 4 record carrying one of these names would key to that
id - a 2024 roster's id answering for a 2025 team. A FACEIT team id follows the roster and can be recycled; a name
staying the same says nothing about the roster or the org.

The proposed rule for each: **the window is the id's FACEIT activity under that name**, closed the day after its last
sighting or at the sighting of its next name. Outside it the name is undecided at that time (never the nearest era),
so a Stage 4 record carrying it stays out of every answer until a person decides what it is - most likely an
org-level anchor (`--org`), the shape SpaceStation Gaming and Extinction already have.

## The known trap

| name | team id | FACEIT activity | proposed window | Stage 4 events outside it |
|---|---|---|---|---|
| crazy raccoon | 4cbafe8a | 5 series, 2024-06-01..2024-06-02, all Dreamhack Dallas; FACEIT name "Crazy Raccoons" | `valid_to` 2024-06-03 | all five |
| team falcons | 2ab92d33 | 4 series, 2024-05-31..2024-06-02, all Dreamhack Dallas | `valid_to` 2024-06-03 | all five |

Neither id carries any org window, and neither appears on FACEIT after Dallas. Whether the Crazy Raccoon or Team
Falcons at EWC 2024, the World Finals and the Midseason Championships is the organisation that played Dallas is an org
decision for the owner; roster overlap between them (including any roster that moved between these two orgs) is
evidence to show, not a basis to decide. Proposed shape if the owner says same org: an org slug (`crazy-raccoon`,
`team-falcons`) mapping the Dallas id over its window in `scope/org_decisions.json`, and the name anchored to the
org, so FACEIT and Liquipedia series count once under one org.

## The same shape: other bare team-id anchors

| name | team id | FACEIT activity under this name | proposed window | why it matters for Stage 4 |
|---|---|---|---|---|
| toronto defiant | 8f632648 | 2024-03-08..2024-06-02 (NA 2024 and Dallas) | `valid_to` 2024-06-03 | a Toronto Defiant at a later event would key to the 2024 id |
| twisted minds | 2b9f2e7a | 2024-03-08..2026-07-05, one name throughout (66 series, EMEA and Dallas) | `valid_to` 2026-07-06 | the only long-lived one; any event after 2026-07-05 (likely the 2026 Midseason) falls outside and needs a decision |
| m80 | 3aca5abd | 2024-03-08..2024-06-02 | `valid_to` 2024-06-03 | Dallas only |
| ence | 62f7752b | "ENCE" 2024-03-22..2024-06-02 (was "BuboSprayCheck" before) | `valid_from` 2024-03-22, `valid_to` 2024-06-03 | EMEA 2024 and Dallas only |
| timeless | c5116cb3 | "Timeless" 2024-03-08..2025-03-08; the id is "NTMR" from 2025-05-10 (org ntmr) | `valid_to` 2025-05-10 | after it, the name is not this roster's |
| avidity | 2b7f8ef6 | "Avidity" 2025-02-01..2025-03-02; "Extinction" from 2025-05-11 (org extinction) | `valid_from` 2025-02-01, `valid_to` 2025-05-11 | NA only; unlikely at an event |
| supernova american team | d20d1868 | "Supernova" 2025-05-11..2025-06-14; "Team Z" from 2025-09-07 (org team-z); earlier names team_chiime, Dreamland in 2024 | `valid_from` 2025-05-11, `valid_to` 2025-09-07 | a recycled id: three unrelated names on it |
| anyone s legend | 75516399 | "Anyones Legend" 2026-03-22..2026-05-25; "1234" from 2026-05-25 (org 1234) | `valid_from` 2026-03-22, `valid_to` 2026-05-25 | EMEA 2026 only |
| the kafe | a35f8d47 | "The Kafe" 2026-06-13..2026-07-01; "Extinction" before (org extinction to 2026-06-13) | `valid_from` 2026-06-13, `valid_to` 2026-07-02 | NA 2026 only |
| shikigami | ec69a520 | 2024-03-08..2025-02-23 | `valid_to` 2025-02-24 | NA only |
| lfo | a24592c1 | 2024-03-08..2024-03-21 | `valid_to` 2024-03-22 | NA 2024 only |
| luminosity gaming | d4ec89d7 | "Luminosity" 2024-03-08..2024-04-29 | `valid_to` 2024-04-30 | NA 2024 only |
| pirates in pyjamas | f4401a61 | "PIP" / "PxG PiP" 2024-03-08..2024-04-29 | `valid_to` 2024-04-30 | NA 2024 only |

Closing a window on an id that is still the same team is harmless to existing answers only if no stored Liquipedia
record of that name falls outside it: before deciding, `liquipedia reconcile` with the windowed map and `check`
(`lp_name_resolution`, `liquipedia_unresolved_not_in_series`) show whether any 2024-2026 main-series record moved.
The 12 org anchors are not this shape: an org's window comes from `team_orgs`, which is already dated.

## Which names will actually meet these anchors

Unknown until the match fetch: the probe asked only for page names. The fetch stores raw responses and the coverage
ledger only; nothing is reconciled or loaded until these windows are decided. Then `liquipedia teams propose` lists
every Stage 4 team name with the evidence for it, against the windowed map.
