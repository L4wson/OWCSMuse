# OWCS Grid: Phase 0 audit

Audited 2026-11-16 on branch `grid/phase-0` (cut from `origin/main` at c96a145). Every number below is from a
read-only query against production Supabase that day, unless it says otherwise. The database was at migration 052,
matching the checkout in both directions. No local database was available, so production was the only option; every
query ran on one connection inside a `READ ONLY` transaction.

The brief is `docs/owcs-grid-planning-brief.md`. Cell counts are in [CELL_COUNTS.md](CELL_COUNTS.md), the plan in
[PLAN.md](PLAN.md).

## Summary

- **Role x season is viable** and is the only player format with deep cells: 21 to 100 answers per cell at Muse's
  4-map floor. Its weakness is coverage, not volume. Roles exist only where FACEIT recorded map stats, so 115
  players who played 2024 Stages 3-4 have no role on record and would be rejected as wrong.
- **Org x org ("played for both") is not viable.** No 3x3 of any team identities gets every cell above 2 answers.
- **Org x season is viable** for a small set of teams (8 identities have a line-up in all three seasons).
- **Team-answer grids are viable** for region x season and for international results, but the answer pool is small
  (28 to 35 teams) and three teams fit most cells.
- **Muse has no player or team pages.** An entity link today is a question (`/q/<slug>`).
- **Muse has no accounts, sessions or cookies**, and its API is read-only. Grid would be the first feature that
  writes on a visitor's behalf.
- **The NL query layer is not reusable as a predicate engine.** Its data layer is: the identity function, the
  line-up view, the fact views, the resolver and the name index are exactly what Grid needs.

## 1. Repo map

| Part | What it is | Where |
|---|---|---|
| Backend | FastAPI, one module, built by `create_app()` | `owcsmuse/api.py` (389 lines) |
| Query layer | No ORM. psycopg 3 with hand-written, parameterized SQL over views and materialized views | `owcsmuse/nlq/`, `owcsmuse/aggregates.py`, `owcsmuse/resolve.py` |
| Schema | 52 plain-SQL migrations, applied in filename order by `python -m owcsmuse migrate`, each in its own transaction, recorded in `schema_migrations`. One schema (`public`), `search_path` pinned | `migrations/`, `owcsmuse/db.py` |
| Frontend | Vite + React 19, plain CSS, no UI framework, no router library | `web/src/` |
| Ingest | FACEIT backfill and history crawl, Liquipedia fetch, reconcile, enrich, refresh, check | `owcsmuse/collector.py`, `crawl.py`, `liquipedia/`, `.github/workflows/ingest.yml` |
| Reviewed decisions | JSON files a person edits through CLI commands; loaders write them to tables | `scope/*.json` |
| CLI | `python -m owcsmuse <command>` | `owcsmuse/cli.py` |

**API conventions.** Five routes: `POST /ask`, `GET /query/{slug}`, `GET /suggestions`, `GET /healthz`, `GET /`. No
`/api` prefix. A refusal is a 200 with `status` in the body; 422 is a malformed request, 404 an unknown slug, 503 a
database that cannot be read, 429 the per-IP throttle. Rows carry raw values plus column descriptors, and join keys
(`player_id`, `org_key`) stay in the rows. The web layer writes no SQL.

**Auth and sessions: none.** Confirmed in `owcsmuse/api.py`: CORS is `allow_origins=["*"]` for GET and POST, no
credentials, no cookies. `query_log` deliberately stores nothing about the asker (no IP, user agent or session).
The only per-client state is an in-memory token bucket keyed by Fly's `Fly-Client-IP` header (20 burst, 30 a minute,
`owcsmuse/throttle.py`). The API holds at most 6 database connections.

**Writes the API makes today:** `saved_queries` (the question behind a slug) and `query_log`. Nothing else.

**Deployment.**

