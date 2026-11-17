"""Grid's clue types for mixed puzzles: one small typed class each. Still a closed list, not a rules engine.

Every clue answers three questions about itself, from the same fact rows the Phase 0 modules load (`data.py`):

- `outcome(facts).answers`: every player who satisfies it, with one short line saying why
  ("14 maps together on SpaceStation Gaming, 2026 NA Stage 1").
- `outcome(facts).unverifiable`: the players it cannot judge, because the data that would decide is missing, not
  because they fail. Someone in a team's line-up for a series with no map stats may or may not have played.
- what it is: a short `label` for a phone-width header, a one-line `definition` that states its scope, and the
  sentence shown for a guess it cannot check.

A cell is the players who satisfy both of its clues, each on its own evidence (`cell()`), with one exception kept
from the beta: a role beside a season or a region means that role *in* that season or region, on the same maps.

Scope, unless a clue says otherwise: OWCS NA and EMEA main series (stages and playoffs), from FACEIT map stats.
Relegation and international events are not counted. "A map" always means a map FACEIT recorded player stats for.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Optional, Union

from conditions import STATS, per10_rates
from data import ROLES, Appearance, MapRow, Warehouse

MIN_ROLE_MAPS = 10          # the beta's floor for "played the role"
STAT_MIN_MAPS = 20          # maps in the role, in the season, before a per-10 rate is ranked
STAT_TOP_SHARE = 0.25
MAX_MAPS_A_SERIES = 7       # a best-of-7 at most: the bound on what an unrecorded series could add
SCOPE_REGIONS = ("na", "emea")
DALLAS = "OWCS 2024 Dreamhack Dallas"

ROLE_LABEL = {"Tank": "Tank", "Damage": "DPS", "Support": "Support"}
REGION_LABEL = {"na": "NA", "emea": "EMEA"}
STAGE_NAME = re.compile(r"^OWCS (\d{4}) (NA|EMEA) Stage (\d)")


@dataclass(frozen=True)
class Outcome:
    answers: dict[str, str]                 # player id -> why
    unverifiable: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    season: int
    region: str
    playoff_championships: frozenset[str]
    winner: str                             # org_key
    runner_up: str
    source: str


@dataclass(frozen=True)
class Award:
    player_id: str
    award: str
    event: str
    date: Optional[str]
    source_url: str


def load_stages(path: Path) -> list[Stage]:
    """The stages whose records agree. A stage with a disagreement is no clue's evidence until a person settles it."""
    if not path.exists():
        return []
    return [
        Stage(s["key"], s["name"], s["season"], s["region"], frozenset(s["playoff_championships"]),
              s["winner"]["org_key"], s["runner_up"]["org_key"], s["source"])
        for s in json.loads(path.read_text(encoding="utf-8"))["stages"] if s.get("agree")
    ]


def load_awards(path: Path, include_unreviewed: bool = False) -> list[Award]:
    """Reviewed awards with a resolved player. `include_unreviewed` is for dry runs only."""
    if not path.exists():
        return []
    return [
        Award(a["player_id"], a["award"], a["event"], a.get("date"), a["source_url"])
        for a in json.loads(path.read_text(encoding="utf-8"))["awards"]
        if a.get("player_id") and (a.get("reviewed") or include_unreviewed)
    ]


def series_of(m: MapRow) -> str:
    return f"faceit:{m.match_id}"


def short_competition(name: str) -> str:
    """"OWCS 2026 NA Stage 1 Regular Season" -> "2026 NA Stage 1"."""
    m = STAGE_NAME.match(name)
    return f"{m.group(1)} {m.group(2)} Stage {m.group(3)}" if m else name.removeprefix("OWCS ")


def years(seasons) -> str:
    seasons = sorted(set(seasons))
    return str(seasons[0]) if len(seasons) == 1 else f"{seasons[0]}-{seasons[-1]}"


def is_mapped(org_key: str) -> bool:
    """A reviewed organisation. `team:<id>` is a team id no org decision covers, standing as itself."""
    return not org_key.startswith("team:")


