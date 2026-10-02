-- A Liquipedia team name resolves at the series' own time.
--
-- In OWCS a roster pickup lands on a stage boundary: "Extinction" was team id
-- 2b7f8ef6 in 2025 and a35f8d47 in 2026, "The Kafe" is a35f8d47 from 2026 Stage 2.
-- A name-to-entity anchor therefore holds over a window, like a team-to-org
-- mapping does (026), and the series view and the integrity check resolve a
-- name against the window that covers the series' played_at.

ALTER TABLE entity_anchors ADD COLUMN valid_from timestamptz NOT NULL DEFAULT '-infinity';
ALTER TABLE entity_anchors ADD COLUMN valid_to   timestamptz NOT NULL DEFAULT 'infinity';
ALTER TABLE entity_anchors ADD CONSTRAINT entity_anchors_window_order CHECK (valid_from < valid_to);
ALTER TABLE entity_anchors DROP CONSTRAINT entity_anchors_pkey;
ALTER TABLE entity_anchors ADD PRIMARY KEY (source, anchor_kind, anchor, region, valid_from);

CREATE OR REPLACE VIEW series AS
WITH linked AS (
    SELECT lk.faceit_match_id, lk.lp_objectname, lk.tier, lm.page_url, lm.played_at AS lp_played_at
      FROM liquipedia_links lk JOIN liquipedia_matches lm ON lm.objectname = lk.lp_objectname
     WHERE lk.faceit_match_id IS NOT NULL AND NOT lk.provisional AND coalesce(lk.decision, '') <> 'rejected'
), lp_side AS (                                                   -- a Liquipedia team name resolved by a decided anchor, at the series' time
    SELECT lm.objectname, s.side, s.name,
           CASE a.entity_type WHEN 'team' THEN a.entity_id
                ELSE 'lp:team:' || a.anchor || CASE WHEN a.region <> '' THEN '|' || a.region ELSE '' END END AS team_id
      FROM liquipedia_matches lm
      CROSS JOIN LATERAL (VALUES (1, lm.team1_name), (2, lm.team2_name)) AS s(side, name)
      JOIN entity_anchors a ON a.anchor_kind = 'team_name' AND a.anchor = fold_name(s.name)
                           AND (a.region = '' OR a.region = coalesce(lm.region, ''))
                           AND lm.played_at >= a.valid_from AND lm.played_at < a.valid_to
      JOIN teams t ON t.team_id = CASE a.entity_type WHEN 'team' THEN a.entity_id
                ELSE 'lp:team:' || a.anchor || CASE WHEN a.region <> '' THEN '|' || a.region ELSE '' END END
)
SELECT 'faceit:' || m.match_id AS series_id,
       m.match_id, m.match_id AS faceit_match_id, l.lp_objectname,
       m.championship_id,
       coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS played_at,
       CASE WHEN m.liquipedia_played_at IS NOT NULL THEN 'liquipedia' ELSE 'faceit' END AS played_at_source,
       m.best_of, 'faceit'::text AS best_of_source,
       m.faction1_team_id AS side1_team_id, m.faction2_team_id AS side2_team_id,
       m.faction1_score AS score1, m.faction2_score AS score2,
       CASE m.winner_faction WHEN 'faction1' THEN 1 WHEN 'faction2' THEN 2 ELSE 0 END AS winner_side,
       'faceit'::text AS result_source,
       m.maps_played,
       CASE WHEN EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = m.match_id AND r.source = 'liquipedia') THEN 'liquipedia'
            WHEN EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = m.match_id) THEN 'faceit' END AS maps_source,
       m.ingest_state AS state,
       EXISTS (SELECT 1 FROM match_players mp WHERE mp.match_id = m.match_id) AS has_player_stats,
       coalesce(l.tier, 'single-source') AS link_tier,
       ARRAY['faceit'::text] || CASE WHEN l.lp_objectname IS NOT NULL THEN ARRAY['liquipedia'::text] ELSE ARRAY[]::text[] END AS sources,
       'https://www.faceit.com/en/ow2/room/' || m.match_id AS source_url,
       l.page_url AS liquipedia_page_url
  FROM matches m
  JOIN championships c ON c.championship_id = m.championship_id
  LEFT JOIN linked l ON l.faceit_match_id = m.match_id
 WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include
UNION ALL
SELECT 'lp:' || lm.objectname,
       'lp:' || lm.objectname, NULL, lm.objectname,
       lm.championship_id,
       lm.played_at, 'liquipedia',
       lm.best_of, 'liquipedia',
       s1.team_id, s2.team_id,
       lm.score1, lm.score2,
       lm.winner, 'liquipedia',
       lm.n_games,
       NULL,
       'result_only',
       false,
       'single-source',
       ARRAY['liquipedia'::text],
       lm.page_url, lm.page_url
  FROM liquipedia_matches lm
  JOIN championships c ON c.championship_id = lm.championship_id AND c.include
  JOIN lp_side s1 ON s1.objectname = lm.objectname AND s1.side = 1
  JOIN lp_side s2 ON s2.objectname = lm.objectname AND s2.side = 2
 WHERE lm.finished AND NOT lm.placeholder AND lm.score1 IS NOT NULL AND lm.score2 IS NOT NULL
   AND lm.winner IN (1, 2)
   AND EXISTS (SELECT 1 FROM liquipedia_links lk
                WHERE lk.lp_objectname = lm.objectname AND lk.faceit_match_id IS NULL
                  AND ((lk.tier = 'unmatched' AND lk.evidence->>'kind' = 'no_faceit_counterpart')
                       OR lk.decision = 'rejected'));

-- searchable names: a Liquipedia name attaches to the entity whose anchor window overlaps the name's sightings
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
    SELECT 'player' AS entity_type, p.player_id AS entity_id, player_display_name(p.nickname, p.game_player_name) AS current_name,
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