| Piece | Host | Config | Trigger |
|---|---|---|---|
| API | Fly.io, one `shared-cpu-1x` 512 MB machine in `sjc`, always on | `fly.toml`, `Dockerfile` | `deploy.yml`, after CI passes on a push to `main`. `release_command` runs `migrate` first |
| Frontend | Vercel, project root `web` | `web/vercel.json`: every unknown path rewrites to `/index.html` | Vercel's own Git integration |
| Database | Supabase Postgres 17, session pooler, 300 MB of a 500 MB free tier | `DATABASE_URL` | n/a |
| Ingest | GitHub Actions | `ingest.yml` | nightly, 22:35 Pacific, and on demand |

The Docker image copies only `owcsmuse/`, `migrations/` and `scope/`, so nothing under `scripts/` or `docs/` reaches
production. **A merge to `main` migrates production unattended**, so any Grid migration must be additive.

**CI** (`ci.yml`, every push and PR): `ruff check .`, the API image build, offline `pytest`, database tests on
Postgres 16 and 17, the golden answer suite on both, frontend tests and build, and `owcsmuse check` on a fixture
warehouse. `ruff` and offline `pytest` both cover new files under `scripts/` and `tests/`.

**Tests.** 60 pytest modules in `tests/`, 8 Vitest files in `web/tests/`. `tests/db_guard.py` refuses any database
that is not on this machine. The golden suite (`tests/golden/`) holds 113 cases (111 in the main set, 108 of them confirmed, and 2 in
`pairs/`) whose expected values come from
`independent.py`, which reads raw payloads and imports nothing from `owcsmuse`; only `confirmed` cases are asserted.

**Routes Grid answers could link to.** The frontend has two routes, `/` and `/q/<slug>`
(`web/src/router.js`, 35 lines of `history.pushState`). There is **no player page and no team or org page**. An
entity in an answer sentence is a button that asks `"<name> record"` (`entityQuestion` in `web/src/format.js`).
The parser accepts `player:<id>`, `team:<id>` and `org:<id>` anywhere a name can appear, so
`player:<id> record` is an unambiguous question, and `slug_for()` in `owcsmuse/web.py` makes its slug
deterministic. A Grid answer can therefore link to `/q/<slug>` for that question. See PLAN.md for the catch: a slug
resolves only after its question has been saved.

## 2. Data model

Provenance for everything: FACEIT Data API v4 for NA and EMEA series, line-ups and per-map player stats; Liquipedia
(LiquipediaDB API v3, CC-BY-SA 3.0) for results, map scores, line-ups, placings, hero bans and every international
event. Refresh is the nightly ingest. The reviewed decisions in `scope/` change only when a person changes them.

### Players

| Concept | Representation | Notes |
|---|---|---|
| Stable id | `players.player_id` | 574 players: 424 FACEIT GUIDs, 150 Liquipedia-born (`lp:player:<page>`) |
| Display name | `player_display_name(display_name, nickname, game_player_name)` | owner override, else in-game name, else FACEIT nickname. 2 overrides (Astro, ZZZ) |
| Name history | `player_nicknames`, `player_game_names` (first and last seen), `lp_player_names` | all searchable through `entity_names` |
| Search index | `entity_names` (materialized): 995 player rows across current nickname, game name, display name, historical nickname and game name, Liquipedia handle and real name; accent-folded | ranked in Python by `owcsmuse.resolve` |
| Community shorthand | `entity_aliases` (17 rows, reviewed) | orgs and teams only today |
| Cross-source identity | `entity_anchors` (608 rows): a Liquipedia player page mapped to a player id, by review | 12 pages still undecided |
| Role | `match_players.role`, **per player per map** (`Tank`, `Damage`, `Support`) | time-aware at the finest grain there is. `player_primary_roles` (view) is the most-played role per player per season. There is no player-level role column, so nothing can leak a current role |
| Region | none on the player | only the region of each competition played. `liquipedia_match_players.nationality` is filled for all 542 Liquipedia pages but was not audited |

### Orgs, teams, rosters

