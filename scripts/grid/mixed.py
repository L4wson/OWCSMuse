"""Mixed-clue puzzles: the pool of clues, the quality rules a grid must pass, and the day-by-day generation.

A puzzle is six clues from `clues.py`, three as rows and three as columns, from at least four families. The rules
below are the whole definition of a publishable grid; `judge()` applies them and names each one a grid fails.

Roughly one day in eight is a role grid (Tank / DPS / Support down the side), as in the beta. Difficulty follows the
weekday: easier early in the week, harder at the weekend.
"""

from __future__ import annotations

import itertools
import random
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Optional

from cell_counter import distinct_solution
from clues import (
    DALLAS, AllSeasonsClue, BothRegionsClue, CellOutcome, Clue, ExperienceClue, Facts, LanClue, OrgClue, Outcome,
    RegionClue, RoleClue, SeasonClue, StageFinalClue, StageWinClue, StatClue, TeammateClue, cell, is_mapped,
)
from data import ROLES

MIN_FAMILIES = 4            # of the six clues
MIN_CELL = 3                # answers in every cell
THIN_CELL = 4               # a cell with 3 or 4 answers is thin ...
MAX_THIN_CELLS = 2          # ... and a grid may have at most this many
IMPLIED_SHARE = 0.9         # a cell holding this share of either clue's own answers means one clue implies the other
MAX_CELLS_ONE_PLAYER = 5    # no player may fit more cells than this
CLUE_GAP_DAYS = 7           # a clue is not reused within this many days
ANCHOR_GAP_DAYS = 14        # nor a teammate clue's player within this many
ROLE_GRID_GAP_DAYS = 8      # a role grid uses all three role clues, so it can recur only after the clue gap
OVERLAP_DAYS = 21           # a puzzle may not share ...
MAX_SHARED_CLUES = 2        # ... more than this many of its six clues with any puzzle in that many days before it
MAX_EXPERIENCE_CLUES = 1    # "N+ maps" clues in one puzzle: two of them nest, and one implies the other
MAX_TEAMMATE_CLUES = 2      # "Teammate of" clues in one puzzle
MAX_STAT_CLUES_AN_AXIS = 1  # stat clues among the rows, and among the columns
GUESSES = 9
RANDOM_PROBES = 40          # random grids judged each day before the guided search, for the rejection record

# the pool's own floors: a clue too narrow to fill three cells is not offered to the search at all
TEAMMATE_ANCHORS = 60       # the players with the most maps
TEAMMATE_MIN_ANSWERS = 7
ORG_MIN_ANSWERS = 6
SCOPED_MIN_ANSWERS = 8      # a stage or roster clue narrowed to one season needs this many answers to be offered
EXPERIENCE_STEPS = (25, 50, 75, 100, 125, 150, 175)
STAT_SEASONS = (2025, 2026)
STATS_OFFERED = ("eliminations", "damage_dealt", "deaths")

EASY, MEDIUM, HARD = "Easy", "Medium", "Hard"
EASY_MEDIAN = 9             # Easy: the median cell has this many answers or more ...
EASY_MIN_CELL = 5           # ... and no cell has fewer than this
MEDIUM_MEDIAN = 7           # Medium: the median cell has this many or more ...
MEDIUM_MIN_CELL = 4         # ... and no cell has fewer than this
HARD_MEDIAN = MEDIUM_MEDIAN  # anything else is Hard, down to the 3-answer floor every cell has
WEEKDAY_TARGET = {0: EASY, 1: EASY, 2: MEDIUM, 3: MEDIUM, 4: MEDIUM, 5: HARD, 6: HARD}     # Monday is 0


def difficulty(counts: list[int]) -> str:
    """The label a grid has earned, by its median cell and its smallest. A grid is never labelled by the day it
    was wanted for: one that misses its weekday's target carries the label it actually deserves."""
    median, smallest = statistics.median(counts), min(counts)
    if median >= EASY_MEDIAN and smallest >= EASY_MIN_CELL:
        return EASY
    if median >= MEDIUM_MEDIAN and smallest >= MEDIUM_MIN_CELL:
        return MEDIUM
    return HARD


