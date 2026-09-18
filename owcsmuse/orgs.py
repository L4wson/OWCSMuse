"""Org-level team identity: propose, review, apply.

FACEIT reissues a team id per season, so one organisation appears as several
team ids. This proposes mappings from evidence and routes every one through the
same manual review gate as scope decisions.

Evidence, in the order it is weighed:

* `name_exact`      the two team names fold to the same string. Necessary for a
                    strong proposal, never sufficient on its own.
* `roster_overlap`  share of the smaller roster the two team ids have in common.
                    This is what actually identifies an organisation.
* `date_adjacent`   the two teams' match windows do not overlap, which is what
                    you expect of the same org in consecutive seasons, and not
                    what you expect of two teams that coexist.

A pair is never proposed on name similarity: "Team Liquid" and "Liquid Academy"
fold differently and would fail `name_exact`, and nothing here does fuzzy
matching. Proposals with different names require strong roster evidence and are
marked `review_required` so they cannot pass without being looked at.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg

from .logging import get_logger, log_event
from .resolve import fold

log = get_logger("owcsmuse.orgs")

DEFAULT_ORG_DECISIONS_PATH = Path("scope") / "org_decisions.json"
DEFAULT_ORG_REPORT_PATH = Path("scope") / "org_report.md"

# A pair with identical names still needs one corroborating signal.
MIN_OVERLAP_SAME_NAME = 0.0      # any shared player, or date adjacency, is enough
MIN_OVERLAP_DIFFERENT_NAME = 0.6  # a rename must be carried by the roster
MAX_GAP_DAYS = 500                # consecutive seasons, not an unrelated revival

# Tokens that carry no identity on their own, so "Team X" and "X" are the same
# handle while "Team Peps" and "Team Falcons" are not.
GENERIC_TOKENS = frozenset({"team", "esports", "esport", "gaming", "club", "gg", "the"})
# Tokens that mark a deliberately SEPARATE entity. "Team Liquid" and
# "Team Liquid Academy" must never merge, so containment is refused when the
# longer name adds one of these.
SEPARATE_ENTITY_TOKENS = frozenset({"academy", "junior", "juniors", "youth", "reserve", "reserves",
                                    "b", "ii", "2", "women", "womens", "w", "black", "white", "blue", "red"})


def _tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in fold(name).split() if t)


def name_contains(a: str, b: str) -> tuple[bool, str]:
    """True when one name's tokens are a proper subset of the other's.

    Exact token containment, never fuzzy similarity: "qadsiah" is inside
    "al qadsiah", but "liquid academy" and "team liquid" contain each other
    neither way, and an added Academy/B-team token refuses the match outright.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb or ta == tb:
        return False, ""
    small, large = (ta, tb) if len(ta) < len(tb) else (tb, ta)
    if not small < large:
        return False, ""
    if not (small - GENERIC_TOKENS):
        return False, f"the shorter name is only generic tokens ({' '.join(sorted(small))})"
    extra = large - small
    blocked = extra & SEPARATE_ENTITY_TOKENS
    if blocked:
        return False, f"refused: the longer name adds {'/'.join(sorted(blocked))}, which marks a separate team"
    return True, f"one name's tokens are inside the other ({' '.join(sorted(small))} in {' '.join(sorted(large))})"


def slugify(name: str) -> str:
    n = unicodedata.normalize("NFKD", name or "")
    n = "".join(ch for ch in n if not unicodedata.combining(ch)).lower()
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n or "org"


@dataclass
class TeamFacts:
    team_id: str
    name: str
    players: set[str] = field(default_factory=set)
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    seasons: set[int] = field(default_factory=set)
    matches: int = 0


