"""The FACEIT side of a reconciliation, and how a Liquipedia match is oriented against it.

`orient` answers one narrow question - is Liquipedia's opponent 1 our faction 1, or our faction 2? - and says
which evidence answered it, because every later comparison (scores, winner) depends on it and a wrong orientation
would manufacture disagreements that are not there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import psycopg

from ..resolve import fold
from .matches import LPMatch

# (name, region of the page it appears on) -> (org_key, source): source 'decided' (a reviewed mapping) or 'proposed'
# (evidence, not yet reviewed). The region matters: two unrelated teams can share a name across NA and EMEA.
# resolve(name, region=None, at=None) -> (org key, "decided" | "proposed") | None; `at` is the series' own time
Resolve = Callable[..., Optional[tuple[str, str]]]


@dataclass(frozen=True)
class FaceitSide:
    match_id: str
    championship_id: str
    competition: str
    region: Optional[str]              # scope_region: na | emea | international | other
    season: Optional[int]
    time: Optional[datetime]           # UTC: started_at, else the best fallback (match_time())
    best_of: Optional[int]
    org1: Optional[str]
    org2: Optional[str]
    name1: str
    name2: str
    score1: Optional[int]
    score2: Optional[int]
    winner: int                        # 1, 2, or 0
    state: str                         # complete | result_only
    maps: int                          # rounds with stats: 0 for a result-only series
    time_reliable: bool = True         # False when there is no started_at: the time is then when the result was entered

    @property
    def pair(self) -> frozenset[Optional[str]]:
        return frozenset({self.org1, self.org2})


def load_faceit_side(conn: psycopg.Connection, championship_ids: Optional[list[str]] = None) -> list[FaceitSide]:
    """Every finished FACEIT series in scope (byes are 'skipped' and so absent), with its teams' org keys."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.match_id, m.championship_id, c.name AS competition, c.scope_region AS region, c.season,
                   match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS t,
                   m.best_of, ti1.org_key AS org1, ti2.org_key AS org2,
                   coalesce(m.faction1_name, '') AS name1, coalesce(m.faction2_name, '') AS name2,
                   m.faction1_score AS s1, m.faction2_score AS s2, m.winner_faction, m.ingest_state,
                   (SELECT count(*) FROM match_rounds r WHERE r.match_id = m.match_id) AS maps,
                   (m.started_at IS NOT NULL) AS time_reliable
              FROM matches m
              JOIN championships c ON c.championship_id = m.championship_id
              CROSS JOIN LATERAL (SELECT match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS at) x
              LEFT JOIN LATERAL team_identity_at(m.faction1_team_id, x.at) ti1 ON true
              LEFT JOIN LATERAL team_identity_at(m.faction2_team_id, x.at) ti2 ON true
             WHERE c.include AND m.status = 'FINISHED' AND m.ingest_state IN ('complete', 'result_only')
               AND (%(cids)s::text[] IS NULL OR m.championship_id = ANY(%(cids)s))
            """, {"cids": championship_ids})
        rows = cur.fetchall()
    return [FaceitSide(r["match_id"], r["championship_id"], r["competition"], r["region"], r["season"], r["t"],
                       r["best_of"], r["org1"], r["org2"], r["name1"], r["name2"], r["s1"], r["s2"],
                       {"faction1": 1, "faction2": 2}.get(r["winner_faction"], 0), r["ingest_state"], int(r["maps"]),
                       bool(r["time_reliable"]))
            for r in rows]


def load_faceit_no_result(conn: psycopg.Connection, championship_ids: Optional[list[str]] = None) -> dict[str, FaceitSide]:
    """FACEIT rooms in scope that hold no result: ABORTED, CANCELLED or PAUSED, no winner and no score (ingest skipped
    them). PAUSED is here because FACEIT moves 2026 Stage 3 rooms between all three (rooms seen ABORTED on 2026-10-23
    were PAUSED or CANCELLED two days later): until a room is FINISHED it says nothing about the series.

    A room FACEIT configured and aborted minutes later holds nothing about the series it was opened for (2026 Stage 3:
    12 rooms, played outside FACEIT). Keyed by match id, with the teams' org keys at the room's time so a caller can
    check the room was opened for the same two teams the Liquipedia record names.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.match_id, m.championship_id, c.name AS competition, c.scope_region AS region, c.season,
                   match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS t,
                   m.best_of, ti1.org_key AS org1, ti2.org_key AS org2,
                   coalesce(m.faction1_name, '') AS name1, coalesce(m.faction2_name, '') AS name2, m.status
              FROM matches m
              JOIN championships c ON c.championship_id = m.championship_id
              CROSS JOIN LATERAL (SELECT match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS at) x
              LEFT JOIN LATERAL team_identity_at(m.faction1_team_id, x.at) ti1 ON true
              LEFT JOIN LATERAL team_identity_at(m.faction2_team_id, x.at) ti2 ON true
             WHERE c.include AND m.status IN ('ABORTED', 'CANCELLED', 'PAUSED') AND m.ingest_state = 'skipped'
               AND m.winner_faction IS NULL AND m.faction1_score IS NULL AND m.faction2_score IS NULL
               AND (%(cids)s::text[] IS NULL OR m.championship_id = ANY(%(cids)s))
            """, {"cids": championship_ids})
        rows = cur.fetchall()
    return {r["match_id"]: FaceitSide(r["match_id"], r["championship_id"], r["competition"], r["region"], r["season"],
                                      r["t"], r["best_of"], r["org1"], r["org2"], r["name1"], r["name2"], None, None, 0,
                                      r["status"].lower(), 0, False)
            for r in rows}


def orient(lp: LPMatch, f: FaceitSide, resolve: Optional[Resolve] = None) -> tuple[Optional[bool], str]:
    """(flip, basis). flip=False: LP team 1 is FACEIT faction 1. flip=True: LP team 1 is faction 2. None: cannot tell.

    In order of strength: the two teams' org keys, then team names that fold equal, then the series score (only
    when it is not level), and last the winner. `basis` names the one that decided it.
    """
    if resolve:
        a, b = resolve(lp.team1, lp.region, lp.played_at), resolve(lp.team2, lp.region, lp.played_at)
        if a and b and {a[0], b[0]} == {f.org1, f.org2} and a[0] != b[0]:
            return (a[0] != f.org1), "orgs"
    n1, n2, m1, m2 = fold(lp.team1), fold(lp.team2), fold(f.name1), fold(f.name2)
    if n1 and n2 and n1 != n2:
        if (n1, n2) == (m1, m2) or n1 == m1 or n2 == m2:
            return False, "names"
        if (n1, n2) == (m2, m1) or n1 == m2 or n2 == m1:
            return True, "names"
    if None not in (lp.score1, lp.score2, f.score1, f.score2) and lp.score1 != lp.score2:
        if (lp.score1, lp.score2) == (f.score1, f.score2):
            return False, "score"
        if (lp.score1, lp.score2) == (f.score2, f.score1):
            return True, "score"
    if lp.winner and f.winner:
        return (lp.winner != f.winner), "winner"
    return None, "unknown"
