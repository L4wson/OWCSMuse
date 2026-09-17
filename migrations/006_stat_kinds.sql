-- Stat kinds. FACEIT mixes three different things in one flat player_stats map,
-- and they must not be aggregated the same way:
--
--   countable    Eliminations, Deaths, Damage Dealt, ...  sum across maps; a
--                per-map average is sum / maps_with_stat.
--   derived_rate K/D Ratio, Eliminations/10m, "... as percent of total output"
--                Already a ratio for one map. Summing is meaningless and
--                averaging is only correct when every map has equal weight, so
--                these are recomputed from their components where the
--                components exist, and otherwise reported per map only.
--   non_numeric  Role, Team, Map, Winner, ... never a metric.
--
-- Everything that reads stats goes through stat_kind(), so a non-numeric key
-- can no longer reach a leaderboard.

CREATE OR REPLACE FUNCTION stat_kind(stat_key text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE
        WHEN stat_key IN ('Role', 'Team', 'Map', 'Winner', 'Score Summary', 'Best Of', 'Nickname') THEN 'non_numeric'
        WHEN stat_key ~ '(/10m|Ratio|percent|per |/Deaths|/Eliminations|/Final Blows|/\(Eliminations|Avg |Average )' THEN 'derived_rate'
        ELSE 'countable'
    END
$$;

-- Components a derived rate can be recomputed from, when both exist as countable keys.
CREATE OR REPLACE FUNCTION stat_rate_components(stat_key text)
RETURNS TABLE (numerator text, denominator text)
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT t.n, t.d FROM (VALUES
        ('K/D Ratio',                          'Eliminations',     'Deaths'),
        ('Eliminations/10m',                   'Eliminations',     'Time Played'),
        ('Final Blows/10m',                    'Final Blows',      'Time Played'),
        ('Deaths/10m',                         'Deaths',           'Time Played'),
        ('Assists/10m',                        'Assists',          'Time Played'),
        ('Damage Dealt/10m',                   'Damage Dealt',     'Time Played'),
        ('Healing Done/10m',                   'Healing Done',     'Time Played'),
        ('Damage Mitigated/10m',               'Damage Mitigated', 'Time Played'),
        ('Solo Kills/10m',                     'Solo Kills',       'Time Played'),
        ('Multi Kills/10m',                    'Multi Kills',      'Time Played'),
        ('Objective Time/10m',                 'Objective Time',   'Time Played'),
        ('Environmental Kills/10m',            'Environmental Kills', 'Time Played'),
        ('(Eliminations + Assists)/Deaths',    'Eliminations',     'Deaths'),
        ('Final Blows/Eliminations',           'Final Blows',      'Eliminations'),
        ('Solo Kills/Eliminations Ratio',      'Solo Kills',       'Eliminations'),
        ('Solo Kills/Deaths Ratio',            'Solo Kills',       'Deaths'),
        ('Healing Done/Deaths',                'Healing Done',     'Deaths'),
        ('Damage Mitigated/Deaths',            'Damage Mitigated', 'Deaths'),
        ('Damage Dealt/Eliminations',          'Damage Dealt',     'Eliminations'),
        ('Healing Done/Eliminations',          'Healing Done',     'Eliminations'),
        ('Damage Mitigated/Eliminations',      'Damage Mitigated', 'Eliminations')
    ) AS t(k, n, d) WHERE t.k = stat_key
$$;

-- ------------------------------------------------------------- availability

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
JOIN totals t ON t.season = f.season
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE kv.value IS NOT NULL AND kv.value <> ''
GROUP BY f.season, kv.key, t.rows_total, t.championships_total;

DROP MATERIALIZED VIEW IF EXISTS stat_coverage CASCADE;
CREATE MATERIALIZED VIEW stat_coverage AS
WITH totals AS (
    SELECT championship_id, count(*) AS rows_total FROM fact_player_maps GROUP BY championship_id
)
SELECT
    f.championship_id, f.season, c.name AS championship_name, kv.key AS stat_key, stat_kind(kv.key) AS stat_kind,
    count(*)                                          AS rows_with_stat,
    t.rows_total,
    round(100.0 * count(*) / t.rows_total, 1)         AS coverage_pct,
    bool_and(stat_num(kv.value) IS NOT NULL)          AS is_numeric,
    min(f.started_at) AS first_at, max(f.started_at)  AS last_at
FROM fact_player_maps f
JOIN championships c ON c.championship_id = f.championship_id
JOIN totals t ON t.championship_id = f.championship_id
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE kv.value IS NOT NULL AND kv.value <> ''
GROUP BY f.championship_id, f.season, c.name, kv.key, t.rows_total;
CREATE INDEX stat_coverage_key_idx ON stat_coverage (stat_key);

-- A numeric stat that is not aggregated by summing is excluded from the long
-- format's `total`, which only ever meant something for countable keys.
DROP MATERIALIZED VIEW IF EXISTS agg_player_stat_long CASCADE;
CREATE MATERIALIZED VIEW agg_player_stat_long AS
SELECT
    f.player_id, f.championship_id, f.season, kv.key AS stat_key, stat_kind(kv.key) AS stat_kind,
    count(*)                 AS maps_with_stat,
    CASE WHEN stat_kind(kv.key) = 'countable' THEN sum(stat_num(kv.value)) END AS total,
    avg(stat_num(kv.value))  AS avg_per_map,
    min(stat_num(kv.value))  AS min_per_map,
    max(stat_num(kv.value))  AS max_per_map,
    min(f.started_at) AS first_at, max(f.started_at) AS last_at
FROM fact_player_maps f
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE stat_num(kv.value) IS NOT NULL
GROUP BY f.player_id, f.championship_id, f.season, kv.key;
CREATE INDEX agg_player_stat_long_key_idx ON agg_player_stat_long (stat_key, season);

-- ------------------------------------------------------------- coverage + leaderboard

-- Coverage for exactly the slice being queried, not the whole warehouse.
CREATE OR REPLACE FUNCTION stat_coverage_summary(
    p_stat text, p_season integer DEFAULT NULL, p_championship text DEFAULT NULL,
    p_player text DEFAULT NULL, p_team text DEFAULT NULL, p_map text DEFAULT NULL,
    p_mode text DEFAULT NULL, p_region text DEFAULT NULL
) RETURNS TABLE (
    stat_key text, stat_kind text, maps_total bigint, maps_with_stat bigint, coverage_pct numeric,
    seasons_with_stat integer[], seasons_without_stat integer[],
    first_at timestamptz, last_at timestamptz, slice text
) LANGUAGE sql STABLE AS $$
    WITH scope AS (
        SELECT * FROM fact_player_maps
        WHERE (p_season IS NULL OR season = p_season)
          AND (p_championship IS NULL OR championship_id = p_championship)
          AND (p_player IS NULL OR player_id = p_player)
          AND (p_team IS NULL OR team_id = p_team)
          AND (p_map IS NULL OR map_name = p_map)
          AND (p_mode IS NULL OR game_mode = p_mode)
          AND (p_region IS NULL OR region = p_region)
    ),
    has AS (SELECT * FROM scope WHERE stat_num(stats ->> p_stat) IS NOT NULL)
    SELECT
        p_stat,
        stat_kind(p_stat),
        (SELECT count(*) FROM scope),
        (SELECT count(*) FROM has),
        CASE WHEN (SELECT count(*) FROM scope) > 0
             THEN round(100.0 * (SELECT count(*) FROM has) / (SELECT count(*) FROM scope), 1) ELSE 0 END,
        (SELECT array_agg(DISTINCT season ORDER BY season) FROM has WHERE season IS NOT NULL),
        (SELECT array_agg(DISTINCT season ORDER BY season) FROM scope
          WHERE season IS NOT NULL AND season NOT IN (SELECT season FROM has WHERE season IS NOT NULL)),
        (SELECT min(started_at) FROM has),
        (SELECT max(started_at) FROM has),
        concat_ws(', ',
            CASE WHEN p_season IS NOT NULL THEN 'season ' || p_season END,
            CASE WHEN p_championship IS NOT NULL THEN 'championship ' || p_championship END,
            CASE WHEN p_player IS NOT NULL THEN 'player ' || p_player END,
            CASE WHEN p_team IS NOT NULL THEN 'team ' || p_team END,
            CASE WHEN p_map IS NOT NULL THEN 'map ' || p_map END,
            CASE WHEN p_mode IS NOT NULL THEN 'mode ' || p_mode END,
            CASE WHEN p_region IS NOT NULL THEN 'region ' || p_region END)
$$;

-- Leaderboards refuse non-numeric keys and recompute derived rates from their
-- components, so K/D Ratio is sum(eliminations)/sum(deaths), never a sum or a
-- mean of per-map ratios.
CREATE OR REPLACE FUNCTION stat_leaderboard(
    p_stat text, p_season integer DEFAULT NULL, p_championship text DEFAULT NULL,
    p_min_maps integer DEFAULT 1, p_limit integer DEFAULT 20, p_order text DEFAULT 'total'
) RETURNS TABLE (
    player_id text, nickname text, maps_with_stat bigint, maps_played bigint, coverage_pct numeric,
    total numeric, avg_per_map numeric, seasons integer[]
) LANGUAGE sql STABLE AS $$
    WITH kind AS (SELECT stat_kind(p_stat) AS k),
    comp AS (SELECT numerator, denominator FROM stat_rate_components(p_stat)),
    base AS (
        SELECT f.player_id, f.season, f.stats,
               stat_num(f.stats ->> p_stat) AS v,
               stat_num(f.stats ->> (SELECT numerator FROM comp))   AS num,
               stat_num(f.stats ->> (SELECT denominator FROM comp)) AS den
        FROM fact_player_maps f
        WHERE (p_season IS NULL OR f.season = p_season)
          AND (p_championship IS NULL OR f.championship_id = p_championship)
          AND (SELECT k FROM kind) <> 'non_numeric'
    )
    SELECT
        b.player_id, p.nickname,
        count(*) FILTER (WHERE b.v IS NOT NULL) AS maps_with_stat,
        count(*) AS maps_played,
        round(100.0 * count(*) FILTER (WHERE b.v IS NOT NULL) / count(*), 1) AS coverage_pct,
        CASE WHEN (SELECT k FROM kind) = 'countable' THEN sum(b.v)
             WHEN (SELECT count(*) FROM comp) = 1 THEN round(sum(b.num) / nullif(sum(b.den), 0), 4)
        END AS total,
        CASE WHEN (SELECT k FROM kind) = 'countable' THEN avg(b.v)
             WHEN (SELECT count(*) FROM comp) = 1 THEN round(sum(b.num) / nullif(sum(b.den), 0), 4)
             ELSE avg(b.v) END AS avg_per_map,
        array_agg(DISTINCT b.season ORDER BY b.season) FILTER (WHERE b.v IS NOT NULL) AS seasons
    FROM base b
    JOIN players p ON p.player_id = b.player_id
    GROUP BY b.player_id, p.nickname
    HAVING count(*) FILTER (WHERE b.v IS NOT NULL) >= greatest(p_min_maps, 1)
    ORDER BY CASE WHEN p_order = 'avg'
                  THEN (CASE WHEN (SELECT k FROM kind) = 'countable' THEN avg(b.v)
                             WHEN (SELECT count(*) FROM comp) = 1 THEN sum(b.num) / nullif(sum(b.den), 0)
                             ELSE avg(b.v) END)
                  ELSE (CASE WHEN (SELECT k FROM kind) = 'countable' THEN sum(b.v)
                             WHEN (SELECT count(*) FROM comp) = 1 THEN sum(b.num) / nullif(sum(b.den), 0)
                             ELSE avg(b.v) END) END DESC NULLS LAST,
             maps_with_stat DESC
    LIMIT p_limit
$$;
