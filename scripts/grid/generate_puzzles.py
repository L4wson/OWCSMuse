"""Generate daily OWCS Grid puzzles into scope/grid_puzzles.json. Reads the warehouse read-only; writes two files.

    python scripts/grid/generate_puzzles.py --start-date 2026-11-18 --days 14 --seed 7

Each puzzle is role x column: the rows are always Tank / DPS / Support, the columns are three of the six in
`COLUMN_POOL`. A player answers a cell with at least `MIN_MAPS` maps in that role inside the column's scope (that
season, that region, or the whole in-scope career for "Played all 3 seasons"). The scope is OWCS NA and EMEA main
series: relegation and international events are left out.

A candidate grid is rejected unless every cell has `MIN_ANSWERS` answers, all nine cells can be filled with nine
different players, and its column set was not used in the previous `REPEAT_WINDOW` days.

Published puzzles never change: a date that is today or earlier (UTC) is refused, and new puzzles are only appended
after the last one in the file. The API serves the file as it is and never queries the database.

The condition classes and the cell evaluation are the Phase 0 modules beside this file, unchanged.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cell_counter import distinct_solution, evaluate, parse_condition  # noqa: E402
from conditions import Region, Role, Season, stats_coverage  # noqa: E402
from data import Appearance, Warehouse, load  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PUZZLES_PATH = REPO / "scope" / "grid_puzzles.json"
PLAYERS_PATH = REPO / "scope" / "grid_players.json"
RUNS_DIR = REPO / "docs" / "grid" / "runs"

MIN_MAPS = 10           # maps in the role, inside the column's scope, for a player to be an answer
MIN_ANSWERS = 5         # every cell needs this many answers
GUESSES = 9
REPEAT_WINDOW = 7       # a column set is not reused within this many days
SCOPE_REGIONS = ("na", "emea")
SCOPE_NOTE = "OWCS NA and EMEA main series (stages and playoffs); relegation and international events are not counted"


@dataclass(frozen=True)
class RowDef:
    key: str
    spec: str
    label: str


@dataclass(frozen=True)
class ColumnDef:
    key: str
    spec: str
    label: str
    help: str           # what the clue means, shown to the player
    explain: str        # the reason line for a correct answer; {maps} and {role} are filled in


ROWS = (
    RowDef("tank", "role:tank", "Tank"),
    RowDef("dps", "role:dps", "DPS"),
    RowDef("support", "role:support", "Support"),
)

COLUMN_POOL: dict[str, ColumnDef] = {c.key: c for c in (
    *(ColumnDef(str(y), f"season:{y}", str(y), f"{MIN_MAPS}+ maps in the role in the {y} season",
                f"{{maps}} {{role}} maps in {y}") for y in (2024, 2025, 2026)),
    ColumnDef("na", "region:na", "NA", f"{MIN_MAPS}+ maps in the role in OWCS North America",
              "{maps} {role} maps in NA"),
    ColumnDef("emea", "region:emea", "EMEA", f"{MIN_MAPS}+ maps in the role in OWCS EMEA",
              "{maps} {role} maps in EMEA"),
    ColumnDef("all3", "min_seasons:3", "Played all 3 seasons",
              f"Played in 2024, 2025 and 2026, with {MIN_MAPS}+ maps in the role across them",
              "{maps} {role} maps, and played in 2024, 2025 and 2026"),
)}


class PublishedError(ValueError):
    """The request would change a puzzle that is already published."""


# ---- scope ------------------------------------------------------------------------------------------------------

def in_scope(wh: Warehouse) -> Warehouse:
    """The warehouse cut down to OWCS NA and EMEA main series: what a puzzle's answers are counted from."""
    keep = {cid for cid, c in wh.championships.items() if c.tier == "main" and c.region in SCOPE_REGIONS}
    return replace(
        wh,
        appearances=[a for a in wh.appearances if a.championship_id in keep],
        map_rows=[m for m in wh.map_rows if m.championship_id in keep],
        team_series=[], placements=[],
        championships={cid: c for cid, c in wh.championships.items() if cid in keep},
    )


def presence_rows(wh: Warehouse) -> list[Appearance]:
    """Every main-tier line-up appearance, international events included: where a player is known to have played.

    Wider than the answer scope on purpose. It decides "can't verify": someone seen playing in a column's scope for
    whom no role was ever recorded there (2024 Stages 3-4, 2026 Stage 3, an international event).
    """
    main = {cid for cid, c in wh.championships.items() if c.tier == "main"}
    return [a for a in wh.appearances if a.championship_id in main]


