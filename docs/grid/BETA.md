# OWCS Grid beta

A small, playable beta of the daily grid, built on branch `grid/beta` on 2026-11-17. It adds no migration, writes
nothing to the database, and stores nothing about visitors. Background: [AUDIT.md](AUDIT.md),
[CELL_COUNTS.md](CELL_COUNTS.md), [PLAN.md](PLAN.md).

## What it is

- A 3x3 grid. Rows are always Tank, DPS, Support. Columns are three of: 2024, 2025, 2026, NA, EMEA, "Played all 3
  seasons".
- A player answers a cell with **10 or more maps in that role inside the column**: that season, that region, or
  the whole in-scope career for "Played all 3 seasons" (which also needs a line-up in each of the three seasons).
- Scope is OWCS NA and EMEA main series. Relegation and international events are not counted.
- Nine guesses a puzzle. A player fills one cell only. Score is cells filled out of nine.
- A guess for a player with no role data in the column returns "can't verify": the cell stays open and no guess is
  spent. Any other miss spends one.
- A new puzzle at 00:00 UTC.

## How the pieces fit

| Piece | Where | Notes |
|---|---|---|
| Generator | `scripts/grid/generate_puzzles.py` | Reads the warehouse read-only. Reuses the Phase 0 `conditions.py`, `cell_counter.py` and `data.py` unchanged |
| Puzzles | `scope/grid_puzzles.json` | Every puzzle with its full answer set, written by the generator |
| Player index | `scope/grid_players.json` | Every player ever in a line-up: id, name, other names, last team, seasons. For the guess box |
| Store | `owcsmuse/grid/store.py` | Loads the two files. Standard library only |
| Routes | `owcsmuse/grid/router.py` | `/api/grid/...`, registered by one line in `create_app()` |
| Page | `web/src/grid/` | `GridPage.jsx`, `game.js` (rules and localStorage), `api.js`, `grid.css` |
| Tests | `tests/grid/test_beta.py`, `web/tests/grid.test.jsx` | offline; no database |

**The API makes no database query for Grid, at all.** Autocomplete and explanations come from the two files too.
`test_the_app_serves_grid_without_a_database_and_throttles_guesses` runs the real app factory against a database
URL nothing listens on.

Edits to existing files, all of them: the import and the `include_router` line in `owcsmuse/api.py`; the `/grid`
patterns in `web/src/router.js`; the page, the flagged nav link and one guard on the suggestions fetch in
`web/src/App.jsx`; the flag's documentation in `web/.env.example`.

### Routes

| Route | Returns |
|---|---|
| `GET /api/grid/today` | number, date, row and column labels with help text, guesses, the coverage note. No answers, no ids |
| `GET /api/grid/archive` | every published puzzle, newest first: number, date, column labels |
| `GET /api/grid/{n}` | a published puzzle, same shape as today's. 404 for a number that is not published yet |
| `GET /api/grid/players?q=` | up to 8 players matching a current or earlier name: `id`, `name`, `detail` ("Team Liquid, 2024-2025"), and `matched` when an earlier name is what matched |
| `POST /api/grid/{n}/guess` | body `{"cell": 0-8, "player_id": "..."}` where cell is row x 3 + column. `result` is `correct`, `wrong` or `cannot_verify`; `uses_guess` says whether it costs one. A correct guess carries `explanation` ("23 Tank maps in 2025 (FACEIT map stats)") |
| `GET /api/grid/{n}/reveal` | up to 5 example answers a cell, most maps first |

A wrong guess is a 200. 404 is a puzzle that is not published. 422 is a cell outside 0-8, an id not in the player
index, or a name sent where an id belongs. Guess and reveal sit behind the app's existing per-IP throttle (20
burst, 30 a minute); the other four do not, because typing in the guess box calls `/players` repeatedly.

**No Muse link on a correct answer.** Muse has no player page and no URL that pre-fills a question. A `/q/<slug>`
link resolves only after that exact question has been asked once, so building one could give a dead link. The
response carries `"link": null` and the page shows none.

## Run it locally

Two terminals. The API needs `DATABASE_URL` only because Muse's own routes do; Grid does not use it.

