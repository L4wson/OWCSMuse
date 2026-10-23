# Answering questions

The aggregation layer, how a question becomes a query, and versus records at both grains.

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

**The leaderboard map floor.** A player leaderboard that a small sample can
win (an ascending total, a per-map average or a rate such as K/D) ranks only
players with at least `LEADERBOARD_MIN_MAPS` = 4 maps (`nlq/compile.py`), and
its sentence says so: "(players with at least 4 maps)". Some players genuinely
get little playing time and should still rank; the floor is there for a
manager or coach filling in for one series. Danny played 1 map (2024 and
2025), K0RTAL 3 (one 2024 series), and at no floor Spectra "had the least
deaths in NA 2024" with 1 death in 1 map. A fill-in lasts as long as the one
series played, 1-3 maps, so the floor is 4; on production (2026-10-08) it
leaves out 32 of 513 player-seasons, among them every player whose season was
one 3-map series. A descending total takes no floor, since few maps cannot top
it, and an explicit "with at least N maps" replaces it.

**Relative periods.** "this year" / "this season", "last year" / "last season",
"this stage" and "last stage" are read against the data, never the calendar
(`resolve_period` in `nlq/validate.py`), and the answer's first note says what
they were read as: "'this stage' is read as OWCS 2026 Stage 2 (EMEA and NA), the
most recent stage in scope, played 2026-05-25 to 2026-07-06."

- The current season is the most recent season with series in scope; last
  season the one before it with series.
- A stage is every championship whose OWCS name says "Stage N" in a season
  (regular season, playoffs and relegation alike); the current stage is the
  latest (season, N) with series, in the asked region when there is one. NA and
  EMEA run side by side, so without a region it is both.
- **Between stages** (no stage running, as on 2026-10-08, three months after
  Stage 2's playoffs) "this stage" is the stage just finished; the note's dates
  show it is over. In January, before a season's first series, "this year" is
  still the last season played, and the note names it.
- A year given as well ("this stage in 2025") picks the period within that
  year. A period with nothing to read ("last stage" with one stage in scope) is
  `no_data`, never every season.

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

Every combination answers at both grains:

| | series grain ("X series record against Y") | map grain ("X vs Y", "X map record against Y") |
|---|---|---|
| player v player | the series they were on opposite sides of | the maps they played against each other |
| player v org, org v player | the series the player was on the side opposite the org | the maps the player played against the org, from the first-named side |
| org v org | series between the two orgs | maps between the two orgs |

**A player's series record** (migration `042_series_lineups.sql`): players do not win series, their teams do, so it
counts the series the two were on opposite sides of and scores each from the first-named side's team. Sides come from
`series_lineups`: FACEIT's declared line-up (a substitute only when he played a map), and Liquipedia's line-up for a
Liquipedia-only series through a reviewed player identity. The answer says so in a note. A player and his own team,
or two players only ever on one line-up, is refused as that ("sugarfree played for SpaceStation Gaming in 2026 (20
series), never against them"), never as "they met".

**Both grains from either answer:** a versus or series-record answer (and its refusal) carries `other_grain`, the same
two sides, season and event at the other grain, and the frontend shows it as a "Series record | Map record" toggle.

**A player's map record counts every played map** (migration `045_every_played_map.sql`). Before 045, "sugarfree map
record against zeruhh" said 22-20 in 42 maps, while the series record said 29-21 in maps (50). The map grain counted
only maps FACEIT returned player stats for. `fact_player_map_results` holds one row per player per played map:

- for a map with player rows, who actually played it, with stats;
- for a map without, the series' declared line-up on that map's side, with no stats.

Maps without player rows are results-only on FACEIT, Liquipedia-enriched, Liquipedia-only, or dropped by FACEIT's
`/stats`. `fact_player_versus` pairs those rows. Stat answers still read `fact_player_maps` only, so a leaderboard
never averages over a map with no stats.

**Maps FACEIT's `/stats` dropped.** In 9 of 409 complete series, `/stats` left out a map whose winner and score the
match's own `detailed_results` still records. `liquipedia enrich` recovers such a map, as `match_rounds.source =
'faceit_results'`, only where Liquipedia's record of the series has the same map at that position with the same winner.
Seven are recovered. The other two entries are not games: a 0-0 "map 6" in Twisted Minds v ENCE, and the phantom 1-0
"Dorado" in Toronto Defiant v Timeless (FACEIT 5-0, Liquipedia 4-0). A score rule alone would have counted that one.
`maps_played` then follows the stored rounds. The consistency check `dropped_stats_maps` fails on any `detailed_results`
map that is neither a stored round nor past the end of Liquipedia's game list.

A series with no map results contributes no map rows, so it cannot deflate a record unnoticed: the answer counts such
series separately and says how many, and how many maps by series score, are excluded. That now means the same thing for
every pairing: no source has the maps (FACEIT's rounds or, since 041, Liquipedia's games). An empty result
distinguishes "never met" from "met, but no map results".

Golden G93/G94 pin one pairing at both grains: sug2rfree v zeruhh, 11 series, 7-4, 29-21 in 50 maps. They run in a
warehouse of their own (`tests/golden/pairs`), so the main golden set's confirmed values do not move.
