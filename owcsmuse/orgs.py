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

What review then found, and what the evidence ordering above gets wrong: in
esports whole rosters migrate between organisations, so a high roster overlap is
weak evidence for org identity and sometimes points the other way. On this data
the one real rename (Al qadsiah -> qadsiah) shared 1 of 8 players, while four
pairs at 80-100% overlap were distinct orgs that a squad moved between. Name
identity with academy/B-team exclusion is the reliable signal; roster overlap is
corroboration only and never merges a pair by itself. A reviewed rejection is
recorded in the decisions file, so a pair that was looked at and turned down
never comes back as pending review.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg

from .log import get_logger, log_event
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


def pair_key(a: str, b: str) -> str:
    """Order-independent key for a team-id pair, so one decision cannot be recorded twice."""
    x, y = sorted((a, b))
    return f"{x}|{y}"


@dataclass
class TeamFacts:
    team_id: str
    name: str
    players: set[str] = field(default_factory=set)
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    seasons: set[int] = field(default_factory=set)
    matches: int = 0
    regions: set[str] = field(default_factory=set)   # scope_region values its matches were played in
    names: list[tuple[str, datetime, datetime]] = field(default_factory=list)   # (name, first seen, last seen)


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
    decision_source: str = "auto"   # auto | manual | rejected
    note: Optional[str] = None
    # team_id -> {"valid_from": iso | None, "valid_to": iso | None, "basis": str}: the window the mapping should be
    # valid over. Proposed when a team id carried a name that is not the org's before it carried the org's name
    # (an acquired roster is not the org's history); a decision's own window replaces it in apply().
    windows: dict[str, dict[str, Any]] = field(default_factory=dict)

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
                   count(*) AS matches, array_agg(DISTINCT c.season) FILTER (WHERE c.season IS NOT NULL) AS seasons,
                   array_agg(DISTINCT c.scope_region) FILTER (WHERE c.scope_region IS NOT NULL) AS regions
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
                f.regions = set(r["regions"] or [])
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
        cur.execute("SELECT team_id, name, first_seen_at, last_seen_at FROM team_names ORDER BY team_id, first_seen_at")
        for r in cur.fetchall():
            f = facts.get(r["team_id"])
            if f:
                f.names.append((r["name"], r["first_seen_at"], r["last_seen_at"]))
    conn.commit()
    return {k: v for k, v in facts.items() if v.matches}


def _overlap(a: TeamFacts, b: TeamFacts) -> tuple[float, int, int]:
    if not a.players or not b.players:
        return 0.0, 0, min(len(a.players), len(b.players))
    shared = a.players & b.players
    smaller = min(len(a.players), len(b.players))
    return (len(shared) / smaller if smaller else 0.0), len(shared), smaller


# OWCS is region-locked: a competing roster plays in one of 'na' or 'emea', not
# both, and does not switch between them season to season. So when two team ids
# each have a home region and those regions differ, they are not the same
# continuing roster, whatever the names say. 'international' events (Dreamhack,
# Midseason Championship, ...) are open to any region and never conflict with
# anything: a team competing in the same region plus one international LAN is
# the ordinary case, not a signal of two different orgs.
#
# This exists because it was missing: "SpaceStation Gaming" (na) was merged with
# "SpaceStation" (emea) on a contained-name match with 0% roster overlap, and
# "Geekay Esports" (emea) was merged with "Geekay Esports" (na) on an identical
# name with 0% roster overlap. Both looked like strong evidence under the old
# rules. Neither team ever played a match in the other's region.
REGION_LOCKED = frozenset({"na", "emea"})


def region_conflict(a: TeamFacts, b: TeamFacts) -> Optional[str]:
    """Why two team ids cannot be the same roster, or None when regions don't rule it out."""
    ra = a.regions & REGION_LOCKED
    rb = b.regions & REGION_LOCKED
    if ra and rb and not (ra & rb):
        return (f"refused: '{a.name}' competed in {'/'.join(sorted(ra))} and '{b.name}' in {'/'.join(sorted(rb))} - "
                f"OWCS is region-locked, so a continuing roster does not cross regions")
    return None


