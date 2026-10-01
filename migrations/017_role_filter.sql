-- Role reaches the query layer.
--
-- match_players.role is real per-map data ('Tank', 'Damage', 'Support'), but
-- nothing before this migration could filter by it: Filters had no role field,
-- so "tank with the most kills" silently dropped the word "tank" and ranked
-- everyone. stat_leaderboard() gains an optional p_role, appended at the end
-- with a default so every existing call keeps working unchanged.
--
-- Role is per player per map, not per player: a flex player who played tank in
-- some maps and DPS in others is correctly counted in both leaderboards, once
-- each, for exactly the maps they played that role. Nothing here picks a
-- "primary" role or merges two roles' stats together.

-- CREATE OR REPLACE cannot append a parameter in place: Postgres treats a
-- longer argument-type list as a distinct overload, not a replacement, which
-- left two ambiguous stat_leaderboard functions and broke every existing
-- 6-argument call ("function stat_leaderboard(...) is not unique"). The old
-- signature has to go first.
DROP FUNCTION IF EXISTS stat_leaderboard(text, integer, text, integer, integer, text);

CREATE OR REPLACE FUNCTION stat_leaderboard(
    p_stat text, p_season integer DEFAULT NULL, p_championship text DEFAULT NULL,
    p_min_maps integer DEFAULT 1, p_limit integer DEFAULT 20, p_order text DEFAULT 'total',
    p_role text DEFAULT NULL
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
          AND (p_role IS NULL OR f.role = p_role)
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
