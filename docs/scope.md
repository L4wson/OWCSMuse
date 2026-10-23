# Scope decisions and known limitations

What is in the warehouse, what is deliberately not, and what the data cannot answer.

## Scope

Target set: OWCS North America and OWCS EMEA main competition (regional
stages, their group stages and playoffs) plus international events where NA
and EMEA teams compete (Midseason Championship, World Finals, Champions Clash,
the 2024 Dreamhack Dallas Major). Excluded: open qualifiers, relegation,
Asia / Korea / Japan / Pacific / China / South America / Oceania, cancelled or
test events. Korea has no usable FACEIT data, so nothing Asia-region is
included from FACEIT even where a championship exists. Korea is a declared
region (`korea`, results only) so that its Liquipedia results can land under
it; until they do, a Korean question is refused as results-only or as having
no data, never as out of scope.

Classification is explicit and reviewable, not a regex flag:

- `championships.scope_region` (`na`, `emea`, `international`, `other`),
  `championships.tier` (`main`, `qualifier`, `relegation`, `unknown`) and
  `championships.season`, with `classification_source` (`auto` or `manual`),
  `classification_evidence` (the rules that fired) and `decision_note`.
- `owcsmuse/scope.py` proposes values from a small rule table; every rule
  names itself in the evidence. A known-event table covers OWCS events whose
  FACEIT name lacks "OWCS" (Dreamhack Dallas).
- `scope/decisions.json` holds reviewed corrections keyed by championship id.
  Re-running `discover` or `classify` applies them on top of the classifier,
  so a decision is never silently reclassified. `scope/classification_report.md`
  is the review table.
- The aggregates below read only championships with `include = true`.

What FACEIT holds, as of 2026-09-17:

- **Reachable through the championship endpoints:** the 2024 NA and EMEA
  Stage 1 and Stage 2 group stages and main events, and Dreamhack Dallas 2024
  (21 championships, 166 matches). Excluding the qualifiers also removes every
  championship that hit FACEIT's 600-item listing cap; `check-listings`
  confirms none of the 21 does.
- **Present but not reachable through those endpoints:** the 2025 and 2026 NA
  and EMEA main series runs inside FACEIT League as the "OWCS Central"
  division: `S4/S5/S6 {NA|EMEA} OWCS Central - Regular Season / Playoffs`
  (2025) and `S8/S9/S10 ...` (2026), plus `OWCS Midseason Championship: Last
  Chance Qualifier at EWC` and the S8 relegation matches, all under organizer
  `f0e8a591-08fd-4619-9d59-d97f0571842e` ("FACEIT League - Overwatch"). These
  competition ids return 404 from `/championships/{id}`, `/hubs/{id}` and
  `/leagues/{id}`, are absent from `/organizers/{id}/championships` and from
  every search endpoint, and the organizer exposes no hubs or tournaments.
  Their matches are fully served by `/matches/{id}` and `/matches/{id}/stats`
  (2026 payloads, ~47 stat keys) and are discoverable only through
  `/players/{id}/history`, which reports the competition id and name per
  match. They are ingested through the history crawl below.
- 2024 Stages 3 and 4 exist on FACEIT only as open qualifiers.

### History crawl

`owcsmuse/crawl.py` is a LIST phase for the competitions the championship
endpoints hide. It seeds from the rosters already ingested, reads
`/players/{id}/history`, records every match under a competition that
classifies as in scope, and adds the opposing rosters to the next generation's
frontier. It is resumable and instrumented for completeness: `crawl status`
reports the convergence curve (players crawled, new matches per generation),
the frontier, per-competition coverage and gap flags.

```bash
python -m owcsmuse crawl seed --from-rosters
python -m owcsmuse crawl run --dry-run      # request projection, before spending any
python -m owcsmuse crawl run
python -m owcsmuse crawl status
python -m owcsmuse crawl competitions       # discovered competitions, for the same review gate
```

It converged in two generations: 315 players / 2,273 requests / 232 new
matches, then 99 players / 724 requests / 0 new matches. Discovered
competitions go through `classify` and `scope/decisions.json` exactly like
anything found by `discover`; the crawl marks nothing included by itself.

