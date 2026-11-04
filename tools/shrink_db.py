"""Get the production database back under its storage limit: drop the test schemas, prune duplicate listings.

Found 2026-11-03 with the project at 638 MB of a 500 MB limit (read-only measurement):

  * 39 scratch schemas the tests and the fixture builder made in production (170 MB), because earlier guidance said to
    point the tests at Supabase. Tests now refuse a remote database (tests/db_guard.py).
  * /championships/{id}/matches listings re-stored every night whether or not the page changed: 1,503 rows for 45
    pages, 170 MB of them identical to a neighbouring fetch. Migration 050 stops the regrowth; this removes what is
    already there.

Read-only unless a step is named, and a step runs only with the confirmation code its plan printed, so what runs is
exactly what was reviewed (any change in between changes the code):

    python tools/shrink_db.py                       # plan: sizes, the exact schema list, the prune per page
    python tools/shrink_db.py schemas --confirm C   # drop the listed schemas
    python tools/shrink_db.py prune --confirm C     # delete duplicate listing rows, in one verified transaction
    python tools/shrink_db.py vacuum                # VACUUM FULL raw_payloads: give the space back (locks the table)

Every step prints the database size after it. DATABASE_URL (or .env) names the database; OWCS_DB_SCHEMA is not used:
the schema list is about the whole database, and the prune is about public.raw_payloads.

THE PRUNE RULE. A listing page is one (endpoint, params) of a FACEIT /championships/{id}/matches request. Its fetches,
oldest first, fall into runs of identical content (same HTTP status, same payload). Each run keeps its first row,
which records the run (`last_seen_at` = the run's last fetch, `times_seen` = its length, as migration 050 records a
sighting from now on); the run's other rows are deleted. So every version of every page survives, a page that changed
and changed back keeps both runs, and the latest content of each page is unchanged. Nothing reads listing rows after
they are parsed, and the transaction refuses to commit if a deleted row is referenced anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
# the owner's patterns: owcs_golden and owcs_test themselves, everything under them, and owcs_fixture (2026-11-04)
APPROVED = re.compile(r"^(owcs_golden(_.+)?|owcs_test(_.+)?|owcs_fixture)$")
NEAR = re.compile(r"^owcs_")            # anything else that looks like ours is listed, never dropped
LISTING = "/championships/%/matches"

RUNS = """
WITH r AS (
    SELECT id, endpoint, params, fetched_at, http_status,
           md5(http_status::text || coalesce(payload::text, '') || coalesce(body_text, '')) AS h
      FROM public.raw_payloads
     WHERE source = 'faceit' AND endpoint LIKE %(listing)s
), o AS (
    SELECT *, lag(h) OVER (PARTITION BY endpoint, params ORDER BY fetched_at, id) AS prev_h FROM r
), g AS (
    SELECT *, sum(CASE WHEN prev_h IS NOT DISTINCT FROM h THEN 0 ELSE 1 END)
                  OVER (PARTITION BY endpoint, params ORDER BY fetched_at, id) AS run FROM o
)
SELECT *, row_number() OVER (PARTITION BY endpoint, params, run ORDER BY fetched_at, id) AS pos,
       count(*) OVER (PARTITION BY endpoint, params, run) AS run_len,
       max(fetched_at) OVER (PARTITION BY endpoint, params, run) AS run_last
  FROM g
"""


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip("'\"")
    if not url:
        sys.exit("DATABASE_URL is required")
    return psycopg.connect(url, row_factory=dict_row)


def mb(n) -> str:
    return f"{float(n or 0) / 1e6:,.1f} MB"


def sizes(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("""SELECT pg_database_size(current_database()) AS db,
                              pg_total_relation_size('public.raw_payloads') AS raw,
                              (SELECT count(*) FROM public.raw_payloads) AS raw_rows""")
        return cur.fetchone()


def report(conn, label: str) -> None:
    s = sizes(conn)
    print(f"[size {label}] database {mb(s['db'])}; raw_payloads {mb(s['raw'])} in {s['raw_rows']:,} rows")


def schema_plan(conn) -> tuple[list[dict], list[dict]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT n.nspname AS schema, count(c.oid) AS objects,
                              coalesce(sum(pg_total_relation_size(c.oid)) FILTER (WHERE c.relkind IN ('r', 'm')), 0) AS bytes
                         FROM pg_namespace n LEFT JOIN pg_class c ON c.relnamespace = n.oid
                        WHERE n.nspname LIKE 'owcs%%' GROUP BY n.nspname ORDER BY n.nspname""")
        rows = cur.fetchall()
    return [r for r in rows if APPROVED.match(r["schema"])], [r for r in rows if not APPROVED.match(r["schema"])]