@dataclass
class Facts:
    """Everything a clue reads. `scoped` is NA and EMEA main series; `full` adds relegation and international."""
    full: Warehouse
    stages: list[Stage] = field(default_factory=list)
    awards: list[Award] = field(default_factory=list)

    @cached_property
    def scoped(self) -> Warehouse:
        keep = {cid for cid, c in self.full.championships.items() if c.tier == "main" and c.region in SCOPE_REGIONS}
        return replace(
            self.full,
            appearances=[a for a in self.full.appearances if a.championship_id in keep],
            map_rows=[m for m in self.full.map_rows if m.championship_id in keep],
            team_series=[], placements=[],
            championships={cid: c for cid, c in self.full.championships.items() if cid in keep},
        )

    @cached_property
    def maps(self) -> list[MapRow]:
        return self.scoped.map_rows

    @cached_property
    def lineups(self) -> list[Appearance]:
        return self.scoped.appearances

    @cached_property
    def main_presence(self) -> set[str]:
        """Everyone in a main-tier line-up anywhere, international events included."""
        main = {cid for cid, c in self.full.championships.items() if c.tier == "main"}
        return {a.player_id for a in self.full.appearances if a.championship_id in main}

    @cached_property
    def maps_by_player(self) -> dict[str, list[MapRow]]:
        out: dict[str, list[MapRow]] = defaultdict(list)
        for m in self.maps:
            out[m.player_id].append(m)
        return out

    @cached_property
    def lineups_by_player(self) -> dict[str, list[Appearance]]:
        out: dict[str, list[Appearance]] = defaultdict(list)
        for a in self.lineups:
            out[a.player_id].append(a)
        return out

    @cached_property
    def recorded_series(self) -> dict[str, set[str]]:
        """player -> the series they have at least one recorded map in."""
        out: dict[str, set[str]] = defaultdict(set)
        for m in self.maps:
            out[m.player_id].add(series_of(m))
        return out

    def unrecorded_series(self, player_id: str, keep=lambda a: True) -> int:
        """Series the player was in the line-up for with no map of theirs on record: what the data cannot see."""
        seen = self.recorded_series.get(player_id, set())
        return len({a.series_id for a in self.lineups_by_player.get(player_id, []) if keep(a) and a.series_id not in seen})

    def name(self, player_id: str) -> str:
        return self.full.player_names.get(player_id) or "(no name)"

    def org(self, org_key: str) -> str:
        return self.full.org_names.get(org_key) or org_key

    def competition(self, championship_id: str) -> str:
        c = self.full.championships.get(championship_id)
        return c.name if c else championship_id


NO_MAP_DATA = "We don't have map data for this player {where}, so this can't be checked."


# ---- role, season, region: the beta's clues, now also usable beside any other ---------------------------------------

@dataclass(frozen=True)
class RoleClue:
    role: str                               # Tank | Damage | Support
    family = "role"
    anchor = None

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")

    @property
    def key(self) -> str:
        return f"role:{ROLE_LABEL[self.role].lower()}"

    @property
    def label(self) -> str:
        return ROLE_LABEL[self.role]

    @property
    def definition(self) -> str:
        return (f"{MIN_ROLE_MAPS}+ maps as {ROLE_LABEL[self.role]} in OWCS NA/EMEA main series (FACEIT map stats). "
                "Beside a season or region, the maps must be in that season or region.")

    cannot_verify = "We don't have role data for this player: their maps are in stages with no map stats."

    def params(self) -> dict:
        return {"type": "role", "role": self.role}

    def outcome(self, f: Facts) -> Outcome:
        n = Counter(m.player_id for m in f.maps if m.role == self.role)
        with_role = {m.player_id for m in f.maps if m.role}
        return Outcome({p: f"{c} {ROLE_LABEL[self.role]} maps" for p, c in n.items() if c >= MIN_ROLE_MAPS},
                       frozenset(f.main_presence - with_role))


