"""Entity resolution: human-typed player / team name -> ranked candidates.

Matching is case- and accent-insensitive and considers every name an entity
has carried: current FACEIT nickname, in-game name, historical nicknames, and
current + historical team names (all from the `entity_names` materialized
view). Ranking is done in Python so no database extension is required:

    exact folded match      1.00
    query is a prefix       0.90
    query is contained      0.80   (handles "ksaa" vs "KSAA0")
    name is contained       0.70   (query has extra words)
    difflib similarity      ratio * 0.75, kept when >= min_score (MIN_SCORE, 0.60)

The floor was 0.50 until 2026-10-02, when "geekay esports" scored 0.54 against "rad esports" on the shared word alone.
Measured on production's names, 0.60 removed every fuzzy extra offered for a team name typed correctly (47 -> 0; 236 ->
12 for players) and kept every typo recovery (158/159 team typos, 419/420 player typos); 0.65 lost 15 recoveries.

`rank_candidates()` is pure and unit-tested; `resolve()` adds the query.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

import psycopg

MIN_SCORE = 0.6   # fuzzy floor: see the module docstring

# A FACEIT player/team id, so an ambiguous name can be disambiguated by id.
ENTITY_ID = re.compile(
    r"^(?:(?P<kind>player|team|org):)?"
    r"(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)
# An explicit prefix means "this is an id, look it up exactly", whatever shape
# the id has: a FACEIT GUID for a player or team, a slug for an org. Without a
# prefix only a GUID counts, so a bare name is still matched by name.
PREFIXED_ID = re.compile(r"^(?P<kind>player|team|org):(?P<id>[A-Za-z0-9._-]{1,64})$", re.I)

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
    # What tells two entities with the same name apart, for whoever has to choose.
    seasons: list[int] = field(default_factory=list)
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    question: Optional[str] = None   # a question that resolves to exactly this entity

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def token(self) -> str:
        """The unambiguous way to name this entity in a question."""
        return f"{self.entity_type}:{self.entity_id}"


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
    min_score: float = MIN_SCORE,
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
            seasons=list(row.get("seasons") or []),
            first_at=row.get("first_at"),
            last_at=row.get("last_at"),
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


# What a reviewed alias resolves to, for `ea` (a row of entity_aliases). An alias names a team id or an org; when that
# team id has since been mapped to an org and has no era of its own, it is no longer an entity (entity_names lists only
# the org), so the alias follows it to the org. The name is the entity's own, else the team's or org's stored name,
# never its id: "SSG" pointed at team 6ddc0431 until that team joined the spacestation-gaming org, and from then on
# answered with the UUID as its name (and the team's empty slice as its data).
ALIAS_TARGET = """
    SELECT coalesce(en.entity_type, ea.entity_type) AS entity_type, coalesce(en.entity_id, ea.entity_id) AS entity_id,
           coalesce(en.current_name, (SELECT t.name FROM teams t WHERE t.team_id = ea.entity_id),
                    (SELECT o.name FROM orgs o WHERE o.org_id = ea.entity_id), ea.alias) AS current_name,
           coalesce(en.matches, 0) AS matches, en.seasons, en.first_at, en.last_at
      FROM (SELECT 1) one
      LEFT JOIN LATERAL (
          SELECT n.entity_type, n.entity_id, n.current_name, n.matches, n.seasons, n.first_at, n.last_at
            FROM entity_names n
           WHERE (n.entity_type = ea.entity_type AND n.entity_id = ea.entity_id)
              OR (ea.entity_type = 'team' AND n.entity_type = 'org'
                  AND n.entity_id IN (SELECT w.org_id FROM team_orgs w WHERE w.team_id = ea.entity_id))
           ORDER BY (n.entity_type = ea.entity_type) DESC, (n.name_kind LIKE 'current%%') DESC LIMIT 1
      ) en ON true
