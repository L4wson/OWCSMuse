"""Competitions waiting on a scope decision, as a report: what the scheduled ingest surfaces and never acts on.

Reads what `discover` (manifest) and `crawl competitions` (history competitions) found, and the reviewed decisions
in scope/decisions.json. A competition with no decision that the classifier would include is listed for review;
nothing is written anywhere, and only `decide` (a person) puts a competition in scope.

    python tools/scope_report.py --manifest out/manifest.json --history out/history_competitions.json [--github]

`--github` also prints one ::warning:: annotation per competition, so a run that found one says so on its page.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def pending(manifest: Path, history: Path, decisions: Path) -> tuple[list[dict], int]:
    """(undecided competitions the classifier would include, undecided ones it would leave out)."""
    decided = set(json.loads(decisions.read_text(encoding="utf-8")).get("decisions", {}))
    seen: dict[str, dict] = {}
    if manifest.exists():
        for c in json.loads(manifest.read_text(encoding="utf-8")).get("championships", []):
            seen[c["championship_id"]] = {"id": c["championship_id"], "name": c.get("name"), "region": c.get("scope_region"),
                                          "season": (c.get("proposed") or {}).get("season") or c.get("season"),
                                          "tier": c.get("tier"), "would_include": bool((c.get("proposed") or {}).get("include")),
                                          "found_via": "discover"}
    if history.exists():
        for c in json.loads(history.read_text(encoding="utf-8")):
            seen.setdefault(c["championship_id"], {"id": c["championship_id"], "name": c.get("name"),
                                                   "region": c.get("derived_region"), "season": None, "tier": None,
                                                   "would_include": bool(c.get("include")), "found_via": "history crawl"})
    undecided = [c for cid, c in seen.items() if cid not in decided]
    wanted = sorted((c for c in undecided if c["would_include"]), key=lambda c: (c["season"] or 0, c["name"] or ""))
    return wanted, len(undecided) - len(wanted)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--history", default="scope/history_competitions.json")
    ap.add_argument("--decisions", default="scope/decisions.json")
    ap.add_argument("--github", action="store_true", help="also emit GitHub Actions ::warning:: annotations")
    args = ap.parse_args(argv)

    wanted, left_out = pending(Path(args.manifest), Path(args.history), Path(args.decisions))
    print("## Competitions awaiting a scope decision\n")
    if not wanted:
        print(f"None. ({left_out} undecided competition(s) the classifier would leave out; see the classification report.)")
    else:
        print(f"{len(wanted)} competition(s) the classifier would include have no reviewed decision. Nothing was "
              "included: review each and record it with `python -m owcsmuse decide <id> --include|--exclude`.\n")
        print("| championship | name | region | season | tier | found by |")
        print("|---|---|---|---|---|---|")
        for c in wanted:
            print(f"| `{c['id']}` | {c['name']} | {c['region'] or '-'} | {c['season'] or '-'} | {c['tier'] or '-'} | {c['found_via']} |")
        print(f"\n{left_out} more undecided competition(s) the classifier would leave out.")
    if args.github:
        for c in wanted:
            print(f"::warning title=Competition awaiting a scope decision::{c['name']} ({c['id']})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
