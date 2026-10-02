-- Capability, not just coverage.
--
-- Coverage says which stat keys exist per season. It has no concept of a slice
-- where no player stats exist at all: a results-only source (Liquipedia) gives
-- series results, map scores and placings and never a player stat, and so does
-- a FACEIT result_only competition (Dreamhack Dallas). Two tables carry that:
--   region_sources       declared: which sources cover a region and whether any of
--                        them records player stats. Korea is results-only by
--                        construction, before any of its data is loaded.
--   source_capabilities  derived per included championship from provenance:
--                        series results, map results, player stats.
-- The query layer refuses a player-stat question over a slice with no player
-- stats (reason code results_only) and names the results-only part of a mixed
-- slice instead of ranking over it silently.

CREATE TABLE region_sources (
    region       text PRIMARY KEY,
    sources      text[] NOT NULL,
    player_stats boolean NOT NULL,
    note         text
);
INSERT INTO region_sources (region, sources, player_stats, note) VALUES
    ('na',            '{faceit,liquipedia}', true,  'FACEIT main series with per-map player stats; Liquipedia fills map results'),
    ('emea',          '{faceit,liquipedia}', true,  'FACEIT main series with per-map player stats; Liquipedia fills map results'),
    ('international', '{faceit,liquipedia}', true,  'LAN events on FACEIT are often result_only (Dreamhack Dallas: no player stats); the derived table says which'),
    ('korea',         '{liquipedia}',        false, 'Korea has no usable FACEIT data; Liquipedia carries results, map scores and picks, never player stats');

CREATE MATERIALIZED VIEW source_capabilities AS
SELECT c.championship_id, c.name, c.scope_region AS region, c.season,
       count(s.series_id)                                        AS series,
       coalesce(bool_or(s.maps_played > 0), false)                AS map_results,
       coalesce(bool_or(s.has_player_stats), false)               AS player_stats,
       coalesce((SELECT array_agg(DISTINCT x) FROM (SELECT unnest(s2.sources) AS x FROM series s2
                  WHERE s2.championship_id = c.championship_id) u), '{}'::text[]) AS sources
  FROM championships c
  LEFT JOIN series s ON s.championship_id = c.championship_id
 WHERE c.include
 GROUP BY c.championship_id, c.name, c.scope_region, c.season;
CREATE UNIQUE INDEX source_capabilities_idx ON source_capabilities (championship_id);