def build_pool(f: Facts, include_awards: bool = False, anchors: Optional[list[str]] = None) -> list[Clue]:
    """Every clue the search may use, built from the data.

    `anchors` is the owner's approved list (scope/grid_anchors.json): the only players a "Teammate of" clue may name.
    Without one, the players with the most maps stand in, which is for tests and experiments, never for publishing.
    """
    pool: list[Clue] = [RoleClue(r) for r in ROLES]
    pool += [SeasonClue(s) for s in (2024, 2025, 2026)] + [AllSeasonsClue()]
    pool += [RegionClue("na"), RegionClue("emea"), BothRegionsClue()]

    maps = Counter(m.player_id for m in f.maps)
    by_maps = [p for p, _ in sorted(maps.items(), key=lambda kv: (-kv[1], kv[0]))[:TEAMMATE_ANCHORS]]
    for player_id in (by_maps if anchors is None else anchors):
        clue = TeammateClue(player_id, f.name(player_id))
        if len(clue.outcome(f).answers) >= TEAMMATE_MIN_ANSWERS:
            pool.append(clue)

    for org_key in sorted({m.org_key for m in f.maps if is_mapped(m.org_key)}):
        clue = OrgClue(org_key, f.org(org_key))
        if len(clue.outcome(f).answers) >= ORG_MIN_ANSWERS:
            pool.append(clue)

    if f.stages:
        pool += [StageWinClue(), StageWinClue("na"), StageWinClue("emea"),
                 StageFinalClue(), StageFinalClue("na"), StageFinalClue("emea")]
        for season in sorted({s.season for s in f.stages}):
            for clue in (StageWinClue(season=season), StageFinalClue(season=season)):
                if len(clue.outcome(f).answers) >= SCOPED_MIN_ANSWERS:
                    pool.append(clue)

    pool.append(LanClue())
    for season in sorted({c.season for c in f.full.championships.values() if c.region == "international"}):
        clue = LanClue(season=season)
        if len(clue.outcome(f).answers) >= SCOPED_MIN_ANSWERS:
            pool.append(clue)
    for cid, c in sorted(f.full.championships.items(), key=lambda kv: kv[1].name):
        if c.region == "international" and c.tier == "main" and c.name != DALLAS:
            pool.append(LanClue(cid, c.name.removeprefix("OWCS ")))

    pool += [ExperienceClue(n) for n in EXPERIENCE_STEPS]
    pool += [StatClue(stat, season) for stat in STATS_OFFERED for season in STAT_SEASONS]
    if include_awards and f.awards:
        from clues import AwardClue
        pool.append(AwardClue())
    return pool


# ---- the quality rules ------------------------------------------------------------------------------------------

@dataclass
class Verdict:
    cells: list[list[CellOutcome]]
    counts: list[list[int]]
    reasons: list[str]

    @property
    def ok(self) -> bool:
        return not self.reasons

    @property
    def flat(self) -> list[int]:
        return [n for line in self.counts for n in line]


class Judge:
    """Applies the rules to a 3x3 of clues. Keeps each clue's outcome and each pair's cell, so a search is cheap."""

    def __init__(self, f: Facts):
        self.f = f
        self.outcomes: dict[str, Outcome] = {}
        self._cells: dict[tuple[str, str], CellOutcome] = {}

    def own(self, clue: Clue) -> Outcome:
        if clue.key not in self.outcomes:
            self.outcomes[clue.key] = clue.outcome(self.f)
        return self.outcomes[clue.key]

    def cell(self, row: Clue, col: Clue) -> CellOutcome:
        key = (row.key, col.key)
        if key not in self._cells:
            self._cells[key] = cell(self.f, row, col, self.outcomes)
        return self._cells[key]

    def pair_ok(self, a: Clue, b: Clue) -> bool:
        """Could these two share a cell: enough answers, and neither clue all but implying the other?"""
        n = len(self.cell(a, b).answers)
        return n >= MIN_CELL and n < IMPLIED_SHARE * len(self.own(a).answers) and n < IMPLIED_SHARE * len(self.own(b).answers)

    def judge(self, rows: list[Clue], cols: list[Clue]) -> Verdict:
        cells = [[self.cell(r, c) for c in cols] for r in rows]
        counts = [[len(x.answers) for x in line] for line in cells]
        reasons: list[str] = []

        families = {c.family for c in rows + cols}
        if len(families) < MIN_FAMILIES:
            reasons.append(f"only {len(families)} clue families ({', '.join(sorted(families))}); needs {MIN_FAMILIES}")
        if len({c.key for c in rows + cols}) < 6:
            reasons.append("the same clue is used twice")
        reasons += shape_reasons(rows, cols)

        thin = 0
        for r, row in enumerate(rows):
            for c, col in enumerate(cols):
                n = counts[r][c]
                pair = f"{row.label} x {col.label}"
                if n == 0:
                    same = " (same family: they cannot overlap)" if row.family == col.family else ""
                    reasons.append(f"{pair} is empty{same}")
                elif n < MIN_CELL:
                    reasons.append(f"{pair} has {n} answers (needs {MIN_CELL})")
                elif n <= THIN_CELL:
                    thin += 1
                if n:
                    for clue in (row, col):
                        own = len(self.own(clue).answers)
                        if own and n >= IMPLIED_SHARE * own:
                            reasons.append(f"{pair} holds {n} of the {own} '{clue.label}' answers: "
                                           "one clue all but implies the other")
        if thin > MAX_THIN_CELLS:
            reasons.append(f"{thin} cells have only {MIN_CELL}-{THIN_CELL} answers (at most {MAX_THIN_CELLS})")

        fits = Counter(p for line in cells for x in line for p in x.answers)
        if fits:
            player, most = max(fits.items(), key=lambda kv: (kv[1], kv[0]))
            if most > MAX_CELLS_ONE_PLAYER:
                reasons.append(f"{self.f.name(player)} fits {most} cells (at most {MAX_CELLS_ONE_PLAYER})")

        fillable = distinct_solution([frozenset(x.answers) for line in cells for x in line])
        if fillable < 9:
            reasons.append(f"only {fillable} of 9 cells can be filled with different players")
        return Verdict(cells, counts, reasons)


