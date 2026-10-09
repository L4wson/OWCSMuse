"""The plan for Stage 1, the completeness cross-check, and the one-request verification that precedes it.

Stage 1 asks Liquipedia for every match of the 2025/2026 main-series stages in
scope/liquipedia_map.json and joins them to ours on the FACEIT match id Liquipedia
records. This module only PLANS that: it says how many requests it will take. It
sends nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import psycopg

from .planner import Plan, or_conditions, plan_requests
from .store import Store

MAP_PATH = "scope/liquipedia_map.json"
MATCH_ENDPOINT = "match"
# The match record field the plan filters on: `pagename`, the page the match is on (a stage's Regular_Season subpage,
# say), which is exactly what scope/liquipedia_map.json lists and is also the page a value must be attributed to.
# NOT `parent`, the enclosing stage page: for the Korea record seen in the verification request, pagename was
# .../Korea/Regular_Season and parent .../Korea. Confirmed for Korea/China rows; the first NA/EMEA rows will show
# rows_seen per page in the coverage ledger, and a short batch is flagged by the runner.
PAGE_FIELD = "pagename"

# A one-request probe of a day we know had OWCS matches (2026-06-13, S9 regular season week 1): enough rows to show the
# record's shape, few enough to be small.
VERIFY_PARAMS = {"conditions": "[[date::>2026-06-13]] AND [[date::<2026-06-14]]", "limit": 5, "order": "date ASC"}

# One request that asks for far more rows than any cap could allow, of a single small field, over every match the wiki has:
# whatever comes back is either the cap or (if fewer) proof that the wiki has fewer than that.
LIMIT_PROBE_PARAMS = {"conditions": "[[date::>2000-01-01]]", "query": "match2id", "limit": 5000, "order": "date ASC"}

FACEIT_ID = re.compile(r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def underscored(page: str) -> str:
    return page.strip().replace(" ", "_")


def stage1_wants(conn: psycopg.Connection, map_path: str = MAP_PATH, events_path: Optional[str] = None) -> dict[str, int]:
    """{Liquipedia page: how many series FACEIT has for the competitions mapped to it}, plus every Stage 4 event page
    (scope/liquipedia_events.json) at the match count its probe saw: those have no FACEIT side to count."""
    from .events import EVENTS_PATH, event_wants
    pages = json.loads(Path(map_path).read_text(encoding="utf-8"))["pages"]
    with conn.cursor() as cur:
        cur.execute("""SELECT championship_id, count(*) AS n FROM matches
                        WHERE championship_id = ANY(%s) AND ingest_state IN ('complete', 'result_only')
                        GROUP BY 1""", (list(pages),))
        counts = {r["championship_id"]: int(r["n"]) for r in cur.fetchall()}
    wants: dict[str, int] = {}
    for cid, entry in pages.items():
        page = underscored(entry["page"])
        wants[page] = wants.get(page, 0) + counts.get(cid, 0)
    for page, n in event_wants(events_path or EVENTS_PATH).items():
        wants[page] = max(wants.get(page, 0), n)
    return wants


def stage1_plan(conn: psycopg.Connection, store: Store, *, limit: int, wiki: str, budget: dict[str, Any],
                field_name: str = PAGE_FIELD, refresh: bool = False, map_path: str = MAP_PATH) -> Plan:
    return plan_requests(store, endpoint=MATCH_ENDPOINT, field_name=field_name, wants=stage1_wants(conn, map_path),
                         limit=limit, wiki=wiki, order="date ASC", budget=budget, refresh=refresh)


def describe_shape(payload: Any, status: int, headers: dict[str, str], raw_id: int, n_bytes: int) -> dict[str, Any]:
    """What a response looks like, for the person deciding how to parse it. Values are truncated."""
    rows = list((payload or {}).get("result") or []) if isinstance(payload, dict) else []
    first = rows[0] if rows else {}

    def brief(v: Any) -> Any:
        if isinstance(v, (dict, list)):
            s = json.dumps(v, ensure_ascii=False)
            return s if len(s) <= 160 else s[:157] + "..."
        return v if not isinstance(v, str) or len(v) <= 100 else v[:97] + "..."

    text = json.dumps(payload, ensure_ascii=False) if payload is not None else ""
    return {
        "http_status": status, "raw_payloads_id": raw_id, "bytes": n_bytes,
        "response_headers": {k: v for k, v in sorted(headers.items())
                             if k in ("content-type", "content-encoding", "retry-after", "date") or "ratelimit" in k
                             or "limit" in k or "remaining" in k or "reset" in k},
        "top_level_keys": sorted(payload) if isinstance(payload, dict) else type(payload).__name__,
        "warnings_or_errors": {k: brief(payload[k]) for k in ("error", "warning", "warnings") if isinstance(payload, dict) and k in payload},
        "rows_returned": len(rows),
        "avg_bytes_per_row": round(n_bytes / len(rows)) if rows else None,
        "first_row_fields": {k: brief(v) for k, v in first.items()},
        "faceit_match_ids_found": sorted(set(FACEIT_ID.findall(text))),
        "where_faceit_id_appears": sorted({k for r in rows for k, v in r.items() if FACEIT_ID.search(json.dumps(v))}),
    }


# ------------------------------------------------------------------------------ one request: do these pages exist?

PROBE_LIMIT = 500


def page_probe_params(pages: list[str], limit: int = PROBE_LIMIT) -> dict[str, Any]:
    """ONE request that asks, for every page in `pages` at once, for the `pagename` of the matches on it.

    Only that one small field comes back, so the answer is cheap; a page with no rows is a page with no matches at
    that name (a wrong path, or a page that holds no {{Match}} templates), and the report says which.
    """
    return {"conditions": or_conditions(PAGE_FIELD, [underscored(p) for p in pages]), "query": PAGE_FIELD,
            "limit": limit, "order": "pagename ASC"}


def project_page_probe(pages: list[str], budget: dict[str, Any], limit: int = PROBE_LIMIT) -> dict[str, Any]:
    """What the probe will cost, before anything is sent."""
    params = page_probe_params(pages, limit)
    return {"requests": 1, "pages": [underscored(p) for p in pages], "condition_chars": len(params["conditions"]),
            "rows_asked_for_at_most": limit, "budget": budget}


def probe_pages(client, pages: list[str], limit: int = PROBE_LIMIT) -> dict[str, Any]:
    """Send the single probe request and say, per page, how many matches Liquipedia holds on it."""
    from collections import Counter

    got = client.get(MATCH_ENDPOINT, page_probe_params(pages, limit))
    seen = Counter(underscored(str(r.get("pagename") or "")).lower() for r in got.rows)
    per_page = {underscored(p): seen.get(underscored(p).lower(), 0) for p in pages}
    return {"requests_sent": client.sent, "from_cache": got.from_cache, "rows_returned": len(got.rows),
            "truncated": len(got.rows) >= limit, "found": sorted(p for p, n in per_page.items() if n),
            "not_found": sorted(p for p, n in per_page.items() if not n), "matches_per_page": per_page,
            "unexpected_pages": sorted(set(seen) - {underscored(p).lower() for p in pages})}
