-- Stage 2 of the Liquipedia integration: map-level results for FACEIT series
-- that carry a result (winner, series score) but no per-map stats
-- (ingest_state = 'result_only'). Liquipedia's match2games has map, mode,
-- per-map score and winner for the ones it also covers - never player stats.
--
-- Source is recorded per field, never merged silently:
--   * match_rounds.source says whose round this is. A Liquipedia round is only
--     ever INSERTed where FACEIT has none (enforced by the ingest code, not by
--     a constraint here, since "FACEIT already has rows" is a normal, legal
--     state to leave alone) - so there is never a same-round conflict to
--     arbitrate. FACEIT wins for map stats by construction: its presence blocks
--     a Liquipedia round from ever being written for that match.
--   * matches.date_source says whether "when this happened" is FACEIT's own
--     time or Liquipedia's. On a result_only series FACEIT's timestamp is when
--     the result was entered, not when it was played (see Stage 1's alignment
--     numbers - up to 100+ hours off), so Liquipedia's scheduled time wins
--     there when it is set; matches.liquipedia_played_at holds it and every
--     underlying FACEIT timestamp column is left exactly as it was, only
--     preferred *over* by the fact views (coalesce(liquipedia_played_at,
--     match_time(...)) - match_time() itself is unchanged, since giving it a
--     5th parameter would leave two ambiguous overloads for every 4-argument
--     call site already in migration 011 and in Python).

ALTER TABLE match_rounds ADD COLUMN source text NOT NULL DEFAULT 'faceit' CHECK (source IN ('faceit', 'liquipedia'));
CREATE INDEX match_rounds_liquipedia_idx ON match_rounds (match_id) WHERE source = 'liquipedia';

ALTER TABLE matches ADD COLUMN liquipedia_played_at timestamptz;
ALTER TABLE matches ADD COLUMN date_source text NOT NULL DEFAULT 'faceit' CHECK (date_source IN ('faceit', 'liquipedia'));
ALTER TABLE matches ADD CONSTRAINT matches_liquipedia_date_needs_value
    CHECK (date_source <> 'liquipedia' OR liquipedia_played_at IS NOT NULL);

-- Map grain now includes result_only series that have been enriched (they have
-- match_rounds rows; plain result_only series still have none, so the INNER
-- JOIN keeps excluding them exactly as before - nothing here changes their
-- absence). fact_player_maps is untouched: it joins match_players, which is
-- never written for a Liquipedia round, so it cannot gain a row here.
CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    m.championship_id, c.season, c.scope_region AS region,
    coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS started_at,
    r.map_name, r.game_mode,
    (r.winner_team_id = t.team_id) AS won,
    (r.winner_team_id IS NULL)     AS drawn,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name,
    r.source AS map_source
FROM match_rounds r
JOIN matches       m ON m.match_id = r.match_id
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (VALUES
    (r.team1_team_id, r.team2_team_id, r.team1_score, r.team2_score),
    (r.team2_team_id, r.team1_team_id, r.team2_score, r.team1_score)
) AS t(team_id, opponent_team_id, score, opp_score)
LEFT JOIN team_identity ti ON ti.team_id = t.team_id
LEFT JOIN team_identity oi ON oi.team_id = t.opponent_team_id
WHERE m.ingest_state IN ('complete', 'result_only') AND c.include AND t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_team_matches AS
SELECT
    m.match_id, t.team_id, t.opponent_team_id, t.faction,
    m.championship_id, c.season, c.scope_region AS region,
    coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS started_at,
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

-- agg_map_modes reads match_rounds directly (not through fact_team_maps) and
-- had its own 'complete'-only filter.
DROP MATERIALIZED VIEW IF EXISTS agg_map_modes CASCADE;
CREATE MATERIALIZED VIEW agg_map_modes AS
SELECT
    r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region AS region,
    count(*)                                             AS maps,
    count(DISTINCT r.match_id)                           AS matches,
    count(*) FILTER (WHERE r.winner_team_id = r.team1_team_id) AS team1_wins,
    count(*) FILTER (WHERE r.winner_team_id = r.team2_team_id) AS team2_wins,
    count(*) FILTER (WHERE r.winner_team_id IS NULL)     AS draws,
    avg(r.team1_score + r.team2_score)                   AS avg_total_score,
    count(d.duration_seconds)                            AS maps_with_duration,
    avg(d.duration_seconds)                              AS avg_duration_seconds,
    min(coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at))) AS first_map_at,
    max(coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at))) AS last_map_at
FROM match_rounds r
JOIN matches       m ON m.match_id = r.match_id
JOIN championships c ON c.championship_id = m.championship_id
LEFT JOIN map_durations d ON (d.match_id, d.round_number) = (r.match_id, r.round_number)
WHERE m.ingest_state IN ('complete', 'result_only') AND c.include
GROUP BY r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region;
