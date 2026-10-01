"""Apply both name-change signals to every team id that carried more than one name, and write the review report.

    python tools/window_review.py [scope/team_name_history_2026-10-01.json] [scope/org_window_review.md]

Reads a name history captured from production (or `python -m owcsmuse orgs propose` output in a later version) and
writes one proposal per team id: which names are eras of their own (pickups) and which are the same organisation
(renames). It decides nothing: the proposals are for a person, and the ones where the two signals disagree are listed
first because those need a person most.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from owcsmuse.orgs import classify_name_change, stage_of  # noqa: E402

DECIDED = {"bb5dd404": "Virtus pro from 2025-01-31T19:17:07Z (decided; the first 'Virtuspro' sighting)",
           "2b7f8ef6": "Extinction from its first 'Extinction' sighting (decided); Avidity is the id's own era",
           "a35f8d47": "Extinction from its first 'Extinction' sighting until the first 'The Kafe' sighting (decided); The Kafe is the id's own era"}


def d(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def review(histories: dict[str, list[dict]]) -> list[dict]:
    out = []
    for team_id, names in histories.items():
        hist = sorted(((n["name"], d(n["first_seen"]), d(n["last_seen"])) for n in names), key=lambda x: x[1])
        changes = [classify_name_change(hist[i], hist[i + 1]) for i in range(len(hist) - 1)]
        # eras: a pickup starts a new one; a rename extends the current one; a disagreement is left open for a person
        eras: list[dict] = [{"names": [hist[0][0]], "from": hist[0][1], "to": hist[0][2], "open": False}]
        for c, nxt in zip(changes, hist[1:], strict=True):
            if c["verdict"] == "pickup":
                eras.append({"names": [nxt[0]], "from": nxt[1], "to": nxt[2], "open": False})
            elif c["verdict"] == "rename":
                eras[-1]["names"].append(nxt[0])
                eras[-1]["to"] = max(eras[-1]["to"], nxt[2])
            else:
                eras[-1]["names"].append(nxt[0] + " (?)")
                eras[-1]["to"] = max(eras[-1]["to"], nxt[2])
                eras[-1]["open"] = True
        out.append({"team_id": team_id, "names": [n for n, *_ in hist], "changes": changes, "eras": eras,
                    "needs_person": any(c["verdict"] == "disagree" for c in changes),
                    "decided": next((v for k, v in DECIDED.items() if team_id.startswith(k)), None)})
    out.sort(key=lambda r: (not r["needs_person"], -len(r["eras"]), r["team_id"]))
    return out


def render(rows: list[dict], source: str) -> str:
    L = ["# Team-id windows: review", "",
         f"Source: `{source}`. {len(rows)} team ids carry more than one FACEIT name. Two signals per name change: the "
         "handle (a new name that contains or extends the old one is a rename by the same organisation) and the stage "
         "boundary (a wholly different name first seen in a new stage is a roster pickup by another organisation; in OWCS "
         "a pickup lands on a stage boundary). One proposal per id. Nothing here is decided: a window is applied only "
         "through `scope/org_decisions.json` (`orgs decide --from-name ... --to-name ...`).", "",
         f"{sum(1 for r in rows if r['needs_person'])} id(s) where the signals disagree, listed first; "
         f"{sum(1 for r in rows if not r['needs_person'] and len(r['eras']) > 1)} with a clear pickup; "
         f"{sum(1 for r in rows if len(r['eras']) == 1 and not r['needs_person'])} rename-only (one organisation, no window).", ""]
    for r in rows:
        tag = "SIGNALS DISAGREE" if r["needs_person"] else ("PICKUP" if len(r["eras"]) > 1 else "RENAME ONLY")
        L.append(f"## `{r['team_id'][:8]}` - {tag}")
        L.append("")
        L.append("| # | name | first seen | last seen | stage at first / last |")
        L.append("|---|---|---|---|---|")
        L.extend(_name_table(r))
        L.append("")
        for c in r["changes"]:
            mark = {"rename": "rename", "pickup": "PICKUP", "disagree": "DISAGREE"}[c["verdict"]]
            L.append(f"- **{mark}**: {c['old']} -> {c['new']}: {c['why']}")
        L.append("")
        L.append("**Proposal:** " + _proposal(r))
        if r["decided"]:
            L.append("")
            L.append(f"_Already decided: {r['decided']}._")
        L.append("")
    return "\n".join(L) + "\n"


def _name_table(r: dict) -> list[str]:
    rows = []
    for i, n in enumerate(r["_hist"], 1):
        rows.append(f"| {i} | {n[0]} | {n[1]:%Y-%m-%d} | {n[2]:%Y-%m-%d} | {stage_of(n[1]) or '?'} / {stage_of(n[2]) or '?'} |")
    return rows


def _proposal(r: dict) -> str:
    if r["needs_person"]:
        return ("no window proposed; a person must say what the disagreeing change is (a temporary rename of one roster, "
                "or a pickup inside a stage). Eras as the signals read them: " + "; ".join(_era(e) for e in r["eras"]))
    if len(r["eras"]) == 1:
        return f"one organisation, no window: {_era(r['eras'][0])}"
    return "one era per pickup, each the team id's own unless an org is decided for it: " + "; ".join(_era(e) for e in r["eras"])


def _era(e: dict) -> str:
    names = " / ".join(e["names"])
    return f"[{names}] from the first sighting of '{e['names'][0].replace(' (?)', '')}' ({e['from']:%Y-%m-%d}) to {e['to']:%Y-%m-%d}"


def main(argv: list[str]) -> int:
    src = Path(argv[1] if len(argv) > 1 else "scope/team_name_history_2026-10-01.json")
    dst = Path(argv[2] if len(argv) > 2 else "scope/org_window_review.md")
    doc = json.loads(src.read_text(encoding="utf-8"))
    rows = review(doc["histories"])
    for r in rows:
        r["_hist"] = sorted(((n["name"], d(n["first_seen"]), d(n["last_seen"])) for n in doc["histories"][r["team_id"]]), key=lambda x: x[1])
    dst.write_text(render(rows, str(src)), encoding="utf-8")
    print(json.dumps({"report": str(dst), "team_ids": len(rows),
                      "signals_disagree": [r["team_id"][:8] for r in rows if r["needs_person"]],
                      "pickups": [r["team_id"][:8] for r in rows if not r["needs_person"] and len(r["eras"]) > 1],
                      "rename_only": [r["team_id"][:8] for r in rows if not r["needs_person"] and len(r["eras"]) == 1]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