def prune_plan(conn) -> list[dict]:
    """Per page: rows, distinct versions, runs (kept), deleted, bytes deleted."""
    with conn.cursor() as cur:
        cur.execute(f"""WITH x AS ({RUNS})
            SELECT x.endpoint, x.params::text AS params, count(*) AS rows, count(DISTINCT x.h) AS versions,
                   count(*) FILTER (WHERE x.pos = 1) AS kept, count(*) FILTER (WHERE x.pos > 1) AS deleted,
                   coalesce(sum(pg_column_size(p.payload)) FILTER (WHERE x.pos > 1), 0) AS deleted_bytes
              FROM x JOIN public.raw_payloads p ON p.id = x.id
             GROUP BY x.endpoint, x.params ORDER BY x.endpoint, x.params""", {"listing": LISTING})
        return cur.fetchall()


def code(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:10]


def plan(conn) -> None:
    report(conn, "now")
    drop, other = schema_plan(conn)
    print(f"\nSTEP 1 - drop {len(drop)} schema(s) matching owcs_golden, owcs_golden_*, owcs_test, owcs_test_*, owcs_fixture "
          f"({mb(sum(r['bytes'] for r in drop))} in tables and materialized views, {sum(r['objects'] for r in drop):,} objects):")
    for r in drop:
        print(f"    {r['schema']:32} {mb(r['bytes']):>10}  {r['objects']:>5} objects")
    if other:
        print("  NOT dropped (outside the patterns; listed so nothing is a surprise):")
        for r in other:
            print(f"    {r['schema']:32} {mb(r['bytes']):>10}  {r['objects']:>5} objects")
    print(f"  confirmation code: {code([r['schema'] for r in drop])}")

    pages = prune_plan(conn)
    print(f"\nSTEP 2 - prune duplicate listing rows: {len(pages)} pages, {sum(p['rows'] for p in pages):,} rows; keep "
          f"{sum(p['kept'] for p in pages):,}, delete {sum(p['deleted'] for p in pages):,} "
          f"({mb(sum(p['deleted_bytes'] for p in pages))} of payload, compressed)")
    print("  Rule: a page's fetches, oldest first, form runs of identical content; each run keeps its first row (which "
          "records the run's last fetch and length) and deletes the rest. Every version survives.")
    print(f"    {'page':58} {'rows':>5} {'versions':>8} {'kept':>5} {'deleted':>7}")
    for p in pages:
        page = p["endpoint"].replace("/championships/", "").replace("/matches", "") + " " + p["params"]
        print(f"    {page[:58]:58} {p['rows']:>5} {p['versions']:>8} {p['kept']:>5} {p['deleted']:>7}")
    lost = [p for p in pages if p["kept"] < p["versions"]]
    print(f"  every page keeps at least one row per distinct version: {'yes' if not lost else 'NO: ' + str(lost)}")
    print(f"  confirmation code: {code([(p['endpoint'], p['params'], p['rows'], p['deleted']) for p in pages])}")
    print("\nSTEP 3 - VACUUM FULL public.raw_payloads after the prune: rewrites the table and returns the space; it holds an "
          "exclusive lock on raw_payloads while it runs (seconds to a minute at this size), so run it when no ingest is.")


def drop_schemas(conn, confirm: str) -> None:
    drop, _ = schema_plan(conn)
    names = [r["schema"] for r in drop]
    if code(names) != confirm:
        sys.exit(f"confirmation code {confirm} does not match the current plan ({code(names)}): re-run the plan")
    report(conn, "before")
    for name in names:
        assert APPROVED.match(name), name
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
        conn.commit()
        print(f"  dropped {name}")
    report(conn, "after dropping schemas")


