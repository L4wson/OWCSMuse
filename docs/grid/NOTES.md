# Grid Phase 0: working notes

## State: mixed clues, IN PROGRESS on `grid/categories` (stopped 2026-11-17, usage limit)

Done and committed as work in progress:

- `scripts/grid/build_facts.py` -> `scope/grid_stages.json` (20 stages, every winner agrees with Liquipedia's match
  record, FACEIT's result and Liquipedia's placement table where held) and `scope/grid_awards.json` (21 awards, all
  `reviewed: false`, 3 unresolved: Proper).
- `scripts/grid/clues.py`: the typed clue classes (role, season, region, teammate, org, org count, stage win, stage
  final, award, LAN roster, experience, stats) with answers, reasons and can't-verify sets; `cell()`.
- `scripts/grid/mixed.py`: clue pool, the quality rules (`Judge`), difficulty, the day search.
- `scripts/grid/generate_puzzles.py`: mixed by default, `--classic` for beta grids, `--include-unreviewed` (dry run
  only). A 30-day dry run from 2026-11-19 produced a valid puzzle every day, 29 on the target difficulty.
- `owcsmuse/grid/store.py` and `router.py`: format 2 puzzles (clue reasons, clue can't-verify messages, difficulty,
  answer count in reveal). The 35 beta tests still pass.

NOT done yet:

- Frontend: header info tooltips, difficulty badge, answer count after reveal, long-label wrapping at 360-390 px.
- Tests for the new clues, each rejection rule, format 2 routes, old puzzles still playing. Nothing new is tested.
- The real 30-day generation (2026-11-19 on; leave #1, 2026-11-18, alone) and its saved run output.
- Smoke test of an Easy, a Medium and a Hard puzzle at phone width.
- docs: CATEGORIES.md (verdicts), proposed_org_mappings.md, VERIFY.md, BETA.md update.
- Full offline suite, frontend tests, build, lint.

Verdicts so far (numbers from 2026-11-17): teammate Ship (47 anchors with 12+ teammates); played-for-org Ship with
limits (14 mapped orgs with 8+ players); won a stage / finalist Ship (41 / 61 answers); award Not yet in puzzles (12
players, unreviewed); LAN roster Ship; both regions Ship with limits (13); 3+ orgs Not yet (15 answers, 283 can't
verify until teams are mapped); experience Ship (50-150+; 200+ has 4); stats Ship with limits (2025: 32, 2026: 15);
hero specialist Not yet (FACEIT map stats have no hero field).

Resume file for the Phase 0 session. Read this first if picking the work up again.

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
