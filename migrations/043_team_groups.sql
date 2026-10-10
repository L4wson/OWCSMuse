-- 043: season-scoped groups of teams, starting with the OWCS partner teams.
--
-- Partner status is per season and per region and changes year to year, so it is a group with a season, not a flag on
-- a team. Membership comes from the reviewed scope/partner_teams.json (Liquipedia's own record: a Stage 1 prize-pool
-- row whose qualifier is "Partner Team"), loaded by `groups load`; nothing infers it.
--
-- team_groups holds the reviewed rows under Liquipedia's names. team_group_members resolves each name through the same
-- decided anchors the series and placements views use, at the row's own date (a region-qualified entry first: "Geekay
-- Esports" is two teams), so a member keys as the fact views key it - an org, or a bare team id's era. A name no
-- decision resolves stays unresolved (org_key NULL), never guessed.

CREATE TABLE IF NOT EXISTS team_groups (
    group_key       text        NOT NULL CHECK (group_key IN ('partner')),
    season          integer     NOT NULL,
    region          text        NOT NULL,
    liquipedia_name text        NOT NULL,
    page            text        NOT NULL,
    placed_at       timestamptz NOT NULL,
    raw_id          bigint,
    PRIMARY KEY (group_key, season, region, liquipedia_name)
);

CREATE OR REPLACE VIEW team_group_members AS
SELECT g.group_key, g.season, g.region, g.liquipedia_name, g.page, g.placed_at,
       t.team_id, ti.org_key, coalesce(CASE WHEN ti.org_id IS NOT NULL OR t.team_id NOT LIKE 'lp:team:%' THEN ti.display_name END,
                                       g.liquipedia_name) AS display_name
  FROM team_groups g
  LEFT JOIN LATERAL (
        SELECT CASE a.entity_type WHEN 'team' THEN a.entity_id ELSE 'lp:team:' || a.anchor
                    || CASE WHEN a.region <> '' THEN '|' || a.region ELSE '' END END AS team_id
          FROM entity_anchors a
         WHERE a.anchor_kind = 'team_name' AND a.anchor = fold_name(g.liquipedia_name) AND a.region IN ('', g.region)
           AND g.placed_at >= a.valid_from AND g.placed_at < a.valid_to
         ORDER BY a.region DESC
         LIMIT 1) r ON true
  LEFT JOIN teams t ON t.team_id = r.team_id
  LEFT JOIN LATERAL team_identity_at(t.team_id, g.placed_at) ti ON true;
