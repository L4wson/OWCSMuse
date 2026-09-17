-- History-crawl LIST phase for competitions that FACEIT does not expose through
-- the championship endpoints (the 2025/2026 "OWCS Central" divisions).
--
-- Matches surface only via /players/{id}/history. The crawl seeds from known
-- OWCS players, records every history item it sees, writes match stubs for
-- main-series competitions (feeding the unchanged DETAIL phase) and expands
-- the player frontier from main-series rosters, generation by generation.

ALTER TABLE championships
    ADD COLUMN source          text NOT NULL DEFAULT 'championship_api'
                               CHECK (source IN ('championship_api', 'history')),
    ADD COLUMN organizer_name  text,
    ADD COLUMN first_match_at  timestamptz,
    ADD COLUMN last_match_at   timestamptz,
    ADD COLUMN matches_seen    integer;

ALTER TABLE matches
    ADD COLUMN discovered_via        text NOT NULL DEFAULT 'championship_listing'
                                     CHECK (discovered_via IN ('championship_listing', 'history')),
    ADD COLUMN discovered_generation integer,
    ADD COLUMN discovered_by_player  text;

-- Every player id the crawl knows about. crawled_at IS NULL = frontier.
CREATE TABLE crawl_players (
    player_id             text PRIMARY KEY,
    nickname              text,
    source                text NOT NULL,           -- roster_db | explicit | team_search | history_roster
    discovered_from_match text,
    generation            integer NOT NULL DEFAULT 0,
    added_at              timestamptz NOT NULL DEFAULT now(),
    crawled_at            timestamptz,
    history_items         integer,
    main_series_items     integer,
    requests              integer,
    last_error            text
);
CREATE INDEX crawl_players_frontier_idx ON crawl_players (generation) WHERE crawled_at IS NULL;

CREATE TABLE crawl_runs (
    run_id          serial PRIMARY KEY,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    generations     integer,
    players_crawled integer,
    requests        integer,
    new_matches     integer,
    new_players     integer,
    notes           jsonb
);

-- The convergence curve: what each expansion round added.
CREATE TABLE crawl_generations (
    run_id           integer NOT NULL REFERENCES crawl_runs (run_id),
    generation       integer NOT NULL,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    players_crawled  integer NOT NULL DEFAULT 0,
    requests         integer NOT NULL DEFAULT 0,
    history_items    integer NOT NULL DEFAULT 0,
    new_main_matches integer NOT NULL DEFAULT 0,
    new_players      integer NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, generation)
);

-- Every match seen in any crawled history, main series or not, so competition
-- discovery is inspectable and the classifier has metadata to work from.
CREATE TABLE history_matches (
    match_id              text PRIMARY KEY,
    competition_id        text,
    competition_name      text,
    competition_type      text,
    organizer_id          text,
    region                text,
    status                text,
    started_at            timestamptz,
    finished_at           timestamptz,
    list_results          jsonb,
    teams                 jsonb,          -- [{team_id, name}]
    player_ids            text[],
    main_series           boolean NOT NULL DEFAULT false,
    first_seen_generation integer,
    first_seen_player     text,
    first_seen_at         timestamptz NOT NULL DEFAULT now(),
    seen_count            integer NOT NULL DEFAULT 1
);
CREATE INDEX history_matches_competition_idx ON history_matches (competition_id);
CREATE INDEX history_matches_started_idx ON history_matches (started_at);
