-- FACEIT's own championship names are the ingestion key and stay exactly as
-- FACEIT wrote them - but the "OWCS Central" naming FACEIT uses internally
-- ("S9 EMEA OWCS Central - Playoffs") reads backwards for anyone who follows
-- the actual competition ("OWCS EMEA S9 Playoffs"). This is a display-only
-- transform: championships.name is untouched, so anything matching free text
-- against a stored name (see validate.py's championship lookup) still matches
-- what FACEIT actually called it.
CREATE OR REPLACE FUNCTION championship_display_name(name text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT regexp_replace(name, '^(S\d+) (EMEA|NA) OWCS Central - (.+)$', 'OWCS \2 \1 \3')
$$;
