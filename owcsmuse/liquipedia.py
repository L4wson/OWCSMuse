"""Cross-check crawled matches against Liquipedia's published results.

Read-only use of the Liquipedia MediaWiki API (wikitext of a stage page),
throttled to one parse request every two seconds as their terms ask, with an
identifying User-Agent. Match templates in the wikitext are parsed for the two
teams, the date and the map winners; each is then looked up in our matches
for the mapped championship by (folded) team names and date.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

import httpx
import psycopg

from .logging import get_logger, log_event
from .resolve import fold

log = get_logger("owcsmuse.liquipedia")

API = "https://liquipedia.net/overwatch/api.php"
USER_AGENT = "OWCSMuse/0.1 (https://github.com/L4wson/OWCSMuse; stats warehouse cross-check)"
MIN_INTERVAL = 2.0

# Known FACEIT nickname -> Liquipedia name differences.
TEAM_ALIASES = {
    "qadsiah": "al qadsiah",
    "al qadsiah": "al qadsiah",
    "virtus pro": "virtus pro",
    "virtus.pro": "virtus pro",
    "spacestation": "spacestation gaming",
    "ssg": "spacestation gaming",
    "nrg": "nrg shock",
    "toronto defiant": "toronto defiant",
    "team liquid": "team liquid",
    "liquid": "team liquid",
}


@dataclass
class LPMatch:
    team1: str
    team2: str
    date: Optional[str]
    winner: Optional[int]
    score1: Optional[int]
    score2: Optional[int]
    raw_index: int
    faceit_id: Optional[str] = None  # Liquipedia records the FACEIT match id on most OWCS matches


@dataclass
class CheckResult:
    championship_id: str
    page: str
    lp_matches: int
    db_matches: int
    matched: int
    lp_only: list[dict[str, Any]] = field(default_factory=list)
    db_only: list[dict[str, Any]] = field(default_factory=list)
    score_mismatches: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiquipediaClient:
    def __init__(self, http: Optional[httpx.Client] = None) -> None:
        self.http = http or httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}, timeout=30)
        self._last = 0.0

    def _throttle(self) -> None:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        self._throttle()
        r = self.http.get(API, params={"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"})
        r.raise_for_status()
        return [{"title": s["title"], "snippet": re.sub(r"<[^>]+>", "", s.get("snippet", ""))} for s in r.json().get("query", {}).get("search", [])]

    def wikitext(self, page: str) -> str:
        self._throttle()
        r = self.http.get(API, params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"})
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise ValueError(f"Liquipedia: {data['error'].get('info')}")
        log_event(log, logging.INFO, "liquipedia_page", page=page, bytes=len(data["parse"]["wikitext"]["*"]))
        return data["parse"]["wikitext"]["*"]


# ---------------------------------------------------------------- wikitext parsing

_MATCH_OPEN = re.compile(r"\{\{\s*Match\s*(?=[|\n])", re.I)


def _template_blocks(text: str, opener: re.Pattern[str]) -> list[str]:
    """Return every balanced {{Match ...}} block, including nested templates."""
    blocks = []
    for m in opener.finditer(text):
        i = m.start()
        depth = 0
        j = i
        while j < len(text) - 1:
            if text.startswith("{{", j):
                depth += 1
                j += 2
                continue
            if text.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    blocks.append(text[i:j])
                    break
                continue
            j += 1
    return blocks


_OPP = re.compile(r"\|\s*opponent(?P<n>[12])\s*=\s*\{\{\s*(?:TeamOpponent|Team)\s*\|\s*(?P<name>[^|}]+)", re.I)
_DATE = re.compile(r"\|\s*date\s*=\s*(?P<d>[^|}\n]+)")
_FACEIT = re.compile(r"\|\s*faceit\s*=\s*(?P<id>1-[0-9a-f\-]{36})", re.I)
_ORDINAL = re.compile(r"(\d)(st|nd|rd|th)\b")
_MAP_WINNER = re.compile(r"\{\{\s*Map\b[^}]*?\|\s*winner\s*=\s*(?P<w>[12])", re.I | re.S)
_WINNER = re.compile(r"\|\s*winner\s*=\s*(?P<w>[12])\s*(?:\||\n|\})")


def parse_matches(wikitext: str) -> list[LPMatch]:
    out: list[LPMatch] = []
    for idx, block in enumerate(_template_blocks(wikitext, _MATCH_OPEN)):
        opps = {m.group("n"): m.group("name").strip() for m in _OPP.finditer(block)}
        if "1" not in opps or "2" not in opps:
            continue
        if opps["1"].lower() in ("tbd", "bye", "") or opps["2"].lower() in ("tbd", "bye", ""):
            continue
        date_m = _DATE.search(block)
        date = None
        if date_m:
            raw = re.sub(r"\{\{.*?(\}\}|$)", "", date_m.group("d")).strip()
            raw = re.sub(r"\s*-\s*\d{1,2}:\d{2}.*$", "", raw)
            raw = _ORDINAL.sub(r"\1", raw).strip()
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y"):
                try:
                    date = datetime.strptime(raw, fmt).date().isoformat()
                    break
                except ValueError:
                    continue
        # map-level winners inside nested {{Map}} templates; top-level winner as fallback
        maps = [int(m.group("w")) for m in _MAP_WINNER.finditer(block)]
        s1, s2 = (maps.count(1), maps.count(2)) if maps else (None, None)
        top = None
        # top-level |winner= outside nested maps: strip nested templates first
        stripped = re.sub(r"\{\{\s*Map\b.*?\}\}", "", block, flags=re.I | re.S)
        wm = _WINNER.search(stripped)
        if wm:
            top = int(wm.group("w"))
        winner = top if top else (1 if (s1 or 0) > (s2 or 0) else 2 if (s2 or 0) > (s1 or 0) else None)
        fm = _FACEIT.search(block)
        out.append(LPMatch(team1=opps["1"], team2=opps["2"], date=date, winner=winner, score1=s1, score2=s2, raw_index=idx,
                           faceit_id=fm.group("id") if fm else None))
    return out


# ---------------------------------------------------------------- comparison

def _norm_team(name: str) -> str:
    f = fold(name)
    f = re.sub(r"\b(esports?|e sports|gaming|team|club)\b", " ", f)
    f = re.sub(r"\s+", " ", f).strip()
    return TEAM_ALIASES.get(f, TEAM_ALIASES.get(fold(name), f))


def _same_team(a: str, b: str) -> bool:
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.8


def compare(conn: psycopg.Connection, championship_id: str, page: str, lp: list[LPMatch], date_tolerance_days: int = 1) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT match_id, started_at, faction1_name, faction2_name, faction1_score, faction2_score, winner_faction, status
            FROM matches WHERE championship_id = %s
            """,
            (championship_id,),
        )
        db = [dict(r) for r in cur.fetchall()]
    conn.commit()
    used: set[str] = set()
    matched = 0
    lp_only: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    by_id = {d["match_id"]: d for d in db}
    for m in lp:
        best = by_id.get(m.faceit_id) if m.faceit_id and m.faceit_id not in used else None
        for d in ([] if best else db):
            if d["match_id"] in used:
                continue
            pair_ok = (_same_team(m.team1, d["faction1_name"] or "") and _same_team(m.team2, d["faction2_name"] or "")) or \
                      (_same_team(m.team1, d["faction2_name"] or "") and _same_team(m.team2, d["faction1_name"] or ""))
            if not pair_ok:
                continue
            if m.date and d["started_at"]:
                delta = abs((d["started_at"].date() - datetime.fromisoformat(m.date).date()).days)
                if delta > date_tolerance_days:
                    continue
            best = d
            break
        if best is None:
            lp_only.append({"team1": m.team1, "team2": m.team2, "date": m.date, "score": f"{m.score1}-{m.score2}"})
            continue
        used.add(best["match_id"])
        matched += 1
        if m.score1 is not None and best["faction1_score"] is not None:
            same_order = _same_team(m.team1, best["faction1_name"] or "")
            db_s1, db_s2 = (best["faction1_score"], best["faction2_score"]) if same_order else (best["faction2_score"], best["faction1_score"])
            if (m.score1, m.score2) != (db_s1, db_s2):
                mismatches.append({"match_id": best["match_id"], "teams": f"{m.team1} vs {m.team2}", "liquipedia": f"{m.score1}-{m.score2}",
                                   "db": f"{db_s1}-{db_s2}", "date": m.date})
    db_only = [{"match_id": d["match_id"], "teams": f"{d['faction1_name']} vs {d['faction2_name']}",
                "date": d["started_at"].date().isoformat() if d["started_at"] else None, "status": d["status"]}
               for d in db if d["match_id"] not in used]
    return CheckResult(championship_id=championship_id, page=page, lp_matches=len(lp), db_matches=len(db), matched=matched,
                       lp_only=lp_only, db_only=db_only, score_mismatches=mismatches)
