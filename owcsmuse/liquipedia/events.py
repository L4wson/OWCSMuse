"""Stage 4: events that exist only on Liquipedia (World Finals, Midseason Championships, EWC 2024).

scope/liquipedia_map.json pairs a FACEIT competition with the Liquipedia page that covers it; these events have no
FACEIT competition, so they get a reviewed file of their own, scope/liquipedia_events.json, keyed by the event's root
page:

    "Overwatch_Champions_Series/2025/World_Finals": {
        "display_name": "OWCS 2025 World Finals", "season": 2025, "region": "international", "tier": "main",
        "include": true, "decided_by": "owner", "decided_at": "...",
        "pages": {"<exact pagename the probe found>": <matches on it>, ...}, "probe_raw_id": 1234
    }

`pages` is filled only from a probe response, never by guessing a path, and is what the planner fetches (expected
rows = the probe's count). `liquipedia events load` writes one championship per event, keyed `lp:<root page>`
(migration 038), and the reconciler stores each record on those pages under it, so a Liquipedia-only series has an
included championship to stand in like any FACEIT one.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import psycopg

from .planner import condition_for
from .stage1 import MATCH_ENDPOINT, PAGE_FIELD, underscored

EVENTS_PATH = "scope/liquipedia_events.json"
LP_CHAMPIONSHIP_PREFIX = "lp:"
PARENT_FIELD = "parent"
SUBPAGE_PROBE_LIMIT = 500
REGIONS = ("international",)
TIERS = ("main",)


def championship_id(root: str) -> str:
    return LP_CHAMPIONSHIP_PREFIX + underscored(root)


def load_events(path: Optional[str | Path] = None) -> dict[str, dict[str, Any]]:
    p = Path(path or EVENTS_PATH)
    if not p.exists():
        return {}
    events = json.loads(p.read_text(encoding="utf-8")).get("events") or {}
    for root, e in events.items():
        problems = [f for f in ("display_name", "season", "region", "tier", "include") if f not in e]
        if e.get("region") not in REGIONS:
            problems.append(f"region {e.get('region')!r}")
        if e.get("tier") not in TIERS:
            problems.append(f"tier {e.get('tier')!r}")
        if problems:
            raise ValueError(f"{path}: event {root!r} is missing or has an invalid {', '.join(problems)}")
    return {underscored(root): e for root, e in events.items()}


def event_wants(path: Optional[str | Path] = None) -> dict[str, int]:
    """{exact pagename: matches the probe saw on it} for every event page, to feed the planner."""
    return {underscored(page): int(n) for e in load_events(path).values() for page, n in (e.get("pages") or {}).items()}


def event_comps(path: Optional[str | Path] = None) -> tuple[dict[str, set[str]], dict[str, str]]:
    """The same shape as pipeline.load_map: {pagename: {championship id}}, {pagename: name}."""
    comps: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for root, e in load_events(path).items():
        for page in e.get("pages") or {}:
            comps.setdefault(underscored(page), set()).add(championship_id(root))
            names[underscored(page)] = e["display_name"]
    return comps, names


def load_championships(conn: psycopg.Connection, path: Optional[str | Path] = None) -> dict[str, int]:
    """Write one championship per event (the file is the whole truth for `lp:` rows: one it no longer lists goes)."""
    events = load_events(path)
    wanted = [championship_id(root) for root in events]
    with conn.cursor() as cur:
        for root, e in events.items():
            cur.execute(
                """INSERT INTO championships (championship_id, name, source, liquipedia_page, scope_region, tier, season,
                                              include, classification_source, decision_note, classified_at)
                   VALUES (%s, %s, 'liquipedia', %s, %s, %s, %s, %s, 'manual', %s, now())
                   ON CONFLICT (championship_id) DO UPDATE SET
                       name = EXCLUDED.name, liquipedia_page = EXCLUDED.liquipedia_page,
                       scope_region = EXCLUDED.scope_region, tier = EXCLUDED.tier, season = EXCLUDED.season,
                       include = EXCLUDED.include, classification_source = 'manual',
                       decision_note = EXCLUDED.decision_note, classified_at = now(), updated_at = now()""",
                (championship_id(root), e["display_name"], root, e["region"], e["tier"], int(e["season"]),
                 bool(e["include"]), e.get("note")))
        cur.execute("DELETE FROM championships WHERE source = 'liquipedia' AND NOT (championship_id = ANY(%s))",
                    (wanted,))
        removed = cur.rowcount
    conn.commit()
    return {"events": len(events), "included": sum(bool(e["include"]) for e in events.values()), "removed": removed}


# ------------------------------------------------------------------------------------------------ placements

PLACEMENT_ENDPOINT = "placement"
# Rows a placement request is planned for, per event: a prize pool lists every team once (8 to 16 at these events).
# Only the projection uses it; a batch is one request whatever the count, up to the row limit.
PLACEMENTS_PER_EVENT = 16


def placement_wants(path: Optional[str | Path] = None) -> dict[str, int]:
    """{root page: rows expected}. A prize pool sits on the event's root page, so placements are asked for by it."""
    return {root: PLACEMENTS_PER_EVENT for root, e in load_events(path).items() if e.get("pages")}


