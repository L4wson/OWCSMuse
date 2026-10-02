-- Date-bounded team-to-org mapping.
--
-- A FACEIT team id mapped to an org for all time over-counts across an
-- acquisition: Virtus pro took over the Ex Oblivione roster and FACEIT kept the
-- team id, so every 2024 series of Ex Oblivione became Virtus pro's. A roster an
-- org acquired is not that org's history. A mapping is now valid over a window
-- [valid_from, valid_to); outside it the team id is itself, keyed `team:<id>`,
-- displayed and searchable by the name it carried then, exactly as an unmapped
-- id is today. A decision with no window is unbounded (-infinity, infinity), so
-- every existing decision means what it meant before.
--
-- Identity is therefore a function of (team id, when): team_identity_at(). The
-- fact views join it at the series' own time; `team_identity` stays as the
-- current view (identity now) for display and status.

ALTER TABLE team_orgs ADD COLUMN valid_from timestamptz NOT NULL DEFAULT '-infinity';
ALTER TABLE team_orgs ADD COLUMN valid_to   timestamptz NOT NULL DEFAULT 'infinity';
ALTER TABLE team_orgs ADD CONSTRAINT team_orgs_window_order CHECK (valid_from < valid_to);
ALTER TABLE team_orgs DROP CONSTRAINT team_orgs_pkey;
ALTER TABLE team_orgs ADD PRIMARY KEY (team_id, valid_from);

-- One team id cannot belong to two orgs at once. A trigger rather than an
-- exclusion constraint: that would need the btree_gist extension, which this
-- schema does not own.
CREATE OR REPLACE FUNCTION team_orgs_no_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM team_orgs w
         WHERE w.team_id = NEW.team_id
           AND (TG_OP = 'INSERT' OR w.valid_from <> OLD.valid_from)   -- an UPDATE must not collide with its own old row
           AND w.valid_from < NEW.valid_to AND NEW.valid_from < w.valid_to
    ) THEN
        RAISE EXCEPTION 'team_orgs: window [%, %) for team % overlaps an existing one',
            NEW.valid_from, NEW.valid_to, NEW.team_id;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS team_orgs_no_overlap ON team_orgs;
CREATE TRIGGER team_orgs_no_overlap BEFORE INSERT OR UPDATE ON team_orgs
    FOR EACH ROW EXECUTE FUNCTION team_orgs_no_overlap();