# ---- one puzzle -------------------------------------------------------------------------------------------------

def role_maps(scoped: Warehouse, role: Role, column) -> dict[str, int]:
    """player -> maps played in `role` inside the column's scope (the whole in-scope career for a set condition)."""
    counts: dict[str, int] = defaultdict(int)
    on_column = column.on_row if isinstance(column, (Season, Region)) else (lambda _row: True)
    for m in scoped.map_rows:
        if role.on_row(m) and on_column(m):
            counts[m.player_id] += 1
    return counts


def unverifiable(scoped: Warehouse, presence: list[Appearance], column) -> set[str]:
    """Players seen in the column's scope with no role recorded there at all, whichever role is asked."""
    if isinstance(column, (Season, Region)):
        seen = {a.player_id for a in presence if column.on_row(a)}
        with_role = {m.player_id for m in scoped.map_rows if m.role and column.on_row(m)}
    else:   # MinSeasons: in a line-up in enough seasons, with no role on record anywhere in scope
        seasons: dict[str, set[int]] = defaultdict(set)
        for a in presence:
            seasons[a.player_id].add(a.season)
        seen = {p for p, s in seasons.items() if len(s) >= column.n}
        with_role = {m.player_id for m in scoped.map_rows if m.role}
    return seen - with_role


@dataclass
class Built:
    entry: Optional[dict]
    counts: list[list[int]]
    reasons: list[str]


def build_puzzle(scoped: Warehouse, presence: list[Appearance], number: int, day: date, column_keys: tuple[str, ...],
                 generated_at: str, snapshot: str, seed: Optional[int] = None) -> Built:
    """Evaluate one candidate grid. `entry` is the publishable puzzle, or None with the reasons it was rejected."""
    columns = [COLUMN_POOL[k] for k in column_keys]
    row_conds = [parse_condition(scoped, r.spec) for r in ROWS]
    col_conds = [parse_condition(scoped, c.spec) for c in columns]
    grid = evaluate(scoped, "player", row_conds, col_conds, MIN_MAPS, 1)
    counts = [[len(cell.ids) for cell in line] for line in grid]

    reasons = [
        f"{ROWS[r].label} x {columns[c].label} has {counts[r][c]} answers (needs {MIN_ANSWERS})"
        for r in range(3) for c in range(3) if counts[r][c] < MIN_ANSWERS
    ]
    fillable = distinct_solution([cell.ids for line in grid for cell in line])
    if fillable < 9:
        reasons.append(f"only {fillable} of 9 cells can be filled with different players")
    if reasons:
        return Built(None, counts, reasons)

    cells = []
    for r, line in enumerate(grid):
        for c, cell in enumerate(line):
            maps = role_maps(scoped, row_conds[r], col_conds[c])
            answers = {
                player_id: {"name": scoped.player_names.get(player_id) or "(no name)", "maps": maps[player_id]}
                for player_id in sorted(cell.ids)
            }
            if any(a["maps"] < MIN_MAPS for a in answers.values()):
                raise AssertionError(f"an answer of cell {r},{c} is under the {MIN_MAPS}-map floor")
            cells.append({"row": r, "col": c, "count": len(answers), "answers": answers})

    valid_by_col = [set().union(*(grid[r][c].ids for r in range(3))) for c in range(3)]
    entry = {
        "number": number,
        "date": day.isoformat(),
        "rows": [{"key": r.key, "spec": r.spec, "label": r.label} for r in ROWS],
        "cols": [{"key": c.key, "spec": c.spec, "label": c.label, "help": c.help, "explain": c.explain}
                 for c in columns],
        "rules": {"min_maps": MIN_MAPS, "min_answers": MIN_ANSWERS, "guesses": GUESSES},
        "cells": cells,
        "unverifiable": [sorted(unverifiable(scoped, presence, col_conds[c]) - valid_by_col[c]) for c in range(3)],
        "coverage": [stats_coverage(scoped, row_conds[0], col_conds[c]) for c in range(3)],
        "generated_at": generated_at,
        "snapshot": snapshot,
        "seed": seed,
    }
    return Built(entry, counts, [])


# ---- a run of days ----------------------------------------------------------------------------------------------

