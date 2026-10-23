# Conventions

The rules this project holds itself to about what data means. Every other document assumes them. The
counting definitions the golden suite rests on are in [testing.md](testing.md#golden-answer-suite).

## Learned from wrong answers

Each was learned from a wrong answer this project actually gave (they were first written down in the Stage 3
closing summary, [liquipedia.md](liquipedia.md#stage-3-closing-summary-2026-10-02)):

- **A FACEIT team id follows the roster, not the organisation.** Its `leader` is always a rostered player and its
  avatar follows the brand; neither tells "the org got a new roster" from "the roster moved to a new org". Only the
  owner's knowledge decides a window. The one helpful signal: the later brand fielding a team id of its own.
- **Team ids get recycled.** One id can carry unrelated teams years apart (0464a373: UNC inc, Rad, Sakura, LuneX), so
  continuity of id is not continuity of anything. A long gap with roster turnover flags a candidate, never decides one.
- **Roster overlap is not identity, and roster change is not org change.** Whole rosters move between orgs, and one
  org fields different rosters (Quick Esports: three rosters on one id, plus a 2024 id).
- **FACEIT renames lag.** A name change usually lands days after the real change (Sakura played the 2025 Stage 2
  opener as "Rad"); a stage boundary, Liquipedia's name and who played outrank FACEIT's first sighting of a name.
- **Liquipedia's team pages follow the brand, not ownership** (1DIPVS100GORILLAS had its own page; same org).
- **FACEIT fabricates results, not map rows.** A sweep's extra map lives only in `/matches` `detailed_results`
  (5-0 for a 4-0); a drawn map is counted as a win. Liquipedia lists unplayed map slots as `notplayed`, never games.
- **A decision recorded is not a decision applied.** 166 identities and 11 team names sat unloaded for a session, and
  one decision was stranded on a branch committed after its PR merged.
- **A name must route to the entity that holds its series.** A Liquipedia name anchored to a bare team id answered with
  the wrong era's record while every record key was correct.

## Known FACEIT quirks handled

| Quirk | Handling |
| --- | --- |
| Listing `results` can describe the first map, not the series | DETAIL re-derives from `/matches/{id}` and overwrites; flips logged and flagged in `result_flipped`; LIST values kept in `list_*` columns for audit |
| `stats.rounds[]` has one entry per map played, fewer than picks | `match_rounds` = rounds only; picks stored separately in `match_map_picks`; `matches.maps_played` vs `matches.maps_picked` |
| `round_stats["OW2 Mode"]` is the game mode | Read directly into `match_rounds.game_mode`; never inferred from the map name |
| `round_stats["Map"]` is a GUID (`0x08...`) | Resolved to a name through the detail payload's `voting.map.entities`; both stored |
| Players sit under `teams[]` in stats | `match_players.team_id` is the team id carried with the player row (the enclosing team's id) and equals `faction_id` from `/matches/{id}` |
| Nicknames change | `players.player_id` is the FACEIT GUID; `players.nickname` is the latest seen; `player_nicknames` keeps every nickname with first/last seen |
| Championship timestamps are epoch ms, match timestamps epoch s | `ts_from_epoch` handles both |
| Listing offset is capped at 500 (600 items max, offset must be a multiple of limit) | Client stops at the cap and flags `championships.list_truncated`; a WARNING `championship_listing_truncated` is logged. Six 2024 open-qualifier Swiss events exceed 600 matches |
| An empty bracket slot is a placeholder faction named `bye`, scored 1-0 for the real team | It is not a series. Ingest marks it `skipped` (`ingest_error` starts `bye:`) at LIST and at DETAIL, and migration 021 reclassified the 24 already stored. Left in, they gave 13 teams wins they never played and a team called "bye" 24 losses across NA and EMEA; `region_consistency` found it |
| Rate limit headers are `ratelimit-limit: 20, 20;w=1` (IETF style) | Parsed alongside `X-RateLimit-*`; limiter paces to the advertised window and pauses at low `remaining`; 429/5xx back off exponentially with full jitter and honour `Retry-After` |

Not observed but worth knowing: FACEIT's `detailed_results` can have more
entries than `stats.rounds[]` (a bo7 fixture has 6 vs 5). Map counts always
come from `rounds[]`.
