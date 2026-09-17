-- Scope classification for championships. `region` already holds FACEIT's own
-- region field, so the reviewed classification lives in `scope_region`.
--
-- scope_region / tier / season are proposed by owcsmuse.scope.classify() and can be
-- overridden by reviewed decisions (scope/decisions.json). `include` remains
-- the single switch the collector and the aggregates honour.

ALTER TABLE championships
    ADD COLUMN scope_region text CHECK (scope_region IN ('na', 'emea', 'international', 'other')),
    ADD COLUMN tier   text CHECK (tier IN ('main', 'qualifier', 'relegation', 'unknown')),
    ADD COLUMN season integer,
    ADD COLUMN classification_source text CHECK (classification_source IN ('auto', 'manual')),
    ADD COLUMN classification_evidence jsonb,
    ADD COLUMN decision_note text,
    ADD COLUMN classified_at timestamptz;

CREATE INDEX championships_scope_idx ON championships (scope_region, tier, season) WHERE include;
