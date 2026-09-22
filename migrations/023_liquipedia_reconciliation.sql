-- Stage 1 of the Liquipedia integration: Liquipedia's match records, parsed out of raw_payloads, and the links
-- between them and FACEIT matches. Nothing here feeds an answer: links are reviewed first (see the README).
--
-- liquipedia_matches is a parsed copy, always rebuildable from raw_payloads (raw_id says which response). Every row
-- carries page_url, mandatory and checked: Liquipedia's data is CC-BY-SA and the attribution promised in the API
-- application must be attachable to whatever is derived from a row.
CREATE TABLE liquipedia_matches (
    objectname      text        PRIMARY KEY,                 -- Liquipedia's row key: <pageid>_<match2id>
    raw_id          bigint      NOT NULL REFERENCES raw_payloads (id),
    match2id        text        NOT NULL,
    bracket_id      text        NOT NULL,
    pagename        text        NOT NULL,                    -- the page the match sits on, e.g. .../EMEA/Stage_2/Regular_Season
    page_url        text        NOT NULL CHECK (page_url LIKE 'https://liquipedia.net/%'),
    region          text,                                    -- na | emea | korea | china | other, from the page name
    championship_id text,                                    -- the FACEIT competition scope/liquipedia_map.json pairs with the page
    played_at       timestamptz NOT NULL,                    -- Liquipedia's `date`, which is UTC and equals extradata.timestamp
    best_of         integer,
    finished        boolean,
    winner          smallint,                                -- 1, 2, or 0 for none
    walkover        text,
    team1_name      text,
    team2_name      text,
    score1          integer,
    score2          integer,
    status1         text,
    status2         text,
    section         text,
    faceit_match_id text,                                    -- from links.faceit, when the page records it
    n_games         integer,
    placeholder     boolean     NOT NULL DEFAULT false,      -- an opponent is TBD/BYE: not a played match
    parsed_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (bracket_id, match2id)
);
CREATE INDEX liquipedia_matches_faceit_idx ON liquipedia_matches (faceit_match_id) WHERE faceit_match_id IS NOT NULL;

-- One row per Liquipedia match: how (or whether) it was tied to a FACEIT match.
--   tier  exact      the page records the FACEIT match id and we hold that match
--         strong     no id, but both teams resolve to known orgs, the time, best-of and series score agree, and the pair is unique
--         ambiguous  several candidates, or partial agreement: NEVER linked automatically; decided by review
--         unmatched  no FACEIT counterpart (with the reason)
--   provisional      the link rests on a Liquipedia team name -> org mapping nobody has reviewed yet
--   decision         the reviewer's word on an ambiguous row: 'confirmed' (faceit_match_id is then the answer) or 'rejected'
CREATE TABLE liquipedia_links (
    lp_objectname   text        PRIMARY KEY REFERENCES liquipedia_matches (objectname) ON DELETE CASCADE,
    faceit_match_id text        REFERENCES matches (match_id),
    tier            text        NOT NULL CHECK (tier IN ('exact', 'strong', 'ambiguous', 'unmatched')),
    basis           text,                                    -- what separated it from the alternatives, or why it is unmatched
    provisional     boolean     NOT NULL DEFAULT false,
    decision        text        CHECK (decision IN ('confirmed', 'rejected')),
    candidates      jsonb       NOT NULL DEFAULT '[]'::jsonb,
    evidence        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    disagreements   jsonb       NOT NULL DEFAULT '[]'::jsonb, -- where the two sources differ about a linked pair
    computed_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (faceit_match_id IS NULL OR tier IN ('exact', 'strong') OR decision = 'confirmed')
);
-- A FACEIT match is tied to at most one Liquipedia match: a match known to both sources is one match.
CREATE UNIQUE INDEX liquipedia_links_faceit_once_idx ON liquipedia_links (faceit_match_id) WHERE faceit_match_id IS NOT NULL;