@dataclass(frozen=True)
class SeasonClue:
    season: int
    family = "season"
    anchor = None

    @property
    def key(self) -> str:
        return f"season:{self.season}"

    @property
    def label(self) -> str:
        return f"Played in {self.season}"

    @property
    def definition(self) -> str:
        return f"1+ map in OWCS NA/EMEA main series in the {self.season} season (FACEIT map stats)."

    @property
    def cannot_verify(self) -> str:
        return NO_MAP_DATA.format(where=f"in the {self.season} stages they were rostered in")

    def params(self) -> dict:
        return {"type": "season", "season": self.season}

    def on(self, row) -> bool:
        return row.season == self.season

    def outcome(self, f: Facts) -> Outcome:
        n = Counter(m.player_id for m in f.maps if m.season == self.season)
        listed = {a.player_id for a in f.lineups if a.season == self.season}
        return Outcome({p: f"{c} maps in {self.season}" for p, c in n.items()}, frozenset(listed - set(n)))


@dataclass(frozen=True)
class AllSeasonsClue:
    family = "season"
    anchor = None
    key = "season:all3"
    label = "Played all 3 seasons"
    definition = "1+ map in OWCS NA/EMEA main series in each of 2024, 2025 and 2026 (FACEIT map stats)."
    cannot_verify = NO_MAP_DATA.format(where="in one of the seasons they were rostered in")

    def params(self) -> dict:
        return {"type": "all_seasons"}

    def outcome(self, f: Facts) -> Outcome:
        played: dict[str, Counter] = defaultdict(Counter)
        for m in f.maps:
            played[m.player_id][m.season] += 1
        listed: dict[str, set[int]] = defaultdict(set)
        for a in f.lineups:
            listed[a.player_id].add(a.season)
        answers = {p: f"{sum(c.values())} maps across 2024, 2025 and 2026" for p, c in played.items() if len(c) == 3}
        maybe = {p for p, s in listed.items() if len(s) == 3} - set(answers)
        return Outcome(answers, frozenset(maybe))


@dataclass(frozen=True)
class RegionClue:
    region: str                             # na | emea: where the competition was, not where the player is from
    family = "region"
    anchor = None

    def __post_init__(self):
        if self.region not in SCOPE_REGIONS:
            raise ValueError(f"unknown region {self.region!r}")

    @property
    def key(self) -> str:
        return f"region:{self.region}"

    @property
    def label(self) -> str:
        return f"Played in {REGION_LABEL[self.region]}"

    @property
    def definition(self) -> str:
        return f"1+ map in an OWCS {REGION_LABEL[self.region]} main-series competition (FACEIT map stats)."

    @property
    def cannot_verify(self) -> str:
        return NO_MAP_DATA.format(where=f"in the {REGION_LABEL[self.region]} stages they were rostered in")

    def params(self) -> dict:
        return {"type": "region", "region": self.region}

    def on(self, row) -> bool:
        return row.region == self.region

    def outcome(self, f: Facts) -> Outcome:
        n = Counter(m.player_id for m in f.maps if m.region == self.region)
        listed = {a.player_id for a in f.lineups if a.region == self.region}
        return Outcome({p: f"{c} maps in {REGION_LABEL[self.region]}" for p, c in n.items()}, frozenset(listed - set(n)))


@dataclass(frozen=True)
class BothRegionsClue:
    family = "region"
    anchor = None
    key = "region:both"
    label = "Played in NA and EMEA"
    definition = "1+ map in an OWCS NA competition and 1+ in an OWCS EMEA one, main series (FACEIT map stats)."
    cannot_verify = NO_MAP_DATA.format(where="in one of the regions they were rostered in")

    def params(self) -> dict:
        return {"type": "both_regions"}

    def outcome(self, f: Facts) -> Outcome:
        played: dict[str, Counter] = defaultdict(Counter)
        for m in f.maps:
            played[m.player_id][m.region] += 1
        listed: dict[str, set[str]] = defaultdict(set)
        for a in f.lineups:
            listed[a.player_id].add(a.region)
        answers = {p: f"{c['na']} maps in NA, {c['emea']} in EMEA" for p, c in played.items() if c["na"] and c["emea"]}
        maybe = {p for p, r in listed.items() if len(r) == 2} - set(answers)
        return Outcome(answers, frozenset(maybe))


