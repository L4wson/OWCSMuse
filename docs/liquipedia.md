# Liquipedia integration

Liquipedia as a second source, stage by stage: the client, map enrichment, identity without FACEIT, the
source-agnostic series, LAN and international events, partner teams.

## Liquipedia integration

FACEIT is complete for NA and EMEA main series but has no map stats for 76
series, and nothing for Korea, China or the LAN events. Liquipedia, through its
LiquipediaDB API, fills that in as results, map scores and picks/bans - never
player stats. It is being integrated in stages, each reported before the next
starts:

| stage | what | status |
|---|---|---|
| 0 | client, request planner, cache, attribution | done; auth confirmed and the match record's shape seen (see below) |
| 1 | completeness cross-check: FACEIT match ids joined to Liquipedia, 2024-2026 main series and Dallas | done: `liquipedia reconcile` ties every stored record to FACEIT in tiers (413 exact, 13 strong, 19 ambiguous all decided by the owner, 6 unmatched; `scope/liquipedia_reconciliation.md`) |
| 2 | enrich the 76 result-only series with map-level results, source recorded per field | done: 33 of them are exact-linked and now enriched (122 maps); see below |
| 3 | source-agnostic match model and cross-source identity | done (closed 2026-10-02): see **Stage 3: closing summary** below |
| 4 | LAN and international events | done (2026-10-09; 4 of 15 approved requests): EWC 2024, the 2024 and 2025 World Finals, the 2025 Champions Clash and the 2025 and 2026 Midseason Championships as `lp:` championships, with placings, every team decided and loaded (see **Stage 4** below) |
| 5 | Korea and China, results only | not started |

### The client (Stage 0)

```bash
python -m owcsmuse liquipedia status                 # budget used this hour, last 429, what is held; sends nothing
python -m owcsmuse liquipedia plan                   # the Stage 1 plan and its PROJECTED REQUEST COUNT; sends nothing
python -m owcsmuse liquipedia run                    # shows the plan, then stops: a dry run
python -m owcsmuse liquipedia run --execute          # carries it out (needs OWCS_LIQUIPEDIA_ENABLED=1)
python -m owcsmuse liquipedia verify                 # ONE request: confirms the key, shows a match record's shape
```

- **Key and opt-in.** `LIQUIPEDIA_API_KEY` in `.env` (see `.env.example`). Nothing is
  ever sent unless `OWCS_LIQUIPEDIA_ENABLED=1` is also set in the process
  environment: the key alone is not consent to spend the allowance. The key travels
  only in the `Authorization` header and is never stored or logged.
- **Budget: 60 requests an hour**, counted from `raw_payloads` itself (rows with
  `source = 'liquipedia'`, failures and timeouts included, cache hits not), so
  restarting a process cannot reset it. When it is spent a run stops as `budget`, not
  as a failure, and rerunning later resumes where it left off.
- **The planner** drops values already held, ORs the rest into as few conditions as a
  URL allows, pages each batch at `OWCS_LIQUIPEDIA_PAGE_LIMIT` rows, and prints the
  projected request count and what the remaining budget allows *before* any run.
- **Never re-request what is held.** Every response is stored in `raw_payloads` with
  its headers (`endpoint = 'liquipedia:<endpoint>'`), an identical request is answered
  from there, and the `liquipedia_coverage` ledger records which pages have been
  fetched in full so that changing the set a run wants does not repeat old requests.
  A stored answer that carried an error is never reused as data.
- **A 429 stops everything.** The run ends on that request with no retry and no
  backoff, the 429 is stored with its headers, and nothing more is sent until its
  `Retry-After` (else one hour) has passed. Any other failure also stops the run; there
  is no automatic retry anywhere, because a retry spends budget on a request that just
  failed.
- **Attribution (CC-BY-SA 3.0).** Every Liquipedia-sourced value carries the URL of the
  page it came from: `Sourced` cannot be built without one, `liquipedia_coverage` has
  a checked `page_url` column, and an answer that used Liquipedia values carries
  `Answer.attribution` (source, licence, the page URLs), which the CLI prints and the
  API returns. Answers that used none carry `null`.
