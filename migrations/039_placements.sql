-- 039: where each team finished at an event (Stage 4), from Liquipedia's prize pool (GET /placement).
--
-- `liquipedia_placements` is a parsed copy of the stored /placement responses, rebuilt by `liquipedia placements
-- load` (sends nothing): one row per team placing on an event's root page, individual awards (MVP and the like) and
-- prize-pool entries without a placing left out. `placement` keeps Liquipedia's text ('1', '3-4', '5-8'); `place_high`
-- and `place_low` are its range, so "7th" finds a team placed 7-8. The page URL is kept for attribution (CC-BY-SA).
--
-- `placements` resolves each team name through the same decided anchors the `series` view uses (an international
-- entry first, as `series` matches a record's region), at the team's exit date:
-- an undecided name keeps Liquipedia's own name and is never merged into an entity (`team_id` NULL).

CREATE TABLE IF NOT EXISTS liquipedia_placements (
    objectname      text PRIMARY KEY,
    raw_id          bigint,
    pagename        text NOT NULL,
    page_url        text NOT NULL CHECK (page_url LIKE 'https://liquipedia.net/%'),
    championship_id text NOT NULL,
    prizepool_index integer,
    placement       text NOT NULL,
    place_high      integer NOT NULL CHECK (place_high >= 1),
    place_low       integer NOT NULL,
    team_name       text NOT NULL,
    team_template   text,
    qualifier       text,
    placed_at       timestamptz,
    CHECK (place_high <= place_low)
);
CREATE INDEX IF NOT EXISTS liquipedia_placements_championship_idx ON liquipedia_placements (championship_id, place_high);

CREATE OR REPLACE VIEW placements AS
SELECT p.objectname, p.championship_id, c.season, championship_display_name(c.name) AS championship_name,
       p.placement, p.place_high, p.place_low, p.team_name, p.team_template, p.qualifier, p.placed_at,
       p.page_url, p.pagename,
       t.team_id, ti.org_key,
       -- an org's own name when the name resolved into one; otherwise Liquipedia's name as the page spells it
       CASE WHEN ti.org_id IS NOT NULL THEN ti.display_name
            WHEN t.team_id LIKE 'lp:team:%' OR t.team_id IS NULL THEN p.team_name
            ELSE ti.display_name END AS display_name
  FROM liquipedia_placements p
  JOIN championships c ON c.championship_id = p.championship_id AND c.include
  LEFT JOIN LATERAL (
        SELECT CASE a.entity_type WHEN 'team' THEN a.entity_id ELSE 'lp:team:' || a.anchor END AS team_id
          FROM entity_anchors a
         WHERE a.anchor_kind = 'team_name' AND a.anchor = fold_name(p.team_name) AND a.region IN ('', 'international')
           AND coalesce(p.placed_at, 'infinity') >= a.valid_from AND coalesce(p.placed_at, '-infinity') < a.valid_to
         ORDER BY a.region DESC            -- an entry for the international events wins over a region-free one
         LIMIT 1) r ON true
  LEFT JOIN teams t ON t.team_id = r.team_id
  LEFT JOIN LATERAL team_identity_at(t.team_id, p.placed_at) ti ON true;
