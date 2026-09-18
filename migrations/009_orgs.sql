-- Org-level team identity.
--
-- FACEIT team ids are not stable across seasons: "Al qadsiah" (2025) and
-- "qadsiah" (2026) are two team ids for one organisation, so every
-- cross-season team query silently undercounts. This mirrors how players are
-- handled: players.player_id is the stable GUID and nicknames are mutable
-- history; here orgs.org_id is the stable identity and team ids are the
-- mutable per-season handles.
--
-- A team id belongs to exactly one org (PRIMARY KEY on team_id); an org has
-- many team ids. Mappings only ever arrive from a reviewed decision file, never
-- from a fuzzy name match: "Team Liquid" and "Liquid Academy" are different
-- organisations.

CREATE TABLE orgs (
    org_id     text PRIMARY KEY,               -- stable slug, e.g. 'al-qadsiah'
    name       text NOT NULL,                  -- display name
    note       text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE team_orgs (
    team_id    text PRIMARY KEY REFERENCES teams (team_id),
    org_id     text NOT NULL REFERENCES orgs (org_id),
    source     text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'auto')),
    evidence   jsonb,
    decided_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX team_orgs_org_idx ON team_orgs (org_id);

-- Every team id, with its org when one has been decided. An unmapped team id
-- stays itself: org_key is prefixed `team:` so an unmapped row is visibly a raw
-- team id in any grouping, never silently folded into something else.
CREATE OR REPLACE VIEW team_identity AS
SELECT
    t.team_id,
    tm.org_id,
    COALESCE(tm.org_id, 'team:' || t.team_id) AS org_key,
    COALESCE(o.name, t.name)                  AS display_name,
    t.name                                    AS team_name,
    (tm.org_id IS NOT NULL)                   AS mapped
FROM teams t
LEFT JOIN team_orgs tm ON tm.team_id = t.team_id
LEFT JOIN orgs o       ON o.org_id = tm.org_id;

-- ---------------------------------------------------------------- org-aware facts

CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    m.championship_id, c.season, c.scope_region AS region, m.started_at, r.map_name, r.game_mode,
    (r.winner_team_id = t.team_id) AS won,
    (r.winner_team_id IS NULL)     AS drawn,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name
FROM match_rounds r
JOIN matches       m ON m.match_id = r.match_id
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (VALUES
    (r.team1_team_id, r.team2_team_id, r.team1_score, r.team2_score),
    (r.team2_team_id, r.team1_team_id, r.team2_score, r.team1_score)
) AS t(team_id, opponent_team_id, score, opp_score)
LEFT JOIN team_identity ti ON ti.team_id = t.team_id
LEFT JOIN team_identity oi ON oi.team_id = t.opponent_team_id
WHERE m.ingest_state = 'complete' AND c.include AND t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_team_matches AS
SELECT
    m.match_id, t.team_id, t.opponent_team_id, t.faction,
    m.championship_id, c.season, c.scope_region AS region, m.started_at, m.best_of, m.maps_played,
    (m.winner_team_id = t.team_id) AS won,
    t.score AS map_wins, t.opp_score AS map_losses,
    m.ingest_state,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name
FROM matches m
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (VALUES
    (m.faction1_team_id, m.faction2_team_id, 'faction1', m.faction1_score, m.faction2_score),
    (m.faction2_team_id, m.faction1_team_id, 'faction2', m.faction2_score, m.faction1_score)
) AS t(team_id, opponent_team_id, faction, score, opp_score)
LEFT JOIN team_identity ti ON ti.team_id = t.team_id
LEFT JOIN team_identity oi ON oi.team_id = t.opponent_team_id
WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include AND t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_player_maps AS
SELECT
    mp.match_id, mp.round_number, mp.player_id, mp.team_id,
    CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END AS opponent_team_id,
    m.championship_id, c.season, c.scope_region AS region, c.tier, m.started_at, r.map_name, r.game_mode,
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
LEFT JOIN team_identity ti ON ti.team_id = mp.team_id
LEFT JOIN team_identity oi ON oi.team_id = (CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END)
WHERE m.ingest_state = 'complete' AND c.include;

-- ---------------------------------------------------------------- versus, at map grain

-- One row per player per map per opposing player: the grain a "map record
-- against X" question actually asks about.
CREATE MATERIALIZED VIEW fact_player_versus AS
SELECT
    a.match_id, a.round_number, a.championship_id, a.season, a.region, a.started_at, a.map_name, a.game_mode,
    a.player_id, a.team_id, a.org_key, a.display_name,
    b.player_id AS opponent_player_id, b.team_id AS opponent_team_id,
    b.org_key   AS opponent_org_key,   b.display_name AS opponent_display_name,
    a.map_won AS won, a.map_drawn AS drawn,
    a.eliminations, a.deaths, a.assists, a.damage_dealt, a.healing_done, a.damage_mitigated
FROM fact_player_maps a
JOIN fact_player_maps b
  ON b.match_id = a.match_id AND b.round_number = a.round_number AND b.team_id IS DISTINCT FROM a.team_id;
CREATE INDEX fact_player_versus_pair_idx ON fact_player_versus (player_id, opponent_player_id);
CREATE INDEX fact_player_versus_org_idx  ON fact_player_versus (player_id, opponent_org_key);

-- Org vs org at map grain, each pairing once per side.
CREATE MATERIALIZED VIEW agg_org_versus_maps AS
SELECT
    org_key, display_name, opponent_org_key, opponent_display_name, season, championship_id,
    count(*)                                     AS maps,
    count(DISTINCT match_id)                     AS matches,
    count(*) FILTER (WHERE won)                  AS map_wins,
    count(*) FILTER (WHERE NOT won AND NOT drawn) AS map_losses,
    count(*) FILTER (WHERE drawn)                AS draws,
    sum(score) AS points_for, sum(opp_score) AS points_against,
    min(started_at) AS first_map_at, max(started_at) AS last_map_at
FROM fact_team_maps
WHERE org_key IS NOT NULL AND opponent_org_key IS NOT NULL
GROUP BY org_key, display_name, opponent_org_key, opponent_display_name, season, championship_id;
CREATE INDEX agg_org_versus_maps_idx ON agg_org_versus_maps (org_key, opponent_org_key);

-- Series between two orgs whose maps were never recorded (result_only), so a
-- versus answer can say how much is missing instead of quietly deflating.
CREATE OR REPLACE VIEW org_versus_missing AS
SELECT
    org_key, display_name, opponent_org_key, opponent_display_name, season,
    count(*) AS matches_without_map_stats,
    sum(map_wins + map_losses) AS maps_implied_by_series_score,
    min(started_at) AS first_match_at, max(started_at) AS last_match_at
FROM fact_team_matches
WHERE ingest_state = 'result_only' AND org_key IS NOT NULL AND opponent_org_key IS NOT NULL
GROUP BY org_key, display_name, opponent_org_key, opponent_display_name, season;
