-- Three corrections to what a map and a series say, found on production 2026-10-02.
--
-- 1. The map winner is derived from the scores; winner_team_id is advisory.
--    1-3e78e269 map 5 (Suravasa, Flashpoint) is scored 0-3 for Twisted Minds and
--    credits Al qadsiah as the winner. The map was really played, so nothing
--    looked wrong, and every map record, map/mode win rate and head-to-head
--    that read winner_team_id attributed it to the wrong team. map_winner()
--    gives the higher score's team, nobody for equal scores (a tied map has no
--    winner), and falls back to winner_team_id only when a score is missing.
--    Every fact view, series_score and agg_map_modes read it; `check`
--    (map_winner_consistency) lists every row where the stored winner
--    contradicts the scores.
-- 2. Liquipedia is the source of record for a series' result and best-of
--    wherever a linked Liquipedia record exists and can be oriented to the
--    FACEIT factions; FACEIT only where Liquipedia has nothing. This inverts
--    the Stage 2 rule (FACEIT first, Liquipedia to fill result_only maps):
--    FACEIT keeps a fixed number of map slots per format and, when a sweep
--    closes a series early, logs a default win for the winner on the next map
--    in the rotation (the 2024 Stage 1 grand finals: real 4-0s stored as 5-0
--    with a Dorado nobody played), and it counts a drawn map as a win. A FACEIT
--    map row beyond Liquipedia's game count for a linked series is a phantom
--    (phantom_maps): out of map records, series scores, map/mode win rates and
--    player aggregates alike; `check` (phantom_map_isolation) proves it and
--    counts the player rows that rode on one. Player stats stay FACEIT-only.
-- 3. Best-of is derived only from real, played map wins (phantoms excluded),
--    capped at the formats OWCS uses (bo1, bo3, bo5, bo7): a derivation past
--    bo7 is implausible and presented as unknown rather than invented. A
--    stored best-of of 1 is junk (Dreamhack Dallas), not a value to correct
--    from; a stored value is used only when no maps were recorded and it is a
--    real format. best_of_source: liquipedia | faceit | derived from map wins |
--    implausible | unknown.

