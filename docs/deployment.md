# Deployment runbook

Where each piece runs, which secret lives where, and the order to bring it up.

## Deploying

Three parts, none of which share a host requirement: the **API** (a stateless container, on Fly.io), the **frontend**
(static files, on Vercel), and **ingest** (a daily GitHub Actions run). Only ingest talks to FACEIT or Liquipedia; the API answers from
the warehouse alone.

### What lives where

| setting | where it is set | used by |
|---|---|---|
| `DATABASE_URL` (Supabase **session** pooler, port 5432) | Fly secret; GitHub Actions secret | API, ingest, `migrate` |
| `FACEIT_API_KEY` | GitHub Actions secret only | ingest (`backfill`, `crawl`, `discover`) |
| `LIQUIPEDIA_API_KEY` | GitHub Actions secret only | ingest (`liquipedia run`); `OWCS_LIQUIPEDIA_ENABLED=1` is set by the workflow |
| `VITE_API_BASE` (the API's public URL) | Vercel project environment variable (used at **build** time) | the frontend bundle (baked in at build time; see `web/.env.example`) |
| `PORT` | `fly.toml` `[env]`, `8000` | the container listens on it; must equal `internal_port` |

The API never needs `FACEIT_API_KEY` or `LIQUIPEDIA_API_KEY`: `serve` reads neither (the FACEIT key is demanded
only by ingest commands, and no Liquipedia request is possible without `OWCS_LIQUIPEDIA_ENABLED`). Keep them in
GitHub Actions secrets only. The image also lacks the `anthropic` package, so `parser: "auto"` answers with the rules
parser and `parser: "llm"` is refused; no `ANTHROPIC_API_KEY` is needed either.

### The pieces in the repository

- **`Dockerfile`**: the API image. Multi-stage (the package and its `api` extra are built in a venv, and only that venv,
  `migrations/` and `scope/` reach the runtime image), runs as the non-root user `owcs`, carries no tests or dev tools
  and never a `.env` (`.dockerignore`). `HEALTHCHECK` hits `/healthz`, which is liveness plus a database round trip:
  503 when Postgres is unreachable. 252 MB on `python:3.12-slim` (2026-10-08). CI's `API image` job builds it and
  checks the user and the absence of pytest and ruff.
- **`docker-compose.yml`**: local development, the API image plus `postgres:17` (production's major). `docker compose
  up -d --build` migrates and serves on `localhost:8000` (`OWCS_API_PORT` moves it, `OWCS_DB_SCHEMA` picks the
  schema).
- **`.github/workflows/ingest.yml`**: nightly at 22:35 Pacific and on demand (two crons, 05:35 and 06:35 UTC, and a
  first job that lets only the one landing at 22:35 local time through, so daylight saving moves nothing). `backfill` -> `crawl seed --from-rosters` +
  `crawl run` -> `liquipedia run --execute` -> `liquipedia reconcile --decided-only` -> `liquipedia enrich` -> `refresh`
  -> `check`. `enrich` alone sends nothing and adds nothing new: it uses Liquipedia records already fetched and
  linked, so the fetch and the reconcile come first, and `--decided-only` keeps unreviewed team-name proposals out of
  an unattended run. A failed step or a failing `check` fails the run with an error annotation, the check output in
  the run summary, and one open issue ("Scheduled ingest failed", commented on by each later failure).
  **New competitions are a report, never an inclusion**: `discover --no-db` and `crawl competitions` run read-only
  after the gate (even when it failed), and `tools/scope_report.py` lists every competition the classifier would
  include that has no reviewed decision, as a table in the run summary and a warning annotation each. Only
  `python -m owcsmuse decide` puts a competition in scope. The reports are the run's `ingest-reports` artifact.
- **`fly.toml`**: the API on Fly.io. One `shared-cpu-1x` machine (512 MB) in `sea` (Seattle, nearest Supabase
  `us-west-2`), `auto_stop_machines = "off"` and `min_machines_running = 1` so it never cold starts, `PORT=8000`
  matching `internal_port = 8000`, an HTTP check on `/healthz`, and `python -m owcsmuse migrate` as the
  `release_command` (run with the app's secrets before each deploy replaces the machine).
- **`web/vercel.json`**: the frontend on Vercel (project root `web`). Vite preset, `npm ci`, `npm run build`, output
  `dist`, and one rewrite, `/(.*)` -> `/index.html`. Vercel serves a file that exists in `dist` (`index.html`,
  `assets/*`) before it applies rewrites, so only paths with no file, such as a shared `/q/<slug>` link, get the app,
  whose router reads the slug. It is a rewrite (status 200, URL unchanged), not a redirect.
- **Vercel Web Analytics and Speed Insights** (`@vercel/analytics`, `@vercel/speed-insights`, mounted in
  `web/src/main.jsx`). Each loads its script from the deployment's own `/_vercel/insights` and
  `/_vercel/speed-insights` paths, which Vercel serves ahead of the rewrite above, so they report only from a Vercel
  deployment with Analytics and Speed Insights enabled in the project's dashboard. In `npm run dev`, the tests and any
  other host they send nothing.

### In order

Steps marked **[browser]** need an account or a web console; **[command]** steps run in a terminal.

1. **[browser] Supabase.** Copy the session-pooler connection string (port 5432, not the 6543 transaction pooler:
   the CLI and API pin `search_path`). Decide on Row Level Security or revoke the Data API grants on these tables (see
   **[Supabase notes](schema-and-migrations.md#supabase-notes)**): a public API makes the project easier to find, and the Data API is open with RLS off.
2. **[command] Migrate production** before the first deploy, and on every deploy after (the host's release command):
   `python -m owcsmuse migrate`. It is idempotent and loads the reviewed competition names; `python -m owcsmuse check`
   should then pass every check.
3. **[command] API on Fly.** See **First Fly deploy** below. Each process keeps up to four idle connections: size
   machines x 4 against the pooler's limit before scaling out.
4. **[command] Check the API**: `curl https://<api>/healthz` returns `{"ok": true, ...}`, and
   `curl -X POST https://<api>/ask -H 'content-type: application/json' -d '{"question": "Toronto Defiant record"}'`
   answers.
5. **[browser] Vercel.** Import the repository, set **Root Directory** to `web` (build settings then come from
   `web/vercel.json`), and add the environment variable `VITE_API_BASE=https://owcsmuse-api.fly.dev` (no trailing
   slash) for Production and Preview. It is baked in at build time: changing it needs a redeploy. CORS needs no
   change for the Vercel URL: `owcsmuse/api.py` (`create_app`, the `CORSMiddleware` line) allows every origin, which
   also covers Vercel's per-commit preview URLs. The API is read-only and uses no cookies or credentials, so that is
   deliberate; to restrict it, replace `allow_origins=["*"]` there with the production origin (e.g.
   `["https://<project>.vercel.app"]`) and rebuild, accepting that preview deployments are then refused.
6. **[command] Check the frontend**: ask a question, then open its shared `/q/<slug>` link in a fresh tab: it must load
   the answer, not a 404.
7. **[browser] GitHub.** Add the three Actions secrets (`DATABASE_URL`, `FACEIT_API_KEY`, `LIQUIPEDIA_API_KEY`) under
   Settings > Secrets and variables > Actions, and make sure Actions are enabled for scheduled runs.
8. **[command] First ingest by hand**: `gh workflow run ingest.yml`, then `gh run watch`. Read the run summary's
   "Competitions awaiting a scope decision" table; decide each with `python -m owcsmuse decide` and commit the
   decisions file.

### Deploying on merge

`.github/workflows/deploy.yml` deploys the API to Fly after **CI passes on a push to `main`**: it is triggered by
the CI workflow finishing (`workflow_run`), runs only when that run succeeded and was a push, and deploys exactly the
commit CI tested. Pull requests never deploy; one deploy runs at a time.

- **Secret:** `FLY_API_TOKEN` (repository secret). Generate a deploy token scoped to the app with
  `fly tokens create deploy -a owcsmuse-api` (optionally `-x 8760h` for a one-year expiry), then
  `gh secret set FLY_API_TOKEN` and paste it, or add it under Settings > Secrets and variables > Actions.
- **Migrations run first.** `fly.toml`'s `release_command` (`python -m owcsmuse migrate`) runs in a temporary machine
  from the new image, with the app's secrets, before any machine is replaced. If it exits non-zero, Fly stops the
  deploy: the running machine keeps serving the previous version, and the workflow fails.
- **A migration failing mid-deploy:** each migration file is its own transaction (`owcsmuse.db.migrate`), so the
  failing file leaves no trace; files applied before it in the same run stay applied and recorded, and the old code
  keeps serving against them. A fix is a new commit; the next deploy resumes from the failed file.
- **So a merge now changes production's schema unattended.** Write migrations expand-then-contract: the version still
  serving must work against the new schema until its machine is replaced (`CREATE OR REPLACE VIEW` with the same
  columns, new tables and columns), and anything destructive (`DROP ... CASCADE`, dropping a column the running code
  reads) belongs in a later migration, after the code that stopped reading it has shipped. A `DROP ... CASCADE` drops
  every dependent object without saying so: check `pg_depend` first (041's drop of `agg_map_modes` has none).
  `release_command` times out after 5 minutes by default; a slow materialized view belongs in `refresh`, not a
  migration.
- **Data is not part of a deploy.** Loaders (`orgs load`, `identity load`, `liquipedia events load`,
  `liquipedia reconcile`, `liquipedia placements load`) and `refresh` do not run on deploy; the daily ingest runs
  `liquipedia reconcile` and `refresh`, or run them by hand. A migration whose new table is filled by a loader (041's
  `liquipedia_rounds`, filled by `liquipedia reconcile`) is empty until then, which degrades to the previous answers,
  never wrong ones.
- **Images.** CI pulls its three images (`postgres:16`, `postgres:17`, `python:3.12-slim`) from this repository's GHCR
  mirror, `ghcr.io/l4wson/owcsmuse/*`, with the job's own `GITHUB_TOKEN`. `.github/workflows/mirror-images.yml` copies
  them from upstream weekly, on demand, and when that file changes. Anonymous pulls are metered per IP and shared runners
  share a hot pool of IPs: Docker Hub's limit failed CI on 2026-10-09, and ECR Public's "Data limit exceeded" failed
  most runs on 2026-10-23. The Dockerfile's base is `ARG BASE_IMAGE`, ECR Public's copy by default, which Fly's builder
  and `docker compose` pull; CI passes the mirror. A new image for CI is added to the mirror's matrix first, and CI
  pulls it from the next commit on. Before the repository goes public, or once it is, make the three packages public
  (each package's settings on GitHub): a pull request from a fork gets no access to a private package.

### First Fly deploy

Run from the repository root with [`flyctl`](https://fly.io/docs/flyctl/install/) installed. `fly.toml` is already
committed, so create the app rather than `fly launch` (which would rewrite it); if `owcsmuse-api` is taken, pick
another name and change `app` in `fly.toml` and `VITE_API_BASE` to match.

```bash
fly auth login
fly apps create owcsmuse-api
fly secrets set --stage DATABASE_URL='postgresql://...'   # the Supabase session pooler string; --stage: no machine yet
fly deploy --ha=false        # one machine: without --ha=false a first deploy creates two
fly status                   # one machine in sea, state started, check passing
fly checks list              # the /healthz check
fly logs                     # streams JSON logs; the release_command's migrate output appears first
curl https://owcsmuse-api.fly.dev/healthz
```

Later deploys are `fly deploy` (the release command migrates first; a failed migrate aborts the deploy and leaves the
running machine alone). `fly secrets set` without `--stage` restarts the machine with the new value. `fly ssh console`
opens a shell in the running machine, e.g. for `python -m owcsmuse check`. Set no `FACEIT_API_KEY` or
`LIQUIPEDIA_API_KEY` here: `fly secrets list` should show `DATABASE_URL` alone.

Every ingest phase is resumable and idempotent, so a failed run is re-run rather than repaired. Daily is ample; OWCS
plays on weekends. What the schedule deliberately never does: put a newly discovered competition in scope (a person's
`decide` through `scope/decisions.json`), merge an org identity without a reviewed entry in `scope/org_decisions.json`,
or use an unreviewed Liquipedia team-name proposal. A deploy that automates those away gets wrong answers that look
right.

## Stale checkouts

Every CLI command first checks that this checkout is not older than what it is about to work against, and stops with
exit 3 if it is:

- the database has applied a migration this checkout has no file for, so the code predates the schema it would read
  and write;
- the branch is behind `origin/main`, by the local remote-tracking ref (`git fetch` keeps that ref current; the check
  makes no network call).

A stale checkout fails silently otherwise. It connects, ingests and answers from a schema it has never seen, and every
result looks plausible. `--allow-stale` or `OWCS_ALLOW_STALE=1` runs the command anyway and still prints the reason.
Two commands only warn, so a rollback to an older image keeps working. `serve` never refuses, and `migrate` refuses
only when it would add the checkout's own migrations to a newer schema. With nothing to add, it changes nothing.