def _adjacency(a: TeamFacts, b: TeamFacts) -> tuple[bool, Optional[int]]:
    """Non-overlapping windows, and the gap in days between them."""
    if not (a.first_at and a.last_at and b.first_at and b.last_at):
        return False, None
    if a.last_at < b.first_at:
        return True, (b.first_at - a.last_at).days
    if b.last_at < a.first_at:
        return True, (a.first_at - b.last_at).days
    return False, 0


# The OWCS calendar as the committed reports show it (stage windows from the first and last series seen in each). A
# name change whose old name's last sighting and new name's first sighting fall in different stages happened on a
# stage boundary. Kept as data so it can be extended as stages are added.
STAGE_CALENDAR: tuple[tuple[str, str, str], ...] = (
    # from the first and last series seen in each stage's competitions (regular season, playoffs, relegation)
    ("2024 Stage 1", "2024-03-08", "2024-03-24"), ("2024 Stage 2", "2024-04-12", "2024-05-05"),
    ("2024 Dreamhack Dallas", "2024-05-31", "2024-06-02"),
    ("2025 Stage 1", "2025-01-31", "2025-03-10"), ("2025 Stage 2", "2025-05-10", "2025-06-21"),
    ("2025 Stage 3", "2025-09-07", "2025-10-26"),
    ("2026 Stage 1", "2026-03-21", "2026-06-12"),      # playoffs 2026-04-11/12, then the S8 relegation into late May
    ("2026 Stage 2", "2026-06-13", "2026-07-06"),      # began 2026-06-13
)


def stage_of(when: Optional[datetime]) -> Optional[str]:
    b = stage_bounds(when)
    return b[0] if b else None


def stage_bounds(when: Optional[datetime]) -> Optional[tuple[str, str, str]]:
    """(stage name, first day, last day) of the stage `when` falls in."""
    if when is None:
        return None
    day = when.date().isoformat()
    for name, lo, hi in STAGE_CALENDAR:
        if lo <= day <= hi:
            return name, lo, hi
    return None


# The third signal. FACEIT registers a team under a placeholder ("team_<captain>", or whatever the captain typed) and
# the organisation's name replaces it once the roster has signed up: a placeholder lives in the opening days of a
# stage and is gone inside the same stage. Decided by the project owner from 0c629c99, d20d1868 and 62f7752b, all in
# the first days of 2024 Stage 1.
PLACEHOLDER_DAYS = 14
PLACEHOLDER_PREFIX = "team_"


def is_registration_placeholder(old: tuple[str, datetime, datetime], new: tuple[str, datetime, datetime]) -> Optional[str]:
    """Why `old` is a registration placeholder that `new` replaced, or None."""
    (o_name, o_first, o_last), (n_name, n_first, _n_last) = old, new
    b = stage_bounds(o_first)
    if b is None or stage_bounds(n_first) != b or n_first <= o_last:
        return None
    name, lo, _hi = b
    if o_name.lower().startswith(PLACEHOLDER_PREFIX):
        return f"'{o_name}' is a FACEIT registration placeholder ('{PLACEHOLDER_PREFIX}' prefix) replaced by '{n_name}' inside {name}"
    days = (o_last.date() - date.fromisoformat(lo)).days
    if days < PLACEHOLDER_DAYS:
        return (f"'{o_name}' lived only in the opening {days + 1} day(s) of {name} and '{n_name}' replaced it inside the "
                "same stage: a registration placeholder")
    return None


def _same_handle(a: str, b: str) -> bool:
    """A rename keeps the handle: equal after folding, equal without spaces/punctuation, or one contains the other."""
    fa, fb = fold(a), fold(b)
    squash = lambda x: re.sub(r"[^a-z0-9]", "", x)  # noqa: E731
    if fa == fb or squash(fa) == squash(fb):
        return True
    return name_contains(a, b)[0] or name_contains(b, a)[0] or (squash(fa) and (squash(fa) in squash(fb) or squash(fb) in squash(fa)))


