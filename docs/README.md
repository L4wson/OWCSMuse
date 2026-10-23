# Documentation

The front page is [../README.md](../README.md). Start with [conventions.md](conventions.md): every other
document assumes it.

| document | what it covers |
|---|---|
| [conventions.md](conventions.md) | what data means here, learned from wrong answers; FACEIT's quirks |
| [identity.md](identity.md) | team ids to orgs, aliases, competition names |
| [scope.md](scope.md) | what is in scope and why; known limitations |
| [ingest.md](ingest.md) | the FACEIT backfill |
| [schema-and-migrations.md](schema-and-migrations.md) | migrations, Supabase notes, core tables |
| [answers.md](answers.md) | aggregates, question parsing, versus records |
| [api-and-frontend.md](api-and-frontend.md) | the answer contract and the web app |
| [liquipedia.md](liquipedia.md) | Liquipedia as a second source, stages 0-4, partner teams |
| [testing.md](testing.md) | consistency checks, the golden suite, CI, tests |
| [deployment.md](deployment.md) | the deployment runbook |
| [open-items.md](open-items.md) | what is left open |

## Layout

```
migrations/001_initial.sql      schema
migrations/002_scope.sql        scope_region / tier / season / classification columns
migrations/003_aggregates.sql   fact views, materialized aggregates, coverage functions, entity_names
migrations/009_orgs.sql         orgs, team_orgs, team_identity, map-grain versus facts
migrations/026_dated_team_orgs.sql  team-to-org windows, team_identity_at(), facts and names keyed at series time
migrations/027_entity_anchors.sql  entity_anchors, Liquipedia line-ups and name history, Liquipedia names in entity_names
migrations/028_series.sql       the source-agnostic series; team-grain facts read it
migrations/029_anchor_windows.sql  Liquipedia names resolve at the series' time
migrations/030_draws.sql        a tied map is nobody's win; plausible series scores with provenance
migrations/031_capabilities.sql region_sources (declared) and source_capabilities (derived): what each slice can answer
migrations/032_best_of_from_wins.sql  best-of derived from the winning score; corrections counted and listed
migrations/033_pin_search_path.sql  every table-reading SQL function survives PostgreSQL 17's restricted search_path
migrations/034_map_winner_precedence.sql  map winner from the scores; Liquipedia the source of record where linked; phantom maps; best-of from played wins
migrations/035_game_names_display.sql  in-game name history (player_game_names), players.display_name, deterministic leaderboard order
migrations/036_primary_role.sql  a role leaderboard ranks the players whose primary role it is (player_primary_roles)
tools/backfill_game_names.py    every earlier in-game name out of the stored match payloads -> player_game_names
tests/test_search_path.py       refreshes every matview under search_path = pg_catalog, pg_temp; every table-reading SQL function qualified or pinned
tools/window_review.py          the three name-change signals over every multi-name team id -> scope/org_window_review.md
scope/org_window_decisions.json the owner's verdict on each of the 18 multi-name team ids (audit record; windows apply via org_decisions.json)
owcsmuse/liquipedia/identity.py  cross-source player identity: match-level evidence, decisions, anchors
owcsmuse/liquipedia/phantoms.py  FACEIT map rows for maps never played: extent report (-> scope/phantom_maps.md)
owcsmuse/scope.py               classifier, decisions file, review report
owcsmuse/orgs.py                org identity: proposals, evidence, decisions and rejections
owcsmuse/aliases.py             community shorthand ("SSG" -> SpaceStation Gaming): decisions and lookup
owcsmuse/crawl.py               history crawl: frontier, generations, completeness instrumentation
owcsmuse/consistency.py         warehouse invariants behind `python -m owcsmuse check`
owcsmuse/limitations.py         known gaps, surfaced by `ask` and documented above
owcsmuse/aggregates.py          refresh + coverage-aware leaderboard helpers
owcsmuse/resolve.py             entity resolver
owcsmuse/nlq/                   question -> StructuredQuery -> validate -> compile -> answer
owcsmuse/nlq/sentence.py        one templated sentence per intent, with entity spans
owcsmuse/nlq/evidence.py        the rows behind an answer, paged
owcsmuse/api.py                 FastAPI service: /ask, /query/{slug}, /suggestions
owcsmuse/web.py                 shareable slugs and data-aware suggestions
web/src/                        Vite + React app: landing, result, evidence, the three refusal states
web/tests/                      component tests with payloads captured from the service
migrations/014_saved_queries.sql  question behind a slug (never the answer)
scope/decisions.json            reviewed scope decisions (commit this)
scope/org_decisions.json        reviewed org merges and rejections (commit this)
scope/alias_decisions.json      reviewed community shorthand (commit this)
scope/classification_report.md  generated review table
scope/org_report.md             generated org proposal table
tools/build_fixture_db.py       CI: a warehouse from the captured fixtures
tools/capture_golden.py         copy the golden matches' payloads out of raw_payloads
tools/golden_report.py          compare every golden case to the live answer (asserts nothing)
tests/golden/                   golden matches, independent.py, derive_expected.py, cases.json, harness.py
.github/workflows/ci.yml        lint, offline tests, database tests, consistency checks
owcsmuse/config.py              pydantic-settings
owcsmuse/log.py                 JSON / text structured logging (not logging.py: that would shadow the stdlib)
owcsmuse/db.py                  connect, migrate, RawPayloadStore
owcsmuse/faceit/ratelimit.py    header parsing, adaptive limiter, jittered backoff
owcsmuse/faceit/client.py       FaceitClient: retries, raw sink, capped pagination
owcsmuse/parsers/               pure payload -> record functions (no I/O)
owcsmuse/discovery.py           deliverable 1: manifest
owcsmuse/collector.py           deliverable 3: LIST / DETAIL / reprocess / status
owcsmuse/cli.py                 python -m owcsmuse ...
tests/                          pytest suites and captured fixtures
```
