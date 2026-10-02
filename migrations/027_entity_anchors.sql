-- Identity without FACEIT: anchors, and Liquipedia's own name history.
--
-- Every entity so far is keyed by a FACEIT id (players.player_id, teams.team_id)
-- and orgs by a slug reached only through FACEIT team ids. Korean teams and
-- players have no FACEIT id. An anchor is "this entity is known in this source
-- by this handle": a FACEIT GUID is implicitly its own anchor (the id IS the
-- anchor), a Liquipedia player page or team name is an explicit row here. One
-- entity may carry anchors in both sources; a Liquipedia-born entity carries one
-- and gets an id of its own (`lp:player:<page>`, `lp:team:<template>`) in the
-- same players / teams tables, so everything keyed on those ids keeps working
-- and it shows, visibly, as itself.
--
-- An anchor arrives only through a reviewed decision (scope/player_identity_decisions.json,
-- scope/liquipedia_team_map.json), never from a name match made in code.

CREATE TABLE entity_anchors (
    entity_type text NOT NULL CHECK (entity_type IN ('player', 'team', 'org')),
    entity_id   text NOT NULL,
    source      text NOT NULL CHECK (source IN ('liquipedia')),      -- FACEIT anchors are the ids themselves
    anchor_kind text NOT NULL CHECK (anchor_kind IN ('player_page', 'team_name')),
    anchor      text NOT NULL,                                       -- the page title, or the folded team name
    region      text NOT NULL DEFAULT '',                            -- team names split by region ('na' / 'emea'), else ''
    basis       text NOT NULL CHECK (basis IN ('decision', 'team_map', 'born')),
    note        text,
    decided_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, anchor_kind, anchor, region)                -- an anchor names one entity
);
CREATE INDEX entity_anchors_entity_idx ON entity_anchors (entity_type, entity_id);

-- Liquipedia's declared line-ups, a parsed copy of match2opponents[].match2players (rebuildable from raw_payloads).
ALTER TABLE liquipedia_matches ADD COLUMN team1_template text;
ALTER TABLE liquipedia_matches ADD COLUMN team2_template text;
ALTER TABLE liquipedia_matches ADD COLUMN team1_page text;
ALTER TABLE liquipedia_matches ADD COLUMN team2_page text;

CREATE TABLE liquipedia_match_players (
    lp_objectname text     NOT NULL REFERENCES liquipedia_matches (objectname) ON DELETE CASCADE,
    side          smallint NOT NULL CHECK (side IN (1, 2)),
    page          text     NOT NULL,          -- player page title: the anchor
    handle        text     NOT NULL,          -- the name shown
    real_name     text,                       -- from the page's "(Given Family)" disambiguation, when there is one
    nationality   text,
    PRIMARY KEY (lp_objectname, side, page)
);
CREATE INDEX liquipedia_match_players_page_idx ON liquipedia_match_players (page);

-- Name history on the Liquipedia side: every handle and real name a page has carried, every name a team
-- template has carried, with first/last seen. The rename-history rule, for Liquipedia-anchored entities.
CREATE OR REPLACE VIEW lp_player_names AS
SELECT p.page, n.name, n.kind, min(m.played_at) AS first_seen_at, max(m.played_at) AS last_seen_at,
       count(DISTINCT m.objectname) AS matches
  FROM liquipedia_match_players p
  JOIN liquipedia_matches m ON m.objectname = p.lp_objectname
  CROSS JOIN LATERAL (VALUES (p.handle, 'lp_handle'), (p.real_name, 'lp_real_name')) AS n(name, kind)
 WHERE n.name IS NOT NULL AND n.name <> ''
 GROUP BY p.page, n.name, n.kind;

CREATE OR REPLACE VIEW lp_team_names AS
SELECT t.template, t.name, t.region, min(m.played_at) AS first_seen_at, max(m.played_at) AS last_seen_at,
       count(DISTINCT m.objectname) AS matches
  FROM liquipedia_matches m
  CROSS JOIN LATERAL (VALUES (m.team1_template, m.team1_name), (m.team2_template, m.team2_name)) AS t0(template, name)
  CROSS JOIN LATERAL (SELECT t0.template, t0.name, CASE WHEN m.region IN ('na', 'emea') THEN m.region ELSE '' END AS region) t
 WHERE t.name IS NOT NULL AND t.name <> '' AND NOT m.placeholder
 GROUP BY t.template, t.name, t.region;

-- ------------------------------------------------------------- searchable names
-- As in 026, plus: the Liquipedia names of every anchored entity.
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
    UNION
    SELECT t2.name, t2.last_seen_at FROM lp_team_names t1 JOIN lp_team_names t2 ON t2.template = t1.template
     WHERE t1.template IS NOT NULL AND fold_name(t1.name) = a.anchor AND (a.region = '' OR t1.region = a.region OR t1.region = '')
) n ON true
WHERE a.anchor_kind = 'team_name' AND fold_name(n.name) <> fold_name(c.current_name);
CREATE INDEX entity_names_idx ON entity_names (entity_type, name_folded);
CREATE INDEX entity_names_id_idx ON entity_names (entity_id);