# ---- teammates and teams ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class TeammateClue:
    player_id: str
    name: str                               # a label only; the id decides
    family = "teammate"

    @property
    def anchor(self) -> str:
        return self.player_id

    @property
    def key(self) -> str:
        return f"teammate:{self.player_id}"

    @property
    def label(self) -> str:
        return f"Teammate of {self.name}"

    @property
    def definition(self) -> str:
        return (f"Played 1+ map on the same team as {self.name} in OWCS NA/EMEA main series (FACEIT map stats). "
                f"{self.name} is not an answer.")

    @property
    def cannot_verify(self) -> str:
        return (f"They were rostered with {self.name} only in series we have no map data for, "
                "so we can't tell whether they played together.")

    def params(self) -> dict:
        return {"type": "teammate", "player_id": self.player_id}

    def outcome(self, f: Facts) -> Outcome:
        # the anchor's maps, as (match, map number, the team they were on for it)
        mine = {(m.match_id, m.round_number, m.org_key) for m in f.maps_by_player.get(self.player_id, [])}
        shared: dict[str, Counter] = defaultdict(Counter)
        for m in f.maps:
            if m.player_id != self.player_id and (m.match_id, m.round_number, m.org_key) in mine:
                shared[m.player_id][(m.org_key, short_competition(f.competition(m.championship_id)))] += 1
        answers = {}
        for player, where in shared.items():
            total = sum(where.values())
            (org_key, stage), most = where.most_common(1)[0]
            if most == total:
                answers[player] = f"{total} map{'s' if total != 1 else ''} together on {f.org(org_key)}, {stage}"
            else:
                answers[player] = f"{total} maps together, most on {f.org(org_key)} in {stage}"
        # the same side of the same series, with no map together on record
        sides = {(a.series_id, a.org_key) for a in f.lineups_by_player.get(self.player_id, [])}
        listed = {a.player_id for a in f.lineups if (a.series_id, a.org_key) in sides}
        return Outcome(answers, frozenset(listed - set(answers) - {self.player_id}))


@dataclass(frozen=True)
class OrgClue:
    org_key: str
    name: str
    family = "org"
    anchor = None

    def __post_init__(self):
        if not is_mapped(self.org_key):
            raise ValueError(f"{self.org_key} is a team id no org decision covers: only a mapped org can be a clue")

    @property
    def key(self) -> str:
        return f"org:{self.org_key}"

    @property
    def label(self) -> str:
        return f"Played for {self.name}"

    @property
    def definition(self) -> str:
        return (f"Played 1+ map for {self.name} in OWCS NA/EMEA main series (FACEIT map stats). The team is the "
                "organisation as reviewed in OWCS Muse, at the time of each map.")

    @property
    def cannot_verify(self) -> str:
        return f"They were rostered for {self.name} only in series we have no map data for."

    def params(self) -> dict:
        return {"type": "org", "org_key": self.org_key}

    def outcome(self, f: Facts) -> Outcome:
        n: Counter = Counter()
        seasons: dict[str, set[int]] = defaultdict(set)
        for m in f.maps:
            if m.org_key == self.org_key:
                n[m.player_id] += 1
                seasons[m.player_id].add(m.season)
        listed = {a.player_id for a in f.lineups if a.org_key == self.org_key}
        return Outcome({p: f"{c} maps for {self.name}, {years(seasons[p])}" for p, c in n.items()},
                       frozenset(listed - set(n)))


