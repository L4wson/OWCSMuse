-- The resolver now returns org ids, but the aggregates were still keyed on
-- team_id, so an org-level question found nothing. Carry org_key on the
-- team-level aggregates so a question can be answered at org grain while the
-- team_id column stays for precise per-season queries.
DROP MATERIALIZED VIEW IF EXISTS agg_team_matches CASCADE;
CREATE MATERIALIZED VIEW agg_team_matches AS
SELECT
    team_id, org_key, org_id, display_name, championship_id, season, region,
    count(*)                        AS matches,
    count(*) FILTER (WHERE won)     AS wins,
    count(*) FILTER (WHERE NOT won) AS losses,
    sum(map_wins)   AS map_wins,
    sum(map_losses) AS map_losses,
    sum(maps_played) AS maps,
    round(100.0 * count(*) FILTER (WHERE won) / count(*), 1) AS win_pct,
    min(started_at) AS first_match_at, max(started_at) AS last_match_at
FROM fact_team_matches
GROUP BY team_id, org_key, org_id, display_name, championship_id, season, region;
CREATE INDEX agg_team_matches_team_idx ON agg_team_matches (team_id);
CREATE INDEX agg_team_matches_org_idx  ON agg_team_matches (org_key);

DROP MATERIALIZED VIEW IF EXISTS agg_team_maps CASCADE;
CREATE MATERIALIZED VIEW agg_team_maps AS
SELECT
    team_id, org_key, org_id, display_name, championship_id, season, region, map_name, game_mode,
    count(*)                                      AS maps,
    count(DISTINCT match_id)                      AS matches,
    count(*) FILTER (WHERE won)                   AS wins,
    count(*) FILTER (WHERE NOT won AND NOT drawn) AS losses,
    count(*) FILTER (WHERE drawn)                 AS draws,
    round(100.0 * count(*) FILTER (WHERE won) / count(*), 1) AS win_pct,
    sum(score) AS points_for, sum(opp_score) AS points_against,
    min(started_at) AS first_map_at, max(started_at) AS last_map_at
FROM fact_team_maps
GROUP BY team_id, org_key, org_id, display_name, championship_id, season, region, map_name, game_mode;
CREATE INDEX agg_team_maps_team_idx ON agg_team_maps (team_id);
CREATE INDEX agg_team_maps_org_idx  ON agg_team_maps (org_key);

DROP MATERIALIZED VIEW IF EXISTS agg_player_stats CASCADE;
CREATE MATERIALIZED VIEW agg_player_stats AS
SELECT
    player_id, team_id, org_key, org_id, championship_id, season, region, map_name, game_mode,
    count(*)                          AS maps,
    count(DISTINCT match_id)          AS matches,
    count(*) FILTER (WHERE map_won)   AS maps_won,
    count(*) FILTER (WHERE map_drawn) AS maps_drawn,
    sum(eliminations) AS sum_eliminations, count(eliminations) AS maps_with_eliminations,
    sum(final_blows) AS sum_final_blows, count(final_blows) AS maps_with_final_blows,
    sum(deaths) AS sum_deaths, count(deaths) AS maps_with_deaths,
    sum(assists) AS sum_assists, count(assists) AS maps_with_assists,
    sum(solo_kills) AS sum_solo_kills, count(solo_kills) AS maps_with_solo_kills,
    sum(multi_kills) AS sum_multi_kills, count(multi_kills) AS maps_with_multi_kills,
    sum(environmental_kills) AS sum_environmental_kills, count(environmental_kills) AS maps_with_environmental_kills,
    sum(damage_dealt) AS sum_damage_dealt, count(damage_dealt) AS maps_with_damage_dealt,
    sum(healing_done) AS sum_healing_done, count(healing_done) AS maps_with_healing_done,
    sum(damage_mitigated) AS sum_damage_mitigated, count(damage_mitigated) AS maps_with_damage_mitigated,
    sum(objective_time) AS sum_objective_time, count(objective_time) AS maps_with_objective_time,
    sum(time_played) AS sum_time_played, count(time_played) AS maps_with_time_played,
    min(started_at) AS first_map_at, max(started_at) AS last_map_at
FROM fact_player_maps
GROUP BY player_id, team_id, org_key, org_id, championship_id, season, region, map_name, game_mode;
CREATE INDEX agg_player_stats_player_idx ON agg_player_stats (player_id);
CREATE INDEX agg_player_stats_champ_idx  ON agg_player_stats (championship_id);
CREATE INDEX agg_player_stats_org_idx    ON agg_player_stats (org_key);
