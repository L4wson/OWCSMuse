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
GUESSES = 9
RANDOM_PROBES = 40          # random grids judged each day before the guided search, for the rejection record

# the pool's own floors: a clue too narrow to fill three cells is not offered to the search at all
TEAMMATE_ANCHORS = 60       # the players with the most maps
TEAMMATE_MIN_ANSWERS = 12
ORG_MIN_ANSWERS = 8
EXPERIENCE_STEPS = (50, 75, 100, 125, 150)
STAT_SEASONS = (2025, 2026)
STATS_OFFERED = ("eliminations", "damage_dealt", "deaths")

EASY, MEDIUM, HARD = "Easy", "Medium", "Hard"
EASY_MEDIAN = 9             # median answers per cell at or above this is Easy ...
HARD_MEDIAN = 7             # ... below this is Hard, between is Medium
WEEKDAY_TARGET = {0: EASY, 1: EASY, 2: MEDIUM, 3: MEDIUM, 4: MEDIUM, 5: HARD, 6: HARD}     # Monday is 0


def difficulty(counts: list[int]) -> str:
    median = statistics.median(counts)
    return EASY if median >= EASY_MEDIAN else HARD if median < HARD_MEDIAN else MEDIUM


def build_pool(f: Facts, include_awards: bool = False) -> list[Clue]:
    """Every clue the search may use, built from the data: anchors and orgs are chosen by what they have played."""
    pool: list[Clue] = [RoleClue(r) for r in ROLES]
    pool += [SeasonClue(s) for s in (2024, 2025, 2026)] + [AllSeasonsClue()]
    pool += [RegionClue("na"), RegionClue("emea"), BothRegionsClue()]

    maps = Counter(m.player_id for m in f.maps)
    for player_id, _ in sorted(maps.items(), key=lambda kv: (-kv[1], kv[0]))[:TEAMMATE_ANCHORS]:
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

    pool.append(LanClue())
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


def recency_reasons(rows: list[Clue], cols: list[Clue], day: date, used: dict[str, date], anchors: dict[str, date]
                    ) -> list[str]:
    """A clue used in the previous 7 days, or a teammate anchor in the previous 14, rules the grid out."""
    reasons = []
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
                         ("was an anchor", "an anchor used in the last 14 days"), ("used twice", "a repeated clue")):
        if needle in reason:
            return kind
    return "other"


def _interest(rows: list[Clue], cols: list[Clue], verdict: Verdict) -> tuple:
    """Between two valid grids for a day: more families first, then a teammate clue, then fewer thin cells."""
    families = {c.family for c in rows + cols}
    thin = sum(1 for n in verdict.flat if n <= THIN_CELL)
    return (len(families), "teammate" in families, len(families & {"org", "stage", "lan", "stats"}), -thin)


class _DaySearch:
    """The candidates judged for one day: the valid ones, and a record of what failed and why."""

    def __init__(self, judge: Judge, rng: random.Random, day: date, target: str, used: dict[str, date],
                 anchors: dict[str, date], samples_kept: int):
        self.judge, self.rng, self.day, self.target = judge, rng, day, target
        self.used, self.anchors, self.samples_kept = used, anchors, samples_kept
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
        reasons = recency_reasons(rows, cols, self.day, self.used, self.anchors)
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
            triples = list(itertools.combinations(usable, 3))
            self.rng.shuffle(triples)
            for cols in triples[:attempts]:
                self.offer(list(roles), list(cols))
        if self.on_target():
            return
        # Otherwise build grids a clue at a time: each one added must already make a usable cell with those opposite.
        fits = {a.key: [b for b in free if b.key != a.key and self.judge.pair_ok(a, b)] for a in free}
        for _ in range(attempts):
            grid = _grow(self.rng, free, fits)
            if grid:
                self.offer(*grid)


def generate_days(f: Facts, kept: list[dict], dates: list[date], seed: int, generated_at: str, snapshot: str,
                  attempts: int = 15000, samples_kept: int = 8, include_awards: bool = False) -> list[DayResult]:
    """One puzzle per date, each passing every rule and no clue-recency conflict with the days before it."""
    rng = random.Random(seed)
    judge = Judge(f)
    pool = build_pool(f, include_awards)
    roles = [c for c in pool if isinstance(c, RoleClue)]
    others = [c for c in pool if not isinstance(c, RoleClue)]
    used, anchors, last_role = history(kept)
    number = max((p["number"] for p in kept), default=0)
    results: list[DayResult] = []

    for day in dates:
        target = WEEKDAY_TARGET[day.weekday()]
        role_day = target != HARD and (last_role is None or (day - last_role).days >= ROLE_GRID_GAP_DAYS)
        free = [c for c in others if not recency_reasons([c], [], day, used, anchors)]
        search = _DaySearch(judge, rng, day, target, used, anchors, samples_kept)
        search.run(free, roles if role_day else [], attempts)
        valid, tried, reason_counts, samples = search.valid, search.tried, search.reason_counts, search.samples
        note = ""
        chosen = [v for v in valid if difficulty(v[3].flat) == target]
        if not chosen and valid:
            order = [EASY, MEDIUM, HARD]
            nearest = min(valid, key=lambda v: abs(order.index(difficulty(v[3].flat)) - order.index(target)))
            near = difficulty(nearest[3].flat)
            chosen = [v for v in valid if difficulty(v[3].flat) == near]
            note = f"no valid {target} grid in {tried} candidates; the nearest valid difficulty is {near}"
        if not chosen:
            results.append(DayResult(day, target, None, tried, reason_counts, samples,
                                     f"no valid grid in {tried} candidates"))
            continue
        best = max(v[0] for v in chosen)
        _, rows, cols, verdict = rng.choice([v for v in chosen if v[0] == best])
        number += 1
        entry = puzzle_entry(f, verdict, rows, cols, number, day, generated_at, snapshot, seed)
        for clue in rows + cols:
            used[clue.key] = day
            if clue.anchor:
                anchors[clue.anchor] = day
        if entry["kind"] == "role":
            last_role = day
        results.append(DayResult(day, target, entry, tried, reason_counts, samples, note))
    return results


def _grow(rng: random.Random, free: list[Clue], fits: dict[str, list[Clue]]) -> Optional[tuple[list[Clue], list[Clue]]]:
    """Seat six clues one at a time, row and column in turn, each fitting every clue already opposite it."""
    if not free:
        return None
    rows, cols = [rng.choice(free)], []
    for step in range(5):
        side, opposite = (cols, rows) if step % 2 == 0 else (rows, cols)
        taken = {c.key for c in rows + cols}
        options = [c for c in fits[opposite[0].key]
                   if c.key not in taken and all(c in fits[o.key] for o in opposite[1:])]
        if not options:
            return None
        side.append(rng.choice(options))
    return rows, cols
