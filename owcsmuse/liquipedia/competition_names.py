"""OWCS names for FACEIT competitions: year + region + stage + phase, sourced from Liquipedia where possible.

FACEIT League numbers its seasons ("S9 NA OWCS Central - Playoffs"); the competition people follow is
"OWCS 2026 NA Stage 2 Playoffs". `scope/liquipedia_map.json` already pairs each FACEIT competition with the
Liquipedia page that covers it (reviewed in Stage 1), so the canonical year, region and stage come from the page
title, not from guessing at a season arithmetic. The phase is FACEIT's own suffix, cross-checked against the page's
shape (a stage's `Regular_Season` subpage versus the stage page itself).

Nothing here applies on its own. `propose` builds a report; a person decides in `scope/competition_names.json`;
`load` copies decisions into `competition_names`, which only `championship_display_name()` reads. The stored
FACEIT name is never touched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg

DEFAULT_DECISIONS_PATH = "scope/competition_names.json"
DEFAULT_REPORT_PATH = "scope/competition_names_report.md"
DEFAULT_MAP_PATH = "scope/liquipedia_map.json"
DEFAULT_SCOPE_PATH = "scope/decisions.json"

_PAGE = re.compile(
    r"^Overwatch[ _]Champions[ _]Series/(?P<year>20\d\d)/(?P<region>NA|EMEA)/Stage[ _](?P<stage>\d+)(?:/(?P<sub>.+))?$")
_FACEIT_LEAGUE = re.compile(r"^S(?P<season>\d+) (?P<region>NA|EMEA) OWCS Central - (?P<phase>Regular Season|Playoffs)$")
_FACEIT_2024 = re.compile(r"^OWCS (?P<year>20\d\d): (?P<region>NA|EMEA) Stage (?P<stage>\d+) - (?P<phase>.+)$")
_LEGACY = re.compile(r"^(S\d+) (EMEA|NA) OWCS Central - (.+)$")


@dataclass(frozen=True)
class PageName:
    year: int
    region: str
    stage: int
    subpage: Optional[str]


def parse_page(page: str) -> Optional[PageName]:
    """Year, region, stage and subpage from a Liquipedia page title (spaces or underscores)."""
    m = _PAGE.match((page or "").strip())
    if not m:
        return None
    return PageName(int(m["year"]), m["region"], int(m["stage"]), (m["sub"] or "").replace("_", " ") or None)


def owcs_name(year: int, region: str, stage: int, phase: str) -> str:
    return f"OWCS {year} {region} Stage {stage} {phase}"


def legacy_display(faceit_name: str) -> str:
    """What championship_display_name() returns with no reviewed name: FACEIT's name, reordered."""
    return _LEGACY.sub(r"OWCS \2 \1 \3", faceit_name)


@dataclass
class Proposal:
    championship_id: str
    faceit_name: str
    current_display: str
    proposed: Optional[str] = None
    basis: str = "none"                  # liquipedia | faceit-name | none
    page: Optional[str] = None
    flags: list[str] = field(default_factory=list)
    status: str = "pending"              # pending | decided | stale | unproposed
    decided_name: Optional[str] = None

    @property
    def effective(self) -> str:
        return self.decided_name if self.status == "decided" and self.decided_name else self.current_display


def _propose_one(cid: str, faceit_name: str, page: Optional[str]) -> Proposal:
    p = Proposal(cid, faceit_name, legacy_display(faceit_name), page=page)
    league = _FACEIT_LEAGUE.match(faceit_name)
    if page:
        pn = parse_page(page)
        if not pn:
            p.flags.append(f"Liquipedia page '{page}' is not a stage page; no name proposed")
            return p
        phase = league["phase"] if league else None
        if not phase:
            p.flags.append("FACEIT name carries no Regular Season / Playoffs suffix; phase taken from the page")
            phase = "Regular Season" if pn.subpage == "Regular Season" else "Playoffs"
        shape = "Regular Season" if pn.subpage == "Regular Season" else ("Playoffs" if pn.subpage is None else pn.subpage)
        if shape != phase:
            p.flags.append(f"FACEIT says {phase} but the page's shape says {shape}")
        if league and league["region"] != pn.region:
            p.flags.append(f"FACEIT region {league['region']} differs from the page's {pn.region}")
        p.proposed, p.basis = owcs_name(pn.year, pn.region, pn.stage, phase), "liquipedia"
        return p
    m = _FACEIT_2024.match(faceit_name)
    if m:
        p.proposed = owcs_name(int(m["year"]), m["region"], int(m["stage"]), m["phase"])
        p.basis = "faceit-name"
        p.flags.append("no Liquipedia page is mapped; year, region and stage are already in FACEIT's own name")
        return p
    p.flags.append("no Liquipedia page is mapped and the FACEIT name carries no year/stage; left as it is")
    return p


