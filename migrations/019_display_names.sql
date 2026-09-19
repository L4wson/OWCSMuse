-- Show the in-game name, not the FACEIT profile nickname, wherever a player
-- is displayed - the two can differ (a player's FACEIT account nickname is
-- not necessarily what showed up in the match client), and the in-game name
-- is what a viewer watching the actual game recognises.
--
-- players.nickname is untouched and stays exactly what it was: the FACEIT
-- identity that ingestion keys everything on, searchable via entity_names
-- (name_kind 'current_nickname') and preserved in full in player_nicknames.
-- Only the DISPLAY value changes, in one function used everywhere a player's
-- name is selected, so a player with no recorded in-game name still shows
-- their nickname rather than a blank.
CREATE OR REPLACE FUNCTION player_display_name(nickname text, game_player_name text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(nullif(game_player_name, ''), nickname)
$$;

-- entity_names.current_name is the one place resolve(), the answer sentence
-- and the clarify UI all read a player's display name from. Everything else
-- (name, name_folded, name_kind) is unchanged, so search and nickname history
-- are unaffected - identical to migration 015 except current_name for players.
DROP MATERIALIZED VIEW IF EXISTS entity_names CASCADE;
CREATE MATERIALIZED VIEW entity_names AS
WITH player_activity AS (
    SELECT player_id,
           count(DISTINCT match_id) AS n,
           array_agg(DISTINCT season ORDER BY season) FILTER (WHERE season IS NOT NULL) AS seasons,
           min(started_at) AS first_at, max(started_at) AS last_at
    FROM fact_player_maps GROUP BY player_id
), team_activity AS (
    SELECT team_id,
           count(DISTINCT match_id) AS n,
           array_agg(DISTINCT season ORDER BY season) FILTER (WHERE season IS NOT NULL) AS seasons,
           min(started_at) AS first_at, max(started_at) AS last_at
    FROM fact_team_matches GROUP BY team_id
), org_activity AS (
    SELECT org_id,
           count(DISTINCT match_id) AS n,
           array_agg(DISTINCT season ORDER BY season) FILTER (WHERE season IS NOT NULL) AS seasons,
           min(started_at) AS first_at, max(started_at) AS last_at
    FROM fact_team_matches WHERE org_id IS NOT NULL GROUP BY org_id
)
SELECT 'player'::text AS entity_type, p.player_id AS entity_id, p.nickname AS name,
       'current_nickname'::text AS name_kind, fold_name(p.nickname) AS name_folded,
       player_display_name(p.nickname, p.game_player_name) AS current_name, p.last_seen_at, coalesce(pa.n, 0) AS matches,
       pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
UNION ALL
SELECT 'player', p.player_id, p.game_player_name, 'game_name', fold_name(p.game_player_name),
       player_display_name(p.nickname, p.game_player_name),
       p.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
WHERE p.game_player_name IS NOT NULL AND fold_name(p.game_player_name) <> fold_name(p.nickname)
UNION ALL
SELECT 'player', pn.player_id, pn.nickname, 'historical_nickname', fold_name(pn.nickname),
       player_display_name(p.nickname, p.game_player_name),
       pn.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM player_nicknames pn JOIN players p ON p.player_id = pn.player_id
LEFT JOIN player_activity pa ON pa.player_id = pn.player_id
WHERE pn.nickname <> p.nickname
UNION ALL
SELECT 'org', o.org_id, o.name, 'current_name', fold_name(o.name), o.name, max(t.last_seen_at),
       coalesce(max(oa.n), 0), max(oa.seasons), min(oa.first_at), max(oa.last_at)
FROM orgs o JOIN team_orgs tm ON tm.org_id = o.org_id JOIN teams t ON t.team_id = tm.team_id
LEFT JOIN org_activity oa ON oa.org_id = o.org_id
GROUP BY o.org_id, o.name
UNION ALL
SELECT 'org', tm.org_id, t.name, 'historical_team_name', fold_name(t.name), o.name, t.last_seen_at,
       coalesce(oa.n, 0), oa.seasons, oa.first_at, oa.last_at
FROM team_orgs tm JOIN teams t ON t.team_id = tm.team_id JOIN orgs o ON o.org_id = tm.org_id
LEFT JOIN org_activity oa ON oa.org_id = tm.org_id
WHERE fold_name(t.name) <> fold_name(o.name)
UNION ALL
SELECT 'team', t.team_id, t.name, 'current_name', fold_name(t.name), t.name, t.last_seen_at,
       coalesce(ta.n, 0), ta.seasons, ta.first_at, ta.last_at
FROM teams t LEFT JOIN team_orgs tm ON tm.team_id = t.team_id
LEFT JOIN team_activity ta ON ta.team_id = t.team_id
WHERE t.name IS NOT NULL AND tm.team_id IS NULL
UNION ALL
SELECT 'team', tn.team_id, tn.name, 'historical_name', fold_name(tn.name), t.name, tn.last_seen_at,
       coalesce(ta.n, 0), ta.seasons, ta.first_at, ta.last_at
FROM team_names tn JOIN teams t ON t.team_id = tn.team_id
LEFT JOIN team_orgs tm ON tm.team_id = tn.team_id
LEFT JOIN team_activity ta ON ta.team_id = tn.team_id
WHERE tn.name <> t.name AND tm.team_id IS NULL;
CREATE INDEX entity_names_idx ON entity_names (entity_type, name_folded);
CREATE INDEX entity_names_id_idx ON entity_names (entity_id);

-- stat_leaderboard() is the other place a player's name is selected outside
-- the Python-built SQL in compile.py (which is fixed in the same commit).
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
        b.player_id, player_display_name(p.nickname, p.game_player_name),
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
    GROUP BY b.player_id, p.nickname, p.game_player_name
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
