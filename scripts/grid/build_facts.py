"""Write the two reviewed fact files Grid's clues read: stage results and individual awards. Read-only on the database.

    python scripts/grid/build_facts.py            # writes scope/grid_stages.json and scope/grid_awards.json
    python scripts/grid/build_facts.py --dry-run  # prints what it would write

Neither fact is a column in Muse's warehouse, so each is derived once, written to `scope/` with a source link on every
entry, and reviewed by a person there:

- **Stage results** (`scope/grid_stages.json`). A stage's grand final is the last series of its playoff bracket; its
  winner and loser are the stage's champion and runner-up. Each is cross-checked against every other record held:
  Liquipedia's own match record of that final, FACEIT's result where FACEIT has one, and Liquipedia's placement
  table where one was fetched. An entry whose records disagree is written with `"agree": false` and no clue uses it.
- **Awards** (`scope/grid_awards.json`). The individual rows of Liquipedia's prize pools, which Muse's placements
  parser leaves out. Every entry is written `"reviewed": false`; the generator uses reviewed entries only.

This sends nothing to Liquipedia: it reads responses Muse already stored. Running it again keeps every `reviewed`
flag and `note` a person has set, matched by the entry's key.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
STAGES_PATH = REPO / "scope" / "grid_stages.json"
AWARDS_PATH = REPO / "scope" / "grid_awards.json"
LIQUIPEDIA = "https://liquipedia.net/overwatch/"

STAGE_NAME = re.compile(r"^OWCS (\d{4}) (NA|EMEA) Stage (\d)(?: (.+))?$")
PLAYOFF_PHASES = {"Playoffs", "Main Event"}

PLAYOFF_SERIES_SQL = """
    SELECT championship_display_name(c.name) AS competition, c.championship_id, s.series_id, s.played_at,
           s.score1, s.score2, s.winner_side, s.has_player_stats, s.liquipedia_page_url,
           a.org_key AS key1, a.display_name AS name1, b.org_key AS key2, b.display_name AS name2,
           lm.match2id, lm.winner AS lp_winner, lm.team1_name AS lp_name1, lm.team2_name AS lp_name2, lm.pagename,
           m.winner_team_id AS faceit_winner, m.faction1_team_id AS faceit_team1, s.lp_flip
      FROM series s
      JOIN championships c ON c.championship_id = s.championship_id AND c.include
      JOIN LATERAL team_identity_at(s.side1_team_id, s.played_at) a ON true
      JOIN LATERAL team_identity_at(s.side2_team_id, s.played_at) b ON true
      LEFT JOIN liquipedia_matches lm ON lm.objectname = s.lp_objectname
      LEFT JOIN matches m ON m.match_id = s.faceit_match_id
     WHERE c.tier = 'main' AND c.scope_region IN ('na', 'emea')
     ORDER BY s.played_at, s.series_id
"""
PLACEMENT_PAYLOADS_SQL = "SELECT id, payload FROM raw_payloads WHERE endpoint = 'liquipedia:placement' AND http_status = 200 ORDER BY id"
PLAYER_PAGES_SQL = "SELECT anchor AS page, entity_id AS player_id FROM entity_anchors WHERE anchor_kind = 'player_page' AND entity_type = 'player'"
EVENT_LINEUPS_SQL = """
    SELECT DISTINCT l.player_id, s.championship_id
      FROM series s JOIN championships c ON c.championship_id = s.championship_id AND c.include
      JOIN series_lineups l ON l.match_id = s.match_id
