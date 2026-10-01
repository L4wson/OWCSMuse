-- A tied map is nobody's win, and no series shows a score its best-of cannot hold.
--
-- Production found two series where FACEIT counted a drawn map (3-3) as a win
-- for the series winner - 4-0 in a best-of-5 with four maps played - and 14
-- Dreamhack Dallas series stored as best-of-1 with 3-1 scores. Map results now
-- decide a draw (equal scores, or no winner), a draw is excluded from map wins
-- everywhere map results feed a record, and the series score a series presents
-- is corrected from its map results when FACEIT's score counted a draw as a win
-- (score_source = 'maps'; FACEIT's stored columns are untouched). A best-of
-- the score cannot fit is replaced by the smallest that can (best_of_source =
-- 'derived from score'). `check` (score_plausibility) asserts the result.

-- A map is drawn when its two scores are equal, or when no winner is recorded.
CREATE OR REPLACE FUNCTION map_is_drawn(team1_score integer, team2_score integer, winner_team_id text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT winner_team_id IS NULL OR (team1_score IS NOT NULL AND team2_score IS NOT NULL AND team1_score = team2_score)
$$;

-- The series score to present, with its provenance.
CREATE OR REPLACE FUNCTION series_score(p_match_id text, p_team1 text, p_team2 text, p_score1 integer, p_score2 integer, p_best_of integer)
RETURNS TABLE (score1 integer, score2 integer, score_source text, best_of integer, best_of_source text)
LANGUAGE sql STABLE AS $$
    WITH maps AS (
        SELECT count(*) FILTER (WHERE r.winner_team_id = p_team1 AND NOT map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS w1,
               count(*) FILTER (WHERE r.winner_team_id = p_team2 AND NOT map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS w2,
               count(*) FILTER (WHERE map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS d,
               count(*) AS n
          FROM match_rounds r WHERE r.match_id = p_match_id
    ), chosen AS (
        -- FACEIT counted a draw as a win: the stored score equals map wins plus draws for the side that "won" it
        SELECT CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN w1 ELSE p_score1 END AS s1,
               CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN w2 ELSE p_score2 END AS s2,
               CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN 'maps' ELSE 'faceit' END AS src
          FROM maps
    )
    SELECT s1, s2, src,
           CASE WHEN p_best_of IS NULL OR GREATEST(s1, s2) > (p_best_of + 1) / 2 THEN 2 * GREATEST(s1, s2) - 1 ELSE p_best_of END,
           CASE WHEN p_best_of IS NULL OR GREATEST(s1, s2) > (p_best_of + 1) / 2 THEN 'derived from score' ELSE 'faceit' END
      FROM chosen
$$;

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
       sc.best_of, sc.best_of_source,
       m.faction1_team_id AS side1_team_id, m.faction2_team_id AS side2_team_id,
       sc.score1, sc.score2,
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
       l.page_url AS liquipedia_page_url,
       sc.score_source
  FROM matches m
  JOIN championships c ON c.championship_id = m.championship_id
  LEFT JOIN linked l ON l.faceit_match_id = m.match_id
  CROSS JOIN LATERAL series_score(m.match_id, m.faction1_team_id, m.faction2_team_id, m.faction1_score, m.faction2_score, m.best_of) sc
 WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include
UNION ALL
SELECT 'lp:' || lm.objectname,
       'lp:' || lm.objectname, NULL, lm.objectname,
       lm.championship_id,
       lm.played_at, 'liquipedia',
       CASE WHEN lm.best_of IS NULL OR GREATEST(lm.score1, lm.score2) > (lm.best_of + 1) / 2
            THEN 2 * GREATEST(lm.score1, lm.score2) - 1 ELSE lm.best_of END,
       CASE WHEN lm.best_of IS NULL OR GREATEST(lm.score1, lm.score2) > (lm.best_of + 1) / 2
            THEN 'derived from score' ELSE 'liquipedia' END,
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
       'liquipedia'
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


-- map grain: a draw is a draw for both sides
CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    s.championship_id, c.season, c.scope_region AS region,
    s.played_at AS started_at,
    r.map_name, r.game_mode,
    (r.winner_team_id = t.team_id AND NOT map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS won,
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
WHERE t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_player_maps AS
SELECT
    mp.match_id, mp.round_number, mp.player_id, mp.team_id,
    CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END AS opponent_team_id,
    m.championship_id, c.season, c.scope_region AS region, c.tier,
    x.at AS started_at,
    r.map_name, r.game_mode,
    (r.winner_team_id = mp.team_id AND NOT map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS map_won,
    map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id) AS map_drawn,
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

-- series grain: the presented score and its provenance ride along
CREATE OR REPLACE VIEW fact_team_matches AS
SELECT
    s.match_id, t.team_id, t.opponent_team_id, t.faction,
    s.championship_id, c.season, c.scope_region AS region,
    s.played_at AS started_at,
    s.best_of, s.maps_played,
    (s.winner_side = t.side) AS won,
    t.score AS map_wins, t.opp_score AS map_losses,
    s.state AS ingest_state,
    ti.org_key, ti.org_id, ti.display_name,
    oi.org_key AS opponent_org_key, oi.org_id AS opponent_org_id, oi.display_name AS opponent_display_name,
    s.series_id, s.sources, s.source_url,
    s.score_source, s.best_of_source
FROM series s
JOIN championships c ON c.championship_id = s.championship_id
CROSS JOIN LATERAL (VALUES
    (1, s.side1_team_id, s.side2_team_id, 'faction1', s.score1, s.score2),
    (2, s.side2_team_id, s.side1_team_id, 'faction2', s.score2, s.score1)
) AS t(side, team_id, opponent_team_id, faction, score, opp_score)
LEFT JOIN LATERAL team_identity_at(t.team_id, s.played_at) ti ON true
LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, s.played_at) oi ON true
WHERE t.team_id IS NOT NULL;
