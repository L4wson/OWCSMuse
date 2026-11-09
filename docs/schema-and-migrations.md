# Schema and migrations

How migrations are applied, the Supabase notes, and the core FACEIT tables. Later migrations are described
where their feature is: identity in [identity.md](identity.md), answers in [answers.md](answers.md), Liquipedia in
[liquipedia.md](liquipedia.md).

## Schema

Migrations live in `migrations/` and are applied in filename order by
`python -m owcsmuse migrate`, which records them in `schema_migrations`.
Every migration runs in its own transaction with `search_path` pinned to
`OWCS_DB_SCHEMA` (default `public`), and every connection the CLI opens pins
the same `search_path`, so all objects are created in and read from that one
schema explicitly. Nothing is created outside it. The token `{{schema}}` in a
migration is replaced by that schema: a `LANGUAGE sql` function body that names
a table writes `{{schema}}.table`, because PostgreSQL 17 re-parses such bodies
under a restricted `search_path` when it plans a materialized-view refresh.

### Supabase notes

- The pooler string goes in `DATABASE_URL`. Use the **session** pooler (port
  5432): the collector holds two long-lived connections for the whole run (one
  transactional connection for processing, one autocommit connection for
  `raw_payloads`), never one per match. Transaction-mode pooling is not
  needed and would break `SET search_path`.
- Objects land in `public`, next to nothing of ours; Supabase's own
  `auth`, `storage`, `realtime` and `extensions` schemas are untouched.
- Nothing in this project uses Supabase's Data API (PostgREST) or a Supabase
  client library: the CLI, the API server and the collector talk to Postgres
  over `DATABASE_URL` only, and the frontend talks to this project's own API.
  Disabling the Data API for the project changes nothing here.
- Supabase runs PostgreSQL 17; CI runs the database suites on 16 and 17 (see
  **[CI](testing.md#ci)**).
- Collation: Supabase and CI's `postgres:16`/`postgres:17` images are
  `en_US.UTF-8`; a local cluster is often `C.UTF-8` (the dev one here is).
  Mixed-case name ordering differs between the two, so a local `ORDER BY name`
  is not production's. Leaderboards carry a deterministic last key (the
  player, org or map) so a planner or collation difference cannot reorder
  tied rows. A `LANGUAGE sql` function that names a table must be written
  `{{schema}}.table` or carry `SET search_path`, or every materialized-view
  refresh fails on 17 (migration `033_pin_search_path.sql`).
- **Row Level Security is not enabled, and the Data API roles hold no grants.**
  Plain SQL migrations bypass the Supabase dashboard's RLS prompts, and Supabase
  grants `anon` and `authenticated` everything in `public` by default, which the
  project's public anon key reaches through the Data API. The owner disabled the
  Data API and revoked those grants on 2026-10-23, default privileges included,
  so a view a migration recreates gets none:

  ```sql
  REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
  REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
  REVOKE USAGE ON SCHEMA public FROM anon, authenticated;
  ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
  ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
  ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  ```

  The consistency check `api_role_grants` fails if any comes back. PUBLIC keeps
  `USAGE` on `public` and `EXECUTE` on the functions, as Postgres grants by
  default; with no table grants that reaches no data, and several of Supabase's
  own roles rely on PUBLIC's `USAGE`. The CLI, the API and ingest connect as
  `postgres` over the pooler and are unaffected.

| Table | Grain | Notes |
| --- | --- | --- |
| `raw_payloads` | one row per distinct HTTP response | `endpoint`, `params`, `http_status`, `payload` (jsonb), `body_text`, `fetched_at`, `match_id`, `championship_id`. Every request, including 429s and 5xx. A FACEIT 200 response identical to the latest stored one for the same endpoint, params and match is recorded on that row (`last_seen_at`, `times_seen`) instead of stored again (050); Liquipedia responses are always stored, since its request budget counts rows |
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
| `heroes` / `hero_aliases` / `hero_ban_settings` | hero / spelling key / one row | the reviewed hero list (`scope/heroes.json`, `heroes load`, also run by `migrate`): canonical name, `available_from`, `basis`; every spelling's key; the season bans began (049) |
| `liquipedia_bans` | Liquipedia record x played game x side x hero | each map's bans in canonical spelling, `banned_first` from `banstart`; rebuilt by `liquipedia reconcile` with `liquipedia_rounds` (049) |
| `fact_hero_bans` (materialized) / `hero_ban_maps` (view) | ban / map with bans | a ban with its series, competition, season, region, map and the team that made it (through `series.lp_flip`) and its opponent; the maps behind every ban rate (049). Materialized in 051, refreshed by `refresh` after `liquipedia reconcile`: as a view, a region-filtered answer took 72-92 s |

`match_players` is per map because that is the grain FACEIT reports; per-match
numbers are sums (the view) and per-map ratios stay in the jsonb. Player stat
keys differ between seasons (2024 payloads have 9 keys, 2026 payloads about 50),
so the typed columns are the stable subset and `stats` keeps everything.

Ingest state machine on `matches.ingest_state` (`owcsmuse/collector.py`):

```
LIST (championship listing, or a player's history in the crawl) upserts the match
   │
   ├── a bye ──────────────▶ skipped              (ingest_error 'bye: ...'; never a series)
   └── otherwise ──────────▶ stub ◀──────────────── LIST sees a different status (any state: ONGOING -> FINISHED)
                              │
          DETAIL: /matches/{id}, then /matches/{id}/stats when FINISHED, applied in one transaction
                              │
       ┌───────────────┬──────┴────────┬───────────────────┐
       ▼               ▼               ▼                   ▼
   complete       result_only       skipped              failed
   FINISHED,      FINISHED,         a bye, or            detail error, stats error other than 404,
   map stats      stats 404:        not FINISHED         empty rounds[], or the apply itself raised
   stored         result kept,      (cancelled,
                  no map stats      aborted)
```

Which states each command picks up again:

| command | re-selects |
| --- | --- |
| `detail` / `backfill` | `stub` (and `detail_fetched`, below) |
| `detail --include-failed` | also `failed` and `result_only`: a stats 404 is sometimes temporary, and a retry that finds stats completes the match |
| `detail --refresh` | also `complete` and `skipped` |
| `reprocess` (stored payloads, no FACEIT) | `stub`, `detail_fetched`, `complete`, `skipped`, `failed`. **Never `result_only`**, on purpose: such a match has no stored stats payload (FACEIT answered 404 and `RawPayloadStore.latest` keeps only 200s), so re-applying it reports "no stored stats payload", which is not a 404, and the match would become `failed`, dropping its series from every record (87 matches in production on 2026-11-08). Only a live retry can change it: `detail --include-failed`. `test_reprocess_leaves_a_result_only_match_holding_its_result` holds this. |

**Has a result** means `complete` or `result_only`: the SQL function `has_result(ingest_state)` (migration 052) is the
one definition, and the `series` view, `agg_map_modes` and every Python query call it rather than spelling the states
out. It is inlined by the planner, so it costs nothing. Map- and player-grain facts that need FACEIT stats rows still
ask for `complete` alone.

`detail_fetched` is allowed by the CHECK constraint (001) but nothing writes it: `apply_detail` goes from `stub` to
its outcome in one transaction. It stays in the constraint and in `RESUMABLE_STATES`, so a row that somehow held it
would still be picked up; production has none. What you will see is `stub`, `complete`, `result_only`, `skipped` and
`failed`.
