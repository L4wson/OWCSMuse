"""Championship / organizer payloads -> records, plus OWCS name filtering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .common import faceit_url, to_int, ts_from_epoch

# What counts as an OWCS event when filtering an organizer's championships.
OWCS_PATTERN = re.compile(r"\bOWCS\b|Overwatch\s+Champions\s+Series", re.IGNORECASE)

_REGION_TOKENS = [
    (re.compile(r"\bEMEA\b", re.I), "EMEA"),
    (re.compile(r"\bNA\b|\bNorth America\b", re.I), "NA"),
    (re.compile(r"\bAPAC\b|\bAsia\b", re.I), "APAC"),
    (re.compile(r"\bKOREA\b|\bKR\b", re.I), "KR"),
    (re.compile(r"\bJAPAN\b|\bJP\b", re.I), "JP"),
    (re.compile(r"\bCHINA\b|\bCN\b", re.I), "CN"),
    (re.compile(r"\bPACIFIC\b", re.I), "PACIFIC"),
    (re.compile(r"\bOCE\b|\bOceania\b", re.I), "OCE"),
    (re.compile(r"\bSA\b|\bLATAM\b|\bSouth America\b", re.I), "SA"),
    (re.compile(r"\bAmericas\b", re.I), "AMERICAS"),
    (re.compile(r"\bWorld Finals\b|\bChampions Clash\b|\bMidseason\b", re.I), "GLOBAL"),
]


def is_owcs(name: Optional[str], pattern: re.Pattern[str] = OWCS_PATTERN) -> bool:
    return bool(name) and pattern.search(name) is not None


def derive_region(name: Optional[str]) -> Optional[str]:
    """FACEIT reports most OWCS events as region GLOBAL; the name is more useful."""
    if not name:
        return None
    for rx, region in _REGION_TOKENS:
        if rx.search(name):
            return region
    return None


@dataclass
class OrganizerRecord:
    organizer_id: str
    name: Optional[str]
    faceit_url: Optional[str]


@dataclass
class ChampionshipRecord:
    championship_id: str
    organizer_id: Optional[str]
    name: str
    game_id: Optional[str]
    region: Optional[str]
    derived_region: Optional[str]
    status: Optional[str]
    type: Optional[str]
    championship_start: Optional[datetime]
    subscription_start: Optional[datetime]
    subscription_end: Optional[datetime]
    total_rounds: Optional[int]
    total_groups: Optional[int]
    slots: Optional[int]
    faceit_url: Optional[str]


def parse_organizer(payload: dict[str, Any]) -> OrganizerRecord:
    return OrganizerRecord(
        organizer_id=payload.get("organizer_id") or payload.get("id"),
        name=payload.get("name"),
        faceit_url=faceit_url(payload.get("faceit_url")),
    )


def parse_championship(item: dict[str, Any]) -> ChampionshipRecord:
    name = item.get("name") or ""
    return ChampionshipRecord(
        championship_id=item.get("championship_id") or item.get("id"),
        organizer_id=item.get("organizer_id"),
        name=name,
        game_id=item.get("game_id") or item.get("game"),
        region=item.get("region"),
        derived_region=derive_region(name),
        status=item.get("status"),
        type=item.get("type"),
        championship_start=ts_from_epoch(item.get("championship_start")),
        subscription_start=ts_from_epoch(item.get("subscription_start")),
        subscription_end=ts_from_epoch(item.get("subscription_end")),
        total_rounds=to_int(item.get("total_rounds")),
        total_groups=to_int(item.get("total_groups")),
        slots=to_int(item.get("slots")),
        faceit_url=faceit_url(item.get("faceit_url")),
    )
