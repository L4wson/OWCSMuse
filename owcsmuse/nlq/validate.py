"""Validate a StructuredQuery against the real schema.

`SchemaInfo` is a snapshot of what actually exists: stat keys per season (from
stat_coverage_season), maps, modes, seasons, championships and regions in
scope. It is loaded from the database in production and constructed by hand in
tests, so validation itself is pure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Optional, Union

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
    championships: dict[str, str] = field(default_factory=dict)    # id -> name (included only)
    regions: set[str] = field(default_factory=set)

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
            cur.execute("SELECT championship_id, name, season FROM championships WHERE include")
            for r in cur.fetchall():
                info.championships[r["championship_id"]] = r["name"]
                if r["season"] is not None:
                    info.seasons.add(r["season"])
        conn.commit()
        return info

    # ---- lookups used by validation and compilation
    def match_map(self, name: str) -> Optional[str]:
        f = fold(name)
        for m in self.maps:
            if fold(m) == f:
                return m
        for m in self.maps:
            if f and f in fold(m):
                return m
        return None

    def match_mode(self, name: str) -> Optional[str]:
        f = fold(name)
        for m in self.modes:
            if fold(m) == f:
                return m
        return None

    def match_championships(self, text: str, season: Optional[int] = None, region: Optional[str] = None) -> list[tuple[str, str]]:
        """All included championships whose name contains every word of `text` (folded)."""
        words = [w for w in fold(text).split() if w not in {"the", "in", "at", "of"}]
        out = []
        for cid, name in self.championships.items():
            fn = fold(name)
            if all(w in fn for w in words):
                if season is not None and str(season) not in fn:
                    continue
                if region == "na" and " na " not in f" {fn} ":
                    continue
                if region == "emea" and "emea" not in fn:
                    continue
                out.append((cid, name))
        return sorted(out, key=lambda x: x[1])


@dataclass
class Validated:
    query: StructuredQuery
    championship_ids: list[str] = field(default_factory=list)   # resolved championship filter (may be several)
    map_name: Optional[str] = None
    mode_name: Optional[str] = None
    notes: list[str] = field(default_factory=list)


ValidationResult = Union[Validated, Unanswerable]


def validate(q: StructuredQuery, info: SchemaInfo) -> ValidationResult:
    notes: list[str] = []
    f = q.filters

    if not info.stat_keys and not info.seasons:
        return Unanswerable(code="no_data",
                            reason="the warehouse has no included, ingested matches yet, so nothing can be answered",
                            suggestions=["Review scope/classification_report.md, then `load-manifest --accept-proposals`, `backfill` and `refresh`."])

    # --- metric
    if q.intent != "stat_availability":
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
            return Unanswerable(code="no_data", reason=f"no included championship matches '{f.championship}'",
                                suggestions=[f"championships in scope: {', '.join(sorted(set(info.championships.values())))[:400]}"])
        champ_ids = [cid for cid, _ in matches]
        if len(matches) > 1:
            notes.append(f"'{f.championship}' matched {len(matches)} championships; results cover all of them: "
                         + "; ".join(n for _, n in matches)[:300])

    # --- combinations the compiler supports
    stat_key = None if q.metric in DERIVED_METRICS else q.metric
    if q.intent in ("leaderboard", "entity_stat") and q.entity == "player" and stat_key and (map_name or mode_name or f.team or f.region):
        if stat_key not in TYPED_STATS:
            return Unanswerable(code="unsupported_metric",
                                reason=f"'{stat_key}' can only be sliced by season or championship, not by map, mode, team or region "
                                       f"(only these stats support that: {', '.join(TYPED_STATS)})")
    if q.intent == "head_to_head" and (map_name or mode_name):
        return Unanswerable(code="unsupported_question", reason="head-to-head is tracked per series, not per map; drop the map/mode filter")
    if q.intent == "stat_availability" and (f.map or f.mode or f.championship):
        notes.append("stat availability is reported per season; map/mode/championship filters ignored")

    # --- metric availability in the requested season slice
    if stat_key and f.season is not None and f.season not in info.stat_keys.get(stat_key, set()):
        with_stat = ", ".join(str(s) for s in sorted(info.stat_keys.get(stat_key, set()))) or "none"
        return Unanswerable(code="no_data", reason=f"'{stat_key}' is not recorded for the {f.season} season (seasons with it: {with_stat})")

    return Validated(query=q, championship_ids=champ_ids, map_name=map_name, mode_name=mode_name, notes=notes)
