# OWCS Grid: plan

Follows from [AUDIT.md](AUDIT.md) and [CELL_COUNTS.md](CELL_COUNTS.md). Nothing here is built. Every item that
touches existing code or the schema is listed separately in section 3 and waits for approval.

## 1. Recommended first format

**A Player Grid whose rows are the three roles.** The first published puzzle is role x season:

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| **Tank** | 33 | 31 | 14 |
| **DPS** | 66 | 55 | 29 |
| **Support** | 65 | 52 | 31 |

Counts are at a 10-map floor (CELL_COUNTS.md, grid a). Reasons:

- It is the only format where every cell is deep, so a correction to one identity cannot sink a cell.
- Role is recorded per map, so "played Tank in 2025" is a fact about 2025, with no current-role field to leak in.
- It is the brief's own first suggestion and needs no explanation to a player.

Role x season is one puzzle, not a format. The daily supply comes from keeping roles as the rows and rotating the
columns, all of which the counter already supports:

| Columns | Status |
|---|---|
| seasons | viable (above) |
| NA, EMEA, "3+ seasons" | viable: 19 to 53 per cell at a 10-map floor (CELL_COUNTS.md, grid f) |
| teams (three of the eight that span all seasons, or any three) | marginal: no team has 5 Tanks (grid c1). Needs a floor of 3 for that format |
| events ("played at 2025 Stage 2 Playoffs") | to count |

Second format, once the first works: org x season (grid c3). Third: a team-answer grid built from cross-cutting
conditions (region, "beat X", "banned hero Y"), not the nested ones tried in d2 and d3.

**I recommend a 10-map floor** for a role cell, stated in the clue's help text ("at least 10 maps in the role that
season"). At 4 maps a single-series fill-in is a valid answer (Simple as a 2025 Tank), which is defensible from the
data and will read as a bug to players.

**I recommend a third result besides right and wrong.** 115 players who played 2024 Stages 3-4 have no role on
record. Guessing one of them for "Tank x 2024" should return "we have no role data for this player in 2024" and
not cost a guess. The alternative is to label the column "2024 (Stages 1-2)", which is honest but reads oddly and
still rejects true answers.

## 2. MVP architecture

One backend, one frontend, one database, as now. Grid is a new package beside `nlq`, a new router, a new route in
the existing React app and four new tables.

### Data flow

```
nightly ingest ... refresh -> check passes
        |
        v
grid generate   compute the nine answer sets for the next unpublished dates, from the warehouse (read-only)
        |       reject a puzzle with a cell under the floor; log why
        v
grid publish    one transaction: write the puzzle and its answer ids. From here the puzzle never reads the warehouse
        |
        v
API  GET /grid/today        conditions and labels only
     POST /grid/{n}/guess   {row, col, entity_id} -> right | wrong | cannot verify, checked against the snapshot
```

### Backend: `owcsmuse/grid/`

| Module | What |
|---|---|
| `conditions.py` | the typed condition classes, promoted from `scripts/grid/conditions.py`. Still a closed list |
| `facts.py` | the four fact loaders (`scripts/grid/data.py`), reading `series_lineups`, `fact_player_maps`, `series`, `placements` through `team_identity_at()` |
| `generate.py` | builds a puzzle from a definition, applies the validation rules, returns the snapshot or the reason it was rejected |
| `store.py` | publish, load, record a guess count. The only module that writes |
| `router.py` | a FastAPI `APIRouter` |

Reuses: `ConnectionPool`, `Throttle` and `per_client` from `api.py`; `fold()` from `resolve.py`; `entity_names`;
`source_capabilities` for coverage lines; `liquipedia/attribution.py` for page credits; `slug_for()` for links.

### Routes

No `/api` prefix, matching the existing five routes. Statuses follow Muse's convention: a wrong guess is a 200 with
a result in the body; 404 is an unknown puzzle; 422 a malformed request; 429 the existing per-IP throttle.

| Route | Returns |
|---|---|
| `GET /grid/today` | puzzle number, date, mode, the six condition labels with their help text and coverage lines, the Liquipedia attribution. **No answers and no ids** |
| `GET /grid/{n}` | the same for a past puzzle |
| `GET /grid/players` (and `/grid/teams`) | the autocomplete index: every player's id, shown name, other names on record, and a disambiguator (last team, seasons). The whole index, the same for every puzzle, cacheable |
| `POST /grid/{n}/guess` | body `{row, col, entity_id}`. Returns `result` (`correct`, `incorrect`, `unverifiable`), and for a correct guess the entity's name, a one-line reason ("31 maps as Tank for Team Liquid in 2025") and its Muse link |
| `GET /grid/{n}/answers` | every cell's answers. **Only for a puzzle whose day has ended** |
| `GET /grid/archive` | past puzzle numbers and dates |

