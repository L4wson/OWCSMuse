-- Every table-reading SQL function survives PostgreSQL 17's restricted search_path.
--
-- PostgreSQL 17 runs CREATE INDEX, REFRESH MATERIALIZED VIEW, CREATE
-- MATERIALIZED VIEW ... WITH DATA, VACUUM, ANALYZE, CLUSTER and REINDEX with
-- search_path = pg_catalog, pg_temp. A LANGUAGE sql function body is re-parsed
-- by name whenever a query calling it is planned (inlining) or run, so a body
-- that names a table of ours resolves nothing under that path: migration 026
-- failed on production (17.6) with `relation "teams" does not exist ... SQL
-- function "team_identity_at" during inlining` while passing every gate on 16.
--
-- Two remedies, chosen per function:
--   * `{{schema}}.` on every relation and function the body names (migrate
--     substitutes OWCS_DB_SCHEMA): keeps the function inlinable. Used for the
--     functions that run once per fact row (team_era_name, team_identity_at,
--     series_score, in 026/030/032) and for championship_display_name here.
--   * SET search_path FROM CURRENT: simpler, but a function with its own
--     search_path is never inlined and re-plans on every call (44x slower
--     refresh when tried on the per-row functions). Used for the query-time
--     set-returning functions, each called once per question.
-- tests/test_search_path.py refreshes every materialized view under the
-- restricted path and keeps every table-reading SQL function in one of the two
-- states.

CREATE OR REPLACE FUNCTION championship_display_name(name text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        (SELECT cn.display_name FROM {{schema}}.competition_names cn WHERE cn.faceit_name = name),
        regexp_replace(name, '^(S\d+) (EMEA|NA) OWCS Central - (.+)$', 'OWCS \2 \1 \3')
    )
$$;

ALTER FUNCTION stat_coverage_summary(text, integer, text) SET search_path FROM CURRENT;
ALTER FUNCTION stat_coverage_summary(text, integer, text, text, text, text, text, text) SET search_path FROM CURRENT;
ALTER FUNCTION stat_leaderboard(text, integer, text, integer, integer, text, text) SET search_path FROM CURRENT;