"""
CHAMPIONSHIP_NAMES_SQL = "SELECT championship_id, championship_display_name(name) AS name, liquipedia_page FROM championships WHERE include"


def fold(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def bracket_round(match2id: str | None) -> tuple[int, int]:
    """("..._R05-M001") -> (5, 1): the round and the match within it, for finding a bracket's last match."""
    m = re.search(r"_R(\d+)-M(\d+)$", match2id or "")
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def stage_results(series: list[dict], placements: dict[str, dict[str, str]]) -> list[dict]:
    """One entry per stage, from its playoff series (already in played order)."""
    by_stage: dict[tuple[int, str, int], list[dict]] = defaultdict(list)
    for s in series:
        m = STAGE_NAME.match(s["competition"])
        if m and (m.group(4) or "") in PLAYOFF_PHASES:
            by_stage[(int(m.group(1)), m.group(2).lower(), int(m.group(3)))].append(s)

    out = []
    for (season, region, number), played in sorted(by_stage.items()):
        final = played[-1]
        side = final["winner_side"]
        winner = {"org_key": final[f"key{side}"], "name": final[f"name{side}"]}
        loser = {"org_key": final[f"key{3 - side}"], "name": final[f"name{3 - side}"]}

        # Liquipedia's own record of that match: is it the bracket's last match, and whom does it name the winner?
        last_round = max((bracket_round(p["match2id"]) for p in played), default=(-1, -1))
        lp_is_final = final["match2id"] is not None and bracket_round(final["match2id"]) == last_round
        lp_winner = final[f"lp_name{final['lp_winner']}"] if final["lp_winner"] in (1, 2) else None
        lp_side = None
        if final["lp_winner"] in (1, 2):
            lp_side = (3 - final["lp_winner"]) if final["lp_flip"] else final["lp_winner"]
        # FACEIT's result, where FACEIT recorded one
        faceit_side = None
        if final["faceit_winner"]:
            faceit_side = 1 if final["faceit_winner"] == final["faceit_team1"] else 2
        # Liquipedia's placement table for the stage page, where one was fetched
        placed = placements.get(final["pagename"] or "", {})
        first, second = placed.get("1"), placed.get("2")
        lp_loser = final[f"lp_name{3 - final['lp_winner']}"] if final["lp_winner"] in (1, 2) else None
        placement_ok = None if not first else (fold(first) == fold(lp_winner) and fold(second) == fold(lp_loser))

        checks = {
            "liquipedia_match_winner": lp_winner,
            "liquipedia_match_is_bracket_final": lp_is_final,
            "faceit_result": None if faceit_side is None else final[f"name{faceit_side}"],
            "liquipedia_placement_first": first,
            "liquipedia_placement_second": second,
        }
        agree = bool(lp_is_final and lp_side == side and (faceit_side is None or faceit_side == side)
                     and placement_ok is not False)
        with_stats = sum(1 for p in played if p["has_player_stats"])
        out.append({
            "key": f"{season}-{region}-{number}",
            "name": f"OWCS {season} {region.upper()} Stage {number}",
            "season": season, "region": region, "stage": number,
            "playoff_championships": sorted({p["championship_id"] for p in played}),
            "final": {"series_id": final["series_id"], "played_at": final["played_at"].strftime("%Y-%m-%dT%H:%MZ"),
                      "score": f"{final[f'score{side}']}-{final[f'score{3 - side}']}"},
            "winner": winner, "runner_up": loser,
            "checks": checks, "agree": agree,
            "playoff_series": len(played), "playoff_series_with_player_stats": with_stats,
            "final_has_player_stats": bool(final["has_player_stats"]),
            "source": final["liquipedia_page_url"] or (LIQUIPEDIA + (final["pagename"] or "")),
            "reviewed": False, "note": "",
        })
    return out


def placement_tables(payloads: list[dict]) -> tuple[dict[str, dict[str, str]], list[dict]]:
    """(page -> {placement -> team name}, the individual award rows), from the stored /placement responses."""
    teams: dict[str, dict[str, str]] = defaultdict(dict)
    awards: dict[tuple, dict] = {}
    for payload in payloads:
        for row in payload["payload"].get("result") or []:
            page = row.get("pagename") or ""
            if row.get("opponenttype") == "team":
                if row.get("placement") and str(row.get("prizepoolindex", 1)) in ("1", "None"):
                    teams[page].setdefault(str(row["placement"]), row.get("opponentname") or "")
            elif row.get("opponenttype") == "solo":
                award = ((row.get("extradata") or {}).get("award") or "").strip()
                if award:
                    awards[(page, award, row.get("opponentname"))] = {**row, "_raw_id": payload["id"], "_award": award}
    return teams, list(awards.values())


def award_entries(rows: list[dict], pages: dict[str, str], lineups: dict[str, set[str]], championship_of: dict[str, list[str]],
                  names: dict[str, str]) -> list[dict]:
    """One entry per award. The player id is filled only when exactly one known player fits the name and the event."""
    by_handle: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for page, player_id in pages.items():
        by_handle[fold(page.split("_(")[0])].append((page, player_id))
    out = []
    for row in sorted(rows, key=lambda r: (r.get("pagename") or "", r["_award"], r.get("opponentname") or "")):
        page, handle = row.get("pagename") or "", row.get("opponentname") or ""
        candidates = by_handle.get(fold(handle), [])
        at_event = set().union(*(lineups.get(cid, set()) for cid in championship_of.get(page, [])))
        fitting = [c for c in candidates if c[1] in at_event]
        if len(fitting) == 1:
            player_id, how = fitting[0][1], f"Liquipedia page '{fitting[0][0]}', in a line-up at this event"
        elif len(candidates) == 1 and not at_event:
            player_id, how = candidates[0][1], f"Liquipedia page '{candidates[0][0]}' (no line-up held for this event)"
        else:
            player_id, how = None, f"not resolved: {len(candidates)} known players are named '{handle}', {len(fitting)} at this event"
        out.append({
            "key": f"{page}|{row['_award']}|{handle}",
            "player_id": player_id,
            "player": handle,
            "award": row["_award"],
            "event": names.get(page) or page.replace("_", " "),
            "team": (row.get("extradata") or {}).get("participantteam") or "",
            "date": (row.get("date") or "")[:10] or None,
            "source_url": LIQUIPEDIA + page,
            "source_note": f"Liquipedia /placement, stored response raw_payloads {row['_raw_id']}",
            "resolved_by": how,
            "reviewed": False, "note": "",
        })
    return out