def placement_plan(store, *, limit: int, wiki: str, budget: dict[str, Any], refresh: bool = False,
                   path: Optional[str | Path] = None):
    from .planner import plan_requests
    return plan_requests(store, endpoint=PLACEMENT_ENDPOINT, field_name=PAGE_FIELD, wants=placement_wants(path),
                         limit=limit, wiki=wiki, order="pagename ASC", budget=budget, refresh=refresh)


def parse_placement(text: str) -> Optional[tuple[int, int]]:
    """'1' -> (1, 1); '3-4' -> (3, 4). None for anything else (an award, an empty placing, 'W', 'DQ')."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", text or "")
    if not m:
        return None
    hi, lo = int(m.group(1)), int(m.group(2) or m.group(1))
    return (hi, lo) if 1 <= hi <= lo else None


def placement_rows(records: list[dict[str, Any]], roots: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Team placings from /placement records, and what was left out and why. Pure: reads records.

    `roots` is {root page: championship id}. Only a team's placing on an event's root page counts; an individual award
    (`mode` award_individual, an MVP) and a prize-pool entry with no placing (a team award) are not placings. A page
    whose team placings sit in more than one prize pool is ambiguous (which pool is the event?) and is reported, never
    picked: none of its rows are kept.
    """
    by_lower = {r.lower(): (r, cid) for r, cid in roots.items()}
    kept: list[dict[str, Any]] = []
    skipped: Counter = Counter()
    pools: dict[str, set] = {}
    for r in records:
        page = underscored(str(r.get(PAGE_FIELD) or ""))
        hit = by_lower.get(page.lower())
        if not hit:
            skipped["not an event root page"] += 1
            continue
        if r.get("opponenttype") != "team" or (r.get("mode") or "").startswith("award"):
            skipped["individual award"] += 1
            continue
        place = parse_placement(str(r.get("placement") or ""))
        if not place or not (r.get("opponentname") or "").strip():
            skipped["no placing (a team award or an empty slot)"] += 1
            continue
        pools.setdefault(hit[0], set()).add(r.get("prizepoolindex"))
        kept.append({"objectname": r["objectname"], "raw_id": r.get("_raw_id"), "pagename": hit[0], "championship_id": hit[1],
                     "prizepool_index": r.get("prizepoolindex"), "placement": str(r["placement"]).strip(),
                     "place_high": place[0], "place_low": place[1], "team_name": r["opponentname"].strip(),
                     "team_template": r.get("opponenttemplate") or None, "qualifier": r.get("qualifier") or None,
                     "placed_at": (r.get("date") or "")[:19] or None})
    ambiguous = {page: sorted(p for p in ps if p is not None) for page, ps in pools.items() if len(ps) > 1}
    kept = [k for k in kept if k["pagename"] not in ambiguous]
    firsts = Counter(k["pagename"] for k in kept if k["place_high"] == 1)
    report = {"kept": len(kept), "skipped": dict(skipped), "ambiguous_prize_pools": ambiguous,
              "pages_without_one_first_place": sorted(p for p in {k["pagename"] for k in kept} if firsts.get(p) != 1)}
    return kept, report


