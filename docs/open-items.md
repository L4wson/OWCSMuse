# Open items

What is known to be unfinished, in the order to pick it up. The list started as the Stage 3 closing summary's "left
open" list (2026-10-02). It was re-checked against the code, the golden cases and production on 2026-10-23, and the
numbers below are from that day.

## Production

1. **"Dallas Fuel record in 2026 NA stage 3" asks which "dallas fuel na".** The same question as "Dallas Fuel record in
   NA stage 3" answers (2-1, 8-3 in maps). With the season ahead of it, the region word is swallowed into the team's
   name, the same class as the earlier name-swallow bugs (a name inside a question matched only as whole words, "per
   10" and an org's own "of" kept out of names: ff5c3dc, ce89c0a). Seen on the live API 2026-10-23. Two more of the
   class (2026-10-25): "highest kd of any player in 2026" answers for Anyones Legend ("any" matched as a team name,
   wrong and with no warning), and "best kd among players in 2026" refuses with "no player or team matches 'among'".
2. **Supabase: `anon` and `authenticated` grants revoked (owner, 2026-10-23); RLS is still off.** `anon` reaches no
   table, view or sequence. PUBLIC keeps schema USAGE and `EXECUTE` on our 18 functions, as Postgres grants by
   default: the 10 that read tables refuse `anon` on the tables inside, and the 8 others compute only on their
   arguments. Supabase's own default privileges (`FOR ROLE supabase_admin`) still grant `anon` on objects that role
   creates in `public`; none of ours are.
3. **12 Liquipedia player pages are undecided:** class C of `scope/lp_only_identity_report.md`, each with a FACEIT
   namesake who never played for the same org (among them the pages held on 2026-10-01: Ailiseu, Aniyun, Shaq). The
   other 152 of the 164 pages on Liquipedia-only series were decided on 2026-10-23: Spectra and Niann03 to their
   FACEIT players, 150 as Liquipedia-only players. A 2024 NA/EMEA one may later turn up on FACEIT and need merging.
   Still open from `scope/identity_report.md` (2026-10-01): W1ll (held strong proposal) and Massivepoop (no FACEIT
   name matched).
4. **Liquipedia records in no series** (2, 2026-10-23, from 18): Ataraxia v
   Metaboiz (2024 EMEA Stage 2), whose FACEIT ids are not in the warehouse; and the Dreamhack Dallas show match (Team
   Hydron v Team Danteh). The FACEIT side needs a crawl, not Liquipedia requests.
5. **31 series have no map results from any source** (28 on 2026-10-02): Liquipedia does not cover them or has no
   record.
6. **Stage 5:** Korea and China, results only (`region_sources` is declared; no data loaded).

## Tests

7. **Two task-3 fixes have only a DB test, no golden case:** an alias following its team into an org, and the
    "team" fallback in `resolve()` ("team twisted minds"). The golden warehouse has no alias at a merged team and no
    "Team X" that resolves only without the word. A real case is worth more than the synthetic one (as G33 now
    backs the synthetic by_match case).
8. **Three golden cases are `proposed`, not asserted:** G27 (Twisted Minds v Geekay at map grain, Stage 2
    enrichment), G28 (a player on the enriched match still has no player stats from it) and G61 (a Korean team's
    record at an international event). Each waits on the owner's review.
9. **The golden warehouse leaves out Toronto Defiant v Avidity and v Shikigami** (2024 NA Stage 3/4). Both are
    FACEIT teams with no series there. Capturing a series of each would let both records in.
10. **No guard against a decision stranded on a merged branch** (how Astro's display name was lost): a git-level CI
    step.

## Done

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