@dataclass
class Proposal:
    team_ids: list[str]
    names: list[str]
    org_id: str
    org_name: str
    roster_overlap: float           # share of the smaller roster shared
    shared_players: int
    smaller_roster: int
    name_exact: bool
    name_contained: bool
    date_adjacent: bool
    gap_days: Optional[int]
    seasons: list[int]
    matches: int
    strength: str                   # strong | review_required
    evidence: list[str] = field(default_factory=list)
    include: bool = False           # only a reviewed decision sets this
    decision_source: str = "auto"
    note: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_team_facts(conn: psycopg.Connection) -> dict[str, TeamFacts]:
    """Per team id: roster, date window, seasons and match count, from ingested data."""
    facts: dict[str, TeamFacts] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT team_id, name FROM teams WHERE name IS NOT NULL")
        for r in cur.fetchall():
            facts[r["team_id"]] = TeamFacts(team_id=r["team_id"], name=r["name"])
        cur.execute(
            """
            SELECT t.team_id,
                   min(coalesce(m.started_at, m.finished_at, m.configured_at)) AS first_at,
                   max(coalesce(m.started_at, m.finished_at, m.configured_at)) AS last_at,
                   count(*) AS matches, array_agg(DISTINCT c.season) FILTER (WHERE c.season IS NOT NULL) AS seasons
            FROM matches m
            JOIN championships c USING (championship_id)
            CROSS JOIN LATERAL (VALUES (m.faction1_team_id), (m.faction2_team_id)) AS t(team_id)
            WHERE c.include AND t.team_id IS NOT NULL
            GROUP BY t.team_id
            """
        )
        for r in cur.fetchall():
            f = facts.get(r["team_id"])
            if f:
                f.first_at, f.last_at, f.matches = r["first_at"], r["last_at"], r["matches"]
                f.seasons = set(r["seasons"] or [])
        cur.execute(
            """
            SELECT team_id, array_agg(DISTINCT player_id) AS players
            FROM match_rosters WHERE team_id IS NOT NULL GROUP BY team_id
            """
        )
        for r in cur.fetchall():
            f = facts.get(r["team_id"])
            if f:
                f.players = set(r["players"] or [])
    conn.commit()
    return {k: v for k, v in facts.items() if v.matches}


def _overlap(a: TeamFacts, b: TeamFacts) -> tuple[float, int, int]:
    if not a.players or not b.players:
        return 0.0, 0, min(len(a.players), len(b.players))
    shared = a.players & b.players
    smaller = min(len(a.players), len(b.players))
    return (len(shared) / smaller if smaller else 0.0), len(shared), smaller


def _adjacency(a: TeamFacts, b: TeamFacts) -> tuple[bool, Optional[int]]:
    """Non-overlapping windows, and the gap in days between them."""
    if not (a.first_at and a.last_at and b.first_at and b.last_at):
        return False, None
    if a.last_at < b.first_at:
        return True, (b.first_at - a.last_at).days
    if b.last_at < a.first_at:
        return True, (a.first_at - b.last_at).days
    return False, 0


def propose(conn: psycopg.Connection, facts: Optional[dict[str, TeamFacts]] = None) -> list[Proposal]:
    """Every candidate team-id pair with the evidence that justifies merging it."""
    facts = facts or load_team_facts(conn)
    ids = sorted(facts)
    out: list[Proposal] = []
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            a, b = facts[a_id], facts[b_id]
            name_exact = fold(a.name) == fold(b.name)
            overlap, shared, smaller = _overlap(a, b)
            adjacent, gap = _adjacency(a, b)
            contained, contain_note = name_contains(a.name, b.name)
            if name_exact:
                if not (shared or adjacent):
                    continue
                strength = "strong"
            elif contained and adjacent:
                strength = "review_required"
            else:
                if overlap < MIN_OVERLAP_DIFFERENT_NAME or not adjacent:
                    continue
                strength = "review_required"
            if adjacent and gap is not None and gap > MAX_GAP_DAYS:
                continue
            ev = []
            if name_exact:
                ev.append(f"names fold identically ('{fold(a.name)}')")
            elif contained:
                ev.append(f"names differ but {contain_note} - requires review")
            else:
                ev.append(f"names differ ('{a.name}' vs '{b.name}') and neither contains the other - requires review")
            ev.append(f"roster overlap {overlap:.0%}: {shared} of the smaller {smaller}-player roster shared"
                      if smaller else "no roster data for either team id")
            if adjacent:
                ev.append(f"match windows do not overlap, {gap} day gap "
                          f"({a.first_at:%Y-%m-%d}..{a.last_at:%Y-%m-%d} then {b.first_at:%Y-%m-%d}..{b.last_at:%Y-%m-%d})"
                          if a.last_at < b.first_at else
                          f"match windows do not overlap, {gap} day gap "
                          f"({b.first_at:%Y-%m-%d}..{b.last_at:%Y-%m-%d} then {a.first_at:%Y-%m-%d}..{a.last_at:%Y-%m-%d})")
            else:
                ev.append("match windows overlap, so these may be two teams that coexisted")
            seasons = sorted(a.seasons | b.seasons)
            ev.append(f"seasons {', '.join(map(str, seasons))}; {a.matches} + {b.matches} matches")
            display = max((a, b), key=lambda t: (t.last_at or datetime.min.replace(tzinfo=timezone.utc)))
            out.append(Proposal(
                team_ids=[a_id, b_id], names=[a.name, b.name], org_id=slugify(display.name), org_name=display.name,
                roster_overlap=round(overlap, 4), shared_players=shared, smaller_roster=smaller,
                name_exact=name_exact, name_contained=contained, date_adjacent=adjacent, gap_days=gap, seasons=seasons,
                matches=a.matches + b.matches, strength=strength, evidence=ev,
            ))
    out.sort(key=lambda p: (p.strength != "strong", -p.roster_overlap, p.org_name))
    log_event(log, logging.INFO, "org_proposals", proposals=len(out),
              strong=sum(1 for p in out if p.strength == "strong"))
    return out


