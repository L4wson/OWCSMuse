"""Liquipedia match records -> `LPMatch`, from the stored /match responses. No network.

What the Stage 1 fetch showed about a record (300 rows, 20 OWCS stage pages):

  * `pagename` is the page the match sits on; that is what a value is attributed to (`page_url`).
  * `date` is UTC and equals `extradata.timestamp` (an epoch) exactly, on every row checked.
  * The FACEIT match id, when the page records it, is in `links.faceit` as a full room URL (298 of 300 rows). Rows
    without one have `links: []`.
  * `match2opponents[i]` has `name`, `score`, `status` ("S" = a played score); `match2games[]` has one entry per map.
  * Identity: `objectname` (<pageid>_<match2id>) is the row key; (`match2bracketid`, `match2id`) is unique too. No
    duplicates appeared in the fetch. `dedupe` still guards against the two ways they could: the same bracket/match
    twice, and one FACEIT id claimed by two records.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .attribution import page_url

FACEIT_ID = re.compile(r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
PLACEHOLDER_NAMES = frozenset({"", "tbd", "tba", "bye", "n/a"})


@dataclass(frozen=True)
class LPGame:
    map: Optional[str]
    mode: Optional[str]
    winner: int                 # 1, 2, or 0
    scores: tuple[Any, ...]


@dataclass(frozen=True)
class LPMatch:
    objectname: str
    raw_id: int
    match2id: str
    bracket_id: str
    pagename: str
    page_url: str
    parent: Optional[str]
    region: Optional[str]
    played_at: datetime
    best_of: Optional[int]
    finished: bool
    winner: int
    walkover: str
    team1: str
    team2: str
    score1: Optional[int]
    score2: Optional[int]
    status1: str
    status2: str
    section: Optional[str]
    faceit_match_id: Optional[str]
    games: tuple[LPGame, ...] = ()
    placeholder: bool = False
    notes: tuple[str, ...] = field(default=())

    @property
    def n_games(self) -> int:
        return len(self.games)


def region_of(pagename: str) -> str:
    """The competition region a page belongs to. na/emea are region-locked; anything else is just a label."""
    parts = [p.upper() for p in pagename.split("/")]
    for name, label in (("NA", "na"), ("EMEA", "emea"), ("KOREA", "korea"), ("CHINA", "china"), ("JAPAN", "japan"),
                        ("PACIFIC", "pacific")):
        if name in parts:
            return label
    return "other"


def faceit_id_of(links: Any) -> Optional[str]:
    """The FACEIT match id in a record's `links`, from whatever shape it arrives in (dict of name -> URL, or a list)."""
    m = FACEIT_ID.search(json.dumps(links, ensure_ascii=False)) if links else None
    return m.group(0) if m else None


def _int(v: Any) -> Optional[int]:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _played_at(row: dict[str, Any]) -> datetime:
    """UTC. The epoch in extradata is authoritative (it matched `date` exactly); `date` is the fallback."""
    ts = (row.get("extradata") or {}).get("timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def parse_row(row: dict[str, Any], raw_id: int, wiki: str = "overwatch") -> Optional[LPMatch]:
    """One record, or None when it is not a two-team match at all."""
    opp = row.get("match2opponents") or []
    if len(opp) != 2:
        return None
    o1, o2 = opp
    notes: list[str] = []
    placeholder = any((o.get("name") or "").strip().lower() in PLACEHOLDER_NAMES or (o.get("type") not in (None, "team"))
                      for o in opp)
    winner = _int(row.get("winner")) or 0
    games = tuple(LPGame(g.get("map"), g.get("mode"), _int(g.get("winner")) or 0, tuple(g.get("scores") or ()))
                  for g in (row.get("match2games") or []) if g.get("map") or g.get("scores"))
    faceit = faceit_id_of(row.get("links"))
    if row.get("links") and not faceit and "faceit" in json.dumps(row["links"]).lower():
        notes.append("links mention FACEIT but hold no match id")
    return LPMatch(
        objectname=row["objectname"], raw_id=raw_id, match2id=row["match2id"], bracket_id=row["match2bracketid"],
        pagename=row["pagename"], page_url=page_url(row["pagename"], wiki), parent=row.get("parent"),
        region=region_of(row["pagename"]), played_at=_played_at(row), best_of=_int(row.get("bestof")),
        finished=bool(row.get("finished")), winner=winner, walkover=row.get("walkover") or "",
        team1=(o1.get("name") or "").strip(), team2=(o2.get("name") or "").strip(),
        score1=_int(o1.get("score")) if o1.get("status") in (None, "", "S") else None,
        score2=_int(o2.get("score")) if o2.get("status") in (None, "", "S") else None,
        status1=o1.get("status") or "", status2=o2.get("status") or "", section=(row.get("section") or None),
        faceit_match_id=faceit, games=games, placeholder=placeholder, notes=tuple(notes))


@dataclass
class Duplicates:
    same_match: list[tuple[LPMatch, LPMatch]] = field(default_factory=list)      # one (bracket, match2id) twice: dropped
    same_faceit_id: list[list[LPMatch]] = field(default_factory=list)            # one FACEIT id on several records: kept, flagged


def parse_rows(rows: Iterable[dict[str, Any]], raw_id: int, wiki: str = "overwatch") -> list[LPMatch]:
    return [m for m in (parse_row(r, raw_id, wiki) for r in rows) if m is not None]


def dedupe(matches: Iterable[LPMatch]) -> tuple[list[LPMatch], Duplicates]:
    """Drop a record repeated under the same (bracket, match2id), keeping the one with the most games; flag - but keep -
    records that share a FACEIT id, because those are a data conflict for a person to look at, not a repeat."""
    dups = Duplicates()
    kept: dict[tuple[str, str], LPMatch] = {}
    for m in matches:
        key = (m.bracket_id, m.match2id)
        if key in kept:
            old = kept[key]
            keep, drop = (m, old) if (m.n_games, m.finished) > (old.n_games, old.finished) else (old, m)
            kept[key] = keep
            dups.same_match.append((keep, drop))
        else:
            kept[key] = m
    out = list(kept.values())
    by_id: dict[str, list[LPMatch]] = {}
    for m in out:
        if m.faceit_match_id:
            by_id.setdefault(m.faceit_match_id, []).append(m)
    dups.same_faceit_id = [v for v in by_id.values() if len(v) > 1]
    return out, dups
