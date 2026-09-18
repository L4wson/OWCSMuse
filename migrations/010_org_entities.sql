-- Orgs are resolvable entities too, so "Al Qadsiah" finds the org rather than
-- one season's team id. Team ids stay resolvable for precise queries.
DROP MATERIALIZED VIEW IF EXISTS entity_names CASCADE;
CREATE MATERIALIZED VIEW entity_names AS
SELECT 'player'::text AS entity_type, p.player_id AS entity_id, p.nickname AS name,
       'current_nickname'::text AS name_kind, fold_name(p.nickname) AS name_folded,
       p.nickname AS current_name, p.last_seen_at
FROM players p
UNION ALL
SELECT 'player', p.player_id, p.game_player_name, 'game_name', fold_name(p.game_player_name), p.nickname, p.last_seen_at
FROM players p
WHERE p.game_player_name IS NOT NULL AND fold_name(p.game_player_name) <> fold_name(p.nickname)
UNION ALL
SELECT 'player', pn.player_id, pn.nickname, 'historical_nickname', fold_name(pn.nickname), p.nickname, pn.last_seen_at
FROM player_nicknames pn JOIN players p ON p.player_id = pn.player_id
WHERE pn.nickname <> p.nickname
UNION ALL
-- an org, under its own name and under every team name it has used
SELECT 'org', o.org_id, o.name, 'current_name', fold_name(o.name), o.name, max(t.last_seen_at)
FROM orgs o JOIN team_orgs tm ON tm.org_id = o.org_id JOIN teams t ON t.team_id = tm.team_id
GROUP BY o.org_id, o.name
UNION ALL
SELECT 'org', tm.org_id, t.name, 'historical_team_name', fold_name(t.name), o.name, t.last_seen_at
FROM team_orgs tm JOIN teams t ON t.team_id = tm.team_id JOIN orgs o ON o.org_id = tm.org_id
WHERE fold_name(t.name) <> fold_name(o.name)
UNION ALL
-- team ids that belong to no org stay addressable as themselves
SELECT 'team', t.team_id, t.name, 'current_name', fold_name(t.name), t.name, t.last_seen_at
FROM teams t LEFT JOIN team_orgs tm ON tm.team_id = t.team_id
WHERE t.name IS NOT NULL AND tm.team_id IS NULL
UNION ALL
SELECT 'team', tn.team_id, tn.name, 'historical_name', fold_name(tn.name), t.name, tn.last_seen_at
FROM team_names tn JOIN teams t ON t.team_id = tn.team_id
LEFT JOIN team_orgs tm ON tm.team_id = tn.team_id
WHERE tn.name <> t.name AND tm.team_id IS NULL;
CREATE INDEX entity_names_idx ON entity_names (entity_type, name_folded);
