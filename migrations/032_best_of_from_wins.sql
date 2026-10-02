-- Best-of is derived from the winning score, not read from FACEIT.
--
-- 030 replaced a stored best-of only when the score could not fit it. That
-- left Al Qadsiah 1-4 Twisted Minds (2025-10-26) presented as the bo7 the
-- score forces while every other FACEIT best-of was taken on trust, and FACEIT
-- stores wrong ones (Dreamhack Dallas as best-of-1 throughout). The rule is
-- now general: a series with four map wins is a best-of-7 whatever FACEIT
-- stored, three wins a best-of-5, two a best-of-3, one a best-of-1. The
-- winning score is the series score after the drawn-map correction, so a draw
-- FACEIT counted as a win (4-0 in a bo5 with one 3-3 map) derives from actual
-- map wins (3) and stays a bo5; and a best-of is never fewer than the maps
-- recorded, so one win plus one draw is a best-of-3. A 0-0 (unplayed) series
-- keeps what was stored.
-- best_of_source says what happened: 'faceit' when the stored value agrees,
-- 'derived from map wins' when the score was itself corrected from map
-- results, 'derived from score' otherwise. `check` (score_plausibility) counts
-- every series this corrects, raised and lowered separately, and lists them.
-- Liquipedia-only series (no FACEIT record) keep Liquipedia's best-of unless
-- the score cannot fit it, as before: that is not FACEIT's stored value.

-- {{schema}}. on every relation and function: see 026 (PostgreSQL 17 plans a refresh under a restricted search_path).
CREATE OR REPLACE FUNCTION series_score(p_match_id text, p_team1 text, p_team2 text, p_score1 integer, p_score2 integer, p_best_of integer)
RETURNS TABLE (score1 integer, score2 integer, score_source text, best_of integer, best_of_source text)
LANGUAGE sql STABLE AS $$
    WITH maps AS (
        SELECT count(*) FILTER (WHERE r.winner_team_id = p_team1 AND NOT {{schema}}.map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS w1,
               count(*) FILTER (WHERE r.winner_team_id = p_team2 AND NOT {{schema}}.map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS w2,
               count(*) FILTER (WHERE {{schema}}.map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)) AS d,
               count(*) AS n
          FROM {{schema}}.match_rounds r WHERE r.match_id = p_match_id
    ), chosen AS (
        -- FACEIT counted a draw as a win: the stored score equals map wins plus draws for the side that "won" it
        SELECT CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN w1 ELSE p_score1 END AS s1,
               CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN w2 ELSE p_score2 END AS s2,
               CASE WHEN n > 0 AND d > 0 AND (p_score1, p_score2) IN ((w1 + d, w2), (w1, w2 + d)) THEN 'maps' ELSE 'faceit' END AS src
          FROM maps
    )
    , derived AS (
        -- the smallest best-of the winning score needs, and never fewer than the maps actually recorded (a draw is a
        -- map played without a win: one win plus one draw is a best-of-3, not a best-of-1)
        SELECT s1, s2, src,
               GREATEST(2 * GREATEST(s1, s2) - 1, n + (n % 2 = 0)::int * (n > 0)::int) AS bo
          FROM chosen, maps
    )
    SELECT s1, s2, src,
           CASE WHEN coalesce(GREATEST(s1, s2), 0) = 0 THEN p_best_of ELSE bo END,
           CASE WHEN coalesce(GREATEST(s1, s2), 0) = 0 OR p_best_of = bo THEN 'faceit'
                WHEN src = 'maps' THEN 'derived from map wins'
                ELSE 'derived from score' END
      FROM derived
$$;
