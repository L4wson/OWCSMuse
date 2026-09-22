"""Run a reconciliation from what is already stored: no request to Liquipedia is made anywhere in this module.

  raw_payloads (source='liquipedia', the responses the coverage ledger points at)
     -> parse + dedupe -> propose team names -> match in tiers -> store liquipedia_matches / liquipedia_links -> report
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg.types.json import Jsonb

from ..resolve import fold
from .matches import Duplicates, LPMatch, dedupe, parse_rows
from .model import FaceitSide, load_faceit_side
from .reconcile import DEFAULT_WINDOW, EXACT, Result, Window, reconcile
from .teams import DEFAULT_TEAM_MAP_PATH, TeamMap, TeamProposal, make_resolver, propose

DEFAULT_LINK_DECISIONS_PATH = "scope/liquipedia_link_decisions.json"
DEFAULT_MAP_PATH = "scope/liquipedia_map.json"


class LinkDecisions:
    """A reviewer's word on ambiguous matches. Same gate, same shape as the org and scope decision files."""

    def __init__(self, path: str | Path = DEFAULT_LINK_DECISIONS_PATH) -> None:
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self.data = dict(json.loads(self.path.read_text(encoding="utf-8")).get("decisions") or {})

    def set(self, lp_objectname: str, faceit_match_id: Optional[str], note: Optional[str] = None) -> dict[str, Any]:
        d = {"faceit_match_id": faceit_match_id, "note": note,
             "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.data[lp_objectname] = {k: v for k, v in d.items() if v is not None or k == "faceit_match_id"}
        return self.data[lp_objectname]

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"note": ("Reviewed decisions on Liquipedia matches the reconciler could not link on its own. Keys are "
                        "Liquipedia objectnames; faceit_match_id names the FACEIT match it is, or is null when there is "
                        "none. Edit by hand or with `python -m owcsmuse liquipedia links decide`."),
               "decisions": dict(sorted(self.data.items()))}
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path


@dataclass
class Run:
    result: Result
    lps: list[LPMatch]
    faceit: list[FaceitSide]
    proposals: list[TeamProposal]
    duplicates: Duplicates
    raw_ids: list[int]
    comps_of_page: dict[str, set[str]]
    page_names: dict[str, str]                     # pagename -> FACEIT competition name it is mapped to
    time_offsets: list[float] = field(default_factory=list)      # exact pairs: FACEIT time minus Liquipedia time, minutes
    use_proposals: bool = True
    bye_times: dict[str, list[datetime]] = field(default_factory=dict)   # competition -> when its bracket byes were created

    def alignment(self) -> dict[str, Any]:
        v = sorted(self.time_offsets)
        if not v:
            return {}
        w = self.result.window
        return {"pairs": len(v), "median_min": round(statistics.median(v)), "p05_min": round(v[int(len(v) * .05)]),
                "p95_min": round(v[min(len(v) - 1, int(len(v) * .95))]), "min": round(v[0]), "max": round(v[-1]),
                "inside_window": sum(1 for x in v if -w.before_min <= x <= w.after_min)}


def load_map(path: str = DEFAULT_MAP_PATH) -> tuple[dict[str, set[str]], dict[str, str]]:
    pages = json.loads(Path(path).read_text(encoding="utf-8"))["pages"]
    comps: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for cid, e in pages.items():
        page = e["page"].replace(" ", "_")
        comps.setdefault(page, set()).add(cid)
        names[page] = e["name"]
    return comps, names


