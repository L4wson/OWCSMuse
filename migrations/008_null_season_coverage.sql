-- A championship with no season silently erased its rows from stat coverage:
-- the totals join used `t.season = f.season`, which is false when both are NULL,
-- so every player-map under an unclassified championship vanished from
-- availability instead of being reported. Exactly the silent-partial failure the
-- coverage machinery exists to prevent.

DROP MATERIALIZED VIEW IF EXISTS stat_coverage_season CASCADE;
CREATE MATERIALIZED VIEW stat_coverage_season AS
WITH totals AS (
    SELECT season, count(*) AS rows_total, count(DISTINCT championship_id) AS championships_total
    FROM fact_player_maps GROUP BY season
)
SELECT
    f.season, kv.key AS stat_key, stat_kind(kv.key) AS stat_kind,
    count(*)                                  AS rows_with_stat,
    t.rows_total,
    round(100.0 * count(*) / t.rows_total, 1) AS coverage_pct,
    count(DISTINCT f.championship_id)         AS championships_with_stat,
    t.championships_total,
    min(f.started_at) AS first_at, max(f.started_at) AS last_at
FROM fact_player_maps f
JOIN totals t ON t.season IS NOT DISTINCT FROM f.season
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE kv.value IS NOT NULL AND kv.value <> ''
GROUP BY f.season, kv.key, t.rows_total, t.championships_total;