def classify_name_change(old: tuple[str, datetime, datetime], new: tuple[str, datetime, datetime]) -> dict[str, Any]:
    """What a change of name on one team id is, from two signals.

    1. Handle: the new name contains or extends the old one -> a rename by the same organisation.
    2. Stage boundary: the old name's last sighting and the new name's first sighting fall in different stages -> a
       roster pickup by another organisation, which in OWCS lands on a stage boundary.
    3. Registration placeholder (`is_registration_placeholder`): the old name is FACEIT's registration placeholder,
       gone inside the opening days of the same stage -> the same organisation, no window.
    A wholly different name on a stage boundary is a pickup (a window); a kept handle is a rename (no window). When the
    signals disagree - a wholly different name inside one stage, or ranges that overlap - it is reported for a person.
    """
    (o_name, o_first, o_last), (n_name, n_first, n_last) = old, new
    handle_kept = _same_handle(o_name, n_name)
    s_old, s_new = stage_of(o_last), stage_of(n_first)
    overlap = n_first <= o_last
    boundary = (s_old != s_new) and not overlap
    placeholder = is_registration_placeholder(old, new)
    if overlap:
        verdict, why = "disagree", (f"'{n_name}' ({n_first:%Y-%m-%d}..{n_last:%Y-%m-%d}) sits inside '{o_name}''s range "
                                    f"({o_first:%Y-%m-%d}..{o_last:%Y-%m-%d}): the id alternated between the names, which "
                                    "neither signal explains")
    elif handle_kept and boundary:
        verdict, why = "rename", f"'{n_name}' keeps the handle of '{o_name}' (rename), though it first appears in a new stage ({s_old} -> {s_new}); the handle decides"
    elif handle_kept:
        verdict, why = "rename", f"'{n_name}' keeps the handle of '{o_name}': a rename by the same organisation"
    elif placeholder:
        verdict, why = "placeholder", placeholder
    elif boundary:
        verdict, why = "pickup", f"'{n_name}' is a wholly different name first seen in {s_new or 'an unknown stage'} after '{o_name}' last played in {s_old or 'an unknown stage'}: a roster pickup"
    else:
        verdict, why = "disagree", f"'{n_name}' is a wholly different name but appears inside the same stage as '{o_name}' ({s_old}): not a stage-boundary pickup and not a rename"
    return {"old": o_name, "new": n_name, "verdict": verdict, "handle_kept": handle_kept, "stage_boundary": boundary,
            "placeholder": placeholder is not None, "stages": [s_old, s_new], "why": why}


def propose_window(team: TeamFacts, org_name: str) -> Optional[dict[str, Any]]:
    """The window over which `team` should count as `org_name`, or None for all time.

    Name identity is the signal this project trusts. If the team id carried a name that is not the org's
    (neither identical nor contained) BEFORE it first carried the org's name, the earlier era is someone else's -
    a roster the org took over - and the mapping is proposed from the org name's first sighting. Nothing is proposed
    from roster movement: a squad that transferred looks the same as a rename and is not evidence here.
    """
    if not team.names:
        return None
    history = sorted(team.names, key=lambda x: x[1])

    def is_orgs(name: str) -> bool:
        # the same handle with or without spaces ("Virtuspro" / "Virtus pro") is the org's name too
        return (fold(name) == fold(org_name) or re.sub(r"[^a-z0-9]", "", fold(name)) == re.sub(r"[^a-z0-9]", "", fold(org_name))
                or name_contains(name, org_name)[0])

    first_org = next((n for n in history if is_orgs(n[0])), None)
    if first_org is None:
        return None
    foreign_before = [n for n in history if n[1] < first_org[1] and not is_orgs(n[0])]
    if not foreign_before:
        return None
    # the second signal: the change that brought the org's name must be a pickup, not a rename of the earlier name
    last_before = max(foreign_before, key=lambda n: n[2])
    change = classify_name_change(last_before, first_org)
    if change["verdict"] == "rename":
        return None
    names = ", ".join(sorted({n[0] for n in foreign_before}))
    return {"valid_from": first_org[1].isoformat(timespec="seconds"), "valid_to": None,
            "basis": f"carried '{names}' before first appearing as '{first_org[0]}' on {first_org[1]:%Y-%m-%d}; "
                     f"the earlier era is proposed as the team's own, not the org's ({change['verdict']}: {change['why']})"}


