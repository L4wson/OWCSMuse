"""Validate a StructuredQuery against the real schema.

`SchemaInfo` is a snapshot of what actually exists: stat keys per season (from
stat_coverage_season), maps, modes, seasons, championships and regions in
scope. It is loaded from the database in production and constructed by hand in
tests, so validation itself is pure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any, Optional, Union

import psycopg

from ..resolve import fold
from .schema import DERIVED_METRICS, StructuredQuery, Unanswerable

# FACEIT stat key -> typed column suffix in agg_player_stats / agg_player_season.
TYPED_STATS: dict[str, str] = {
    "Eliminations": "eliminations",
    "Final Blows": "final_blows",
    "Deaths": "deaths",
    "Assists": "assists",
    "Solo Kills": "solo_kills",
    "Multi Kills": "multi_kills",
    "Environmental Kills": "environmental_kills",
    "Damage Dealt": "damage_dealt",
    "Healing Done": "healing_done",
    "Damage Mitigated": "damage_mitigated",
    "Objective Time": "objective_time",
    "Time Played": "time_played",
}

TEAM_METRICS = {"record", "win_rate", "wins", "losses", "matches", "maps", "map_wins", "map_losses", "map_win_rate"}
PLAYER_DERIVED = {"kd_ratio", "maps", "matches", "map_win_rate", "map_wins", "map_losses", "wins", "losses"}


@dataclass
class SchemaInfo:
    stat_keys: dict[str, set[int]] = field(default_factory=dict)   # key -> seasons with the key
    stat_kinds: dict[str, str] = field(default_factory=dict)       # key -> countable | derived_rate | non_numeric
    maps: set[str] = field(default_factory=set)
    modes: set[str] = field(default_factory=set)
    seasons: set[int] = field(default_factory=set)
    championships: dict[str, str] = field(default_factory=dict)    # id -> FACEIT's stored name (included only)
    # id -> the name people see (championship_display_name). A question may use either: the stored FACEIT name is
    # what the data says, the displayed name is what an answer calls the competition, and a name that is shown
    # must be a name that can be searched.
    championship_display: dict[str, str] = field(default_factory=dict)
    championship_season: dict[str, int] = field(default_factory=dict)
    championship_region: dict[str, str] = field(default_factory=dict)
    regions: set[str] = field(default_factory=set)
    # Capability (Stage 3): per championship, whether any source gives it map results / player stats; per declared
    # region, whether any source records player stats there at all (korea: no, by construction).
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    region_player_stats: dict[str, bool] = field(default_factory=dict)
    # first and last series per championship (the series view), for reading "this stage" and saying when it was played
    championship_dates: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    # championships whose only source is Liquipedia (`lp:`, Stage 4): no player stats by declaration, like a region in
    # region_sources, whether or not any of their series has loaded yet
    liquipedia_only: set[str] = field(default_factory=set)
    # season-scoped team groups (043): the seasons each group has members in
    group_seasons: dict[str, set[int]] = field(default_factory=dict)

    @classmethod
    def from_db(cls, conn: psycopg.Connection) -> "SchemaInfo":
        info = cls()
        with conn.cursor() as cur:
            cur.execute("SELECT stat_key, season, stat_kind FROM stat_coverage_season")
            for r in cur.fetchall():
                info.stat_keys.setdefault(r["stat_key"], set()).add(r["season"])
                info.stat_kinds[r["stat_key"]] = r["stat_kind"]
            cur.execute("SELECT DISTINCT map_name, game_mode, season, region FROM agg_map_modes")
            for r in cur.fetchall():
                if r["map_name"]:
                    info.maps.add(r["map_name"])
                if r["game_mode"]:
                    info.modes.add(r["game_mode"])
                if r["season"] is not None:
                    info.seasons.add(r["season"])
                if r["region"]:
                    info.regions.add(r["region"])
            cur.execute("SELECT championship_id, map_results, player_stats, series FROM source_capabilities")
            for r in cur.fetchall():
                info.capabilities[r["championship_id"]] = {"map_results": bool(r["map_results"]),
                                                           "player_stats": bool(r["player_stats"]), "series": int(r["series"])}
            cur.execute("SELECT region, player_stats FROM region_sources")
            for r in cur.fetchall():
                info.region_player_stats[r["region"]] = bool(r["player_stats"])
            cur.execute("SELECT group_key, season FROM team_groups GROUP BY group_key, season")
            for r in cur.fetchall():
                info.group_seasons.setdefault(r["group_key"], set()).add(r["season"])
            cur.execute("SELECT championship_id, min(played_at) AS first_at, max(played_at) AS last_at FROM series "
                        "WHERE championship_id IS NOT NULL GROUP BY championship_id")
            for r in cur.fetchall():
                info.championship_dates[r["championship_id"]] = (r["first_at"], r["last_at"])
            cur.execute("SELECT championship_id, name, championship_display_name(name) AS display_name, season, "
                        "scope_region, source FROM championships WHERE include")
            for r in cur.fetchall():
                cid = r["championship_id"]
                info.championships[cid] = r["name"]
                if r["source"] == "liquipedia":
                    info.liquipedia_only.add(cid)
                info.championship_display[cid] = r["display_name"] or r["name"]
                if r["scope_region"]:
                    info.championship_region[cid] = r["scope_region"]
                if r["season"] is not None:
                    info.seasons.add(r["season"])
                    info.championship_season[cid] = r["season"]
        conn.commit()
        return info

    # ---- relative periods
    def stages(self, region: Optional[str] = None, season: Optional[int] = None) -> list[tuple[int, int, list[str]]]:
        """(season, stage number, championship ids) of every stage with series in scope, oldest first.

        A stage is every included championship whose OWCS name says "Stage N" in that season ("Regular Season",
        "Playoffs" and "Relegation" alike), in the given region when one is asked for. NA and EMEA run their stages
        side by side, so without a region a stage is both.
        """
        out: dict[tuple[int, int], list[str]] = {}
        for cid in self.championship_dates:
            if cid not in self.championships or self.championship_season.get(cid) is None:
                continue
            if region is not None and self.championship_region.get(cid) not in (None, region):
                continue
            if season is not None and self.championship_season[cid] != season:
                continue
            m = re.search(r"\bstage\s*(\d+)\b", fold(self.championship_display.get(cid, self.championships[cid])))
            if m:
                out.setdefault((self.championship_season[cid], int(m.group(1))), []).append(cid)
        return [(se, n, sorted(cids)) for (se, n), cids in sorted(out.items())]

    def seasons_played(self) -> list[int]:
        """Seasons with series in scope, oldest first."""
        return sorted({self.championship_season[c] for c in self.championship_dates
                       if c in self.championships and self.championship_season.get(c) is not None})

    # ---- lookups used by validation and compilation
    # Sorted: a set's order is the process's hash seed, so with "Control" and "control" both stored, one process
    # answered every Control question from 2 maps and another from 1,218. 048 keeps one spelling stored; this keeps the
    # choice the same in every process regardless, and never takes a rarer spelling because a question typed it.
    def match_map(self, name: str) -> Optional[str]:
        f = fold(name)
        for m in sorted(self.maps):
            if fold(m) == f:
                return m
        for m in sorted(self.maps):
            if f and f in fold(m):
                return m
        return None

    def match_mode(self, name: str) -> Optional[str]:
        f = fold(name)
        for m in sorted(self.modes):
            if fold(m) == f:
                return m
        return None

    def match_championships(self, text: str, season: Optional[int] = None, region: Optional[str] = None) -> list[tuple[str, str]]:
        """All included championships one of whose names contains every word of `text` (folded).

        A championship answers to its FACEIT name and to its displayed OWCS name; the words must all come from the
        same one, so "stage 2 playoffs" cannot be assembled from two different names. Season and region are read
        from the championship's own columns when known (FACEIT League names carry no year), else from its name.
        """
        folded = fold(text)
        # "stage 2" is one thing: its digit must follow the word, and may not be read out of "2026".
        stages = re.findall(r"\bstage\s*(\d+)\b", folded)
        words = [w for w in re.sub(r"\bstage\s*\d+\b", " ", folded).split() if w not in {"the", "in", "at", "of"}]

        def has_all(name: str) -> bool:
            tokens = re.findall(r"[a-z0-9]+", name)
            return (all(re.search(rf"\bstage {n}\b", name) for n in stages)
                    and all(w in tokens or (len(w) >= 3 and any(t.startswith(w) for t in tokens)) for w in words))

        out = []
        for cid, stored in self.championships.items():
            shown = self.championship_display.get(cid, stored)
            names = [fold(n) for n in dict.fromkeys((stored, shown))]
            if not any(has_all(n) for n in names):
                continue
            if season is not None:
                known = self.championship_season.get(cid)
                if (known != season) if known is not None else not any(str(season) in n for n in names):
                    continue
            if region in ("na", "emea"):
                known = self.championship_region.get(cid)
                if known is not None:
                    if known != region:
                        continue
                elif not any((" na " in f" {n} ") if region == "na" else ("emea" in n) for n in names):
                    continue
            out.append((cid, shown))
        return sorted(out, key=lambda x: x[1])


@dataclass
class Validated:
    query: StructuredQuery
    championship_ids: list[str] = field(default_factory=list)   # resolved championship filter (may be several)
    map_name: Optional[str] = None
    mode_name: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    results_only_parts: list[str] = field(default_factory=list)   # competitions in the slice that carry no player stats
    stat_kind: Optional[str] = None                                # countable | derived_rate | non_numeric, for a stat key


# ------------------------------------------------------------------ capability

def needs(q: StructuredQuery, info: SchemaInfo) -> str:
    """What a question needs from its slice: 'player_stats', 'maps' or 'series'."""
    if q.metric and q.metric in info.stat_keys:
        return "player_stats"
    if q.metric == "kd_ratio" or (q.entity == "player" and q.intent in ("leaderboard", "entity_stat", "map_stats", "versus")):
        return "player_stats"
    if q.intent in ("versus", "map_stats", "season_compare") or (q.metric or "").startswith("map"):
        return "maps"
    return "series"


def slice_championships(q: StructuredQuery, info: SchemaInfo, champ_ids: list[str]) -> list[str]:
    """The championships a question draws on: the resolved filter, else every included one in its season/region."""
    if champ_ids:
        return list(champ_ids)
    out = []
    for cid in info.championships:
        if q.filters.season is not None and info.championship_season.get(cid) not in (None, q.filters.season):
            continue
        if q.filters.region is not None and info.championship_region.get(cid) not in (None, q.filters.region):
            continue
        out.append(cid)
    return out


def capability(q: StructuredQuery, info: SchemaInfo, champ_ids: list[str]) -> tuple[str, list[str]]:
    """('full' | 'partial' | 'none', the results-only competitions) for what this question needs.

    'none' means no championship in the slice can answer it, or the region is declared results-only and holds no
    data yet; 'partial' names the competitions that cannot, so the answer can say which part it could not rank.
    """
    need = needs(q, info)
    if need == "series":
        return "full", []
    key = "player_stats" if need == "player_stats" else "map_results"
    cids = slice_championships(q, info, champ_ids)
    if not cids:
        region = q.filters.region
        if region and info.region_player_stats.get(region) is False and need == "player_stats":
            return "none", [f"the {region.upper()} region"]
        return "full", []
    # an included championship with no series at all is empty, not results-only: leave that to the no-data path. A
    # Liquipedia-only one never has player stats, by declaration, loaded or not; its map results are Liquipedia's own
    # (041) and count like any other.
    lacking = [cid for cid in cids if (cid in info.liquipedia_only and key == "player_stats")
               or (info.capabilities.get(cid, {}).get(key) is False and info.capabilities.get(cid, {}).get("series", 0) > 0)]
    if not lacking:
        return "full", []
    names = sorted({info.championship_display.get(cid, info.championships.get(cid, cid)) for cid in lacking})
    return ("none" if len(lacking) == len(cids) else "partial"), names


ValidationResult = Union[Validated, Unanswerable]


_PERIOD_WORDS = {"this_season": "this year / this season", "last_season": "last year / last season", "this_stage": "this stage",
                 "last_stage": "last stage"}


def resolve_period(q: StructuredQuery, info: SchemaInfo) -> Union[tuple[StructuredQuery, Optional[str]], Unanswerable]:
    """Read "this year", "last season", "this stage", "last stage" against the data: (query with a season and, for a
    stage, a championship filter; the note that says what it was read as).

    The current season is the most recent season in scope and the current stage the most recent stage with series
    (by season, then stage number), in the asked region if there is one. Nothing reads today's date: between stages
    "this stage" is the stage just finished, and the note gives its dates so a reader can see it is over; in January,
    before the new season's first series, "this year" is still the last season played, and the note says which.
    A year asked for as well ("this stage in 2025") picks the period within that year.
    """
    f = q.filters
    if not f.period:
        return q, None
    words = _PERIOD_WORDS[f.period]
    if f.period in ("this_season", "last_season"):
        played = info.seasons_played() or sorted(info.seasons)
        if f.season is not None:
            return q.model_copy(update={"filters": f.model_copy(update={"period": None})}), (
                f"'{words}' was given with {f.season}; the year asked for is used")
        if not played or (f.period == "last_season" and len(played) < 2):
            return Unanswerable(code="no_data", reason=f"there is no {words} in scope: seasons with data: "
                                + (", ".join(map(str, played)) or "none"))
        season = played[-1] if f.period == "this_season" else played[-2]
        why = "the most recent season in scope" if f.period == "this_season" else "the season before the most recent in scope"
        return (q.model_copy(update={"filters": f.model_copy(update={"season": season, "period": None})}),
                f"'{words}' is read as the {season} season, {why}.")
    stages = info.stages(f.region, f.season)
    need = 1 if f.period == "this_stage" else 2
    if len(stages) < need:
        where = f" in {f.region.upper()}" if f.region else ""
        return Unanswerable(code="no_data", reason=f"there is no {words}{where} in scope: no stage has series"
                            + (f" in {f.season}" if f.season else ""))
    season, n, cids = stages[-need]
    dates = [d for c in cids for d in info.championship_dates.get(c, ()) if d is not None]
    regions = sorted({(info.championship_region.get(c) or "").upper() for c in cids} - {""})
    played = f", played {min(dates):%Y-%m-%d} to {max(dates):%Y-%m-%d}" if dates else ""
    why = "the most recent stage in scope" if f.period == "this_stage" else "the stage before the most recent in scope"
    champ = f"stage {n}" + (f" {f.championship}" if f.championship else "")
    return (q.model_copy(update={"filters": f.model_copy(update={"season": season, "championship": champ, "period": None})}),
            f"'{words}' is read as OWCS {season} Stage {n} ({' and '.join(regions) or 'all regions'}), {why}{played}.")


def _validate_placement(q: StructuredQuery, info: SchemaInfo) -> ValidationResult:
    """A placing belongs to one event: the question must name one, and it must be in scope."""
    f = q.filters
    if not f.championship:
        return Unanswerable(code="invalid_query", reason="a placing is per event: name the event, e.g. `who won the 2025 world finals`")
    matches = info.match_championships(f.championship, f.season, f.region)
    if not matches:
        return Unanswerable(code="no_data", reason=f"no tournament in scope matches '{f.championship}'"
                                                   + (f" in {f.season}" if f.season else ""))
    notes = []
    if len(matches) > 1:
        notes.append(f"'{f.championship}' matched {len(matches)} events; placings are listed for each: "
                     + "; ".join(n for _, n in matches)[:300])
    return Validated(query=q, championship_ids=[cid for cid, _ in matches], notes=notes)


def validate(q: StructuredQuery, info: SchemaInfo) -> ValidationResult:
    notes: list[str] = []
    f = q.filters

    if not info.stat_keys and not info.seasons:
        return Unanswerable(code="no_data",
                            reason="the warehouse has no included, ingested matches yet, so nothing can be answered",
                            suggestions=["Review scope/classification_report.md, then `load-manifest --accept-proposals`, `backfill` and `refresh`."])

    # --- per-side seasons on a comparison
    for side in ("subject_season", "opponent_season"):
        val = getattr(f, side, None)
        if val is not None and val not in info.seasons:
            have = ", ".join(str(s) for s in sorted(info.seasons)) or "none"
            return Unanswerable(code="no_data", reason=f"no data for the {val} season; seasons with data: {have}")

    if q.intent == "placement":
        return _validate_placement(q, info)
    if f.group:
        have = sorted(info.group_seasons.get(f.group, set()))
        if not have:
            return Unanswerable(code="no_data", reason=f"no {f.group} teams are recorded yet")
        if f.season is not None and f.season not in have:
            return Unanswerable(code="no_data",
                                reason=f"no {f.group} teams are recorded for {f.season}; seasons with them: "
                                       f"{', '.join(map(str, have))}")
        if q.intent == "team_group":
            return Validated(query=q)

    # --- metric
    if q.intent in ("versus", "season_compare"):
        if q.metric and q.metric not in DERIVED_METRICS and q.metric not in info.stat_keys:
            return Unanswerable(code="unsupported_metric",
                                reason=f"'{q.metric}' is not a stat in the warehouse")
    elif q.intent != "stat_availability":
        if q.metric is None:
            return Unanswerable(code="invalid_query", reason="no metric given")
        if q.metric in DERIVED_METRICS:
            if q.entity == "player" and q.metric not in PLAYER_DERIVED and q.intent in ("leaderboard", "entity_stat"):
                return Unanswerable(code="unsupported_metric", reason=f"{q.metric} is a team metric; ask about a team or use K/D for players")
        elif info.stat_kinds.get(q.metric) == "non_numeric":
            return Unanswerable(
                code="unsupported_metric",
                reason=f"'{q.metric}' is a label, not a number, so it cannot be ranked or totalled",
                suggestions=[f"'{q.metric}' can filter or group results once that is supported; "
                             "ask `what stats are available` for the numeric keys."])
        elif q.metric not in info.stat_keys:
            close = get_close_matches(q.metric, list(info.stat_keys), n=3, cutoff=0.6)
            base = q.metric.replace("/10m", "")
            if q.metric.endswith("/10m") and base in info.stat_keys:
                return Unanswerable(code="unsupported_metric",
                                    reason=f"per-10-minute {base} is only available where FACEIT provides it (2026-era payloads); "
                                           f"no season in the warehouse carries '{q.metric}'",
                                    suggestions=[f"Ask for total or per-map {base} instead."])
            return Unanswerable(code="unsupported_metric", reason=f"'{q.metric}' is not a stat in the warehouse",
                                suggestions=[f"did you mean: {', '.join(close)}"] if close else ["Ask `what stats are available`."])
    elif q.metric is not None and q.metric not in info.stat_keys:
        close = get_close_matches(q.metric, list(info.stat_keys), n=3, cutoff=0.6)
        return Unanswerable(code="unsupported_metric", reason=f"'{q.metric}' is not a stat in the warehouse",
                            suggestions=[f"did you mean: {', '.join(close)}"] if close else [])

    # --- season
    if f.season is not None and f.season not in info.seasons:
        have = ", ".join(str(s) for s in sorted(info.seasons)) or "none"
        return Unanswerable(code="no_data", reason=f"no data for the {f.season} season; seasons with data: {have}")

    # --- region
    if f.region is not None and info.regions and f.region not in info.regions:
        # a declared results-only region refuses a player-stat question for that reason, not for lack of data
        if info.region_player_stats.get(f.region) is False and needs(q, info) == "player_stats":
            return Unanswerable(code="results_only",
                                reason=f"{f.region.upper()} is a results-only region: no source records player stats there, "
                                       "so there is no player leaderboard to give",
                                suggestions=["Records, head-to-heads and placings are answerable for a results-only region; "
                                             "player stats exist only where FACEIT recorded them (NA and EMEA)."])
        return Unanswerable(code="no_data", reason=f"no data for region '{f.region}'; regions with data: {', '.join(sorted(info.regions))}")

    # --- map / mode
    map_name = mode_name = None
    if f.map:
        map_name = info.match_map(f.map)
        if not map_name:
            close = get_close_matches(fold(f.map), [fold(m) for m in info.maps], n=3, cutoff=0.6)
            return Unanswerable(code="no_data", reason=f"no maps named '{f.map}' in the warehouse",
                                suggestions=[f"maps with data: {', '.join(sorted(info.maps))}"] + ([f"did you mean: {', '.join(close)}"] if close else []))
    if f.mode:
        mode_name = info.match_mode(f.mode)
        if not mode_name:
            return Unanswerable(code="no_data", reason=f"no game mode '{f.mode}' in the warehouse; modes with data: {', '.join(sorted(info.modes))}")

    # --- championship
    champ_ids: list[str] = []
    if f.championship:
        matches = info.match_championships(f.championship, f.season, f.region)
        if not matches:
            return Unanswerable(code="no_data", reason=f"no tournament in scope matches '{f.championship}'",
                                suggestions=[f"tournaments in scope: {', '.join(sorted(set(info.championship_display.values() or info.championships.values())))[:400]}"])
        champ_ids = [cid for cid, _ in matches]
        if len(matches) > 1:
            notes.append(f"'{f.championship}' matched {len(matches)} tournaments; results cover all of them: "
                         + "; ".join(n for _, n in matches)[:300])

    # --- role
    # Role is recorded per player per map (match_players.role), not per player:
    # a flex player who played tank in some maps and DPS in others belongs to
    # both leaderboards for the maps they actually played that role. That only
    # has a clean meaning at player + map grain, so it is scoped there rather
    # than silently ignored or guessed at elsewhere.
    if (f.role is not None and q.intent != "stat_availability"
            and not (q.intent in ("leaderboard", "entity_stat") and q.entity == "player")):
        return Unanswerable(code="unsupported_question",
                            reason=f"a role filter ('{f.role}') is only supported for a player leaderboard or a "
                                   "player's own stat, since role is recorded per map",
                            suggestions=["Try e.g. `tank with the most eliminations` or `KSAA eliminations as tank`."])

    # --- combinations the compiler supports
    stat_key = None if q.metric in DERIVED_METRICS else q.metric
    if q.intent in ("leaderboard", "entity_stat") and q.entity == "player" and stat_key and (map_name or mode_name or f.team or f.region or f.role):
        if stat_key not in TYPED_STATS:
            reason = (f"'{stat_key}' can only be sliced by season or tournament, not by map, mode, team or region "
                      f"(only these stats support that: {', '.join(TYPED_STATS)})")
            if f.role:
                reason = (f"'{stat_key}' can only be filtered by role for these stats: {', '.join(TYPED_STATS)} "
                          "(role is per map, so it needs a stat that is tracked per map)")
            return Unanswerable(code="unsupported_metric", reason=reason)
    if q.intent == "season_compare" and f.subject_season == f.opponent_season:
        return Unanswerable(code="invalid_query", reason="both sides name the same season, so there is nothing to compare")
    if q.intent == "head_to_head" and (map_name or mode_name):
        return Unanswerable(code="unsupported_question", reason="head-to-head is tracked per series, not per map; drop the map/mode filter")
    if q.intent == "stat_availability" and (f.map or f.mode or f.championship or f.role):
        notes.append("stat availability is reported per season; map/mode/tournament/role filters ignored")

    # --- capability: does any source give this slice what the question needs? Asked before the season's stat
    # coverage: a slice that can carry no player stats at all (a Liquipedia-only event) refuses for that reason,
    # not because its season happens to lack this one stat elsewhere ("final blows at EWC 2024": 2024's FACEIT
    # payloads carry 9 keys, but EWC 2024 carries none).
    cap, parts = capability(q, info, champ_ids)

    # --- metric availability in the requested season slice
    if cap != "none" and stat_key and f.season is not None and f.season not in info.stat_keys.get(stat_key, set()):
        with_stat = ", ".join(str(s) for s in sorted(info.stat_keys.get(stat_key, set()))) or "none"
        return Unanswerable(code="no_data", reason=f"'{stat_key}' is not recorded for the {f.season} season (seasons with it: {with_stat})")

    if cap == "none":
        what = "player stats" if needs(q, info) == "player_stats" else "map results"
        where = ", ".join(parts) if parts else "this slice"
        return Unanswerable(code="results_only",
                            reason=f"no source records {what} for {where}: results only, so there is nothing to rank or average",
                            suggestions=["Records, head-to-heads and placings are answerable there; player stats exist only "
                                         "where FACEIT recorded per-map stats."])
    if cap == "partial":
        notes.append("results only for " + ", ".join(parts) + ": no source records "
                     + ("player stats" if needs(q, info) == "player_stats" else "map results")
                     + " there, so that part is not in this answer")

    return Validated(query=q, championship_ids=champ_ids, map_name=map_name, mode_name=mode_name, notes=notes,
                     results_only_parts=parts if cap == "partial" else [], stat_kind=info.stat_kinds.get(stat_key or ""))