def keep_reviews(new: list[dict], path: Path, list_key: str) -> list[dict]:
    """Carry `reviewed` and `note` over from the file on disk, so a rebuild never undoes a person's review."""
    if not path.exists():
        return new
    old = {e["key"]: e for e in json.loads(path.read_text(encoding="utf-8")).get(list_key, [])}
    for entry in new:
        before = old.get(entry["key"])
        if before:
            entry["reviewed"], entry["note"] = bool(before.get("reviewed")), before.get("note", "")
    return new


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Derive stage results and awards into scope/ (reads the database read-only).")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    from db import connect_readonly
    conn = connect_readonly()
    try:
        def rows(sql: str) -> list[dict]:
            result = conn.execute(sql).fetchall()
            conn.rollback()
            return result
        series = rows(PLAYOFF_SERIES_SQL)
        placements, award_rows = placement_tables(rows(PLACEMENT_PAYLOADS_SQL))
        pages = {r["page"]: r["player_id"] for r in rows(PLAYER_PAGES_SQL)}
        lineups: dict[str, set[str]] = defaultdict(set)
        for r in rows(EVENT_LINEUPS_SQL):
            lineups[r["championship_id"]].add(r["player_id"])
        championships = rows(CHAMPIONSHIP_NAMES_SQL)
    finally:
        conn.close()

    stages = keep_reviews(stage_results(series, placements), STAGES_PATH, "stages")
    # an award's page is an international event ("lp:<page>") or a stage page (every competition of that stage)
    championship_of: dict[str, list[str]] = defaultdict(list)
    names: dict[str, str] = {}
    for c in championships:
        if c["championship_id"].startswith("lp:"):
            page = c["championship_id"][3:]
            championship_of[page].append(c["championship_id"])
            names.setdefault(page, c["name"])
        m = STAGE_NAME.match(c["name"])
        if m:
            region_path = {"NA": "NA", "EMEA": "EMEA"}[m.group(2)]
            page = f"Overwatch_Champions_Series/{m.group(1)}/{region_path}/Stage_{m.group(3)}"
            championship_of[page].append(c["championship_id"])
            names[page] = f"OWCS {m.group(1)} {m.group(2)} Stage {m.group(3)}"
    awards = keep_reviews(award_entries(award_rows, pages, lineups, championship_of, names), AWARDS_PATH, "awards")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stage_doc = {
        "note": "OWCS NA and EMEA stage results for Grid's 'Won a stage' and 'Stage finalist' clues, derived by "
                "scripts/grid/build_facts.py from the playoff brackets: the last series of a stage's playoffs is its "
                "grand final. 'checks' holds what each other record says; 'agree' is false when any disagrees, and a "
                "clue never uses such a stage. Set 'reviewed' to true once checked against the source page. A rebuild "
                "keeps 'reviewed' and 'note'.",
        "generated_at": generated, "stages": stages,
    }
    award_doc = {
        "note": "Individual OWCS awards for Grid's 'Won an award' clue: the solo rows of Liquipedia's prize pools "
                "(CC-BY-SA 3.0), from responses Muse already stored. Written by scripts/grid/build_facts.py. The "
                "generator uses an entry only when 'reviewed' is true and 'player_id' is set. A rebuild keeps "
                "'reviewed' and 'note'.",
        "license": "CC-BY-SA 3.0", "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "generated_at": generated, "awards": awards,
    }

    for s in stages:
        stats = f"{s['playoff_series_with_player_stats']}/{s['playoff_series']} series with player stats"
        print(f"{s['name']:24s} {s['winner']['name']:22s} beat {s['runner_up']['name']:22s} {s['final']['score']}  "
              f"agree={s['agree']}  {stats}")
    print()
    for a in awards:
        print(f"{a['event']:36s} {a['award']:34s} {a['player']:12s} -> {a['player_id'] or 'UNRESOLVED'}")
    if not args.dry_run:
        for path, doc in ((STAGES_PATH, stage_doc), (AWARDS_PATH, award_doc)):
            path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {STAGES_PATH.relative_to(REPO)} ({len(stages)} stages) and {AWARDS_PATH.relative_to(REPO)} ({len(awards)} awards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