```bash
pip install -e ".[dev]"
python -m owcsmuse serve                                   # http://127.0.0.1:8000

cd web && npm install
VITE_API_BASE=http://127.0.0.1:8000 npm run dev            # http://localhost:5173/grid
```

`VITE_API_BASE` is needed in development: the dev server's proxy lists Muse's paths (`/ask`, `/query`, ...) and not
`/api`, and `vite.config.js` was outside what this beta was allowed to change. CORS is open, so pointing the page
straight at the API works. Add `VITE_GRID_NAV=true` to see the nav link.

`/grid` shows "no puzzle for today yet" until the first puzzle's date (2026-11-18 UTC). To play before then, copy
`scope/grid_puzzles.json` and `scope/grid_players.json` into `<some dir>/scope/`, move the dates back in the copy,
and start the API from `<some dir>`: the files are read relative to the working directory. That is how the smoke
test below was run. Do not edit dates in the real file.

Tests:

```bash
pytest tests/grid -q          # 35 tests, under a second
pytest -q                     # the whole offline suite
cd web && npm test && npm run build
```

## Generate more puzzles

```bash
python scripts/grid/generate_puzzles.py --start-date 2026-12-02 --days 14
python scripts/grid/generate_puzzles.py --start-date 2026-12-02 --days 14 --dry-run     # report only
python scripts/grid/generate_puzzles.py --start-date 2026-11-25 --replace-future        # redo unpublished ones
```

- `--seed` defaults to the start date as a number; the same seed and data give the same puzzles.
- It prints the nine counts of every puzzle and writes the same report, with every rejected candidate and why, to
  `docs/grid/runs/generate_<start>_<days>d_seed<seed>.txt`.
- A candidate is rejected if any cell has under 5 answers, if nine different players cannot fill the grid, or if
  its three columns were used in the previous 7 days.
- **Published puzzles are immutable.** A start date of today or earlier (UTC) is refused, with exit code 2 and
  nothing written. A future date already in the file is left alone and new dates are appended after the last one.
  `--replace-future` regenerates from the start date on and still cannot reach a published date.
- It regenerates `scope/grid_players.json` each run, so new players become guessable.
- Commit both files. They reach production with the next deploy: the image copies `scope/`.

The database is read on one connection that cannot write (`scripts/grid/db.py`): nine SELECTs, rolled back.
Before generating, check that the nightly ingest has run recently; a puzzle is a snapshot of the warehouse at
generation, and each entry records the last series date it saw.

**The supply is 14 puzzles, 2026-11-18 to 2026-12-01.** Nothing generates more automatically. On 2026-12-02 `/grid`
will say there is no puzzle unless more have been generated, committed and deployed.

## Deploy it hidden, and share the link

1. Merge `grid/beta` to `main`. CI runs; `deploy.yml` deploys the API to Fly. There is no migration, so
   `release_command` finds nothing to apply. Vercel builds the frontend from the same merge.
2. Leave `VITE_GRID_NAV` unset in Vercel. The masthead shows no link to Grid, and nothing else on Muse changes.
3. Share `https://owcsmuse.vercel.app/grid` directly. `/grid/<n>` opens a specific puzzle; `/grid/archive` lists
   them. `web/vercel.json` already rewrites every path to the app.
4. To show the nav link later: set `VITE_GRID_NAV=true` (exactly that string) in Vercel for Production and
   redeploy. It is read at build time.
5. To take Grid away: remove the two `scope/grid_*.json` files and deploy. Every Grid route then answers 404 or an
   empty list and the page says there is no puzzle.

