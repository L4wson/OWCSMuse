# OWCS Muse: ingestion layer

[![CI](https://github.com/L4wson/OWCSMuse/actions/workflows/ci.yml/badge.svg)](https://github.com/L4wson/OWCSMuse/actions/workflows/ci.yml)

Pulls Overwatch Champions Series (OWCS) match data from the FACEIT Data API v4
into a local Postgres warehouse. No web layer, no ORM: Python 3.11+, `httpx`,
`psycopg`, `pydantic-settings`, plain SQL migrations, `pytest`.

Nothing queries FACEIT at request time. A backfill runs in two resumable
phases and every FACEIT response is stored verbatim so parsing can be redone
offline.

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate    # or source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                                  # put FACEIT_API_KEY in .env
docker compose up -d                                  # local Postgres on :5432 (optional)
python -m owcsmuse migrate
```

Configuration is read from environment variables or `.env` (see `.env.example`).
Two settings are required and have no default, so an unset value fails at
startup instead of connecting somewhere unintended:

- `FACEIT_API_KEY`
- `DATABASE_URL` (also accepted as `OWCS_DATABASE_URL`), a Postgres URL such
  as a Supabase session-pooler string.

Everything else is optional and prefixed `OWCS_` (`OWCS_LOG_FORMAT=json|text`,
`OWCS_PAGE_SIZE`, `OWCS_DB_SCHEMA`, ...). See `owcsmuse/config.py` for the full
list and defaults. `docker-compose.yml` is only a convenience for a local
Postgres; the code has no localhost fallback.

## Running a backfill

1. **Discover** OWCS competitions and write a manifest for review:

   ```bash
   python -m owcsmuse discover --out manifest.json
   ```

   The script searches FACEIT organizers and championships for the OWCS name
   pattern, enumerates every organizer it finds, and writes all of their
   championships with `include: true` pre-set where the name matches
   `\bOWCS\b|Overwatch Champions Series`. Use `--organizer-id`, `--name` and
   `--pattern` to widen the net. Add `--no-db` to run it without Postgres.

   As of 2026-09-17 two organizers host OWCS on FACEIT:
   `abd401de-e6ec-4ef1-8d4b-3d820f8f62ce` ("OWCS | Overwatch Champions Series",
   OWCS 2024 stages) and `f0e8a591-08fd-4619-9d59-d97f0571842e` (OWCS 2025/2026
   open qualifiers alongside unrelated FACEIT League events, which the pattern
   excludes). FACEIT reports most OWCS events as region `GLOBAL`; the manifest
   adds `derived_region` (NA / EMEA / ...) parsed from the name.

   Discovery also runs the scope classifier over every championship and
   writes `scope/classification_report.md` (see **Scope** below).

2. **Review** `scope/classification_report.md`. Every row shows the proposed
   region, tier, season and include flag with the evidence behind it. Record
   corrections, which are stored in `scope/decisions.json` and override the
   classifier on every future run:

   ```bash
   python -m owcsmuse decide <championship_id> --include --region na --tier main --note "group stage"
   python -m owcsmuse decide <championship_id> --exclude --note "duplicate bracket"
   python -m owcsmuse classify          # re-render manifest + report from decisions, no network
   ```

   Nothing is collected until a championship is included in the database, and
   `load-manifest` only honours `include` for championships with a manual
   decision. Once the proposals look right, accept them in bulk with
   `--accept-proposals`, or decide each one explicitly.

3. **Load** the reviewed manifest:

   ```bash
   python -m owcsmuse load-manifest manifest.json                    # manual decisions only
   python -m owcsmuse load-manifest manifest.json --accept-proposals # also the classifier's proposals
   python -m owcsmuse check-listings                                 # read-only: sizes + offset-cap check
   ```

4. **Collect**:

   ```bash
   python -m owcsmuse backfill                 # LIST then DETAIL for every included championship
   python -m owcsmuse list --championship ID   # LIST only, one championship
   python -m owcsmuse detail --limit 200       # DETAIL only, at most 200 matches this run
   python -m owcsmuse status                   # progress per state and championship
   ```

   Interrupt at any time. `detail` picks up matches still in `stub` /
   `detail_fetched`; `--include-failed` retries `failed` ones; `--refresh`
   re-fetches everything. Re-running never duplicates rows.

5. **Reprocess** after a parser change, without touching FACEIT:

   ```bash
   python -m owcsmuse reprocess
   ```

   This re-applies the newest stored `/matches/{id}` and `/matches/{id}/stats`
   payloads from `raw_payloads`.

Logs go to stderr as one JSON object per line (`--log-format text` for a
terminal). Every request logs `faceit_request` with `endpoint`, `status`,
`latency_ms`, `ratelimit_remaining`, `ratelimit_limit`, `attempt` and the
`raw_id` of the stored payload.

## The two phases

**LIST** pages `/championships/{id}/matches?type=all` (100 per page) and
upserts a stub row per match (`ingest_state='stub'`), including whatever
result the listing reports. That result is provisional: FACEIT's listing can
carry the first map's result rather than the series result. The stub keeps it
in `list_winner_faction` / `list_faction1_score` / `list_faction2_score`.

**DETAIL** takes pending matches in `started_at` order and, per match:

1. fetches `/matches/{id}`, parses the series result and overwrites
   `winner_faction`, `winner_team_id`, `faction1_score`, `faction2_score`
   unconditionally, setting `result_source='detail'`;
2. logs `series_result_flipped` (WARNING) whenever the listing named a
   different winner, and sets `matches.result_flipped = true`;
3. for `FINISHED` matches fetches `/matches/{id}/stats` and replaces the
   match's `match_rounds` and `match_players` rows in the same transaction;
4. moves the match to `complete` (stats applied), `skipped` (not played, e.g.
   `CANCELLED`) or `failed` (`ingest_error` says why, `--include-failed`
   retries).

A later LIST run never clobbers a DETAIL-sourced result. If the listing shows a
changed `status` (say ONGOING became FINISHED) the match is re-queued as `stub`.

## Known FACEIT quirks handled

| Quirk | Handling |
| --- | --- |
| Listing `results` can describe the first map, not the series | DETAIL re-derives from `/matches/{id}` and overwrites; flips logged and flagged in `result_flipped`; LIST values kept in `list_*` columns for audit |
| `stats.rounds[]` has one entry per map played, fewer than picks | `match_rounds` = rounds only; picks stored separately in `match_map_picks`; `matches.maps_played` vs `matches.maps_picked` |
| `round_stats["OW2 Mode"]` is the game mode | Read directly into `match_rounds.game_mode`; never inferred from the map name |
| `round_stats["Map"]` is a GUID (`0x08...`) | Resolved to a name through the detail payload's `voting.map.entities`; both stored |
| Players sit under `teams[]` in stats | `match_players.team_id` is the team id carried with the player row (the enclosing team's id) and equals `faction_id` from `/matches/{id}` |
| Nicknames change | `players.player_id` is the FACEIT GUID; `players.nickname` is the latest seen; `player_nicknames` keeps every nickname with first/last seen |
| Championship timestamps are epoch ms, match timestamps epoch s | `ts_from_epoch` handles both |
| Listing offset is capped at 500 (600 items max, offset must be a multiple of limit) | Client stops at the cap and flags `championships.list_truncated`; a WARNING `championship_listing_truncated` is logged. Six 2024 open-qualifier Swiss events exceed 600 matches |
| Rate limit headers are `ratelimit-limit: 20, 20;w=1` (IETF style) | Parsed alongside `X-RateLimit-*`; limiter paces to the advertised window and pauses at low `remaining`; 429/5xx back off exponentially with full jitter and honour `Retry-After` |

Not observed but worth knowing: FACEIT's `detailed_results` can have more
entries than `stats.rounds[]` (a bo7 fixture has 6 vs 5). Map counts always
come from `rounds[]`.

## Schema

Migrations live in `migrations/` and are applied in filename order by
`python -m owcsmuse migrate`, which records them in `schema_migrations`.
Every migration runs in its own transaction with `search_path` pinned to
`OWCS_DB_SCHEMA` (default `public`), and every connection the CLI opens pins
the same `search_path`, so all objects are created in and read from that one
schema explicitly. Nothing is created outside it.

### Supabase notes

- The pooler string goes in `DATABASE_URL`. Use the **session** pooler (port
  5432): the collector holds two long-lived connections for the whole run (one
  transactional connection for processing, one autocommit connection for
  `raw_payloads`), never one per match. Transaction-mode pooling is not
  needed and would break `SET search_path`.
- Objects land in `public`, next to nothing of ours; Supabase's own
  `auth`, `storage`, `realtime` and `extensions` schemas are untouched.
- **Row Level Security is not enabled on any of these tables.** Plain SQL
  migrations bypass the Supabase dashboard's RLS prompts. On Supabase every
  table in `public` is also exposed through the auto-generated Data API
  (PostgREST), so with RLS off the `anon` and `authenticated` roles can read
  and write everything the way the API's grants allow. Decide on RLS
  policies, or revoke the Data API grants on these tables, before any client
  connects to the project directly. The ingestion CLI uses the `postgres`
  role over the pooler and is unaffected either way.

| Table | Grain | Notes |
| --- | --- | --- |
| `raw_payloads` | one row per HTTP response | `endpoint`, `params`, `http_status`, `payload` (jsonb), `body_text`, `fetched_at`, `match_id`, `championship_id`. Every request, including 429s and 5xx |
| `organizers` | FACEIT organizer | |
| `championships` | FACEIT championship | `include` (from manifest), `region` as reported, `derived_region` from the name, `list_truncated`, `list_completed_at` |
| `teams` / `team_names` | FACEIT team (faction) id | latest name plus name history |
| `players` / `player_nicknames` | FACEIT player GUID | latest nickname, Battle.net id (`game_player_id`), nickname history |
| `matches` | one series | timestamps, `best_of`, both factions, series result and its source, LIST audit columns, `result_flipped`, `maps_picked` / `maps_played`, ingest state (`ingest_state`, `ingest_error`, `ingest_attempts`, `detail_raw_id`, `stats_raw_id`, fetched-at stamps) |
| `match_rosters` | match x player | starters and substitutes as declared on `/matches/{id}`, with nickname at match time |
| `match_map_picks` | match x pick order | veto/pick sequence; not the maps played |
| `match_rounds` | match x map played | `map_guid`, `map_name`, `game_mode`, `score_summary`, winner and both team ids/scores, both teams' `team_stats` and the raw `round_stats` as jsonb |
| `match_players` | match x map played x player | typed columns (eliminations, final blows, deaths, assists, damage, healing, mitigation, objective time, time played, role, result) plus the complete `player_stats` as jsonb |
| `match_player_totals` (view) | match x player | sums over `match_players` for a per-match scoreboard |

`match_players` is per map because that is the grain FACEIT reports; per-match
numbers are sums (the view) and per-map ratios stay in the jsonb. Player stat
keys differ between seasons (2024 payloads have 9 keys, 2026 payloads about 50),
so the typed columns are the stable subset and `stats` keeps everything.

Ingest state machine on `matches.ingest_state`:

```
stub ──detail ok──▶ detail_fetched ──stats ok──▶ complete
  │                        │
  │                        ├── not FINISHED ──▶ skipped
  └── 404 / error ─────────┴── stats error ──▶ failed   (retry with --include-failed)
```

(`detail_fetched` is transient inside one transaction; you will normally see
only `stub`, `complete`, `skipped`, `failed`.)

## Scope

Target set: OWCS North America and OWCS EMEA main competition (regional
stages, their group stages and playoffs) plus international events where NA
and EMEA teams compete (Midseason Championship, World Finals, Champions Clash,
the 2024 Dreamhack Dallas Major). Excluded: open qualifiers, relegation,
Asia / Korea / Japan / Pacific / China / South America / Oceania, cancelled or
test events. Korea has no usable FACEIT data, so nothing Asia-region is
included even where a championship exists.

Classification is explicit and reviewable, not a regex flag:

- `championships.scope_region` (`na`, `emea`, `international`, `other`),
  `championships.tier` (`main`, `qualifier`, `relegation`, `unknown`) and
  `championships.season`, with `classification_source` (`auto` or `manual`),
  `classification_evidence` (the rules that fired) and `decision_note`.
- `owcsmuse/scope.py` proposes values from a small rule table; every rule
  names itself in the evidence. A known-event table covers OWCS events whose
  FACEIT name lacks "OWCS" (Dreamhack Dallas).
- `scope/decisions.json` holds reviewed corrections keyed by championship id.
  Re-running `discover` or `classify` applies them on top of the classifier,
  so a decision is never silently reclassified. `scope/classification_report.md`
  is the review table.
- The aggregates below read only championships with `include = true`.

What FACEIT holds, as of 2026-09-17:

- **Reachable through the championship endpoints:** the 2024 NA and EMEA
  Stage 1 and Stage 2 group stages and main events, and Dreamhack Dallas 2024
  (21 championships, 166 matches). Excluding the qualifiers also removes every
  championship that hit FACEIT's 600-item listing cap; `check-listings`
  confirms none of the 21 does.
- **Present but not reachable through those endpoints:** the 2025 and 2026 NA
  and EMEA main series runs inside FACEIT League as the "OWCS Central"
  division: `S4/S5/S6 {NA|EMEA} OWCS Central - Regular Season / Playoffs`
  (2025) and `S8/S9/S10 ...` (2026), plus `OWCS Midseason Championship: Last
  Chance Qualifier at EWC` and the S8 relegation matches, all under organizer
  `f0e8a591-08fd-4619-9d59-d97f0571842e` ("FACEIT League - Overwatch"). These
  competition ids return 404 from `/championships/{id}`, `/hubs/{id}` and
  `/leagues/{id}`, are absent from `/organizers/{id}/championships` and from
  every search endpoint, and the organizer exposes no hubs or tournaments.
  Their matches are fully served by `/matches/{id}` and `/matches/{id}/stats`
  (2026 payloads, ~47 stat keys) and are discoverable only through
  `/players/{id}/history`, which reports the competition id and name per
  match. They are ingested through the history crawl below.
- 2024 Stages 3 and 4 exist on FACEIT only as open qualifiers.

### History crawl

`owcsmuse/crawl.py` is a LIST phase for the competitions the championship
endpoints hide. It seeds from the rosters already ingested, reads
`/players/{id}/history`, records every match under a competition that
classifies as in scope, and adds the opposing rosters to the next generation's
frontier. It is resumable and instrumented for completeness: `crawl status`
reports the convergence curve (players crawled, new matches per generation),
the frontier, per-competition coverage and gap flags.

```bash
python -m owcsmuse crawl seed --from-rosters
python -m owcsmuse crawl run --dry-run      # request projection, before spending any
python -m owcsmuse crawl run
python -m owcsmuse crawl status
python -m owcsmuse crawl competitions       # discovered competitions, for the same review gate
```

It converged in two generations: 315 players / 2,273 requests / 232 new
matches, then 99 players / 724 requests / 0 new matches. Discovered
competitions go through `classify` and `scope/decisions.json` exactly like
anything found by `discover`; the crawl marks nothing included by itself.

## Known limitations

Coverage percentages say how much of a stat exists. They do not say why it is
missing, and here the gaps are not random. `owcsmuse/limitations.py` holds these
as data; `python -m owcsmuse limitations` prints them, and `ask` attaches the
ones a question lands in to its answer.

### Offline and LAN days have series results but no map stats

`offline_map_stats` - FACEIT records a result for an offline series without
per-map player stats, so those series land in `result_only`: the winner and
series score are known, the maps are not. 100 of 509 finished series in scope
are `result_only`, and they are not spread evenly - 52 of 118 series in playoff
and LAN competitions have no map stats against 48 of 391 elsewhere, and all 14
Dreamhack Dallas matches are `result_only`. **Map-grain answers therefore
under-represent exactly the matches that mattered most.** Series-grain answers
(`record`, `series record against`) still count them, and a versus answer names
the series it had to exclude.

### 2024 carries 9 stat keys; 2025 and 2026 carry 47

`stats_2024` - the 2024 payloads expose only Eliminations, Deaths, Assists,
Damage Dealt, Healing Done, Damage Mitigated, K/D Ratio, Result and Role. Per-10
minute rates, Final Blows, Solo Kills, Objective Time and Time Played do not
exist for that season at all, so an all-seasons leaderboard for any of them is a
2025+ leaderboard wearing an all-time label. `stat_coverage_season` is the
machine-readable form of this.

### Map duration is derived, and only from 2025 onward

`map_duration` - no payload carries a map duration field. `map_durations`
derives it from the per-player `Time Played` stat, which 2024 does not have.
1,004 of 1,482 ingested maps carry a duration: all 748 maps of 2025 and all 256
of 2026, and none of 2024's 478.

### Scope is OWCS NA + EMEA main competition

`scope_na_emea` - Korea, China, Japan and the Pacific regions are not ingested,
nor are open qualifiers, community cups or relegation brackets held outside the
main series. Korea in particular has no usable FACEIT data at all. A leaderboard
here ranks NA and EMEA main-competition play, not OWCS worldwide.

### The 2025 and 2026 main series is reconstructed from player history

`main_series_2025_2026` - FACEIT publishes those OWCS Central divisions on no
championship, hub or league endpoint and in no search result. They were
assembled by the roster-seeded crawl above, which ran to convergence, so a
series played entirely by players the crawl never reached would be absent with
nothing to indicate it. 2024 comes from the championship endpoints directly and
carries no such caveat.

## Team identity (orgs)

FACEIT issues a new team id per season, so one organisation appears as several
team ids and every cross-season team query silently undercounts. `orgs` and
`team_orgs` (migration `009_orgs.sql`) give an organisation a stable id with
team ids as the mutable handles, mirroring how `players.player_id` is stable and
nicknames are history. A team id belongs to exactly one org.

```bash
python -m owcsmuse orgs propose                  # writes scope/org_report.md with the evidence
python -m owcsmuse orgs decide <team_id> --org <org-id> --org-name "Name" --note "..."
python -m owcsmuse orgs reject <id_a> <id_b> --reason "..."   # decided: different orgs
python -m owcsmuse orgs load                     # write decided mappings into orgs / team_orgs
python -m owcsmuse orgs status
python -m owcsmuse refresh                       # required: the aggregates carry org_key
```

Nothing merges without review. Proposals go through `scope/org_decisions.json`
the same way scope decisions go through `scope/decisions.json`, and a rejection
is recorded as a decision too, so a pair that was looked at and turned down
never returns as pending review. An unmapped team id stays unmapped and keys as
`team:<id>`, visibly itself in any grouping - there is no silent fallback.

**What the evidence is actually worth.** The proposer weighs three signals:
name identity after folding, roster overlap across the two date windows, and
date adjacency. Reviewing the output on real data inverted the expected
ordering:

- **Roster overlap is weak evidence, and sometimes points the wrong way.** In
  esports whole rosters move between organisations, so a squad that transferred
  looks identical to a rename. Four pairs at 80-100% overlap - Geekay Esports /
  NTMR, NTMR / Dallas Fuel, LeftRightGnight / Geekay Esports, Al qadsiah /
  Geekay Esports - are distinct organisations. Meanwhile the one real rename in
  the data, Al qadsiah to qadsiah, shared **1 of 8** players, because the roster
  turned over at the same time. Merging on overlap would have made four wrong
  merges and missed the right one.
- **Name identity is the reliable signal**, with two guards: generic tokens
  (`team`, `esports`, `gaming`, ...) carry no identity, so "Team X" and "X" are
  the same handle; and an added academy or B-team token refuses the match
  outright, so `name_contains("Team Liquid", "Liquid Academy")` is `False` and
  says why. Nothing here does fuzzy string similarity.
- **Date adjacency corroborates.** Two ids whose match windows overlap may be
  two teams that coexisted, which is reported rather than assumed.

Current state: 11 orgs covering 22 team ids, 5 pairs recorded as reviewed
rejections, 58 team ids unmapped and queryable as themselves.

## Aggregation layer

Read-only derived tables for a query engine, defined in
`migrations/003_aggregates.sql`. `fact_*` and `map_durations` are plain views;
everything else is a materialized view.

Refresh runbook, after any ingest or scope change:

```bash
python -m owcsmuse refresh                       # all materialized views, in order
python -m owcsmuse refresh --view entity_names   # one view
python -m owcsmuse stats                         # stat availability per season
python -m owcsmuse stats --stat "Final Blows"    # coverage window of one stat
python -m owcsmuse stats --stat "Eliminations" --leaderboard --season 2024 --min-maps 10
python -m owcsmuse resolve "ksaa" --type player  # entity resolution
```

| View | Grain | Sample size columns | Notes |
| --- | --- | --- | --- |
| `fact_player_maps` (view) | player x map played | | base fact, scoped to included championships and complete matches; carries season, region, map, mode, opponent, all typed stats and the `stats` jsonb |
| `fact_team_maps`, `fact_team_matches` (views) | team x map, team x series | | one row per side |
| `agg_player_stats` | player x team x championship x map x mode | `maps`, `matches` | `sum_<stat>` and `maps_with_<stat>` per typed stat; average = sum / maps_with, so slices re-aggregate correctly by summing |
| `agg_player_season` | player x season | `maps`, `matches` | sums, per-map averages, coverage counts, K/D |
| `agg_player_stat_long` | player x championship x season x stat key | `maps_with_stat` | every numeric FACEIT key, including the 2026-only ones and the FACEIT-provided per-10-minute rates |
| `stat_coverage`, `stat_coverage_season` | championship or season x stat key | `rows_with_stat`, `rows_total`, `coverage_pct` | which stats exist where. 2024 payloads carry 9 keys, 2026 about 50 |
| `agg_team_matches` | team x championship | `matches`, `maps` | series wins/losses, map wins/losses, win % |
| `agg_team_maps` | team x championship x map x mode | `maps`, `matches` | map wins/losses/draws, win % |
| `agg_head_to_head` | team pair x championship | `matches`, `maps` | `team_a < team_b`, series and map wins each way |
| `agg_map_modes` | map x mode x championship | `maps`, `matches` | side wins, draws, average duration where available |
| `entity_names` | every name an entity has carried | | current and historical player nicknames, in-game names, current and historical team names, accent-folded |

Coverage-aware functions, always use them for leaderboards:

- `stat_coverage_summary(stat, season, championship)` returns maps total, maps
  with the stat, coverage %, the seasons with and without the stat, and the
  first/last time it was seen.
- `stat_leaderboard(stat, season, championship, min_maps, limit, order)`
  returns rows with `maps_with_stat`, `maps_played`, `coverage_pct` and
  `seasons` per player, omitting players with no data for the stat. The Python
  wrapper `owcsmuse.aggregates.stat_leaderboard` returns rows and the coverage
  summary together. An all-seasons leaderboard for a 2026-only stat therefore
  reports `seasons_without_stat = [2024]` and 27 % coverage instead of a silent
  partial ranking; the aggregate tests check this.

**Map duration.** Neither `round_stats` nor `team_stats` carries a map duration
on 2024 payloads (keys: Map, OW2 Mode, Score Summary, Winner), and there are no
per-map timestamps anywhere; only the series has `started_at` / `finished_at`.
2026 payloads carry `Time Played` per player (seconds) and
`Total Team Time Played`, from which `map_durations` derives
`duration_seconds` as the maximum player time on the map. So durations, and
per-10-minute rates, exist only for 2026-era data. FACEIT already ships the
per-10-minute rates in those payloads (`Eliminations/10m` etc.), and they are
available through `agg_player_stat_long` with their own coverage. No
per-10-minute rate is computed for 2024 data, and `agg_map_modes` reports
`maps_with_duration` alongside `avg_duration_seconds`.

**Entity resolution.** `owcsmuse.resolve.resolve(conn, "typed name", "player"|"team"|None)`
folds case and accents on both sides and ranks every known name (exact,
prefix, substring, fuzzy) to return candidates with the entity id, its current
name, the name that matched and whether that was a current or historical name.
Ranking runs in Python over `entity_names`, so no Postgres extension is needed.

On Supabase the materialized views live in `public` like the tables and are
exposed by the Data API under the same grants; the RLS note above applies.

## Natural-language questions (v0, CLI only)

```bash
python -m owcsmuse ask "who had the most eliminations in 2024"
python -m owcsmuse ask "KSAA average healing on control maps" --debug   # shows the compiled SQL + params
python -m owcsmuse ask "Twisted Minds vs ENCE" --json
python -m owcsmuse ask "what stats are available"
```

This is not text-to-SQL. `owcsmuse/nlq/` runs a fixed pipeline and no model
ever emits SQL:

1. **parse** the question into a validated pydantic `StructuredQuery`
   (`intent`, `entity`, `metric`, `filters` for player / team / opponent /
   championship / season / map / mode / region, `aggregation`, `sort`,
   `limit`, `min_maps`). The default parser is deterministic and rule-based
   (`nlq/parser.py`). `--parser llm` uses Claude structured outputs
   (`nlq/llm_parser.py`, needs the optional `anthropic` package and
   credentials) to fill the same object; `--parser auto` tries Claude and
   falls back to the rules. Either way the object is validated and compiled
   identically.
2. **resolve** every name through `owcsmuse.resolve` before anything else. A
   strong, clearly leading match is accepted; a tie or weak match returns
   `status: clarify` with the candidates instead of a guess; no match is
   `unknown_entity`. An untyped name ("Twisted Minds record") is retargeted
   to whatever it resolved to, player or team.
3. **validate** against the live schema (`nlq/validate.py`): stat keys must
   exist in `stat_coverage_season`, seasons / maps / modes / regions must have
   data, championship text must match an included championship, and
   unsupported combinations (a non-typed stat sliced by map) are refused with
   the reason.
4. **compile** to parameterized SQL over the `agg_*` views
   (`nlq/compile.py`). Leaderboards reuse `stat_leaderboard()`; every value is
   a bound parameter and column names come from a whitelist.
5. **execute** and attach `stat_coverage_summary()` for the metric and slice.
   A stat that exists only in some seasons is answered with an explicit
   coverage note (`seasons without it: 2024`) and per-row coverage, never a
   silently partial leaderboard.

Every failure is a first-class answer with a reason code: `unsupported_metric`,
`unsupported_question`, `out_of_scope`, `ambiguous_entity`, `unknown_entity`,
`no_data`, `invalid_query`, each with suggestions. Exit code is 0 for an
answer and 2 otherwise.

Tests: `tests/test_nlq_parser.py` holds 60+ question / expected-object pairs
(supported, ambiguous and unanswerable) asserted on the parsed object, and
`tests/test_nlq_compile.py` covers validation and compilation against a
hand-built schema, all without a database or model. `tests/test_nlq_db.py`
runs `ask()` end to end on the fixture data when a database is configured.

## Versus queries

`versus` answers "X against Y" at **map** grain for any two entities - player vs
player, player vs org, org vs org - from `fact_player_versus` and
`agg_org_versus_maps`, each row carrying maps, matches and the seasons covered.
`season_compare` puts one entity's season against its own other season.

```bash
python -m owcsmuse ask "Sugarfree map record against Zeruhh"
python -m owcsmuse ask "Twisted Minds vs Al Qadsiah"
python -m owcsmuse ask "2024 Twisted Minds vs 2026 Twisted Minds"
python -m owcsmuse ask "Twisted Minds series record against ENCE"   # series grain instead
```

`result_only` series contribute no map rows, so they cannot deflate a record
unnoticed: the answer counts them separately and says how many series and how
many maps by series score are excluded. An empty result distinguishes "never
met" from "met, but FACEIT recorded no maps".

## Consistency checks

Three bugs in this project had the same shape: a join or key mismatch that
returned a plausible, smaller answer instead of failing - a NULL season that
made a coverage join false, a NULL `started_at` that hid 30 matches from every
date-keyed view, and team aggregates still keyed on `team_id` after the resolver
began returning org ids. None raised anything. A wrong answer that looks like a
right one is the worst failure this product has.

`python -m owcsmuse check` asserts the invariants against whatever is loaded,
and exits 1 with the specific discrepancy:

| check | invariant |
|---|---|
| `fact_view_reconciliation` | every fact view's row count equals what its source tables say it must be, at that view's grain |
| `date_visibility` | every in-scope match has a usable `match_time()` and appears in the date-keyed views; no fact row has a NULL date |
| `org_key_resolution` | every team id resolves to an org key, unmapped ids are counted explicitly, and no materialized view is still carrying a superseded org key |
| `aggregate_sums` | the aggregates' sums equal the facts' sums, per stat, per season, in both the wide and long formats |
| `stat_reachability` | every stat `stat_coverage_season` advertises returns a leaderboard, and every non-numeric label returns none |

```bash
python -m owcsmuse check
python -m owcsmuse check --only aggregate_sums --json
```

`tests/test_consistency.py` covers both directions: the checks pass on the
fixture warehouse, and each one fails with the right discrepancy when its
invariant is deliberately broken (an undated match, an edited stat under a stale
aggregate, a deleted player row, an unrefreshed org merge).

## CI

`.github/workflows/ci.yml` runs on every push and pull request:

| job | what it runs |
|---|---|
| `lint` | `ruff check .` - correctness rules only (`E`, `F`, `W`, `B`); line length and statement layout are deliberately not enforced |
| `offline tests` | `pytest` with no database configured, proving the parsers, classifier, limiter and query layer need neither network nor DB |
| `database tests` | `pytest` against a `postgres:16` service container, with the full integration suite |
| `consistency checks` | builds a warehouse from the captured fixtures (`tools/build_fixture_db.py`) and runs `python -m owcsmuse check` against it |

## Tests

```bash
pytest                                        # parsers, rate limiter, client, classifier, resolver: no network, no DB
OWCS_TEST_DATABASE_URL="postgresql://..." pytest            # adds the Postgres integration tests
OWCS_TEST_DATABASE_URL="postgresql://..." OWCS_TEST_SCHEMA=owcs_test pytest
ruff check .                                  # the lint gate CI runs
```

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

## Layout

```
migrations/001_initial.sql      schema
migrations/002_scope.sql        scope_region / tier / season / classification columns
migrations/003_aggregates.sql   fact views, materialized aggregates, coverage functions, entity_names
migrations/009_orgs.sql         orgs, team_orgs, team_identity, map-grain versus facts
owcsmuse/scope.py               classifier, decisions file, review report
owcsmuse/orgs.py                org identity: proposals, evidence, decisions and rejections
owcsmuse/crawl.py               history crawl: frontier, generations, completeness instrumentation
owcsmuse/consistency.py         warehouse invariants behind `python -m owcsmuse check`
owcsmuse/limitations.py         known gaps, surfaced by `ask` and documented above
owcsmuse/aggregates.py          refresh + coverage-aware leaderboard helpers
owcsmuse/resolve.py             entity resolver
owcsmuse/nlq/                   question -> StructuredQuery -> validate -> compile -> answer
scope/decisions.json            reviewed scope decisions (commit this)
scope/org_decisions.json        reviewed org merges and rejections (commit this)
scope/classification_report.md  generated review table
scope/org_report.md             generated org proposal table
tools/build_fixture_db.py       CI: a warehouse from the captured fixtures
.github/workflows/ci.yml        lint, offline tests, database tests, consistency checks
owcsmuse/config.py              pydantic-settings
owcsmuse/logging.py             JSON / text structured logging
owcsmuse/db.py                  connect, migrate, RawPayloadStore
owcsmuse/faceit/ratelimit.py    header parsing, adaptive limiter, jittered backoff
owcsmuse/faceit/client.py       FaceitClient: retries, raw sink, capped pagination
owcsmuse/parsers/               pure payload -> record functions (no I/O)
owcsmuse/discovery.py           deliverable 1: manifest
owcsmuse/collector.py           deliverable 3: LIST / DETAIL / reprocess / status
owcsmuse/cli.py                 python -m owcsmuse ...
tests/                          pytest suites and captured fixtures
```
