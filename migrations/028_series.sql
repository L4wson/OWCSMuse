-- The source-agnostic series.
--
-- A match may come from FACEIT, from Liquipedia, or from both, and is one
-- match either way. `matches` stays FACEIT's own table and `liquipedia_matches`
-- Liquipedia's; `series` is the one row per match the team-grain facts read,
-- with per-field provenance (Stage 2's rule, now for every field). It is a
-- plain view over the two source tables and the reviewed links between them,
-- so it is always current and never needs a run of its own.
--
--   * A FACEIT series is a series; when a reviewed link ties a Liquipedia record
--     to it, that record's values join it (date, maps) and the row carries both
--     sources. A link that is provisional (rests on an unreviewed team-name
--     proposal) or ambiguous never merges anything: both records stay visible as
--     what they are, which can at worst double-count visibly, never attribute.
--   * A Liquipedia record is a series of its own only when the reconciler found
--     it NO FACEIT counterpart at all (or a reviewer rejected the link it might
--     have had) AND both its teams resolve through a decided anchor
--     (scope/liquipedia_team_map.json, loaded by `identity load`): a team anchored
--     to a FACEIT team id plays as that id; a team anchored to an org plays as
--     its Liquipedia-born team id (`lp:team:<name>`), mapped to the org. A record
--     that names a FACEIT id, or sits ambiguous with candidates, waits: it may
--     be the FACEIT series under another key, and two rows for one match is the
--     error this view exists to prevent. Nothing is resolved on a guess.
--   * series_id is `faceit:<match_id>` or `lp:<objectname>`; match_id keeps the
--     FACEIT id where there is one so every FACEIT-keyed table still joins.

CREATE OR REPLACE VIEW series AS
WITH linked AS (
    SELECT lk.faceit_match_id, lk.lp_objectname, lk.tier, lm.page_url, lm.played_at AS lp_played_at
      FROM liquipedia_links lk JOIN liquipedia_matches lm ON lm.objectname = lk.lp_objectname
     WHERE lk.faceit_match_id IS NOT NULL AND NOT lk.provisional AND coalesce(lk.decision, '') <> 'rejected'
), lp_side AS (                                                   -- a Liquipedia team name resolved by a decided anchor only
    SELECT lm.objectname, s.side, s.name,
           CASE a.entity_type WHEN 'team' THEN a.entity_id
                ELSE 'lp:team:' || a.anchor || CASE WHEN a.region <> '' THEN '|' || a.region ELSE '' END END AS team_id
      FROM liquipedia_matches lm
      CROSS JOIN LATERAL (VALUES (1, lm.team1_name), (2, lm.team2_name)) AS s(side, name)
      JOIN entity_anchors a ON a.anchor_kind = 'team_name' AND a.anchor = fold_name(s.name)
                           AND (a.region = '' OR a.region = coalesce(lm.region, ''))
      JOIN teams t ON t.team_id = CASE a.entity_type WHEN 'team' THEN a.entity_id
                ELSE 'lp:team:' || a.anchor || CASE WHEN a.region <> '' THEN '|' || a.region ELSE '' END END
)
SELECT 'faceit:' || m.match_id AS series_id,
       m.match_id, m.match_id AS faceit_match_id, l.lp_objectname,
       m.championship_id,
       coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS played_at,
       CASE WHEN m.liquipedia_played_at IS NOT NULL THEN 'liquipedia' ELSE 'faceit' END AS played_at_source,
       m.best_of, 'faceit'::text AS best_of_source,
       m.faction1_team_id AS side1_team_id, m.faction2_team_id AS side2_team_id,
       m.faction1_score AS score1, m.faction2_score AS score2,
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
       l.page_url AS liquipedia_page_url
  FROM matches m
  JOIN championships c ON c.championship_id = m.championship_id
  LEFT JOIN linked l ON l.faceit_match_id = m.match_id
 WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include
UNION ALL
SELECT 'lp:' || lm.objectname,
       'lp:' || lm.objectname, NULL, lm.objectname,
       lm.championship_id,
       lm.played_at, 'liquipedia',
       lm.best_of, 'liquipedia',
       s1.team_id, s2.team_id,
       lm.score1, lm.score2,
       lm.winner, 'liquipedia',
       lm.n_games,
       NULL,                                      -- no map rows of its own yet (map grain is FACEIT-keyed for now)
       'result_only',                             -- a result with no FACEIT stats: what the series-grain consumers already handle
       false,
       'single-source',
       ARRAY['liquipedia'::text],
       lm.page_url, lm.page_url
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

-- ------------------------------------------------ the team-grain facts, from series
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
    s.series_id, s.sources, s.source_url
FROM series s
JOIN championships c ON c.championship_id = s.championship_id
CROSS JOIN LATERAL (VALUES
    (1, s.side1_team_id, s.side2_team_id, 'faction1', s.score1, s.score2),
    (2, s.side2_team_id, s.side1_team_id, 'faction2', s.score2, s.score1)
) AS t(side, team_id, opponent_team_id, faction, score, opp_score)
LEFT JOIN LATERAL team_identity_at(t.team_id, s.played_at) ti ON true
LEFT JOIN LATERAL team_identity_at(t.opponent_team_id, s.played_at) oi ON true
WHERE t.team_id IS NOT NULL;

CREATE OR REPLACE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    s.championship_id, c.season, c.scope_region AS region,
    s.played_at AS started_at,
    r.map_name, r.game_mode,
    (r.winner_team_id = t.team_id) AS won,
    (r.winner_team_id IS NULL)     AS drawn,
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
