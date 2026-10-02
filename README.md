# OWCS Muse

[![CI](https://github.com/L4wson/OWCSMuse/actions/workflows/ci.yml/badge.svg)](https://github.com/L4wson/OWCSMuse/actions/workflows/ci.yml)

Pulls Overwatch Champions Series (OWCS) match data from the FACEIT Data API v4
into a Postgres warehouse, answers questions about it, and shows the rows behind
every answer. No ORM: Python 3.11+, `httpx`, `psycopg`, `pydantic-settings`,
plain SQL migrations, `pytest`, `fastapi` for the HTTP layer, and a Vite + React
frontend in `web/`.

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
`.env` is read from the repository root whatever the working directory; real
environment variables take precedence. One setting is required everywhere and has
no default, so an unset value fails at startup instead of connecting somewhere
unintended; a second is required only by commands that call FACEIT:

- `FACEIT_API_KEY` (ingest commands only: `discover`, `backfill`, `crawl`, ...;
  `serve`, `ask` and the tests do not need it)
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
| An empty bracket slot is a placeholder faction named `bye`, scored 1-0 for the real team | It is not a series. Ingest marks it `skipped` (`ingest_error` starts `bye:`) at LIST and at DETAIL, and migration 021 reclassified the 24 already stored. Left in, they gave 13 teams wins they never played and a team called "bye" 24 losses across NA and EMEA; `region_consistency` found it |
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
- Supabase runs PostgreSQL 17; CI runs the database suites on 16 and 17 (see
  **CI**). A `LANGUAGE sql` function that names a table must be written
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

## Scope

Target set: OWCS North America and OWCS EMEA main competition (regional
stages, their group stages and playoffs) plus international events where NA
and EMEA teams compete (Midseason Championship, World Finals, Champions Clash,
the 2024 Dreamhack Dallas Major). Excluded: open qualifiers, relegation,
Asia / Korea / Japan / Pacific / China / South America / Oceania, cancelled or
test events. Korea has no usable FACEIT data, so nothing Asia-region is
included from FACEIT even where a championship exists. Korea is a declared
region (`korea`, results only) so that its Liquipedia results can land under
it; until they do, a Korean question is refused as results-only or as having
no data, never as out of scope.

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
series score are known, the maps are not. 76 of 485 finished series in scope
are `result_only`, and they are not spread evenly - 28 of 94 series in playoff
and LAN competitions have no map stats against 48 of 391 elsewhere, and all 14
Dreamhack Dallas matches are `result_only`. **Map-grain answers therefore
under-represent exactly the matches that mattered most.** Series-grain answers
(`record`, `series record against`) still count them, and a versus answer names
the series it had to exclude.

### 2024 carries 9 stat keys; 2025 and 2026 carry 47

`stats_2024` - the 2024 payloads expose only Eliminations, Deaths, Assists,
Damage Dealt, Healing Done, Damage Mitigated, K/D Ratio, Result and Role (the
last two of those are a rate and a label, so six countable stats). Per-10
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
here ranks NA and EMEA main-competition play, not OWCS worldwide. Korea is
declared a results-only region (`region_sources`): when its data arrives through
Liquipedia it will answer records, head-to-heads and placings, never a player
stat.

### A results-only slice has series results but no player stats, from any source

`results_only_source` - coverage says which stat keys exist per season; it has
no concept of a slice where no player stats exist at all. Liquipedia records
results, map scores, picks and placings and never a player stat; a FACEIT
`result_only` competition (Dreamhack Dallas, all 14 series) has series results
and no per-map stats either. `source_capabilities` (migration
`031_capabilities.sql`) derives per included championship, from provenance,
whether any source gives it map results and whether any gives it player stats;
`region_sources` declares the same per region (Korea: `{liquipedia}`, no
player stats). Where a whole slice is results-only, a player-stat question is
refused with reason code `results_only` and offered what that slice can answer
(the series record, the question without the region) rather than answered with
an empty or partial ranking. Where only part of a slice is, the answer names
the part it could not rank. An included championship with no series at all is
empty, not results-only, and stays on the no-data path.

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

**What the evidence is actually worth.** The proposer weighs four signals: name
identity after folding, roster overlap across the two date windows, date
adjacency, and region. Reviewing the output on real data inverted the expected
ordering, twice:

- **Roster overlap is weak evidence, and sometimes points the wrong way.** In
  esports whole rosters move between organisations, so a squad that transferred
  looks identical to a rename. Four pairs at 80-100% overlap - Geekay Esports /
  NTMR, NTMR / Dallas Fuel, LeftRightGnight / Geekay Esports, Al qadsiah /
  Geekay Esports - are distinct organisations. Meanwhile the one real rename in
  the data, Al qadsiah to qadsiah, shared **1 of 8** players, because the roster
  turned over at the same time. Merging on overlap would have made four wrong
  merges and missed the right one.
- **Name identity is not enough by itself, and two applied merges proved it
  the hard way.** "SpaceStation Gaming" (NA) was merged with "SpaceStation"
  (EMEA) on a contained-name match; "Geekay Esports" (NA) was merged with an
  *identically named* "Geekay Esports" (EMEA). Both had 0% roster overlap.
  Both were wrong: the two are unrelated teams that happen to share a name,
  and the wrong merge surfaced as a real bug - an NA player's "record" query
  pulled in a completely unrelated EMEA team's matches. Name identity, even
  exact-fold, is corroborating evidence, not identity by itself.
- **Region is a hard rule, not a signal.** OWCS is region-locked: a
  competing roster plays in `na` or `emea`, never both, and does not switch
  between them season to season. `region_conflict()` refuses any pair whose
  match history spans disjoint regions, before name or roster evidence is even
  considered - identical names included. `international` events (Dreamhack,
  Midseason Championship, ...) never conflict with anything, since any region
  can attend one alongside its home-region schedule.
- **Date adjacency corroborates**, but only within a region. Two ids whose
  match windows overlap may be two teams that coexisted, which is reported
  rather than assumed.
- **A name change on a stage boundary is a roster pickup, not a rebrand.** In
  OWCS a team id is issued per roster and the name on it changes when another
  organisation picks the roster up between stages: Ex Oblivione -> Virtuspro
  (2025 Stage 1), Avidity -> Extinction (2025 Stage 2), Extinction -> The Kafe
  (2026 Stage 2, which began 2026-06-13). The roster continues, the organisation
  does not, so the new name starts a new era of the same team id (a window,
  below) rather than extending the old org's history. A rename by the same org
  (Al qadsiah -> qadsiah) lands mid-stream and keeps the roster's org. The stage
  boundary is the tell - but not alone: production shows 18 team ids carrying
  more than one name, and SpaceStation -> SpaceStation Gaming, GenG -> GenG
  Esports, Goud Guys -> Goud Guys ANM, PIP -> PxG PiP and Sakura -> Sakura
  Esports also land on stage boundaries and are renames. So three signals read
  a change (`classify_name_change`): a new name that **contains or extends** the
  old one is a rename and starts no window; a **wholly different** name on a
  stage boundary is a pickup; a **registration placeholder** (a `team_<captain>`
  name, or one that lived only in a stage's opening fortnight, replaced inside
  that stage once the roster signed up: team_chiime -> Dreamland, BuboSprayCheck
  -> ENCE) is the same organisation and no window; anything else (a different
  name inside one stage, or two names whose date ranges overlap) is reported for
  a person. The tool decides nothing. The review of all 18 is
  `scope/org_window_review.md` (`python tools/window_review.py`, from the
  captured history in `scope/team_name_history_2026-10-01.json`); the owner's
  verdict on each is `scope/org_window_decisions.json`, and the report shows it
  under the id, flagging where a signal reads the id differently (Umbrellaacademy
  -> ROCstars fires the placeholder signal and was decided an org change; the
  overlapping Anyones Legend / 1234 and Quick Esports / 1DIPv100GORILLA dates
  are a FACEIT artifact over a roster drop, decided pickups). A team id whose
  names are several organisations' eras carries one mapping per era
  (`orgs decide --add`, stored under `windows`): 0464a373 is UNC inc (its own),
  Rad, Sakura / Sakura Esports and LuneX; d20d1868 is team_chiime / Dreamland
  (its own), Supernova and Team Z. NTMR is one organisation across cefc3f72
  (2025 Stage 1) and c5116cb3 (from Stage 2), each mapped only over its own
  NTMR era so FMCL's and Timeless's eras stay out of it.

**A mapping holds over a window.** A FACEIT team id belongs to an org over
`[valid_from, valid_to)` (`orgs decide --from ... --to ...`; absent means for all
time, which is what every decision made before windows existed still means).
Outside its window the team id is itself: keyed `team:<id>`, displayed and
searchable by the name it carried then, with its own record. That is how an
acquired roster stays out of the acquiring org's history - Virtus pro took over
the Ex Oblivione roster in 2025 and FACEIT kept the team id, so `bb5dd404` is
Virtus pro from 2025-01-01 and Ex Oblivione before it; "Ex Oblivione record"
answers with the 2024 series and "VP record" without them. Identity is a
function of (team id, when): `team_identity_at()`, which every fact view joins
at the series' own time; `team_identity` is identity now. The proposer proposes
a window whenever a team id carried a name that is not the org's before it first
carried the org's name (`propose_window`), and nothing is proposed from roster
movement. A window is sourced, not chosen: `orgs decide --from-name "Virtuspro"`
bounds it by the first sighting of that FACEIT name on the team id, resolved
from `team_names` at load (a name the id never carried applies nothing and is
reported). One org can span several team ids each bounded to its own era -
Extinction is `2b7f8ef6` over its 2025 Extinction era and `a35f8d47` over its
2026 one, on org branding rather than roster continuity. A team id cannot
belong to two orgs at once (a trigger refuses the overlap), and `check` flags a
window that covers none of its team id's series.

Current state: 9 orgs covering 18 team ids (one of them windowed), 7 pairs
recorded as reviewed rejections (2 of them region conflicts found after the fact
and reversed), 62 team ids unmapped and queryable as themselves.

**Known gap: a team id maps to an org for all time.** A FACEIT team id can outlive
an organisation: id `bb5dd404` was "Ex Oblivione" in 2024 and "Virtuspro" in 2025,
because Virtus pro acquired that roster. Roster movement is not org identity (see
above), so Ex Oblivione's 2024 series are not Virtus pro's, yet today the org's
record includes them (5 series where 2 are Virtus pro's). Two consequences: an
org's record over-counts across an acquisition, and an org's searchable names hold
each team id's *current* name only, so "Ex Oblivione" finds nothing. The fix is a
date-bounded team-to-org mapping with a name history for each side; it is
scheduled with the source-agnostic identity work (Stage 3 of the Liquipedia
integration). The golden suite holds both as known bugs (G11, G13).

## Aliases

`resolve()` already finds an abbreviation FACEIT itself recorded - if a team
really was named "SOG" at some point, that is in `entity_names` (nickname and
team-name history) and needs nothing further. It cannot find community
shorthand nobody on FACEIT ever typed - "SSG" for SpaceStation Gaming, "TL"
for Team Liquid - because there is nothing in the data to match it against;
the fuzzy scorer in `resolve.py` picks something unrelated instead. That is
not something to guess at: it is a human decision, routed through the same
reviewed-decisions-file pattern as scope and org identity, never a hardcoded
table baked into the resolver.

```bash
python -m owcsmuse alias set SSG --type org --entity-id spacestation-gaming --note "..."
python -m owcsmuse alias set TL  --type team --entity-id a58dedff-8045-46be-a13e-2402495b6a9d --note "..."
python -m owcsmuse alias forget SSG
python -m owcsmuse alias load      # write scope/alias_decisions.json into entity_aliases
python -m owcsmuse alias status
```

An alias resolves as an exact, authoritative lookup (`resolve_alias()`), ahead
of the fuzzy scoring in `rank_candidates()` and before it ever runs - not
folded into the same ranked pool. That distinction mattered in practice: "TM"
scores 1.0 against the Twisted Minds alias, but "TML Nightmare" (an unrelated
team) scores 0.9 against the bare letters "tm" by starting with them, close
enough that the ordinary ambiguity margin would have asked which one was
meant. A human already decided that; resolve() must not re-open it.

Seeded so far: `SSG` -> SpaceStation Gaming, `TL` -> Team Liquid, `TM` ->
Twisted Minds, `CR` -> Crazy Raccoons, each pointing at a team id rather than
an org where the team is currently unmapped.

## Competition names

FACEIT League numbers its seasons ("S9 NA OWCS Central - Playoffs"); the competition people follow is
"OWCS 2026 NA Stage 2 Playoffs". The mapping is display-only: `championships.name` stays FACEIT's, and only
`championship_display_name()` reads the reviewed names in `competition_names`. A name is shown only after a person
has decided it.

```bash
python -m owcsmuse competitions propose           # scope/competition_names_report.md; applies nothing
python -m owcsmuse competitions accept            # bulk-accept the reviewed Liquipedia page map
python -m owcsmuse competitions accept --bases liquipedia-owner,owner   # pages / descriptions you supplied
python -m owcsmuse competitions decide <id> [--name "..."]              # one competition
python -m owcsmuse competitions load              # decisions -> competition_names (`migrate` also does this)
```

Sources, in order of trust: `scope/liquipedia_map.json` (the page that covers each FACEIT League competition,
reviewed in Stage 1: `liquipedia`), `scope/competition_pages.json` (pages supplied by the project owner for the 2024
competitions: `liquipedia-owner`; a path marked `verified: false` was inferred, not seen) and events described by
the owner with no page (Dreamhack Dallas, the relegations: `owner`). Year, region and stage come from the page path
and the phase from FACEIT's own suffix, cross-checked against the page's shape. A decision made against a FACEIT
name that later changes stops applying and is reported as stale.

A page path nobody has seen (`"verified": false` in `scope/competition_pages.json`) is never bulk-accepted. One request
checks them all, projection first:

```bash
python -m owcsmuse liquipedia probe-pages              # shows the projection (1 request) and the budget; sends nothing
python -m owcsmuse liquipedia probe-pages --execute    # sends it (needs LIQUIPEDIA_API_KEY and OWCS_LIQUIPEDIA_ENABLED=1)
```

It reports, per page, how many matches Liquipedia holds on it. Set `"verified": true` for the pages that came back, and
`competitions accept --bases liquipedia-owner` takes them.

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

## Natural-language questions

```bash
python -m owcsmuse ask "who had the most eliminations in 2024"
python -m owcsmuse ask "KSAA average healing on control maps" --debug   # shows the compiled SQL + params
python -m owcsmuse ask "Twisted Minds vs ENCE" --json
python -m owcsmuse ask "what stats are available"
python -m owcsmuse ask "Sugarfree map record against Zeruhh" --page 2 --evidence-rows 10
python -m owcsmuse ask "who had the most eliminations" --evidence-for <player_id>
```

Every answer opens with one deterministic sentence and carries the rows behind
it; see [HTTP API](#http-api) for both, which the CLI and the API share.

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
`unsupported_question`, `out_of_scope`, `results_only`, `ambiguous_entity`, `unknown_entity`,
`no_data`, `invalid_query`, each with suggestions. Exit code is 0 for an
answer and 2 otherwise.

Tests: `tests/test_nlq_parser.py` holds 60+ question / expected-object pairs
(supported, ambiguous and unanswerable) asserted on the parsed object, and
`tests/test_nlq_compile.py` covers validation and compilation against a
hand-built schema, all without a database or model. `tests/test_nlq_db.py`
runs `ask()` end to end on the fixture data when a database is configured,
`tests/test_sentence.py` and `tests/test_evidence.py` cover the sentence
templates and the evidence SQL offline, and `tests/test_api.py` drives the HTTP
layer and reconciles evidence rows against the aggregates they explain.

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

## HTTP API

```bash
pip install -e ".[api]"
python -m owcsmuse serve                      # http://127.0.0.1:8000, /docs for the OpenAPI page
python -m owcsmuse serve --host 0.0.0.0 --port 8080
```

Three endpoints, all read-only, over the same `ask()` pipeline the CLI uses - so
there is one definition of what an answer is, and no SQL is written anywhere in
the web layer.

| endpoint | what it does |
|---|---|
| `POST /ask` | a question in, an answer object out |
| `GET /query/{slug}` | the same question re-run against current data, from a shareable link |
| `GET /suggestions` | example questions built from entities that actually have data |
| `GET /healthz` | liveness plus a database round trip |
| `GET /` | what the service is, and the known limitations by id |

```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "Sugarfree map record against Zeruhh", "page_size": 5}'
```

```jsonc
{
  "slug": "V5iNpKcbhata",
  "url": "/query/V5iNpKcbhata",
  "status": "ok",                       // ok | clarify | cannot_answer
  "sentence": {
    "text": "sug2rfree is 22-20 in maps against zeruhh across 2024-2026.",
    "spans": [ {"start": 0, "end": 9, "kind": "player", "text": "sug2rfree", "entity_id": "..."} ]
  },
  "aggregate": {
    "description": "player vs player, map grain",
    "columns": [{"key": "map_wins", "label": "Map wins", "type": "integer"}, ...],
    "rows": [ ... ]
  },
  "evidence": {
    "available": true, "grain": "map", "description": "every map behind this record",
    "page": 1, "page_size": 5, "total_rows": 42, "total_pages": 9, "has_more": true,
    "expanded_for": null, "expandable_by": null,
    "columns": [{"key": "played_at", "label": "Date", "type": "date"},
                {"key": "score", "label": "Score", "type": "score", "pair_key": "opponent_score"}, ...],
    "rows": [ {"played_at": "2026-07-04T22:47:50Z", "competition": "S9 NA OWCS Central - Playoffs",
               "team": "SpaceStation Gaming", "opponent": "Team Liquid", "map_name": "Ilios",
               "game_mode": "Control", "score": 2, "opponent_score": 1, "result": "won",
               "eliminations": 20, "deaths": 10, "assists": 2,
               "match_url": "https://www.faceit.com/en/ow2/room/1-1985af81-..."} ]
  },
  "coverage": { ... }, "limitations": [ ... ], "notes": [ ... ],
  "attribution": null,     // {source, license, license_url, pages[]} whenever a Liquipedia value fed the answer
  "entities": { ... }, "query": { ... },   // the structured query it understood
  "code": null, "reason": null,
  "suggestions": [],       // advice, when advice is the answer ("check the spelling")
  "alternatives": [],      // questions that do work, ready to run
  "parser": "rules"
}
```

### Column descriptors

Rows carry raw values, so anything reading them can sort, sum or plot. What each
column *is* comes with it, from `owcsmuse/nlq/columns.py`:

```jsonc
{"key": "played_at", "label": "Date", "type": "date"}
{"key": "score", "label": "Score", "type": "score", "pair_key": "opponent_score"}
{"key": "coverage_pct", "label": "Coverage %", "type": "percent"}
```

`type` is the formatting contract - `date`, `score`, `percent`, `integer`,
`decimal`, `text`, `link`, `flag`, `result`, `list` - and it is decided from the
values as well as the name, so a Postgres `numeric` holding whole numbers is an
`integer` column and a damage total does not render as `9730.00`. Join keys
(`match_id`, `player_id`, `org_key`) stay in the rows and are never described as
columns: a client needs them, a reader does not. A column that is empty at this
grain is left out, which is how a series answer has no "Map #".

A ranked row also carries `entity: {id, type, name, column}`, so expanding it is
mechanical rather than a guess about which column holds the id.

`status` is part of the body, not the HTTP code: a refusal or a clarification is
a real answer with a reason code, so `POST /ask` returns 200 for all three and
reserves 422 for a malformed request and 404 for an unknown slug. A database that
cannot be read is **503 on every endpoint**, `/ask` included - the service is up
and nothing was refused, and a client must be able to say so.

### Evidence rows

Every answer that summarises something carries the rows that produce it, at the
grain the claim was made at: a map record returns each map, a series record
returns each series. They come from the same fact views as the aggregate and
carry the same filters, so they add up to it - `tests/test_api.py` pages through
them and checks exactly that.

- Newest first, `page` / `page_size` (default 25, max 200), with `total_rows`,
  `total_pages` and `has_more` from one query.
- Each row carries the date, competition, both sides, map, mode, score, result,
  the subject's stat line, and `match_url`, the FACEIT room it came from.
- A series row carries `map_stats_recorded`, so a `result_only` series is
  visibly a series with no maps rather than a gap.
- A ranking is a claim about many rows, so one page of evidence can only be
  about one of them: `expanded_for` says which (the top row by default),
  `expandable_by` names the field to pass back, and `evidence_for` asks for
  another. A map or mode breakdown expands the same way.
- When a map record is empty **because the maps were never recorded**, the
  evidence is the series themselves - the proof that the pairing happened and
  the stats did not.

### Answer sentences

One deterministic sentence per intent, built from a template and the rows that
came back (`owcsmuse/nlq/sentence.py`). No model writes it: every number is read
out of a returned row, so the same question on the same data always produces the
same words, and a template that lacks a value it needs degrades to a shorter
sentence instead of inventing one. `tests/test_sentence.py` asserts that every
digit group in a sentence appears in the row behind it.

Entity mentions carry character offsets and the entity id they resolved to, so a
client can link a name without re-parsing the text.

### Choosing between candidates

An ambiguous name returns `status: "clarify"` with the candidates, and **each
candidate carries a `question` that resolves to exactly that entity**:

```jsonc
{"entity_type": "org",  "entity_id": "team-peps", "current_name": "Team Peps",
 "matches": 55, "seasons": [2024, 2025, 2026],
 "first_at": "2024-03-08T...", "last_at": "2026-05-27T...",
 "question": "org:team-peps record"}
```

The question is the original one with the ambiguous name replaced by the entity's
id, so the season, map or opponent in it survives. A client must never build this
itself by substituting a name - substituting a name is exactly what fails when
two entities share one. The parser accepts `player:`, `team:` and `org:` prefixed
ids anywhere a name can appear, and a bare FACEIT GUID as well.

`seasons`, `first_at` and `last_at` are what tell two same-named entities apart:
"Team Falcons, 4 matches, season 2024" against "Team Falcons, no matches".

### Refusals that go somewhere

`suggestions` is advice and stays advice where advice is the answer ("check the
spelling"). `alternatives` are runnable questions, built from what the service
already knows: the entities it resolved, and which seasons actually carry the
stat.

```
Team Falcons and Crazy Raccoons met, but none of those series has map stats on FACEIT
  try: Team Falcons series record against Crazy Raccoons     <- series grain counts them
  try: Team Falcons record
  try: Crazy Raccoons record

'Final Blows' is not recorded for the 2024 season (seasons with it: 2025, 2026)
  try: who had the most final blows in 2026

KOREA is a results-only region: no source records player stats there, so there is no player leaderboard to give
  try: who had the most eliminations                       <- the same question where stats exist
```

The question that just failed is never offered back.

### Shareable links

A slug is a digest of the normalized question, so the same ask always produces
the same link and "who had the most eliminations in 2024" and
"WHO had the most  eliminations in 2024" share one. `saved_queries` stores the
question, never the answer: a link re-runs against current data, which is the
point of sharing it.

`GET /query/{slug}` compares the parse saved with the link against today's and
returns the verdict, so no client diffs two objects to find out:

```jsonc
"shared": {"times_asked": 3, "parsed_when_saved": { ... },
           "parse_changed": true, "parse_change": ["intent: head_to_head -> versus"]}
```

### Suggestions

Built from the warehouse, not hardcoded: the stat keys, teams and players in
`/suggestions` are the ones with the most data, so a suggested question never
teaches a new visitor that the tool returns nothing. A test asks the first few
and asserts none of them comes back empty.

## Frontend

```bash
python -m owcsmuse serve                      # the API, on :8000
cd web && npm install && npm run dev          # the app, on :5173, proxying to it
npm test                                      # component tests, no server needed
npm run build                                 # static files in web/dist
```

Vite + React, plain CSS, no UI framework and no router: two routes (`/` and
`/q/<slug>`) are thirty lines of `history.pushState` in `src/router.js`, which is
less code than configuring a router would be. `OWCS_API_URL` moves the dev proxy;
`VITE_API_BASE` points a build at a deployed service. A static host must rewrite
unknown paths to `index.html`, or a shared `/q/<slug>` link 404s before the app
loads.

The landing page is a question box and three or four examples taken live from
`/suggestions`, so every example has data behind it. Everything else is the
result view:

- **The sentence**, large, at the top. Entity names are links, and they are found
  by the API's character offsets - the text is sliced at `start`/`end` and never
  searched for a name. A nickname that is also an ordinary word, or a name that
  appears twice as two different entities, stays right.
- **Coverage, notes and limitations** sit between the sentence and the table. A
  leaderboard that covers 2025 and 2026 but not 2024 says so above the numbers,
  not in a tooltip or a footer.
- **The evidence table**, rendering the columns the API described - label and
  type - so a map-grain answer shows maps and a series-grain answer shows series
  with no client-side knowledge of either. The client holds no label table and no
  key-name formatter; it formats by `type`, which is why a new column renders
  correctly the day the warehouse grows one.
- **Paging** follows `page` / `total_pages` / `has_more`, newest first.
- **Ranked answers** expand one row at a time: the expanded row is marked in the
  ranking, the evidence header names it, and any other row can be expanded
  through `evidence_for`.
- Below 720px the same table markup becomes cards, using the column label each
  cell already carries. No second component, no horizontal scrolling on a phone.

### The states that are not answers

Built first, because they are common:

- **clarify** renders the candidates as options with what separates them - kind,
  matches in scope, the seasons they were active, and the id when two of them
  share a name. Picking one sends the `question` the service shipped with that
  candidate, verbatim; the client constructs nothing.
- **cannot_answer** shows the reason plainly, the API's advice, and the API's
  `alternatives` - questions that do work - falling back to live suggestions only
  when the service has nothing specific to offer.
- **cannot_answer with evidence** is the informative refusal: a map record that
  is empty because FACEIT never recorded the maps still renders the series behind
  it, flagged as having no map stats.
- **Service failures** are kept apart from refusals: 503 says the service is
  unavailable, a failed `fetch` says it could not be reached, 404 on a shared
  link says the link has nothing behind it. None of them look like a question
  that was understood and declined.

`web/tests/` covers all of the above with payloads captured from the running
service (`tests/fixtures.js`), so the tests exercise what the API actually
sends. `npm test` runs them against a mocked `fetch`; nothing contacts a server.

## Deploying

Three moving parts, none of which share a host requirement.

**The API** is a stateless uvicorn process: `python -m owcsmuse serve --host
0.0.0.0 --port 8000`, or any ASGI runner pointed at `owcsmuse.api:app_factory`.
It needs `DATABASE_URL`, outbound access to Postgres, and TLS in front of it.
It does not need `FACEIT_API_KEY`: no request path calls FACEIT, answers come
from the warehouse. Each process keeps up to four idle connections, so size
`workers x 4` against the Supabase pooler's ceiling before scaling out. Run
`python -m owcsmuse migrate` on deploy; it is idempotent and applies in filename
order.

**The frontend** is static: `cd web && npm ci && npm run build` produces
`web/dist`, which any static host or CDN serves. Two requirements. It needs
`VITE_API_BASE` at build time pointing at the API (or same-origin routing, in
which case leave it unset), and the host must rewrite unknown paths to
`index.html` or a shared `/q/<slug>` link 404s before the app loads. CORS on the
API is open, so a separate origin works as-is.

**Ingest is a cron, not part of the API.** A scheduled worker with
`FACEIT_API_KEY`, `DATABASE_URL` and outbound access to FACEIT:

```bash
python -m owcsmuse backfill           # LIST + DETAIL for the championships in scope
python -m owcsmuse crawl run          # the 2025/2026 main series, which the endpoints hide
python -m owcsmuse refresh            # materialized views; nothing new is visible until this runs
python -m owcsmuse check              # gate: exit 1 means do not trust what just landed
```

Every phase is resumable and idempotent, so a failed run is re-run rather than
repaired, and the adaptive limiter keeps FACEIT requests inside the published
allowance. Daily is ample; OWCS plays on weekends. Two things it deliberately
does not do: it never marks a newly discovered competition as in scope - that
stays a human decision through `classify` and `scope/decisions.json` - and it
never merges an org identity without a reviewed entry in
`scope/org_decisions.json`. A deploy that automates those away gets wrong answers
that look right.

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
| `phantom_map_isolation` | a FACEIT map row beyond Liquipedia's game count for a linked series is in no fact view; counts the player rows that rode on one |
| `region_consistency` | no org and no team id has matches in both `na` and `emea` (OWCS is region-locked); `international` never counts. This audits what is applied, where the proposer's `region_conflict()` only guards new merges |
| `liquipedia_map_isolation` | no `match_players` row joins to a `source = 'liquipedia'` round: Stage 2 map enrichment never invents player stats |

```bash
python -m owcsmuse check
python -m owcsmuse check --only aggregate_sums --json
```

`tests/test_consistency.py` covers both directions: the checks pass on the
fixture warehouse, and each one fails with the right discrepancy when its
invariant is deliberately broken (an undated match, an edited stat under a stale
aggregate, a deleted player row, an unrefreshed org merge).

## Liquipedia integration

FACEIT is complete for NA and EMEA main series but has no map stats for 76
series, and nothing for Korea, China or the LAN events. Liquipedia, through its
LiquipediaDB API, fills that in as results, map scores and picks/bans - never
player stats. It is being integrated in stages, each reported before the next
starts:

| stage | what | status |
|---|---|---|
| 0 | client, request planner, cache, attribution | done; auth confirmed and the match record's shape seen (see below) |
| 1 | completeness cross-check: FACEIT match ids joined to Liquipedia, 2025/2026 main series | not started |
| 2 | enrich the 76 result-only series with map-level results, source recorded per field | done: 33 of them are exact-linked and now enriched (122 maps); see below |
| 3 | source-agnostic match model and cross-source identity | not started |
| 4 | LAN and international events | Dreamhack Dallas 2024: page owner-confirmed (`Overwatch_Champions_Series/2024/Major`, in `scope/liquipedia_map.json`), one request planned, not yet fetched |
| 5 | Korea and China, results only | not started |

### The client (Stage 0)

```bash
python -m owcsmuse liquipedia status                 # budget used this hour, last 429, what is held; sends nothing
python -m owcsmuse liquipedia plan                   # the Stage 1 plan and its PROJECTED REQUEST COUNT; sends nothing
python -m owcsmuse liquipedia run                    # shows the plan, then stops: a dry run
python -m owcsmuse liquipedia run --execute          # carries it out (needs OWCS_LIQUIPEDIA_ENABLED=1)
python -m owcsmuse liquipedia verify                 # ONE request: confirms the key, shows a match record's shape
```

- **Key and opt-in.** `LIQUIPEDIA_API_KEY` in `.env` (see `.env.example`). Nothing is
  ever sent unless `OWCS_LIQUIPEDIA_ENABLED=1` is also set in the process
  environment: the key alone is not consent to spend the allowance. The key travels
  only in the `Authorization` header and is never stored or logged.
- **Budget: 60 requests an hour**, counted from `raw_payloads` itself (rows with
  `source = 'liquipedia'`, failures and timeouts included, cache hits not), so
  restarting a process cannot reset it. When it is spent a run stops as `budget`, not
  as a failure, and rerunning later resumes where it left off.
- **The planner** drops values already held, ORs the rest into as few conditions as a
  URL allows, pages each batch at `OWCS_LIQUIPEDIA_PAGE_LIMIT` rows, and prints the
  projected request count and what the remaining budget allows *before* any run.
- **Never re-request what is held.** Every response is stored in `raw_payloads` with
  its headers (`endpoint = 'liquipedia:<endpoint>'`), an identical request is answered
  from there, and the `liquipedia_coverage` ledger records which pages have been
  fetched in full so that changing the set a run wants does not repeat old requests.
  A stored answer that carried an error is never reused as data.
- **A 429 stops everything.** The run ends on that request with no retry and no
  backoff, the 429 is stored with its headers, and nothing more is sent until its
  `Retry-After` (else one hour) has passed. Any other failure also stops the run; there
  is no automatic retry anywhere, because a retry spends budget on a request that just
  failed.
- **Attribution (CC-BY-SA 3.0).** Every Liquipedia-sourced value carries the URL of the
  page it came from: `Sourced` cannot be built without one, `liquipedia_coverage` has
  a checked `page_url` column, and an answer that used Liquipedia values carries
  `Answer.attribution` (source, licence, the page URLs), which the CLI prints and the
  API returns. Answers that used none carry `null`.
- **The key is never kept.** Liquipedia's own 403 quotes the key back (`API key "..." is
  not valid`), so anything that came off the wire is scrubbed of the key before it is
  stored, raised or logged.
- **API only.** Liquipedia's terms forbid automated access to rendered pages, so
  nothing fetches or parses HTML.

### What a match record looks like (seen in the verification request)

`GET /match` returns `{"result": [...]}`; there are no rate-limit headers, so the budget is our own count. A record
is about 6 KB of JSON, with structured fields already decoded (not JSON-in-a-string):

- **Where it is:** `pagename` is the page the match sits on (`.../Korea/Regular_Season`), `parent` the stage above
  it (`.../Korea`). The plan filters on `pagename`, and a value's attribution URL is built from it.
- **The match:** `match2id`, `match2bracketid`, `date` (UTC), `winner` (`"1"`/`"2"`), `bestof`, `type` (Online/Offline),
  `finished`, and `match2opponents` (team `name`, `score`, `status`, `teamtemplate`, and `match2players` with page-style
  names such as `HYEON_(Kim_Seong-hyeon)`).
- **Maps:** `match2games[]` has `map`, `mode`, `scores`, `winner`, `opponents[]` and, in `extradata`, the hero bans
  (`team1ban1`, `team2ban1`, `banstart`): map-level results without player stats, as Stage 2 needs.
- **Not yet seen:** where the FACEIT match id sits. The five sample rows were Korea and China, which are not on FACEIT;
  the first NA/EMEA rows in the Stage 1 fetch will show it (candidates: `links`, `extradata`).

### Stage 2: map-level enrichment of result_only series

`python -m owcsmuse liquipedia enrich [--plan]` reads what Stage 1 already linked (`liquipedia_links`, tier
`exact`) and, for every one whose FACEIT series is `result_only`, inserts `match_rounds` rows from Liquipedia's
`match2games` - map, mode, per-map score, winner. `--plan` classifies without writing and reports whether a gap
would need a new request (none does here: everything is already in `raw_payloads` from Stage 1). Currently 33 of
the 76 result_only series in scope are exact-linked and enriched this way (122 maps); the other 43 sit on a page
Liquipedia does not cover, or Liquipedia has no matching record.

Source is recorded per field, never merged silently:

- `match_rounds.source` (`faceit` | `liquipedia`). A Liquipedia round is only ever inserted where FACEIT has none,
  so there is never a same-round conflict to arbitrate. **The Stage 2 rule that FACEIT won for map stats by
  construction was inverted on 2026-10-02** (migration `034_map_winner_precedence.sql`, see **Stage 3: the
  source-agnostic series**): FACEIT fabricates map rows when a sweep closes a series early and counts drawn maps as
  wins, so Liquipedia is now the source of record for a series' result, best-of and map count wherever a linked
  record exists, and a FACEIT map row beyond Liquipedia's game count is a phantom in no fact view. Player stats
  remain FACEIT-only, as before.
- `matches.date_source` (`faceit` | `liquipedia`) and `matches.liquipedia_played_at`. On a `result_only` series
  FACEIT's own timestamp is when the result was entered, not when it was played - Stage 1's alignment numbers put
  some of these 70+ hours off - so Liquipedia's scheduled time wins there, read through `fact_team_maps` /
  `fact_team_matches`'s `coalesce(liquipedia_played_at, match_time(...))`, without touching FACEIT's own
  `started_at` / `finished_at` / `configured_at` columns.
- Push-mode maps are normalised to the same win/loss indicator (1/0) FACEIT's own `round_stats` already uses for
  that mode (it never carries the push distance), rather than storing Liquipedia's literal distance score
  alongside FACEIT's indicator scores in the same integer column.

Never touched: `match_players`, and therefore `fact_player_maps` and every player aggregate - Liquipedia carries
no player stats, so none is invented. `python -m owcsmuse check` asserts this directly
(`liquipedia_map_isolation`): no `match_players` row may join to a `source = 'liquipedia'` round.

**Attribution.** `Answer.attribution` (CLI and API, see above) is populated from the FACEIT match ids an answer's
evidence rows actually name: a match only carries a page when a Liquipedia-sourced value (a map or a date
correction) contributed to it. An answer built entirely from FACEIT's own data carries `attribution: null`, exactly
as before Stage 2.

### Stage 3: identity without FACEIT

Players are keyed by FACEIT GUID and teams map to orgs through FACEIT team ids; Korean teams and players have
neither. An **anchor** is "this entity is known in this source by this handle": a FACEIT id is implicitly its own
anchor, a Liquipedia player page or team name is a row in `entity_anchors` (migration `027_entity_anchors.sql`).
One entity may carry anchors in both sources; a Liquipedia-born entity carries one and gets an id of its own
(`lp:player:<page>`) in the same `players` table, so everything keyed on ids keeps working and it shows as itself.

Liquipedia's line-ups are stored as a parsed copy (`liquipedia_match_players`: page, handle, real name,
nationality; `liquipedia_matches` gains the team templates), and `lp_player_names` / `lp_team_names` are the
Liquipedia-side name history - every handle and real name a page has carried, every name a template has carried,
with first/last seen. Page-style names parse into both parts (`HYEON_(Kim_Seong-hyeon)` -> handle `HYEON`, real name
`Kim Seong-hyeon`) and both are searchable once the page is anchored; the rename-history rule applies to
Liquipedia-anchored entities exactly as to FACEIT ones.

Anchors arrive only through review:

```bash
python -m owcsmuse identity propose          # scope/identity_report.md from the linked series; applies nothing
python -m owcsmuse identity accept           # the strong proposals in bulk
python -m owcsmuse identity decide <page> --player <guid>     # or --new for a Liquipedia-born player
python -m owcsmuse identity reject <page> <guid> --reason "..."
python -m owcsmuse identity load             # scope/player_identity_decisions.json + the team map -> entity_anchors
python -m owcsmuse refresh --view entity_names
```

The only evidence proposed is match-level: the same handle on the same side of the same linked series (an exact or
strong, non-provisional link), which both sources name independently. One page to one GUID is `strong`; a page
matching several GUIDs, or a GUID matched by several pages, needs a person; a handle that matches no FACEIT name is
listed with what FACEIT named on that side, so a reviewer can see "Sugarfree / sug2rfree" and decide - the code
never does. Roster overlap across different series is not evidence of anything. Team-side anchors come from the
Stage 1 team map (`scope/liquipedia_team_map.json`), already reviewed.

A Liquipedia team name resolves **at the series' own time**. An entry in the team map may carry `valid_from` /
`valid_to`, or `eras` (a list of `{entity_type, entity_id, valid_from, valid_to}`) when different team ids carried
the name over time; outside every era the name is undecided at that time, never the nearest one. A name decided to a
team id keys as that id's org inside the id's window and as the id itself outside it, exactly as the fact views key
it, so "Extinction" on a 2026 page and the FACEIT team id that was Extinction in 2026 agree without a link decision.
Anchors carry the same windows (migration `029_anchor_windows.sql`), and `series` and `check` resolve against them.

### Stage 3: the source-agnostic series

A match may come from FACEIT, from Liquipedia, or from both, and is one match either way. `series` (migration
`028_series.sql`) is the one row per match that the team-grain facts (`fact_team_matches`, `fact_team_maps`) now
read, with per-field provenance: `played_at_source`, `best_of_source`, `result_source`, `maps_source`, and
`sources` (`{faceit}`, `{faceit, liquipedia}` or `{liquipedia}`). It is a plain view over `matches`,
`liquipedia_matches` and the reviewed links, so it is always current. `series_id` is `faceit:<match_id>` or
`lp:<objectname>`; `match_id` keeps the FACEIT id where there is one, so every FACEIT-keyed table still joins, and a
Liquipedia-only series is `lp:...` throughout. Evidence rows carry `sources` and a source link that is the FACEIT
room or the Liquipedia page, and an answer that used a Liquipedia-only series carries the page in its attribution.

- A reviewed link (exact or strong, not provisional, not rejected) merges a Liquipedia record into the FACEIT series
  it names. **An exact id whose records disagree on teams, score, winner, best-of, competition or finished state is
  now ambiguous, never linked** - a wrong id looks exactly like that, and a wrong link silently gives one team
  another team's result. It carries the id as its one candidate and waits for `liquipedia links decide`; a date gap
  alone (FACEIT's `result_only` times are entry times) still annotates without downgrading.
- A Liquipedia record linked to nothing is a series of its own only when **both** its teams resolve through a decided
  anchor: a team anchored to a FACEIT team id plays as that id, a team anchored to an org plays as its
  Liquipedia-born team id (`lp:team:<name>`, mapped to the org by `identity load`). An undecided team keeps the record
  out of every answer; `check` counts those (`liquipedia_unresolved_not_in_series`).
- Map grain stays FACEIT-keyed (`match_rounds`), so a Liquipedia-only series answers at series grain only, for now.
- **A tied map is nobody's win** (migration `030_draws.sql`). FACEIT counts a drawn map as a win for the series
  winner (4-0 in a best-of-5 with four maps played, one of them 3-3) and stored Dreamhack Dallas as best-of-1 with
  3-1 scores. A map is drawn when its scores are equal or no winner is recorded, a draw is excluded from map wins in
  every fact view, and the series score a series presents is corrected from its map results when FACEIT's counted a
  draw as a win (`score_source = 'maps'`; FACEIT's stored columns are untouched).
- **The map winner is derived from the scores; `winner_team_id` is advisory** (migration
  `034_map_winner_precedence.sql`). 1-3e78e269 map 5 (Suravasa, Flashpoint) is scored 0-3 for Twisted Minds and
  credits Al qadsiah as the winner; the map was really played, so nothing looked wrong, and every map record,
  map/mode win rate and head-to-head that read `winner_team_id` attributed it to the wrong team. `map_winner()`
  gives the higher score's team, nobody for equal scores (a tied map has no winner), and the stored winner only
  when a score is missing. Every fact view, `series_score` and `agg_map_modes` read it; `check`
  (`map_winner_consistency`) lists each stored winner that contradicts its scores and fails if a fact row follows one.
- **Liquipedia is the source of record for a linked series' result and best-of; FACEIT only where Liquipedia has
  nothing** (034, inverting Stage 2's rule). FACEIT keeps a fixed number of map slots per format and, when a sweep
  closes a series early, logs a default win for the winner on the next map in the rotation (the 2024 Stage 1 grand
  finals: real 4-0s stored as 5-0 with a Dorado nobody played), and it counts a drawn map as a win. Where a linked
  record orients to the FACEIT factions (decided anchors, then names, then an unlevel score, then the winner), the
  series presents Liquipedia's score, winner and best-of (`result_source`, `score_source`, `best_of_source` =
  `liquipedia`). A FACEIT map row beyond Liquipedia's game count for a linked series is a phantom (`phantom_maps`):
  out of map records, series scores, map/mode win rates and player aggregates alike, and `check`
  (`phantom_map_isolation`) counts the player rows that rode on one. Player stats stay FACEIT-only. The extent
  report is `python -m owcsmuse liquipedia phantoms` (below).
- **Best-of is derived only from real, played map wins** (034, scoping back 032's rule, which derived from any
  score and produced best-of-9 from phantom-inflated sweeps). With phantoms excluded, a series with four map wins
  is a best-of-7 whatever FACEIT stored (Al Qadsiah 1-4 Twisted Minds, stored bo5; the link is confirmed in
  `scope/liquipedia_link_decisions.json`), three a best-of-5, and never fewer than the maps played; the cap is the
  formats OWCS uses (bo1, bo3, bo5, bo7), and a derivation past bo7 is `implausible` and presented as unknown
  rather than invented. A stored best-of of 1 is junk (Dreamhack Dallas), not a value to correct from; a stored
  value is used only when no maps were recorded and it is a real format, else the best-of is `unknown`.
  `best_of_source` is `liquipedia` | `faceit` | `derived from map wins` | `implausible` | `unknown`; `check`
  (`score_plausibility`) counts each kind and lists the corrections (`best_of_corrections`).
- A link decision may be keyed `faceit:<match id>` (the report shows FACEIT ids, not objectnames); it settles the one
  record naming that id. The two drawn-map pairs are confirmed that way in `scope/liquipedia_link_decisions.json`.
- `check` gains `series_integrity`: no FACEIT id or Liquipedia record in two series, the series count reconciles
  against its sources, and a linked pair whose Liquipedia teams are decided names the same identities on both sides -
  a link that stops agreeing after an identity decision fails here rather than staying.

### Stage 3: capability, not just coverage

A source may carry a slice without carrying what a question needs from it. `region_sources` (migration
`031_capabilities.sql`) declares per region which sources cover it and whether any of them records player stats
(`korea`: `{liquipedia}`, no); `source_capabilities` derives per included championship, from `series` provenance,
whether it has series results, map results and player stats, and which sources it came from. The query layer asks
what a question needs (`player_stats`, `maps` or `series`) and checks the slice it draws on: a results-only slice
refuses a player-stat question with reason code `results_only` and the alternatives a results-only slice can answer;
a mixed slice answers and names the results-only part in a note and the `results_only_source` limitation. A
Korean team's record is answerable the moment its Liquipedia results are loaded; a Korean player leaderboard never
is, and says so by construction rather than by returning nobody.

### Phantom maps: FACEIT map rows for maps never played

FACEIT keeps a fixed number of map slots per series format and, when a sweep closes a series early, logs a default
win for the winner on the next map in the rotation (the 2024 NA and EMEA Stage 1 grand finals: real 4-0 sweeps that
FACEIT stores as 5-0 with a Dorado nobody played; Liquipedia records the 4-0). Map records, series scores and the
best-of a score implies are all inflated by such a row. `python -m owcsmuse liquipedia phantoms` (sends nothing)
writes `scope/phantom_maps.md` from stored data: every record carrying a FACEIT id where FACEIT's map count or
series score exceeds Liquipedia's, with both values and the map Liquipedia lacks; every FACEIT map row with a
placeholder shape (a win with no player rows while the match has them elsewhere, a score its mode cannot produce, no
map name); and whether those cluster on sweeps and last maps as the mechanism predicts. An exact FACEIT id whose
score a phantom inflated lands in the ambiguous tier (the records disagree on the score), so the report includes
those rather than only confirmed links. The precedence change this implies (Liquipedia as the source of record for
results and maps wherever a linked record exists) waits on that report.

### Open items for later stages

- **Stage 3, date-bounded team-to-org mapping.** A team id maps to an org for all time
  today, which over-counts across an acquisition (Virtus pro's record includes the 2024
  series of Ex Oblivione, whose roster it acquired: 5 series where 2 are its own), and
  an org's searchable names hold only each team id's current name, so "Ex Oblivione"
  finds nothing. Liquipedia identities need the same shape - a history table with
  validity dates for every renameable thing, and searchable aliases - so this is fixed
  once, there. Golden cases G11 and G13 hold it as known bugs.

## Golden answer suite

Unit tests check that code does what its author meant. The golden suite checks
that an *answer* is right: real questions asked end to end through `ask()`
against a small real warehouse, with expected values that were never produced by
the code under test. That rule exists because a test written from output encodes
the bug as correct - it is how the FACEIT nickname `KSAA0` got asserted where the
in-game name `KSAA` belonged.

- **The warehouse** is 20 real matches (`tests/golden/matches.json`, each with why
  it is there) captured verbatim from `raw_payloads` by `tools/capture_golden.py`,
  their championships' scope decisions, and the repository's own
  `scope/org_decisions.json` and `scope/alias_decisions.json`, built by
  `tests/golden_support.py`. It holds both NA and EMEA, both teams named Geekay
  Esports, both SpaceStation teams, a bracket bye and a series with no map stats,
  so each past bug has something to bite on.
- **The expected values** come from `tests/golden/independent.py`, which reads the
  raw payload JSON and imports nothing from `owcsmuse`, and are written by
  `tests/golden/derive_expected.py` into `tests/golden/cases.json` together with
  how each was derived. Nothing in either calls `ask()`.
- **Each case is labelled** `exact` (asserts numbers) or `invariant` (asserts a
  property: NA only, tank-role players only, a clarify candidate answers verbatim,
  a refusal's alternative works), and names the regression it guards.
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
  the series score, so a series with no map stats still counts in them (the `maps`
  column counts only rounds that have stats); `kd_ratio` is total Eliminations over
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

`.github/workflows/ci.yml` runs on every push and pull request. The repository is
private, so the badge above renders only for accounts with access:

| job | what it runs |
|---|---|
| `lint` | `ruff check .` - correctness rules only (`E`, `F`, `W`, `B`); line length and statement layout are deliberately not enforced |
| `offline tests` | `pytest` with no database configured, proving the parsers, classifier, limiter and query layer need neither network nor DB |
| `database tests` | `pytest -m "not golden"` against `postgres:16` **and** `postgres:17` service containers (a matrix): 17 is what Supabase runs, 16 is docker-compose and the dev default |
| `golden answers` | builds the golden warehouse and asserts the confirmed golden cases through `ask()` (see **Golden answer suite**), on both majors |
| `frontend` | `npm ci && npm test && npm run build` in `web/` - component tests against a mocked API, then a production build |
| `consistency checks` | builds a warehouse from the captured fixtures (`tools/build_fixture_db.py`) and runs `python -m owcsmuse check` against it, on both majors |

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
