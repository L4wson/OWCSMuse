# Open items

What is known to be unfinished, in the order to pick it up. The list started as the Stage 3 closing summary's "left
open" list (2026-10-02). It was re-checked against the code, the golden cases and production on 2026-10-23, and the
numbers below are from that day.

## Production

1. **Supabase: `anon` and `authenticated` grants revoked (owner, 2026-10-23); RLS is still off.** `anon` reaches no
   table, view or sequence. PUBLIC keeps schema USAGE and `EXECUTE` on our 18 functions, as Postgres grants by
   default: the 10 that read tables refuse `anon` on the tables inside, and the 8 others compute only on their
   arguments. Supabase's own default privileges (`FOR ROLE supabase_admin`) still grant `anon` on objects that role
   creates in `public`; none of ours are.
2. **12 Liquipedia player pages are undecided:** class C of `scope/lp_only_identity_report.md`, each with a FACEIT
   namesake who never played for the same org (among them the pages held on 2026-10-01: Ailiseu, Aniyun, Shaq). The
   other 152 of the 164 pages on Liquipedia-only series were decided on 2026-10-23: Spectra and Niann03 to their
   FACEIT players, 150 as Liquipedia-only players. A 2024 NA/EMEA one may later turn up on FACEIT and need merging.
   Still open from `scope/identity_report.md` (2026-10-01): W1ll (held strong proposal) and Massivepoop (no FACEIT
   name matched).
3. **Liquipedia records in no series** (2, 2026-10-23, from 18): Ataraxia v
   Metaboiz (2024 EMEA Stage 2), whose FACEIT ids are not in the warehouse; and the Dreamhack Dallas show match (Team
   Hydron v Team Danteh). The FACEIT side needs a crawl, not Liquipedia requests.
4. **31 series have no map results from any source** (28 on 2026-10-02): Liquipedia does not cover them or has no
   record.
5. **Stage 5:** Korea and China, results only (`region_sources` is declared; no data loaded). Hero bans would come
   with them: Liquipedia records bans for every region, but none of their leagues' pages is stored.
6. **The nightly ingest starts hours after its cron.** `ingest.yml` is scheduled for 05:35 / 06:35 UTC (22:35
   Pacific), but real runs started between 11:00 and 16:30 UTC over 2026-10-29 to 11-04, and the 2026-10-31 run took
   nine hours (11:06 to 19:59 UTC, failed). Worth understanding on its own: GitHub's schedule lag, a queue, or something
   in the run. It matters for anything timed around the ingest (the VACUUM FULL of 2026-11-05 was run at 00:09 UTC,
   outside every observed run).
7. **Hero bans by role** ("most banned support") refuse: the hero list records no roles. FACEIT's pool tags each hero
   with one (Sombra with two), which could seed a reviewed `role` per hero.

## Tests

8. **Two task-3 fixes have only a DB test, no golden case:** an alias following its team into an org, and the
    "team" fallback in `resolve()` ("team twisted minds"). The golden warehouse has no alias at a merged team and no
    "Team X" that resolves only without the word. A real case is worth more than the synthetic one (as G33 now
    backs the synthetic by_match case).
9. **Golden cases `proposed`, not asserted:** G27 (Twisted Minds v Geekay at map grain, Stage 2
    enrichment), G28 (a player on the enriched match still has no player stats from it), G61 (a Korean team's
    record at an international event). Each waits on the owner's review.
10. **The golden warehouse leaves out Toronto Defiant v Avidity and v Shikigami** (2024 NA Stage 3/4). Both are
    FACEIT teams with no series there. Capturing a series of each would let both records in.
11. **No guard against a decision stranded on a merged branch** (how Astro's display name was lost): a git-level CI
    step.

## Implicit state machines (structure, not defects)

Found in a survey of the code on 2026-11-08. Each works today. These are notes on how the state is held, not bugs to
fix, and are left as they are unless one of them starts causing a real problem. (`matches.ingest_state`, the
largest, is now drawn in [schema-and-migrations.md](schema-and-migrations.md) with `has_result()` as its one
"has a result" definition.)

13. **Crawl frontier: `crawl_players.crawled_at` and `last_error` together.** The frontier is `crawled_at` null with no
    error. Done is `crawled_at` set. A 404 or other 4xx marks the player done with an error, so they are never
    retried. Retries exhausted leaves `crawled_at` null with an error, so they wait in the frontier. Which pair means
    what lives only in `Crawler._mark_player`'s `crawled=` flag.
14. **Crawl runs and generations: a null `finished_at`** means either "still running" or "died partway"
    (`crawl_runs`, `crawl_generations`). Nothing tells the two apart afterwards.
15. **Liquipedia link review: `liquipedia_links.tier` and `decision` together.** Whether a link counts as settled is
    worked out inline in `liquipedia/reconcile.py` (around lines 211 and 314). The `series` view repeats its own reading
    (`NOT provisional AND decision <> 'rejected'`).
16. **Answer status has two vocabularies.** The pipeline says `ok`, `clarify` or `cannot_answer`, as a bare `str`
    (`nlq/pipeline.py`, `Answer.status`). The query log says `ok`, `clarify`, `refusal` or `error`, translated
    through `querylog._STATUS`. The web app (`Result.jsx`) and the CLI compare against string literals.
17. **Liquipedia run outcome** (`liquipedia/runner.py`, `RunResult.outcome`): four outcomes (`complete`, `budget`,
    `rate_limited`, `failed`), documented in the module docstring and held as a bare `str`.

## Done

- ~~**Names swallowed filter and quantifier words**~~ ("which dallas fuel na", "highest kd of any player" read as
  Anyones Legend, "best kd among players" refused). Fixed 2026-11-05: one closed word list and one name extractor,
  filters read wherever they stand, and every partial match said in `read_as` ([answers.md](answers.md#names-in-a-question)).

- ~~**Team Risk is undecided**~~ (97ef2653 mapped to qadsiah for all time). Decided 2026-10-23: its own org from
  2026 Stage 3; qadsiah's era ends there.
- ~~**The KAFE and NTMR (2026) windows have no end.**~~ Bounded to 2026 Stage 3 (to 2026-11-03), 2026-10-23.

- ~~**CI jobs fail on image pulls**~~ (`toomanyrequests: Data limit exceeded`). Fixed by #29 (2026-10-23): CI pulls
  from a GHCR mirror ([deployment.md](deployment.md)).

- ~~**2026 Stage 3 stops after its first weekend.**~~ 12 FACEIT rooms aborted with no result, 3 finished rooms on
  undecided ids. Fixed 2026-10-23: a room with no result is no FACEIT counterpart, and KAFE and NTMR on their recycled
  ids are their own entities from Stage 3 ([liquipedia.md](liquipedia.md#2026-stage-3-faceit-rooms-with-no-result-2026-10-23)).
- ~~**The web app does not show an answer's Liquipedia attribution.**~~ Fixed by #28 (2026-10-23).

- ~~**The nightly `check` failed from #23 to #26 (18/19, `region_consistency`).**~~ SpaceStation Gaming's Liquipedia
  name was in both regions. Fixed by #26 (2026-10-23): a decided cross-region org's `lp:team:` name is excused.

- ~~**`teams decide` does not validate its id**~~ (a truncated `ec69a520-04` was accepted). Done 2026-10-09: it
  refuses a truncated or unknown id and an unknown org.
- ~~**Stage 4:** LAN and international events beyond Dreamhack Dallas.~~ Done 2026-10-09
  ([liquipedia.md](liquipedia.md#stage-4-lan-and-international-events-2026-10-09)).