| Concept | Representation | Notes |
|---|---|---|
| Team | `teams.team_id`: a FACEIT team id, or `lp:team:<name>` | 146. A FACEIT id follows a roster and can be recycled |
| Team name history | `team_names` (first and last seen) | 107 rows |
| Organisation | `orgs.org_id` | 69, each created by a reviewed decision |
| Team to org | `team_orgs` with `valid_from` / `valid_to`; a trigger refuses overlap | 109 windows. `scope/org_decisions.json` is the source |
| Identity at a time | `team_identity_at(team_id, at)` returns `org_key`: the org id inside a window, else `team:<id>` | every fact view joins it at the series' own time. 13 team ids resolve to more than one identity over time (0464a373 to five) |
| Roster membership | **No roster table and no membership dates.** `series_lineups` (view): player x series x team | FACEIT's declared line-up (a substitute only if he played a map), or Liquipedia's line-up for a Liquipedia-only series through a reviewed player anchor |
| Stints | computed in `owcsmuse/nlq/membership.py` as runs of consecutive series for one identity | first and last series dates, not signing dates |
| Season-scoped groups | `team_groups` / `team_group_members`: the partner teams, 23 rows over 2025 and 2026 | Liquipedia's record, reviewed |

So "played for X" can only mean "was in a line-up of a series X played", dated by that series. That is a sound
definition for a trivia game: it is evidence of playing, not of being signed.

### Seasons, events, stages, placements

| Concept | Representation | Notes |
|---|---|---|
| Season | `championships.season` (2024, 2025, 2026) | no season table |
| Competition | `championships`: 62 included. FACEIT championships, FACEIT League divisions found by the history crawl, and `lp:` events | `scope_region` is `na`, `emea` or `international`; `tier` is `main` or `relegation` |
| Display name | `championship_display_name()` over reviewed `competition_names` | "OWCS 2025 NA Stage 2 Playoffs" |
| Stage and phase | **Not structured.** Year, region, stage and phase live in the reviewed display name | 32 regular-season or group competitions, 20 playoffs or main events, 2 relegation, 8 international. `matches.round` and `matches."group"` are filled for all 542 FACEIT matches but carry no bracket meaning that was verified |
| Placings | `liquipedia_placements` and the `placements` view, position kept as a range (`7-8`) | **76 rows over 6 international events only.** All 76 resolve to an identity. No regional stage, Dreamhack Dallas or 2026 Champions Clash placings |

### Matches and maps

| Concept | Representation | Notes |
|---|---|---|
| Series | `series` (view): one row per match whichever source holds it, with per-field provenance | 822 in scope, none without a winner, a date or both teams |
| Maps | `match_rounds` (FACEIT), `liquipedia_rounds` (Liquipedia-only series); `fact_team_maps` reads both | 28 series have no map rows from any source |
| Map winner | `map_winner()` from the scores; a tie is nobody's win | |
| Player map participation | `fact_player_maps` (maps with stats, 14,817 rows, 351 players) and `fact_player_map_results` (every played map, 30,633 rows, 406 players, filled from the series line-up where a map has no player rows) | |

### Player stats

- **Grain:** player x map (`match_players`), the grain FACEIT reports. Typed columns for eliminations, final blows,
  deaths, assists, damage, healing, mitigation, objective time and time played, plus the full payload as jsonb.
- **Units:** counts and totals per map. `time_played` is seconds. FACEIT also ships per-10 rates per map; Muse
  recomputes a rate from its components (`stat_rate_components`, migration 047) and never averages them.
- **Sample-size fields:** `maps`, `matches`, and `maps_with_<stat>` per stat on every aggregate.
- **Aggregates:** `agg_player_stats` (player x team x competition x map x mode), `agg_player_season`,
  `agg_player_stat_long`. Coverage is in `stat_coverage_season`.
- **Coverage-aware access:** `stat_leaderboard()` and `stat_coverage_summary()`.

### Hero bans

`liquipedia_bans` and `fact_hero_bans` (materialized): 3,242 bans, one per team per map, 2025 and 2026 only (bans
began in 2025), NA, EMEA and international. Each ban belongs to a team identity. Hero picks are recorded by neither
source, and the hero list has no roles.

## 3. Coverage

### Series, by season and region