- **The key is never kept.** Liquipedia's own 403 quotes the key back (`API key "..." is
  not valid`), so anything that came off the wire is scrubbed of the key before it is
  stored, raised or logged.
- **API only.** Liquipedia's terms forbid automated access to rendered pages, so
  nothing fetches or parses HTML.

### What a match record looks like (seen in the verification request)

`GET /match` returns `{"result": [...]}`; there are no rate-limit headers, so the budget is our own count. A record
is about 6 KB of JSON, with structured fields already decoded (not JSON-in-a-string):

- **Where it is:** `pagename` is the page the match sits on (`.../Korea/Regular_Season`), `parent` the stage above
  it (`.../Korea`). The plan filters on `pagename`, and a value's attribution URL is built from it.
- **The match:** `match2id`, `match2bracketid`, `date` (UTC), `winner` (`"1"`/`"2"`), `bestof`, `type` (Online/Offline),
  `finished`, and `match2opponents` (team `name`, `score`, `status`, `teamtemplate`, and `match2players` with page-style
  names such as `HYEON_(Kim_Seong-hyeon)`).
- **Maps:** `match2games[]` has `map`, `mode`, `scores`, `winner`, `opponents[]` and, in `extradata`, the hero bans
  (`team1ban1`, `team2ban1`, `banstart`): map-level results without player stats, as Stage 2 needs.
- **Not yet seen:** where the FACEIT match id sits. The five sample rows were Korea and China, which are not on FACEIT;
  the first NA/EMEA rows in the Stage 1 fetch will show it (candidates: `links`, `extradata`).

### Stage 2: map-level enrichment of result_only series

`python -m owcsmuse liquipedia enrich [--plan]` reads what Stage 1 already linked (`liquipedia_links`, tier
`exact`) and, for every one whose FACEIT series is `result_only`, inserts `match_rounds` rows from Liquipedia's
`match2games` - map, mode, per-map score, winner. `--plan` classifies without writing and reports whether a gap
would need a new request (none does here: everything is already in `raw_payloads` from Stage 1). Currently 33 of
the 76 result_only series in scope are exact-linked and enriched this way (122 maps); the other 43 sit on a page
Liquipedia does not cover, or Liquipedia has no matching record.

Source is recorded per field, never merged silently:

- `match_rounds.source` (`faceit` | `liquipedia`). A Liquipedia round is only ever inserted where FACEIT has none,
  so there is never a same-round conflict to arbitrate. **The Stage 2 rule that FACEIT won for map stats by
  construction was inverted on 2026-10-02** (migration `034_map_winner_precedence.sql`, see **Stage 3: the
  source-agnostic series**): FACEIT fabricates map rows when a sweep closes a series early and counts drawn maps as
  wins, so Liquipedia is now the source of record for a series' result, best-of and map count wherever a linked
  record exists, and a FACEIT map row beyond Liquipedia's game count is a phantom in no fact view. Player stats
  remain FACEIT-only, as before.
- `matches.date_source` (`faceit` | `liquipedia`) and `matches.liquipedia_played_at`. On a `result_only` series
  FACEIT's own timestamp is when the result was entered, not when it was played - Stage 1's alignment numbers put
  some of these 70+ hours off - so Liquipedia's scheduled time wins there, read through `fact_team_maps` /
  `fact_team_matches`'s `coalesce(liquipedia_played_at, match_time(...))`, without touching FACEIT's own
  `started_at` / `finished_at` / `configured_at` columns.
- Push-mode maps are normalised to the same win/loss indicator (1/0) FACEIT's own `round_stats` already uses for
  that mode (it never carries the push distance), rather than storing Liquipedia's literal distance score
  alongside FACEIT's indicator scores in the same integer column.
- **A parenthetical ending in "player" is a disambiguator, not a real name.** `Haven_(American_player)` is the handle
  Haven; read as a real name, "American player" resolved to five players. `Goose_(Matthew_Gisi)` keeps its real name.
- **A map slot Liquipedia marks not played is not a game.** A series decided early still lists its remaining slots
  (`status: notplayed`, `resulttype: np`, no scores, no winner): 143 across 81 2024 records. Until 2026-10-02 the
  parser counted them, inflating `n_games` (which hides a FACEIT phantom beyond the real count) and readying them to
  be enriched as 0-0 draws nobody played; none had been stored. A real draw (`resulttype: draw`, its scores) stays.

Never touched: `match_players`, and therefore `fact_player_maps` and every player aggregate - Liquipedia carries
no player stats, so none is invented. `python -m owcsmuse check` asserts this directly
(`liquipedia_map_isolation`): no `match_players` row may join to a `source = 'liquipedia'` round.

**Attribution.** `Answer.attribution` (CLI and API, see above) names the Liquipedia page of every value an answer
presented, by the grain it presented them at (`answer_attribution` in `liquipedia/attribution.py`):

- a series-grain answer (a record, a head-to-head, a series leaderboard, a versus answer's missing series) presents
  a linked series' score, result and best-of, which are Liquipedia's since migration 034, so a linked series always
  owes its page (the `series` view's `*_source` columns, and the page it read);
- a map-grain answer owes the page for a Liquipedia map, a Liquipedia date, or a FACEIT phantom map Liquipedia's
  game count removed;
- a team history owes it for a stint dated by Liquipedia.

It covers every match behind the answer (`answer_matches` in `nlq/evidence.py`): every ranked row, every page of
evidence, with or without evidence asked for. If it cannot be computed the answer says so in a note rather than
shipping uncredited. An answer built entirely from FACEIT's own data carries `attribution: null`. Until 2026-10-08
only the map-grain rule existed, read from the one evidence page shown: 397 of 445 linked series on production
presented Liquipedia's score with no credit, and no answer asked without evidence carried any (golden G48-G50, and
`test_attribution_does_not_depend_on_evidence_being_asked_for`).

### Stage 3: identity without FACEIT

Players are keyed by FACEIT GUID and teams map to orgs through FACEIT team ids; Korean teams and players have
neither. An **anchor** is "this entity is known in this source by this handle": a FACEIT id is implicitly its own
anchor, a Liquipedia player page or team name is a row in `entity_anchors` (migration `027_entity_anchors.sql`).
One entity may carry anchors in both sources; a Liquipedia-born entity carries one and gets an id of its own
(`lp:player:<page>`) in the same `players` table, so everything keyed on ids keeps working and it shows as itself.

Liquipedia's line-ups are stored as a parsed copy (`liquipedia_match_players`: page, handle, real name,
nationality; `liquipedia_matches` gains the team templates), and `lp_player_names` / `lp_team_names` are the
Liquipedia-side name history - every handle and real name a page has carried, every name a template has carried,
with first/last seen. Page-style names parse into both parts (`HYEON_(Kim_Seong-hyeon)` -> handle `HYEON`, real name
`Kim Seong-hyeon`) and both are searchable once the page is anchored; the rename-history rule applies to
Liquipedia-anchored entities exactly as to FACEIT ones.

Anchors arrive only through review:

```bash
python -m owcsmuse identity propose          # scope/identity_report.md from the linked series; applies nothing
python -m owcsmuse identity accept           # the strong proposals in bulk
python -m owcsmuse identity decide <page> --player <guid>     # or --new for a Liquipedia-born player
python -m owcsmuse identity reject <page> <guid> --reason "..."
python -m owcsmuse identity load             # scope/player_identity_decisions.json + the team map -> entity_anchors
python -m owcsmuse refresh --view entity_names
```

The only evidence proposed is match-level: the same handle on the same side of the same linked series (an exact or
strong, non-provisional link), which both sources name independently. One page to one GUID is `strong`; a page
matching several GUIDs, or a GUID matched by several pages, needs a person; a handle that matches no FACEIT name is
listed with what FACEIT named on that side, so a reviewer can see "Sugarfree / sug2rfree" and decide - the code
never does. Roster overlap across different series is not evidence of anything. Team-side anchors come from the
Stage 1 team map (`scope/liquipedia_team_map.json`), already reviewed.

A Liquipedia team name resolves **at the series' own time**. An entry in the team map may carry `valid_from` /
`valid_to`, or `eras` (a list of `{entity_type, entity_id, valid_from, valid_to}`) when different team ids carried
the name over time; outside every era the name is undecided at that time, never the nearest one. A name decided to a
team id keys as that id's org inside the id's window and as the id itself outside it, exactly as the fact views key
it, so "Extinction" on a 2026 page and the FACEIT team id that was Extinction in 2026 agree without a link decision.
Anchors carry the same windows (migration `029_anchor_windows.sql`), and `series` and `check` resolve against them.

### Stage 3: the source-agnostic series

A match may come from FACEIT, from Liquipedia, or from both, and is one match either way. `series` (migration
`028_series.sql`) is the one row per match that the team-grain facts (`fact_team_matches`, `fact_team_maps`) now
read, with per-field provenance: `played_at_source`, `best_of_source`, `result_source`, `maps_source`, and
`sources` (`{faceit}`, `{faceit, liquipedia}` or `{liquipedia}`). It is a plain view over `matches`,
`liquipedia_matches` and the reviewed links, so it is always current. `series_id` is `faceit:<match_id>` or
`lp:<objectname>`; `match_id` keeps the FACEIT id where there is one, so every FACEIT-keyed table still joins, and a
Liquipedia-only series is `lp:...` throughout. Evidence rows carry `sources` and a source link that is the FACEIT
room or the Liquipedia page, and an answer that used a Liquipedia-only series carries the page in its attribution.

- A reviewed link (exact or strong, not provisional, not rejected) merges a Liquipedia record into the FACEIT series
  it names. **An exact id whose records disagree on teams, score, winner, best-of, competition or finished state is
  now ambiguous, never linked** - a wrong id looks exactly like that, and a wrong link silently gives one team
  another team's result. It carries the id as its one candidate and waits for `liquipedia links decide`; a date gap
  alone (FACEIT's `result_only` times are entry times) still annotates without downgrading.
- A Liquipedia record linked to nothing is a series of its own only when **both** its teams resolve through a decided
  anchor: a team anchored to a FACEIT team id plays as that id, a team anchored to an org plays as its
  Liquipedia-born team id (`lp:team:<name>`, mapped to the org by `identity load`). An undecided team keeps the record
  out of every answer; `check` counts those (`liquipedia_unresolved_not_in_series`).
- A Liquipedia-only series has maps too (migration `041_liquipedia_only_maps.sql`): its played games are stored in
  `liquipedia_rounds` and read by `fact_team_maps` and `agg_map_modes` beside FACEIT's `match_rounds`, which a
  foreign key keeps FACEIT-only. No player row exists for those maps.
- **A tied map is nobody's win** (migration `030_draws.sql`). FACEIT counts a drawn map as a win for the series
  winner (4-0 in a best-of-5 with four maps played, one of them 3-3) and stored Dreamhack Dallas as best-of-1 with
  3-1 scores. A map is drawn when its scores are equal or no winner is recorded, a draw is excluded from map wins in
  every fact view, and the series score a series presents is corrected from its map results when FACEIT's counted a
  draw as a win (`score_source = 'maps'`; FACEIT's stored columns are untouched).
- **The map winner is derived from the scores; `winner_team_id` is advisory** (migration
  `034_map_winner_precedence.sql`). 1-3e78e269 map 5 (Suravasa, Flashpoint) is scored 0-3 for Twisted Minds and
  credits Al qadsiah as the winner; the map was really played, so nothing looked wrong, and every map record,
  map/mode win rate and head-to-head that read `winner_team_id` attributed it to the wrong team. `map_winner()`
  gives the higher score's team, nobody for equal scores (a tied map has no winner), and the stored winner only
  when a score is missing. Every fact view, `series_score` and `agg_map_modes` read it; `check`
  (`map_winner_consistency`) lists each stored winner that contradicts its scores and fails if a fact row follows one.
- **Liquipedia is the source of record for a linked series' result and best-of; FACEIT only where Liquipedia has
  nothing** (034, inverting Stage 2's rule). FACEIT keeps a fixed number of map slots per format and, when a sweep
  closes a series early, logs a default win for the winner on the next map in the rotation (the 2024 Stage 1 grand
  finals, see **Phantom maps** below: a real 4-0 stored as 5-0 and a real 4-1 stored as 5-1), and it counts a drawn
  map as a win. Where a linked
  record orients to the FACEIT factions (decided anchors, then names, then an unlevel score, then the winner), the
  series presents Liquipedia's score, winner and best-of (`result_source`, `score_source`, `best_of_source` =
  `liquipedia`). A FACEIT map row beyond Liquipedia's game count for a linked series is a phantom (`phantom_maps`):
  out of map records, series scores, map/mode win rates and player aggregates alike, and `check`
  (`phantom_map_isolation`) counts the player rows that rode on one. Player stats stay FACEIT-only. The extent
  report is `python -m owcsmuse liquipedia phantoms` (below).
- **Best-of is derived only from real, played map wins** (034, scoping back 032's rule, which derived from any
  score and produced best-of-9 from phantom-inflated sweeps). With phantoms excluded, a series with four map wins
  is a best-of-7 whatever FACEIT stored (Al Qadsiah 1-4 Twisted Minds, stored bo5; the link is confirmed in
  `scope/liquipedia_link_decisions.json`), three a best-of-5, and never fewer than the maps played; the cap is the
  formats OWCS uses (bo1, bo3, bo5, bo7), and a derivation past bo7 is `implausible` and presented as unknown
  rather than invented. A stored best-of of 1 is junk (Dreamhack Dallas), not a value to correct from; a stored
  value is used only when no maps were recorded and it is a real format, else the best-of is `unknown`.
  `best_of_source` is `liquipedia` | `faceit` | `derived from map wins` | `implausible` | `unknown`; `check`
  (`score_plausibility`) counts each kind and lists the corrections (`best_of_corrections`).
- A link decision may be keyed `faceit:<match id>` (the report shows FACEIT ids, not objectnames); it settles the one
  record naming that id. The two drawn-map pairs are confirmed that way in `scope/liquipedia_link_decisions.json`.
- `check` gains `series_integrity`: no FACEIT id or Liquipedia record in two series, the series count reconciles
  against its sources, and a linked pair whose Liquipedia teams are decided names the same identities on both sides -
  a link that stops agreeing after an identity decision fails here rather than staying.

### Stage 3: in-game name history and an owner's display name

The in-game name (`players.game_player_name`) is the name answers display, and it changes: three rename gaps bit
before migration `035_game_names_display.sql`. `player_game_names` now keeps every value a GUID has carried with
its first and last sighting, the same shape as `player_nicknames`; the collector versions it on every change, and
`python tools/backfill_game_names.py` fills the earlier values out of the stored `/matches/{id}` payloads
(`raw_payloads`, no request). `entity_names` makes each historical value searchable (`historical_game_name`).
`players.display_name` is an owner's override set by `identity load` from a player identity decision's `display`
(`identity decide <page> --player <guid> --display "ZZZ"`, or `--nickname <FACEIT name>` to find the GUID by a
name that names exactly one player): shown everywhere and, since migration `037_display_name_search.sql`, searchable
too (`display_name` rows in `entity_names`), every nickname and in-game name still searchable. Until 037 "ZZZ record"
found nobody while "zss" worked, and "Astro" resolved only as a prefix of Astronexz. `check` (display_names_searchable)
proves every entity's shown name is one of its own search names (golden G51). Decided so far: ZZZ (FACEIT z_ow, in-game zss) and Astro (FACEIT Astronexz). Astro's decision was
committed to `stage3-identity` three minutes after PR #6 merged (363a35e) and so never reached main; restored from that
commit on 2026-10-02. `decisions_loaded` compares the files on main with production in both directions, display names
included, but a decision stranded on an unmerged branch is in neither and no file-to-table comparison can see it.

**SpaceStation Gaming is one organisation** across its 2024 EMEA team (`a359db61`, OWCS 2024 EMEA Stage 1 and
Dreamhack Dallas) and its NA partner team from 2025 (`6ddc0431`): decided by the owner on 2026-10-02, reversing
the 2026-09-19 unmerge. Each team id is mapped over its own era; the region check carries the org as an
owner-decided exception (`cross_region_ok` in every window's evidence, listed under
`decided_cross_region_orgs`), since the rule it enforces exists to catch merges nobody decided.

### Stage 3: capability, not just coverage

A source may carry a slice without carrying what a question needs from it. `region_sources` (migration
`031_capabilities.sql`) declares per region which sources cover it and whether any of them records player stats
(`korea`: `{liquipedia}`, no); `source_capabilities` derives per included championship, from `series` provenance,
whether it has series results, map results and player stats, and which sources it came from. The query layer asks
what a question needs (`player_stats`, `maps` or `series`) and checks the slice it draws on: a results-only slice
refuses a player-stat question with reason code `results_only` and the alternatives a results-only slice can answer;
a mixed slice answers and names the results-only part in a note and the `results_only_source` limitation. A
Korean team's record is answerable the moment its Liquipedia results are loaded; a Korean player leaderboard never
is, and says so by construction rather than by returning nobody.

### Phantom maps: FACEIT map rows for maps never played

FACEIT keeps a fixed number of map slots per series format and, when a series is decided early, logs a default
win for the winner on the next map in the rotation. **Where the phantom lives, precisely:** only in the `/matches`
payload's `detailed_results` (one entry per map slot) and therefore in FACEIT's stored series score. The `/stats`
payload, which is what `match_rounds` and every player row are built from, carries only the maps actually played,
so **no fabricated map has ever entered the warehouse** as of the 2024 fetch. The two known cases, both confirmed in
`scope/liquipedia_link_decisions.json` on 2026-10-02:

| grand final | FACEIT score | phantom entry in `detailed_results` | `match_rounds` | Liquipedia |
|---|---|---|---|---|
| 2024 NA Stage 1, Toronto Defiant v Timeless (1-70cff415) | 5-0 | 5th: Dorado (the next pick), 1-0 | 4 maps, 10 player rows each | 4-0, the same 4 maps |
| 2024 EMEA Stage 1, Twisted Minds v ENCE (1-c5823143) | 5-1 | 6th: Ilios (the next pick), 0-0, credited to the winner | 5 maps, 10 player rows each | 4-1, the same 5 maps |

So what the phantom inflates is the **series score** (and the best-of a score implies), which the linked Liquipedia
record corrects (`score_source = liquipedia`). `phantom_maps` and `check` (`phantom_map_isolation`) guard the other
shape, a FACEIT map *row* beyond Liquipedia's game count, which would carry the phantom into map records, map/mode
win rates and player aggregates; it holds 0 rows today and stands as a guard should a payload ever carry one.
`python -m owcsmuse liquipedia phantoms` (sends nothing)
writes `scope/phantom_maps.md` from stored data: every record carrying a FACEIT id where FACEIT's map count or
series score exceeds Liquipedia's, with both values and the map Liquipedia lacks; every FACEIT map row with a
placeholder shape (a win with no player rows while the match has them elsewhere, a score its mode cannot produce, no
map name); and whether those cluster on sweeps and last maps as the mechanism predicts. An exact FACEIT id whose
score a phantom inflated lands in the ambiguous tier (the records disagree on the score), so the report includes
those rather than only confirmed links. The precedence change this implies (Liquipedia as the source of record for
results and maps wherever a linked record exists) waits on that report.

### Stage 3: closing summary (2026-10-02)

**What it established.** A match is one series whichever source holds it (`series`, migration 028), with
per-field provenance; Liquipedia is the source of record for a linked series' result, best-of and map count, and
FACEIT the only source of player stats (034). Players, teams and orgs carry identity across sources through reviewed
anchors (`entity_anchors`): 363 player identities, 27 Liquipedia team names, and team-to-org windows dated per era
(026, 029). Every reviewed decision in `scope/` is provably loaded (`decisions_loaded`), every check counts its
failures exactly (no LIMIT feeds a count), and every Liquipedia team name resolves to the entity that holds its series
(`lp_name_resolution`). The 2024 season, Dreamhack Dallas included, is linked to Liquipedia; Dallas carries
Liquipedia's maps and schedule. The golden suite covers Liquipedia-linked results (G32-G34).

**Conventions it produced** are in [conventions.md](conventions.md), with the others this project learned the
same way. **What it left open** is tracked in [open-items.md](open-items.md).

### 2026 Stage 3: FACEIT rooms with no result (2026-10-23)

From 2026 Stage 3's second weekend, FACEIT has nothing about the series it was meant to run. Of the 30 rooms in the S10
NA and EMEA regular seasons (2026-10-23), 12 were configured and aborted about 8 minutes later (`ABORTED`, once
`CANCELLED`) with empty `results` and `detailed_results`, and none was replaced: both listings hold exactly the rooms
stored. Week 1's results were entered by hand a week late (2026-10-17, 16:28-16:34Z), and the remaining rooms were
aborted minutes after. Liquipedia records every series, naming the room FACEIT opened for it.

- **A room with no result is no FACEIT counterpart.** A Liquipedia record whose FACEIT id is a stored room that ended
  `ABORTED`, `CANCELLED` or `PAUSED` with no winner and no score, opened for the same two teams the record resolves to,
  is linked `unmatched` with `no_faceit_counterpart` (`faceit_room`: `aborted_no_result` / `cancelled_no_result` /
  `paused_no_result`), so `series`
  makes it a Liquipedia-only series. Before, it was "a FACEIT id we do not hold" and in no answer. A room opened for
  other teams, or a record with an undecided team, stays reported, never stands alone. If FACEIT later enters a result,
  the room's status change re-queues it, and the next reconcile links it like any other: still one series.
- **It found two more:** the 2026 Stage 1 playoff records Geekay Esports v Virtus.pro and Spacestation Gaming v Team
  Liquid (2026-04-12), whose rooms FACEIT cancelled with no result.
- **Two recycled ids play Stage 3** (owner, 2026-10-23). KAFE is FACEIT team `0464a373` (UNC inc, Rad, Sakura, LuneX):
  from Stage 3 it is its own org, `kafe`, and Liquipedia's "The Kafe" routes to it, inheriting neither that id's history
  nor `a35f8d47`'s. Stage 3's NTMR is `d20d1868` (team_chiime, Dreamland, Supernova, Team Z): its own org, `ntmr-2026`,
  not the NTMR org, and Liquipedia's "NTMR" routes to it from Stage 3. Both windows start at Stage 3 (2026-10-09) and
  end the LuneX and Team Z windows there, which had run open-ended and credited Stage 3 results to LuneX and Team Z.
  Both end with the stage (owner: regular season October 10-25, regional playoffs October 30 - November 1): to
  2026-11-03, clear of November 1 in every timezone.
- **PAUSED counts too** (2026-10-25). FACEIT moves Stage 3 rooms between `ABORTED`, `PAUSED` and `CANCELLED` (two rooms
  seen `ABORTED` on 10-23 were `PAUSED` on 10-25), and week 3's rooms sat `PAUSED`: none holds a result until it is
  `FINISHED`.
- **An undated bracket slot is not a match yet** (2026-10-25). The playoff pages' empty slots carry Liquipedia's "no
  date", `0000-01-01` (epoch -62167219200, year 0). Read as a date it raised in `parse_row`, and the 10-24 and 10-25
  nightly runs stopped at `liquipedia reconcile`: nothing fetched was stored, Saturday's week 3 results among it. Such
  a slot (a placeholder, or unfinished) now parses to nothing until Liquipedia dates it; the page is re-requested while
  any slot is unfinished, so it is read then. A finished record between two real teams with no date still stops the
  run, by name.
- **Team Risk** (owner, 2026-10-23) is its own org on FACEIT team `97ef2653`, whose `qadsiah` era (Al Qadsiah) ends at
  Stage 3: new players, no longer sponsored by Al Qadsiah. The linked 1234 0-3 Team Risk counts for Team Risk.
- **The playoffs are Liquipedia-only events.** The S8/S9 regional playoffs are FACEIT "Central - Playoffs"
  championships mapped to the stage page, where Liquipedia keeps the bracket. FACEIT has no S10 playoffs championship,
  so nothing mapped `2026/NA/Stage_3` or `2026/EMEA/Stage_3` and the nightly run would never have fetched the
  playoffs. Both are now `lp:` events (`scope/liquipedia_events.json`, 6 matches each in the subpage probe, raw 4463). The
  nightly fetch requests a page it does not hold, then re-requests it while it has unfinished matches, so the bracket
  is picked up as it is played.

### Stage 4: LAN and international events (2026-10-09)

The events with no FACEIT competition - EWC 2024, the 2024 and 2025 World Finals, the 2025 Champions Clash and the
2025 and 2026 Midseason Championships - come from Liquipedia alone. Dreamhack Dallas stays a FACEIT competition with
Liquipedia linked onto it.

```bash
python -m owcsmuse liquipedia probe-subpages <root page>...    # ONE request: which pages at or under each root hold matches
python -m owcsmuse liquipedia plan                              # the match fetch, now including every event page
python -m owcsmuse liquipedia run --execute --max-requests 15   # a per-run ceiling below the hourly budget
python -m owcsmuse liquipedia placements plan|run|load          # /placement by event root page; load sends nothing
python -m owcsmuse liquipedia events load                       # scope/liquipedia_events.json -> lp: championships
python -m owcsmuse liquipedia teams decide "<name>" --org <slug> --new-org-name "<display>"   # a Liquipedia-only org
```

- **`lp:` championships** (migration `038_lp_championships.sql`). `scope/liquipedia_events.json` is the reviewed list,
  keyed by the event's root page; its `pages` come only from a probe response, never a guessed path. `events load`
  writes each as `lp:<root page>` with `source = 'liquipedia'` and the usual scope columns, and the reconciler stores
  every record on those pages under it, so a Liquipedia-only series has an included championship like any FACEIT one.
  `decisions_loaded` compares the file with the table.
- **The subpage probe** matches `pagename` OR `parent`: a LAN event's matches sit on subpages (`/Group_Stage`), which an
  exact-pagename probe reports as not found. It found 141 matches on 9 pages; the alternative roots
  `.../2024/Finals`, `Esports_World_Cup/2025` and `/2026` hold none (the Midseason Championships at EWC sit under the
  OWCS path).
- **Placings** (migration `039_placements.sql`): `liquipedia_placements` is the parsed prize pool, team rows only
  (individual awards and team awards with no position are left out), the position kept as a range (`7-8`), each with
  its page for attribution. The `placements` view resolves a name through the same decided anchors as `series`, at the
  team's exit date; an undecided name is shown as Liquipedia names it, marked `identity: undecided`, never merged.
  A page whose team placings sit in more than one prize pool is reported as ambiguous and none of its rows load.
  `check` (`placement_consistency`) holds each event to exactly one winner who also won its last series: a bracket
  reset, a mixed-in LCQ pool or a placing entered early would break it. All six events pass; none has a bracket reset.
- **Questions:** a `placement` intent - "who won the 2025 world finals", "who placed second / 7th at ...", "where did X
  place at ...", "... standings". The winner as people ask it: "who won", "winner", "champion", "who took the title".
  The events as people say them: "worlds" and a bare "finals" (with no stage, region or bracket word: "NA Stage 2
  finals" stays the stage) are the World Finals; "MSC" and "mid-season" the Midseason Championship; "EWC" the
  Esports World Cup; "Champions Clash" is the event, while "clash" alone stays the game mode. A champion with no event
  named ("who was the 2025 champion") is the world champion, the World Finals winner (owner, 2026-10-09), and the
  answer says that is how it read the question. Golden G55-G60 and G67-G81 pin each phrasing. A sentence about a named
  event says "at OWCS 2025 World Finals" rather than "in 2025".
- **No player stats, by declaration.** An `lp:` championship can carry no player stats, loaded or not, so a player-stat
  question about one refuses `results_only` before the season's stat coverage is consulted, and offers the event's
  standings and its series-wins table. Its map results are Liquipedia's game-by-game results (041) and answer at map
  grain like any other: a team v team map record counts them, and refuses only when no source has a series' maps
  ("none of those series has map results from any source"; before 041, 95 pairings refused although every map was
  on Liquipedia, and 15 answered with those series silently left out).
- **Liquipedia-only orgs.** A team with no FACEIT counterpart (T1, Weibo Gaming, ZETA DIVISION, ...) is decided with
  `--new-org-name`; `identity load` creates the org and its `lp:team:` id, and `orgs load` no longer deletes an org that
  only a Liquipedia-born team maps to. `teams decide` refuses a truncated or unknown team id, an unknown org, and a
  `--new-org-name` for an org that already exists.

**Loaded into production 2026-10-09** (rehearsed first on a local copy of production): migrations 038-040,
`orgs load`, `identity load`, `liquipedia events load`, `liquipedia reconcile`, `liquipedia placements load`,
`refresh`; `check` passes all 17. Every team at the six events is decided (`scope/stage4_team_report.md`): Crazy Raccoon
and Team Falcons are one continuous org each, Dallas included (`crazy-raccoon`, `team-falcons`); Team Liquid and Dallas
Fuel are orgs, not bare ids; Toronto Ultra is Toronto Defiant at EWC 2024; Sign Esports is NTMR under a short-lived
name (2025-06-30 to 2025-09-06); Geekay Esports at the events is the NA team in 2025 and the EMEA team in 2026, from
each event's qualifier, under the `international` region bucket (revisit if both ever attend one event); ROC Esports
is the 2024 roster's id through 2024, then a separate China org; 18 teams are Liquipedia-only orgs. 143 series are
Liquipedia-only: the 141 event series and the two 2026 Stage 1 grand finals Stage 3 left unmatched.

Found while loading, and fixed:

- **SQL `fold_name()` now folds as Python's `fold()` does** (migration 040). Anchors are written with one and looked
  up with the other; a Liquipedia name with a dot, apostrophe, hyphen or parenthesis (Virtus.pro, Anyone's Legend,
  Team CC (Chinese orgless team)) never met its anchor, so its Liquipedia-only series reached no answer.
  `tests/test_fold_parity.py` holds the two equal.
- **Head-to-head keys both sides by org** (`org_key` in `fact_team_matches`), like a team record. `agg_head_to_head`
  is keyed by raw team id, so an org on either side (SpaceStation Gaming, Al Qadsiah) matched nothing and answered
  "ok" with an empty row; no series is now no data.
- **A question by a team id an org since absorbed** (`team:<id>`, as in a clarify hint or a shared link) answers as
  that org.
- **Attribution no longer rebuilds the team-map view per ranked row.** `answer_matches` asks only for match ids, and a
  player's evidence reads the map score from its round: a 10-row player leaderboard took 22-40 s, now under a second.
- **Suggestions pair teams and players that met on maps.** The two most active were paired blindly and one pair
  answered no data; the golden suite now asks every suggestion and fails on any that does not answer.

### Partner teams (2026-10-10)

The OWCS partner teams are a **season-scoped group**: partner status is per season and per region and changes year to
year. Membership is Liquipedia's own record, never inferred: a Stage 1 prize-pool row whose `qualifier` is
`Partner Team`, fetched as one `/placement [[qualifier::Partner Team]]` request (the Partner_Teams page itself stores no
structured data). The reviewed groups are `scope/partner_teams.json` (proposals and evidence in
`scope/partner_teams_report.md`), loaded by `python -m owcsmuse groups load` into `team_groups` (migration
`043_team_groups.sql`); `team_group_members` resolves each Liquipedia name through the decided anchors at its own date.
`decisions_loaded` compares the file with the table.

| season | partner teams |
|---|---|
| 2025 | Korea: T1, Team Falcons, Crazy Raccoon, ZETA DIVISION; EMEA: Gen.G Esports, Twisted Minds, Virtus.pro; NA: Team Liquid, Spacestation Gaming |
| 2026 | Korea: the same four; China: All Gamers (Global), JD Gaming, Weibo Gaming; EMEA: Team Peps, Twisted Minds, Virtus.pro; NA: Disguised, Dallas Fuel, Spacestation Gaming, Team Liquid |

Liquipedia tags no partners for China 2025, Japan or the Pacific.

- "which teams are the partner teams" lists the latest season's (saying so), or the season or region named.
- Any team question restricted to them ("which partner team won the most series in 2026") counts a team only in a
  season it was a partner, and the answer names every team it included. "Games" means series.
- A tie at the top of any leaderboard is said as a shared lead ("Dallas Fuel and Twisted Minds share the lead in
  series won with 17"), never as whichever row sorted first.
- Keeping it current: one `/placement [[qualifier::Partner Team]]` request a season, reviewed like any decision.
