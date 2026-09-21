-- FACEIT fills an empty bracket slot with a placeholder faction whose team id
-- and name are both 'bye', and scores the real team 1-0 against it. Those rows
-- were ingested as finished series, so every fact and aggregate credited the
-- real team a win it never played and gave a team called "bye" 24 losses spread
-- across NA and EMEA. It surfaced when the region_consistency check found one
-- team id in both regions.
--
-- A bye is not a match. Mark them skipped, the same state as a cancelled match:
-- the row stays for audit and the views (which admit only 'complete' and
-- 'result_only') no longer see it. The ingest change makes new ones arrive
-- skipped. Idempotent, and reversible with:
--   UPDATE matches SET ingest_state = 'result_only', ingest_error = NULL
--    WHERE ingest_error LIKE 'bye:%' AND finished_at IS NOT NULL;
-- Run `python -m owcsmuse refresh` afterwards.
UPDATE matches
   SET ingest_state = 'skipped',
       ingest_error = 'bye: a bracket slot filled by a placeholder opponent, not a played series',
       updated_at = now()
 WHERE (lower(faction1_team_id) = 'bye' OR lower(faction2_team_id) = 'bye'
        OR lower(faction1_name) = 'bye' OR lower(faction2_name) = 'bye')
   AND ingest_state <> 'skipped';
