-- 051: fact_hero_bans is materialized, refreshed with the other aggregates.
--
-- As a plain view it re-evaluated the series view (and its lateral identity lookups) inside every ban answer. Postgres
-- had no statistics for the result, and with a region filter it estimated one map where EMEA 2025 holds hundreds, then
-- planned nested loops that re-ran the series view per row: "least banned hero in EMEA 2025" took 72-92 s on the live
-- API (2026-11-03), while the unfiltered shapes took 3-5 s. Materialized, it is a 3,242-row table with statistics and
-- indexes. `liquipedia reconcile` rebuilds liquipedia_bans; the nightly `refresh` that follows it brings this up to
-- date (owcsmuse/aggregates.py lists it last: it reads only plain views and tables). hero_ban_maps stays a plain
-- view, now over the table.
--
-- Same name and columns as 049's view, so the running code reads it unchanged.

DROP VIEW IF EXISTS hero_ban_maps;
DROP VIEW IF EXISTS fact_hero_bans;

CREATE MATERIALIZED VIEW fact_hero_bans AS
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

CREATE UNIQUE INDEX fact_hero_bans_key ON fact_hero_bans (series_id, round_number, lp_side, hero);
CREATE INDEX fact_hero_bans_slice ON fact_hero_bans (season, region);
CREATE INDEX fact_hero_bans_hero ON fact_hero_bans (hero);
CREATE INDEX fact_hero_bans_org ON fact_hero_bans (org_key);
CREATE INDEX fact_hero_bans_opponent ON fact_hero_bans (opponent_org_key);

CREATE OR REPLACE VIEW hero_ban_maps AS
SELECT DISTINCT ON (series_id, round_number)
       series_id, match_id, round_number, map_name, game_mode, championship_id, season, region, played_at,
       lp_objectname, liquipedia_page_url
  FROM fact_hero_bans
 ORDER BY series_id, round_number;