def plan_dates(existing: list[dict], start: date, days: int, today: date, replace_future: bool = False
               ) -> tuple[list[dict], list[date], list[date]]:
    """(puzzles kept, dates to generate, dates skipped because the file already has them).

    A date that is today or earlier is published: asking for one is an error, never a rewrite. A future date already
    in the file is left alone unless `replace_future`, which regenerates from `start` on and still cannot reach a
    published date. New dates are only ever added after the last one kept, so numbers follow dates.
    """
    wanted = [start + timedelta(days=i) for i in range(days)]
    published = [d for d in wanted if d <= today]
    if published:
        raise PublishedError(
            f"{published[0].isoformat()} is today or earlier (UTC today is {today.isoformat()}): a published puzzle "
            "is never changed and past dates are never filled in. Start from tomorrow.")
    kept = [p for p in existing if not (replace_future and date.fromisoformat(p["date"]) >= start)]
    last = max((date.fromisoformat(p["date"]) for p in kept), default=None)
    have = {date.fromisoformat(p["date"]) for p in kept}
    todo = [d for d in wanted if last is None or d > last]
    skipped = [d for d in wanted if d in have]
    gap = [d for d in wanted if d not in have and last is not None and d <= last]
    if gap:
        raise PublishedError(f"{gap[0].isoformat()} is before the last puzzle in the file ({last.isoformat()}): "
                             "puzzles are only appended")
    return kept, todo, skipped


def generate(scoped: Warehouse, presence: list[Appearance], kept: list[dict], dates: list[date], seed: int,
             generated_at: str, snapshot: str) -> tuple[list[dict], list[dict]]:
    """(new puzzles, rejected candidates). Each day tries the column sets in a seeded random order."""
    rng = random.Random(seed)
    combos = list(itertools.combinations(COLUMN_POOL, 3))
    history = {date.fromisoformat(p["date"]): frozenset(c["key"] for c in p["cols"]) for p in kept}
    number = max((p["number"] for p in kept), default=0)
    verdicts: dict[tuple[str, ...], Built] = {}      # a column set's counts do not depend on the day
    new, rejected = [], []
    for day in dates:
        order = combos[:]
        rng.shuffle(order)
        for combo in order:
            recent = [d for d, used in history.items() if used == frozenset(combo) and 0 < (day - d).days < REPEAT_WINDOW]
            if recent:
                rejected.append({"date": day.isoformat(), "columns": list(combo), "counts": None, "reasons": [
                    f"the same columns were used on {max(recent).isoformat()}, within {REPEAT_WINDOW} days"]})
                continue
            columns = tuple(rng.sample(combo, 3))                 # the order on the board
            built = verdicts.get(combo) or build_puzzle(scoped, presence, 0, day, columns, generated_at, snapshot, seed)
            verdicts[combo] = built
            if built.entry is None:
                rejected.append({"date": day.isoformat(), "columns": list(combo), "counts": built.counts,
                                 "reasons": built.reasons})
                continue
            number += 1
            entry = build_puzzle(scoped, presence, number, day, columns, generated_at, snapshot, seed).entry
            new.append(entry)
            history[day] = frozenset(combo)
            break
        else:
            raise RuntimeError(f"no valid grid exists for {day.isoformat()}: every column set was rejected")
    return new, rejected


# ---- the player index (autocomplete) ----------------------------------------------------------------------------

NAMES_SQL = """
    SELECT entity_id AS player_id, name FROM entity_names WHERE entity_type = 'player' AND name IS NOT NULL AND name <> ''
"""
LAST_SERIES_SQL = """
    SELECT max(s.played_at) AS last FROM series s JOIN championships c ON c.championship_id = s.championship_id AND c.include
"""


def player_index(wh: Warehouse, other_names: dict[str, set[str]]) -> list[dict]:
    """Every player who was ever in a line-up, with what tells two same-named players apart: last team, seasons."""
    latest: dict[str, Appearance] = {}
    seasons: dict[str, set[int]] = defaultdict(set)
    for a in presence_rows(wh):
        seasons[a.player_id].add(a.season)
        if a.player_id not in latest or a.played_at > latest[a.player_id].played_at:
            latest[a.player_id] = a
    index = []
    for player_id, last in latest.items():
        name = wh.player_names.get(player_id) or "(no name)"
        index.append({
            "id": player_id, "name": name,
            "names": sorted(n for n in other_names.get(player_id, set()) if n.casefold() != name.casefold()),
            "team": wh.org_names.get(last.org_key) or "", "seasons": sorted(seasons[player_id]),
        })
    return sorted(index, key=lambda p: (p["name"].casefold(), p["id"]))


# ---- files and report -------------------------------------------------------------------------------------------

