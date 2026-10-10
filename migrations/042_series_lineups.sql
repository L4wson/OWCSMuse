-- 042: who was on which side of every series, from every source that says so.
--
-- A player's series record against a player or an org is the series in which the two were on opposite sides, scored
-- from the subject's team's side: players do not win series, their teams do. Until now the series-grain head-to-head
-- demanded two teams ("head-to-head needs two resolved teams" for "zeruhh series record against sugarfree"), and the
-- note that says two entities "met" counted any series both appeared in - a player's own team's series among them
-- ("zeruhh and Team Liquid met" for Team Liquid's own player).
--
-- series_lineups: one row per player per side of a series.
--   * FACEIT series (any series with a FACEIT match): the declared line-up (match_rosters), a substitute only when he
--     played a map of it (match_players), since a bench is no side;
--   * Liquipedia-only series: Liquipedia's line-up, through a reviewed player identity (entity_anchors player_page),
--     on the series side Liquipedia's side number is (side 1 is Liquipedia's team 1, as in `series`).
-- A player with no reviewed identity is on no Liquipedia-only series' side: unknown, never guessed.

CREATE OR REPLACE VIEW series_lineups AS
SELECT s.match_id, mr.player_id, mr.team_id, 'faceit'::text AS source
  FROM series s
  JOIN match_rosters mr ON mr.match_id = s.match_id
 WHERE mr.team_id IS NOT NULL
   AND (NOT mr.is_substitute
        OR EXISTS (SELECT 1 FROM match_players mp WHERE mp.match_id = mr.match_id AND mp.player_id = mr.player_id))
UNION ALL
SELECT DISTINCT s.match_id, a.entity_id AS player_id,
       CASE lp.side WHEN 1 THEN s.side1_team_id ELSE s.side2_team_id END AS team_id, 'liquipedia'::text AS source
  FROM series s
  JOIN liquipedia_match_players lp ON lp.lp_objectname = s.lp_objectname
  JOIN entity_anchors a ON a.anchor_kind = 'player_page' AND a.entity_type = 'player' AND a.anchor = lp.page
 WHERE s.sources = ARRAY['liquipedia'::text];
