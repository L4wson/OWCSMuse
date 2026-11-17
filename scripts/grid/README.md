# Grid cell counter (Phase 0)

A read-only prototype that answers one question: for a candidate 3x3 grid, how many valid canonical answers does
each cell have? It is not the game and it is not the generator. It exists to decide which grid formats the
warehouse can support. Results from the Phase 0 run are in [docs/grid/CELL_COUNTS.md](../../docs/grid/CELL_COUNTS.md).

## Running it

From the repository root, with `DATABASE_URL` set as Muse reads it (`.env` or the environment):

```bash
python scripts/grid/cell_counter.py scripts/grid/grids/role_x_season.json
python scripts/grid/cell_counter.py scripts/grid/grids/role_x_season.json --min-maps 10
python scripts/grid/cell_counter.py scripts/grid/grids/role_x_season.json --full 0,2      # every answer of cell [0,2]
python scripts/grid/cell_counter.py scripts/grid/grids/role_x_season.json --json          # every cell's full answer set
python scripts/grid/cell_counter.py --top-orgs 12                                         # org keys to build grids from
python scripts/grid/cell_counter.py --entity team \
    --rows region:na region:emea region:international --cols season:2024 season:2025 season:2026
```

It needs the `owcsmuse` package importable (`pip install -e .`) for `Settings` only. Exit code 2 means a condition
was refused (an unknown org key, a per-10 condition on a season with no Time Played).

| option | meaning |
|---|---|
| `--min-maps N` | maps a player needs for a role or stat cell. Default 4, Muse's leaderboard floor |
| `--min-series N` | series needed for a series-grain cell. Default 1 |
| `--samples N` | sample answers printed per cell. Default 10 |
| `--full R,C` | print every answer of one cell; repeatable |
| `--json` | every cell's full answer set, for diffing or building golden cases |

## It cannot write

`db.py` opens one connection with psycopg's `read_only` flag and `default_transaction_read_only = on`, then asks the
server to confirm before any query runs. The whole run is seven SELECTs (`data.py`), each followed by a rollback.
It was run against production Supabase in Phase 0 because no local database was available. A local copy is
preferable when there is one: point `DATABASE_URL` at it.

## What a count means

Every answer is a canonical id: a `player_id`, or an `org_key` (a reviewed org id, or `team:<id>` for a team id no
org decision covers). Names are labels only. An org is named on the command line by its key and a name is refused.

A team id becomes an `org_key` through `team_identity_at(team_id, <the series' own time>)`, the function Muse's own
fact views use. A recycled or acquired FACEIT team id therefore counts for whoever held it that day.

Two grains, chosen per cell:

- **Series grain** (`series_lineups`): who was in a series' line-up. FACEIT's declared line-up, or Liquipedia's for
  a Liquipedia-only series. Covers every series in scope. Used when neither condition needs a role or a stat.
- **Map grain** (`fact_player_maps`): who played a map, in which role, with which stats. Exists only where FACEIT
  recorded map stats. Used whenever a cell has a role or stat condition, with the `--min-maps` floor. Each such
  cell prints a `coverage:` line naming the competitions of its slice that have no player stats, because the count
  cannot see them.

Two ways a cell combines its conditions:

- **Same rows.** Row conditions of different dimensions (role, season, org, competition) must hold on the same
  series or map. "Tank x 2024" is a player with at least `--min-maps` maps played as Tank in 2024. A player who was
  a Tank in 2025 and a Support in 2024 is not an answer.
- **Own rows.** Two conditions of the same dimension ("played for A" x "played for B", or a region x an event), and
  any condition that states its own scope (`min_orgs`, `per10_*`, `placed_top`, `beat`), are each evaluated on
  their own and intersected.

The `overlap` block at the end says how samey the grid is: how many distinct answers exist, whether all nine cells
can be filled without reusing an answer, and which answers fit the most cells.

## Condition specs