Check after deploying: `curl https://owcsmuse-api.fly.dev/api/grid/today` returns the puzzle (or a 404 naming
today's date before 2026-11-18), and the response contains no `answers`.

## Known limitations

- **The guess limit and the one-cell-per-player rule are enforced in the browser only.** The server is stateless:
  it checks one player against one cell and remembers nothing. Clearing site data resets a game. Acceptable while
  there is no leaderboard and nothing to win.
- **The reveal endpoint works at any time.** The page calls it only after a game ends, but anyone can request it
  for today's puzzle and see up to five answers a cell. It never returns a full set.
- **A cell can be enumerated** by guessing every player. The throttle makes that 30 guesses a minute per IP.
- **The answers are in the repository**, in `scope/grid_puzzles.json`, including future puzzles. Anyone who can
  read the repo can read them. If the repository becomes public, move the file out or generate later.
- **Roles are missing for part of the scope.** There is role data for 2024 Stages 1-2, 2025 Stages 1-3 and 2026
  Stages 1-2 only. Per column, the players who return "can't verify": 159 for 2024, 61 for 2025, 66 for 2026, 54
  for NA, 44 for EMEA, 16 for "Played all 3 seasons". Most of the 2024 ones played Stages 3-4.
- **"Can't verify" means no role data at all in the column.** A player with some role data there is judged on it.
  Someone with 8 Tank maps in 2026 Stages 1-2 who also played Tank in Stage 3, where no roles exist, is "wrong",
  not "can't verify".
- **A line-up is not proof of playing** for Liquipedia-only series, which list the roster. This affects only
  "Played all 3 seasons" and who counts as "seen" for can't-verify. Role maps are FACEIT's per-map record.
- **No link from an answer to Muse** (above).
- **No streak across devices**, and private windows or in-app browsers that block storage play without saving.
- **The end-screen examples show names as they were at generation.** A filled cell and the guess box show the
  name in the current player index.
- **Columns repeat.** Six columns give 20 sets; consecutive days often share two columns.
- **Nothing was verified by hand.** The answer sets are what the warehouse says. The three golden cells proposed in
  CELL_COUNTS.md are still unconfirmed, and they were drawn at a 4-map floor, not this beta's 10.
- **Not checked here:** the Docker image build (Docker was not running; CI's `API image` job builds it), and real
  phones. The page was driven in a desktop browser at 360 and 390 px wide.

## What Phase 2 would add

- **Aggregate guess counts** in a `grid_guess_counts` table (puzzle, cell, player, count). The first schema
  change, and still nothing about a visitor.
- **Rarity scoring** from those counts, once there is enough play for a percentage to mean something.
- **Puzzles in a table with an immutability trigger**, published by a step after the nightly `check`, a week ahead
  (PLAN.md section 2). That removes the answers from the repository and the manual generate-commit-deploy.
- **A server-side guess budget**, if leaderboards ever need one. It requires a per-player token, which changes
  Muse's "nothing about the asker" stance and is a decision of its own.
- **Team clues** ("played for X"), once the unmapped team ids that matter are mapped to orgs (AUDIT.md, issue 8).
- **The Dreamhack Dallas line-up fix**: read Liquipedia's line-up for linked result-only series. It changes Muse's
  own answers, so it needs its own review and golden cases.
- **A role source for the gaps**: a reviewed per-season role from Liquipedia player pages, to shrink "can't
  verify".
- **A real Muse link** per answer: a player page, or a pre-filled question URL.
- **`/api` in the dev proxy**, one line in `vite.config.js`.

## Smoke test, 2026-11-17

Run against the real API code and the real generated data, with the puzzle dates moved back two days in a scratch
copy so that puzzle 2 (EMEA / Played all 3 seasons / 2025) was "today". Transcript:
[runs/smoke_2026-11-17.txt](runs/smoke_2026-11-17.txt).

| Step | Result |
|---|---|
| `GET /today` | puzzle 2, no answer data |
| Tank x EMEA, TVNT | `correct`: "107 Tank maps in EMEA (FACEIT map stats)" |
| Tank x EMEA, sugarfree | `wrong`, one guess spent |
| Tank x 2025, MER1T | `cannot_verify`, no guess spent |
| Support x 2025, searched as "zss" | found ZZZ by an earlier name; `correct`, 80 Support maps |
| cell 9 | 422 |
| puzzle 3 (tomorrow's) | 404 |
| `GET /reveal` | 5 examples in every cell |
| In the browser at 390 px | played the same guesses through the page; progress survived a reload; end screen showed 2/9, the examples and the share text; archive listed both puzzles with the score |
| Share text | `OWCS Grid #2  2/9`, three rows of squares, the `/grid/2` link, no names |
| Before any puzzle's date (the real file) | `/today` 404 "no puzzle is published for 2026-11-17", archive empty |
