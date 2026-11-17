# Grid Phase 0: working notes

## State: polish, IN PROGRESS on `grid/polish` (stopped 2026-11-17, usage limit)

Done and committed: the new generator rules (3+ shared clues within 21 days, one "N+ maps" clue, two teammate clues,
one stat clue an axis; difficulty by median and smallest cell), backtracking in the day search, a wider clue pool,
`scope/grid_anchors.json` (60 candidates, 52 approved by rule; the generator uses approved ones only), `/?q=` in the
Muse frontend, a Muse link on every Grid answer with a FACEIT id, `--rebuild-all`, and all 35 puzzles regenerated
(2026-11-17 to 2026-12-21, run output in `runs/generate_2026-11-17_35d_seed20261117.txt`). Grid tests (88) and
frontend tests (125) pass; lint is clean.

NOT done: VERIFY.md still lists the old puzzles 2-8 (regenerate it for the new puzzles 1-7); BETA.md and
CATEGORIES.md do not yet describe the new rules, the anchor file, the links or the 35-puzzle supply; the full
offline suite and the frontend build were not rerun after these changes; the two older run files in `runs/`
describe discarded puzzles. Step 3 (org mappings) was skipped: the list in the request was left as a placeholder.

## State: mixed clues built on `grid/categories`, not pushed, not deployed (2026-11-17)

Read [BETA.md](BETA.md) (top section) and [CATEGORIES.md](CATEGORIES.md) first.

- Branch `grid/categories`, cut from `grid/beta`. Still no migration, no database writes, no visitor data.
- 31 puzzles in `scope/grid_puzzles.json`: puzzle 1 (2026-11-18, a beta role grid, untouched) and 30 mixed-clue
  puzzles, 2026-11-19 to 2026-12-18. **Nothing generates more automatically.** Before 2026-12-19: run
  `build_facts.py`, then `generate_puzzles.py`, commit, deploy.
- Decisions the owner made for this step (do not reopen): mixed clues from at least 4 families; the rejection rules
  in BETA.md; difficulty by median cell, easier early in the week; awards only when reviewed; never apply an org
  mapping; every clue states its scope.
- **Waiting on the owner:** [VERIFY.md](VERIFY.md) (answers to hand-check, 20 stage winners, 21 awards),
  [proposed_org_mappings.md](proposed_org_mappings.md) (49 unmapped team ids, nothing applied), and the `reviewed`
  flags in `scope/grid_awards.json` and `scope/grid_stages.json`.
- Existing files touched in this step: none outside Grid's own (`owcsmuse/grid/`, `scripts/grid/`, `web/src/grid/`,
  `tests/grid/`, `web/tests/grid.test.jsx`, `scope/grid_*.json`, `docs/grid/`).

Easy to forget:

- A cell is two clues judged separately, except a role beside a season or region (that role, there).
- `clues.py` counts maps for season and region clues; the beta's column conditions counted line-ups for "all 3
  seasons". Puzzle 1 keeps the beta's meaning.
- The stage clues use every stage in `scope/grid_stages.json` whose `agree` is true, reviewed or not. Awards need
  `reviewed: true` and a `player_id`.
- Liquipedia was not called. Muse's client stores each response in `raw_payloads`, which is a database write.
  Everything Liquipedia-sourced here was read from responses already stored.
- A teammate clue's stored key holds the anchor's player id; the API sends positional keys (`row0`, `col2`).
- Heredocs with long quoted content fail in this shell: write a patch script to a file and run it.

Not done:

- Ten stages have no Liquipedia placement table to cross-check against (not fetched: it needs a write).
- "N+ maps" bounds unrecorded series at 7 maps each; the real count is in Muse and could be loaded.
- No independent derivation of any answer from raw payloads; nothing is confirmed by a person.
- Not tried on real phones; the Docker image was not built locally.

## State: beta built on `grid/beta`, not pushed, not deployed (2026-11-17)

Read [BETA.md](BETA.md) first: what was built, how to run it, how to generate puzzles, what is not done.

- Branch `grid/beta`, cut from `grid/phase-0`. No migration, no database writes, no visitor data on the server.
- 14 puzzles generated, 2026-11-18 to 2026-12-01 (`scope/grid_puzzles.json`). **Nothing generates more
  automatically**: run `scripts/grid/generate_puzzles.py` before 2026-12-02, commit, deploy.
- Decisions the owner made for the beta (do not reopen): role x column only; 10-map floor everywhere; players only;
  "can't verify" for no role data; 9 guesses, one cell per player, score out of 9; NA and EMEA main series only;
  00:00 UTC rollover; all progress in localStorage.
- Existing files touched: `owcsmuse/api.py` (router registration), `web/src/router.js`, `web/src/App.jsx`,
  `web/.env.example`. Nothing else.
- Still open from Phase 0: the three golden cells are unconfirmed; PLAN.md sections 3 and 6 describe the
  table-backed version this beta deliberately is not.

## Phase 0 (2026-11-16)

Deliverables, all on branch `grid/phase-0`:

- [AUDIT.md](AUDIT.md): repo map, data model, coverage, data-quality issues, capability matrix.
- [CELL_COUNTS.md](CELL_COUNTS.md): every candidate grid, verdicts, three proposed golden cells.
- [PLAN.md](PLAN.md): first format, architecture, schema changes, test plan, Phase 1 tasks, decisions.
- `scripts/grid/`: the read-only cell counter and its README. `tests/grid/test_conditions.py`: 12 offline tests.
- [runs/](runs/): the raw output of every counter run.

**Nothing may proceed past here without approval:** no schema change, no edit to existing code. PLAN.md section 3
lists every such change; section 6 lists the decisions.

## How the session was set up

- Branch cut from `origin/main` at c96a145. The checkout had been on `fix-cls-web-nav-ingest-state`, 3 commits
  behind, so the branch was not cut from it.
- The brief is at `docs/owcs-grid-planning-brief.md`, untracked, not under `docs/grid/`. Left where it was and not
  committed.
- Database: no local Postgres (Docker not running, nothing on localhost:5432). Production Supabase was the only
  database reachable. Every query was a SELECT on one connection in a `READ ONLY` transaction
  (`scripts/grid/db.py`). `schema_migrations` matched `migrations/` in both directions (52).
- Nothing outside `docs/grid/`, `scripts/grid/` and `tests/grid/` was created or changed.

## Things learned that are easy to forget

- Role lives on `match_players.role`, per map. There is no player-level role. Values `-` and `None` occur (12 rows).
- There is no roster table. Membership is `series_lineups`, and identity is `team_identity_at(team_id, played_at)`.
- `series_lineups` uses Liquipedia's line-up only for Liquipedia-only series. Linked result-only series (all of
  Dreamhack Dallas) keep FACEIT's short line-up: 4 players a series.
- Liquipedia line-ups list the roster, not who played: 12 to 14 players a series in 2024 Stages 3-4.
- Placings exist for 6 international events only.
- In the counter, `Region` and `Event` share the dimension `competition`, so a region x an event is each on its own
  series. Every other pair of different row dimensions is correlated on the same rows.
- Counts move with the nightly ingest. Rerun the counter before quoting a number; the ones in these documents are
  from 2026-11-16, with the last series in the warehouse played 2026-11-01.

## Not done, deliberately

- No independent derivation of the golden cells from raw payloads. They are proposed, and agree across two SQL
  paths over the same tables only.
- `player:<id> record` was not asked through the API (it writes `saved_queries` and `query_log`).
- Conditions for "won on map X", "banned hero Y", maps played including maps without stats, and regional stage
  winners are described in AUDIT.md but not in the counter.
