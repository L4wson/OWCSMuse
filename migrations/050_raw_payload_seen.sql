-- 050: a FACEIT response identical to the latest stored one is not stored again.
--
-- The nightly ingest re-lists every included championship and stored each listing page whether or not it had changed:
-- 1,503 rows for 45 pages by 2026-11-03, 170 MB of them byte-identical to a later fetch of the same page, 5.4 MB a day,
-- with the project over its 500 MB storage limit. Nothing reads a superseded listing (`reprocess` reads the latest
-- /matches/{id} and /stats; listings are parsed when fetched). From now on RawPayloadStore.store() keeps one row per
-- distinct content: when a FACEIT 200 response equals the latest row for the same endpoint, params and match, that row
-- records the sighting instead. Liquipedia responses are always stored: its hourly request budget counts the rows.
--
-- Adding a column with a constant default is metadata-only from PostgreSQL 11: no table rewrite.

ALTER TABLE raw_payloads ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;          -- latest fetch that returned this content
ALTER TABLE raw_payloads ADD COLUMN IF NOT EXISTS times_seen integer NOT NULL DEFAULT 1;