FILE_NOTE = (
    "OWCS Grid puzzles, written by scripts/grid/generate_puzzles.py and served as-is by the API "
    "(owcsmuse/grid). A puzzle whose date is today or earlier (UTC) is published and never edited: the generator "
    "refuses to, and nobody should by hand. Each cell holds every accepted player id with the name and maps-in-role "
    "at generation; 'unverifiable' holds, per column, the players seen there with no role on record."
)


def read_puzzles(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["puzzles"]


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def report(new: list[dict], rejected: list[dict], skipped: list[date], header: list[str]) -> str:
    lines = list(header)
    if skipped:
        lines.append(f"already in the file, left alone: {skipped[0].isoformat()} to {skipped[-1].isoformat()}")
    lines.append("")
    for p in new:
        labels = [c["label"] for c in p["cols"]]
        counts = [[p["cells"][r * 3 + c]["count"] for c in range(3)] for r in range(3)]
        smallest = min(min(line) for line in counts)
        lines.append(f"#{p['number']}  {p['date']}  columns: {' | '.join(labels)}   smallest cell: {smallest}")
        for r, row in enumerate(p["rows"]):
            lines.append(f"    {row['label']:8s}" + "".join(f"{n:>6d}" for n in counts[r]))
        lines.append("    can't verify (per column): " + ", ".join(str(len(u)) for u in p["unverifiable"]))
    lines.append("")
    lines.append(f"rejected candidates: {len(rejected)}")
    for r in rejected:
        counts = "" if r["counts"] is None else f"  counts {r['counts']}"
        lines.append(f"    {r['date']}  {' | '.join(r['columns'])}{counts}")
        for reason in r["reasons"]:
            lines.append(f"        {reason}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Generate OWCS Grid puzzles (reads the database read-only).")
    p.add_argument("--start-date", required=True, type=date.fromisoformat, help="first puzzle date, YYYY-MM-DD (UTC)")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--seed", type=int, default=None, help="default: the start date as a number")
    p.add_argument("--replace-future", action="store_true",
                   help="regenerate unpublished puzzles from the start date on (never a published one)")
    p.add_argument("--dry-run", action="store_true", help="print the report; write nothing")
    args = p.parse_args(argv)
    if args.days < 1:
        p.error("--days must be at least 1")
    seed = args.seed if args.seed is not None else int(args.start_date.strftime("%Y%m%d"))
    now = datetime.now(timezone.utc)

    try:
        kept, dates, skipped = plan_dates(read_puzzles(PUZZLES_PATH), args.start_date, args.days, now.date(),
                                          args.replace_future)
    except PublishedError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2

    from db import connect_readonly     # imported here so the offline tests never need a database driver configured
    conn = connect_readonly()
    try:
        wh = load(conn)
        other_names: dict[str, set[str]] = defaultdict(set)
        for row in conn.execute(NAMES_SQL).fetchall():
            other_names[row["player_id"]].add(row["name"])
        last_series = conn.execute(LAST_SERIES_SQL).fetchone()["last"]
        conn.rollback()
    finally:
        conn.close()

    scoped = in_scope(wh)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot = (f"warehouse as read {generated_at}; last series played {last_series:%Y-%m-%d}; "
                f"{len(scoped.map_rows)} player-map rows and {len(scoped.appearances)} line-up rows in scope "
                f"({SCOPE_NOTE})")
    new, rejected = generate(scoped, presence_rows(wh), kept, dates, seed, generated_at, snapshot)

    header = [
        f"OWCS Grid generation, {generated_at}",
        f"start {args.start_date.isoformat()}, {args.days} days, seed {seed}; floor {MIN_MAPS} maps; "
        f"{MIN_ANSWERS}+ answers a cell; no column set within {REPEAT_WINDOW} days",
        snapshot,
        f"new puzzles: {len(new)}",
    ]
    text = report(new, rejected, skipped, header)
    print(text, end="")
    if args.dry_run:
        return 0
    if new:
        write_json(PUZZLES_PATH, {"version": 1, "note": FILE_NOTE, "puzzles": kept + new})
        write_json(PLAYERS_PATH, {
            "note": "The OWCS Grid autocomplete index: every player seen in a line-up, written by "
                    "scripts/grid/generate_puzzles.py. Not answers: the same list whatever the puzzle.",
            "generated_at": generated_at, "players": player_index(wh, other_names)})
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = RUNS_DIR / f"generate_{args.start_date.isoformat()}_{args.days}d_seed{seed}.txt"
    run_file.write_text(text, encoding="utf-8")
    print(f"wrote {run_file.relative_to(REPO)}" + (f", {PUZZLES_PATH.relative_to(REPO)}, {PLAYERS_PATH.relative_to(REPO)}" if new else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
