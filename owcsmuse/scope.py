"""Scope classification: which championships are in the NA + EMEA main series.

Three parts:

* `classify()` proposes region / tier / season / include for one championship
  and returns the evidence it used. It is deliberately a small rule table,
  every rule names itself in the evidence so a reviewer can see why.
* `Decisions` is the reviewed override file (default `scope/decisions.json`).
  A decision beats the classifier and survives re-running discovery.
* `render_report()` writes the per-championship review table.

Target set: OWCS North America and EMEA main competition (regional stages,
their group stages and playoffs) plus international events where NA and EMEA
teams compete (Midseason Championship, World Finals, Champions Clash, the 2024
Dreamhack Dallas Major). Excluded: open qualifiers, relegation, Asia / Korea /
Japan / Pacific / China / South America / Oceania, cancelled or test events.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .parsers.championships import OWCS_PATTERN, is_owcs

REGIONS = ("na", "emea", "international", "other")
TIERS = ("main", "qualifier", "relegation", "unknown")

DEFAULT_DECISIONS_PATH = Path("scope") / "decisions.json"

# (regex, value, evidence label). First match wins within each table.
_REGION_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(Midseason|Mid-Season|World Finals|Champions Clash|Major|International)\b", re.I),
     "international", "name has an international-event token"),
    (re.compile(r"\bEMEA\b", re.I), "emea", "name has EMEA"),
    (re.compile(r"\bNA\b|\bNorth America\b", re.I), "na", "name has NA"),
    (re.compile(r"\b(Asia|APAC|Korea|KR|Japan|JP|China|CN|Pacific|OCE|Oceania|SA|LATAM|South America|Americas)\b", re.I),
     "other", "name has a non-NA/EMEA region token"),
]

_TIER_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bRelegation\b", re.I), "relegation", "name has Relegation"),
    (re.compile(r"\b(Open Qualifier|Open Qualifiers|OQ|Qualifier|Qualifiers|Last Chance|LCQ)\b", re.I),
     "qualifier", "name has a qualifier token"),
    (re.compile(r"\b(Stage \d|Main Event|Group [A-Z]|Playoffs?|Finals?|Midseason|Mid-Season|Champions Clash|Major|Split \d|Week \d)\b", re.I),
     "main", "name has a main-competition token"),
]

_EXCLUDE_NAME = re.compile(r"\b(test|not used|placeholder|dummy)\b", re.I)
_YEAR = re.compile(r"\b(20[2-3]\d)\b")

# Known OWCS events whose FACEIT name does not say "OWCS". Reviewed manually.
_KNOWN_OWCS_NAMES: dict[str, tuple[str, str]] = {
    # name (case-insensitive exact) -> (region, tier)
    "dreamhack dallas": ("international", "main"),  # OWCS 2024 Major, NA/EMEA/Asia teams
}


@dataclass
class Classification:
    region: str
    tier: str
    season: Optional[int]
    include: bool
    evidence: list[str] = field(default_factory=list)
    source: str = "auto"  # auto | manual
    note: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(
    name: str,
    faceit_region: Optional[str] = None,
    status: Optional[str] = None,
    championship_type: Optional[str] = None,
    championship_start: Optional[datetime] = None,
    organizer_is_owcs: bool = False,
    pattern: re.Pattern[str] = OWCS_PATTERN,
) -> Classification:
    ev: list[str] = []
    name = name or ""
    lowered = name.strip().lower()

    # --- season
    season: Optional[int] = None
    ym = _YEAR.search(name)
    if ym:
        season = int(ym.group(1))
        ev.append(f"season {season} from name")
    elif championship_start is not None:
        season = championship_start.year
        ev.append(f"season {season} from championship_start")
    else:
        ev.append("season unknown: no year in name and no start date")

    # --- is it an OWCS event at all?
    known = _KNOWN_OWCS_NAMES.get(lowered)
    owcs_named = is_owcs(name, pattern)
    if owcs_named:
        ev.append("name matches OWCS pattern")
    elif known:
        ev.append("name is a known OWCS event without 'OWCS' in it")
    else:
        ev.append("name does not match OWCS pattern" + (" (hosted by an OWCS organizer, review)" if organizer_is_owcs else ""))

    # --- region
    region = "other"
    if known:
        region = known[0]
        ev.append(f"region {region} from known-event table")
    else:
        for rx, value, label in _REGION_RULES:
            if rx.search(name):
                region, ev = value, ev + [f"region {value}: {label}"]
                break
        else:
            if faceit_region and faceit_region.upper() in ("NA", "EMEA"):
                region = faceit_region.lower()
                ev.append(f"region {region} from FACEIT region field")
            else:
                ev.append(f"region other: no region token in name (FACEIT region={faceit_region})")

    # --- tier
    tier = "unknown"
    if known:
        tier = known[1]
        ev.append(f"tier {tier} from known-event table")
    else:
        for rx, value, label in _TIER_RULES:
            if rx.search(name):
                tier, ev = value, ev + [f"tier {value}: {label}"]
                break
        else:
            ev.append("tier unknown: no tier token in name")

    # --- include proposal
    include = True
    reasons_out: list[str] = []
    if not (owcs_named or known):
        reasons_out.append("not an OWCS event")
    if (status or "").lower() == "cancelled":
        reasons_out.append("status=cancelled")
    if _EXCLUDE_NAME.search(name):
        reasons_out.append("name marks it as test/unused")
    if tier != "main":
        reasons_out.append(f"tier={tier}")
    if region not in ("na", "emea", "international"):
        reasons_out.append(f"region={region}")
    if reasons_out:
        include = False
        ev.append("exclude: " + ", ".join(reasons_out))
    else:
        ev.append("include: OWCS main competition in NA/EMEA/international")

    return Classification(region=region, tier=tier, season=season, include=include, evidence=ev)


# ------------------------------------------------- history-crawl competitions

# Competitions only reachable through /players/{id}/history. Their names carry a
# FACEIT League season number instead of a year; the season (year) comes from
# the dates of the matches seen. The allowlist below is the reviewed target set.
_HISTORY_MAIN = re.compile(r"^S(?P<s>\d+)\s+(?P<r>NA|EMEA)\s+OWCS Central\s*-\s*(?P<stage>Regular Season|Playoffs)\s*$", re.I)
_HISTORY_MSC_LCQ = re.compile(r"^OWCS Midseason Championship: Last Chance Qualifier", re.I)
_HISTORY_S8_RELEGATION = re.compile(r"^S8\s+(?P<r>NA|EMEA)\s+OWCS Relegation", re.I)
_HISTORY_OTHER_RELEGATION = re.compile(r"OWCS\s+(Relegation|P\s*[&|/]\s*R|Promotion)", re.I)
HISTORY_SEASON_RANGE = (4, 10)  # S4..S10 = 2025 Stage 1 .. 2026 Stage 3


def classify_history_competition(
    name: str,
    first_match_at: Optional[datetime] = None,
    faceit_region: Optional[str] = None,
) -> Classification:
    """Propose region / tier / season / include for a history-discovered competition."""
    ev: list[str] = ["discovered via player history (not exposed by championship endpoints)"]
    name = name or ""
    season = first_match_at.year if first_match_at else None
    ev.append(f"season {season} from first match date" if season else "season unknown: no match dates yet")

    m = _HISTORY_MAIN.match(name)
    if m:
        s = int(m.group("s"))
        region = m.group("r").lower()
        ev.append(f"region {region}: name has {m.group('r')}")
        ev.append(f"tier main: FACEIT League S{s} OWCS Central {m.group('stage')}")
        lo, hi = HISTORY_SEASON_RANGE
        if lo <= s <= hi:
            ev.append(f"include: S{s} is within the reviewed S{lo}-S{hi} main-series range")
            return Classification(region=region, tier="main", season=season, include=True, evidence=ev)
        ev.append(f"exclude: S{s} is outside the reviewed S{lo}-S{hi} range")
        return Classification(region=region, tier="main", season=season, include=False, evidence=ev)
    if _HISTORY_MSC_LCQ.match(name):
        ev += ["region international: Midseason Championship (EWC)", "tier main: Midseason Championship last chance qualifier",
               "include: Midseason Championship LCQ is in the reviewed target set"]
        return Classification(region="international", tier="main", season=season, include=True, evidence=ev)
    m = _HISTORY_S8_RELEGATION.match(name)
    if m:
        region = m.group("r").lower()
        ev += [f"region {region}: name has {m.group('r')}", "tier relegation: S8 relegation for Season 9",
               "include: S8 relegation is explicitly in the reviewed target set"]
        return Classification(region=region, tier="relegation", season=season, include=True, evidence=ev)
    if _HISTORY_OTHER_RELEGATION.search(name):
        region = "na" if re.search(r"\bNA\b", name) else "emea" if re.search(r"\bEMEA\b", name) else "other"
        ev += [f"region {region}", "tier relegation: promotion/relegation event", "exclude: only S8 relegation is in the target set"]
        return Classification(region=region, tier="relegation", season=season, include=False, evidence=ev)
    region = "na" if re.search(r"\bNA\b", name) else "emea" if re.search(r"\bEMEA\b", name) else "other"
    if _EXCLUDE_NAME.search(name):
        ev += [f"region {region}", "tier unknown", "exclude: name marks it as test/unused"]
    elif is_owcs(name):
        ev += [f"region {region}", "tier unknown: OWCS-named but not a recognised main-series pattern (review)", "exclude: tier unknown"]
    else:
        ev += [f"region {region}", "tier unknown", "exclude: not an OWCS event"]
    return Classification(region=region, tier="unknown", season=season, include=False, evidence=ev)


# ---------------------------------------------------------------- decisions

class Decisions:
    """Reviewed overrides keyed by championship id, stored as JSON in the repo."""

    def __init__(self, path: str | Path = DEFAULT_DECISIONS_PATH) -> None:
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
            self.data = dict(doc.get("decisions") or {})

    def get(self, championship_id: str) -> Optional[dict[str, Any]]:
        return self.data.get(championship_id)

    def set(
        self,
        championship_id: str,
        *,
        region: Optional[str] = None,
        tier: Optional[str] = None,
        include: Optional[bool] = None,
        season: Optional[int] = None,
        note: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        if region is not None and region not in REGIONS:
            raise ValueError(f"region must be one of {REGIONS}")
        if tier is not None and tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        d = dict(self.data.get(championship_id) or {})
        for k, v in (("region", region), ("tier", tier), ("include", include), ("season", season), ("note", note), ("name", name)):
            if v is not None:
                d[k] = v
        d["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.data[championship_id] = d
        return d

    def apply(self, championship_id: str, proposed: Classification) -> Classification:
        """Return the classification with any reviewed decision applied on top."""
        d = self.data.get(championship_id)
        if not d:
            return proposed
        out = Classification(
            region=d.get("region", proposed.region),
            tier=d.get("tier", proposed.tier),
            season=d.get("season", proposed.season),
            include=bool(d.get("include", proposed.include)),
            evidence=list(proposed.evidence) + [f"manual decision ({d.get('decided_at', '?')}): "
                                                 + ", ".join(f"{k}={d[k]}" for k in ("region", "tier", "include", "season") if k in d)],
            source="manual",
            note=d.get("note"),
        )
        return out

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "note": (
                "Reviewed scope decisions. Keys are FACEIT championship ids; values override the "
                "classifier's region/tier/season/include. Edit by hand or with `python -m owcsmuse decide`."
            ),
            "decisions": dict(sorted(self.data.items(), key=lambda kv: (kv[1].get("name") or "", kv[0]))),
        }
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path


# ------------------------------------------------------------------ manifest

def classify_manifest_entries(entries: Iterable[dict[str, Any]], decisions: Decisions,
                              owcs_organizer_ids: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Attach classification fields to manifest championship entries (in place) and return them."""
    owcs_orgs = set(owcs_organizer_ids)
    out = []
    for e in entries:
        start = e.get("championship_start") or e.get("first_match_at")
        start_dt = datetime.fromisoformat(start) if isinstance(start, str) and start else None
        if e.get("found_via") == "history_crawl":
            proposed = classify_history_competition(e.get("name") or "", start_dt, e.get("region"))
        else:
            proposed = classify(
                e.get("name") or "",
                faceit_region=e.get("region"),
                status=e.get("status"),
                championship_type=e.get("type"),
                championship_start=start_dt,
                organizer_is_owcs=e.get("organizer_id") in owcs_orgs,
            )
        final = decisions.apply(e["championship_id"], proposed)
        e["proposed"] = {"region": proposed.region, "tier": proposed.tier, "season": proposed.season, "include": proposed.include}
        e["scope_region"] = final.region
        e["tier"] = final.tier
        e["season"] = final.season
        e["include"] = final.include
        e["decision_source"] = final.source
        e["decision_note"] = final.note
        e["evidence"] = final.evidence
        out.append(e)
    return out


