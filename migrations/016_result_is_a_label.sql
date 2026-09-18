-- "Result" is a label, not a metric.
--
-- FACEIT writes 1 or 0 per map for whether that player's team won, so stat_kind()
-- read it as countable and a leaderboard would happily rank players by "most
-- Result" - which is map wins, said badly. Ranking by it was never wrong
-- arithmetic, it was a wrong name for a number, and the record questions answer
-- it properly.
--
-- Reclassifying it removes it from leaderboards (validate refuses a non-numeric
-- metric), from the long format's totals, and from the suggestion list, while
-- leaving the key itself in stat_coverage_season where availability is reported.

CREATE OR REPLACE FUNCTION stat_kind(stat_key text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE
        WHEN stat_key IN ('Role', 'Team', 'Map', 'Winner', 'Score Summary', 'Best Of', 'Nickname', 'Result')
            THEN 'non_numeric'
        WHEN stat_key ~ '(/10m|Ratio|percent|per |/Deaths|/Eliminations|/Final Blows|/\(Eliminations|Avg |Average )'
            THEN 'derived_rate'
        ELSE 'countable'
    END
$$;