**The answer set never reaches the client.** The only way to learn it is one guess at a time. Shipping the whole
player index for autocomplete is deliberate: it is every player, not the valid ones, so it leaks nothing, and it
avoids a database query per keystroke on an API limited to 6 connections. A guess submits an id chosen from that
list, never text, so "Danny" (three players) is never resolved by the server guessing.

Someone can still enumerate a cell by guessing all 574 players. The existing throttle (20 burst, 30 a minute)
makes that take 20 minutes per cell. With no leaderboard there is nothing to gain. If rarity or leaderboards
arrive, guesses need a server-side budget (below).

Today's puzzle and its answer sets are loaded into memory once per process and kept (a published puzzle is
immutable), so validating a guess touches no database. Guess counts are written in a background task, like
`query_log`, and never fail the response.

### Frontend: `/grid`

- `web/src/router.js` gains two patterns, `/grid` and `/grid/<n>`. `web/vercel.json` already rewrites every path
  to `index.html`.
- New files under `web/src/grid/`: the board, a cell, the autocomplete input, the result and share view. Plain CSS
  in the existing stylesheet's vocabulary. No new dependency.
- A nav link between the question page and the grid.
- Progress lives in `localStorage`, keyed by puzzle number.
- **Linking an answer to Muse.** There is no player page. A correct answer links to the question
  `player:<id> record` (or `org:<id> record`), asked through the app's existing `onAsk` path, which produces a
  `/q/<slug>` URL. A plain `<a href>` to `/q/<slug>` works only after that question has been saved once, so the
  link must go through the ask path, not be precomputed. To verify in Phase 1: that `player:<id> record` gives a
  useful answer for a Liquipedia-born player, who has series but no stats. If it does not, omit the link for them.

### Anonymous play

Muse has no accounts and stores nothing about who asked. I recommend Grid's MVP keeps that: **no per-player rows on
the server at all.** The browser holds its own progress, streak and history. The server stores only an aggregate
count per (puzzle, cell, answer), which is all rarity needs later.

The cost: a guess limit is enforced by the client only, and streaks do not follow a player across devices. Both
are acceptable without leaderboards. A server-side play record (a random token from `localStorage`, no IP) is the
upgrade path, and is a decision for you because it changes Muse's "nothing about the asker" stance.

### Snapshotting

- `grid publish` computes all nine cells in one `REPEATABLE READ` transaction, so they agree with each other, and
  writes the puzzle and its answer ids in that same transaction.
- A published puzzle's answer rows cannot be updated or deleted (a trigger refuses, as `team_orgs_no_overlap`
  already refuses overlapping windows).
- Each answer row stores the id, the name as shown at publish, and the reason line. A later rename or identity
  merge does not change yesterday's puzzle.
- The puzzle row stores the condition definitions, the rules (floor, minimum answers), the generator version and
  the newest series date it saw.
- A correction after publication **adds** an accepted answer through an append-only corrections table with a
  note. It never removes one: nobody loses a cell they were given.

### Where generation runs

A new last step in `ingest.yml`, after `check` passes: `python -m owcsmuse grid publish --ahead 7`, which makes
sure the next seven dates each have a published puzzle. If `check` fails, the step does not run, so a puzzle is
never built on data the gate rejected.

The buffer is the important part. The ingest is not reliable on any given night: its start has drifted by hours
(`docs/open-items.md`, item 6), a Liquipedia 429 can leave it partial, and project memory records a GitHub Actions
billing lock from 2026-11-06 that stops it entirely. With seven days published ahead, the game outlives a week of
that. The API picks today's puzzle by date alone and never generates anything.

The trade: a puzzle published on Monday for Sunday does not know Saturday's matches. That is the same property as
"yesterday's puzzle never changes", applied forward.

Selection of which puzzle to publish: see decision 9. I recommend definitions in a reviewed file,
`scope/grid_puzzles.json`, loaded like every other decision in `scope/`, with the generator proposing and
validating and a person approving. That is the pattern this project already trusts.