# ------------------------------------------------------------------ decisions

class OrgDecisions:
    """Reviewed team-id -> org mappings. Identical shape to the scope decisions file."""

    def __init__(self, path: str | Path = DEFAULT_ORG_DECISIONS_PATH) -> None:
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                self.data = dict(json.load(f).get("decisions") or {})

    def get(self, team_id: str) -> Optional[dict[str, Any]]:
        return self.data.get(team_id)

    def set(self, team_id: str, org_id: str, org_name: str, note: Optional[str] = None,
            team_name: Optional[str] = None, evidence: Optional[list[str]] = None) -> dict[str, Any]:
        d = {"org_id": org_id, "org_name": org_name, "team_name": team_name, "note": note,
             "evidence": evidence or [], "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.data[team_id] = {k: v for k, v in d.items() if v is not None}
        return self.data[team_id]

    def unset(self, team_id: str) -> bool:
        return self.data.pop(team_id, None) is not None

    def apply(self, proposals: Iterable[Proposal]) -> list[Proposal]:
        """Mark proposals whose team ids are already decided."""
        out = []
        for p in proposals:
            decided = [self.data.get(t) for t in p.team_ids]
            if all(d and d["org_id"] == decided[0]["org_id"] for d in decided):
                p.include, p.decision_source = True, "manual"
                p.org_id, p.org_name = decided[0]["org_id"], decided[0].get("org_name", p.org_name)
                p.note = decided[0].get("note")
            out.append(p)
        return out

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "note": ("Reviewed org identity. Keys are FACEIT team ids; each maps to the org it belongs to. "
                     "A team id absent from this file stays unmapped and is queryable as itself. "
                     "Edit by hand or with `python -m owcsmuse orgs decide`."),
            "decisions": dict(sorted(self.data.items(), key=lambda kv: (kv[1].get("org_id", ""), kv[0]))),
        }
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path


def load_decisions(conn: psycopg.Connection, decisions: OrgDecisions) -> dict[str, int]:
    """Write the decided mappings into orgs / team_orgs. Only decided ids are written."""
    by_org: dict[str, str] = {}
    for team_id, d in decisions.data.items():
        by_org[d["org_id"]] = d.get("org_name") or d["org_id"]
    with conn.cursor() as cur:
        for org_id, name in by_org.items():
            cur.execute(
                """
                INSERT INTO orgs (org_id, name) VALUES (%s, %s)
                ON CONFLICT (org_id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
                """,
                (org_id, name),
            )
        cur.execute("SELECT team_id FROM teams")
        known = {r["team_id"] for r in cur.fetchall()}
        written = skipped = 0
        for team_id, d in decisions.data.items():
            if team_id not in known:
                skipped += 1
                continue
            cur.execute(
                """
                INSERT INTO team_orgs (team_id, org_id, source, evidence)
                VALUES (%s, %s, 'manual', %s)
                ON CONFLICT (team_id) DO UPDATE SET org_id = EXCLUDED.org_id, evidence = EXCLUDED.evidence,
                                                    source = 'manual', decided_at = now()
                """,
                (team_id, d["org_id"], psycopg.types.json.Jsonb(d.get("evidence") or [])),
            )
            written += 1
        # a team id removed from the decisions file becomes unmapped again
        cur.execute("DELETE FROM team_orgs WHERE NOT (team_id = ANY(%s))", (list(decisions.data),))
        removed = cur.rowcount
    conn.commit()
    out = {"orgs": len(by_org), "team_ids_mapped": written, "unknown_team_ids_skipped": skipped, "unmapped": removed}
    log_event(log, logging.INFO, "org_decisions_loaded", **out)
    return out