| Season | Region | Series | With per-map player stats | Without | Notes |
|---|---|---|---|---|---|
| 2024 | NA | 144 | 68 | 76 | Stages 1-2 from FACEIT. Stages 3-4 (68 series) are Liquipedia-only |
| 2024 | EMEA | 143 | 68 | 75 | same |
| 2024 | International | 63 | 0 | 63 | Dreamhack Dallas (14), EWC 2024 (35), World Finals (14) |
| 2025 | NA | 114 | 102 | 12 | all three stages |
| 2025 | EMEA | 114 | 103 | 11 | all three stages |
| 2025 | International | 64 | 0 | 64 | Champions Clash, Midseason Championship, World Finals |
| 2026 | NA | 69 | 34 | 35 | Stages 1-2 and relegation. Stage 3 has none: FACEIT's rooms were aborted |
| 2026 | EMEA | 69 | 34 | 35 | same |
| 2026 | International | 42 | 0 | 42 | Champions Clash, Midseason Championship |

Team and event history covers all 822 series. Player stats cover 409 of them, and **no international series at
all**.

### Players

| Season | In a line-up | With role data | No role data | of those, played NA/EMEA regional |
|---|---|---|---|---|
| 2024 | 427 | 268 | 159 | **115** |
| 2025 | 212 | 151 | 61 | 1 |
| 2026 | 158 | 94 | 64 | 8 |

517 players have at least one line-up appearance; 351 have at least one map with stats. All 150 Liquipedia-born
players have none. 90 players appear in all three seasons, 100 in two, 327 in one. 22 players have line-ups in both
NA and EMEA regional play.

Roles played per player-season: 481 of 513 player-seasons are one role, 31 are two, 1 is three. Two player-seasons
tie for primary role. 12 map rows carry a role that is not one of the three (`-`, `None`); the counter ignores them.

### Stats

| Stat | 2024 | 2025 | 2026 |
|---|---|---|---|
| Eliminations, Deaths, Damage, Healing, Mitigation (totals) | 100% | 100% | 100% |
| Time Played, Final Blows | none | 99.9% | 99.8% |
| Any per-10 rate | none | 100% | 100% |

Maps per player-season: median 12 in 2024, 37 in 2025, 31.5 in 2026. Player-seasons with 10 or more maps: 164 of
268, 140 of 151, 74 of 94.

### Teams

118 team identities have a series: 69 orgs and 49 unmapped team ids standing as themselves. Identities with a
series, by season: NA 39 / 14 / 11, EMEA 34 / 11 / 10, international 17 / 19 / 16. 2024 is wide because the open
group stages were in the main competition that year.

### Freshness

The last series in the warehouse was played 2026-11-01. The last FACEIT payload was fetched 2026-10-29 and the last
Liquipedia payload 2026-11-02. A note in project memory says GitHub Actions has been billing-locked since
2026-11-06, which blocks the nightly ingest; I did not verify that today, but the fetch dates are consistent with
it. Nothing in season is being missed yet (2026 Stage 3 playoffs ended 2026-11-01), but a daily puzzle that depends
on the ingest needs it running.

## 4. Data-quality issues that could produce wrong grid answers

Ordered by how much they would hurt the recommended first grid.

1. **No role for anyone outside FACEIT's map stats.** 115 players played 2024 NA or EMEA Stages 3-4 and have no
   role data for 2024; 8 more for 2026 Stage 3. A player who was a Tank only in 2024 Stage 4 is a true answer the
   game would reject. This is a false negative, the worst kind for a guessing game. It affects every role cell.
2. **Role is per map, so a fill-in counts.** Simple has 104 Support maps and 4 Tank maps in 2025, and at a 4-map
   floor is a valid "Tank x 2025" answer. KSAA is a "Tank x 2026" answer on exactly 4 maps. Whether that is right
   is a product rule, not a data fact. Raising the floor to 10 removes both.