class CompetitionDecisions:
    FILE_NOTE = ("Reviewed OWCS display names for FACEIT competitions, keyed by championship id. Display-only: "
                 "championships.name stays FACEIT's. Edit by hand or with `python -m owcsmuse competitions decide`. "
                 "A decision made against a FACEIT name that later changes stops applying (reported as stale).")

    def __init__(self, path: str | Path = DEFAULT_DECISIONS_PATH):
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8")).get("decisions", {})

    def get(self, cid: str) -> Optional[dict[str, Any]]:
        return self.data.get(cid)

    def set(self, cid: str, faceit_name: str, display_name: str, basis: str, page: Optional[str] = None,
            note: Optional[str] = None) -> None:
        self.data[cid] = {"faceit_name": faceit_name, "display_name": display_name, "basis": basis, "page": page,
                          "note": note, "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def unset(self, cid: str) -> bool:
        return self.data.pop(cid, None) is not None

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"note": self.FILE_NOTE, "decisions": dict(sorted(self.data.items(), key=lambda kv: kv[1]["display_name"]))}
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path

    def apply(self, proposals: list[Proposal]) -> list[Proposal]:
        for p in proposals:
            d = self.data.get(p.championship_id)
            if not d:
                continue
            if d["faceit_name"] != p.faceit_name:
                p.status = "stale"
                p.flags.append(f"decided against '{d['faceit_name']}', which FACEIT has since renamed; not applied")
            else:
                p.status, p.decided_name = "decided", d["display_name"]
        return proposals


def propose(map_path: str | Path = DEFAULT_MAP_PATH, scope_path: str | Path = DEFAULT_SCOPE_PATH) -> list[Proposal]:
    """A proposal for every in-scope competition. Offline: reads the two committed scope files, nothing else."""
    pages = json.loads(Path(map_path).read_text(encoding="utf-8"))["pages"]
    scope = json.loads(Path(scope_path).read_text(encoding="utf-8"))["decisions"]
    out = []
    for cid, d in scope.items():
        if not d.get("include"):
            continue
        name = d.get("name") or (pages.get(cid) or {}).get("name") or cid
        page = (pages.get(cid) or {}).get("page")
        p = _propose_one(cid, name, page)
        if p.proposed is None and page is None and _FACEIT_LEAGUE.match(name):
            p.flags.append("a FACEIT League competition with no mapped page")
        out.append(p)
    out.sort(key=lambda p: (p.proposed is None, p.proposed or p.faceit_name))
    return out


def accept(decisions: CompetitionDecisions, proposals: list[Proposal], bases: tuple[str, ...] = ("liquipedia",)) -> int:
    """Bulk-accept pending proposals of the given bases that carry no flags. Flagged ones need a person."""
    n = 0
    for p in proposals:
        if p.status == "pending" and p.proposed and p.basis in bases and not [f for f in p.flags if "FACEIT says" in f or "differs" in f]:
            decisions.set(p.championship_id, p.faceit_name, p.proposed, p.basis, p.page)
            p.status, p.decided_name = "decided", p.proposed
            n += 1
    return n


def render_report(proposals: list[Proposal]) -> str:
    pend = [p for p in proposals if p.status == "pending" and p.proposed]
    lines = [
        "# OWCS competition names",
        "",
        f"{len(proposals)} in-scope competitions: {sum(p.status == 'decided' for p in proposals)} decided, "
        f"{len(pend)} proposed and waiting for review, "
        f"{sum(p.proposed is None for p in proposals)} with no proposal (left as they are).",
        "",
        "Display-only. FACEIT's name stays the stored source of record; nothing below applies until it is decided "
        "(`python -m owcsmuse competitions accept`, or `competitions decide <id> --name ...`) and loaded "
        "(`competitions load`).",
        "",
        "| status | FACEIT name (stored) | shown today | proposed | basis | Liquipedia page | flags |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in proposals:
        lines.append("| " + " | ".join([
            p.status, p.faceit_name, p.current_display, p.proposed or "(unchanged)", p.basis,
            f"[{p.page}](https://liquipedia.net/overwatch/{p.page.replace(' ', '_')})" if p.page else "",
            "; ".join(p.flags),
        ]) + " |")
    return "\n".join(lines) + "\n"


def load(conn: psycopg.Connection, decisions: CompetitionDecisions, proposals: Optional[list[Proposal]] = None) -> dict[str, int]:
    """Write decided, non-stale names into competition_names. Only reviewed names are written."""
    proposals = decisions.apply(proposals if proposals is not None else propose())
    written = stale = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM competition_names")
        for p in proposals:
            if p.status == "stale":
                stale += 1
            elif p.status == "decided":
                d = decisions.data[p.championship_id]
                cur.execute("INSERT INTO competition_names (championship_id, faceit_name, display_name, basis, page) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (p.championship_id, p.faceit_name, d["display_name"], d["basis"], d.get("page")))
                written += 1
    conn.commit()
    return {"names_written": written, "stale_not_applied": stale}
