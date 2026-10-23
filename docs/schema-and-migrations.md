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