3. **Dreamhack Dallas line-ups are incomplete.** All 14 Dallas series hold 4 players each in `series_lineups`
   (FACEIT's LAN rooms declared about two per side). Liquipedia's line-ups for linked series are stored but the
   view uses them only for Liquipedia-only series. Across all linked result-only series, Liquipedia names 202
   player-series appearances (73 players) that `series_lineups` lacks. A player whose only series for a team was at
   Dallas is missing from "played for" and "competed at".
4. **A Liquipedia line-up is the listed roster, not who played.** Liquipedia-only series average 12.4 (EMEA) and
   14.0 (NA) players per series in 2024 Stages 3-4, against 10 for FACEIT. Benched players are counted as having
   played. This is a false positive for "played for X in 2024".
5. **12 Liquipedia player pages are undecided** (class C in `scope/lp_only_identity_report.md`), plus W1ll and
   Massivepoop. Their Liquipedia-only appearances are in no line-up. Per season and region, 1 to 6 pages are
   unanchored. Several have FACEIT namesakes (Ailiseu, Aniyun) who are in the answer sets as different people.
6. **Display-name collisions among players.** Three players are shown as "Danny" and two as "Goose". Autocomplete
   must show something that tells them apart (team and seasons), and a guess must submit an id.
7. **Display-name collisions among teams.** Two unrelated identities are each shown as "Geekay Esports" (NA 2025,
   EMEA 2026), "NTMR" (`ntmr`, `ntmr-2026`) and "Sakura" (NA org, EMEA team id). All six appear in team-answer
   cells.
8. **49 of 118 team identities are unmapped team ids.** Twisted Minds, ENCE, Toronto Defiant and M80 are
   `team:<id>`, not orgs. All 18 multi-name ids were reviewed by the owner, and three unmapped ids carry two names
   that were decided renames (Goud Guys ANM, ENCE, PxG PiP). An unmapped single-name id that spans seasons has not
   been explicitly confirmed as one organisation. That is correct by Muse's rules ("an unmapped id is itself") but
   Grid would present it to players as an organisation.
9. **Identity is finer than a fan's idea of a team.** `ntmr-2026` is deliberately not NTMR; KAFE is not Extinction
   or The Kafe's earlier id. "Played for NTMR" excludes the 2026 Stage 3 roster. Correct, and guaranteed to
   generate disputes.
10. **Two players are shown under names in non-Latin script** (꼴리는대로한다, 서휘) whose folded form is empty, and
    two have an empty in-game name. They resolve by FACEIT nickname, but a fold-based autocomplete would not match
    their shown name.
11. **Placings exist for 6 events.** "Won an event" cannot be asked of a regional stage, Dreamhack Dallas or the
    2026 Champions Clash without new data or a derivation from the bracket.
12. **Relegation is in scope in the data** (2 competitions, 12 series, `tier = 'relegation'`, `include = true`)
    though the stated scope is main series. The counter includes whatever `include` says.
13. **The 2025 and 2026 main series was reconstructed by a crawl** (`main_series_2025_2026` limitation). A series
    played wholly by players the crawl never reached would be absent with nothing to show it.

## 5. Can the NL query layer supply grid predicates?

Not as it stands. `StructuredQuery` (`owcsmuse/nlq/schema.py`) describes one question: an intent, one entity, one
metric, one set of filters, and it compiles to SQL that returns ranked rows for display (`nlq/compile.py`, one
branch per intent). A grid condition is a different shape: a predicate that yields a set of entity ids, to be
intersected with another on the same fact rows. There is no intent that returns "every player who satisfies X", and
the compiler has no notion of two filters that must hold on the same row versus independently.

What is reusable, and should be reused rather than rebuilt:

| Muse piece | Use in Grid |
|---|---|
| `team_identity_at()` | every "played for" and every team answer |
| `series_lineups`, `series` | participation, at series grain |
| `fact_player_maps`, `match_players.role` | role and stat conditions |
| `placements`, `team_group_members` | team conditions |
| `stat_rate_components` and the recompute-from-components rule | per-10 conditions |
| `LEADERBOARD_MIN_MAPS` (4) | the default floor, so Grid and Muse agree on who "counts" |
| `entity_names`, `owcsmuse.resolve.fold()` and `rank_candidates()` | autocomplete |
| `Filters`' vocabulary (`Role`, `Region`, season) | condition parameter types |
| `source_capabilities` | the coverage statement on every stat cell |
| `Answer.attribution` / `liquipedia/attribution.py` | crediting Liquipedia pages behind a cell |
| `ConnectionPool`, `Throttle`, `per_client` in `api.py` | the Grid router |
| the reviewed-decisions pattern (`scope/*.json` plus a loader plus `decisions_loaded`) | curated puzzles and answer overrides |

## 6. Capability matrix

**Supported** means the schema holds it, a query proved it, and coverage is complete for the scope stated.
**Partially** means it works for a stated slice or needs a rule. **Unsupported** means the data is not there.
"Counter" says whether the Phase 0 cell counter exercises it.

### 4A. Player Grid

| Family | Status | Evidence | Coverage | Missing work |
|---|---|---|---|---|
| Role | **Partially** | `match_players.role` per map; 513 player-seasons with a role. Counter: `role:` | Maps with FACEIT stats only: 2024 Stages 1-2, 2025, 2026 Stages 1-2. None for international events, 2024 Stages 3-4, 2026 Stage 3, or the 150 Liquipedia-born players | A role source for the gaps (Liquipedia player pages, reviewed), or labels that scope the clue, plus a "cannot verify" result for players with no role data. A floor decision (4 or 10 maps, or primary role) |
| Season participation | **Supported** | `series_lineups` x `championships.season`: 427 / 212 / 158 players. Counter: `season:` | All 822 series | Dallas line-ups (issue 3); listed-not-played on Liquipedia-only series (issue 4) |
| Region | **Partially** | `championships.scope_region`. Counter: `region:` | NA, EMEA, international. Nothing for Asia, Korea or China leagues: not ingested | Stage 5 of the Liquipedia work for Korea and China. A player has no home region, only regions played in |
| Team affiliation | **Supported** | `series_lineups` + `team_identity_at()`: 118 identities, 252 players with two or more. Counter: `org:` | All series | Name collisions (issue 7); unmapped ids presented as orgs (issue 8) |
| Tournament participation | **Supported** | line-up x competition, 62 competitions. Counter: `event:` | All series | An event is matched by reviewed name; a stage spans several competitions. Dallas (issue 3) |
| Performance ranking | **Partially** | per-10 recomputed from totals and Time Played. Counter: `per10_top:` | 2025 and 2026 regional only | Nothing for 2024 (no Time Played). Refused there, by design |
| Elimination, death, healing, mitigation thresholds | **Partially** | same. Counter: `per10_min:`, `per10_max:` | 2025 and 2026 regional only | Thresholds need choosing per role and season so cells are neither empty nor everyone |
| Experience (N maps) | **Partially** | `fact_player_map_results`: 30,633 rows, 406 players, including maps with no player stats. Not in the counter | NA and EMEA regional; international maps have no per-player rows beyond the line-up | A condition class; a rule for Liquipedia-only series (listed roster) |
| Longevity | **Supported** | seasons per player: 327 / 100 / 90. Counter: `min_seasons:` | All series | Only three seasons exist, so "3+ seasons" is the only non-trivial value |
| Roster movement | **Supported** | identities per player: 265 with one, 130 two, 62 three, 60 four or more. Counter: `min_orgs:` | All series | Counts identities, not organisations a fan would count (issue 9). One player has 9 |
| Playoff experience | **Partially** | 20 competitions are named Playoffs or Main Event. `event:Playoffs` works in the counter | Regional playoffs and main events | "Reached the semi-final" is unsupported: no structured bracket round. Needs a phase column or a reviewed list |
| Championship experience | **Partially** | `placements` for 6 international events, crossed with that event's line-up. Not in the counter for players | International only | Regional stage winners (derivable from each playoff bracket's last series, as `placement_consistency` does, then reviewed) |

