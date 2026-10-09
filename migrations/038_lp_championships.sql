-- 038: championships that exist only on Liquipedia (Stage 4: LAN and international events).
--
-- `series` takes a Liquipedia record only through an included championship (028): until now that was always the
-- FACEIT competition scope/liquipedia_map.json pairs with the record's page. The World Finals, the Midseason
-- Championships and EWC 2024 have no FACEIT competition, so their records reached no answer. A Liquipedia-only
-- championship is keyed `lp:<root page>` (the event's Liquipedia page, underscored), written by
-- `liquipedia events load` from the reviewed scope/liquipedia_events.json, and carries the same scope columns
-- (scope_region, tier, season, include) every other championship does. `liquipedia_page` is the root page whose
-- subpages hold the event's matches.

ALTER TABLE championships DROP CONSTRAINT IF EXISTS championships_source_check;
ALTER TABLE championships
    ADD CONSTRAINT championships_source_check CHECK (source IN ('championship_api', 'history', 'liquipedia')),
    ADD COLUMN IF NOT EXISTS liquipedia_page text,
    ADD CONSTRAINT championships_liquipedia_key CHECK (
        (source = 'liquipedia') = (championship_id LIKE 'lp:%')
        AND (source <> 'liquipedia' OR liquipedia_page IS NOT NULL));
