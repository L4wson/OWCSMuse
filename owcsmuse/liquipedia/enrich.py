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
        # an exact link, or an ambiguous one a person confirmed; never a provisional or disagreeing pair
        if ((lk.tier == EXACT or lk.decision == "confirmed") and lk.faceit_id and not lk.provisional
                and by_id.get(lk.faceit_id) and by_id[lk.faceit_id].state == "result_only"):
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
    from .pipeline import load_team_windows
    decided = TeamMap(team_map_path)
    resolver = make_resolver(decided, {p.key: p for p in run.proposals}, use_proposals=True,
                             team_windows=load_team_windows(conn))
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


# ------------------------------------------------------------------ maps FACEIT's /stats dropped (045)

@dataclass
class Recovery:
    """One map FACEIT's /stats left out of a complete series, and what was done about it."""
    match_id: str
    round_number: int
    map_name: str | None
    action: str        # recovered | not_on_liquipedia | map_differs | winner_differs | cannot_orient | picks_unaligned
    faceit: dict[str, Any] = field(default_factory=dict)
    liquipedia: dict[str, Any] = field(default_factory=dict)


def dropped_positions(detailed_results: list[Any], stored: set[int]) -> list[tuple[int, dict[str, Any]]]:
    """(position, entry) for every detailed_results entry with a winner that /stats returned no round for.

    Not every such entry is a played map: FACEIT keeps entries no game stands behind - the phantom 1-0 "Dorado" in
    Toronto Defiant v Timeless's grand final (FACEIT 5-0, presented 4-0 from Liquipedia), a 0-0 "map 6" in Twisted
    Minds v ENCE - so an entry is only a candidate until Liquipedia's record of the same series has a game there.
    """
    out = []
    for n, e in enumerate(detailed_results or [], start=1):
        if n in stored or not isinstance(e, dict) or e.get("winner") not in ("faction1", "faction2"):
            continue
        out.append((n, e))
    return out


def judge(n: int, entry: dict[str, Any], pick_name: str | None, aligned: bool, flip: bool | None,
          game: LPGame | None) -> str:
    """Whether a dropped position is a played map: Liquipedia must have a game there, on the same map, with the same
    winner. Pure, so the rule is testable without a database."""
    from ..resolve import fold
    if not aligned:
        return "picks_unaligned"
    if flip is None:
        return "cannot_orient"
    if game is None:
        return "not_on_liquipedia"
    if fold(game.map or "") != fold(pick_name or ""):
        return "map_differs"
    faceit_side1_won = entry.get("winner") == "faction1"
    lp_side1_won = game.winner == 1
    if game.winner not in (1, 2) or (lp_side1_won != faceit_side1_won) != flip:
        return "winner_differs"
    return "recovered"


def _complete_links(run: Run) -> list[tuple[LPMatch, FaceitSide, Any]]:
    by_id = {f.match_id: f for f in run.faceit}
    return [(lk.lp, by_id[lk.faceit_id], lk) for lk in run.result.links
            if (lk.tier == EXACT or lk.decision == "confirmed") and lk.faceit_id and not lk.provisional
            and by_id.get(lk.faceit_id) and by_id[lk.faceit_id].state == "complete"]


def recover_dropped_maps(conn: psycopg.Connection, run: Run, team_map_path: str, write: bool = True) -> list[Recovery]:
    """Write the maps FACEIT's /stats dropped from a complete series, where Liquipedia corroborates them.

    The match's own detailed_results still holds every map's winner and score. A position counts as a played map
    only when the linked Liquipedia record has a game there with the same map (FACEIT's pick at that position, when
    every stored round sits at its own pick) and the same winner. Written as source 'faceit_results': FACEIT's
    winner and score, Liquipedia's mode, no player rows. maps_played then becomes the match's round count. Sends
    nothing: the detail payload and the Liquipedia record are both already stored. A detail re-apply clears a match's
    rounds, so this runs with every enrich, after the detail phase, the way Liquipedia's own rounds are restored.
    """
    from .pipeline import load_team_windows
    links = _complete_links(run)
    if not links:
        return []
    ids = [f.match_id for _, f, _ in links]
    with conn.cursor() as cur:
        cur.execute("""SELECT m.match_id, m.faction1_team_id, m.faction2_team_id, d.payload->'detailed_results' AS dr
                         FROM matches m JOIN raw_payloads d ON d.id = m.detail_raw_id WHERE m.match_id = ANY(%s)""", (ids,))
        detail = {r["match_id"]: r for r in cur.fetchall()}
        cur.execute("SELECT match_id, round_number, map_guid FROM match_rounds WHERE match_id = ANY(%s)", (ids,))
        stored: dict[str, dict[int, Any]] = {}
        for r in cur.fetchall():
            stored.setdefault(r["match_id"], {})[r["round_number"]] = r["map_guid"]
        cur.execute("SELECT match_id, pick_order, map_guid, map_name FROM match_map_picks WHERE match_id = ANY(%s)", (ids,))
        picks: dict[str, dict[int, Any]] = {}
        for r in cur.fetchall():
            picks.setdefault(r["match_id"], {})[r["pick_order"]] = r
    conn.commit()

    todo = [(lp, f) for lp, f, _ in links
            if dropped_positions((detail.get(f.match_id) or {}).get("dr") or [], set(stored.get(f.match_id, {})))]
    if not todo:
        return []
    resolver = make_resolver(TeamMap(team_map_path), {p.key: p for p in run.proposals}, use_proposals=True,
                             team_windows=load_team_windows(conn))
    out: list[Recovery] = []
    for lp, f in todo:
        d = detail[f.match_id]
        have = stored.get(f.match_id, {})
        mp = picks.get(f.match_id, {})
        aligned = bool(have) and all(g and n in mp and mp[n]["map_guid"] == g for n, g in have.items())
        flip, _basis = orient(lp, f, resolver)
        t1, t2 = d["faction1_team_id"], d["faction2_team_id"]
        rows = []
        for n, e in dropped_positions(d["dr"] or [], set(have)):
            fa = e.get("factions") or {}
            s1, s2 = (fa.get("faction1") or {}).get("score"), (fa.get("faction2") or {}).get("score")
            pick = mp.get(n) if aligned else None
            game = lp.games[n - 1] if 0 < n <= len(lp.games) else None
            rec = Recovery(f.match_id, n, pick["map_name"] if pick else None,
                           judge(n, e, pick["map_name"] if pick else None, aligned, flip, game),
                           faceit={"winner": e.get("winner"), "score": [s1, s2]},
                           liquipedia={"map": game.map, "winner": game.winner, "mode": game.mode} if game else {})
            out.append(rec)
            if rec.action == "recovered":
                raw = {"recovered_from": "faceit detailed_results", "entry": e,
                       "corroborated_by": {"liquipedia": rec.liquipedia, "page_url": lp.page_url}}
                rows.append((f.match_id, n, pick["map_guid"], pick["map_name"], game.mode, f"{s1} / {s2}",
                             t1 if e["winner"] == "faction1" else t2, t1, s1, t2, s2, None, Jsonb(raw),
                             "faceit_results"))
        if rows and write:
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO match_rounds
                         (match_id, round_number, map_guid, map_name, game_mode, score_summary, winner_team_id,
                          team1_team_id, team1_score, team2_team_id, team2_score, team_stats, raw_round_stats, source)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (match_id, round_number) DO NOTHING""", rows)
                cur.execute("UPDATE matches SET maps_played = (SELECT count(*) FROM match_rounds r WHERE r.match_id = %s) "
                            "WHERE match_id = %s", (f.match_id, f.match_id))
    if write:
        conn.commit()
    return out