-- ------------------------------------------------------------ 1. the map winner
CREATE OR REPLACE FUNCTION map_winner(team1_id text, team1_score integer, team2_id text, team2_score integer, advisory text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN team1_score IS NOT NULL AND team2_score IS NOT NULL
                THEN CASE WHEN team1_score > team2_score THEN team1_id WHEN team2_score > team1_score THEN team2_id END
                ELSE advisory END
$$;

-- same signature as 030: the scores decide, the stored winner only when a score is missing
CREATE OR REPLACE FUNCTION map_is_drawn(team1_score integer, team2_score integer, winner_team_id text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN team1_score IS NOT NULL AND team2_score IS NOT NULL THEN team1_score = team2_score
                ELSE winner_team_id IS NULL END
$$;

-- ------------------------------------------------------------ 2. phantom maps
-- A FACEIT map row of a linked series beyond Liquipedia's game count. Liquipedia's games include drawn maps, so a
-- series with a draw is not over-counted; a template's unplayed slots are never parsed as games (matches.py).
CREATE OR REPLACE VIEW phantom_maps AS
SELECT r.match_id, r.round_number, r.map_name, lm.objectname AS lp_objectname, lm.n_games AS liquipedia_games,
       (SELECT count(*) FROM match_players mp WHERE mp.match_id = r.match_id AND mp.round_number = r.round_number) AS player_rows
  FROM match_rounds r
  JOIN liquipedia_links lk ON lk.faceit_match_id = r.match_id AND NOT lk.provisional AND coalesce(lk.decision, '') <> 'rejected'
  JOIN liquipedia_matches lm ON lm.objectname = lk.lp_objectname
 WHERE coalesce(r.source, 'faceit') <> 'liquipedia' AND coalesce(lm.n_games, 0) > 0 AND r.round_number > lm.n_games;

-- ------------------------------------------------------------ 3. the series score and best-of
CREATE OR REPLACE FUNCTION series_score(p_match_id text, p_team1 text, p_team2 text, p_score1 integer, p_score2 integer, p_best_of integer)
RETURNS TABLE (score1 integer, score2 integer, score_source text, best_of integer, best_of_source text)
LANGUAGE sql STABLE AS $$
    WITH maps AS (   -- real, played maps only: no phantom, winners from the scores
        SELECT count(*) FILTER (WHERE {{schema}}.map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = p_team1) AS w1,
               count(*) FILTER (WHERE {{schema}}.map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = p_team2) AS w2,
               count(*) FILTER (WHERE {{schema}}.map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS d,
               count(*) AS n
          FROM {{schema}}.match_rounds r
         WHERE r.match_id = p_match_id
           AND NOT EXISTS (SELECT 1 FROM {{schema}}.phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number))
    ), chosen AS (
        -- FACEIT counted a draw as a win: the stored score equals map wins plus draws for the side that "won" it
        SELECT CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN w1 ELSE p_score1 END AS s1,
               CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN w2 ELSE p_score2 END AS s2,
               CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN 'maps' ELSE 'faceit' END AS src,
               w1, w2, d, n,
               CASE WHEN p_best_of IN (3, 5, 7) THEN p_best_of END AS stored          -- 1 is junk; anything else is no format
          FROM maps
    ), derived AS (
        SELECT s1, s2, src, stored, n,
               CASE WHEN n > 0 THEN GREATEST(2 * GREATEST(w1, w2) - 1, n + (n % 2 = 0)::int) END AS from_wins   -- never fewer than the maps played
          FROM chosen
    )
    SELECT s1, s2, src,
           CASE WHEN n > 0 AND from_wins <= 7 THEN from_wins
                WHEN n > 0 THEN NULL                                   -- implausible: more wins than any OWCS format holds
                ELSE stored END,
           CASE WHEN n > 0 AND from_wins > 7 THEN 'implausible'
                WHEN n > 0 AND from_wins = stored THEN 'faceit'
                WHEN n > 0 THEN 'derived from map wins'
                WHEN stored IS NOT NULL THEN 'faceit'
                ELSE 'unknown' END
      FROM derived
$$;

-- The series: Liquipedia's result where a linked record orients to the FACEIT factions, FACEIT's otherwise.
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
       CASE WHEN u.use_lp THEN 'liquipedia' ELSE sc.score_source END AS score_source
  FROM matches m
  JOIN championships c ON c.championship_id = m.championship_id
  LEFT JOIN linked l ON l.faceit_match_id = m.match_id
  LEFT JOIN oriented o ON o.faceit_match_id = m.match_id
  CROSS JOIN LATERAL (SELECT o.flip IS NOT NULL AND o.lp_score1 IS NOT NULL AND o.lp_score2 IS NOT NULL AS use_lp) u
  CROSS JOIN LATERAL series_score(m.match_id, m.faction1_team_id, m.faction2_team_id, m.faction1_score, m.faction2_score, m.best_of) sc
 WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include
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

-- ------------------------------------------------------------ the fact views read the derived winner and skip phantoms
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
  AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number));

CREATE OR REPLACE VIEW fact_player_maps AS
SELECT
    mp.match_id, mp.round_number, mp.player_id, mp.team_id,
    CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END AS opponent_team_id,
    m.championship_id, c.season, c.scope_region AS region, c.tier,
    x.at AS started_at,
    r.map_name, r.game_mode,
    coalesce(map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = mp.team_id, false) AS map_won,
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
WHERE m.ingest_state = 'complete' AND c.include
  AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (mp.match_id, mp.round_number));

DROP MATERIALIZED VIEW IF EXISTS agg_map_modes CASCADE;
CREATE MATERIALIZED VIEW agg_map_modes AS
SELECT
    r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region AS region,
    count(*)                                             AS maps,
    count(DISTINCT r.match_id)                           AS matches,
    count(*) FILTER (WHERE map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = r.team1_team_id) AS team1_wins,
    count(*) FILTER (WHERE map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = r.team2_team_id) AS team2_wins,
    count(*) FILTER (WHERE map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS draws,
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
  AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number))
GROUP BY r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region;
