-- 048: one stored spelling per map and per mode - FACEIT's.
--
-- Liquipedia's records spelled some modes in lower case ("control" x2, "hybrid" x2 among the maps in fact_team_maps)
-- and some maps differently ("Watchpoint: Gibraltar" for FACEIT's "Watchpoint Gibraltar", "Paraíso" for "Paraiso",
-- "Esperanca" for "Esperança"). Answers filter on the exact value, and the validator picked one spelling from a set in
-- the order of Python's per-process hash seed: for the life of a process "on Control maps" read 1,218 maps or 2
-- ("Twisted Minds has no series on Control maps"), and the same question flipped between runs.
--
-- Each fold's canonical spelling: the one FACEIT's own rounds use most, else the most common (owcsmuse/names.py holds
-- the same rule for what is written from now on: enrich and the liquipedia_rounds rebuild). Then the materialized
-- views that carry a map or mode name are refreshed, in dependency order, so a deploy does not serve the old groups.
-- The `name_variants` check fails if two stored spellings ever fold together again.

CREATE TEMP TABLE _spellings ON COMMIT DROP AS
SELECT 'map'::text AS kind, map_name AS name, (source = 'faceit') AS faceit, count(*) AS n
  FROM match_rounds WHERE map_name IS NOT NULL GROUP BY map_name, source
UNION ALL
SELECT 'mode', game_mode, (source = 'faceit'), count(*) FROM match_rounds WHERE game_mode IS NOT NULL GROUP BY game_mode, source
UNION ALL
SELECT 'map', map_name, false, count(*) FROM liquipedia_rounds WHERE map_name IS NOT NULL GROUP BY map_name
UNION ALL
SELECT 'mode', game_mode, false, count(*) FROM liquipedia_rounds WHERE game_mode IS NOT NULL GROUP BY game_mode;

CREATE TEMP TABLE _canon ON COMMIT DROP AS
SELECT DISTINCT ON (kind, fold_name(name)) kind, fold_name(name) AS k, name AS canonical
  FROM (SELECT kind, name, sum(n) FILTER (WHERE faceit) AS faceit_n, sum(n) AS n FROM _spellings GROUP BY kind, name) s
 ORDER BY kind, fold_name(name), coalesce(faceit_n, 0) DESC, n DESC, name;

UPDATE match_rounds r SET map_name = c.canonical
  FROM _canon c WHERE c.kind = 'map' AND fold_name(r.map_name) = c.k AND r.map_name <> c.canonical;
UPDATE match_rounds r SET game_mode = c.canonical
  FROM _canon c WHERE c.kind = 'mode' AND fold_name(r.game_mode) = c.k AND r.game_mode <> c.canonical;
UPDATE liquipedia_rounds r SET map_name = c.canonical
  FROM _canon c WHERE c.kind = 'map' AND fold_name(r.map_name) = c.k AND r.map_name <> c.canonical;
UPDATE liquipedia_rounds r SET game_mode = c.canonical
  FROM _canon c WHERE c.kind = 'mode' AND fold_name(r.game_mode) = c.k AND r.game_mode <> c.canonical;

REFRESH MATERIALIZED VIEW agg_player_stats;
REFRESH MATERIALIZED VIEW agg_team_maps;
REFRESH MATERIALIZED VIEW agg_map_modes;
REFRESH MATERIALIZED VIEW fact_player_map_results;
REFRESH MATERIALIZED VIEW fact_player_versus;