def _cell(value: Any) -> str:
    """Escape a value for a markdown table cell. A literal | in a competition name
    ("S10 EMEA OWCS P|R Bracket") silently truncates the column otherwise."""
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def render_report(manifest: dict[str, Any]) -> str:
    """Markdown review table: one row per championship, evidence included."""
    rows = sorted(
        manifest["championships"],
        key=lambda c: (not c.get("include"), c.get("decision_source") != "manual", c.get("championship_start") or "", c.get("name") or ""),
    )
    n_inc = sum(1 for c in rows if c.get("include"))
    n_manual = sum(1 for c in rows if c.get("decision_source") == "manual")
    lines = [
        "# OWCS scope classification report",
        "",
        f"Generated {manifest.get('generated_at', '?')} from {len(rows)} championships: "
        f"**{n_inc} proposed/decided included**, {len(rows) - n_inc} excluded, {n_manual} with manual decisions.",
        "",
        "Review each row. To correct one: `python -m owcsmuse decide <championship_id> --region na --tier main --include --note \"...\"` "
        "(or `--exclude`). Decisions live in `scope/decisions.json` and override the classifier on every future run. "
        "Then `python -m owcsmuse classify` to re-render, and `python -m owcsmuse load-manifest manifest.json` to apply.",
        "",
        "| include | src | via | season | region | tier | name | FACEIT region | status | type | start | matches seen | championship_id | evidence |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in rows:
        start = (c.get("championship_start") or c.get("first_match_at") or "")[:10]
        ev = "<br>".join(c.get("evidence") or [])
        note = f" **note:** {c['decision_note']}" if c.get("decision_note") else ""
        via = "history" if c.get("found_via") == "history_crawl" else "api"
        seen = c.get("matches_seen") if c.get("matches_seen") is not None else ""
        lines.append(
            f"| {'YES' if c.get('include') else 'no'} | {c.get('decision_source', 'auto')} | {via} | {_cell(c.get('season'))} | "
            f"{_cell(c.get('scope_region'))} | {_cell(c.get('tier'))} | {_cell(c.get('name'))} | {_cell(c.get('region'))} | "
            f"{_cell(c.get('status'))} | {_cell(c.get('type'))} | {start} | {seen} | `{c['championship_id']}` | {_cell(ev)}{_cell(note)} |"
        )
    lines.append("")
    return "\n".join(lines)