### Attribution

A cell that drew on a Liquipedia line-up, a Liquipedia-only series or a placing owes its page under CC-BY-SA. The
snapshot stores the page URLs behind each puzzle at publish, and `/grid/today` returns them in the same
`attribution` shape `/ask` uses, so the existing `Attribution` component renders them.

## 3. Schema changes

Listed apart from the architecture because **a merge to `main` migrates production unattended**
(`fly.toml` `release_command`). All of these are additive: new tables only, nothing existing altered.

### Phase 1: one migration, `053_grid.sql`

Tables in `public` with a `grid_` prefix, not a schema of their own. Muse pins one `search_path`
(`OWCS_DB_SCHEMA`), and the test suites rebuild everything inside one scratch schema; a second schema would break
both.

| Table | Columns | Notes |
|---|---|---|
| `grid_puzzles` | `puzzle_no` (PK), `puzzle_date` (unique), `mode`, `entity`, `row_conditions` jsonb, `col_conditions` jsonb, `rules` jsonb, `generator_version`, `data_as_of`, `attribution` jsonb, `published_at` | one row per day |
| `grid_cell_answers` | `puzzle_no`, `cell_row`, `cell_col`, `entity_id`, `verdict` (`valid` or `unverifiable`), `name_at_publish`, `reason`; PK on the first four | the snapshot. Update and delete refused by trigger |
| `grid_answer_corrections` | `puzzle_no`, `cell_row`, `cell_col`, `entity_id`, `note`, `decided_at` | append-only additions |
| `grid_guess_counts` | `puzzle_no`, `cell_row`, `cell_col`, `entity_id`, `guesses`, `correct` | aggregate only; no player, no IP |

Size: a role x season puzzle at a 10-map floor has about 380 answer rows plus the unverifiable ones. A year is
roughly 200,000 rows, on the order of 20 MB. The database is at 300 MB of 500, so this is affordable but not free;
an archive older than a year could be compacted to one jsonb row per puzzle.

Supabase: the default privileges already revoke `anon` and `authenticated` on new objects, and the
`api_role_grants` check will confirm it.

### Edits to existing files that Phase 1 needs (each needs approval)

| File | Change |
|---|---|
| `owcsmuse/api.py` | one `app.include_router(...)` line in `create_app()`; `POST` is already allowed by CORS |
| `owcsmuse/cli.py` | a `grid` command group (`generate`, `publish`, `preview`) |
| `owcsmuse/consistency.py` | one check: every published puzzle has nine cells, each at or above its floor, each answer id still exists |
| `.github/workflows/ingest.yml` | the publish step after `check` |
| `web/src/router.js`, `web/src/App.jsx` | the two routes and the nav link |
| `tools/build_fixture_db.py` or `tests/golden_support.py` | only if grid golden cases run on the golden warehouse |

### Later, not Phase 1, and each changes existing behaviour

| Change | Why | Risk |
|---|---|---|
| A reviewed `player_roles` table (player, season, role, basis, page) from Liquipedia player pages | closes the 115-player role gap for 2024 and gives Liquipedia-born players a role | Liquipedia budget (60 requests an hour); a new review queue; primary role, not per-map |
| `series_lineups` reads Liquipedia's line-up for a linked result-only series | fixes Dreamhack Dallas (4 players a series) and 202 missing appearances | **changes Muse's own answers** (player series records). Needs the golden suite and its own review |
| `stage` and `phase` columns on `championships` | "reached the playoffs", roster continuity, stage winners | must agree with the reviewed display names |
| Regional stage placings | "won a stage" | a derivation from brackets plus review, or new Liquipedia requests |

## 4. Test plan

Existing suites to follow: the offline `pytest` job (no database), the database job on Postgres 16 and 17, the
golden suite with independently derived expectations, and `web/tests/` with captured payloads.
`tests/grid/test_conditions.py` (12 tests, offline, on a hand-built warehouse) already covers the condition
semantics from this phase.