def shape_reasons(rows: list[Clue], cols: list[Clue]) -> list[str]:
    """Limits on what kinds of clue one puzzle may hold, whatever their answers."""
    reasons = []
    families = Counter(c.family for c in rows + cols)
    if families["experience"] > MAX_EXPERIENCE_CLUES:
        reasons.append(f"{families['experience']} 'N+ maps' clues (at most {MAX_EXPERIENCE_CLUES})")
    if families["teammate"] > MAX_TEAMMATE_CLUES:
        reasons.append(f"{families['teammate']} 'Teammate of' clues (at most {MAX_TEAMMATE_CLUES})")
    for axis, clues in (("rows", rows), ("columns", cols)):
        stats = sum(1 for c in clues if c.family == "stats")
        if stats > MAX_STAT_CLUES_AN_AXIS:
            reasons.append(f"{stats} stat clues among the {axis} (at most {MAX_STAT_CLUES_AN_AXIS})")
    return reasons


def overlap_reasons(rows: list[Clue], cols: list[Clue], day: date, past: list[tuple[date, frozenset[str]]]) -> list[str]:
    """A puzzle sharing three or more of its six clues with one from the previous 21 days is a near-repeat."""
    mine = {c.key for c in rows + cols}
    reasons = []
    for when, keys in past:
        shared = len(mine & keys)
        if 0 < (day - when).days <= OVERLAP_DAYS and shared > MAX_SHARED_CLUES:
            reasons.append(f"shares {shared} of its 6 clues with the puzzle of {when.isoformat()}, within {OVERLAP_DAYS} days "
                           f"(at most {MAX_SHARED_CLUES})")
    return reasons


def clue_sets(puzzles: list[dict]) -> list[tuple[date, frozenset[str]]]:
    """(day, the six clue keys) for each puzzle, in the keys mixed puzzles use, for the overlap rule."""
    out = []
    for p in puzzles:
        keys = frozenset(c["key"] if p.get("format") == 2 else LEGACY_KEYS.get(c["key"], c["key"]) for c in p["rows"] + p["cols"])
        out.append((date.fromisoformat(p["date"]), keys))
    return out


def recency_reasons(rows: list[Clue], cols: list[Clue], day: date, used: dict[str, date], anchors: dict[str, date],
                    past: Optional[list[tuple[date, frozenset[str]]]] = None) -> list[str]:
    """A clue used in the previous 7 days, a teammate anchor in the previous 14, or three clues shared with a
    puzzle of the previous 21 (when `past` is given), rules the grid out."""
    reasons = overlap_reasons(rows, cols, day, past) if past else []
    for clue in rows + cols:
        last = used.get(clue.key)
        if last is not None and 0 < (day - last).days <= CLUE_GAP_DAYS:
            reasons.append(f"'{clue.label}' was used on {last.isoformat()}, within {CLUE_GAP_DAYS} days")
        if clue.anchor:
            last = anchors.get(clue.anchor)
            if last is not None and 0 < (day - last).days <= ANCHOR_GAP_DAYS:
                reasons.append(f"{clue.name} was an anchor on {last.isoformat()}, within {ANCHOR_GAP_DAYS} days")
    return reasons


