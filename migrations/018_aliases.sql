-- Community shorthand ("SSG" for SpaceStation Gaming, "TL" for Team Liquid) is
-- not derivable from anything FACEIT recorded: no team in this warehouse was
-- ever literally named "SSG" on FACEIT, so entity_names (built entirely from
-- FACEIT's own nickname and team-name history) has nothing to match it against,
-- and the fuzzy scorer in resolve.py picks something unrelated instead.
--
-- Where the abbreviation DOES appear in FACEIT's own history - a team really
-- was named "SOG" at some point - that already resolves through entity_names
-- and needs nothing here. This table is only for the abbreviations nobody on
-- FACEIT ever typed: a human decision, reviewed the same way an org merge is,
-- never a hardcoded guess table baked into the resolver.
--
-- An alias means exactly one entity - that is the point of it being a
-- shortcut - so the alias itself (folded at write time; see aliases.py) is the
-- primary key, not a pair. Setting it again replaces the mapping.
CREATE TABLE entity_aliases (
    alias       text PRIMARY KEY,
    entity_type text NOT NULL CHECK (entity_type IN ('player', 'team', 'org')),
    entity_id   text NOT NULL,
    note        text,
    decided_at  timestamptz NOT NULL DEFAULT now()
);
