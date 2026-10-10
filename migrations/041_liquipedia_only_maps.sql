-- 041: a Liquipedia-only series has maps.
--
-- Stage 2 put Liquipedia's game-by-game results into match_rounds for series linked to FACEIT; match_rounds is keyed
-- to FACEIT matches (a foreign key), so the 143 Liquipedia-only series (Stage 4's events, two 2026 Stage 1 finals)
-- had map results on Liquipedia and none in any map-grain answer: 95 team pairings refused "no map stats on FACEIT"
-- although every map was known, and 15 answered with the Liquipedia-only series silently left out (Crazy Raccoon v
-- Team Falcons: 11 maps from 2 of their 7 series).
--
-- liquipedia_rounds holds each stored record's played games (a slot marked not played is no game; Push scored win/loss
-- as Stage 2 does, the convention FACEIT's own rounds use), rebuilt with liquipedia_matches by `liquipedia reconcile`.
-- fact_team_maps reads them for Liquipedia-only series only (a linked series' maps are already in match_rounds), and
-- agg_map_modes reads both. No player row exists for these maps; player views are unchanged.

CREATE TABLE IF NOT EXISTS liquipedia_rounds (
    lp_objectname text    NOT NULL REFERENCES liquipedia_matches (objectname) ON DELETE CASCADE,
    round_number  integer NOT NULL CHECK (round_number >= 1),
    map_name      text,
    game_mode     text,
    score1        integer,
    score2        integer,
    winner        integer NOT NULL CHECK (winner IN (0, 1, 2)),
    PRIMARY KEY (lp_objectname, round_number)
);

CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    s.championship_id, c.season, c.scope_region AS region,
    s.played_at AS started_at,
    r.map_name, r.game_mode,
    coalesce(map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = t.team_id, false) AS won,
    map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id) AS drawn,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name,
    r.source AS map_source,
    s.series_id, s.sources, s.source_url
FROM match_rounds r
JOIN series s ON s.match_id = r.match_id
JOIN championships c ON c.championship_id = s.championship_id
CROSS JOIN LATERAL (VALUES
    (r.team1_team_id, r.team2_team_id, r.team1_score, r.team2_score),
    (r.team2_team_id, r.team1_team_id, r.team2_score, r.team1_score)
) AS t(team_id, opponent_team_id, score, opp_score)
LEFT JOIN LATERAL team_identity_at(t.team_id, s.played_at) ti ON true
LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, s.played_at) oi ON true
WHERE t.team_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number))
UNION ALL
-- a Liquipedia-only series' maps (041): its played games, oriented to the series' sides (Liquipedia's team 1 is side 1)
SELECT
    s.match_id, lr.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    s.championship_id, c.season, c.scope_region AS region,
    s.played_at AS started_at,
    lr.map_name, lr.game_mode,
    coalesce(map_winner(s.side1_team_id, lr.score1, s.side2_team_id, lr.score2,
                        CASE lr.winner WHEN 1 THEN s.side1_team_id WHEN 2 THEN s.side2_team_id END) = t.team_id, false) AS won,
    map_is_drawn(lr.score1, lr.score2, CASE lr.winner WHEN 1 THEN s.side1_team_id WHEN 2 THEN s.side2_team_id END) AS drawn,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name,
    'liquipedia'::text AS map_source,
    s.series_id, s.sources, s.source_url
FROM liquipedia_rounds lr
JOIN series s ON s.lp_objectname = lr.lp_objectname AND s.sources = ARRAY['liquipedia'::text]
JOIN championships c ON c.championship_id = s.championship_id
CROSS JOIN LATERAL (VALUES
    (s.side1_team_id, s.side2_team_id, lr.score1, lr.score2),
    (s.side2_team_id, s.side1_team_id, lr.score2, lr.score1)
) AS t(team_id, opponent_team_id, score, opp_score)
LEFT JOIN LATERAL team_identity_at(t.team_id, s.played_at) ti ON true
LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, s.played_at) oi ON true
WHERE t.team_id IS NOT NULL;

DROP MATERIALIZED VIEW IF EXISTS agg_map_modes CASCADE;
CREATE MATERIALIZED VIEW agg_map_modes AS
WITH rounds AS (
    SELECT r.match_id, r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region AS region,
           map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = r.team1_team_id AS team1_won,
           map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = r.team2_team_id AS team2_won,
           map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id) AS drawn,
           r.team1_score + r.team2_score AS total_score, d.duration_seconds,
           coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS played_at
      FROM match_rounds r
      JOIN matches       m ON m.match_id = r.match_id
      JOIN championships c ON c.championship_id = m.championship_id
      LEFT JOIN map_durations d ON (d.match_id, d.round_number) = (r.match_id, r.round_number)
     WHERE m.ingest_state IN ('complete', 'result_only') AND c.include
       AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number))
    UNION ALL
    SELECT s.match_id, lr.map_name, lr.game_mode, s.championship_id, c.season, c.scope_region,
           map_winner('1', lr.score1, '2', lr.score2, lr.winner::text) = '1',
           map_winner('1', lr.score1, '2', lr.score2, lr.winner::text) = '2',
           map_is_drawn(lr.score1, lr.score2, nullif(lr.winner, 0)::text),
           lr.score1 + lr.score2, NULL, s.played_at
      FROM liquipedia_rounds lr
      JOIN series s ON s.lp_objectname = lr.lp_objectname AND s.sources = ARRAY['liquipedia'::text]
      JOIN championships c ON c.championship_id = s.championship_id AND c.include
)
SELECT map_name, game_mode, championship_id, season, region,
       count(*)                                  AS maps,
       count(DISTINCT match_id)                  AS matches,
       count(*) FILTER (WHERE team1_won)         AS team1_wins,
       count(*) FILTER (WHERE team2_won)         AS team2_wins,
       count(*) FILTER (WHERE drawn)             AS draws,
       avg(total_score)                          AS avg_total_score,
       count(duration_seconds)                   AS maps_with_duration,
       avg(duration_seconds)                     AS avg_duration_seconds,
       min(played_at)                            AS first_map_at,
       max(played_at)                            AS last_map_at
  FROM rounds
 GROUP BY map_name, game_mode, championship_id, season, region;
