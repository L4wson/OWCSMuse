# Ingest

Pulling FACEIT data into the warehouse: the backfill and its two resumable phases. Liquipedia's fetch is in
[liquipedia.md](liquipedia.md); the nightly run is in [deployment.md](deployment.md).

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
   writes `scope/classification_report.md` (see **[Scope](scope.md#scope)** below).

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

6. **Load** the reviewed manifest:

   ```bash
   python -m owcsmuse load-manifest manifest.json                    # manual decisions only
   python -m owcsmuse load-manifest manifest.json --accept-proposals # also the classifier's proposals
   python -m owcsmuse check-listings                                 # read-only: sizes + offset-cap check
   ```

7. **Collect**:

   ```bash
   python -m owcsmuse backfill                 # LIST then DETAIL for every included championship
   python -m owcsmuse list --championship ID   # LIST only, one championship
   python -m owcsmuse detail --limit 200       # DETAIL only, at most 200 matches this run
   python -m owcsmuse status                   # progress per state and championship
   ```

   Interrupt at any time. `detail` picks up matches still in `stub` /
   `detail_fetched`; `--include-failed` retries `failed` ones; `--refresh`
   re-fetches everything. Re-running never duplicates rows.

8. **Reprocess** after a parser change, without touching FACEIT:

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