@dataclass(frozen=True)
class OrgCountClue:
    n: int
    family = "org"
    anchor = None

    @property
    def key(self) -> str:
        return f"orgs:{self.n}"

    @property
    def label(self) -> str:
        return f"Played for {self.n}+ orgs"

    @property
    def definition(self) -> str:
        return (f"Played 1+ map for each of {self.n} or more reviewed organisations in OWCS NA/EMEA main series. "
                "A team not yet mapped to an organisation is not counted.")

    cannot_verify = ("Some of their teams are not mapped to an organisation yet, or have no map data, "
                     "so we can't count their orgs.")

    def params(self) -> dict:
        return {"type": "org_count", "n": self.n}

    def outcome(self, f: Facts) -> Outcome:
        played: dict[str, set[str]] = defaultdict(set)
        for m in f.maps:
            if is_mapped(m.org_key):
                played[m.player_id].add(m.org_key)
        listed: dict[str, set[str]] = defaultdict(set)         # mapped orgs by line-up, and any unmapped team at all
        unmapped: set[str] = set()
        for a in f.lineups:
            if is_mapped(a.org_key):
                listed[a.player_id].add(a.org_key)
            else:
                unmapped.add(a.player_id)
        answers = {
            p: f"{len(orgs)} orgs: " + ", ".join(sorted(f.org(k) for k in orgs))
            for p, orgs in played.items() if len(orgs) >= self.n
        }
        # not provably short: an unmapped stint could be one more org, and a line-up-only stint could be a played one
        maybe = unmapped | {p for p, orgs in listed.items() if len(orgs) >= self.n}
        return Outcome(answers, frozenset(maybe - set(answers)))


# ---- stages, awards, international events -----------------------------------------------------------------------

def _stage_players(f: Facts, stages: list[Stage], finalists: bool) -> Outcome:
    """Players with 1+ playoff map for a stage's champion (or either finalist), and those only rostered there."""
    teams = {(cid, org) for s in stages for cid in s.playoff_championships
             for org in ((s.winner, s.runner_up) if finalists else (s.winner,))}
    stage_of = {cid: s for s in stages for cid in s.playoff_championships}
    maps: dict[str, Counter] = defaultdict(Counter)
    for m in f.maps:
        if (m.championship_id, m.org_key) in teams:
            maps[m.player_id][(stage_of[m.championship_id].key, m.org_key)] += 1
    answers = {}
    for player, where in maps.items():
        (stage_key, org_key), n = sorted(where.items(), key=lambda kv: (kv[0][0], kv[0][1]))[0]
        stage = next(s for s in stages if s.key == stage_key)
        verb = "Won" if org_key == stage.winner else "Runner-up in"
        more = f", and {len(where) - 1} more" if len(where) > 1 else ""
        answers[player] = f"{verb} {short_competition(stage.name)} with {f.org(org_key)} ({n} playoff maps){more}"
    listed = {a.player_id for a in f.lineups if (a.championship_id, a.org_key) in teams}
    return Outcome(answers, frozenset(listed - set(answers)))


@dataclass(frozen=True)
class StageWinClue:
    region: Optional[str] = None            # None: either region
    family = "stage"
    anchor = None

    @property
    def key(self) -> str:
        return f"stage_win:{self.region or 'any'}"

    @property
    def label(self) -> str:
        return f"Won an {REGION_LABEL[self.region]} stage" if self.region else "Won an OWCS stage"

    @property
    def definition(self) -> str:
        where = f"OWCS {REGION_LABEL[self.region]}" if self.region else "OWCS NA or EMEA"
        return f"Played 1+ playoff map for the team that won an {where} stage's playoffs (FACEIT map stats)."

    cannot_verify = ("They were on a stage winner's playoff roster, but we have no map data for those playoffs, "
                     "so we can't tell whether they played.")

    def params(self) -> dict:
        return {"type": "stage_win", "region": self.region}

    def outcome(self, f: Facts) -> Outcome:
        return _stage_players(f, [s for s in f.stages if self.region in (None, s.region)], finalists=False)


@dataclass(frozen=True)
class StageFinalClue:
    region: Optional[str] = None
    family = "stage"
    anchor = None

    @property
    def key(self) -> str:
        return f"stage_final:{self.region or 'any'}"

    @property
    def label(self) -> str:
        return f"{REGION_LABEL[self.region]} stage finalist" if self.region else "Stage grand finalist"

    @property
    def definition(self) -> str:
        where = f"OWCS {REGION_LABEL[self.region]}" if self.region else "OWCS NA or EMEA"
        return (f"Played 1+ playoff map for a team that reached an {where} stage's grand final, win or lose "
                "(FACEIT map stats).")

    cannot_verify = ("They were on a stage finalist's playoff roster, but we have no map data for those playoffs, "
                     "so we can't tell whether they played.")

    def params(self) -> dict:
        return {"type": "stage_final", "region": self.region}

    def outcome(self, f: Facts) -> Outcome:
        return _stage_players(f, [s for s in f.stages if self.region in (None, s.region)], finalists=True)