## Known limitations

Coverage percentages say how much of a stat exists. They do not say why it is
missing, and here the gaps are not random. `owcsmuse/limitations.py` holds these
as data; `python -m owcsmuse limitations` prints them, and `ask` attaches the
ones a question lands in to its answer.

### Offline and LAN days have series results but no map stats

`offline_map_stats` - FACEIT records a result for an offline series without
per-map player stats, so those series land in `result_only`: the winner and
series score are known, the maps are not. 76 of 485 finished series in scope
are `result_only`, and they are not spread evenly - 28 of 94 series in playoff
and LAN competitions have no map stats against 48 of 391 elsewhere, and all 14
Dreamhack Dallas matches are `result_only`. Liquipedia's map results (map, mode, per-map score, winner, never player
stats) now fill 48 of the 76, all 14 Dallas series among them (2026-10-02, each map checked against the raw
Liquipedia record), with Liquipedia's scheduled time in place of FACEIT's result-entry time. **Map-grain player
answers still under-represent exactly the matches that mattered most**, and the 28 `result_only` series Liquipedia has
not linked have no map results at all. Series-grain answers (`record`, `series record against`) count every one, and a
versus answer names the series it had to exclude.

### 2024 carries 9 stat keys; 2025 and 2026 carry 47

`stats_2024` - the 2024 payloads expose only Eliminations, Deaths, Assists,
Damage Dealt, Healing Done, Damage Mitigated, K/D Ratio, Result and Role (the
last two of those are a rate and a label, so six countable stats). Per-10
minute rates, Final Blows, Solo Kills, Objective Time and Time Played do not
exist for that season at all, so an all-seasons leaderboard for any of them is a
2025+ leaderboard wearing an all-time label. `stat_coverage_season` is the
machine-readable form of this.

### Map duration is derived, and only from 2025 onward

`map_duration` - no payload carries a map duration field. `map_durations`
derives it from the per-player `Time Played` stat, which 2024 does not have.
1,004 of 1,482 ingested maps carry a duration: all 748 maps of 2025 and all 256
of 2026, and none of 2024's 478.

### Scope is OWCS NA + EMEA main competition

`scope_na_emea` - The Korea, China, Japan and Pacific regional leagues are not
ingested, nor are open qualifiers, community cups or relegation brackets held
outside the main series. Korea in particular has no usable FACEIT data at all. A
leaderboard here ranks NA and EMEA main-competition play plus the international
events (Dreamhack Dallas, EWC 2024, the World Finals, Midseason Championships and
Champions Clash), not OWCS worldwide. The international events other than Dallas
come from Liquipedia alone: they answer records, head-to-heads and placings, never a
player stat. The note is not attached to an answer about one of those events.

### A results-only slice has series results but no player stats, from any source

`results_only_source` - coverage says which stat keys exist per season; it has
no concept of a slice where no player stats exist at all. Liquipedia records
results, map scores, picks and placings and never a player stat; a FACEIT
`result_only` competition (Dreamhack Dallas, all 14 series) has series results
and no per-map stats either. `source_capabilities` (migration
`031_capabilities.sql`) derives per included championship, from provenance,
whether any source gives it map results and whether any gives it player stats;
`region_sources` declares the same per region (Korea: `{liquipedia}`, no
player stats). Where a whole slice is results-only, a player-stat question is
refused with reason code `results_only` and offered what that slice can answer
(the series record, the question without the region) rather than answered with
an empty or partial ranking. Where only part of a slice is, the answer names
the part it could not rank. An included championship with no series at all is
empty, not results-only, and stays on the no-data path.

### The 2025 and 2026 main series is reconstructed from player history

`main_series_2025_2026` - FACEIT publishes those OWCS Central divisions on no
championship, hub or league endpoint and in no search result. They were
assembled by the roster-seeded crawl above, which ran to convergence, so a
series played entirely by players the crawl never reached would be absent with
nothing to indicate it. 2024 comes from the championship endpoints directly and
carries no such caveat.
