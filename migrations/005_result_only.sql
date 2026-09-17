-- Matches whose series result is known but which carry no map stats on FACEIT
-- (admin-scored deciders, the Dreamhack Dallas 2024 LAN, ...). /matches/{id}
-- returns the result; /matches/{id}/stats returns 404. These count in team
-- series records and head-to-head, never in map or player aggregates.

ALTER TABLE matches DROP CONSTRAINT matches_ingest_state_check;
ALTER TABLE matches ADD CONSTRAINT matches_ingest_state_check
    CHECK (ingest_state IN ('stub', 'detail_fetched', 'complete', 'result_only', 'skipped', 'failed'));

CREATE OR REPLACE VIEW fact_team_matches AS
SELECT
    m.match_id, t.team_id, t.opponent_team_id, t.faction,
    m.championship_id, c.season, c.scope_region AS region, m.started_at, m.best_of, m.maps_played,
    (m.winner_team_id = t.team_id) AS won,
    t.score AS map_wins, t.opp_score AS map_losses
FROM matches m
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (VALUES
    (m.faction1_team_id, m.faction2_team_id, 'faction1', m.faction1_score, m.faction2_score),
    (m.faction2_team_id, m.faction1_team_id, 'faction2', m.faction2_score, m.faction1_score)
) AS t(team_id, opponent_team_id, faction, score, opp_score)
WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include AND t.team_id IS NOT NULL;