@dataclass(frozen=True)
class AwardClue:
    family = "award"
    anchor = None
    key = "award:any"
    label = "Won an OWCS award"
    definition = "Named for an individual award (MVP, Super Star) at an OWCS event, per Liquipedia. Reviewed awards only."
    cannot_verify = "We can't check this."

    def params(self) -> dict:
        return {"type": "award"}

    def outcome(self, f: Facts) -> Outcome:
        won: dict[str, list[Award]] = defaultdict(list)
        for a in f.awards:
            won[a.player_id].append(a)
        answers = {}
        for player, awards in won.items():
            first = sorted(awards, key=lambda a: (a.date or "", a.award))[0]
            more = f", and {len(awards) - 1} more" if len(awards) > 1 else ""
            answers[player] = f"{first.award}, {first.event}{more}"
        return Outcome(answers)


@dataclass(frozen=True)
class LanClue:
    championship_id: Optional[str] = None   # None: any international event held
    name: str = ""
    family = "lan"
    anchor = None

    @property
    def key(self) -> str:
        return f"lan:{self.championship_id or 'any'}"

    @property
    def label(self) -> str:
        return f"Rostered at {self.name}" if self.championship_id else "Rostered at an international LAN"

    @property
    def definition(self) -> str:
        what = self.name if self.championship_id else "an OWCS international event (World Finals, Midseason Championship, Champions Clash, EWC 2024)"
        return (f"On a team's roster at {what}, per Liquipedia's line-ups. Rostered, not necessarily played. "
                "Dreamhack Dallas 2024 is not counted: its line-ups are incomplete.")

    cannot_verify = "They were at Dreamhack Dallas 2024, whose line-ups we hold incompletely, so we can't count it."

    def params(self) -> dict:
        return {"type": "lan", "championship_id": self.championship_id}

    def outcome(self, f: Facts) -> Outcome:
        events = {cid: c for cid, c in f.full.championships.items() if c.region == "international" and c.tier == "main"}
        dallas = {cid for cid, c in events.items() if c.name == DALLAS}
        if self.championship_id is not None and (self.championship_id not in events or self.championship_id in dallas):
            raise ValueError(f"{self.championship_id} is not an international event a roster clue can use")
        wanted = {self.championship_id} if self.championship_id else set(events) - dallas
        at: dict[str, list[Appearance]] = defaultdict(list)
        for a in f.full.appearances:
            if a.championship_id in wanted:
                at[a.player_id].append(a)
        answers = {}
        for player, rows in at.items():
            first = sorted(rows, key=lambda a: a.played_at)[0]
            n = len({a.championship_id for a in rows})
            more = f", and {n - 1} more" if n > 1 else ""
            answers[player] = f"On {f.org(first.org_key)}'s roster at {f.competition(first.championship_id).removeprefix('OWCS ')}{more}"
        at_dallas = set() if self.championship_id else {a.player_id for a in f.full.appearances if a.championship_id in dallas}
        return Outcome(answers, frozenset(at_dallas - set(answers)))


# ---- experience and stats ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ExperienceClue:
    n: int
    family = "experience"
    anchor = None

    @property
    def key(self) -> str:
        return f"maps:{self.n}"

    @property
    def label(self) -> str:
        return f"{self.n}+ OWCS maps"

    @property
    def definition(self) -> str:
        return f"{self.n} or more maps played in OWCS NA/EMEA main series, 2024-2026 (FACEIT map stats)."

    @property
    def cannot_verify(self) -> str:
        return (f"They are under {self.n} maps on record, but played series we have no map data for, "
                "which could take them past it.")

    def params(self) -> dict:
        return {"type": "experience", "n": self.n}

    def outcome(self, f: Facts) -> Outcome:
        n = Counter(m.player_id for m in f.maps)
        answers = {p: f"{c} OWCS maps" for p, c in n.items() if c >= self.n}
        maybe = {p for p in f.lineups_by_player
                 if p not in answers and n[p] + MAX_MAPS_A_SERIES * f.unrecorded_series(p) >= self.n}
        return Outcome(answers, frozenset(maybe))