| spec | entity | condition |
|---|---|---|
| `season:2025` | both | has a series (or maps) in that season |
| `region:na` / `emea` / `international` | both | has a series in a competition of that region. The region of the competition, not a home region |
| `event:World Finals` | both | competed in a competition whose reviewed name contains every word given. Several may match ("World Finals" is 2024 and 2025) |
| `role:tank` / `dps` / `support` | player | maps played in that role (FACEIT's per-map value) |
| `org:<org_key>` | player | was in a line-up of that identity |
| `min_orgs:3`, `min_seasons:3` | player | career counts over line-ups |
| `per10_min:<stat>:<value>:<season>:<role>` | player | stat per 10 minutes at or above a value, in that role and season |
| `per10_max:<stat>:<value>:<season>:<role>` | player | at or below |
| `per10_top:<stat>:<n>:<season>:<role>` | player | the top n by stat per 10 in that role and season. A tie at the cutoff is included |
| `placed_top:8` or `placed_top:8:2025` | team | finished in the top n at an international event (Liquipedia placings) |
| `beat:<org_key>` | team | won a series against that identity |

Stats are `eliminations`, `deaths`, `damage_dealt`, `healing_done` and `damage_mitigated`. A per-10 rate is total
stat over total Time Played across the maps counted, never an average of per-map rates. 2024 has no Time Played, so
a per-10 condition on 2024 is refused.

A grid file is `{"name": ..., "entity": "player" | "team", "rows": [3 specs], "cols": [3 specs]}`. The candidate
grids from Phase 0 are in `grids/`.

## The puzzle generator

`generate_puzzles.py` builds the daily puzzles the site serves:

```bash
python scripts/grid/build_facts.py                                                # stage results, awards, anchors -> scope/
python scripts/grid/generate_puzzles.py --start-date 2026-12-22 --days 14         # mixed-clue puzzles
python scripts/grid/generate_puzzles.py --start-date 2026-12-22 --days 14 --dry-run
python scripts/grid/generate_puzzles.py --start-date 2026-12-22 --days 14 --classic    # the first beta's role x column grids
```

It writes `scope/grid_puzzles.json` and `scope/grid_players.json`, and a report under `docs/grid/runs/`. A date that
is today or earlier (UTC) is refused.

- **Mixed puzzles** (the default) are six clues from at least four families. The clue types are the classes in
  `clues.py`: each returns its answers with a reason apiece, the players it cannot judge, a short label and a
  one-line definition. `mixed.py` holds the clue pool, the rules a grid must pass, and the search.
- **Classic puzzles** (`--classic`) use the Phase 0 conditions in `conditions.py` through `cell_counter.py`,
  unchanged: Tank / DPS / Support against three of 2024, 2025, 2026, NA, EMEA and "Played all 3 seasons".
- `build_facts.py` derives what Muse's database does not hold as a column, stage winners and individual awards,
  into `scope/grid_stages.json` and `scope/grid_awards.json`, each entry with a source link, and the candidate
  "Teammate of" anchors into `scope/grid_anchors.json`. It keeps `reviewed` and `approved` flags already set. The
  generator names approved anchors only.
- `--rebuild-all` discards every puzzle and starts again, today included. It is only for a file no visitor has
  been served.

What every clue means and how the API and page use the files: [docs/grid/CATEGORIES.md](../../docs/grid/CATEGORIES.md)
and [docs/grid/BETA.md](../../docs/grid/BETA.md).

## Files

| file | what |
|---|---|
| `db.py` | the read-only connection |
| `data.py` | the four fact sets and the seven SELECTs that load them |
| `conditions.py` | the condition classes and `cell_answers()` |
| `cell_counter.py` | spec parsing, the report, the CLI |
| `grids/*.json` | candidate grids |
| `generate_puzzles.py` | the puzzle generator: mixed clues by default, `--classic` for role grids |
| `clues.py` | the mixed-clue types |
| `mixed.py` | the clue pool, the quality rules, the day search |
| `build_facts.py` | stage results and awards into `scope/` |
| `../../tests/grid/test_conditions.py` | the semantics above on a hand-built warehouse; no database |
| `../../tests/grid/test_beta.py`, `test_categories.py` | the generator, every clue type, every rule, both puzzle formats through the routes |

## Known limits

- Conditions are a closed list on purpose. Adding one is a class of about fifteen lines, not a configuration.
- Everything is loaded into memory (about 9,000 line-up rows and 15,000 map rows). Fine for a prototype; the real
  generator can do the same thing and snapshot the result.
- It reads line-ups exactly as Muse's `series_lineups` view defines them, so it inherits that view's gaps. See
  "Data-quality issues" in [docs/grid/AUDIT.md](../../docs/grid/AUDIT.md).
