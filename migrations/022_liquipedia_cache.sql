-- Liquipedia responses go in raw_payloads beside FACEIT's, with their headers.
-- `source` says whose they are: the hourly request budget counts Liquipedia rows
-- only, and a FACEIT `reprocess` must never see a Liquipedia payload. Every
-- existing row is FACEIT's, which is the default.
ALTER TABLE raw_payloads ADD COLUMN source text NOT NULL DEFAULT 'faceit' CHECK (source IN ('faceit', 'liquipedia'));
CREATE INDEX raw_payloads_source_fetched_idx ON raw_payloads (source, fetched_at DESC);

-- What has already been fetched, by the thing asked for, so that changing the
-- set of pages a run wants never re-requests a page already held: batching is
-- an implementation detail of a request, coverage is the fact.
--
-- One row per value of the field a query was filtered on (a tournament page, say),
-- written only once every page of the batch that carried it came back, so a row
-- here means "all of this value's matches are in raw_payloads", never "some".
--
-- page_url is the Liquipedia page the value comes from, mandatory and checked:
-- Liquipedia's data is CC-BY-SA, and the attribution promised in the API
-- application has to be attachable to everything derived from it.
CREATE TABLE liquipedia_coverage (
    endpoint   text        NOT NULL,                        -- e.g. 'match'
    field      text        NOT NULL,                        -- e.g. 'parent'
    value      text        NOT NULL,                        -- e.g. 'Overwatch_Champions_Series/2026/EMEA/Stage_2'
    page_url   text        NOT NULL CHECK (page_url LIKE 'https://liquipedia.net/%'),
    rows_seen  integer,                                     -- records the response carried for this value, when countable
    raw_ids    bigint[]    NOT NULL,                        -- the raw_payloads rows that hold them
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (endpoint, field, value)
);