STAT_WORDS = {"eliminations": "elims", "damage_dealt": "damage", "deaths": "deaths"}


@dataclass(frozen=True)
class StatClue:
    stat: str                               # eliminations | damage_dealt | deaths
    season: int
    family = "stats"
    anchor = None

    def __post_init__(self):
        if self.stat not in STAT_WORDS:
            raise ValueError(f"unknown stat {self.stat!r}; one of {sorted(STAT_WORDS)}")

    @property
    def lowest(self) -> bool:
        return self.stat == "deaths"         # fewer deaths is better: the top quarter is the lowest rates

    @property
    def key(self) -> str:
        return f"stat:{self.stat}:{self.season}"

    @property
    def label(self) -> str:
        what = "fewest deaths" if self.lowest else STAT_WORDS[self.stat]
        return f"Top 25% {what}/10, {self.season} NA/EMEA"

    @property
    def definition(self) -> str:
        which = "lowest" if self.lowest else "highest"
        return (f"In the {which} 25% for {STATS[self.stat].lower()} per 10 minutes among players of the same role, "
                f"{self.season} season, OWCS NA/EMEA main series. Needs {STAT_MIN_MAPS}+ maps in that role that "
                "season. The rate is total over total time played.")

    @property
    def cannot_verify(self) -> str:
        return (f"They have under {STAT_MIN_MAPS} maps in a role on record for {self.season}, and played series "
                "we have no map data for, so they can't be ranked.")

    def params(self) -> dict:
        return {"type": "stat", "stat": self.stat, "season": self.season}

    def ranked(self, f: Facts, role: str) -> list[tuple[str, float, int]]:
        """(player, rate, maps), best first, for everyone with enough maps in the role that season."""
        try:
            rates = per10_rates(f.scoped, self.stat, self.season, role, STAT_MIN_MAPS)
        except ValueError:
            return []       # nobody played this role with Time Played that season; outcome() refuses if no role has any
        return sorted(((p, rate, maps) for p, (rate, maps) in rates.items()),
                      key=lambda x: (x[1] if self.lowest else -x[1], x[0]))

    def outcome(self, f: Facts) -> Outcome:
        answers: dict[str, str] = {}
        eligible: set[str] = set()
        any_ranked = False
        for role in ROLES:
            ranked = self.ranked(f, role)
            eligible |= {p for p, _, _ in ranked}
            if not ranked:
                continue
            any_ranked = True
            take = math.ceil(len(ranked) * STAT_TOP_SHARE)
            cutoff = ranked[take - 1][1]
            for rank, (player, rate, _maps) in enumerate(ranked, start=1):
                if (rate <= cutoff) if self.lowest else (rate >= cutoff):      # a tie at the cutoff is in
                    line = (f"{rate:.1f} {STAT_WORDS[self.stat]}/10 as {ROLE_LABEL[role]} in {self.season}, "
                            f"#{rank} of {len(ranked)}")
                    answers.setdefault(player, line)
        if not any_ranked:
            # 2024 has no Time Played at all: a per-10 clue for it is refused, never answered with nobody
            raise ValueError(f"no player has {STAT_MIN_MAPS}+ maps with Time Played in a role in {self.season}: "
                             "a per-10 clue cannot be stated for it")
        in_season = lambda a: a.season == self.season  # noqa: E731
        maybe = {p for p in f.lineups_by_player
                 if p not in eligible and any(in_season(a) for a in f.lineups_by_player[p])
                 and f.unrecorded_series(p, in_season) > 0}
        return Outcome(answers, frozenset(maybe - set(answers)))


