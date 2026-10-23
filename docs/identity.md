# Identity: orgs, aliases and competition names

How a team id becomes an organisation, how a name a fan types reaches an entity, and how competitions are
named. Identity across sources (Liquipedia anchors, line-ups, name history) is in [liquipedia.md](liquipedia.md).

## Team identity (orgs)

FACEIT issues a new team id per season, so one organisation appears as several
team ids and every cross-season team query silently undercounts. `orgs` and
`team_orgs` (migration `009_orgs.sql`) give an organisation a stable id with
team ids as the mutable handles, mirroring how `players.player_id` is stable and
nicknames are history. A team id belongs to exactly one org.

```bash
python -m owcsmuse orgs propose                  # writes scope/org_report.md with the evidence
python -m owcsmuse orgs decide <team_id> --org <org-id> --org-name "Name" --note "..."
python -m owcsmuse orgs reject <id_a> <id_b> --reason "..."   # decided: different orgs
python -m owcsmuse orgs load                     # write decided mappings into orgs / team_orgs
python -m owcsmuse orgs status
python -m owcsmuse refresh                       # required: the aggregates carry org_key
```

Nothing merges without review. Proposals go through `scope/org_decisions.json`
the same way scope decisions go through `scope/decisions.json`, and a rejection
is recorded as a decision too, so a pair that was looked at and turned down
never returns as pending review. An unmapped team id stays unmapped and keys as
`team:<id>`, visibly itself in any grouping - there is no silent fallback.

**What the evidence is actually worth.** The proposer weighs four signals: name
identity after folding, roster overlap across the two date windows, date
adjacency, and region. Reviewing the output on real data inverted the expected
ordering, twice:

- **Roster overlap is weak evidence, and sometimes points the wrong way.** In
  esports whole rosters move between organisations, so a squad that transferred
  looks identical to a rename. Four pairs at 80-100% overlap - Geekay Esports /
  NTMR, NTMR / Dallas Fuel, LeftRightGnight / Geekay Esports, Al qadsiah /
  Geekay Esports - are distinct organisations. Meanwhile the one real rename in
  the data, Al qadsiah to qadsiah, shared **1 of 8** players, because the roster
  turned over at the same time. Merging on overlap would have made four wrong
  merges and missed the right one.
- **A new name that shares players with an earlier team is not that team.**
  The same rule applies to the Liquipedia-only names. Of the 2024 Stage 3/4
  teams with no FACEIT side, TSM fielded 6 of NTMR's players, FLUFFY AIMERS 8
  from the NTMR team id's Supernova/Team Z eras, YFP 4 of Vice's, and Vendetta
  and Piece of Cake ex-Team Peps players. Each is its own org (owner,
  2026-10-17). Each season stands on its own, and a roster that moved does not
  carry its old org's record with it. Identity needs a decision that says so,
  such as a name change on the same team id or a named pickup bounded to its
  window like Citrus Nightmare's Stage 3. Shared players are never enough.
- **Name identity is not enough by itself, and two applied merges proved it
  the hard way.** "SpaceStation Gaming" (NA) was merged with "SpaceStation"
  (EMEA) on a contained-name match; "Geekay Esports" (NA) was merged with an
  *identically named* "Geekay Esports" (EMEA). Both had 0% roster overlap.
  Both were wrong: the two are unrelated teams that happen to share a name,
  and the wrong merge surfaced as a real bug - an NA player's "record" query
  pulled in a completely unrelated EMEA team's matches. Name identity, even
  exact-fold, is corroborating evidence, not identity by itself.
- **Region is a hard rule, not a signal.** OWCS is region-locked: a
  competing roster plays in `na` or `emea`, never both, and does not switch
  between them season to season. `region_conflict()` refuses any pair whose
  match history spans disjoint regions, before name or roster evidence is even
  considered - identical names included. `international` events (Dreamhack,
  Midseason Championship, ...) never conflict with anything, since any region
  can attend one alongside its home-region schedule.
- **Date adjacency corroborates**, but only within a region. Two ids whose
  match windows overlap may be two teams that coexisted, which is reported
  rather than assumed.
