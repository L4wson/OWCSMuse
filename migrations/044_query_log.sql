-- One row per answered question: what was asked, how it was read, and how it
-- turned out. This is the table that says which questions fail and why.
--
-- Nothing about the asker is stored - no IP, no user agent, no session, no
-- cookie. A question is free text someone typed, and it is kept only as text,
-- so a row cannot be tied back to a person. Do not add such a column.
--
-- saved_queries is not this: it holds one row per distinct question (the slug
-- behind a shareable link) and never records how an answer turned out.
--
--   source            'ask' (POST /ask) or 'shared' (GET /query/{slug}, a link re-run)
--   status            ok | clarify | refusal | error. 'refusal' is the
--                     pipeline's cannot_answer; 'error' is an exception the
--                     request then failed with (reason_code = exception class).
--   reason_code       the Unanswerable / clarify code (no_data, unknown_entity,
--                     ambiguous_entity, ...), NULL on ok
--   structured_query  the parse, StructuredQuery.compact(); NULL when the
--                     question parsed to nothing
--   entities          role -> {type, id, name}; on a clarify, role -> {candidates: [...]}
--   row_count         aggregate rows on an ok answer
--   latency_ms        time spent inside the pipeline, not including the log write
--
-- Size: 493 bytes a row with its indexes (measured), so ~0.5 MB per thousand
-- questions. See README "Query log" for the retention rule.

CREATE TABLE query_log (
    id               bigserial PRIMARY KEY,
    asked_at         timestamptz NOT NULL DEFAULT now(),
    source           text NOT NULL CHECK (source IN ('ask', 'shared')),
    question         text NOT NULL,
    parser           text,
    status           text NOT NULL CHECK (status IN ('ok', 'clarify', 'refusal', 'error')),
    reason_code      text,
    structured_query jsonb,
    entities         jsonb,
    row_count        integer,
    latency_ms       integer NOT NULL
);

-- Reports and the retention delete both scan by time.
CREATE INDEX query_log_asked_at_idx ON query_log (asked_at);
