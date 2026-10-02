-- 036: a role filter means the players whose role it is, not every map played in it.
--
-- "which na support had the least deaths in 2024" answered MER1T: 45 maps as Damage, 1 as Support (4 deaths). The role
-- filter applied per map, so one flex map made a damage player a support, and an ascending total put him first. A map
-- now counts toward role R only when R is the player's primary role in that map's season: the role with the most maps
-- (a tie keeps every tied role). Per-map stats are still summed over the role's maps.

CREATE OR REPLACE VIEW player_primary_roles AS
SELECT player_id, season, role
  FROM (SELECT player_id, season, role, rank() OVER (PARTITION BY player_id, season ORDER BY count(*) DESC) AS rk
          FROM fact_player_maps WHERE role IS NOT NULL GROUP BY player_id, season, role) x
 WHERE rk = 1;

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
             WHEN (SELECT count(*) FROM comp) = 1 THEN round(sum(b.num) / nullif(sum(b.den), 0), 4)
        END AS total,
        CASE WHEN (SELECT k FROM kind) = 'countable' THEN avg(b.v)
             WHEN (SELECT count(*) FROM comp) = 1 THEN round(sum(b.num) / nullif(sum(b.den), 0), 4)
             ELSE avg(b.v) END AS avg_per_map,
        array_agg(DISTINCT b.season ORDER BY b.season) FILTER (WHERE b.v IS NOT NULL) AS seasons
    FROM base b
    JOIN players p ON p.player_id = b.player_id
    GROUP BY b.player_id, p.display_name, p.nickname, p.game_player_name
    HAVING count(*) FILTER (WHERE b.v IS NOT NULL) >= greatest(p_min_maps, 1)
    ORDER BY CASE WHEN p_order = 'avg'
                  THEN (CASE WHEN (SELECT k FROM kind) = 'countable' THEN avg(b.v)
                             WHEN (SELECT count(*) FROM comp) = 1 THEN sum(b.num) / nullif(sum(b.den), 0)
                             ELSE avg(b.v) END)
                  ELSE (CASE WHEN (SELECT k FROM kind) = 'countable' THEN sum(b.v)
                             WHEN (SELECT count(*) FROM comp) = 1 THEN sum(b.num) / nullif(sum(b.den), 0)
                             ELSE avg(b.v) END) END DESC NULLS LAST,
             maps_with_stat DESC, b.player_id            -- a deterministic last key: a planner change cannot reorder ties
    LIMIT p_limit
$$;