Clue = Union[RoleClue, SeasonClue, AllSeasonsClue, RegionClue, BothRegionsClue, TeammateClue, OrgClue, OrgCountClue,
             StageWinClue, StageFinalClue, AwardClue, LanClue, ExperienceClue, StatClue]


# ---- a cell -----------------------------------------------------------------------------------------------------

def _role_in_scope(f: Facts, role: RoleClue, scope: Union[SeasonClue, RegionClue]) -> Outcome:
    """A role beside a season or a region: 10+ maps in that role in that season or region, as in the beta."""
    n = Counter(m.player_id for m in f.maps if m.role == role.role and scope.on(m))
    what = scope.season if isinstance(scope, SeasonClue) else REGION_LABEL[scope.region]
    answers = {p: f"{c} {ROLE_LABEL[role.role]} maps in {what}" for p, c in n.items() if c >= MIN_ROLE_MAPS}
    # seen in that season or region (for a season, at an international event too) with no role on record there
    main = {cid for cid, c in f.full.championships.items() if c.tier == "main"}
    seen = {a.player_id for a in f.full.appearances if a.championship_id in main and scope.on(a)}
    with_role = {m.player_id for m in f.maps if m.role and scope.on(m)}
    return Outcome(answers, frozenset(seen - with_role))


@dataclass(frozen=True)
class CellOutcome:
    answers: dict[str, str]
    unverifiable: dict[str, str]            # player id -> "row" | "col": whose data is missing


def cell(f: Facts, row: Clue, col: Clue, outcomes: Optional[dict[str, Outcome]] = None) -> CellOutcome:
    """The players who fit both clues, and the ones the cell cannot judge.

    A player is unverifiable for the cell when neither clue rules them out and at least one cannot judge them. A
    player one clue plainly fails is wrong, however little is known about the other.
    """
    pair = {type(row), type(col)}
    if RoleClue in pair and pair & {SeasonClue, RegionClue}:
        role, scope = (row, col) if isinstance(row, RoleClue) else (col, row)
        together = _role_in_scope(f, role, scope)
        side = "row" if isinstance(row, RoleClue) else "col"
        return CellOutcome(dict(together.answers), {p: side for p in together.unverifiable})

    def of(clue: Clue) -> Outcome:
        if outcomes is not None:
            if clue.key not in outcomes:
                outcomes[clue.key] = clue.outcome(f)
            return outcomes[clue.key]
        return clue.outcome(f)

    a, b = of(row), of(col)
    answers = {p: f"{a.answers[p]}. {b.answers[p]}" for p in a.answers.keys() & b.answers.keys()}
    possible_a = a.answers.keys() | a.unverifiable
    possible_b = b.answers.keys() | b.unverifiable
    unverifiable = {}
    for p in (possible_a & possible_b) - answers.keys():
        unverifiable[p] = "row" if p in a.unverifiable else "col"
    return CellOutcome(answers, unverifiable)


def from_params(f: Facts, params: dict) -> Clue:
    """Rebuild a clue from the typed params stored with a puzzle."""
    kind = params["type"]
    if kind == "role":
        return RoleClue(params["role"])
    if kind == "season":
        return SeasonClue(params["season"])
    if kind == "all_seasons":
        return AllSeasonsClue()
    if kind == "region":
        return RegionClue(params["region"])
    if kind == "both_regions":
        return BothRegionsClue()
    if kind == "teammate":
        return TeammateClue(params["player_id"], f.name(params["player_id"]))
    if kind == "org":
        return OrgClue(params["org_key"], f.org(params["org_key"]))
    if kind == "org_count":
        return OrgCountClue(params["n"])
    if kind == "stage_win":
        return StageWinClue(params.get("region"))
    if kind == "stage_final":
        return StageFinalClue(params.get("region"))
    if kind == "award":
        return AwardClue()
    if kind == "lan":
        cid = params.get("championship_id")
        return LanClue(cid, f.competition(cid).removeprefix("OWCS ") if cid else "")
    if kind == "experience":
        return ExperienceClue(params["n"])
    if kind == "stat":
        return StatClue(params["stat"], params["season"])
    raise ValueError(f"unknown clue type {kind!r}")
