-- 049: hero bans, from Liquipedia only.
--
-- Liquipedia's match2games records each map's bans in `extradata`: team1ban1, team2ban1 (one hero per team, the hero
-- that team banned) and banstart (the team that banned first). FACEIT's room vote is not used (owner, 2026-11-03): it
-- has no team attribution, and in a room the series was not played in it describes other maps. Bans began in 2025.
--
-- liquipedia_bans holds each stored record's bans per played game (round_number as liquipedia_rounds numbers them),
-- rebuilt with it by `liquipedia reconcile` in each hero's canonical spelling (heroes, loaded from scope/heroes.json).
-- A ban belongs to a team through the series' sides: a Liquipedia-only series' side 1 is Liquipedia's team 1; a linked
-- series is FACEIT's, and `series.lp_flip` (appended below) says whether Liquipedia's team 1 is its side 2 - the same
-- orientation the series view already decides its Liquipedia score by. fact_hero_bans is one row per ban.

CREATE TABLE IF NOT EXISTS heroes (
    hero           text PRIMARY KEY,                 -- canonical spelling (Liquipedia's)
    available_from date,                             -- first day it could be banned; NULL: before bans began
    basis          text NOT NULL DEFAULT ''          -- pool_at_bans_start | proposed | owner
);

CREATE TABLE IF NOT EXISTS hero_aliases (
    alias_key text PRIMARY KEY,                      -- owcsmuse.heroes.key(): fold() without spaces
    hero      text NOT NULL REFERENCES heroes (hero) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS hero_ban_settings (
    bans_introduced_season integer NOT NULL
);

CREATE TABLE IF NOT EXISTS liquipedia_bans (
    lp_objectname text    NOT NULL REFERENCES liquipedia_matches (objectname) ON DELETE CASCADE,
    round_number  integer NOT NULL CHECK (round_number >= 1),
    side          integer NOT NULL CHECK (side IN (1, 2)),      -- Liquipedia's team 1 or team 2: the team that banned
    hero          text    NOT NULL,
    banned_first  boolean,                                       -- extradata.banstart names this side
    PRIMARY KEY (lp_objectname, round_number, side, hero)
);

-- the series view of 034, with lp_flip appended: is Liquipedia's team 1 this series' side 2? NULL when the series
-- has no linked Liquipedia record or the record could not be oriented; false for a Liquipedia-only series
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

-- One row per ban, with the banning team and its opponent at the series' time.
CREATE OR REPLACE VIEW fact_hero_bans AS
SELECT s.series_id, s.match_id, b.round_number, b.hero, b.side AS lp_side, b.banned_first,
       lr.map_name, lr.game_mode,
       s.championship_id, c.season, c.scope_region AS region, s.played_at,
       t.team_id, t.opponent_team_id,
       ti.org_key, ti.display_name, oi.org_key AS opponent_org_key, oi.display_name AS opponent_display_name,
       s.lp_objectname, s.liquipedia_page_url, s.source_url, s.sources
  FROM liquipedia_bans b
  JOIN series s ON s.lp_objectname = b.lp_objectname
  JOIN championships c ON c.championship_id = s.championship_id
  LEFT JOIN liquipedia_rounds lr ON lr.lp_objectname = b.lp_objectname AND lr.round_number = b.round_number
 CROSS JOIN LATERAL (
       SELECT CASE WHEN s.lp_flip IS NULL THEN NULL WHEN (b.side = 1) <> s.lp_flip THEN s.side1_team_id ELSE s.side2_team_id END,
              CASE WHEN s.lp_flip IS NULL THEN NULL WHEN (b.side = 1) <> s.lp_flip THEN s.side2_team_id ELSE s.side1_team_id END
       ) AS t(team_id, opponent_team_id)
  LEFT JOIN LATERAL team_identity_at(t.team_id, s.played_at) ti ON true
  LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, s.played_at) oi ON true;

-- One row per map with bans: the denominator of every ban rate.
CREATE OR REPLACE VIEW hero_ban_maps AS
SELECT DISTINCT ON (series_id, round_number)
       series_id, match_id, round_number, map_name, game_mode, championship_id, season, region, played_at,
       lp_objectname, liquipedia_page_url
  FROM fact_hero_bans
 ORDER BY series_id, round_number;