# ---- one puzzle as stored ---------------------------------------------------------------------------------------

def clue_entry(clue: Clue) -> dict:
    return {"key": clue.key, "family": clue.family, "label": clue.label, "help": clue.definition,
            "cannot_verify": clue.cannot_verify, "params": clue.params()}


def puzzle_entry(f: Facts, verdict: Verdict, rows: list[Clue], cols: list[Clue], number: int, day: date,
                 generated_at: str, snapshot: str, seed: Optional[int]) -> dict:
    cells = []
    for r in range(3):
        for c in range(3):
            out = verdict.cells[r][c]
            cells.append({
                "row": r, "col": c, "count": len(out.answers),
                "answers": {p: {"name": f.name(p), "why": out.answers[p]} for p in sorted(out.answers)},
                "unverifiable": {p: out.unverifiable[p] for p in sorted(out.unverifiable)},
            })
    flat = verdict.flat
    return {
        "format": 2,
        "number": number,
        "date": day.isoformat(),
        "kind": "role" if all(isinstance(r, RoleClue) for r in rows) else "mixed",
        "difficulty": difficulty(flat),
        "median_answers": statistics.median(flat),
        "rows": [clue_entry(c) for c in rows],
        "cols": [clue_entry(c) for c in cols],
        "rules": {"min_answers": MIN_CELL, "guesses": GUESSES},
        "cells": cells,
        "generated_at": generated_at,
        "snapshot": snapshot,
        "seed": seed,
    }


# ---- the search -------------------------------------------------------------------------------------------------

LEGACY_KEYS = {"tank": "role:tank", "dps": "role:dps", "support": "role:support", "2024": "season:2024",
               "2025": "season:2025", "2026": "season:2026", "na": "region:na", "emea": "region:emea",
               "all3": "season:all3"}


def history(puzzles: list[dict]) -> tuple[dict[str, date], dict[str, date], Optional[date]]:
    """(clue key -> last day used, anchor player -> last day used, last role-grid day), from puzzles already kept."""
    used: dict[str, date] = {}
    anchors: dict[str, date] = {}
    last_role: Optional[date] = None
    for p in sorted(puzzles, key=lambda p: p["date"]):
        day = date.fromisoformat(p["date"])
        role_rows = True
        for clue in p["rows"] + p["cols"]:
            key = clue["key"] if p.get("format") == 2 else LEGACY_KEYS.get(clue["key"], clue["key"])
            used[key] = day
            if key.startswith("teammate:"):
                anchors[key.split(":", 1)[1]] = day
        for clue in p["rows"]:
            key = clue["key"] if p.get("format") == 2 else LEGACY_KEYS.get(clue["key"], clue["key"])
            role_rows = role_rows and key.startswith("role:")
        if role_rows:
            last_role = day
    return used, anchors, last_role


@dataclass
class DayResult:
    day: date
    target: str
    entry: Optional[dict]
    tried: int
    reason_counts: Counter
    samples: list[dict]             # a few rejected candidates, with their reasons
    note: str = ""


def _reason_kind(reason: str) -> str:
    for needle, kind in (("is empty", "an empty cell"), ("answers (needs", "a cell under 3 answers"),
                         ("implies the other", "one clue implies the other"), ("cells have only", "too many thin cells"),
                         ("fits", "one player fits too many cells"), ("can be filled", "not fillable by 9 players"),
                         ("clue families", "too few families"), ("was used on", "a clue used in the last 7 days"),
                         ("of its 6 clues", "three clues shared with a puzzle of the last 21 days"),
                         ("'N+ maps' clues", "more than one 'N+ maps' clue"),
                         ("'Teammate of' clues", "more than two 'Teammate of' clues"),
                         ("stat clues among", "two stat clues on one axis"),
                         ("was an anchor", "an anchor used in the last 14 days"), ("used twice", "a repeated clue")):
        if needle in reason:
            return kind
    return "other"


def _interest(rows: list[Clue], cols: list[Clue], verdict: Verdict) -> tuple:
    """Between two valid grids of one difficulty: a Hard one that is hard throughout (a low median, not one thin cell
    in an easy grid) first; then more families, a teammate clue, and fewer thin cells."""
    families = {c.family for c in rows + cols}
    thin = sum(1 for n in verdict.flat if n <= THIN_CELL)
    hard_throughout = difficulty(verdict.flat) == HARD and statistics.median(verdict.flat) < MEDIUM_MEDIAN
    return (hard_throughout, len(families), "teammate" in families, len(families & {"org", "stage", "lan", "stats"}), -thin)