"""


def load_names(conn: psycopg.Connection, entity_type: Optional[str] = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT entity_type, entity_id, name, name_kind, name_folded, current_name, matches,
                   seasons, first_at, last_at
            FROM entity_names
            WHERE %s::text IS NULL OR entity_type = %s

            UNION ALL

            -- Reviewed community shorthand ("SSG" -> SpaceStation Gaming) that FACEIT's own
            -- name history does not carry: see aliases.py. `name` is the alias itself (already
            -- folded, and fold() is idempotent) so it scores an exact match against the query
            -- the same way any other name does; `current_name` carries the entity's real display
            -- name for showing what the alias actually resolved to.
            SELECT at.entity_type, at.entity_id, ea.alias AS name,
                   'alias' AS name_kind, ea.alias AS name_folded, at.current_name,
                   at.matches, at.seasons, at.first_at, at.last_at
            FROM entity_aliases ea, LATERAL (""" + ALIAS_TARGET + """) at
            WHERE %s::text IS NULL OR at.entity_type = %s
            """,
            (entity_type, entity_type, entity_type, entity_type),
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows


def resolve_id(conn: psycopg.Connection, entity_id: str, entity_type: Optional[str] = None) -> list[Candidate]:
    """Exact lookup by FACEIT entity id, which is how an identical-name tie is broken."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT entity_type, entity_id, current_name, name, name_kind, matches, seasons, first_at, last_at
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
                      matches=int(row.get("matches") or 0), seasons=list(row.get("seasons") or []),
                      first_at=row.get("first_at"), last_at=row.get("last_at"))]


def resolve_alias(conn: psycopg.Connection, alias: str, entity_type: Optional[str] = None) -> list[Candidate]:
    """Exact lookup of a reviewed alias ('SSG' -> SpaceStation Gaming; see aliases.py).

    A human decided this mapping deliberately, so it must win outright rather
    than being scored against whatever else happens to fuzzy-match the same
    letters - "tm" also starts "TML Nightmare" at score 0.9, close enough to
    the alias's 1.0 to read as ambiguous under the ordinary scoring rules, and
    the alias is exactly the thing that is not supposed to be ambiguous.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT at.entity_type, at.entity_id, at.current_name, ea.alias AS name, at.matches, at.seasons,
                   at.first_at, at.last_at
            FROM entity_aliases ea, LATERAL (""" + ALIAS_TARGET + """) at
            WHERE ea.alias = %s AND (%s::text IS NULL OR at.entity_type = %s)
            """,
            (fold(alias), entity_type, entity_type),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        return []
    return [Candidate(entity_type=row["entity_type"], entity_id=row["entity_id"],
                      current_name=row["current_name"], matched_name=row["name"],
                      name_kind="alias", score=1.0, matches=int(row.get("matches") or 0),
                      seasons=list(row.get("seasons") or []), first_at=row.get("first_at"), last_at=row.get("last_at"))]


def resolve(conn: psycopg.Connection, query: str, entity_type: Optional[str] = None,
            limit: int = 5, min_score: float = MIN_SCORE) -> list[Candidate]:
    """Rank all known names for `entity_type` ('player', 'team' or None for both).

    A FACEIT id resolves exactly, so two entities with identical names can still
    be told apart: bare when it is a GUID, or prefixed `player:` / `team:` /
    `org:` for any id, which is how a clarify candidate names itself. A reviewed
    alias resolves exactly too, and takes precedence over whatever else happens
    to fuzzy-match the same short string.
    """
    q = (query or "").strip()
    m = PREFIXED_ID.match(q)
    if m:
        return resolve_id(conn, m.group("id").lower(), m.group("kind").lower())
    m = ENTITY_ID.match(q)
    if m:
        return resolve_id(conn, m.group("id").lower(), m.group("kind") or entity_type)
    alias_hit = resolve_alias(conn, q, entity_type)
    if alias_hit:
        return alias_hit
    cands = rank_candidates(query, load_names(conn, entity_type), limit=limit, min_score=min_score)
    words = q.split()
    if len(words) > 1 and fold(words[0]) == "team" and not (cands and cands[0].score >= 1.0):
        # "Team Liquid" is a name and matched whole above; "team twisted minds" is the word in front of one
        rest = resolve(conn, " ".join(words[1:]), entity_type, limit=limit, min_score=min_score)
        if rest and (not cands or rest[0].score > cands[0].score):
            return rest
    return cands