def load_placements(conn: psycopg.Connection, path: Optional[str | Path] = None, wiki: str = "overwatch") -> dict[str, Any]:
    """Rebuild liquipedia_placements from the stored /placement responses the coverage ledger holds. Sends nothing."""
    from .attribution import page_url

    roots = {root: championship_id(root) for root in load_events(path)}
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT unnest(raw_ids) AS id FROM liquipedia_coverage WHERE endpoint = %s AND field = %s",
                    (PLACEMENT_ENDPOINT, PAGE_FIELD))
        ids = sorted(r["id"] for r in cur.fetchall())
        records: list[dict[str, Any]] = []
        for rid in ids:
            cur.execute("SELECT payload FROM raw_payloads WHERE id = %s AND source = 'liquipedia'", (rid,))
            row = cur.fetchone()
            records += [{"_raw_id": rid, **x} for x in ((row or {}).get("payload") or {}).get("result") or []]
        kept, report = placement_rows(records, roots)
        cur.execute("DELETE FROM liquipedia_placements")
        for k in kept:
            cur.execute(
                """INSERT INTO liquipedia_placements (objectname, raw_id, pagename, page_url, championship_id,
                       prizepool_index, placement, place_high, place_low, team_name, team_template, qualifier, placed_at)
                   VALUES (%(objectname)s, %(raw_id)s, %(pagename)s, %(page_url)s, %(championship_id)s, %(prizepool_index)s,
                           %(placement)s, %(place_high)s, %(place_low)s, %(team_name)s, %(team_template)s, %(qualifier)s,
                           %(placed_at)s)""", {**k, "page_url": page_url(k["pagename"], wiki)})
    conn.commit()
    return {"responses": len(ids), **report}


# ------------------------------------------------------------- one request: which subpages hold an event's matches?

def subpage_probe_params(roots: list[str], limit: int = SUBPAGE_PROBE_LIMIT) -> dict[str, Any]:
    """ONE request: every match whose page IS a candidate root or whose parent is one, two small fields each.

    `probe-pages` matches `pagename` exactly, and a LAN event's matches usually sit on subpages (Group_Stage,
    Playoffs), so it would report a real event as not found. Matching `parent` too finds the subpages without
    guessing their names; the response names each exact page, which is what the fetch then asks for.
    """
    roots = [underscored(r) for r in roots]
    conditions = "(" + " OR ".join(condition_for(f, r) for f in (PAGE_FIELD, PARENT_FIELD) for r in roots) + ")"
    return {"conditions": conditions, "query": f"{PAGE_FIELD},{PARENT_FIELD}", "limit": limit, "order": "pagename ASC"}


def project_subpage_probe(roots: list[str], budget: dict[str, Any], limit: int = SUBPAGE_PROBE_LIMIT) -> dict[str, Any]:
    params = subpage_probe_params(roots, limit)
    return {"requests": 1, "endpoint": MATCH_ENDPOINT, "roots": [underscored(r) for r in roots],
            "fields": params["query"], "condition_chars": len(params["conditions"]),
            "rows_asked_for_at_most": limit, "budget": budget}


def summarise_subpage_probe(roots: list[str], rows: list[dict[str, Any]], limit: int = SUBPAGE_PROBE_LIMIT,
                            raw_id: Optional[int] = None) -> dict[str, Any]:
    """Per candidate root: the exact pages under it and how many matches each holds. Pure: reads a response."""
    roots = [underscored(r) for r in roots]
    by_lower = {r.lower(): r for r in roots}
    pages: dict[str, Counter] = {r: Counter() for r in roots}
    unplaced: Counter = Counter()
    for row in rows:
        page = underscored(str(row.get(PAGE_FIELD) or ""))
        parent = underscored(str(row.get(PARENT_FIELD) or ""))
        root = by_lower.get(page.lower()) or by_lower.get(parent.lower())
        if root:
            pages[root][page] += 1
        else:
            unplaced[f"{page} (parent {parent})"] += 1
    return {"raw_id": raw_id, "rows_returned": len(rows), "truncated": len(rows) >= limit,
            "found": {r: dict(sorted(c.items())) for r, c in pages.items() if c},
            "not_found": [r for r, c in pages.items() if not c],
            "unplaced_rows": dict(unplaced)}


def probe_subpages(client, roots: list[str], limit: int = SUBPAGE_PROBE_LIMIT) -> dict[str, Any]:
    got = client.get(MATCH_ENDPOINT, subpage_probe_params(roots, limit))
    return {"requests_sent": client.sent, "from_cache": got.from_cache,
            **summarise_subpage_probe(roots, got.rows, limit, got.raw_id)}