- **A name change on a stage boundary is a roster pickup, not a rebrand.** In
  OWCS a team id is issued per roster and the name on it changes when another
  organisation picks the roster up between stages: Ex Oblivione -> Virtuspro
  (2025 Stage 1), Avidity -> Extinction (2025 Stage 2), Extinction -> The Kafe
  (2026 Stage 2, which began 2026-06-13). The roster continues, the organisation
  does not, so the new name starts a new era of the same team id (a window,
  below) rather than extending the old org's history. A rename by the same org
  (Al qadsiah -> qadsiah) lands mid-stream and keeps the roster's org. The stage
  boundary is the tell - but not alone: production shows 18 team ids carrying
  more than one name, and SpaceStation -> SpaceStation Gaming, GenG -> GenG
  Esports, Goud Guys -> Goud Guys ANM, PIP -> PxG PiP and Sakura -> Sakura
  Esports also land on stage boundaries and are renames. So three signals read
  a change (`classify_name_change`): a new name that **contains or extends** the
  old one is a rename and starts no window; a **wholly different** name on a
  stage boundary is a pickup; a **registration placeholder** (a `team_<captain>`
  name, or one that lived only in a stage's opening fortnight, replaced inside
  that stage once the roster signed up: team_chiime -> Dreamland, BuboSprayCheck
  -> ENCE) is the same organisation and no window; anything else (a different
  name inside one stage, or two names whose date ranges overlap) is reported for
  a person. The tool decides nothing. The review of all 18 is
  `scope/org_window_review.md` (`python tools/window_review.py`, from the
  captured history in `scope/team_name_history_2026-10-01.json`); the owner's
  verdict on each is `scope/org_window_decisions.json`, and the report shows it
  under the id, flagging where a signal reads the id differently (Umbrellaacademy
  -> ROCstars fires the placeholder signal and was decided an org change; the
  overlapping Anyones Legend / 1234 dates are a FACEIT artifact over a roster
  drop, decided a pickup). cb90edf6 is Quick Esports throughout (owner,
  2026-10-02, reversing a 2026-10-01 window): the org fielded three rosters on
  it, one of them as 1DIPv100GORILLA in 2025 Stage 2, and a name change on a
  team id can be the same organisation fielding a different roster - neither
  FACEIT's team leader and avatar nor Liquipedia's team pages tell the two
  apart, so a window needs the owner's knowledge, not the signals.

  **A FACEIT team id follows the roster, not the organisation.** Neither the
  team's `leader` nor its avatar tells "the org got a new roster" from "the
  roster moved to a new org". Across all 19 multi-name team ids (2026-10-02)
  the leader is a rostered player in every match, rotates inside one brand
  (GenG had five), and carries over exactly when the players do: it carried
  across Timeless -> NTMR (different orgs) and changed between Quick Esports'
  June and September rosters (one org). The one signal that helps is whether
  the later brand also fields a team id of its own (NTMR on two ids, Virtus pro
  and Extinction on a second id in 2026): that makes it an organisation in its
  own right, though it still does not prove the earlier brand was a different
  one.

  **An id can also be recycled across unrelated teams, so continuity of id is
  not continuity of anything.** 0464a373 is four teams FACEIT reassigned one id
  to - UNC inc (2024), Rad (2025 Stages 1-2), Sakura (2025), LuneX (2026) -
  decided by the owner on 2026-10-02 as four entities with nothing connecting
  them, and its Liquipedia names anchor to each era's org rather than to the id
  (anchored to the id, "LuneX Gaming" and "Rad Esports" once answered with UNC
  inc's 2024 record). A long gap with roster turnover flags a candidate but
  decides nothing: every off-season is 145-290 days, and Twisted Minds kept 2 of
  8 players from 2024 to 2025 as one organisation. A FACEIT rename can also lag
  the real change: Sakura played the 2025 Stage 2 opener under FACEIT's stale
  name "Rad", so its window starts at the stage boundary, not the first sighting.
  A team id whose
  names are several organisations' eras carries one mapping per era
  (`orgs decide --add`, stored under `windows`): 0464a373 is UNC inc (its own),
  Rad, Sakura / Sakura Esports and LuneX; d20d1868 is team_chiime / Dreamland
  (its own), Supernova and Team Z. NTMR is one organisation across cefc3f72
  (2025 Stage 1) and c5116cb3 (from Stage 2), each mapped only over its own
  NTMR era so FMCL's and Timeless's eras stay out of it.

**A mapping holds over a window.** A FACEIT team id belongs to an org over
`[valid_from, valid_to)` (`orgs decide --from ... --to ...`; absent means for all
time, which is what every decision made before windows existed still means).
Outside its window the team id is itself: keyed `team:<id>`, displayed and
searchable by the name it carried then, with its own record. That is how an
acquired roster stays out of the acquiring org's history - Virtus pro took over
the Ex Oblivione roster in 2025 and FACEIT kept the team id, so `bb5dd404` is
Virtus pro from 2025-01-01 and Ex Oblivione before it; "Ex Oblivione record"
answers with the 2024 series and "VP record" without them. Identity is a
function of (team id, when): `team_identity_at()`, which every fact view joins
at the series' own time; `team_identity` is identity now. The proposer proposes
a window whenever a team id carried a name that is not the org's before it first
carried the org's name (`propose_window`), and nothing is proposed from roster
movement. A window is sourced, not chosen: `orgs decide --from-name "Virtuspro"`
bounds it by the first sighting of that FACEIT name on the team id, resolved
from `team_names` at load (a name the id never carried applies nothing and is
reported). One org can span several team ids each bounded to its own era -
Extinction is `2b7f8ef6` over its 2025 Extinction era and `a35f8d47` over its
2026 one, on org branding rather than roster continuity. A team id cannot
belong to two orgs at once (a trigger refuses the overlap), and `check` flags a
window that covers none of its team id's series.

Current state: 9 orgs covering 18 team ids (one of them windowed), 7 pairs
recorded as reviewed rejections (2 of them region conflicts found after the fact
and reversed), 62 team ids unmapped and queryable as themselves.

**Known gap: a team id maps to an org for all time.** A FACEIT team id can outlive
an organisation: id `bb5dd404` was "Ex Oblivione" in 2024 and "Virtuspro" in 2025,
because Virtus pro acquired that roster. Roster movement is not org identity (see
above), so Ex Oblivione's 2024 series are not Virtus pro's, yet today the org's
record includes them (5 series where 2 are Virtus pro's). Two consequences: an
org's record over-counts across an acquisition, and an org's searchable names hold
each team id's *current* name only, so "Ex Oblivione" finds nothing. The fix is a
date-bounded team-to-org mapping with a name history for each side; it is
scheduled with the source-agnostic identity work (Stage 3 of the Liquipedia
integration). The golden suite holds both as known bugs (G11, G13).

## Aliases

`resolve()` already finds an abbreviation FACEIT itself recorded - if a team
really was named "SOG" at some point, that is in `entity_names` (nickname and
team-name history) and needs nothing further. It cannot find community
shorthand nobody on FACEIT ever typed - "SSG" for SpaceStation Gaming, "TL"
for Team Liquid - because there is nothing in the data to match it against;
the fuzzy scorer in `resolve.py` picks something unrelated instead. That is
not something to guess at: it is a human decision, routed through the same
reviewed-decisions-file pattern as scope and org identity, never a hardcoded
table baked into the resolver.

```bash
python -m owcsmuse alias set SSG --type org --entity-id spacestation-gaming --note "..."
python -m owcsmuse alias set TL  --type team --entity-id a58dedff-8045-46be-a13e-2402495b6a9d --note "..."
python -m owcsmuse alias forget SSG
python -m owcsmuse alias load      # write scope/alias_decisions.json into entity_aliases
python -m owcsmuse alias status
```

An alias resolves as an exact, authoritative lookup (`resolve_alias()`), ahead
of the fuzzy scoring in `rank_candidates()` and before it ever runs - not
folded into the same ranked pool. That distinction mattered in practice: "TM"
scores 1.0 against the Twisted Minds alias, but "TML Nightmare" (an unrelated
team) scores 0.9 against the bare letters "tm" by starting with them, close
enough that the ordinary ambiguity margin would have asked which one was
meant. A human already decided that; resolve() must not re-open it.

Decided so far: `SSG` -> SpaceStation Gaming, `VP` -> Virtus pro, `peps` ->
Team Peps and `quick` -> Quick Esports (orgs); `TL` -> Team Liquid, `TM` ->
Twisted Minds, `CR` -> Crazy Raccoons, `DSG` -> Disguised, `DF` -> Dallas Fuel,
`toronto` / `defiant` / `TD` -> Toronto Defiant, `GG` / `Gen.G` -> GenG
Esports, `TF` -> Team Falcons, and `GK NA` / `GK EMEA` -> the two Geekay
Esports teams (team ids, unmapped to any org).

Geekay is region-split: two team ids, NA (2025) and EMEA (2026), and an alias
names one entity. A single `GK` would pick a region silently, so the aliases
carry the region; a bare "GK" prefix-matches both and asks which (golden
G46-G47). Not aliased, by owner decision (2026-10-08): `vision` is the exact
in-game name of the player Vision (VisionLIVE), and an alias to Vision Esports
would hide that player; it stays a clarify between the two. `CN` (Citrus Nation over
the player CNYXC) was considered and dropped.

A partial name ("toronto", "peps") is the same mechanism as an initialism: an
alias is an exact lookup of the folded string, whatever its shape, and fires
only when the whole name asked for equals it, ahead of fuzzy scoring.
"Toronto Defiant" still resolves by its own name. `quick` was checked for
collisions first: "Vanir Quick" is a historical name of the Quick Esports org
itself, not another team.

`TF` overrides a resolution that existed: "tf" reached the team TFW (no series)
by prefix. The collision is settled in Team Falcons' favour by community
usage, not by evidence strength, so TFW also fitting the initials is no reason
to undo it (golden G45). `GG` likewise overrides a fuzzy match to the player
Zerggy.

An alias that names a team id follows that team into its org once the team is
mapped and has no era of its own (`ALIAS_TARGET` in `resolve.py`), and its name
comes from the entity, else the stored team or org name, never the id. `SSG`
pointed at team 6ddc0431 until that team joined the spacestation-gaming org;
from then on it answered with the UUID as its name and the team's empty slice
as its data.

A team named in front of the player or role noun is a filter ("which DF
player", "which twisted minds tank", "most deaths by a spacestation gaming
dps"), read by one extractor (`_find_team_qualifier` in `nlq/parser.py`) before
role words are stripped, and the sentence names the players it ranked: "TVNT
leads Deaths among Twisted Minds tanks". "Team" is part of a name: "team
liquid" is searched whole, and `resolve()` drops the word only when the whole
names nobody ("team twisted minds").

## Competition names

FACEIT League numbers its seasons ("S9 NA OWCS Central - Playoffs"); the competition people follow is
"OWCS 2026 NA Stage 2 Playoffs". The mapping is display-only: `championships.name` stays FACEIT's, and only
`championship_display_name()` reads the reviewed names in `competition_names`. A name is shown only after a person
has decided it.

```bash
python -m owcsmuse competitions propose           # scope/competition_names_report.md; applies nothing
python -m owcsmuse competitions accept            # bulk-accept the reviewed Liquipedia page map
python -m owcsmuse competitions accept --bases liquipedia-owner,owner   # pages / descriptions you supplied
python -m owcsmuse competitions decide <id> [--name "..."]              # one competition
python -m owcsmuse competitions load              # decisions -> competition_names (`migrate` also does this)
```

Sources, in order of trust: `scope/liquipedia_map.json` (the page that covers each FACEIT League competition,
reviewed in Stage 1: `liquipedia`), `scope/competition_pages.json` (pages supplied by the project owner for the 2024
competitions: `liquipedia-owner`; a path marked `verified: false` was inferred, not seen) and events described by
the owner with no page (Dreamhack Dallas, the relegations: `owner`). Year, region and stage come from the page path
and the phase from FACEIT's own suffix, cross-checked against the page's shape. A decision made against a FACEIT
name that later changes stops applying and is reported as stale.

A page path nobody has seen (`"verified": false` in `scope/competition_pages.json`) is never bulk-accepted. One request
checks them all, projection first:

```bash
python -m owcsmuse liquipedia probe-pages              # shows the projection (1 request) and the budget; sends nothing
python -m owcsmuse liquipedia probe-pages --execute    # sends it (needs LIQUIPEDIA_API_KEY and OWCS_LIQUIPEDIA_ENABLED=1)
```

It reports, per page, how many matches Liquipedia holds on it. Set `"verified": true` for the pages that came back, and
`competitions accept --bases liquipedia-owner` takes them.