| Area | Test | Kind |
|---|---|---|
| **Aliases and IGN changes** | A player with a historical nickname, a historical in-game name and an owner display name appears once in the index, findable by each name; guessing by id is correct whichever name was typed. ZZZ (`z_ow`, `zss`) and Astro (`Astronexz`) are the real cases | database, golden |
| | Two players shown as "Danny": the index holds both with different disambiguators; a guess for one is not credited to the other | database |
| | A player renamed after publication: the snapshot's `name_at_publish` is unchanged and the guess is still correct | database |
| | A shown name that folds to nothing (서휘) is still findable | offline |
| **Historical rosters** | A player who moved mid-season counts for each team only in the series played for it. Hitori in 2025 (Extinction, then Sakura) | golden |
| | Org x season uses the team at the series' time, not now (already in `test_org_and_season_use_the_team_at_the_time`) | offline, done |
| | A substitute who never played a map is not an answer; one who played is | database |
| | A Liquipedia-only series contributes line-up players only through a decided anchor; an undecided page contributes nobody | database |
| **Recycled FACEIT team ids** | 0464a373 across UNC inc, Rad, Sakura, LuneX and KAFE: a player from one era is not an answer for another, and "played for both" across two eras of one id needs both line-ups | golden |
| | bb5dd404: an Ex Oblivione 2024 player is not a Virtus pro answer | golden |
| | A new org window loaded after publication changes the next puzzle and not a published one | database |
| **Sample-size thresholds** | A player with floor minus one maps is out, with exactly the floor is in (done offline); the same through `generate` on real payloads | offline done, golden |
| | A per-10 rate equals total over total time, not the mean of per-map rates, on a player whose map lengths differ | golden, from raw payloads |
| | A per-10 condition on 2024 is refused, not answered (done offline) | offline, done |
| | Role rows that are not Tank, Damage or Support (`-`, `None`) count for nothing | database |
| **Server-side validation** | `GET /grid/today` and `GET /grid/players` responses contain no id from any `grid_cell_answers` row beyond what the full index holds for everyone, and no per-cell data. Asserted by scanning the serialized response | API |
| | A guess with an id outside the index is 422; a wrong guess is 200 `incorrect` and reveals nothing else; a correct guess reveals that one entity | API |
| | `GET /grid/{n}/answers` is refused for today's puzzle and served for yesterday's | API |
| | The same on the frontend: no answer id in any fetched payload before a guess | Vitest, captured payloads |
| **Immutable snapshots** | After publish, change the warehouse (add a series, load an org window, rename a player), refresh, and assert every cell of the published puzzle is byte-identical | database |
| | `UPDATE` and `DELETE` on a published puzzle's answers raise | database |
| | A correction adds an answer and removes none | database |
| | Publishing the same date twice is refused | database |
| **Under-populated cells** | A definition with a cell under the floor is rejected, names the cell and its count, and writes nothing (org x org from grid b is the real case) | database |
| | A cell with zero answers is rejected even at a floor of 0 | offline |
| | A grid that cannot be filled with nine distinct answers is rejected (`distinct_solution`, done offline) | offline, done |
| | The `unverifiable` set never counts toward a cell's floor | offline |
| **Coverage** | Every role or stat cell carries a coverage line naming the competitions without player stats (done offline) | offline, done |
| **Golden** | G-A1, G-A2, G-A3 from CELL_COUNTS.md, once confirmed, with expectations derived by a function that reads `Role` from the raw `/stats` payloads and imports nothing from `owcsmuse` | golden |

Golden expectations are proposed first and asserted only once you confirm them, as for every other golden case.

## 5. Phase 1 tasks, in order

Each ends in something reviewable. Steps 1 to 4 change no existing behaviour.

1. **Settle the decisions in section 6** that shape the snapshot: floor, the unverifiable result, guess rule, which
   identities may be answers.
2. **Confirm the golden cells.** Review G-A1 to G-A3; write the independent derivation over raw payloads; record
   the cases as `proposed`, then `confirmed`.
3. **Promote the counter into `owcsmuse/grid/`** (`conditions.py`, `facts.py`) with its tests. Count the remaining
   role-row grids (role x event, role x team at a lower floor) so the first week of puzzles is known to exist.
4. **`generate.py`**: definition in, validated snapshot or a rejection out. Pure function over the fact sets.
   Tests for under-populated cells and the unverifiable set.
5. **Migration `053_grid.sql`** and `store.py`: publish, load, corrections, guess counts. Immutability tests.
   *First schema change.*
6. **CLI**: `grid preview <definition>` (the nine counts and names, before anything is written), `grid publish`.
7. **Router** and the one line in `api.py`. API tests, including the no-answers-in-the-payload scan.
8. **Consistency check** for published puzzles.
9. **Frontend**: route, board, autocomplete, results and share text, Muse links, attribution. Vitest with captured
   payloads.
