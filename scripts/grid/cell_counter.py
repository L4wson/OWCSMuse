"""Count the valid answers in every cell of a candidate 3x3 grid. Read-only: seven SELECTs, nothing else.

    python scripts/grid/cell_counter.py scripts/grid/grids/role_x_season.json
    python scripts/grid/cell_counter.py --rows role:Tank role:Damage role:Support --cols season:2024 season:2025 season:2026
    python scripts/grid/cell_counter.py <grid.json> --min-maps 10 --full 0,0 --json
    python scripts/grid/cell_counter.py --top-orgs 6

See README.md for the condition specs and what each count means.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conditions import (  # noqa: E402
    Beat, Condition, Entity, Event, MinOrgs, MinSeasons, Org, Per10, PlacedTop, Region, Role, Season, TopPer10,
    cell_answers, check_entity, stats_coverage,
)
from data import Warehouse, load  # noqa: E402
from db import connect_readonly  # noqa: E402

MIN_ANSWERS = 5         # the brief's starting floor for a standard puzzle (section 6)
DEFAULT_MIN_MAPS = 4    # Muse's own leaderboard floor (LEADERBOARD_MIN_MAPS in owcsmuse/nlq/compile.py)
ROLE_WORDS = {"tank": "Tank", "dps": "Damage", "damage": "Damage", "support": "Support"}


# ---- condition specs --------------------------------------------------------------------------------------------

def _org(wh: Warehouse, key: str) -> tuple[str, str]:
    if key not in wh.org_names:
        raise ValueError(f"unknown org key {key!r}: use an org id or team:<id> (see --top-orgs), never a name")
    return key, wh.org_names[key]


def _event(wh: Warehouse, text: str) -> Event:
    """Every included competition whose reviewed name contains all the words given."""
    words = text.lower().split()
    hits = [c for c in wh.championships.values() if all(w in c.name.lower() for w in words)]
    if not hits:
        raise ValueError(f"no competition in scope is named like {text!r}")
    return Event(frozenset(c.championship_id for c in hits), text if len(hits) > 1 else hits[0].name)


def parse_condition(wh: Warehouse, spec: str) -> Condition:
    kind, _, arg = spec.partition(":")
    try:
        if kind == "season":
            return Season(int(arg))
        if kind == "region":
            if arg not in {"na", "emea", "international"}:
                raise ValueError("region is na, emea or international")
            return Region(arg)
        if kind == "role":
            return Role(ROLE_WORDS[arg.lower()])
        if kind == "org":
            return Org(*_org(wh, arg))
        if kind == "event":
            return _event(wh, arg)
        if kind == "min_orgs":
            return MinOrgs(int(arg))
        if kind == "min_seasons":
            return MinSeasons(int(arg))
        if kind in ("per10_min", "per10_max"):
            stat, threshold, season, role = arg.split(":")
            return Per10(stat, ">=" if kind == "per10_min" else "<=", float(threshold), int(season), ROLE_WORDS[role.lower()])
        if kind == "per10_top":
            stat, n, season, role = arg.split(":")
            return TopPer10(stat, int(n), int(season), ROLE_WORDS[role.lower()])
        if kind == "placed_top":
            n, _, season = arg.partition(":")
            return PlacedTop(int(n), int(season) if season else None)
        if kind == "beat":
            return Beat(*_org(wh, arg))
    except KeyError as e:
        raise ValueError(f"bad condition {spec!r}: unknown value {e}") from None
    except ValueError as e:
        raise ValueError(f"bad condition {spec!r}: {e}") from None
    raise ValueError(f"bad condition {spec!r}: unknown kind {kind!r}")


# ---- the grid ---------------------------------------------------------------------------------------------------

@dataclass
class Cell:
    row: Condition
    col: Condition
    ids: frozenset[str]
    grain: str
    correlated: bool
    coverage: str | None


def name_of(wh: Warehouse, entity: Entity, entity_id: str) -> str:
    names = wh.player_names if entity == "player" else wh.org_names
    return names.get(entity_id) or "(no name)"


def sorted_answers(wh: Warehouse, entity: Entity, ids: frozenset[str]) -> list[tuple[str, str]]:
    """(name, id), ordered by name then id so samples are stable between runs."""
    return sorted(((name_of(wh, entity, i), i) for i in ids), key=lambda x: (x[0].casefold(), x[1]))


def evaluate(wh: Warehouse, entity: Entity, rows: list[Condition], cols: list[Condition], min_maps: int,
             min_series: int) -> list[list[Cell]]:
    for cond in rows + cols:
        check_entity(entity, cond)
    grid = []
    for r in rows:
        line = []
        for c in cols:
            ans = cell_answers(wh, entity, r, c, min_maps, min_series)
            line.append(Cell(r, c, ans.ids, ans.grain, ans.correlated, stats_coverage(wh, r, c)))
        grid.append(line)
    return grid


def distinct_solution(cells: list[frozenset[str]]) -> int:
    """How many of the cells can be filled at once with no answer used twice (maximum bipartite matching)."""
    owner: dict[str, int] = {}

    def place(cell: int, seen: set[str]) -> bool:
        for answer in sorted(cells[cell]):
            if answer in seen:
                continue
            seen.add(answer)
            if answer not in owner or place(owner[answer], seen):
                owner[answer] = cell
                return True
        return False

    return sum(place(i, set()) for i in range(len(cells)))


def overlap_report(wh: Warehouse, entity: Entity, grid: list[list[Cell]]) -> dict:
    flat = [cell.ids for line in grid for cell in line]
    fits: Counter[str] = Counter()
    for ids in flat:
        fits.update(ids)
    by_count: dict[int, int] = defaultdict(int)
    for n in fits.values():
        by_count[n] += 1
    top = sorted(fits.items(), key=lambda kv: (-kv[1], name_of(wh, entity, kv[0]).casefold(), kv[0]))[:8]
    row_sets = [frozenset().union(*(c.ids for c in line)) for line in grid]
    col_sets = [frozenset().union(*(grid[r][c].ids for r in range(len(grid)))) for c in range(len(grid[0]))]
    return {
        "distinct_answers": len(fits),
        "cells_fillable_with_distinct_answers": distinct_solution(flat),
        "answers_by_cells_fitted": dict(sorted(by_count.items())),
        "most_reusable": [{"id": i, "name": name_of(wh, entity, i), "cells": n} for i, n in top],
        "answers_fitting_a_whole_row": [sum(1 for i in s if all(i in c.ids for c in line))
                                        for s, line in zip(row_sets, grid, strict=True)],
        "answers_fitting_a_whole_column": [sum(1 for i in s if all(i in grid[r][c].ids for r in range(len(grid))))
                                           for c, s in enumerate(col_sets)],
    }


# ---- output -----------------------------------------------------------------------------------------------------

def print_text(wh: Warehouse, name: str, entity: Entity, grid: list[list[Cell]], samples: int, min_maps: int,
               full: set[tuple[int, int]]) -> None:
    print(f"# {name}")
    print(f"answer entity: {entity}; min maps for a role or stat cell: {min_maps}; flag below {MIN_ANSWERS} answers\n")
    width = max(len(c.col.label) for c in grid[0]) + 2
    left = max(len(line[0].row.label) for line in grid) + 2
    print(" " * left + "".join(c.col.label.ljust(width) for c in grid[0]))
    for line in grid:
        counts = "".join((f"{len(c.ids)}" + (" (!)" if len(c.ids) < MIN_ANSWERS else "")).ljust(width) for c in line)
        print(line[0].row.label.ljust(left) + counts)
    print()
    for r, line in enumerate(grid):
        for c, cell in enumerate(line):
            flag = f"  ** under {MIN_ANSWERS} **" if len(cell.ids) < MIN_ANSWERS else ""
            print(f"[{r},{c}] {cell.row.label} x {cell.col.label}: {len(cell.ids)}{flag}")
            how = "both conditions on the same rows" if cell.correlated else "each condition on its own rows"
            print(f"      counted by: {cell.grain}; {how}")
            if cell.coverage:
                print(f"      coverage: {cell.coverage}")
            answers = sorted_answers(wh, entity, cell.ids)
            shown = answers if (r, c) in full else answers[:samples]
            for answer_name, answer_id in shown:
                print(f"      {answer_name}  [{answer_id}]")
            if len(answers) > len(shown):
                print(f"      ... {len(answers) - len(shown)} more")
    report = overlap_report(wh, entity, grid)
    print("\noverlap")
    print(f"  distinct answers across the grid: {report['distinct_answers']}")
    print(f"  cells fillable with no answer reused: {report['cells_fillable_with_distinct_answers']} of 9")
    print(f"  answers by number of cells they fit: {report['answers_by_cells_fitted']}")
    print(f"  answers that fit a whole row: {report['answers_fitting_a_whole_row']}; "
          f"a whole column: {report['answers_fitting_a_whole_column']}")
    print("  most reusable: " + ", ".join(f"{a['name']} ({a['cells']})" for a in report["most_reusable"]))


def as_json(wh: Warehouse, name: str, entity: Entity, grid: list[list[Cell]], min_maps: int) -> dict:
    return {
        "name": name, "entity": entity, "min_maps": min_maps, "min_answers": MIN_ANSWERS,
        "cells": [
            {"row": r, "col": c, "row_label": cell.row.label, "col_label": cell.col.label, "count": len(cell.ids),
             "under_populated": len(cell.ids) < MIN_ANSWERS, "grain": cell.grain, "correlated": cell.correlated,
             "coverage": cell.coverage,
             "answers": [{"id": i, "name": n} for n, i in sorted_answers(wh, entity, cell.ids)]}
            for r, line in enumerate(grid) for c, cell in enumerate(line)
        ],
        "overlap": overlap_report(wh, entity, grid),
    }


def top_orgs(wh: Warehouse, n: int) -> None:
    players: dict[str, set[str]] = defaultdict(set)
    seasons: dict[str, set[int]] = defaultdict(set)
    for a in wh.appearances:
        players[a.org_key].add(a.player_id)
        seasons[a.org_key].add(a.season)
    ranked = sorted(players.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:n]
    print("team identities by distinct players in their series line-ups (identity at each series' own time)")
    for key, ids in ranked:
        print(f"  {len(ids):3d}  {wh.org_names.get(key, '(no name)'):28s} {sorted(seasons[key])}  [{key}]")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Count valid answers per cell of a 3x3 grid (read-only).")
    p.add_argument("grid", nargs="?", help="a grid definition JSON file: {name, entity, rows[3], cols[3]}")
    p.add_argument("--rows", nargs=3, metavar="SPEC", help="three row conditions, instead of a file")
    p.add_argument("--cols", nargs=3, metavar="SPEC", help="three column conditions, instead of a file")
    p.add_argument("--entity", choices=["player", "team"], default="player", help="with --rows/--cols")
    p.add_argument("--min-maps", type=int, default=DEFAULT_MIN_MAPS,
                   help=f"maps a player needs for a role or stat cell (default {DEFAULT_MIN_MAPS})")
    p.add_argument("--min-series", type=int, default=1, help="series needed for a series-grain cell (default 1)")
    p.add_argument("--samples", type=int, default=10, help="sample answers printed per cell (default 10)")
    p.add_argument("--full", action="append", default=[], metavar="R,C", help="print every answer of this cell")
    p.add_argument("--json", action="store_true", help="every cell's full answer set as JSON")
    p.add_argument("--top-orgs", type=int, metavar="N", help="list the N team identities with the most players, then stop")
    args = p.parse_args(argv)
    if args.min_maps < 1 or args.min_series < 1:
        p.error("--min-maps and --min-series must be at least 1")

    conn = connect_readonly()
    try:
        wh = load(conn)
    finally:
        conn.close()

    if args.top_orgs:
        top_orgs(wh, args.top_orgs)
        return 0
    if args.grid:
        spec = json.loads(Path(args.grid).read_text(encoding="utf-8"))
        name, entity, row_specs, col_specs = spec["name"], spec.get("entity", "player"), spec["rows"], spec["cols"]
    elif args.rows and args.cols:
        name, entity, row_specs, col_specs = "ad hoc grid", args.entity, args.rows, args.cols
    else:
        p.error("give a grid file, or --rows and --cols")
    if len(row_specs) != 3 or len(col_specs) != 3:
        p.error("a grid is three row conditions by three column conditions")
    try:
        rows = [parse_condition(wh, s) for s in row_specs]
        cols = [parse_condition(wh, s) for s in col_specs]
        grid = evaluate(wh, entity, rows, cols, args.min_maps, args.min_series)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(as_json(wh, name, entity, grid, args.min_maps), indent=1, ensure_ascii=False))
    else:
        full = {tuple(int(x) for x in f.split(",")) for f in args.full}
        print_text(wh, name, entity, grid, args.samples, args.min_maps, full)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