class _DaySearch:
    """The candidates judged for one day: the valid ones, and a record of what failed and why."""

    def __init__(self, judge: Judge, rng: random.Random, day: date, target: str, used: dict[str, date],
                 anchors: dict[str, date], samples_kept: int, past: Optional[list[tuple[date, frozenset[str]]]] = None):
        self.judge, self.rng, self.day, self.target = judge, rng, day, target
        self.used, self.anchors, self.samples_kept, self.past = used, anchors, samples_kept, past or []
        self.valid: list[tuple[tuple, list[Clue], list[Clue], Verdict]] = []
        self.reason_counts: Counter = Counter()
        self.samples: list[dict] = []
        self.seen: set[tuple] = set()
        self.tried = 0

    def offer(self, rows: list[Clue], cols: list[Clue]) -> None:
        signature = (frozenset(c.key for c in rows), frozenset(c.key for c in cols))
        if signature in self.seen or (signature[1], signature[0]) in self.seen:
            return
        self.seen.add(signature)
        self.tried += 1
        reasons = recency_reasons(rows, cols, self.day, self.used, self.anchors, self.past)
        verdict = self.judge.judge(rows, cols)
        reasons += verdict.reasons
        if reasons:
            self.reason_counts.update({_reason_kind(r) for r in reasons})
            if len(self.samples) < self.samples_kept:
                self.samples.append({"rows": [c.label for c in rows], "cols": [c.label for c in cols],
                                     "counts": verdict.counts, "reasons": reasons})
            return
        self.valid.append((_interest(rows, cols, verdict), rows, cols, verdict))

    def on_target(self) -> bool:
        return any(difficulty(v[3].flat) == self.target for v in self.valid)

    def run(self, free: list[Clue], roles: list[Clue], attempts: int) -> None:
        # A few purely random grids first, for the record of what fails and why: almost all of them do.
        for _ in range(min(RANDOM_PROBES, attempts)):
            if len(free) < 6:
                break
            six = self.rng.sample(free, 6)
            self.offer(six[:3], six[3:])
        # A role grid, when one is due: the three roles against every usable trio of columns.
        if roles:
            usable = [c for c in free if all(self.judge.pair_ok(r, c) for r in roles)]
            triples = [t for t in itertools.combinations(usable, 3) if not shape_reasons(list(roles), list(t))]
            self.rng.shuffle(triples)
            for cols in triples[:attempts]:
                self.offer(list(roles), list(cols))
        if self.on_target():
            return
        # Otherwise build grids a clue at a time: each one added must already make a usable cell with those opposite.
        fits = {a.key: [b for b in free if b.key != a.key and self.judge.pair_ok(a, b)] for a in free}
        recent = tuple(keys for when, keys in self.past if 0 < (self.day - when).days <= OVERLAP_DAYS)
        for _ in range(attempts):
            grid = _grow(self.rng, free, fits, recent)
            if grid:
                self.offer(*grid)
        # nothing at all yet: keep building for as long again, three times, before giving the day up
        for _ in range(3):
            if self.valid:
                break
            for _ in range(attempts):
                grid = _grow(self.rng, free, fits, recent)
                if grid:
                    self.offer(*grid)


MAX_BACKTRACKS = 150        # times a run may step back a day to choose differently, when a later day has no grid


