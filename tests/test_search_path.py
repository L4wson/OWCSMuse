"""PostgreSQL 17 plans CREATE/REFRESH MATERIALIZED VIEW (and CREATE INDEX, VACUUM, ANALYZE, CLUSTER, REINDEX) under
search_path = pg_catalog, pg_temp. A LANGUAGE sql function body is re-parsed by name at plan time, so one that names
a table of ours must carry its own search_path or every refresh fails there - which is how migration 026 failed on
production (17.6) after passing every gate on 16. Two gates here: the condition itself, reproduced on any major by
refreshing every materialized view under that restricted path; and the rule that keeps it fixed, that every
table-reading SQL function in the schema is pinned."""

from __future__ import annotations

import os
import re

import pytest

from owcsmuse.aggregates import MATERIALIZED_VIEWS

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


def test_every_materialized_view_refreshes_under_the_restricted_search_path_17_uses(agg_db):
    """What PG 17 does on its own, done by hand so PG 16 exercises it too: the view is named by schema (as the
    server does internally) and nothing else is on the path."""
    with agg_db.cursor() as cur:
        for view in MATERIALIZED_VIEWS:
            cur.execute("SET LOCAL search_path TO pg_catalog, pg_temp")
            cur.execute(f"REFRESH MATERIALIZED VIEW {SCHEMA}.{view}")
    agg_db.rollback()


def test_every_table_reading_sql_function_survives_the_restricted_path(agg_db):
    """A LANGUAGE sql function whose body names one of our relations is either pinned (SET search_path, for the
    once-per-question set-returning functions) or names every relation and function `schema.`-qualified (for the
    once-per-row functions, which must stay inlinable). A pure one (fold_name, stat_num, match_time, map_is_drawn)
    is neither and keeps inlining."""
    with agg_db.cursor() as cur:
        cur.execute("SELECT relname FROM pg_class WHERE relnamespace = %s::regnamespace AND relkind IN ('r', 'v', 'm')", [SCHEMA])
        relations = {r["relname"] for r in cur.fetchall()}
        cur.execute("""
            SELECT p.proname, p.prosrc, p.proconfig FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
             WHERE p.pronamespace = %s::regnamespace AND l.lanname = 'sql'""", [SCHEMA])
        rows = cur.fetchall()
    assert rows
    PER_ROW = {"team_identity_at", "team_era_name", "series_score", "championship_display_name"}
    PINNED = {"stat_leaderboard", "stat_coverage_summary"}
    bad = []
    for r in rows:
        refs = re.findall(r"\b(?:FROM|JOIN)\s+([a-z_.]+)", r["prosrc"])
        unqualified = {x for x in refs if "." not in x} & relations
        qualified = {x for x in refs if "." in x}
        pinned = [c for c in (r["proconfig"] or []) if c.startswith("search_path=")]
        if r["proname"] in PER_ROW:
            if pinned:
                bad.append((r["proname"], "pinned: it would never be inlined and would re-plan on every fact row"))
            if unqualified:
                bad.append((r["proname"], f"unqualified relations {sorted(unqualified)}"))
            if any(not q.startswith(SCHEMA + ".") for q in qualified):
                bad.append((r["proname"], f"qualified with a schema other than the migration's: {sorted(qualified)}"))
        elif unqualified and not pinned:
            bad.append((r["proname"], f"reads {sorted(unqualified)} with neither SET search_path nor qualification"))
        if pinned and pinned != [f"search_path={SCHEMA}"]:
            bad.append((r["proname"], f"pinned to {pinned}, not the migration schema"))
    assert not bad, bad
    assert PER_ROW | PINNED <= {r["proname"] for r in rows}
