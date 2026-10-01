-- OWCS naming for competitions, display-only.
--
-- FACEIT's own championship names stay exactly as FACEIT wrote them in championships.name (the ingestion key,
-- and what free-text matching in validate.py compares against). "S9 NA OWCS Central - Playoffs" is FACEIT League's
-- season number; the competition people know is OWCS 2026 NA Stage 2 Playoffs. Liquipedia has the canonical name,
-- and scope/liquipedia_map.json pairs each FACEIT competition with its Liquipedia page.
--
-- competition_names holds only REVIEWED names: `python -m owcsmuse competitions propose` writes a report, a person
-- decides in scope/competition_names.json, and `competitions load` copies the decisions here. Until a competition
-- has a row, championship_display_name() falls back to the previous reordering of FACEIT's name, so an unreviewed
-- proposal never changes what anyone sees.
CREATE TABLE IF NOT EXISTS competition_names (
    championship_id text PRIMARY KEY,
    faceit_name     text NOT NULL UNIQUE,   -- the name this was decided against; a FACEIT rename stops it applying
    display_name    text NOT NULL,
    basis           text NOT NULL,          -- liquipedia | faceit-name | manual
    page            text,                   -- the Liquipedia page behind it, when there is one
    decided_at      timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION championship_display_name(name text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        (SELECT cn.display_name FROM competition_names cn WHERE cn.faceit_name = name),
        regexp_replace(name, '^(S\d+) (EMEA|NA) OWCS Central - (.+)$', 'OWCS \2 \1 \3')
    )
$$;
