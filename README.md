# OWCS Muse

[![CI](https://github.com/L4wson/OWCSMuse/actions/workflows/ci.yml/badge.svg)](https://github.com/L4wson/OWCSMuse/actions/workflows/ci.yml)

Ask a question about the Overwatch Champions Series (OWCS) in plain English, such as "Toronto Defiant record",
"sugarfree map record against zeruhh" or "who won the 2025 world finals", and get a sentence back along with the rows
behind it. It covers OWCS North America and EMEA from 2024, plus the international events.

**Live:** [owcsmuse.vercel.app](https://owcsmuse.vercel.app) (API: `https://owcsmuse-api.fly.dev`)

Match data comes from the FACEIT Data API v4 and from Liquipedia. It lands in a Postgres warehouse, and every
response is stored verbatim so parsing can be redone offline. Nothing queries FACEIT or Liquipedia at request time:
a nightly ingest updates the warehouse, and the API answers from the warehouse alone.

## Stack

- **Python 3.11+** with `httpx`, `psycopg`, `pydantic-settings` and plain SQL migrations (no ORM). `fastapi` serves
  the HTTP layer, and `pytest` runs the tests.
- **Postgres 17** (Supabase in production; CI also runs 16).
- **Vite + React** frontend in `web/`, with plain CSS and no UI framework.
- **Hosting:** the API on Fly.io, the frontend on Vercel, ingest on GitHub Actions.

## Local setup

```bash
python -m venv .venv && . .venv/Scripts/activate    # or source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                                  # put FACEIT_API_KEY in .env
docker compose up -d db                               # local Postgres 17 on :5432 (optional)
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

A new database is empty. [docs/ingest.md](docs/ingest.md) covers filling it from FACEIT, and
[docs/liquipedia.md](docs/liquipedia.md) covers adding Liquipedia. Then:

```bash
python -m owcsmuse ask "Toronto Defiant record"   # one answer in the terminal
python -m owcsmuse serve                          # the API, on :8000
cd web && npm install && npm run dev              # the app, on :5173, proxying to it
pytest                                            # OWCS_TEST_DATABASE_URL=... adds the database and golden suites
```

## Documentation

[docs/](docs/README.md) has the rest. Start with [docs/conventions.md](docs/conventions.md), which covers what the
data means and the rules learned from wrong answers. The other documents cover identity, scope decisions, the schema
and migrations, how questions are answered, the API, the checks and tests, the deployment runbook, and the open items.

## Data sources and attribution

- **FACEIT.** Match, roster and player statistics come from the
  [FACEIT Data API](https://developers.faceit.com). OWCS Muse is not affiliated with or endorsed by FACEIT.
- **Liquipedia.** Results, maps, line-ups, schedules and placings that FACEIT lacks come from the
  [Liquipedia Overwatch wiki](https://liquipedia.net/overwatch/) through the LiquipediaDB API. Liquipedia content is
  licensed under [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Every answer that uses a
  Liquipedia value carries the licence and the URL of each page it came from (`attribution`), and the app shows them
  with the answer.

**2026 Stage 3 comes from Liquipedia alone.** FACEIT appears to have stopped running the stage now in progress: since
its first weekend (2026-10-10), the rooms for NA and EMEA Stage 3 are configured and then aborted minutes later with no
result, so FACEIT holds nothing about those series. Liquipedia is the only source for them, the regional playoffs (October 30 - November 1)
included: results and maps, no player statistics. A result FACEIT enters later is picked up on the next nightly run
([docs/liquipedia.md](docs/liquipedia.md#2026-stage-3-faceit-rooms-with-no-result-2026-10-23)).

Overwatch is a trademark of Blizzard Entertainment. This project is not affiliated with or endorsed by Blizzard
Entertainment.

## License

[MIT](LICENSE). The MIT license covers the code. Data from FACEIT and Liquipedia stays under its sources' terms.