10. **Publish step in `ingest.yml`**, seven days ahead. Publish the first week by hand before enabling it.
11. **Soft launch** at `/grid` with no nav link, play a week of puzzles, then link it.

## 6. Decisions I need from you

The brief's section 13, each with what the audit found and what I recommend.

| # | Question | Finding | Recommendation |
|---|---|---|---|
| 1 | Players only, or players and teams, at first release? | Player grids have 326 distinct answers; team grids 28 to 35, dominated by three teams | **Players only.** Teams as the third format |
| 2 | Does Muse store dated roster and role relationships? | Role: yes, per map. Roster: line-ups per series, no join or leave dates | **Nothing to add for Phase 1.** "Played for" means "was in a line-up of" |
| 3 | Which regions have reliable player stats, at what granularity? | NA and EMEA regional play: 2024 Stages 1-2, 2025 all stages, 2026 Stages 1-2. Nothing international. Per-10 rates from 2025 only | **Stat clues only for 2025 and 2026 regional play.** Never 2024 |
| 4 | Stats at match or map level, or aggregates? | Per player per map, with aggregates on top | No change |
| 5 | Player and team detail routes for links? | **None exist** | Link to the `player:<id> record` question. A real profile page is a separate Muse feature, worth considering on its own |
| 6 | Accounts or anonymous sessions? | No accounts, no sessions, nothing stored about the asker | **Anonymous, state in the browser, aggregate counts only on the server** |
| 7 | Unlimited guesses, a number per cell, or a shared budget? | A data fact bears on it: with ids chosen from a list there are no typos to forgive | **A shared budget of 9 guesses**, one per cell, as the genre does. Client-enforced in the MVP |
| 8 | Completion score only, or rarity from day one? | 182 questions asked on Muse in the last 30 days; rarity over that traffic is noise | **Completion only.** Collect the counts from day one so rarity can be switched on later |
| 9 | Generated, curated, or generated then approved? | Few formats pass; identity is review-driven everywhere else in this project | **Generated then approved**, definitions in a reviewed `scope/grid_puzzles.json` |
| 10 | Is `/grid` enough, or a separate app? | Two routes in a 35-line router; Vercel already rewrites every path | **`/grid` in the existing app** |

Decisions the audit raised that the brief did not list:

| # | Question | Recommendation |
|---|---|---|
| 11 | The floor for "played a role": 4 maps (Muse's leaderboard floor), 10, or primary role only? | **10 maps.** Smallest cell is still 14 |
| 12 | A player with no role data for the season (115 in 2024): wrong, or "cannot verify" without costing a guess? | **Cannot verify.** Or fund the Liquipedia role table |
| 13 | May an unmapped team id (`team:<id>`: Twisted Minds, ENCE, Toronto Defiant, M80) be a clue or an answer? | **Yes for single-name ids you recognise**, listed explicitly in the puzzle definitions; or map them to orgs first, which is the cleaner fix |
| 14 | How to show two identities with one name (Geekay Esports, NTMR, Sakura; players Danny, Goose) | A disambiguator in the index: region and seasons for teams, last team and seasons for players |
| 15 | Is relegation play in scope for Grid? It is `include = true` (12 series) | **Yes**, following Muse; say so if you would rather not |
| 16 | When does the day roll over? | One fixed time for everyone. Midnight Pacific fits the ingest (22:35 Pacific) and the audience; your call |
| 17 | Can a published answer set be corrected? | **Additions only**, with a note |
| 18 | Fix `series_lineups` for linked result-only series (Dallas)? It would change Muse answers too | **Yes, as its own reviewed change**, before any "competed at Dreamhack Dallas" clue. Not needed for role x season |

## 7. What I am not sure of

- Whether `player:<id> record` gives a good answer for Liquipedia-born players. Not run, because asking through the
  API writes `saved_queries` and `query_log`, and this session was read-only.
- Whether the 115 role-less 2024 players matter in practice. Many are open-bracket players nobody would guess. The
  count is exact; the impact on a real player's game is a guess until people play.
- The GitHub Actions billing lock is from a note dated before this session. I did not check its current state.
- The three golden cells agree across two SQL paths over the same tables. That is consistency, not correctness.
