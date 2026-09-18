-- Shareable question URLs.
--
-- A slug is a deterministic digest of the question and the parser that read it,
-- so asking the same thing twice gives the same link and the table never grows a
-- second row for it. The answer itself is NOT stored: re-running the question
-- against current data is the point, and a cached aggregate would go stale the
-- moment anything is ingested or refreshed.
--
-- structured_query keeps the parse that was recorded when the slug was created,
-- so a link can be inspected without re-parsing, and a parser change is visible
-- as a difference between this and the live parse.

CREATE TABLE saved_queries (
    slug             text PRIMARY KEY,
    question         text NOT NULL,
    parser           text NOT NULL DEFAULT 'rules',
    structured_query jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    last_asked_at    timestamptz NOT NULL DEFAULT now(),
    times_asked      integer NOT NULL DEFAULT 1
);

CREATE INDEX saved_queries_recent_idx ON saved_queries (last_asked_at DESC);