# --------------------------------------------------------------------- report

def render_report(proposals: list[Proposal], unmapped: Optional[list[dict[str, Any]]] = None) -> str:
    strong = [p for p in proposals if p.strength == "strong"]
    review = [p for p in proposals if p.strength != "strong"]
    decided = [p for p in proposals if p.decision_source == "manual"]
    lines = [
        "# Org identity proposals",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}. "
        f"{len(proposals)} candidate pairs: {len(strong)} strong, {len(review)} needing review, "
        f"{len(decided)} already decided.",
        "",
        "A pair is proposed only with evidence. Names that merely look alike are never merged: a pair whose "
        "names differ must be carried by roster overlap and is marked **review required**. "
        "Nothing merges until it is in `scope/org_decisions.json`.",
        "",
        "Apply one with:",
        "",
        "```",
        "python -m owcsmuse orgs decide <team_id> --org <org-id> --org-name \"<Display Name>\" --note \"...\"",
        "python -m owcsmuse orgs load      # write decisions into orgs / team_orgs",
        "```",
        "",
        "## Strong proposals (identical names, corroborated)",
        "",
        "| decided | org | overlap | shared | names | seasons | matches | team ids | evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def row(p: Proposal) -> str:
        ev = "<br>".join(p.evidence)
        ids = "<br>".join(f"`{t}`" for t in p.team_ids)
        names = " / ".join(p.names)
        note = f" **note:** {p.note}" if p.note else ""
        return (f"| {'YES' if p.include else 'no'} | {p.org_name} | {p.roster_overlap:.0%} | "
                f"{p.shared_players}/{p.smaller_roster} | {names} | {', '.join(map(str, p.seasons))} | "
                f"{p.matches} | {ids} | {ev}{note} |")

    lines += [row(p) for p in strong] or ["| | | | | none | | | | |"]
    lines += ["", "## Review required (names differ, merge only on roster evidence)", "",
              "| decided | org | overlap | shared | names | seasons | matches | team ids | evidence |",
              "|---|---|---|---|---|---|---|---|---|"]
    lines += [row(p) for p in review] or ["| | | | | none | | | | |"]
    if unmapped:
        lines += ["", f"## Unmapped team ids ({len(unmapped)})", "",
                  "These stay queryable as themselves; nothing is assumed about them.", "",
                  "| team | matches | seasons | team_id |", "|---|---|---|---|"]
        for u in unmapped:
            lines.append(f"| {u['name']} | {u['matches']} | {', '.join(map(str, u.get('seasons') or []))} | `{u['team_id']}` |")
    lines.append("")
    return "\n".join(lines)


def unmapped_teams(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.team_id, t.name,
                   count(m.match_id) AS matches,
                   array_agg(DISTINCT c.season) FILTER (WHERE c.season IS NOT NULL) AS seasons
            FROM teams t
            LEFT JOIN team_orgs tm ON tm.team_id = t.team_id
            LEFT JOIN matches m ON t.team_id IN (m.faction1_team_id, m.faction2_team_id)
            LEFT JOIN championships c ON c.championship_id = m.championship_id AND c.include
            WHERE tm.team_id IS NULL
            GROUP BY t.team_id, t.name
            HAVING count(m.match_id) > 0
            ORDER BY count(m.match_id) DESC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows
