"""Cross-source identity: which FACEIT player a Liquipedia page is, proposed with evidence and decided by a person.

A Liquipedia line-up names its players by page ("HYEON_(Kim_Seong-hyeon)"); FACEIT names its roster by GUID. When a
series is linked across the two sources (an exact or strong link, nothing provisional), both sides name the same
line-up of the same match, so "the same handle, on the same side, of the same series" is match-level evidence that a
page and a GUID are one player. That is the only evidence proposed here. Roster overlap across different matches is
not evidence of anything (a squad that transferred looks the same), and a handle match with no shared series is
listed for a person to look at, never proposed.

Nothing is applied without a decision: `scope/player_identity_decisions.json` holds page -> GUID (or "new", a
Liquipedia-born player with no FACEIT id), and rejections; `load_identity` writes anchors from that file and from the
reviewed team map, and nothing else.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg

from ..resolve import fold
from .model import orient
from .teams import TeamMap, make_resolver

DEFAULT_PLAYER_DECISIONS_PATH = "scope/player_identity_decisions.json"
DEFAULT_REPORT_PATH = "scope/identity_report.md"
BORN_PREFIX = "lp:player:"

STRONG, REVIEW, UNMATCHED = "strong", "review", "unmatched"


@dataclass
class Sighting:
    """One Liquipedia player on one side of one linked series, with the FACEIT roster that stood on that side."""
    page: str
    handle: str
    real_name: Optional[str]
    nationality: Optional[str]
    faceit_match_id: str
    faceit_team_id: Optional[str]
    roster: list[tuple[str, str, Optional[str]]]       # (player_id, nickname at match, in-game name)


@dataclass
class PlayerProposal:
    page: str
    handle: str
    real_name: Optional[str] = None
    nationality: Optional[str] = None
    candidates: dict[str, dict[str, Any]] = field(default_factory=dict)   # GUID -> {names, matches}
    series: int = 0
    faceit_names_seen: list[str] = field(default_factory=list)
    strength: str = UNMATCHED
    evidence: list[str] = field(default_factory=list)
    decided: Optional[dict[str, Any]] = None
    decision_source: str = "auto"                                          # auto | manual | rejected

    @property
    def guid(self) -> Optional[str]:
        return next(iter(self.candidates)) if len(self.candidates) == 1 else None


def _names(roster_row: tuple[str, str, Optional[str]]) -> set[str]:
    return {fold(n) for n in roster_row[1:] if n}


def sightings(conn: psycopg.Connection, run, team_map_path: str) -> list[Sighting]:
    """Every (page, side, series) on an exact or strong, non-provisional link, with the FACEIT roster of that side."""
    decided = TeamMap(team_map_path)
    resolver = make_resolver(decided, {p.key: p for p in run.proposals}, use_proposals=True)
    by_id = {f.match_id: f for f in run.faceit}
    links = [lk for lk in run.result.links if lk.faceit_id and lk.tier in ("exact", "strong") and not lk.provisional]
    ids = [lk.faceit_id for lk in links]
    with conn.cursor() as cur:
        cur.execute("SELECT match_id, faction1_team_id, faction2_team_id FROM matches WHERE match_id = ANY(%s)", (ids,))
        factions = {r["match_id"]: (r["faction1_team_id"], r["faction2_team_id"]) for r in cur.fetchall()}
        cur.execute(
            """SELECT r.match_id, r.team_id, r.player_id, coalesce(r.nickname_at_match, p.nickname) AS nickname,
                      coalesce(r.game_player_name, p.game_player_name) AS game_name
                 FROM match_rosters r JOIN players p ON p.player_id = r.player_id
                WHERE r.match_id = ANY(%s)""", (ids,))
        rosters: dict[tuple[str, Optional[str]], list[tuple[str, str, Optional[str]]]] = defaultdict(list)
        for r in cur.fetchall():
            rosters[(r["match_id"], r["team_id"])].append((r["player_id"], r["nickname"], r["game_name"]))
    conn.commit()
    out: list[Sighting] = []
    for lk in links:
        f = by_id.get(lk.faceit_id)
        if not f or lk.faceit_id not in factions:
            continue
        flip, _ = orient(lk.lp, f, resolver)
        if flip is None:
            continue
        t1, t2 = factions[lk.faceit_id]
        for side, players in ((1, lk.lp.players1), (2, lk.lp.players2)):
            team_id = (t2 if flip else t1) if side == 1 else (t1 if flip else t2)
            roster = rosters.get((lk.faceit_id, team_id), [])
            for pl in players:
                out.append(Sighting(pl.page, pl.handle, pl.real_name, pl.nationality, lk.faceit_id, team_id, roster))
    return out


def propose_players(seen: Iterable[Sighting]) -> list[PlayerProposal]:
    """One proposal per Liquipedia page: the GUID(s) whose FACEIT name equalled its handle on the same side of a
    linked series. Strong only when the pairing is one-to-one; anything else waits for a person."""
    by_page: dict[str, PlayerProposal] = {}
    pages_of_guid: dict[str, set[str]] = defaultdict(set)
    for s in seen:
        p = by_page.setdefault(s.page, PlayerProposal(s.page, s.handle, s.real_name, s.nationality))
        p.series += 1
        handle = fold(s.handle)
        hit = False
        for row in s.roster:
            if handle and handle in _names(row):
                c = p.candidates.setdefault(row[0], {"names": set(), "matches": []})
                c["names"].update(n for n in row[1:] if n)
                c["matches"].append(s.faceit_match_id)
                pages_of_guid[row[0]].add(s.page)
                hit = True
        if not hit:
            p.faceit_names_seen.extend(n for row in s.roster for n in (row[1],) if n)
    for p in by_page.values():
        for c in p.candidates.values():
            c["names"] = sorted(c["names"])
            c["matches"] = sorted(set(c["matches"]))
        if not p.candidates:
            p.strength = UNMATCHED
            names = sorted(set(p.faceit_names_seen))
            p.evidence.append(f"no FACEIT name on the same side of {p.series} linked series equals '{p.handle}'"
                              + (f"; FACEIT named: {', '.join(names[:12])}" if names else ""))
            continue
        if len(p.candidates) == 1:
            guid, c = next(iter(p.candidates.items()))
            others = pages_of_guid[guid] - {p.page}
            if others:
                p.strength = REVIEW
                p.evidence.append(f"GUID {guid[:8]} also matched Liquipedia page(s) {', '.join(sorted(others))}")
            else:
                p.strength = STRONG
            p.evidence.append(f"'{p.handle}' stood on the same side as FACEIT {guid[:8]} "
                              f"({' / '.join(c['names'])}) in {len(c['matches'])} linked series")
        else:
            p.strength = REVIEW
            p.evidence.append("the handle matched several FACEIT players: "
                              + "; ".join(f"{g[:8]} ({' / '.join(c['names'])}) in {len(c['matches'])}" for g, c in p.candidates.items()))
    return sorted(by_page.values(), key=lambda p: ({STRONG: 0, REVIEW: 1, UNMATCHED: 2}[p.strength], fold(p.handle)))


class PlayerDecisions:
    """page -> {entity_id (a FACEIT GUID) | null (a Liquipedia-born player), handle, note}; plus rejections."""

    FILE_NOTE = ("Reviewed Liquipedia player page -> FACEIT player. entity_id null means a Liquipedia-born player "
                 "with no FACEIT id (it gets id lp:player:<page>). `rejections` are page|guid pairs reviewed and "
                 "turned down. Edit by hand or with `python -m owcsmuse identity decide` / `identity reject`.")

    def __init__(self, path: str | Path = DEFAULT_PLAYER_DECISIONS_PATH) -> None:
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        self.rejections: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = dict(doc.get("decisions") or {})
            self.rejections = dict(doc.get("rejections") or {})

    def set(self, page: str, entity_id: Optional[str], handle: str, note: Optional[str] = None,
            real_name: Optional[str] = None) -> dict[str, Any]:
        self.data[page] = {"entity_id": entity_id, "handle": handle, "real_name": real_name, "note": note,
                           "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return self.data[page]

    def unset(self, page: str) -> bool:
        return self.data.pop(page, None) is not None

    def reject(self, page: str, guid: str, reason: str) -> dict[str, Any]:
        self.rejections[f"{page}|{guid}"] = {"page": page, "entity_id": guid, "reason": reason,
                                            "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return self.rejections[f"{page}|{guid}"]

    def rejected(self, page: str, guid: str) -> bool:
        return f"{page}|{guid}" in self.rejections

    def apply(self, proposals: list[PlayerProposal]) -> list[PlayerProposal]:
        for p in proposals:
            for guid in [g for g in p.candidates if self.rejected(p.page, g)]:
                p.candidates.pop(guid)
                p.evidence.append(f"GUID {guid[:8]} reviewed and rejected for this page")
                if p.strength == STRONG:
                    p.strength = REVIEW
            d = self.data.get(p.page)
            if d:
                p.decided, p.decision_source = d, "manual"
        return proposals

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"note": self.FILE_NOTE, "decisions": dict(sorted(self.data.items())),
               "rejections": dict(sorted(self.rejections.items()))}
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path


def accept_strong(decisions: PlayerDecisions, proposals: list[PlayerProposal]) -> int:
    n = 0
    for p in proposals:
        if p.strength == STRONG and p.decided is None and p.guid:
            decisions.set(p.page, p.guid, p.handle, "accepted strong proposal: " + p.evidence[-1], p.real_name)
            p.decided, p.decision_source = decisions.data[p.page], "manual"
            n += 1
    return n


def render_report(proposals: list[PlayerProposal], team_map: TeamMap) -> str:
    strong = [p for p in proposals if p.strength == STRONG and not p.decided]
    review = [p for p in proposals if p.strength == REVIEW and not p.decided]
    unmatched = [p for p in proposals if p.strength == UNMATCHED and not p.decided]
    decided = [p for p in proposals if p.decided]
    lines = [
        "# Cross-source identity: Liquipedia pages -> FACEIT players",
        "",
        f"{len(proposals)} Liquipedia player pages seen on linked series: {len(decided)} decided, {len(strong)} proposed "
        f"strong, {len(review)} need a person, {len(unmatched)} matched no FACEIT name. Team names: "
        f"{len(team_map.data)} decided in scope/liquipedia_team_map.json (they become team anchors on load).",
        "",
        "Evidence is match-level only: the same handle on the same side of the same linked series. Nothing is applied "
        "until decided (`identity accept`, `identity decide <page> --player <guid>` or `--new`) and loaded (`identity load`).",
        "",
    ]

    def table(title: str, ps: list[PlayerProposal]) -> None:
        lines.extend([f"## {title} ({len(ps)})", "", "| page | handle | real name | nationality | FACEIT | series | evidence |",
                      "|---|---|---|---|---|---|---|"])
        for p in ps:
            fac = p.decided["entity_id"] if p.decided else (", ".join(f"`{g}`" for g in p.candidates) or "")
            if p.decided and p.decided["entity_id"] is None:
                fac = "(Liquipedia-born)"
            lines.append(f"| {p.page} | {p.handle} | {p.real_name or ''} | {p.nationality or ''} | {fac} | {p.series} | "
                         + "; ".join(p.evidence) + " |")
        lines.append("")

    table("Proposed - strong (one page, one GUID, same side of a linked series)", strong)
    table("Needs a person", review)
    table("No FACEIT name matched", unmatched)
    table("Already decided", decided)
    return "\n".join(lines) + "\n"


def load_identity(conn: psycopg.Connection, decisions: PlayerDecisions, team_map: TeamMap) -> dict[str, int]:
    """Rewrite entity_anchors from the two reviewed files; create Liquipedia-born players for `null` decisions."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM entity_anchors")
        teams = 0
        for key, d in team_map.data.items():
            name, _, region = key.partition("|")
            cur.execute(
                """INSERT INTO entity_anchors (entity_type, entity_id, source, anchor_kind, anchor, region, basis, note)
                   VALUES (%s, %s, 'liquipedia', 'team_name', %s, %s, 'team_map', %s)
                   ON CONFLICT DO NOTHING""",
                (d["entity_type"], d["entity_id"], name, region or "", d.get("note")))
            teams += 1
        cur.execute("SELECT player_id FROM players")
        known = {r["player_id"] for r in cur.fetchall()}
        players = born = skipped = 0
        for page, d in decisions.data.items():
            if d.get("entity_id") is None:
                pid = BORN_PREFIX + page
                cur.execute(
                    """INSERT INTO players (player_id, nickname, game_player_name)
                       VALUES (%s, %s, %s) ON CONFLICT (player_id) DO UPDATE SET nickname = EXCLUDED.nickname,
                       game_player_name = EXCLUDED.game_player_name, updated_at = now()""",
                    (pid, d.get("handle") or page, d.get("real_name")))
                basis, born = "born", born + 1
            else:
                pid = d["entity_id"]
                if pid not in known:
                    skipped += 1
                    continue
                basis = "decision"
            cur.execute(
                """INSERT INTO entity_anchors (entity_type, entity_id, source, anchor_kind, anchor, basis, note)
                   VALUES ('player', %s, 'liquipedia', 'player_page', %s, %s, %s)""",
                (pid, page, basis, d.get("note")))
            players += 1
        # a Liquipedia-born player whose decision was withdrawn must not linger as a ghost entity
        cur.execute("DELETE FROM players WHERE player_id LIKE %s AND NOT (player_id = ANY(%s))",
                    (BORN_PREFIX + "%", [BORN_PREFIX + p for p, d in decisions.data.items() if d.get("entity_id") is None]))
        ghosts = cur.rowcount
    conn.commit()
    return {"team_anchors": teams, "player_anchors": players, "liquipedia_born_players": born,
            "unknown_faceit_ids_skipped": skipped, "ghost_players_removed": ghosts}
