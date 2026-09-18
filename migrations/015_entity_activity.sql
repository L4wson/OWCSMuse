-- A candidate list has to be choosable.
--
-- When two entities share a name, "48 matches" and a UUID is not enough for a
-- person to tell them apart - the question they are answering is usually "which
-- era is this one?". Seasons and a date range answer that, and entity_names is
-- already computing the match count from the same facts.

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
       p.nickname AS current_name, p.last_seen_at, coalesce(pa.n, 0) AS matches,
       pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
UNION ALL
SELECT 'player', p.player_id, p.game_player_name, 'game_name', fold_name(p.game_player_name), p.nickname,
       p.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
WHERE p.game_player_name IS NOT NULL AND fold_name(p.game_player_name) <> fold_name(p.nickname)
UNION ALL
SELECT 'player', pn.player_id, pn.nickname, 'historical_nickname', fold_name(pn.nickname), p.nickname,
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