### 4B. Performance Grid

| Clue | Status | Evidence | Missing work |
|---|---|---|---|
| Top N in a stat for an event or period | **Partially** | `per10_top:` by season and role; `stat_leaderboard()` by competition | 2025-2026 only. Event scope is a small extension |
| Above or below a threshold | **Partially** | `per10_min:`, `per10_max:` | 2025-2026 only |
| Highest or lowest within a role | **Partially** | role is a required parameter of every per-10 condition | same |
| Top percentile among eligible players | **Partially** | derivable from the same rates | Not built |
| N maps and a threshold | **Partially** | `--min-maps` applies to every stat condition | same |
| Metrics: eliminations, deaths, damage, healing, mitigation per 10 | **Partially** | 100% coverage in 2025 and 2026, none in 2024 | 2024 supports totals and per-map averages only |

A Performance Grid for 2025 passed at a 10-map floor (7 to 12 per cell), but only with "top 15", which is half of
the eligible Tanks. See CELL_COUNTS.md.

### 4C. Esports History Grid (team answers)

| Family | Status | Evidence | Coverage | Missing work |
|---|---|---|---|---|
| Region | **Partially** | competitions played in, by `scope_region`. Counter: `region:` | NA, EMEA, international | No home region for a team. Korea and China teams appear only at international events. Partner teams have a region (`team_groups`), others do not |
| Event participation | **Supported** | `series` x competition. Counter: `event:` | All 822 series | none |
| Placement | **Partially** | `placements`, 76 rows. Counter: `placed_top:` | 6 international events | Regional stages, Dallas, 2026 Champions Clash |
| Championship | **Partially** | `placed_top:1` | same | same |
| International appearance | **Supported** | `region:international`: 17 / 19 / 16 identities by season | All international events in scope | none |
| Organisation | **Partially** | the answer is itself an identity | 69 orgs, 49 unmapped ids | A decision on whether an unmapped id may be a team answer |
| Roster continuity | **Unsupported** | no dated roster snapshots; derivable from line-ups per stage only once a stage is structured | n/a | A stage dimension, and a rule for listed-not-played rosters |
| Match history ("beat X") | **Supported** | `series.winner_side`, no series without a winner. Counter: `beat:` | All series | none |
| Map history ("won on map X") | **Supported in data** | `fact_team_maps`: 66 identities have won on Lijiang Tower, 53 on King's Row. Not in the counter | 794 of 822 series have map results | A condition class |
| Competition stage | **Partially** | phase readable from the reviewed name | 54 regional competitions | A structured phase column |

