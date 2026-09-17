-- OWCS Muse warehouse: initial schema.
-- Applied by `python -m owcsmuse migrate` (see owcsmuse/db.py). Plain SQL, no ORM.
--
-- Identity rules
--   * players.player_id  = FACEIT player GUID (stable). Nicknames are mutable and
--     tracked in player_nicknames with first/last seen.
--   * teams.team_id      = FACEIT faction_id in /matches/{id}, which is the same
--     value as teams[].team_id in /matches/{id}/stats.
--   * match_rounds       = one row per map ACTUALLY PLAYED (stats rounds[]),
--     never per pick. Picks/vetoes live in match_map_picks.

-- ---------------------------------------------------------------- raw store
CREATE TABLE raw_payloads (
    id              bigserial PRIMARY KEY,
    endpoint        text        NOT NULL,      -- request path, e.g. /matches/{id}/stats
    params          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    http_status     integer     NOT NULL,
    payload         jsonb,                     -- untouched JSON body (NULL if not JSON)
    body_text       text,                      -- non-JSON body fallback
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    match_id        text,                      -- convenience filters for reprocessing
    championship_id text
);
CREATE INDEX raw_payloads_endpoint_fetched_idx ON raw_payloads (endpoint, fetched_at DESC);
CREATE INDEX raw_payloads_match_idx ON raw_payloads (match_id) WHERE match_id IS NOT NULL;
CREATE INDEX raw_payloads_championship_idx ON raw_payloads (championship_id) WHERE championship_id IS NOT NULL;

