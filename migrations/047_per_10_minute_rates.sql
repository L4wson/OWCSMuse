-- 047: a per-10-minutes rate is per 10 minutes.
--
-- A derived rate is computed from its components, time-weighted across maps: sum(numerator) / sum(denominator). For the
-- eleven "/10m" stats the denominator is Time Played in seconds, so every one of them was per second: "Snowl leads
-- Deaths/10m with 0.01 across 8 maps" for about 8 deaths per 10 minutes. FACEIT's own per-map value is
-- 600 x numerator / Time Played (checked on zeruhh's 156 maps: every one within 0.005, its rounding), so the scale is
-- 600 for a "/10m" rate over Time Played and 1 for every other ratio (K/D, Final Blows/Eliminations, ...).
--
-- The components are also summed over the same maps only: a map with the stat and both components. Summed over every
-- row, a 2024 map that records Deaths but no Time Played added deaths and no time (zeruhh: 5.43 deaths per 10 minutes
-- for 4.83). That held for every ratio (K/D, Final Blows/Eliminations, ...), not only the per-10 ones.
--
-- stat_rate_scale() is new; stat_leaderboard is 036's verbatim but for those two changes to its rate expressions. The
-- one-player answer (compile.py) uses the same rule.

CREATE OR REPLACE FUNCTION stat_rate_scale(stat_key text) RETURNS numeric
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN stat_key LIKE '%/10m'
                 AND (SELECT denominator FROM stat_rate_components(stat_key)) = 'Time Played' THEN 600
                ELSE 1 END::numeric
$$;

CREATE OR REPLACE FUNCTION stat_leaderboard(
    p_stat text, p_season integer DEFAULT NULL, p_championship text DEFAULT NULL,
    p_min_maps integer DEFAULT 1, p_limit integer DEFAULT 20, p_order text DEFAULT 'total',
    p_role text DEFAULT NULL
) RETURNS TABLE (
    player_id text, nickname text, maps_with_stat bigint, maps_played bigint, coverage_pct numeric,
    total numeric, avg_per_map numeric, seasons integer[]
) LANGUAGE sql STABLE SET search_path FROM CURRENT AS $$
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
          AND (p_role IS NULL OR (f.role = p_role AND EXISTS (
                SELECT 1 FROM player_primary_roles r WHERE r.player_id = f.player_id AND r.season = f.season AND r.role = p_role)))
          AND (SELECT k FROM kind) <> 'non_numeric'
    )
    SELECT
        b.player_id, player_display_name(p.display_name, p.nickname, p.game_player_name),
        count(*) FILTER (WHERE b.v IS NOT NULL) AS maps_with_stat,
        count(*) AS maps_played,
        round(100.0 * count(*) FILTER (WHERE b.v IS NOT NULL) / count(*), 1) AS coverage_pct,
        CASE WHEN (SELECT k FROM kind) = 'countable' THEN sum(b.v)
             WHEN (SELECT count(*) FROM comp) = 1 THEN round(stat_rate_scale(p_stat) * sum(b.num) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL)
                   / nullif(sum(b.den) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL), 0), 4)
        END AS total,
        CASE WHEN (SELECT k FROM kind) = 'countable' THEN avg(b.v)
             WHEN (SELECT count(*) FROM comp) = 1 THEN round(stat_rate_scale(p_stat) * sum(b.num) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL)
                   / nullif(sum(b.den) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL), 0), 4)
             ELSE avg(b.v) END AS avg_per_map,
        array_agg(DISTINCT b.season ORDER BY b.season) FILTER (WHERE b.v IS NOT NULL) AS seasons
    FROM base b
    JOIN players p ON p.player_id = b.player_id
    GROUP BY b.player_id, p.display_name, p.nickname, p.game_player_name
    HAVING count(*) FILTER (WHERE b.v IS NOT NULL) >= greatest(p_min_maps, 1)
    ORDER BY CASE WHEN p_order = 'avg'
                  THEN (CASE WHEN (SELECT k FROM kind) = 'countable' THEN avg(b.v)
                             WHEN (SELECT count(*) FROM comp) = 1 THEN sum(b.num) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL)
                                  / nullif(sum(b.den) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL), 0)
                             ELSE avg(b.v) END)
                  ELSE (CASE WHEN (SELECT k FROM kind) = 'countable' THEN sum(b.v)
                             WHEN (SELECT count(*) FROM comp) = 1 THEN sum(b.num) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL)
                                  / nullif(sum(b.den) FILTER (WHERE b.v IS NOT NULL AND b.num IS NOT NULL AND b.den IS NOT NULL), 0)
                             ELSE avg(b.v) END) END DESC NULLS LAST,
             maps_with_stat DESC, b.player_id            -- a deterministic last key: a planner change cannot reorder ties
    LIMIT p_limit
$$;
