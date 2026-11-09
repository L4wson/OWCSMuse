-- 052: one definition of "this match has a result".
--
-- A FACEIT match carries a series result when its ingest reached 'complete' (result and map stats) or 'result_only'
-- (FACEIT has the result but no map stats: an admin-scored decider, a LAN event). Every reader of results asked that
-- question by spelling the two states out, in views and in Python; a third state that also carries a result would
-- have had to be found in each one. has_result() is the answer, and the series view, agg_map_modes and the Python
-- queries call it. The state machine itself is drawn in docs/schema-and-migrations.md.
--
-- A plain IMMUTABLE SQL expression with no SET clause, so the planner inlines it back into the IN (...) it replaces:
-- plans, the matches_ingest_state_idx index and statistics are unchanged. It reads no table, so PostgreSQL 17's
-- restricted search_path for REFRESH (033) does not apply to it.
--
-- The two objects below are 049's series view and 041's agg_map_modes, text unchanged except that predicate. series
-- keeps its name and columns (CREATE OR REPLACE: its dependents stay); agg_map_modes has no dependents or indexes and
-- is rebuilt with its data.

CREATE OR REPLACE FUNCTION has_result(ingest_state text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN ingest_state IN ('complete', 'result_only');

COMMENT ON FUNCTION has_result(text) IS
    'A match in this ingest state carries a series result: complete (with map stats) or result_only (without).';

-- 049's series view, the FACEIT branch filtered through has_result()
CREATE OR REPLACE VIEW series AS
WITH linked AS (
    SELECT lk.faceit_match_id, lk.lp_objectname, lk.tier, lm.page_url, lm.played_at AS lp_played_at,
           lm.team1_name, lm.team2_name, lm.score1 AS lp_score1, lm.score2 AS lp_score2, lm.best_of AS lp_best_of,
           lm.winner AS lp_winner, lm.n_games
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
), oriented AS (   -- is Liquipedia's team 1 FACEIT's faction 1? decided anchors, then names, then an unlevel score, then the winner
    SELECT l.faceit_match_id, l.lp_score1, l.lp_score2, l.lp_best_of, l.lp_winner,
           CASE WHEN a1.team_id = m.faction1_team_id AND a2.team_id = m.faction2_team_id THEN false
                WHEN a1.team_id = m.faction2_team_id AND a2.team_id = m.faction1_team_id THEN true
                WHEN fold_name(l.team1_name) = fold_name(m.faction1_name) OR fold_name(l.team2_name) = fold_name(m.faction2_name) THEN false
                WHEN fold_name(l.team1_name) = fold_name(m.faction2_name) OR fold_name(l.team2_name) = fold_name(m.faction1_name) THEN true
                WHEN l.lp_score1 <> l.lp_score2 AND (l.lp_score1, l.lp_score2) = (m.faction1_score, m.faction2_score) THEN false
                WHEN l.lp_score1 <> l.lp_score2 AND (l.lp_score1, l.lp_score2) = (m.faction2_score, m.faction1_score) THEN true
                WHEN l.lp_winner IN (1, 2) AND m.winner_faction IN ('faction1', 'faction2') THEN (l.lp_winner = 1) <> (m.winner_faction = 'faction1')
           END AS flip
      FROM linked l
      JOIN matches m ON m.match_id = l.faceit_match_id
      LEFT JOIN lp_side a1 ON a1.objectname = l.lp_objectname AND a1.side = 1
      LEFT JOIN lp_side a2 ON a2.objectname = l.lp_objectname AND a2.side = 2
)
SELECT 'faceit:' || m.match_id AS series_id,
       m.match_id, m.match_id AS faceit_match_id, l.lp_objectname,
       m.championship_id,
       coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS played_at,
       CASE WHEN m.liquipedia_played_at IS NOT NULL THEN 'liquipedia' ELSE 'faceit' END AS played_at_source,
       CASE WHEN u.use_lp THEN CASE WHEN o.lp_best_of IN (1, 3, 5, 7) AND GREATEST(o.lp_score1, o.lp_score2) <= (o.lp_best_of + 1) / 2 THEN o.lp_best_of
                                    WHEN 2 * GREATEST(o.lp_score1, o.lp_score2) - 1 <= 7 THEN 2 * GREATEST(o.lp_score1, o.lp_score2) - 1 END
            ELSE sc.best_of END AS best_of,
       CASE WHEN u.use_lp THEN CASE WHEN o.lp_best_of IN (1, 3, 5, 7) AND GREATEST(o.lp_score1, o.lp_score2) <= (o.lp_best_of + 1) / 2 THEN 'liquipedia'
                                    WHEN 2 * GREATEST(o.lp_score1, o.lp_score2) - 1 <= 7 THEN 'derived from score' ELSE 'implausible' END
            ELSE sc.best_of_source END AS best_of_source,
       m.faction1_team_id AS side1_team_id, m.faction2_team_id AS side2_team_id,
       CASE WHEN u.use_lp THEN CASE WHEN o.flip THEN o.lp_score2 ELSE o.lp_score1 END ELSE sc.score1 END AS score1,
       CASE WHEN u.use_lp THEN CASE WHEN o.flip THEN o.lp_score1 ELSE o.lp_score2 END ELSE sc.score2 END AS score2,
       CASE WHEN u.use_lp THEN CASE WHEN o.lp_winner NOT IN (1, 2) THEN 0 WHEN o.flip THEN 3 - o.lp_winner ELSE o.lp_winner END
            ELSE CASE m.winner_faction WHEN 'faction1' THEN 1 WHEN 'faction2' THEN 2 ELSE 0 END END AS winner_side,
       CASE WHEN u.use_lp THEN 'liquipedia' ELSE 'faceit' END::text AS result_source,
       m.maps_played,
       CASE WHEN EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = m.match_id AND r.source = 'liquipedia') THEN 'liquipedia'
            WHEN EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = m.match_id) THEN 'faceit' END AS maps_source,
       m.ingest_state AS state,
       EXISTS (SELECT 1 FROM match_players mp WHERE mp.match_id = m.match_id) AS has_player_stats,
       coalesce(l.tier, 'single-source') AS link_tier,
       ARRAY['faceit'::text] || CASE WHEN l.lp_objectname IS NOT NULL THEN ARRAY['liquipedia'::text] ELSE ARRAY[]::text[] END AS sources,
       'https://www.faceit.com/en/ow2/room/' || m.match_id AS source_url,
       l.page_url AS liquipedia_page_url,
       CASE WHEN u.use_lp THEN 'liquipedia' ELSE sc.score_source END AS score_source,
       CASE WHEN l.lp_objectname IS NOT NULL THEN o.flip END AS lp_flip
  FROM matches m
  JOIN championships c ON c.championship_id = m.championship_id
  LEFT JOIN linked l ON l.faceit_match_id = m.match_id
  LEFT JOIN oriented o ON o.faceit_match_id = m.match_id
  CROSS JOIN LATERAL (SELECT o.flip IS NOT NULL AND o.lp_score1 IS NOT NULL AND o.lp_score2 IS NOT NULL AS use_lp) u
  CROSS JOIN LATERAL series_score(m.match_id, m.faction1_team_id, m.faction2_team_id, m.faction1_score, m.faction2_score, m.best_of) sc
 WHERE has_result(m.ingest_state) AND m.status = 'FINISHED' AND c.include