def stored_match_rows(conn: psycopg.Connection, field_name: str = "pagename") -> tuple[list[dict[str, Any]], list[int]]:
    """Every record of the responses the coverage ledger says hold the planned pages (never the probes)."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT unnest(raw_ids) AS id FROM liquipedia_coverage WHERE endpoint = 'match' AND field = %s",
                    (field_name,))
        ids = sorted(r["id"] for r in cur.fetchall())
        rows: list[tuple[int, dict[str, Any]]] = []
        for rid in ids:
            cur.execute("SELECT payload FROM raw_payloads WHERE id = %s AND source = 'liquipedia'", (rid,))
            for r in (cur.fetchone()["payload"] or {}).get("result") or []:
                rows.append((rid, r))
    conn.commit()
    # parse per response so each record remembers the response it came from
    return [{"_raw_id": rid, **r} for rid, r in rows], ids


def run_reconciliation(conn: psycopg.Connection, *, team_map_path: str = DEFAULT_TEAM_MAP_PATH,
                       decisions_path: str = DEFAULT_LINK_DECISIONS_PATH, map_path: str = DEFAULT_MAP_PATH,
                       window: Window = DEFAULT_WINDOW, use_proposals: bool = True, wiki: str = "overwatch") -> Run:
    rows, raw_ids = stored_match_rows(conn)
    if not rows:
        raise RuntimeError("no stored Liquipedia match responses: the Stage 1 fetch has not been run "
                           "(`liquipedia run --execute`), and this command never sends a request itself")
    lps: list[LPMatch] = []
    for rid in raw_ids:
        lps += parse_rows([{k: v for k, v in r.items() if k != "_raw_id"} for r in rows if r["_raw_id"] == rid], rid, wiki)
    lps, dups = dedupe(lps)
    comps_of_page, page_names = load_map(map_path)
    faceit = load_faceit_side(conn, sorted({c for cs in comps_of_page.values() for c in cs}))
    by_id = {f.match_id: f for f in faceit}

    decided = TeamMap(team_map_path)
    pairs = [(lp, by_id[lp.faceit_match_id]) for lp in lps if lp.faceit_match_id in by_id and not lp.placeholder]
    fnames: dict[str, set[str]] = {}
    org_regions: dict[str, set[str]] = {}
    for f in faceit:
        for n, o in ((f.name1, f.org1), (f.name2, f.org2)):
            if o:
                fnames.setdefault(fold(n), set()).add(o)
                if f.region:
                    org_regions.setdefault(o, set()).add(f.region)
    proposals = propose(pairs, [n for lp in lps for n in (lp.team1, lp.team2)], decided, fnames, org_regions)
    resolver = make_resolver(decided, {p.key: p for p in proposals}, use_proposals)
    result = reconcile(lps, faceit, resolver, comps_of_page, window, LinkDecisions(decisions_path).data)
    run = Run(result, lps, faceit, proposals, dups, raw_ids, comps_of_page, page_names, use_proposals=use_proposals)
    with conn.cursor() as cur:
        cur.execute("""SELECT championship_id, coalesce(started_at, finished_at, scheduled_at) AS t FROM matches
                        WHERE ingest_state = 'skipped' AND ingest_error LIKE 'bye:%%' AND championship_id = ANY(%s)""",
                    (sorted({c for cs in comps_of_page.values() for c in cs}),))
        for r in cur.fetchall():
            if r["t"]:
                run.bye_times.setdefault(r["championship_id"], []).append(r["t"])
    conn.commit()
    run.time_offsets = [(by_id[lk.faceit_id].time - lk.lp.played_at).total_seconds() / 60
                        for lk in result.links if lk.tier == EXACT and lk.faceit_id and by_id[lk.faceit_id].time]
    return run


def store_run(conn: psycopg.Connection, run: Run) -> dict[str, int]:
    """Replace liquipedia_matches / liquipedia_links with this run's. Idempotent; reviewer decisions come from the file."""
    comp_by_page = {p: sorted(c)[0] for p, c in run.comps_of_page.items()}
    with conn.cursor() as cur:
        cur.execute("DELETE FROM liquipedia_links")
        cur.execute("DELETE FROM liquipedia_matches")
        for m in run.lps:
            cur.execute(
                """INSERT INTO liquipedia_matches
                     (objectname, raw_id, match2id, bracket_id, pagename, page_url, region, championship_id, played_at,
                      best_of, finished, winner, walkover, team1_name, team2_name, score1, score2, status1, status2,
                      section, faceit_match_id, n_games, placeholder)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (m.objectname, m.raw_id, m.match2id, m.bracket_id, m.pagename, m.page_url, m.region,
                 comp_by_page.get(m.pagename), m.played_at, m.best_of, m.finished, m.winner, m.walkover, m.team1,
                 m.team2, m.score1, m.score2, m.status1, m.status2, m.section, m.faceit_match_id, m.n_games,
                 m.placeholder))
        n = 0
        for lk in run.result.links:
            cur.execute(
                """INSERT INTO liquipedia_links
                     (lp_objectname, faceit_match_id, tier, basis, provisional, decision, candidates, evidence, disagreements)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (lk.lp.objectname, lk.faceit_id, lk.tier, lk.basis, lk.provisional, lk.decision, Jsonb(lk.candidates),
                 Jsonb(lk.evidence), Jsonb(lk.disagreements)))
            n += 1
    conn.commit()
    return {"liquipedia_matches": len(run.lps), "liquipedia_links": n}


def summary(run: Run) -> dict[str, Any]:
    tiers = Counter(lk.tier for lk in run.result.links)
    return {"liquipedia_records": len(run.lps), "placeholders_excluded": len(run.result.placeholders),
            "faceit_series_in_these_competitions": len(run.faceit), "tiers": dict(tiers),
            "provisional_links": sum(1 for lk in run.result.links if lk.provisional and lk.faceit_id),
            "faceit_without_liquipedia": len(run.result.faceit_unlinked),
            "linked_pairs_that_disagree": sum(1 for lk in run.result.links if lk.faceit_id and lk.disagreements),
            "region_rejections": len(run.result.region_rejections),
            "duplicate_records_dropped": len(run.duplicates.same_match),
            "faceit_ids_claimed_twice": len(run.duplicates.same_faceit_id), "time_alignment": run.alignment(),
            "raw_payload_ids": run.raw_ids}
