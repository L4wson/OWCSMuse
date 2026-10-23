# Open items

What is known to be unfinished, in the order to pick it up. The list started as the Stage 3 closing summary's "left
open" list (2026-10-02). It was re-checked against the code, the golden cases and production on 2026-10-23, and the
numbers below are from that day.

## Production

1. **2026 Stage 3 stops after its first weekend.** Liquipedia has 14 finished Stage 3 series from 2026-10-10 to
   2026-10-18 (NA 9, EMEA 5) that are in no series. Two causes, found with FACEIT requests on 2026-10-23:
   - **12 FACEIT rooms have no result.** Each was configured, aborted about 8 minutes later (`ABORTED`, or `CANCELLED`
     once) with empty `results`, and never replaced: both S10 listings hold exactly the 15 rooms stored. The series
     were played outside FACEIT, and only Liquipedia has them. The reconciler lists such a record under "a FACEIT id
     we do not hold" and leaves it out of every answer.
   - **3 FINISHED rooms use team ids no decision maps:** KAFE is `0464a373` (the recycled id: UNC inc, Rad, Sakura,
     LuneX) and NTMR is `d20d1868`, so their Liquipedia records are "ambiguous: disagrees on teams".
2. **Supabase: Row Level Security is off on all 33 tables, and `anon` holds SELECT, INSERT, UPDATE, DELETE and
   TRUNCATE on 49 relations.** Nothing here uses the Data API (see [schema-and-migrations.md](schema-and-migrations.md),
   Supabase notes). If the Data API is enabled, anyone with the project URL and its public anon key can change the
   warehouse. Neither is in the repository, but the decision the runbook asks for is still open: revoke the
   `anon`/`authenticated` grants, or disable the Data API.
3. **The web app does not show an answer's Liquipedia attribution.** The API and CLI return `attribution` (licence
   and page URLs). The app links only a Liquipedia-only series' row to its page. A linked series' Liquipedia score,
   an event placing and a Liquipedia map result reach the page with no CC-BY-SA notice and no page link.
4. **CI's Postgres 16 jobs fail on image pulls**, not tests: `public.ecr.aws` answers `429 toomanyrequests: Data limit
   exceeded` when several runs pull at once (four did on 2026-10-23). A re-run usually passes.

## Identity and data

5. **Identities left undecided by the owner** (from `scope/identity_report.md`, 2026-10-01): 4 strong proposals held
   (W1ll, Ailiseu, Aniyun, Niann03: Liquipedia lists them in series whose FACEIT roster lacks the proposed GUID),
   Shaq (two candidate GUIDs) and Massivepoop (no FACEIT name matched).
6. **164 Liquipedia player pages on Liquipedia-only series have no reviewed identity** (1,134 line-up rows), so those
   players are on no side of those series. Most are on the 2025 and 2026 Midseason Championships (51, 45), 2024 NA
   and EMEA Stages 3/4 (47, 40) and EWC 2024 (38). `identity propose` reads only linked series, so it proposes none
   of them.
7. **18 Liquipedia records are in no series:** the 14 Stage 3 records above (item 1); Ataraxia v Metaboiz (2024 EMEA Stage 2),
   whose FACEIT ids are not in the warehouse; the Dreamhack Dallas show match (Team Hydron v Team Danteh); and two
   2026-04-12 Stage 1 records (Geekay Esports v Virtus.pro, Spacestation Gaming v Team Liquid). The FACEIT side needs
   a crawl, not Liquipedia requests.
8. **31 series have no map results from any source** (28 on 2026-10-02): Liquipedia does not cover them or has no
   record.
9. **Stage 5:** Korea and China, results only (`region_sources` is declared; no data loaded).

## Tests

10. **Two task-3 fixes have only a DB test, no golden case:** an alias following its team into an org, and the
    "team" fallback in `resolve()` ("team twisted minds"). The golden warehouse has no alias at a merged team and no
    "Team X" that resolves only without the word. A real case is worth more than the synthetic one (as G33 now
    backs the synthetic by_match case).
11. **Three golden cases are `proposed`, not asserted:** G27 (Twisted Minds v Geekay at map grain, Stage 2
    enrichment), G28 (a player on the enriched match still has no player stats from it) and G61 (a Korean team's
    record at an international event). Each waits on the owner's review.
12. **The golden warehouse leaves out Toronto Defiant v Avidity and v Shikigami** (2024 NA Stage 3/4). Both are
    FACEIT teams with no series there. Capturing a series of each would let both records in.
13. **No guard against a decision stranded on a merged branch** (how Astro's display name was lost): a git-level CI
    step.

## Done

- ~~**The nightly `check` failed from #23 to #26 (18/19, `region_consistency`).**~~ SpaceStation Gaming's Liquipedia
  name was in both regions. Fixed by #26 (2026-10-23): a decided cross-region org's `lp:team:` name is excused.

- ~~**`teams decide` does not validate its id**~~ (a truncated `ec69a520-04` was accepted). Done 2026-10-09: it
  refuses a truncated or unknown id and an unknown org.
- ~~**Stage 4:** LAN and international events beyond Dreamhack Dallas.~~ Done 2026-10-09
  ([liquipedia.md](liquipedia.md#stage-4-lan-and-international-events-2026-10-09)).