UNION ALL
SELECT 'lp:' || lm.objectname,
       'lp:' || lm.objectname, NULL, lm.objectname,
       lm.championship_id,
       lm.played_at, 'liquipedia',
       CASE WHEN lm.best_of IN (1, 3, 5, 7) AND GREATEST(lm.score1, lm.score2) <= (lm.best_of + 1) / 2 THEN lm.best_of
            WHEN 2 * GREATEST(lm.score1, lm.score2) - 1 <= 7 THEN 2 * GREATEST(lm.score1, lm.score2) - 1 END,
       CASE WHEN lm.best_of IN (1, 3, 5, 7) AND GREATEST(lm.score1, lm.score2) <= (lm.best_of + 1) / 2 THEN 'liquipedia'
            WHEN 2 * GREATEST(lm.score1, lm.score2) - 1 <= 7 THEN 'derived from score' ELSE 'implausible' END,
       s1.team_id, s2.team_id,
       lm.score1, lm.score2,
       lm.winner, 'liquipedia',
       lm.n_games,
       NULL,
       'result_only',
       false,
       'single-source',
       ARRAY['liquipedia'::text],
       lm.page_url, lm.page_url,
       'liquipedia',
       false
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

-- 041's agg_map_modes, the FACEIT rounds filtered through has_result()
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
     WHERE has_result(m.ingest_state) AND c.include
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
