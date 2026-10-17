-- 045: a player's map record counts every map he played, not only the maps FACEIT returned stats for.
--
-- "sugarfree map record against zeruhh" said 22-20 in 42 maps; "sugarfree series record against zeruhh" said 7-4 in
-- series, 29-21 in maps (50). Both counted the same 11 series, but the map grain read only maps with a per-player row,
-- and 8 of the 50 have none:
--   * 7 from the two 2026 series FACEIT holds as results only (stats 404): Liquipedia has the map winners;
--   * 1 that FACEIT's /stats endpoint dropped (1-1d2eaf73 map 1, Ilios): the match's own detailed_results has it.
-- 22-20 answered "maps where FACEIT happened to return stats", which nobody asks. The maps were played and their
-- winners are known, so they count.
--
-- fact_player_map_results: one row per player per played map, with the opposing side.
--   * a map a player row covers (fact_player_maps): who actually played it, with his stats;
--   * a map no player row covers (FACEIT results-only, a map FACEIT's stats dropped, Liquipedia-enriched or
--     Liquipedia-only): the series' declared line-up (series_lineups, 042) on that map's side, no stats.
-- lineup_source says which: 'map' or 'series'. Stat answers stay on fact_player_maps, so a leaderboard never averages
-- over a map with no stats.
--
-- fact_player_versus becomes the pairing of those rows, so every player-vs-player map counts too. Player v org reads
-- fact_player_map_results directly, so it never depends on knowing the opposing line-up.
--
-- match_rounds.source gains 'faceit_results': a map recovered from FACEIT's detailed_results when /stats dropped it
-- (winner and score, no stats, no player rows).

ALTER TABLE match_rounds DROP CONSTRAINT IF EXISTS match_rounds_source_check;
ALTER TABLE match_rounds ADD CONSTRAINT match_rounds_source_check
    CHECK (source IN ('faceit', 'liquipedia', 'faceit_results'));

DROP MATERIALIZED VIEW IF EXISTS fact_player_versus;

CREATE MATERIALIZED VIEW fact_player_map_results AS
SELECT f.match_id, f.round_number, f.championship_id, f.season, f.region, f.started_at, f.map_name, f.game_mode,
       f.player_id, f.team_id, f.org_key, f.display_name,
       f.opponent_team_id, f.opponent_org_key, f.opponent_display_name,
       f.map_won AS won, f.map_drawn AS drawn,
       f.eliminations, f.deaths, f.assists, f.damage_dealt, f.healing_done, f.damage_mitigated,
       'map'::text AS lineup_source
  FROM fact_player_maps f
UNION ALL
SELECT t.match_id, t.round_number, t.championship_id, t.season, t.region, t.started_at, t.map_name, t.game_mode,
       l.player_id, t.team_id, t.org_key, t.display_name,
       t.opponent_team_id, t.opponent_org_key, t.opponent_display_name,
       t.won, t.drawn,
       NULL::int, NULL::int, NULL::int, NULL::numeric, NULL::numeric, NULL::numeric,
       'series'::text
  FROM fact_team_maps t
  JOIN series_lineups l ON l.match_id = t.match_id AND l.team_id = t.team_id
 WHERE NOT EXISTS (SELECT 1 FROM match_players mp WHERE mp.match_id = t.match_id AND mp.round_number = t.round_number);
CREATE INDEX fact_player_map_results_player_idx ON fact_player_map_results (player_id, opponent_org_key);
CREATE INDEX fact_player_map_results_map_idx    ON fact_player_map_results (match_id, round_number);
CREATE INDEX fact_player_map_results_org_idx    ON fact_player_map_results (opponent_org_key);

CREATE MATERIALIZED VIEW fact_player_versus AS
SELECT a.match_id, a.round_number, a.championship_id, a.season, a.region, a.started_at, a.map_name, a.game_mode,
       a.player_id, a.team_id, a.org_key, a.display_name,
       b.player_id AS opponent_player_id, b.team_id AS opponent_team_id,
       b.org_key AS opponent_org_key, b.display_name AS opponent_display_name,
       a.won, a.drawn,
       a.eliminations, a.deaths, a.assists, a.damage_dealt, a.healing_done, a.damage_mitigated,
       a.lineup_source
  FROM fact_player_map_results a
  JOIN fact_player_map_results b
    ON b.match_id = a.match_id AND b.round_number = a.round_number AND b.team_id IS DISTINCT FROM a.team_id;
CREATE INDEX fact_player_versus_pair_idx ON fact_player_versus (player_id, opponent_player_id);
CREATE INDEX fact_player_versus_org_idx  ON fact_player_versus (player_id, opponent_org_key);
