-- Aggregation layer read by the query engine.
--
-- Conventions
--   * fact_* are plain views over the scoped raw tables (championships.include
--     AND matches.ingest_state = 'complete'). agg_* / stat_* / entity_names are
--     MATERIALIZED views refreshed by `python -m owcsmuse refresh`.
--   * Every aggregate carries sample sizes: `maps` (maps played) and `matches`.
--   * Stable typed stats aggregate as sum_<stat> plus maps_with_<stat>, so a
--     per-map average is sum / maps_with, never sum / maps. Extended stats are
--     in agg_player_stat_long keyed by their FACEIT stat key, with coverage.
--   * Map duration exists only where the payload carries "Time Played"
--     (2026-era payloads). map_durations.duration_seconds is NULL otherwise.

-- ------------------------------------------------------------- helpers

-- Accent-folding, lower-casing for name matching without extensions.
CREATE OR REPLACE FUNCTION fold_name(t text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT lower(translate(t,
        'ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖØòóôõöøÙÚÛÜùúûüÝýÿÑñÇçŠšŽžĀāĒēĪīŌōŪūĂăĄąĆćĘęŁłŃńŚśŹźŻżĞğİıŞş',
        'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOOooooooUUUUuuuuYyyNnCcSsZzAaEeIiOoUuAaAaCcEeLlNnSsZzZzGgIiSs'))
$$;

-- FACEIT stat values are strings; only numeric-looking ones aggregate.
CREATE OR REPLACE FUNCTION stat_num(v text) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN v ~ '^-?[0-9]+(\.[0-9]+)?$' THEN v::numeric END
$$;

-- ------------------------------------------------------------- facts

-- One row per player per map played, inside scope.
CREATE VIEW fact_player_maps AS
SELECT
    mp.match_id,
    mp.round_number,
    mp.player_id,
    mp.team_id,
    CASE WHEN r.team1_team_id = mp.team_id THEN r.team2_team_id ELSE r.team1_team_id END AS opponent_team_id,
    m.championship_id,
    c.season,
    c.scope_region AS region,
    c.tier,
    m.started_at,
    r.map_name,
    r.game_mode,
    (r.winner_team_id = mp.team_id)  AS map_won,
    (r.winner_team_id IS NULL)       AS map_drawn,
    mp.role,
    mp.eliminations, mp.final_blows, mp.deaths, mp.assists,
    mp.solo_kills, mp.multi_kills, mp.environmental_kills,
    mp.damage_dealt, mp.healing_done, mp.damage_mitigated,
    mp.objective_time, mp.time_played,
    mp.stats
FROM match_players mp
JOIN match_rounds  r ON (r.match_id, r.round_number) = (mp.match_id, mp.round_number)
JOIN matches       m ON m.match_id = mp.match_id
JOIN championships c ON c.championship_id = m.championship_id
WHERE m.ingest_state = 'complete' AND c.include;

-- One row per team per map played (each map appears twice, once per side).
CREATE VIEW fact_team_maps AS
SELECT
    r.match_id, r.round_number, t.team_id, t.opponent_team_id, t.score, t.opp_score,
    m.championship_id, c.season, c.scope_region AS region, m.started_at, r.map_name, r.game_mode,
    (r.winner_team_id = t.team_id) AS won,
    (r.winner_team_id IS NULL)     AS drawn
FROM match_rounds r
JOIN matches       m ON m.match_id = r.match_id
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (VALUES
    (r.team1_team_id, r.team2_team_id, r.team1_score, r.team2_score),
    (r.team2_team_id, r.team1_team_id, r.team2_score, r.team1_score)
) AS t(team_id, opponent_team_id, score, opp_score)
WHERE m.ingest_state = 'complete' AND c.include AND t.team_id IS NOT NULL;

-- One row per team per series (each match appears twice, once per side).
CREATE VIEW fact_team_matches AS
SELECT
    m.match_id, t.team_id, t.opponent_team_id, t.faction,
    m.championship_id, c.season, c.scope_region AS region, m.started_at, m.best_of, m.maps_played,
    (m.winner_team_id = t.team_id) AS won,
    t.score AS map_wins, t.opp_score AS map_losses
FROM matches m
JOIN championships c ON c.championship_id = m.championship_id
CROSS JOIN LATERAL (VALUES
    (m.faction1_team_id, m.faction2_team_id, 'faction1', m.faction1_score, m.faction2_score),
    (m.faction2_team_id, m.faction1_team_id, 'faction2', m.faction2_score, m.faction1_score)
) AS t(team_id, opponent_team_id, faction, score, opp_score)
WHERE m.ingest_state = 'complete' AND m.status = 'FINISHED' AND c.include AND t.team_id IS NOT NULL;

-- Map duration where derivable. Only "Time Played" (seconds, per player) carries it.
CREATE VIEW map_durations AS
SELECT match_id, round_number,
       max(time_played)     AS duration_seconds,
       'player_time_played' AS duration_source,
       count(time_played)   AS players_with_time
FROM match_players
WHERE time_played IS NOT NULL
GROUP BY match_id, round_number;

-- ------------------------------------------------------------- player aggregates

-- Finest grain: player x team x championship x map x mode. Slice by summing.
CREATE MATERIALIZED VIEW agg_player_stats AS
SELECT
    player_id, team_id, championship_id, season, region, map_name, game_mode,
    count(*)                                   AS maps,
    count(DISTINCT match_id)                   AS matches,
    count(*) FILTER (WHERE map_won)            AS maps_won,
    count(*) FILTER (WHERE map_drawn)          AS maps_drawn,
    sum(eliminations)        AS sum_eliminations,        count(eliminations)        AS maps_with_eliminations,
    sum(final_blows)         AS sum_final_blows,         count(final_blows)         AS maps_with_final_blows,
    sum(deaths)              AS sum_deaths,              count(deaths)              AS maps_with_deaths,
    sum(assists)             AS sum_assists,             count(assists)             AS maps_with_assists,
    sum(solo_kills)          AS sum_solo_kills,          count(solo_kills)          AS maps_with_solo_kills,
    sum(multi_kills)         AS sum_multi_kills,         count(multi_kills)         AS maps_with_multi_kills,
    sum(environmental_kills) AS sum_environmental_kills, count(environmental_kills) AS maps_with_environmental_kills,
    sum(damage_dealt)        AS sum_damage_dealt,        count(damage_dealt)        AS maps_with_damage_dealt,
    sum(healing_done)        AS sum_healing_done,        count(healing_done)        AS maps_with_healing_done,
    sum(damage_mitigated)    AS sum_damage_mitigated,    count(damage_mitigated)    AS maps_with_damage_mitigated,
    sum(objective_time)      AS sum_objective_time,      count(objective_time)      AS maps_with_objective_time,
    sum(time_played)         AS sum_time_played,         count(time_played)         AS maps_with_time_played,
    min(started_at) AS first_map_at,
    max(started_at) AS last_map_at
FROM fact_player_maps
GROUP BY player_id, team_id, championship_id, season, region, map_name, game_mode;
CREATE INDEX agg_player_stats_player_idx ON agg_player_stats (player_id);
CREATE INDEX agg_player_stats_champ_idx  ON agg_player_stats (championship_id);

-- Convenience roll-up: player x season with per-map averages already divided by coverage.
CREATE MATERIALIZED VIEW agg_player_season AS
SELECT
    player_id, season,
    count(*) AS maps, count(DISTINCT match_id) AS matches,
    count(*) FILTER (WHERE map_won) AS maps_won,
    sum(eliminations)      AS sum_eliminations,     count(eliminations)     AS maps_with_eliminations,
    avg(eliminations)      AS avg_eliminations,
    sum(final_blows)       AS sum_final_blows,      count(final_blows)      AS maps_with_final_blows,
    avg(final_blows)       AS avg_final_blows,
    sum(deaths)            AS sum_deaths,           count(deaths)           AS maps_with_deaths,
    avg(deaths)            AS avg_deaths,
    sum(assists)           AS sum_assists,          count(assists)          AS maps_with_assists,
    avg(assists)           AS avg_assists,
    sum(damage_dealt)      AS sum_damage_dealt,     count(damage_dealt)     AS maps_with_damage_dealt,
    avg(damage_dealt)      AS avg_damage_dealt,
    sum(healing_done)      AS sum_healing_done,     count(healing_done)     AS maps_with_healing_done,
    avg(healing_done)      AS avg_healing_done,
    sum(damage_mitigated)  AS sum_damage_mitigated, count(damage_mitigated) AS maps_with_damage_mitigated,
    avg(damage_mitigated)  AS avg_damage_mitigated,
    CASE WHEN sum(deaths) > 0 THEN round(sum(eliminations)::numeric / sum(deaths), 2) END AS kd_ratio,
    min(started_at) AS first_map_at, max(started_at) AS last_map_at
FROM fact_player_maps
GROUP BY player_id, season;
CREATE INDEX agg_player_season_player_idx ON agg_player_season (player_id);

-- Every numeric FACEIT stat key, long format, with its own coverage.
CREATE MATERIALIZED VIEW agg_player_stat_long AS
SELECT
    f.player_id, f.championship_id, f.season, kv.key AS stat_key,
    count(*)                 AS maps_with_stat,
    sum(stat_num(kv.value))  AS total,
    avg(stat_num(kv.value))  AS avg_per_map,
    min(stat_num(kv.value))  AS min_per_map,
    max(stat_num(kv.value))  AS max_per_map,
    min(f.started_at) AS first_at, max(f.started_at) AS last_at
FROM fact_player_maps f
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE stat_num(kv.value) IS NOT NULL
GROUP BY f.player_id, f.championship_id, f.season, kv.key;
CREATE INDEX agg_player_stat_long_key_idx ON agg_player_stat_long (stat_key, season);

-- ------------------------------------------------------------- stat availability

-- Which stat keys exist for which championship, and how completely.
CREATE MATERIALIZED VIEW stat_coverage AS
WITH totals AS (
    SELECT championship_id, count(*) AS rows_total FROM fact_player_maps GROUP BY championship_id
)
SELECT
    f.championship_id, f.season, c.name AS championship_name, kv.key AS stat_key,
    count(*)                                          AS rows_with_stat,
    t.rows_total,
    round(100.0 * count(*) / t.rows_total, 1)         AS coverage_pct,
    bool_and(stat_num(kv.value) IS NOT NULL)          AS is_numeric,
    min(f.started_at) AS first_at, max(f.started_at)  AS last_at
FROM fact_player_maps f
JOIN championships c ON c.championship_id = f.championship_id
JOIN totals t ON t.championship_id = f.championship_id
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE kv.value IS NOT NULL AND kv.value <> ''
GROUP BY f.championship_id, f.season, c.name, kv.key, t.rows_total;
CREATE INDEX stat_coverage_key_idx ON stat_coverage (stat_key);

CREATE MATERIALIZED VIEW stat_coverage_season AS
WITH totals AS (
    SELECT season, count(*) AS rows_total, count(DISTINCT championship_id) AS championships_total
    FROM fact_player_maps GROUP BY season
)
SELECT
    f.season, kv.key AS stat_key,
    count(*)                                  AS rows_with_stat,
    t.rows_total,
    round(100.0 * count(*) / t.rows_total, 1) AS coverage_pct,
    count(DISTINCT f.championship_id)         AS championships_with_stat,
    t.championships_total,
    min(f.started_at) AS first_at, max(f.started_at) AS last_at
FROM fact_player_maps f
JOIN totals t ON t.season = f.season
CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
WHERE kv.value IS NOT NULL AND kv.value <> ''
GROUP BY f.season, kv.key, t.rows_total, t.championships_total;

-- Coverage window of one stat within an optional season / championship slice.
CREATE OR REPLACE FUNCTION stat_coverage_summary(
    p_stat text, p_season integer DEFAULT NULL, p_championship text DEFAULT NULL
) RETURNS TABLE (
    stat_key text, maps_total bigint, maps_with_stat bigint, coverage_pct numeric,
    seasons_with_stat integer[], seasons_without_stat integer[],
    first_at timestamptz, last_at timestamptz
) LANGUAGE sql STABLE AS $$
    WITH scope AS (
        SELECT * FROM fact_player_maps
        WHERE (p_season IS NULL OR season = p_season)
          AND (p_championship IS NULL OR championship_id = p_championship)
    ),
    has AS (SELECT * FROM scope WHERE stat_num(stats ->> p_stat) IS NOT NULL)
    SELECT
        p_stat,
        (SELECT count(*) FROM scope),
        (SELECT count(*) FROM has),
        CASE WHEN (SELECT count(*) FROM scope) > 0
             THEN round(100.0 * (SELECT count(*) FROM has) / (SELECT count(*) FROM scope), 1) ELSE 0 END,
        (SELECT array_agg(DISTINCT season ORDER BY season) FROM has WHERE season IS NOT NULL),
        (SELECT array_agg(DISTINCT season ORDER BY season) FROM scope
          WHERE season IS NOT NULL AND season NOT IN (SELECT season FROM has WHERE season IS NOT NULL)),
        (SELECT min(started_at) FROM has),
        (SELECT max(started_at) FROM has)
$$;

-- Leaderboard over any FACEIT stat key. Each row reports its own coverage:
-- maps_with_stat vs maps_played. Players with no data for the stat are omitted.
CREATE OR REPLACE FUNCTION stat_leaderboard(
    p_stat text, p_season integer DEFAULT NULL, p_championship text DEFAULT NULL,
    p_min_maps integer DEFAULT 1, p_limit integer DEFAULT 20, p_order text DEFAULT 'total'
) RETURNS TABLE (
    player_id text, nickname text, maps_with_stat bigint, maps_played bigint, coverage_pct numeric,
    total numeric, avg_per_map numeric, seasons integer[]
) LANGUAGE sql STABLE AS $$
    SELECT
        f.player_id, p.nickname,
        count(*) FILTER (WHERE stat_num(f.stats ->> p_stat) IS NOT NULL) AS maps_with_stat,
        count(*) AS maps_played,
        round(100.0 * count(*) FILTER (WHERE stat_num(f.stats ->> p_stat) IS NOT NULL) / count(*), 1) AS coverage_pct,
        sum(stat_num(f.stats ->> p_stat)) AS total,
        avg(stat_num(f.stats ->> p_stat)) AS avg_per_map,
        array_agg(DISTINCT f.season ORDER BY f.season) FILTER (WHERE stat_num(f.stats ->> p_stat) IS NOT NULL) AS seasons
    FROM fact_player_maps f
    JOIN players p ON p.player_id = f.player_id
    WHERE (p_season IS NULL OR f.season = p_season)
      AND (p_championship IS NULL OR f.championship_id = p_championship)
    GROUP BY f.player_id, p.nickname
    HAVING count(*) FILTER (WHERE stat_num(f.stats ->> p_stat) IS NOT NULL) >= greatest(p_min_maps, 1)
    ORDER BY CASE WHEN p_order = 'avg' THEN avg(stat_num(f.stats ->> p_stat)) ELSE sum(stat_num(f.stats ->> p_stat)) END DESC NULLS LAST,
             maps_with_stat DESC
    LIMIT p_limit
$$;

-- ------------------------------------------------------------- team aggregates

CREATE MATERIALIZED VIEW agg_team_matches AS
SELECT
    team_id, championship_id, season, region,
    count(*)                              AS matches,
    count(*) FILTER (WHERE won)           AS wins,
    count(*) FILTER (WHERE NOT won)       AS losses,
    sum(map_wins)                         AS map_wins,
    sum(map_losses)                       AS map_losses,
    sum(maps_played)                      AS maps,
    round(100.0 * count(*) FILTER (WHERE won) / count(*), 1) AS win_pct,
    min(started_at) AS first_match_at, max(started_at) AS last_match_at
FROM fact_team_matches
GROUP BY team_id, championship_id, season, region;
CREATE INDEX agg_team_matches_team_idx ON agg_team_matches (team_id);

CREATE MATERIALIZED VIEW agg_team_maps AS
SELECT
    team_id, championship_id, season, region, map_name, game_mode,
    count(*)                                     AS maps,
    count(DISTINCT match_id)                     AS matches,
    count(*) FILTER (WHERE won)                  AS wins,
    count(*) FILTER (WHERE NOT won AND NOT drawn) AS losses,
    count(*) FILTER (WHERE drawn)                AS draws,
    round(100.0 * count(*) FILTER (WHERE won) / count(*), 1) AS win_pct,
    sum(score) AS points_for, sum(opp_score) AS points_against,
    min(started_at) AS first_map_at, max(started_at) AS last_map_at
FROM fact_team_maps
GROUP BY team_id, championship_id, season, region, map_name, game_mode;
CREATE INDEX agg_team_maps_team_idx ON agg_team_maps (team_id);

-- team_a < team_b so each pairing appears once per championship.
CREATE MATERIALIZED VIEW agg_head_to_head AS
SELECT
    team_id          AS team_a,
    opponent_team_id AS team_b,
    championship_id, season, region,
    count(*)                        AS matches,
    count(*) FILTER (WHERE won)     AS a_wins,
    count(*) FILTER (WHERE NOT won) AS b_wins,
    sum(map_wins)                   AS a_map_wins,
    sum(map_losses)                 AS b_map_wins,
    sum(maps_played)                AS maps,
    min(started_at) AS first_match_at, max(started_at) AS last_match_at
FROM fact_team_matches
WHERE team_id < opponent_team_id
GROUP BY team_id, opponent_team_id, championship_id, season, region;
CREATE INDEX agg_head_to_head_idx ON agg_head_to_head (team_a, team_b);

-- ------------------------------------------------------------- map / mode

CREATE MATERIALIZED VIEW agg_map_modes AS
SELECT
    r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region AS region,
    count(*)                                             AS maps,
    count(DISTINCT r.match_id)                           AS matches,
    count(*) FILTER (WHERE r.winner_team_id = r.team1_team_id) AS team1_wins,
    count(*) FILTER (WHERE r.winner_team_id = r.team2_team_id) AS team2_wins,
    count(*) FILTER (WHERE r.winner_team_id IS NULL)     AS draws,
    avg(r.team1_score + r.team2_score)                   AS avg_total_score,
    count(d.duration_seconds)                            AS maps_with_duration,
    avg(d.duration_seconds)                              AS avg_duration_seconds,
    min(m.started_at) AS first_map_at, max(m.started_at) AS last_map_at
FROM match_rounds r
JOIN matches       m ON m.match_id = r.match_id
JOIN championships c ON c.championship_id = m.championship_id
LEFT JOIN map_durations d ON (d.match_id, d.round_number) = (r.match_id, r.round_number)
WHERE m.ingest_state = 'complete' AND c.include
GROUP BY r.map_name, r.game_mode, m.championship_id, c.season, c.scope_region;

-- ------------------------------------------------------------- entity resolution

-- Every name an entity has been known by, folded for matching.
CREATE MATERIALIZED VIEW entity_names AS
SELECT 'player'::text AS entity_type, p.player_id AS entity_id, p.nickname AS name,
       'current_nickname'::text AS name_kind, fold_name(p.nickname) AS name_folded,
       p.nickname AS current_name, p.last_seen_at
FROM players p
UNION ALL
SELECT 'player', p.player_id, p.game_player_name, 'game_name', fold_name(p.game_player_name), p.nickname, p.last_seen_at
FROM players p
WHERE p.game_player_name IS NOT NULL AND fold_name(p.game_player_name) <> fold_name(p.nickname)
UNION ALL
SELECT 'player', pn.player_id, pn.nickname, 'historical_nickname', fold_name(pn.nickname), p.nickname, pn.last_seen_at
FROM player_nicknames pn JOIN players p ON p.player_id = pn.player_id
WHERE pn.nickname <> p.nickname
UNION ALL
SELECT 'team', t.team_id, t.name, 'current_name', fold_name(t.name), t.name, t.last_seen_at
FROM teams t WHERE t.name IS NOT NULL
UNION ALL
SELECT 'team', tn.team_id, tn.name, 'historical_name', fold_name(tn.name), t.name, tn.last_seen_at
FROM team_names tn JOIN teams t ON t.team_id = tn.team_id
WHERE tn.name <> t.name;
CREATE INDEX entity_names_idx ON entity_names (entity_type, name_folded);
