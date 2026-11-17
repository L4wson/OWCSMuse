# Grid Phase 0: working notes

Resume file for the Phase 0 session. Read this first if picking the work up again.

## State: Phase 0 complete, waiting for the owner's decisions (2026-11-16)

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
