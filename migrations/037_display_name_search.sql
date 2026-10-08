-- 037: a display name is a searchable name.
--
-- An owner's display name (players.display_name, 035) is what every answer shows, but 035 left search untouched, so
-- the name a reader sees was not one they could ask by: "ZZZ record" found nobody while "zss" (his in-game name)
-- worked, and "Astro" worked only as a prefix of the nickname Astronexz. entity_names gains a 'display_name' row for
-- every player whose display name is not already their nickname or in-game name. Otherwise identical to 035's
-- definition. `check` (display_names_searchable) proves every entity's shown name is one of its own search names.

DROP MATERIALIZED VIEW IF EXISTS entity_names;
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
    FROM fact_team_matches WHERE org_id IS NULL GROUP BY team_id
), org_activity AS (
    SELECT org_id,
           count(DISTINCT match_id) AS n,
           array_agg(DISTINCT season ORDER BY season) FILTER (WHERE season IS NOT NULL) AS seasons,
           min(started_at) AS first_at, max(started_at) AS last_at
    FROM fact_team_matches WHERE org_id IS NOT NULL GROUP BY org_id
), team_entities AS (
    SELECT t.team_id, t.name AS current_name, t.last_seen_at
      FROM teams t
     WHERE t.name IS NOT NULL AND NOT EXISTS (SELECT 1 FROM team_orgs w WHERE w.team_id = t.team_id)
    UNION ALL
    SELECT t.team_id, COALESCE(team_era_name(t.team_id), t.name), t.last_seen_at
      FROM teams t
     WHERE EXISTS (SELECT 1 FROM team_orgs w WHERE w.team_id = t.team_id)
       AND EXISTS (SELECT 1 FROM team_activity ta WHERE ta.team_id = t.team_id)
), org_names AS (
    SELECT w.org_id, tn.name, max(tn.last_seen_at) AS last_seen_at
      FROM team_orgs w JOIN team_names tn ON tn.team_id = w.team_id
     WHERE tn.first_seen_at >= w.valid_from AND tn.first_seen_at < w.valid_to
     GROUP BY w.org_id, tn.name
    UNION
    SELECT w.org_id, t.name, max(t.last_seen_at)
      FROM team_orgs w JOIN teams t ON t.team_id = w.team_id
     WHERE t.name IS NOT NULL
       AND (t.last_seen_at IS NULL OR (t.last_seen_at >= w.valid_from AND t.last_seen_at < w.valid_to))
     GROUP BY w.org_id, t.name
), current_names AS (                       -- what each entity is called, for the Liquipedia rows below
    SELECT 'player' AS entity_type, p.player_id AS entity_id, player_display_name(p.display_name, p.nickname, p.game_player_name) AS current_name,
           p.last_seen_at, coalesce(pa.n, 0) AS matches, pa.seasons, pa.first_at, pa.last_at
      FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
    UNION ALL
    SELECT 'org', o.org_id, o.name, NULL::timestamptz, coalesce(oa.n, 0), oa.seasons, oa.first_at, oa.last_at
      FROM orgs o LEFT JOIN org_activity oa ON oa.org_id = o.org_id
    UNION ALL
    SELECT 'team', te.team_id, te.current_name, te.last_seen_at, coalesce(ta.n, 0), ta.seasons, ta.first_at, ta.last_at
      FROM team_entities te LEFT JOIN team_activity ta ON ta.team_id = te.team_id
)
SELECT 'player'::text AS entity_type, p.player_id AS entity_id, p.nickname AS name,
       'current_nickname'::text AS name_kind, fold_name(p.nickname) AS name_folded,
       player_display_name(p.display_name, p.nickname, p.game_player_name) AS current_name, p.last_seen_at, coalesce(pa.n, 0) AS matches,
       pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
UNION ALL
SELECT 'player', p.player_id, p.game_player_name, 'game_name', fold_name(p.game_player_name),
       player_display_name(p.display_name, p.nickname, p.game_player_name),
       p.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
WHERE p.game_player_name IS NOT NULL AND fold_name(p.game_player_name) <> fold_name(p.nickname)
UNION ALL
-- the owner's display name (037): shown everywhere, so searchable too
SELECT 'player', p.player_id, p.display_name, 'display_name', fold_name(p.display_name),
       player_display_name(p.display_name, p.nickname, p.game_player_name),
       p.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM players p LEFT JOIN player_activity pa ON pa.player_id = p.player_id
WHERE nullif(p.display_name, '') IS NOT NULL
  AND fold_name(p.display_name) NOT IN (fold_name(p.nickname), fold_name(coalesce(p.game_player_name, '')))
UNION ALL
SELECT 'player', pn.player_id, pn.nickname, 'historical_nickname', fold_name(pn.nickname),
       player_display_name(p.display_name, p.nickname, p.game_player_name),
       pn.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM player_nicknames pn JOIN players p ON p.player_id = pn.player_id
