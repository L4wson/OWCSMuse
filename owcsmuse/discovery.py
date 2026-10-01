"""Deliverable 1: locate OWCS competitions on FACEIT and write a reviewable manifest.

Strategy (all read-only):
  1. /search/organizers?name=<each search name>   -> organizers whose name matches
  2. /search/championships?name=<each search name> -> organizer ids of OWCS-named events
     (catches seasons hosted under a differently named organizer)
  3. plus any --organizer-id passed explicitly
  4. /organizers/{id} + /organizers/{id}/championships for every organizer found;
     every championship is written to the manifest.
  5. owcsmuse.scope classifies each entry (region / tier / season / include)
     with evidence, and reviewed decisions from scope/decisions.json override
     the classifier. A markdown report is written next to the manifest.

The user reviews the report, records corrections with `decide`, then runs
`load-manifest` before any bulk ingest.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .faceit.client import FaceitClient, FaceitClientError
from .log import get_logger, log_event
from .parsers.championships import OWCS_PATTERN, is_owcs, parse_championship, parse_organizer
from .scope import Decisions, classify_manifest_entries, render_report

log = get_logger("owcsmuse.discovery")

DEFAULT_SEARCH_NAMES = ("OWCS", "Overwatch Champions Series")


@dataclass
class ManifestEntry:
    championship_id: str
    name: str
    organizer_id: Optional[str]
    organizer_name: Optional[str]
    region: Optional[str]
    derived_region: Optional[str]
    status: Optional[str]
    type: Optional[str]
    game_id: Optional[str]
    championship_start: Optional[str]
    subscription_start: Optional[str]
    subscription_end: Optional[str]
    faceit_url: Optional[str]
    include: bool
    found_via: str


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def discover(
    client: FaceitClient,
    search_names: Iterable[str] = DEFAULT_SEARCH_NAMES,
    extra_organizer_ids: Iterable[str] = (),
    pattern: re.Pattern[str] = OWCS_PATTERN,
    game: str = "ow2",
    decisions: Optional[Decisions] = None,
) -> dict[str, Any]:
    search_names = list(search_names)
    organizers: dict[str, dict[str, Any]] = {}

    def note_org(org_id: Optional[str], name: Optional[str], via: str) -> None:
        if not org_id:
            return
        entry = organizers.setdefault(org_id, {"organizer_id": org_id, "name": name, "found_via": via})
        if name and not entry.get("name"):
            entry["name"] = name

    # 1. organizer search
    for name in search_names:
        res = client.search_organizers(name)
        for item in res.items:
            if is_owcs(item.get("name"), pattern):
                note_org(item.get("organizer_id"), item.get("name"), f"search_organizers:{name}")

    # 2. championship search -> organizer ids
    searched_championships: dict[str, dict[str, Any]] = {}
    for name in search_names:
        res = client.search_championships(name, game=game)
        for item in res.items:
            if is_owcs(item.get("name"), pattern):
                cid = item.get("championship_id") or item.get("id")
                if cid:
                    searched_championships[cid] = item
                note_org(item.get("organizer_id"), None, f"search_championships:{name}")

    # 3. explicit
    for oid in extra_organizer_ids:
        note_org(oid, None, "explicit")

    # 4. enumerate every organizer
    entries: dict[str, ManifestEntry] = {}
    org_summaries: list[dict[str, Any]] = []
    for oid, org in organizers.items():
        org_name = org.get("name")
        try:
            org_payload = client.get_organizer(oid).payload or {}
            org_name = parse_organizer(org_payload).name or org_name
        except FaceitClientError as exc:
            log_event(log, logging.WARNING, "organizer_fetch_failed", organizer_id=oid, error=str(exc))
        listing = client.list_organizer_championships(oid)
        n_included = 0
        for item in listing.items:
            rec = parse_championship(item)
            if not rec.championship_id:
                continue
            include = is_owcs(rec.name, pattern)
            n_included += int(include)
            entries[rec.championship_id] = ManifestEntry(
                championship_id=rec.championship_id,
                name=rec.name,
                organizer_id=rec.organizer_id or oid,
                organizer_name=org_name,
                region=rec.region,
                derived_region=rec.derived_region,
                status=rec.status,
                type=rec.type,
                game_id=rec.game_id,
                championship_start=_iso(rec.championship_start),
                subscription_start=_iso(rec.subscription_start),
                subscription_end=_iso(rec.subscription_end),
                faceit_url=rec.faceit_url,
                include=include,
                found_via="organizer_listing",
            )
        org_summaries.append(
            {
                "organizer_id": oid,
                "name": org_name,
                "found_via": org.get("found_via"),
                "championships_listed": len(listing.items),
                "championships_included": n_included,
                "listing_truncated": listing.truncated,
            }
        )
        log_event(log, logging.INFO, "organizer_enumerated", organizer_id=oid, name=org_name,
                  championships=len(listing.items), included=n_included, truncated=listing.truncated)

    # championships that only the search surfaced (e.g. organizer listing truncated)
    for cid, item in searched_championships.items():
        if cid in entries:
            continue
        rec = parse_championship(item)
        entries[cid] = ManifestEntry(
            championship_id=cid,
            name=rec.name,
            organizer_id=rec.organizer_id,
            organizer_name=organizers.get(rec.organizer_id or "", {}).get("name"),
            region=rec.region,
            derived_region=rec.derived_region,
            status=rec.status,
            type=rec.type,
            game_id=rec.game_id,
            championship_start=_iso(rec.championship_start),
            subscription_start=_iso(rec.subscription_start),
            subscription_end=_iso(rec.subscription_end),
            faceit_url=rec.faceit_url,
            include=True,
            found_via="search_championships",
        )

    ordered = sorted(entries.values(), key=lambda e: (e.championship_start or "", e.name))
    champ_dicts = [asdict(e) for e in ordered]
    classify_manifest_entries(champ_dicts, decisions or Decisions(), owcs_organizer_ids=organizers.keys())
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "search_names": search_names,
        "pattern": pattern.pattern,
        "game": game,
        "note": (
            "Review before ingest. `include`, `scope_region`, `tier` and `season` are classifier proposals "
            "unless decision_source is 'manual'. Record corrections with `python -m owcsmuse decide`, "
            "re-render with `classify`, then `load-manifest`. Only reviewed (manual) decisions mark a "
            "championship included unless load-manifest is run with --accept-proposals."
        ),
        "organizers": org_summaries,
        "championships": champ_dicts,
    }
    log_event(log, logging.INFO, "discovery_complete", organizers=len(org_summaries),
              championships=len(champ_dicts), included=sum(1 for c in champ_dicts if c["include"]),
              manual=sum(1 for c in champ_dicts if c["decision_source"] == "manual"))
    return manifest


HISTORY_COMPETITIONS_PATH = Path("scope") / "history_competitions.json"


def merge_history_competitions(manifest: dict[str, Any], path: str | Path = HISTORY_COMPETITIONS_PATH) -> int:
    """Add / refresh competitions discovered by the history crawl (written by `crawl competitions`)."""
    p = Path(path)
    if not p.exists():
        return 0
    with open(p, encoding="utf-8") as f:
        comps = json.load(f)
    by_id = {c["championship_id"]: c for c in manifest["championships"]}
    n = 0
    for c in comps:
        c = dict(c)
        c["found_via"] = "history_crawl"
        if c["championship_id"] in by_id:
            by_id[c["championship_id"]].update(c)
        else:
            manifest["championships"].append(c)
            by_id[c["championship_id"]] = c
        n += 1
    return n


def reclassify_manifest(manifest: dict[str, Any], decisions: Optional[Decisions] = None,
                        history_path: str | Path = HISTORY_COMPETITIONS_PATH) -> dict[str, Any]:
    """Re-run the classifier + decisions over an existing manifest without touching FACEIT."""
    org_ids = [o["organizer_id"] for o in manifest.get("organizers") or []]
    merged = merge_history_competitions(manifest, history_path)
    classify_manifest_entries(manifest["championships"], decisions or Decisions(), owcs_organizer_ids=org_ids)
    manifest["reclassified_at"] = datetime.now(timezone.utc).isoformat()
    manifest["history_competitions_merged"] = merged
    return manifest


def write_report(manifest: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_report(manifest), encoding="utf-8")
    return p


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def read_manifest(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    if "championships" not in manifest:
        raise ValueError(f"{path} does not look like a discovery manifest (missing 'championships')")
    return manifest
