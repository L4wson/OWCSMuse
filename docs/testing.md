# Checks and tests

Production consistency checks, the golden answer suite, CI and the test layout.

## Consistency checks

Four bugs in this project had the same shape: a join or key mismatch that
returned a plausible answer instead of failing - a NULL season that
made a coverage join false, a NULL `started_at` that hid 30 matches from every
date-keyed view, team aggregates still keyed on `team_id` after the resolver
began returning org ids, and two org merges that joined an NA roster to an EMEA
one. None raised anything. A wrong answer that looks like a
right one is the worst failure this product has.

`python -m owcsmuse check` asserts the invariants against whatever is loaded,
and exits 1 with the specific discrepancy:

| check | invariant |
|---|---|
| `fact_view_reconciliation` | every fact view's row count equals what its sources say it must be, at that view's grain (`series` for the team-grain views) |
| `date_visibility` | every in-scope match has a usable `match_time()` and appears in the date-keyed views; no fact row has a NULL date |
| `org_key_resolution` | every team id resolves to an org key, unmapped ids are counted explicitly, and no materialized view is still carrying a superseded org key |
| `aggregate_sums` | the aggregates' sums equal the facts' sums, per stat, per season, in both the wide and long formats |
| `stat_reachability` | every stat `stat_coverage_season` advertises returns a leaderboard, and every non-numeric label returns none |
| `identity_windows` | every team-to-org window covers real series of its team id, no team id is two orgs at once, and no series carries two identities for one team |
| `series_integrity` | a match is one series whichever source holds it; the series count reconciles against FACEIT plus the resolved Liquipedia-only records; a linked pair names the same identities on both sides |
| `score_plausibility` | no series presents a score its best-of cannot hold, no map is both won and drawn, and map wins never exceed the presented series score; counts the best-of corrections (raised, lowered, unknown, implausible) and the results taken from Liquipedia |
| `map_winner_consistency` | every fact row follows the winner the map scores give; lists every `winner_team_id` that contradicts its scores (1-3e78e269 map 5) |
| `phantom_map_isolation` | a FACEIT map row beyond Liquipedia's game count for a linked series is in no fact view; counts the player rows that rode on one (none has ever been stored: see **[Phantom maps](liquipedia.md#phantom-maps-faceit-map-rows-for-maps-never-played)**) |
| `region_consistency` | no org and no team id has matches in both `na` and `emea` (OWCS is region-locked); `international` never counts. This audits what is applied, where the proposer's `region_conflict()` only guards new merges. An owner-decided exception (`cross_region_ok` on every one of the org's FACEIT windows) is listed, not failed; the Liquipedia-born `lp:team:` windows `identity load` derives from the team map are not merge decisions and are not judged against it. A FACEIT team id is a roster and must stay in one region; an `lp:team:` id is a name, and one whose every org is such an exception is listed (`decided_cross_region_names`), not failed (SpaceStation Gaming's name, NA and, from 2024 EMEA Stage 3/4, EMEA) |
| `display_names_searchable` | every entity's shown name (`entity_names.current_name`) is one of its own search names, so a name a reader sees is a name they can ask by; a shown name shared by two entities is counted, not failed (it asks which). Added 2026-10-08: it failed Astro and ZZZ, the two owner display names, until migration 037 |
| `decisions_loaded` | every reviewed decision in `scope/` (org, alias, team map, player identity, link, scope and competition-name files) is in the table its loader writes, and nothing loaded lacks one; each discrepancy is `decided_not_loaded`, `loaded_not_decided` or `loaded_differs`, with the file, the key and the command that reloads it. A decision about a team, player, championship or record the warehouse does not hold is counted as not applicable, by the loader's own skip rule. Added 2026-10-02 after production was found carrying 166 decided player identities with no anchor, 11 decided team names with none, and a stale `timeless` anchor that failed five `series_integrity` rows |
| `lp_name_resolution` | every Liquipedia team-map name resolves, in search, to an entity that holds its linked series: a name anchored to a bare team id whose era sits in an org window answers with the wrong era ("LuneX Gaming" once answered with UNC inc's 2024 record while every record key was correctly split). Also fails a team-map entry naming a team id that is not a FACEIT id or an org no decision defines (a truncated id typed into `teams decide` is accepted). Added 2026-10-02; it caught 1234, NRG Shock and Team Z on its first run |
| `placement_consistency` | every event with placings (Stage 4) has exactly one winner, and that winner won the event's last series, both by Liquipedia's own names: a bracket reset, an LCQ prize pool mixed into the event's, or a placing entered before the final would each break it. Added 2026-10-09 |
| `api_role_grants` | Supabase's Data API roles, `anon` and `authenticated`, hold no grant in the schema (tables, views, materialized views, sequences, functions, the schema itself), and the default privileges of the roles that own its objects give them none, so a recreated view cannot bring one back. Reads the ACLs themselves: PUBLIC's default `EXECUTE` and role membership are not grants. Supabase's own `supabase_admin` defaults are counted, not failed. Off Supabase the roles do not exist and it passes. Added 2026-10-26 after the owner revoked the grants Supabase gives by default |
| `answer_rates` | asks the rate questions through the real parser and pipeline (highest K/D, eliminations per map, map and series win rate) for every season and all seasons: every rate in a row is plausible (K/D at most 15 over 3+ maps, a percentage within 0-100, an average at most its total, series at most maps) and the sentence quotes the metric's own column. Added 2026-10-02 after "highest NA kd in 2026" printed Attack's 77.80 map win % as his K/D (5.00); on the old code it fails five answers |
| `liquipedia_map_isolation` | no `match_players` row joins to a `source = 'liquipedia'` round: Stage 2 map enrichment never invents player stats |

```bash
python -m owcsmuse check
python -m owcsmuse check --only aggregate_sums --json
```

`tests/test_consistency.py` covers both directions: the checks pass on the
fixture warehouse, and each one fails with the right discrepancy when its
invariant is deliberately broken (an undated match, an edited stat under a stale
aggregate, a deleted player row, an unrefreshed org merge).

## Golden answer suite

Unit tests check that code does what its author meant. The golden suite checks
that an *answer* is right: real questions asked end to end through `ask()`
against a small real warehouse, with expected values that were never produced by
the code under test. That rule exists because a test written from output encodes
the bug as correct - it is how the FACEIT nickname `KSAA0` got asserted where the
in-game name `KSAA` belonged.

- **The warehouse** is 23 real matches (`tests/golden/matches.json`, each with why
  it is there) and 4 captured Liquipedia records (`tests/golden/liquipedia_matches.json`), reconciled with the
  repository's own team map and link decisions as production does captured verbatim from `raw_payloads` by `tools/capture_golden.py`,
  their championships' scope decisions, and the repository's own
  `scope/org_decisions.json` and `scope/alias_decisions.json`, built by
  `tests/golden_support.py`. It holds both NA and EMEA, both teams named Geekay
  Esports, both SpaceStation teams, a bracket bye and a series with no map stats,
  so each past bug has something to bite on. G32-G34 cover Liquipedia-linked results: a 2024 NA series linked
  only through the region fix (G32), the NA grand final presenting Liquipedia's 4-0 over FACEIT's phantom 5-0 (G33),
  and a Dreamhack Dallas series with Liquipedia's maps, a drawn map and its schedule (G34); an evidence `by_match`
  expectation pins one series' row (score, best-of, sources, played_at). G38-G40 cover the leaderboard map
  floor: a per-map average and an ascending total rank only players with 4+ maps and say so (G38, G40), a
  descending total takes no floor (G39). G36 asks "with at least 1 map" so it still isolates the primary-role
  rule, which the floor would otherwise mask. G41-G44 cover team qualifiers: an abbreviation before "player"
  (G41, DF), a full name before a role (G42), "Team" kept in a name (G43), and no raw id in anything a reader
  sees (G44, `no_raw_ids`, which scans the rendered CLI answer too). G45-G47 cover overriding and region-qualified
  aliases, G48-G50 Liquipedia attribution (`attribution_pages`), G51 display-name search, G52-G54 relative periods
  (`notes_contain`). 11 of Toronto Defiant's 2024 NA Stage 3/4 series are Liquipedia-only records
  (`tests/golden/liquipedia_events.json`): G33 counts them in the team's record, and G22 and G82 count the four
  against NTMR through Liquipedia's line-ups (sug2rfree for Toronto, ZSS and cjay for NTMR). Toronto's series against
  Avidity and Shikigami are left out: both are FACEIT teams with no series here, so neither would resolve.
- **The expected values** come from `tests/golden/independent.py`, which reads the
  raw payload JSON and imports nothing from `owcsmuse`, and are written by
  `tests/golden/derive_expected.py` into `tests/golden/cases.json` together with
  how each was derived. Nothing in either calls `ask()`.
- **Each case is labelled** `exact` (asserts numbers) or `invariant` (asserts a
  property: NA only, tank-role players only, a clarify candidate answers verbatim,
  a refusal's alternative works), and names the regression it guards.
- **Every expectation is evaluated.** Each harness check names the expectation it
  reads, and `tests/test_golden_harness.py` walks every case's `expect` (without
  the harness's vocabulary) against a stub answer that opens every gate: an
  expectation no check reads, including a key the harness does not know, fails
  the suite. It found G24's 2026 leader had never been compared (only the offered
  season's was); a rebound `exp` once skipped every check after `by_match`.
- **Only `confirmed` cases are asserted.** A case is proposed by the derivation and
  becomes an assertion when a person reviews the value and flips `status`.
  `python tools/golden_report.py` compares every case, proposed or confirmed, to the
  live answer without asserting anything: a disagreement is either a bug in the code
  or an error in the derivation, and the raw payload decides which.
- **A failure means an answer changed**, and prints expected against actual, the
  sentence that was given and how the value was derived. Fix the code if it is a bug;
  if it is a correct improvement, change the value in `cases.json` and say why in the
  commit.
- **Definitions the expected values rest on**, confirmed by the project owner:
  "kills" means FACEIT's `Eliminations`; a team's `map_wins` / `map_losses` come from
  the series score, so a series with no map stats still counts in them; the `maps`
  column counts the maps a series records as played: FACEIT rounds where there are
  stats, otherwise Liquipedia's game-by-game results (Stage 2's rule for a linked
  result_only series, and the same for a Liquipedia-only one), a slot Liquipedia marks
  not played never counted; `kd_ratio` is total Eliminations over
  total Deaths; a map is won when the round's `Winner` is the team's id; a bracket
  bye is not a series.
- **`known_bug`** marks a case whose expectation is right and whose answer is wrong
  today. It shows as `xfail` with the reason, and fails the day it is fixed so the
  marker gets removed.

```bash
OWCS_TEST_DATABASE_URL=... pytest -m golden tests/test_golden_answers.py
OWCS_TEST_DATABASE_URL=... python tools/golden_report.py --failures
```

It runs as its own CI job, `golden answers`, on a scratch schema (`owcs_golden`).

## CI

`.github/workflows/ci.yml` runs on every push and pull request. The badge is on the front page
([../README.md](../README.md)); while the repository is private it renders only for accounts with access:

| job | what it runs |
|---|---|
| `lint` | `ruff check .` - correctness rules only (`E`, `F`, `W`, `B`); line length and statement layout are deliberately not enforced |
| `API image` | `docker build` of the deployable image, then checks it runs as the non-root user `owcs` and carries neither pytest nor ruff |
| `offline tests` | `pytest` with no database configured, proving the parsers, classifier, limiter and query layer need neither network nor DB |
| `database tests` | `pytest -m "not golden"` against `postgres:16` **and** `postgres:17` service containers (a matrix): 17 is what Supabase and docker-compose run; 16 stays covered |
| `golden answers` | builds the golden warehouse and asserts the confirmed golden cases through `ask()` (see **Golden answer suite**), on both majors |
| `frontend` | `npm ci && npm test && npm run build` in `web/` - component tests against a mocked API, then a production build |
| `consistency checks` | builds a warehouse from the captured fixtures (`tools/build_fixture_db.py`), loads every `scope/` decision file through its own loader as production does, and runs `python -m owcsmuse check` against it, on both majors. It also ingests the golden capture of 1-36219ab4, the series that opens Virtus pro's window on `bb5dd404`, so `identity_windows` judges a decided window against a series it covers |

Why both majors: migrations 026 to 031 passed every gate on 16 and failed on
production (Supabase, PostgreSQL 17.6) at the first materialized view. PG 17
plans `CREATE`/`REFRESH MATERIALIZED VIEW` (and `CREATE INDEX`, `VACUUM`,
`ANALYZE`, `CLUSTER`, `REINDEX`) under `search_path = pg_catalog, pg_temp`,
and a `LANGUAGE sql` function body is re-parsed by name at plan time, so a body
that says `FROM teams` finds nothing there (`relation "teams" does not exist
... SQL function "team_identity_at" during inlining`). Views are unaffected
(they store OIDs). The remedy per function is in migration
`033_pin_search_path.sql`: a once-per-row function names every relation and
function `{{schema}}.`-qualified (the token `migrate` replaces with
`OWCS_DB_SCHEMA`), which keeps it inlinable; a once-per-question set-returning
function gets `SET search_path FROM CURRENT`, which is simpler but blocks
inlining and re-plans on every call (tried on the per-row functions, it made
the golden refresh 44x slower: 0.44 s to 19 s; qualified, 0.46 s).
`tests/test_search_path.py` refreshes every materialized view under the
restricted path, which reproduces the PG 17 condition on any major, and keeps
every table-reading SQL function in one of the two states.

## Tests

```bash
pytest                                        # parsers, rate limiter, client, classifier, resolver: no network, no DB
OWCS_TEST_DATABASE_URL="postgresql://..." pytest            # adds the Postgres integration tests
OWCS_TEST_DATABASE_URL="postgresql://..." OWCS_TEST_SCHEMA=owcs_test pytest
ruff check .                                  # the lint gate CI runs
```

`tests/test_api.py` needs the `api` extra; without it the module skips.

The database tests never touch `public`: they drop and recreate the scratch
schema named by `OWCS_TEST_SCHEMA` (default `owcs_test`) at the start of every
test, run the migrations into it, and drive the collector with a fake client
that serves the captured fixtures, checking the first-map override, idempotent
re-runs, resume, failure retry, offline reprocess and nickname history. Point
`OWCS_TEST_DATABASE_URL` at the local Docker Postgres or at Supabase; the role
needs `CREATE SCHEMA`.

`tests/fixtures/` holds real payloads captured on 2026-09-17 from OWCS 2024
EMEA Stage 1 Main Event and OWCS 2026 OQ EMEA:

- `match_*_bo5_4rounds`: 5 picks, 4 maps played (3-1).
- `match_*_bo7_5rounds`: 7 picks, 5 maps played, 6 `detailed_results`.
- `list_item_bo5_first_map_result` + `match_*_bo5_flip`: Twisted Minds beat Ex
  Oblivione 3-1 after losing map 1 2-0. The list item's `results` was replaced
  with that first-map result (see its `_fixture_note`), because at capture time
  every live listing agreed with its detail payload across all 5,458 finished
  OWCS matches on FACEIT. The override path is exercised exactly as it would be
  when the quirk appears.