def prune(conn, confirm: str) -> None:
    pages = prune_plan(conn)
    if code([(p["endpoint"], p["params"], p["rows"], p["deleted"]) for p in pages]) != confirm:
        sys.exit("confirmation code does not match the current plan: re-run the plan")
    report(conn, "before")
    with conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout = '10s'")
        cur.execute(f"CREATE TEMP TABLE _runs ON COMMIT DROP AS {RUNS}", {"listing": LISTING})
        cur.execute("""CREATE TEMP TABLE _versions_before ON COMMIT DROP AS
                       SELECT DISTINCT endpoint, params, h FROM _runs""")
        # a row to delete must not be referenced: listing rows never are, and this proves it
        cur.execute("""SELECT count(*) AS n FROM _runs r WHERE r.pos > 1 AND (
                         EXISTS (SELECT 1 FROM public.matches m WHERE r.id IN (m.detail_raw_id, m.stats_raw_id))
                         OR EXISTS (SELECT 1 FROM public.liquipedia_matches l WHERE l.raw_id = r.id)
                         OR EXISTS (SELECT 1 FROM public.liquipedia_coverage c WHERE r.id = ANY(c.raw_ids)))""")
        if cur.fetchone()["n"]:
            conn.rollback()
            sys.exit("a row to delete is referenced: nothing changed")
        cur.execute("""UPDATE public.raw_payloads p SET last_seen_at = r.run_last, times_seen = r.run_len
                         FROM _runs r WHERE r.id = p.id AND r.pos = 1 AND r.run_len > 1""")
        updated = cur.rowcount
        cur.execute("DELETE FROM public.raw_payloads p USING _runs r WHERE r.id = p.id AND r.pos > 1")
        deleted = cur.rowcount
        # verify before commit: the same distinct versions on every page, one row per run, every sighting counted
        cur.execute(f"""WITH x AS ({RUNS}) SELECT
                (SELECT count(*) FROM (SELECT endpoint, params, h FROM x EXCEPT SELECT * FROM _versions_before) a)
              + (SELECT count(*) FROM (SELECT * FROM _versions_before EXCEPT SELECT endpoint, params, h FROM x) b) AS changed,
                (SELECT count(*) FROM x WHERE pos > 1) AS left_over,
                (SELECT count(*) FROM _runs) AS fetches_before,
                (SELECT sum(p.times_seen) FROM x JOIN public.raw_payloads p ON p.id = x.id) AS fetches_after""",
                    {"listing": LISTING})
        v = cur.fetchone()
        expected = sum(p["deleted"] for p in pages)
        if v["changed"] or v["left_over"] or deleted != expected or v["fetches_after"] != v["fetches_before"]:
            conn.rollback()
            sys.exit(f"verification failed, nothing changed: {dict(v)}, deleted {deleted} of {expected}")
    conn.commit()
    print(f"  deleted {deleted:,} duplicate listing rows; {updated:,} kept rows record their runs; every version kept, "
          f"all {v['fetches_before']:,} fetches still counted in times_seen")
    report(conn, "after the prune (space returns after VACUUM FULL)")


def vacuum(conn) -> None:
    report(conn, "before")
    conn.commit()                 # VACUUM runs outside a transaction: close the one the size report opened
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout = '30s'")
        cur.execute("VACUUM (FULL, ANALYZE) public.raw_payloads")
    report(conn, "after VACUUM FULL")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("step", nargs="?", choices=["plan", "schemas", "prune", "vacuum"], default="plan")
    p.add_argument("--confirm", help="the confirmation code the plan printed for this step")
    a = p.parse_args()
    with connect() as conn:
        if a.step == "plan":
            conn.read_only = True
            plan(conn)
        elif a.step == "vacuum":
            vacuum(conn)
        elif not a.confirm:
            sys.exit(f"{a.step} needs --confirm <code>: run the plan first")
        elif a.step == "schemas":
            drop_schemas(conn, a.confirm)
        else:
            prune(conn, a.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
