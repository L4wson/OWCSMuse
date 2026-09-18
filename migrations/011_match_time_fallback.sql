-- 30 matches carry no started_at but all of them carry finished_at: admin-scored
-- deciders and the Dreamhack Dallas LAN never started on FACEIT's clock. Every
-- fact view keyed on m.started_at treated those matches as undated, which made
-- them invisible to season and date logic and hid one whole team's history from
-- the org identity proposals.
--
-- match_time() is the one definition of "when this match happened", matching the
-- parser's MatchRecord.event_time fallback.

CREATE OR REPLACE FUNCTION match_time(started timestamptz, finished timestamptz,
                                      configured timestamptz, scheduled timestamptz)
RETURNS timestamptz LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(started, finished, configured, scheduled)
$$;

CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    m.championship_id, c.season, c.scope_region AS region,
    match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS started_at,
    r.map_name, r.game_mode,
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
    m.championship_id, c.season, c.scope_region AS region,
    match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS started_at,
    m.best_of, m.maps_played,
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
    m.championship_id, c.season, c.scope_region AS region, c.tier,
    match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS started_at,
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
LEFT JOIN team_identity ti ON ti.team_id = mp.team_id
LEFT JOIN team_identity oi ON oi.team_id = (CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END)
WHERE m.ingest_state = 'complete' AND c.include;