### 4D. Advanced

| Family | Status | Evidence | Missing work |
|---|---|---|---|
| Hero specialists | **Unsupported** | hero picks are recorded by neither source (`docs/answers.md`) | no source |
| Team compositions | **Unsupported** | same | no source |
| Map specialists and map win rates | **Partially** | `agg_team_maps` for teams; `agg_player_stats` by map for players with stats | thresholds and a sample floor |
| Hero bans | **Partially** | `fact_hero_bans`: 3,242 bans; 19 identities banned D.Va on 5 or more maps | 2025-2026 only; team answers only; no Korea or China leagues |
| MVPs and awards | **Unsupported** | the placings parser leaves individual awards out | new data |
| Head-to-head records | **Supported** | series results between identities | none |
| Cross-region career | **Partially** | 22 players have line-ups in both NA and EMEA | NA and EMEA only |
| Career chronology and transfers | **Partially** | stints from consecutive series (`nlq/membership.py`) | series dates, not transfer dates |

## 7. Answers to the brief's section 8 checklist

- **Stable ids:** yes, for players and for team identities. Never a display name.
- **Aliases:** yes, and time-stamped. Community shorthand is reviewed and currently team-only.
- **Role time-aware:** yes, per map. There is no current-role field to misuse.
- **Dated roster membership:** no. Line-ups per series, which is better evidence but has no join and leave dates.
- **International and regional events represented consistently:** yes for series and teams; no for player stats
  and placings.
- **Maps played computable reliably:** yes for NA and EMEA regional play.
- **Stats comparable across formats and patches:** within a season and a role, yes. Across 2024 and later, no:
  different stat keys. Patch is not recorded anywhere.
- **Last updated:** not stored as one value. The newest payload and series dates serve; see Freshness.