def propose(conn: psycopg.Connection, facts: Optional[dict[str, TeamFacts]] = None) -> list[Proposal]:
    """Every candidate team-id pair with the evidence that justifies merging it."""
    facts = facts or load_team_facts(conn)
    ids = sorted(facts)
    out: list[Proposal] = []
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            a, b = facts[a_id], facts[b_id]
            conflict = region_conflict(a, b)
            if conflict:
                continue
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
            windows = {}
            for t in (a, b):
                w = propose_window(t, display.name)
                if w:
                    windows[t.team_id] = w
                    ev.append(f"window for {t.team_id[:8]}: from {w['valid_from'][:10]} - {w['basis']}")
            out.append(Proposal(
                team_ids=[a_id, b_id], names=[a.name, b.name], org_id=slugify(display.name), org_name=display.name,
                roster_overlap=round(overlap, 4), shared_players=shared, smaller_roster=smaller,
                name_exact=name_exact, name_contained=contained, date_adjacent=adjacent, gap_days=gap, seasons=seasons,
                matches=a.matches + b.matches, strength=strength, evidence=ev, windows=windows,
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
        self.rejections: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
            self.data = dict(doc.get("decisions") or {})
            self.rejections = dict(doc.get("rejections") or {})

    def get(self, team_id: str) -> Optional[dict[str, Any]]:
        return self.data.get(team_id)

    def set(self, team_id: str, org_id: str, org_name: str, note: Optional[str] = None,
            team_name: Optional[str] = None, evidence: Optional[list[str]] = None,
            valid_from: Optional[str] = None, valid_to: Optional[str] = None,
            valid_from_name: Optional[str] = None, valid_to_name: Optional[str] = None) -> dict[str, Any]:
        """`valid_from` / `valid_to` (ISO 8601) bound the mapping; absent means for all time.

        `valid_from_name` / `valid_to_name` bound it by the first sighting of that FACEIT team name on this team id
        (team_names.first_seen_at), resolved at load time - a window sourced from the data rather than chosen. An
        explicit timestamp wins where both are given; a name that never appears on the id leaves the mapping unapplied
        and reported, never applied for all time.
        """
        d = {"org_id": org_id, "org_name": org_name, "team_name": team_name, "note": note,
             "evidence": evidence or [], "valid_from": valid_from, "valid_to": valid_to,
             "valid_from_name": valid_from_name, "valid_to_name": valid_to_name,
             "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.data[team_id] = {k: v for k, v in d.items() if v is not None}
        return self.data[team_id]

    def add_window(self, team_id: str, org_id: str, org_name: str, note: Optional[str] = None,
                   team_name: Optional[str] = None, evidence: Optional[list[str]] = None,
                   valid_from: Optional[str] = None, valid_to: Optional[str] = None,
                   valid_from_name: Optional[str] = None, valid_to_name: Optional[str] = None) -> dict[str, Any]:
        """Add a second (third, ...) windowed mapping to a team id that already has one.

        A team id whose names are several organisations' eras carries one window per era under `windows`; each
        window has the same fields as a plain decision. The first call on an undecided id is a plain `set`.
        """
        if team_id not in self.data:
            return self.set(team_id, org_id, org_name, note, team_name, evidence, valid_from, valid_to, valid_from_name, valid_to_name)
        if not (valid_from or valid_from_name or valid_to or valid_to_name):
            raise ValueError("a second mapping on one team id must be windowed")
        entry = self.data[team_id]
        if "windows" not in entry:
            first = {k: v for k, v in entry.items() if k != "decided_at"}
            entry = self.data[team_id] = {"windows": [first], "decided_at": entry.get("decided_at")}
        w = {"org_id": org_id, "org_name": org_name, "team_name": team_name, "note": note, "evidence": evidence or [],
             "valid_from": valid_from, "valid_to": valid_to, "valid_from_name": valid_from_name, "valid_to_name": valid_to_name}
        entry["windows"].append({k: v for k, v in w.items() if v is not None})
        entry["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return entry

    def mappings(self, team_id: str) -> list[dict[str, Any]]:
        """Every org mapping decided for a team id: one for a plain decision, one per window otherwise."""
        d = self.data.get(team_id)
        if not d:
            return []
        if "windows" in d:
            return [{**w, "decided_at": d.get("decided_at")} for w in d["windows"]]
        return [d]

    def unset(self, team_id: str) -> bool:
        return self.data.pop(team_id, None) is not None

    # A rejection is as much a decision as a merge. Without one, a pair that was
    # looked at and turned down comes back as pending review on every run, and
    # the reviewer has no record of having already answered it.
    def reject(self, team_a: str, team_b: str, reason: str,
               names: Optional[list[str]] = None) -> dict[str, Any]:
        d = {"team_ids": sorted((team_a, team_b)), "names": names or [], "reason": reason,
             "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.rejections[pair_key(team_a, team_b)] = d
        return d

    def unreject(self, team_a: str, team_b: str) -> bool:
        return self.rejections.pop(pair_key(team_a, team_b), None) is not None

    def rejection(self, team_a: str, team_b: str) -> Optional[dict[str, Any]]:
        return self.rejections.get(pair_key(team_a, team_b))

    def apply(self, proposals: Iterable[Proposal]) -> list[Proposal]:
        """Mark proposals that are already decided, whether merged or rejected."""
        out = []
        for p in proposals:
            rejected = self.rejection(*p.team_ids) if len(p.team_ids) == 2 else None
            if rejected:
                p.include, p.decision_source = False, "rejected"
                p.note = rejected.get("reason")
                out.append(p)
                continue
            shared = set.intersection(*[{m["org_id"] for m in self.mappings(t)} for t in p.team_ids]) if p.team_ids else set()
            if shared:
                org = sorted(shared)[0]
                decided = [next(m for m in self.mappings(t) if m["org_id"] == org) for t in p.team_ids]
                p.include, p.decision_source = True, "manual"
                p.org_id, p.org_name = decided[0]["org_id"], decided[0].get("org_name", p.org_name)
                p.note = decided[0].get("note")
                for t, d in zip(p.team_ids, decided, strict=True):
                    if d.get("valid_from") or d.get("valid_to"):
                        p.windows[t] = {"valid_from": d.get("valid_from"), "valid_to": d.get("valid_to"), "basis": "decided"}
                    else:
                        p.windows.pop(t, None)      # decided for all time
            out.append(p)
        return out

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "note": ("Reviewed org identity. Keys under `decisions` are FACEIT team ids; each maps to the org it "
                     "belongs to, over [valid_from, valid_to) when those are set (ISO 8601; absent = for all time). "
                     "Outside its window a team id is itself, by the name it carried then. "
                     "A team id whose names are several organisations' eras carries one mapping per era under `windows`. "
                     "A team id absent from this file stays unmapped and is queryable as itself. "
                     "`rejections` are pairs that were reviewed and turned down; they are never proposed again. "
                     "Edit by hand or with `python -m owcsmuse orgs decide` / `orgs reject`."),
            "decisions": dict(sorted(self.data.items(), key=lambda kv: (self.mappings(kv[0])[0].get("org_id", ""), kv[0]))),
            "rejections": dict(sorted(self.rejections.items())),
        }
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path


def load_decisions(conn: psycopg.Connection, decisions: OrgDecisions) -> dict[str, int]:
    """Write the decided mappings into orgs / team_orgs. Only decided ids are written."""
    by_org: dict[str, str] = {}
    for team_id in decisions.data:
        for d in decisions.mappings(team_id):
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
        cur.execute("SELECT DISTINCT team_id FROM team_orgs WHERE team_id NOT LIKE 'lp:team:%'")
        before = {r["team_id"] for r in cur.fetchall()}
        # The file is the whole truth for FACEIT team ids: rewrite the table from it, so a changed window or a
        # removed team id takes effect and nothing stale survives. Liquipedia-born team ids belong to `identity load`.
        cur.execute("DELETE FROM team_orgs WHERE team_id NOT LIKE 'lp:team:%'")
        written = skipped = 0
        unresolved: list[dict[str, str]] = []

        def sighting(team_id: str, name: Optional[str]) -> Optional[datetime]:
            """When this FACEIT name was first seen on this team id, at the series' time as the facts read it.

            team_names.first_seen_at is FACEIT's timestamp, and a result_only series' FACEIT time is when the
            result was entered - hours after Liquipedia dates the same series. A window that starts at FACEIT's
            time of an era's first series leaves Liquipedia's record of that very series outside it, so the
            Liquipedia side resolves to the previous era and the two sources "disagree on teams" (17 of 20
            ambiguous links on production, 2026-10-02). The earliest time any source gives a series the team
            played under that name is the start; it covers the series on both sides.
            """
            if not name:
                return None
            cur.execute("""
                SELECT least(
                    (SELECT first_seen_at FROM team_names WHERE team_id = %s AND name = %s),
                    (SELECT min(least(coalesce(m.liquipedia_played_at, lm.played_at, 'infinity'::timestamptz),
                                      match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)))
                       FROM matches m LEFT JOIN liquipedia_matches lm ON lm.faceit_match_id = m.match_id
                      WHERE (m.faction1_team_id = %s AND m.faction1_name = %s) OR (m.faction2_team_id = %s AND m.faction2_name = %s))
                ) AS at""", (team_id, name, team_id, name, team_id, name))
            row = cur.fetchone()
            return row["at"] if row and row["at"] else None

        for team_id, d in ((t, m) for t in decisions.data for m in decisions.mappings(t)):
            if team_id not in known:
                skipped += 1
                continue
            evidence = list(d.get("evidence") or [])
            bounds: dict[str, Any] = {}
            ok = True
            for side in ("valid_from", "valid_to"):
                bounds[side] = d.get(side)
                name = d.get(f"{side}_name")
                if name and not bounds[side]:
                    seen = sighting(team_id, name)
                    if seen is None:
                        unresolved.append({"team_id": team_id, "org_id": d["org_id"], side: name,
                                           "reason": f"'{name}' never appears on this team id in team_names; mapping not applied"})
                        ok = False
                        break
                    bounds[side] = seen
                    evidence.append(f"{side} = {seen.isoformat(timespec='seconds')}: first sighting of '{name}' on this team id")
                elif name and bounds[side]:
                    evidence.append(f"{side} sourced from the first sighting of '{name}'")
            if not ok:
                continue
            cur.execute(
                """
                INSERT INTO team_orgs (team_id, org_id, source, evidence, valid_from, valid_to)
                VALUES (%s, %s, 'manual', %s, coalesce(%s::timestamptz, '-infinity'), coalesce(%s::timestamptz, 'infinity'))
                """,
                (team_id, d["org_id"], psycopg.types.json.Jsonb(evidence), bounds["valid_from"], bounds["valid_to"]),
            )
            written += 1
        # a team id removed from the decisions file becomes unmapped again
        removed = len(before - set(decisions.data))
        # An org whose last team id was just unmapped (an unmerge, e.g. reversing
        # a wrong cross-region merge) must not linger: it would then resolve as
        # an org entity with no team_ids under it and no rows in any fact view -
        # exactly the shape of a stale reference this project keeps finding.
        # An org a Liquipedia-born team maps to stays: a Liquipedia-only org (scope/liquipedia_team_map.json's
        # `org_name`) has no FACEIT team id at all, and `identity load` owns it and its `lp:team:` mapping.
        cur.execute("DELETE FROM orgs WHERE org_id NOT IN (SELECT DISTINCT org_id FROM team_orgs)")
        cur.execute("DELETE FROM team_orgs WHERE org_id NOT IN (SELECT org_id FROM orgs)")
        orphaned = cur.rowcount
    conn.commit()
    out = {"orgs": len(by_org) - orphaned, "team_ids_mapped": written, "unknown_team_ids_skipped": skipped,
          "unmapped": removed, "orphaned_orgs_removed": orphaned, "windows_unresolved": unresolved}
    log_event(log, logging.INFO, "org_decisions_loaded", **out)
    return out


# --------------------------------------------------------------------- report

def render_report(proposals: list[Proposal], unmapped: Optional[list[dict[str, Any]]] = None) -> str:
    rejected = [p for p in proposals if p.decision_source == "rejected"]
    pending = [p for p in proposals if p.decision_source != "rejected"]
    strong = [p for p in pending if p.strength == "strong"]
    review = [p for p in pending if p.strength != "strong"]
    decided = [p for p in pending if p.decision_source == "manual"]
    lines = [
        "# Org identity proposals",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}. "
        f"{len(proposals)} candidate pairs: {len(strong)} strong, {len(review)} needing review, "
        f"{len(decided)} already merged, {len(rejected)} reviewed and rejected.",
        "",
        "A pair is proposed only with evidence. Names that merely look alike are never merged: a pair whose "
        "names differ must be carried by roster overlap and is marked **review required**. "
        "Nothing merges until it is in `scope/org_decisions.json`.",
        "",
        "Roster overlap is the weakest of the three signals, not the strongest. Whole rosters move between "
        "organisations, so a squad that transferred looks exactly like a rename: the one real rename here "
        "(Al qadsiah / qadsiah) shared 1 of 8 players, while four pairs at 80-100% overlap are distinct orgs. "
        "Name identity is what merges a pair; overlap only corroborates it.",
        "",
        "Apply or turn down one with:",
        "",
        "```",
        "python -m owcsmuse orgs decide <team_id> --org <org-id> --org-name \"<Display Name>\" --note \"...\"",
        "python -m owcsmuse orgs reject <team_id_a> <team_id_b> --reason \"...\"   # decided: not the same org",
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
        mark = "YES" if p.include else ("REJECTED" if p.decision_source == "rejected" else "no")
        return (f"| {mark} | {p.org_name} | {p.roster_overlap:.0%} | "
                f"{p.shared_players}/{p.smaller_roster} | {names} | {', '.join(map(str, p.seasons))} | "
                f"{p.matches} | {ids} | {ev}{note} |")

    lines += [row(p) for p in strong] or ["| | | | | none | | | | |"]
    lines += ["", "## Review required (names differ, merge only on roster evidence)", "",
              "| decided | org | overlap | shared | names | seasons | matches | team ids | evidence |",
              "|---|---|---|---|---|---|---|---|---|"]
    lines += [row(p) for p in review] or ["| | | | | none | | | | |"]
    lines += ["", f"## Reviewed and rejected ({len(rejected)})", "",
              "Decided: these are different organisations. They are not proposed again.", "",
              "| names | overlap | shared | seasons | reason | team ids |", "|---|---|---|---|---|---|"]
    lines += [f"| {' / '.join(p.names)} | {p.roster_overlap:.0%} | {p.shared_players}/{p.smaller_roster} | "
              f"{', '.join(map(str, p.seasons))} | {p.note or ''} | "
              f"{'<br>'.join('`' + t + '`' for t in p.team_ids)} |" for p in rejected] or ["| none | | | | | |"]
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