-- ---------------------------------------------------------------- reference
CREATE TABLE organizers (
    organizer_id text PRIMARY KEY,
    name         text,
    faceit_url   text,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE championships (
    championship_id    text PRIMARY KEY,
    organizer_id       text REFERENCES organizers (organizer_id),
    name               text NOT NULL,
    game_id            text,
    region             text,            -- as reported by FACEIT (frequently 'GLOBAL')
    derived_region     text,            -- parsed from the name: NA, EMEA, ...
    status             text,            -- finished | cancelled | ongoing | ...
    type               text,            -- swiss | doubleElimination | roundRobin | ...
    championship_start timestamptz,
    subscription_start timestamptz,
    subscription_end   timestamptz,
    total_rounds       integer,
    total_groups       integer,
    slots              integer,
    faceit_url         text,
    include            boolean NOT NULL DEFAULT false,  -- confirmed in the manifest
    list_truncated     boolean NOT NULL DEFAULT false,  -- hit FACEIT's 600-item listing cap
    list_completed_at  timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX championships_include_idx ON championships (include);

CREATE TABLE teams (
    team_id       text PRIMARY KEY,
    name          text,             -- most recently seen name
    avatar        text,
    first_seen_at timestamptz,
    last_seen_at  timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE team_names (
    team_id       text NOT NULL REFERENCES teams (team_id),
    name          text NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    PRIMARY KEY (team_id, name)
);

CREATE TABLE players (
    player_id        text PRIMARY KEY,   -- FACEIT GUID: the stable identity
    nickname         text NOT NULL,      -- most recently seen FACEIT nickname
    game_player_id   text,               -- Battle.net account id as reported by FACEIT
    game_player_name text,               -- in-game name at last sighting
    avatar           text,
    first_seen_at    timestamptz,
    last_seen_at     timestamptz,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE player_nicknames (
    player_id     text NOT NULL REFERENCES players (player_id),
    nickname      text NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    PRIMARY KEY (player_id, nickname)
);
CREATE INDEX player_nicknames_nickname_idx ON player_nicknames (lower(nickname));

-- ---------------------------------------------------------------- matches
CREATE TABLE matches (
    match_id           text PRIMARY KEY,
    championship_id    text REFERENCES championships (championship_id),
    competition_name   text,
    game_id            text,
    region             text,
    best_of            integer,
    status             text,             -- FINISHED | CANCELLED | SCHEDULED | ONGOING ...
    round              integer,
    "group"            integer,
    scheduled_at       timestamptz,
    configured_at      timestamptz,
    started_at         timestamptz,
    finished_at        timestamptz,
    faceit_url         text,

    faction1_team_id   text REFERENCES teams (team_id),
    faction2_team_id   text REFERENCES teams (team_id),
    faction1_name      text,             -- team name at match time
    faction2_name      text,

    -- Series result. Written provisionally by LIST, then always overwritten by
    -- DETAIL (/matches/{id}); LIST results can reflect only the first map.
    winner_faction     text CHECK (winner_faction IN ('faction1', 'faction2')),
    winner_team_id     text REFERENCES teams (team_id),
    faction1_score     integer,
    faction2_score     integer,
    result_source      text NOT NULL DEFAULT 'list' CHECK (result_source IN ('list', 'detail')),
    -- audit trail of what LIST said, and whether DETAIL disagreed
    list_winner_faction text,
    list_faction1_score integer,
    list_faction2_score integer,
    result_flipped     boolean NOT NULL DEFAULT false,

    maps_picked        integer,          -- len(voting.map.pick): picks, not maps played
    maps_played        integer,          -- count(match_rounds): the real number of maps

    -- ingest state machine: stub -> detail_fetched -> complete | skipped | failed
    ingest_state       text NOT NULL DEFAULT 'stub'
                       CHECK (ingest_state IN ('stub', 'detail_fetched', 'complete', 'skipped', 'failed')),
    ingest_error       text,
    ingest_attempts    integer NOT NULL DEFAULT 0,
    detail_raw_id      bigint REFERENCES raw_payloads (id),
    stats_raw_id       bigint REFERENCES raw_payloads (id),
    listed_at          timestamptz,
    detail_fetched_at  timestamptz,
    stats_fetched_at   timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX matches_championship_idx ON matches (championship_id);
CREATE INDEX matches_ingest_state_idx ON matches (ingest_state);
CREATE INDEX matches_started_idx ON matches (started_at);

-- Match roster as declared in /matches/{id} (starters + substitutes).
CREATE TABLE match_rosters (
    match_id          text NOT NULL REFERENCES matches (match_id) ON DELETE CASCADE,
    player_id         text NOT NULL REFERENCES players (player_id),
    faction           text NOT NULL CHECK (faction IN ('faction1', 'faction2')),
    team_id           text REFERENCES teams (team_id),
    is_substitute     boolean NOT NULL DEFAULT false,
    nickname_at_match text,
    game_player_name  text,
    PRIMARY KEY (match_id, player_id)
);

-- Map veto/pick sequence from voting.map.pick. NOT the maps played.
CREATE TABLE match_map_picks (
    match_id   text NOT NULL REFERENCES matches (match_id) ON DELETE CASCADE,
    pick_order integer NOT NULL,
    map_guid   text,
    map_name   text,
    PRIMARY KEY (match_id, pick_order)
);

-- One row per map actually played (stats rounds[]).
CREATE TABLE match_rounds (
    match_id        text NOT NULL REFERENCES matches (match_id) ON DELETE CASCADE,
    round_number    integer NOT NULL,      -- stats match_round
    map_guid        text,                  -- round_stats.Map (a GUID on current payloads)
    map_name        text,                  -- resolved via /matches/{id} voting entities
    game_mode       text,                  -- round_stats["OW2 Mode"], read directly
    score_summary   text,                  -- round_stats["Score Summary"], team1 / team2
    winner_team_id  text REFERENCES teams (team_id),
    team1_team_id   text REFERENCES teams (team_id),
    team1_score     integer,
    team2_team_id   text REFERENCES teams (team_id),
    team2_score     integer,
    team_stats      jsonb,                 -- {team_id: team_stats}
    raw_round_stats jsonb,
    PRIMARY KEY (match_id, round_number)
);

-- Per player, per match, per map played. Aggregate over round_number for the
-- per-match scoreboard (see view match_player_totals).
CREATE TABLE match_players (
    match_id            text NOT NULL,
    round_number        integer NOT NULL,
    player_id           text NOT NULL REFERENCES players (player_id),
    team_id             text REFERENCES teams (team_id),
    nickname_at_match   text,
    role                text,
    result              integer,           -- 1 win, 0 loss
    eliminations        integer,
    final_blows         integer,
    deaths              integer,
    assists             integer,
    solo_kills          integer,
    multi_kills         integer,
    environmental_kills integer,
    damage_dealt        numeric,
    healing_done        numeric,
    damage_mitigated    numeric,
    objective_time      numeric,           -- seconds
    time_played         numeric,           -- seconds
    stats               jsonb NOT NULL,    -- every player_stats key, untouched strings
    PRIMARY KEY (match_id, round_number, player_id),
    FOREIGN KEY (match_id, round_number) REFERENCES match_rounds (match_id, round_number) ON DELETE CASCADE
);
CREATE INDEX match_players_player_idx ON match_players (player_id);
CREATE INDEX match_players_team_idx ON match_players (team_id);

CREATE VIEW match_player_totals AS
SELECT
    mp.match_id,
    mp.player_id,
    mp.team_id,
    max(mp.nickname_at_match)  AS nickname_at_match,
    count(*)                   AS maps_played,
    sum(mp.result)             AS maps_won,
    sum(mp.eliminations)       AS eliminations,
    sum(mp.final_blows)        AS final_blows,
    sum(mp.deaths)             AS deaths,
    sum(mp.assists)            AS assists,
    sum(mp.damage_dealt)       AS damage_dealt,
    sum(mp.healing_done)       AS healing_done,
    sum(mp.damage_mitigated)   AS damage_mitigated,
    sum(mp.time_played)        AS time_played
FROM match_players mp
GROUP BY mp.match_id, mp.player_id, mp.team_id;
