-- Response headers were not archived, so rate-limit history could not be
-- reprocessed from raw_payloads. Stored going forward; existing rows stay NULL.
ALTER TABLE raw_payloads ADD COLUMN headers jsonb;
