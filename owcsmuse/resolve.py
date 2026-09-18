"""Entity resolution: human-typed player / team name -> ranked candidates.

Matching is case- and accent-insensitive and considers every name an entity
has carried: current FACEIT nickname, in-game name, historical nicknames, and
current + historical team names (all from the `entity_names` materialized
view). Ranking is done in Python so no database extension is required:

    exact folded match      1.00
    query is a prefix       0.90
    query is contained      0.80   (handles "ksaa" vs "KSAA0")
    name is contained       0.70   (query has extra words)
    difflib similarity      ratio * 0.75, kept when >= min_score

`rank_candidates()` is pure and unit-tested; `resolve()` adds the query.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

import psycopg

# A FACEIT player/team id, so an ambiguous name can be disambiguated by id.
ENTITY_ID = re.compile(
    r"^(?:(?P<kind>player|team|org):)?"
    r"(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)
ORG_ID = re.compile(r"^org:(?P<id>[a-z0-9-]+)$", re.I)

_NON_ALNUM = re.compile(r"[^0-9a-z ]+")
_SPACES = re.compile(r"\s+")
# Letters with no Unicode decomposition that NFKD cannot strip.
_SPECIAL = str.maketrans({
    "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE", "ı": "i", "İ": "I", "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D",
})


def fold(text: Optional[str]) -> str:
    """Lower-case, strip accents, collapse punctuation to spaces."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.translate(_SPECIAL))
    ascii_only = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = _NON_ALNUM.sub(" ", ascii_only)
    return _SPACES.sub(" ", ascii_only).strip()


@dataclass
class Candidate:
    entity_type: str
    entity_id: str
    current_name: Optional[str]
    matched_name: str
    name_kind: str
    score: float
    matches: int = 0          # in-scope matches, used only to break an exact tie

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_name(query_folded: str, name_folded: str) -> float:
    if not query_folded or not name_folded:
        return 0.0
    if name_folded == query_folded:
        return 1.0
    if name_folded.startswith(query_folded):
        return 0.9
    if query_folded in name_folded:
        return 0.8
    if name_folded in query_folded:
        return 0.7
    compact_q = query_folded.replace(" ", "")
    compact_n = name_folded.replace(" ", "")
    if compact_q and compact_q == compact_n:
        return 0.95
    return SequenceMatcher(None, query_folded, name_folded).ratio() * 0.75


def rank_candidates(
    query: str,
    names: Iterable[dict[str, Any]],
    limit: int = 5,
    min_score: float = 0.5,
) -> list[Candidate]:
    """names: rows with entity_type, entity_id, name, name_kind, current_name (name_folded optional)."""
    q = fold(query)
    best: dict[tuple[str, str], Candidate] = {}
    for row in names:
        nf = fold(row.get("name"))  # always the Python fold, so query and names agree exactly
        s = score_name(q, nf)
        if s < min_score:
            continue
        key = (row["entity_type"], row["entity_id"])
        cand = Candidate(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            current_name=row.get("current_name"),
            matched_name=row.get("name") or "",
            name_kind=row.get("name_kind") or "",
            score=round(s, 3),
            matches=int(row.get("matches") or 0),
        )
        prev = best.get(key)
        # prefer higher score, then current names over historical ones
        if prev is None or (cand.score, cand.name_kind.startswith("current")) > (prev.score, prev.name_kind.startswith("current")):
            best[key] = cand
    # On an exact tie, an entity with matches in scope beats one with none: two team
    # ids can share a name while only one of them ever played.
    ranked = sorted(best.values(),
                    key=lambda c: (-c.score, -c.matches, c.name_kind != "current_nickname", c.matched_name.lower()))
    return ranked[:limit]


def load_names(conn: psycopg.Connection, entity_type: Optional[str] = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT entity_type, entity_id, name, name_kind, name_folded, current_name, matches
            FROM entity_names
            WHERE %s::text IS NULL OR entity_type = %s
            """,
            (entity_type, entity_type),
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows


def resolve_id(conn: psycopg.Connection, entity_id: str, entity_type: Optional[str] = None) -> list[Candidate]:
    """Exact lookup by FACEIT entity id, which is how an identical-name tie is broken."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT entity_type, entity_id, current_name, name, name_kind, matches
            FROM entity_names
            WHERE entity_id = %s AND (%s::text IS NULL OR entity_type = %s) AND name_kind LIKE 'current%%'
            LIMIT 1
            """,
            (entity_id, entity_type, entity_type),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        return []
    return [Candidate(entity_type=row["entity_type"], entity_id=row["entity_id"], current_name=row["current_name"],
                      matched_name=row["name"], name_kind="entity_id", score=1.0,
                      matches=int(row.get("matches") or 0))]


def resolve(conn: psycopg.Connection, query: str, entity_type: Optional[str] = None,
            limit: int = 5, min_score: float = 0.5) -> list[Candidate]:
    """Rank all known names for `entity_type` ('player', 'team' or None for both).

    A bare FACEIT id (optionally prefixed `player:` / `team:`) resolves exactly,
    so two entities with identical names can still be told apart.
    """
    q = (query or "").strip()
    m = ENTITY_ID.match(q)
    if m:
        return resolve_id(conn, m.group("id").lower(), m.group("kind") or entity_type)
    m = ORG_ID.match(q)
    if m:
        return resolve_id(conn, m.group("id").lower(), "org")
    return rank_candidates(query, load_names(conn, entity_type), limit=limit, min_score=min_score)