def generate_days(f: Facts, kept: list[dict], dates: list[date], seed: int, generated_at: str, snapshot: str,
                  attempts: int = 15000, samples_kept: int = 8, include_awards: bool = False,
                  anchors: Optional[list[str]] = None) -> list[DayResult]:
    """One puzzle per date, each passing every rule and no clue-recency conflict with the days before it.

    Days are chosen in order, and a day's choice uses up clues the following week needs. When a day has no valid
    grid at all, the run steps back one day, sets aside the puzzle it chose there, and chooses again.
    """
    rng = random.Random(seed)
    judge = Judge(f)
    pool = build_pool(f, include_awards, anchors)
    roles = [c for c in pool if isinstance(c, RoleClue)]
    others = [c for c in pool if not isinstance(c, RoleClue)]
    used, anchor_days, last_role = history(kept)
    past = clue_sets(kept)
    first_number = max((p["number"] for p in kept), default=0) + 1
    results: list[DayResult] = []
    before: list[tuple] = []                            # the state each day started from, to step back to
    set_aside: dict[int, set[frozenset[str]]] = {}      # day index -> puzzles tried there that led to a dead end
    backtracks = 0

    i = 0
    while i < len(dates):
        day = dates[i]
        if len(before) == i:
            before.append((dict(used), dict(anchor_days), last_role, list(past)))
        target = WEEKDAY_TARGET[day.weekday()]
        role_day = target != HARD and (last_role is None or (day - last_role).days >= ROLE_GRID_GAP_DAYS)
        free = [c for c in others if not recency_reasons([c], [], day, used, anchor_days)]
        search = _DaySearch(judge, rng, day, target, used, anchor_days, samples_kept, past)
        search.run(free, roles if role_day else [], attempts)
        tried, reason_counts, samples = search.tried, search.reason_counts, search.samples
        barred = set_aside.get(i, set())
        valid = [v for v in search.valid if frozenset(c.key for c in v[1] + v[2]) not in barred]
        note = ""
        chosen = [v for v in valid if difficulty(v[3].flat) == target]
        if not chosen and valid:
            order = [EASY, MEDIUM, HARD]
            nearest = min(valid, key=lambda v: abs(order.index(difficulty(v[3].flat)) - order.index(target)))
            near = difficulty(nearest[3].flat)
            chosen = [v for v in valid if difficulty(v[3].flat) == near]
            note = f"no valid {target} grid in {tried} candidates; relabelled {near}, the nearest valid difficulty"
        if not chosen:
            if i > 0 and results[i - 1].entry is not None and backtracks < MAX_BACKTRACKS:
                # a dead end: undo yesterday, set its puzzle aside, and choose yesterday again
                backtracks += 1
                set_aside.pop(i, None)
                gone = results.pop()
                set_aside.setdefault(i - 1, set()).add(frozenset(c["key"] for c in gone.entry["rows"] + gone.entry["cols"]))
                before.pop()
                used, anchor_days, last_role, past = (dict(before[i - 1][0]), dict(before[i - 1][1]), before[i - 1][2],
                                                      list(before[i - 1][3]))
                i -= 1
                continue
            results.append(DayResult(day, target, None, tried, reason_counts, samples,
                                     f"no valid grid in {tried} candidates"))
            i += 1
            continue
        best = max(v[0] for v in chosen)
        _, rows, cols, verdict = rng.choice([v for v in chosen if v[0] == best])
        entry = puzzle_entry(f, verdict, rows, cols, first_number + i, day, generated_at, snapshot, seed)
        for clue in rows + cols:
            used[clue.key] = day
            if clue.anchor:
                anchor_days[clue.anchor] = day
        if entry["kind"] == "role":
            last_role = day
        past.append((day, frozenset(c.key for c in rows + cols)))
        if backtracks and set_aside.get(i):
            note = (note + "; " if note else "") + f"chosen again after a later day had no valid grid ({len(set_aside[i])} set aside)"
        results.append(DayResult(day, target, entry, tried, reason_counts, samples, note))
        i += 1
    return results


def _grow(rng: random.Random, free: list[Clue], fits: dict[str, list[Clue]],
          recent: tuple[frozenset[str], ...] = ()) -> Optional[tuple[list[Clue], list[Clue]]]:
    """Seat six clues one at a time, row and column in turn, each fitting every clue already opposite it.

    A clue is not seated if the rules would refuse the grid for it whatever came next: a shape limit, too few
    families left to reach four, or a third clue shared with one of the `recent` puzzles.
    """
    if not free:
        return None
    rows, cols = [rng.choice(free)], []
    for step in range(5):
        side, opposite = (cols, rows) if step % 2 == 0 else (rows, cols)
        seated = rows + cols
        taken = {c.key for c in seated}
        families = {c.family for c in seated}
        slots_after = 5 - len(seated)               # seats still empty once this one is filled
        options = []
        for c in fits[opposite[0].key]:
            if c.key in taken or not all(c in fits[o.key] for o in opposite[1:]):
                continue
            if len(families | {c.family}) + slots_after < MIN_FAMILIES:
                continue
            if shape_reasons(rows + ([c] if side is rows else []), cols + ([c] if side is cols else [])):
                continue
            keys = taken | {c.key}
            if any(len(keys & past) > MAX_SHARED_CLUES for past in recent):
                continue
            options.append(c)
        if not options:
            return None
        side.append(rng.choice(options))
    return rows, cols
