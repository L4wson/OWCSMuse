"""Grid conditions: a small, closed set of typed classes. This is deliberately not a rules engine.

Two kinds:

- A **row condition** (`Season`, `Region`, `Org`, `Event`, `Role`) is a test on one fact row: one series a player
  appeared in, one map a player played, one series a team played. Two row conditions of *different* dimensions in a
  cell are applied to the **same row**: "Tank x 2024" is a player with maps played as Tank in 2024, not a player who
  was a Tank at some point and also competed in 2024. Two row conditions of the *same* dimension ("played for A" x
  "played for B", or a region x an event, which are both where a series was played) cannot usefully hold on one
  row, so each is satisfied on its own rows.
- A **set condition** (`MinOrgs`, `MinSeasons`, `Per10`, `TopPer10`, `PlacedTop`, `Beat`) states its own scope and
  yields a set of ids. In a cell it is intersected with the other side.

`Role` and the stat conditions read map rows (FACEIT `/stats`), so a cell that uses one is counted at map grain and
takes the min-maps threshold. Every other player cell is counted at series grain, from line-ups.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal, Union

from data import ROLES, Appearance, Championship, MapRow, TeamSeries, Warehouse

Entity = Literal["player", "team"]
FactRow = Union[Appearance, MapRow, TeamSeries]

STATS = {
    "eliminations": "Eliminations",
    "deaths": "Deaths",
    "damage_dealt": "Damage",
    "healing_done": "Healing",
    "damage_mitigated": "Mitigation",
}


# ---- row conditions ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Season:
    season: int
    dimension = "season"
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Competed in {self.season}"

    def on_row(self, row: FactRow) -> bool:
        return row.season == self.season

    def covers(self, c: Championship) -> bool:
        return c.season == self.season


@dataclass(frozen=True)
class Region:
    region: str             # 'na' | 'emea' | 'international': the region of the competition, not of the player or team
    dimension = "competition"
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Played in {self.region.upper() if self.region != 'international' else 'an international event'}"

    def on_row(self, row: FactRow) -> bool:
        return row.region == self.region

    def covers(self, c: Championship) -> bool:
        return c.region == self.region


@dataclass(frozen=True)
class Org:
    org_key: str            # an org id, or team:<id>; the name is only ever a label
    name: str
    dimension = "org"
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Played for {self.name}"

    def on_row(self, row: FactRow) -> bool:
        return row.org_key == self.org_key

    def covers(self, c: Championship) -> bool:
        return True


@dataclass(frozen=True)
class Event:
    championship_ids: frozenset[str]
    name: str
    dimension = "competition"   # the same dimension as Region: an event has one region, so the two never share a row
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Competed at {self.name}"

    def on_row(self, row: FactRow) -> bool:
        return row.championship_id in self.championship_ids

    def covers(self, c: Championship) -> bool:
        return c.championship_id in self.championship_ids


@dataclass(frozen=True)
class Role:
    role: str               # FACEIT's value on the map row: Tank | Damage | Support
    dimension = "role"
    needs_maps = True

    @property
    def label(self) -> str:
        return {"Damage": "Played DPS"}.get(self.role, f"Played {self.role}")

    def on_row(self, row: FactRow) -> bool:
        return isinstance(row, MapRow) and row.role == self.role

    def covers(self, c: Championship) -> bool:
        return True


RowCondition = Union[Season, Region, Org, Event, Role]


# ---- set conditions: players ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class MinOrgs:
    n: int
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Played for {self.n}+ teams"

    def answers(self, wh: Warehouse, min_maps: int, min_series: int) -> set[str]:
        orgs: dict[str, set[str]] = defaultdict(set)
        for a in wh.appearances:
            orgs[a.player_id].add(a.org_key)
        return {p for p, keys in orgs.items() if len(keys) >= self.n}


@dataclass(frozen=True)
class MinSeasons:
    n: int
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Competed in {self.n}+ seasons"

    def answers(self, wh: Warehouse, min_maps: int, min_series: int) -> set[str]:
        seasons: dict[str, set[int]] = defaultdict(set)
        for a in wh.appearances:
            seasons[a.player_id].add(a.season)
        return {p for p, s in seasons.items() if len(s) >= self.n}


def per10_rates(wh: Warehouse, stat: str, season: int, role: str, min_maps: int) -> dict[str, tuple[float, int]]:
    """player -> (stat per 10 minutes, maps counted), for maps played in `role` in `season`.

    The rate is recomputed from its components, total stat over total time played, never an average of per-map
    rates. A map counts only when it carries both the stat and Time Played. A season with no Time Played at all
    (2024) is refused, not answered with whoever happens to have a value.
    """
    if stat not in STATS:
        raise ValueError(f"unknown stat {stat!r}; one of {sorted(STATS)}")
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; one of {ROLES}")
    total: dict[str, float] = defaultdict(float)
    seconds: dict[str, float] = defaultdict(float)
    maps: dict[str, int] = defaultdict(int)
    for m in wh.map_rows:
        if m.season != season or m.role != role:
            continue
        value = getattr(m, stat)
        if value is None or not m.time_played:
            continue
        total[m.player_id] += float(value)
        seconds[m.player_id] += m.time_played
        maps[m.player_id] += 1
    if not maps:
        raise ValueError(f"{season} has no maps with both {STATS[stat]} and Time Played for {role}: "
                         "a per-10 condition cannot be stated for it")
    return {p: (total[p] / seconds[p] * 600.0, maps[p]) for p in maps if maps[p] >= min_maps}


@dataclass(frozen=True)
class Per10:
    stat: str
    op: Literal[">=", "<="]
    threshold: float
    season: int
    role: str
    needs_maps = True

    @property
    def label(self) -> str:
        return f"{STATS[self.stat]} per 10 {self.op} {self.threshold:g} as {self.role} in {self.season}"

    def answers(self, wh: Warehouse, min_maps: int, min_series: int) -> set[str]:
        rates = per10_rates(wh, self.stat, self.season, self.role, min_maps)
        if self.op == ">=":
            return {p for p, (rate, _) in rates.items() if rate >= self.threshold}
        return {p for p, (rate, _) in rates.items() if rate <= self.threshold}


@dataclass(frozen=True)
class TopPer10:
    stat: str
    n: int
    season: int
    role: str
    needs_maps = True

    @property
    def label(self) -> str:
        return f"Top {self.n} {STATS[self.stat]} per 10 among {self.role} players in {self.season}"

    def answers(self, wh: Warehouse, min_maps: int, min_series: int) -> set[str]:
        rates = per10_rates(wh, self.stat, self.season, self.role, min_maps)
        ranked = sorted(rates.items(), key=lambda kv: (-kv[1][0], kv[0]))
        if len(ranked) <= self.n:
            return {p for p, _ in ranked}
        cutoff = ranked[self.n - 1][1][0]
        return {p for p, (rate, _) in ranked if rate >= cutoff}       # a tie at the cutoff is in, not broken by id


# ---- set conditions: teams --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PlacedTop:
    n: int
    season: int | None = None
    needs_maps = False

    @property
    def label(self) -> str:
        what = "Won" if self.n == 1 else f"Finished top {self.n} at"
        when = f" in {self.season}" if self.season else ""
        return f"{what} an international event{when}"

    def answers(self, wh: Warehouse, min_maps: int, min_series: int) -> set[str]:
        # place_low is the worst position of a shared range: "3-4" is top 4, not top 3
        return {p.org_key for p in wh.placements
                if p.place_low <= self.n and (self.season is None or p.season == self.season)}


@dataclass(frozen=True)
class Beat:
    org_key: str
    name: str
    needs_maps = False

    @property
    def label(self) -> str:
        return f"Beat {self.name} in a series"

    def answers(self, wh: Warehouse, min_maps: int, min_series: int) -> set[str]:
        return {t.org_key for t in wh.team_series if t.won and t.opponent_org_key == self.org_key}


SetCondition = Union[MinOrgs, MinSeasons, Per10, TopPer10, PlacedTop, Beat]
Condition = Union[RowCondition, SetCondition]
ROW_TYPES = (Season, Region, Org, Event, Role)
PLAYER_ONLY = (Org, Role, MinOrgs, MinSeasons, Per10, TopPer10)
TEAM_ONLY = (PlacedTop, Beat)


# ---- evaluation -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class CellAnswers:
    ids: frozenset[str]
    grain: str              # how the cell was counted, with its threshold
    correlated: bool        # True when both conditions were applied to the same fact rows


def _row_answers(wh: Warehouse, entity: Entity, conds: tuple[RowCondition, ...], min_maps: int, min_series: int
                 ) -> tuple[set[str], str]:
    """The entities with enough fact rows on which every condition in `conds` holds together."""
    if entity == "team":
        series: dict[str, set[str]] = defaultdict(set)
        for t in wh.team_series:
            if all(c.on_row(t) for c in conds):
                series[t.org_key].add(t.series_id)
        return {k for k, s in series.items() if len(s) >= min_series}, f"series (>= {min_series})"
    if any(c.needs_maps for c in conds):
        maps: dict[str, int] = defaultdict(int)
        for m in wh.map_rows:
            if all(c.on_row(m) for c in conds):
                maps[m.player_id] += 1
        return {p for p, n in maps.items() if n >= min_maps}, f"maps with FACEIT stats (>= {min_maps})"
    seen: dict[str, set[str]] = defaultdict(set)
    for a in wh.appearances:
        if all(c.on_row(a) for c in conds):
            seen[a.player_id].add(a.series_id)
    return {p for p, s in seen.items() if len(s) >= min_series}, f"series line-ups (>= {min_series})"


def _alone(wh: Warehouse, entity: Entity, cond: Condition, min_maps: int, min_series: int) -> tuple[set[str], str]:
    if isinstance(cond, ROW_TYPES):
        return _row_answers(wh, entity, (cond,), min_maps, min_series)
    grain = f"maps with FACEIT stats (>= {min_maps})" if cond.needs_maps else "stated by the condition"
    return cond.answers(wh, min_maps, min_series), grain


def check_entity(entity: Entity, cond: Condition) -> None:
    if entity == "team" and isinstance(cond, PLAYER_ONLY):
        raise ValueError(f"{type(cond).__name__} is a player condition; this grid's answers are teams")
    if entity == "player" and isinstance(cond, TEAM_ONLY):
        raise ValueError(f"{type(cond).__name__} is a team condition; this grid's answers are players")


def cell_answers(wh: Warehouse, entity: Entity, row: Condition, col: Condition, min_maps: int, min_series: int
                 ) -> CellAnswers:
    """The canonical ids that satisfy both conditions of one cell."""
    both_rows = isinstance(row, ROW_TYPES) and isinstance(col, ROW_TYPES)
    if both_rows and row.dimension != col.dimension:
        ids, grain = _row_answers(wh, entity, (row, col), min_maps, min_series)
        return CellAnswers(frozenset(ids), grain, correlated=True)
    a, grain_a = _alone(wh, entity, row, min_maps, min_series)
    b, grain_b = _alone(wh, entity, col, min_maps, min_series)
    grain = grain_a if grain_a == grain_b else f"{grain_a} x {grain_b}"
    return CellAnswers(frozenset(a & b), grain, correlated=False)


def stats_coverage(wh: Warehouse, row: Condition, col: Condition) -> str | None:
    """For a map-grain cell: how much of the slice the conditions name has player stats at all.

    A role or stat cell can only see competitions FACEIT recorded map stats for. This says which part of the slice
    that is, so a count is never read as covering competitions it cannot see.
    """
    if not (row.needs_maps or col.needs_maps):
        return None
    scoping = [c for c in (row, col) if isinstance(c, (Season, Region, Event))]
    for c in (row, col):
        if isinstance(c, (Per10, TopPer10)):
            scoping.append(Season(c.season))
    in_slice = [c for c in wh.championships.values() if all(s.covers(c) for s in scoping)]
    without = sorted(c.name for c in in_slice if not c.player_stats)
    if not in_slice:
        return "no competition in scope matches this slice"
    line = f"player stats in {len(in_slice) - len(without)} of {len(in_slice)} competitions of this slice"
    if without:
        shown = ", ".join(without[:4]) + (f", and {len(without) - 4} more" if len(without) > 4 else "")
        line += f"; none for: {shown}"
    return line
