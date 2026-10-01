"""Stage 2: map-level results for `result_only` FACEIT series, from what Stage 1 already linked and stored.

FACEIT records a series result without per-map stats for 76 series in scope; Liquipedia's `match2games` has map,
mode, per-map score and winner for the ones it also covers - never player stats. This module only ever INSERTs
match_rounds rows for a match FACEIT holds none for, so there is never a same-round conflict between the two
sources to arbitrate: FACEIT wins for map stats by construction, because its presence is what skips a match here.

Offline: `plan()` and `enrich()` both read only what `run_reconciliation()` already loaded from stored raw_payloads
(see pipeline.py's own docstring) plus one small query for team ids. Neither sends a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .matches import LPGame, LPMatch
from .model import FaceitSide, orient
from .pipeline import Run
from .reconcile import EXACT
from .teams import TeamMap, make_resolver

PUSH_MODE = "push"


@dataclass
class Candidate:
    match_id: str
    lp_objectname: str
    page_url: str
    action: str                                # enriched | already_has_rounds | no_liquipedia_games | cannot_orient
    games: int = 0
    disagreements: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EnrichResult:
    candidates: list[Candidate] = field(default_factory=list)

    def by_action(self) -> dict[str, list[Candidate]]:
        out: dict[str, list[Candidate]] = {}
        for c in self.candidates:
            out.setdefault(c.action, []).append(c)
        return out


def _round_scores(game: LPGame) -> tuple[int, int]:
    """FACEIT's own convention: a round-count for every mode except Push, which it always scores as a 1/0 win
    indicator (round_stats never carries the push distance). Liquipedia's Push score is the literal distance
    (e.g. 103.12), which does not fit an integer round-count column and would misrepresent the other rows of the
    same mode - so a Push map is normalised to the same win indicator FACEIT already uses everywhere else."""
    if (game.mode or "").strip().lower() == PUSH_MODE:
        return (1, 0) if game.winner == 1 else (0, 1) if game.winner == 2 else (0, 0)
    if len(game.scores) == 2:
        try:
            return int(game.scores[0]), int(game.scores[1])
        except (TypeError, ValueError):
            pass
    return (1, 0) if game.winner == 1 else (0, 1) if game.winner == 2 else (0, 0)


def _candidates(run: Run) -> list[tuple[LPMatch, FaceitSide, Any]]:
    by_id = {f.match_id: f for f in run.faceit}
    out = []
    for lk in run.result.links:
        if lk.tier == EXACT and lk.faceit_id and by_id.get(lk.faceit_id) and by_id[lk.faceit_id].state == "result_only":
            out.append((lk.lp, by_id[lk.faceit_id], lk))
    return out


def plan(run: Run) -> EnrichResult:
    """Classify every exact-linked result_only match, writing nothing. All data needed is already in `run`
    (loaded from stored raw_payloads), so there is never a gap here that would need a new request."""
    out = EnrichResult()
    for lp, f, _lk in _candidates(run):
        if not lp.games:
            out.candidates.append(Candidate(f.match_id, lp.objectname, lp.page_url, "no_liquipedia_games"))
        else:
            out.candidates.append(Candidate(f.match_id, lp.objectname, lp.page_url, "enriched", games=len(lp.games)))
    return out


def enrich(conn: psycopg.Connection, run: Run, team_map_path: str) -> EnrichResult:
    """Insert match_rounds for every exact-linked result_only match FACEIT has none for, and correct the played
    date for the ones that gain rows. Skips (never overwrites) any match FACEIT already has rounds for."""
    decided = TeamMap(team_map_path)
    resolver = make_resolver(decided, {p.key: p for p in run.proposals}, use_proposals=True)
    candidates = _candidates(run)
    result = EnrichResult()
    if not candidates:
        return result

    match_ids = [f.match_id for _, f, _lk in candidates]
    with conn.cursor() as cur:
        cur.execute("SELECT match_id, faction1_team_id, faction2_team_id FROM matches WHERE match_id = ANY(%s)",
                    (match_ids,))
        team_ids = {r["match_id"]: (r["faction1_team_id"], r["faction2_team_id"]) for r in cur.fetchall()}
        cur.execute("SELECT match_id, count(*) AS n FROM match_rounds WHERE match_id = ANY(%s) GROUP BY match_id",
                    (match_ids,))
        existing = {r["match_id"]: r["n"] for r in cur.fetchall()}

        for lp, f, lk in candidates:
            cand = Candidate(f.match_id, lp.objectname, lp.page_url, "enriched", disagreements=[])
            if existing.get(f.match_id):
                cand.action = "already_has_rounds"
                result.candidates.append(cand)
                continue
            if not lp.games:
                cand.action = "no_liquipedia_games"
                result.candidates.append(cand)
                continue
            flip, _basis = orient(lp, f, resolver)
            if flip is None:
                cand.action = "cannot_orient"
                result.candidates.append(cand)
                continue
            t1_id, t2_id = team_ids[f.match_id]
            rows = []
            for i, game in enumerate(lp.games):
                s1, s2 = _round_scores(game)
                if flip:
                    s1, s2 = s2, s1
                winner_id = None
                if game.winner == 1:
                    winner_id = t2_id if flip else t1_id
                elif game.winner == 2:
                    winner_id = t1_id if flip else t2_id
                raw = {"liquipedia": {"map": game.map, "mode": game.mode, "winner": game.winner,
                                      "scores": list(game.scores), "page_url": lp.page_url}}
                rows.append((f.match_id, i + 1, None, game.map, game.mode, f"{s1} / {s2}", winner_id,
                            t1_id, s1, t2_id, s2, None, Jsonb(raw), "liquipedia"))
            cur.executemany(
                """INSERT INTO match_rounds
                     (match_id, round_number, map_guid, map_name, game_mode, score_summary, winner_team_id,
                      team1_team_id, team1_score, team2_team_id, team2_score, team_stats, raw_round_stats, source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
            cur.execute(
                """UPDATE matches SET maps_played = %s, liquipedia_played_at = %s, date_source = 'liquipedia'
                    WHERE match_id = %s""",
                (len(lp.games), lp.played_at, f.match_id))
            cand.games = len(lp.games)
            cand.disagreements = lk.disagreements  # already computed by Stage 1's own comparison
            result.candidates.append(cand)
    conn.commit()
    return result