-- The name a team id carried outside its org window: the latest name whose first
-- sighting falls outside every window (NULL when it never carried one, or when
-- the id has no window at all - then teams.name is the name, as before).
CREATE OR REPLACE FUNCTION team_era_name(p_team_id text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT tn.name FROM {{schema}}.team_names tn
     WHERE tn.team_id = p_team_id
       AND EXISTS (SELECT 1 FROM {{schema}}.team_orgs w WHERE w.team_id = p_team_id)
       AND NOT EXISTS (SELECT 1 FROM {{schema}}.team_orgs w WHERE w.team_id = p_team_id
                         AND tn.first_seen_at >= w.valid_from AND tn.first_seen_at < w.valid_to)
     ORDER BY tn.last_seen_at DESC LIMIT 1
$$;

-- Who a team id was at a moment.
--
-- Every relation and function the two bodies name is written {{schema}}.name:
-- `migrate` substitutes the schema it runs in (OWCS_DB_SCHEMA). A LANGUAGE sql
-- body is re-parsed by name every time a query that calls it is planned, and
-- PostgreSQL 17 plans CREATE/REFRESH MATERIALIZED VIEW under search_path =
-- pg_catalog, pg_temp: unqualified, `teams` is not found "during inlining" and
-- every refresh fails (production, 2026-10-01). SET search_path on the function
-- would fix that too but blocks inlining, and these run once per fact row: it
-- made the golden refresh 44x slower (0.44 s -> 19 s). Qualifying keeps inlining.
CREATE OR REPLACE FUNCTION team_identity_at(p_team_id text, p_at timestamptz)
RETURNS TABLE (team_id text, org_id text, org_key text, display_name text, team_name text, mapped boolean)
LANGUAGE sql STABLE AS $$
    SELECT t.team_id, w.org_id,
           COALESCE(w.org_id, 'team:' || t.team_id),
           COALESCE(o.name, CASE WHEN w.org_id IS NULL THEN {{schema}}.team_era_name(t.team_id) END, t.name),
           t.name, (w.org_id IS NOT NULL)
      FROM {{schema}}.teams t
      LEFT JOIN {{schema}}.team_orgs w ON w.team_id = t.team_id AND p_at IS NOT NULL
                           AND p_at >= w.valid_from AND p_at < w.valid_to
      LEFT JOIN {{schema}}.orgs o ON o.org_id = w.org_id
     WHERE t.team_id = p_team_id
$$;

-- Identity now: what `orgs status` and display code read. Same columns as before.
CREATE OR REPLACE VIEW team_identity AS
SELECT ti.team_id, ti.org_id, ti.org_key, ti.display_name, ti.team_name, ti.mapped
FROM teams t CROSS JOIN LATERAL team_identity_at(t.team_id, now()) ti;

-- Every org_key that can appear in a fact row, with the name to show for it:
-- orgs by their name, and each team id as itself by the name of its own era.
CREATE OR REPLACE VIEW identity_keys AS
SELECT org_id AS org_key, name AS display_name FROM orgs
UNION ALL
SELECT 'team:' || t.team_id, COALESCE(team_era_name(t.team_id), t.name) FROM teams t;

-- ------------------------------------------------- facts: identity at series time
-- Column lists are unchanged (CREATE OR REPLACE); only the identity join moves
-- from "team id -> org, always" to "team id at this series' time -> org".

CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    m.championship_id, c.season, c.scope_region AS region,
    x.at AS started_at,
    r.map_name, r.game_mode,
    (r.winner_team_id = t.team_id) AS won,
    (r.winner_team_id IS NULL)     AS drawn,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name,
    r.source AS map_source
FROM match_rounds r
JOIN matches       m ON m.match_id = r.match_id
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (SELECT coalesce(m.liquipedia_played_at,
                                    match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS at) x
CROSS JOIN LATERAL (VALUES
    (r.team1_team_id, r.team2_team_id, r.team1_score, r.team2_score),
    (r.team2_team_id, r.team1_team_id, r.team2_score, r.team1_score)
) AS t(team_id, opponent_team_id, score, opp_score)
LEFT JOIN LATERAL team_identity_at(t.team_id, x.at) ti ON true
LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, x.at) oi ON true
WHERE m.ingest_state IN ('complete', 'result_only') AND c.include AND t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_team_matches AS
SELECT
    m.match_id, t.team_id, t.opponent_team_id, t.faction,
    m.championship_id, c.season, c.scope_region AS region,
    x.at AS started_at,
    m.best_of, m.maps_played,
    (m.winner_team_id = t.team_id) AS won,
    t.score AS map_wins, t.opp_score AS map_losses,
    m.ingest_state,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name
FROM matches m
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (SELECT coalesce(m.liquipedia_played_at,
                                    match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS at) x
CROSS JOIN LATERAL (VALUES
    (m.faction1_team_id, m.faction2_team_id, 'faction1', m.faction1_score, m.faction2_score),
    (m.faction2_team_id, m.faction1_team_id, 'faction2', m.faction2_score, m.faction1_score)
) AS t(team_id, opponent_team_id, faction, score, opp_score)
LEFT JOIN LATERAL team_identity_at(t.team_id, x.at) ti ON true
LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, x.at) oi ON true
WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include AND t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_player_maps AS
SELECT
    mp.match_id, mp.round_number, mp.player_id, mp.team_id,
    CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END AS opponent_team_id,
    m.championship_id, c.season, c.scope_region AS region, c.tier,
    x.at AS started_at,
    r.map_name, r.game_mode,
    (r.winner_team_id = mp.team_id) AS map_won,
    (r.winner_team_id IS NULL)      AS map_drawn,
    mp.role, mp.eliminations, mp.final_blows, mp.deaths, mp.assists,
    mp.solo_kills, mp.multi_kills, mp.environmental_kills,
    mp.damage_dealt, mp.healing_done, mp.damage_mitigated, mp.objective_time, mp.time_played,
    mp.stats,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name
FROM match_players mp
JOIN match_rounds  r ON (r.match_id, r.round_number) = (mp.match_id, mp.round_number)
JOIN matches       m ON m.match_id = mp.match_id
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (SELECT match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS at) x
LEFT JOIN LATERAL team_identity_at(mp.team_id, x.at) ti ON true
LEFT JOIN LATERAL team_identity_at(CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END, x.at) oi ON true
WHERE m.ingest_state = 'complete' AND c.include;

-- -------------------------------------------------- searchable names, by era
-- An org's searchable names are the names its team ids carried INSIDE their
-- windows (every name, not only the current one: the rename-history rule). A
-- team id with an era of its own - no window, or matches outside its window -
-- is a `team` entity named by that era, with its own activity.

DROP MATERIALIZED VIEW IF EXISTS entity_names;
CREATE MATERIALIZED VIEW entity_names AS
WITH player_activity AS (
    SELECT player_id,
           count(DISTINCT match_id) AS n,
           array_agg(DISTINCT season ORDER BY season) FILTER (WHERE season IS NOT NULL) AS seasons,
           min(started_at) AS first_at, max(started_at) AS last_at
    FROM fact_player_maps GROUP BY player_id
), team_activity AS (                                   -- the team-as-itself era only
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
), org_names AS (                                       -- names carried inside a window
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
                    AND tn.first_seen_at >= w.valid_from AND tn.first_seen_at < w.valid_to);
CREATE INDEX entity_names_idx ON entity_names (entity_type, name_folded);
CREATE INDEX entity_names_id_idx ON entity_names (entity_id);