LEFT JOIN player_activity pa ON pa.player_id = pn.player_id
WHERE pn.nickname <> p.nickname
UNION ALL
SELECT 'player', gn.player_id, gn.game_player_name, 'historical_game_name', fold_name(gn.game_player_name),
       player_display_name(p.display_name, p.nickname, p.game_player_name),
       gn.last_seen_at, coalesce(pa.n, 0), pa.seasons, pa.first_at, pa.last_at
FROM player_game_names gn JOIN players p ON p.player_id = gn.player_id
LEFT JOIN player_activity pa ON pa.player_id = gn.player_id
WHERE gn.game_player_name <> coalesce(p.game_player_name, '')
UNION ALL
SELECT 'org', o.org_id, o.name, 'current_name', fold_name(o.name), o.name, max(t.last_seen_at),
       coalesce(max(oa.n), 0), max(oa.seasons), min(oa.first_at), max(oa.last_at)
FROM orgs o JOIN team_orgs w ON w.org_id = o.org_id JOIN teams t ON t.team_id = w.team_id
LEFT JOIN org_activity oa ON oa.org_id = o.org_id
GROUP BY o.org_id, o.name
UNION ALL
SELECT 'org', n.org_id, n.name, 'historical_team_name', fold_name(n.name), o.name, n.last_seen_at,
       coalesce(oa.n, 0), oa.seasons, oa.first_at, oa.last_at
FROM org_names n JOIN orgs o ON o.org_id = n.org_id
LEFT JOIN org_activity oa ON oa.org_id = n.org_id
WHERE fold_name(n.name) <> fold_name(o.name)
UNION ALL
SELECT 'team', te.team_id, te.current_name, 'current_name', fold_name(te.current_name), te.current_name,
       te.last_seen_at, coalesce(ta.n, 0), ta.seasons, ta.first_at, ta.last_at
FROM team_entities te LEFT JOIN team_activity ta ON ta.team_id = te.team_id
WHERE te.current_name IS NOT NULL
UNION ALL
SELECT 'team', tn.team_id, tn.name, 'historical_name', fold_name(tn.name), te.current_name, tn.last_seen_at,
       coalesce(ta.n, 0), ta.seasons, ta.first_at, ta.last_at
FROM team_entities te JOIN team_names tn ON tn.team_id = te.team_id
LEFT JOIN team_activity ta ON ta.team_id = te.team_id
WHERE tn.name <> te.current_name
  AND NOT EXISTS (SELECT 1 FROM team_orgs w WHERE w.team_id = tn.team_id
                    AND tn.first_seen_at >= w.valid_from AND tn.first_seen_at < w.valid_to)
-- Liquipedia: every handle and real name an anchored player's page has carried ...
UNION ALL
SELECT 'player', a.entity_id, n.name, n.kind, fold_name(n.name), c.current_name, n.last_seen_at,
       c.matches, c.seasons, c.first_at, c.last_at
FROM entity_anchors a
JOIN lp_player_names n ON n.page = a.anchor
JOIN current_names c ON c.entity_type = 'player' AND c.entity_id = a.entity_id
WHERE a.anchor_kind = 'player_page' AND fold_name(n.name) <> fold_name(c.current_name)
-- ... and every name an anchored team or org has carried on Liquipedia (the decided name itself, and its template's history)
UNION ALL
SELECT a.entity_type, a.entity_id, n.name, 'lp_team_name', fold_name(n.name), c.current_name, n.last_seen_at,
       c.matches, c.seasons, c.first_at, c.last_at
FROM entity_anchors a
JOIN current_names c ON c.entity_type = a.entity_type AND c.entity_id = a.entity_id
JOIN LATERAL (
    SELECT t.name, t.last_seen_at FROM lp_team_names t
     WHERE fold_name(t.name) = a.anchor AND (a.region = '' OR t.region = a.region OR t.region = '')
       AND t.first_seen_at < a.valid_to AND t.last_seen_at >= a.valid_from
    UNION
    SELECT t2.name, t2.last_seen_at FROM lp_team_names t1 JOIN lp_team_names t2 ON t2.template = t1.template
     WHERE t1.template IS NOT NULL AND fold_name(t1.name) = a.anchor AND (a.region = '' OR t1.region = a.region OR t1.region = '')
       AND t1.first_seen_at < a.valid_to AND t1.last_seen_at >= a.valid_from
       AND t2.first_seen_at < a.valid_to AND t2.last_seen_at >= a.valid_from
) n ON true
WHERE a.anchor_kind = 'team_name' AND fold_name(n.name) <> fold_name(c.current_name);
CREATE INDEX entity_names_idx ON entity_names (entity_type, name_folded);
CREATE INDEX entity_names_id_idx ON entity_names (entity_id);
