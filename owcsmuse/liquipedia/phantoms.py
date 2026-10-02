"""Phantom maps: FACEIT map rows for maps that were never played.

FACEIT's platform keeps a fixed number of map slots per series format. When a sweep closes a series early, its
parser logs a default placeholder win for the winning team on the next map in the pool rotation; the map was never
picked or played, the series score is inflated by it, and the best-of the score implies is wrong (the 2024 NA and
EMEA Stage 1 grand finals: 4-0 sweeps that FACEIT stores as 5-0 with a Dorado nobody played). Liquipedia records
the real result.

This module finds the extent, from stored data only (no request is ever sent):
  1. linked_excess     every linked series where FACEIT's map count or series score exceeds Liquipedia's, with both
                       sources' values and the FACEIT map(s) Liquipedia does not have
  2. placeholder_rows  every FACEIT map row with a placeholder shape: a win with no player rows, a score pattern its
                       game mode cannot produce, or no map name
  3. clustering        whether those rows sit on sweeps and on the last map, as the mechanism predicts
`python -m owcsmuse liquipedia phantoms` writes the report; nothing here changes data or precedence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import psycopg

from .model import orient
from .pipeline import Run, load_team_windows
from .reconcile import EXACT
from .teams import TeamMap, make_resolver

# the score a game mode's winner shows in FACEIT's round_stats, and the most the loser can: anything else is not a
# played map of that mode (Escort and Hybrid score by distance/points and are not constrained here)
MODE_SHAPES: dict[str, tuple[int, int]] = {"control": (2, 1), "flashpoint": (3, 2), "push": (1, 0)}


@dataclass
class Excess:
    match_id: str
    lp_objectname: str
    page_url: str
    competition: str
    teams: str
    link_tier: str                    # exact | confirmed | ambiguous (an exact id whose records disagree on the score)
    faceit_score: str
    lp_score: str
    faceit_maps: int                  # match_rounds rows from FACEIT
    lp_games: int
    faceit_map_names: list[str]
    lp_map_names: list[str]
    extra_maps: list[str]             # FACEIT maps Liquipedia does not list (by name, in FACEIT order)
    stored_best_of: Optional[int]
    lp_best_of: Optional[int]
    sweep: bool                       # Liquipedia's loser score is 0
    orientation: str


@dataclass
class PlaceholderRow:
    match_id: str
    round_number: int
    map_name: Optional[str]
    game_mode: Optional[str]
    score: str
    reasons: list[str]
    last_map: bool
    sweep: bool                       # FACEIT's stored loser score is 0
    stored_best_of: Optional[int]
    competition: str
    player_rows: int
    linked: bool
    beyond_liquipedia: Optional[bool]  # round_number > Liquipedia's game count, when linked


@dataclass
class PhantomReport:
    excess: list[Excess] = field(default_factory=list)
    rows: list[PlaceholderRow] = field(default_factory=list)
    linked_checked: int = 0
    faceit_maps_checked: int = 0
    sweeps_checked: int = 0            # FACEIT series whose stored loser score is 0

    def clustering(self) -> dict[str, Any]:
        on_sweeps = sum(1 for r in self.rows if r.sweep)
        last = sum(1 for r in self.rows if r.last_map)
        beyond = sum(1 for r in self.rows if r.beyond_liquipedia)
        return {"placeholder_rows": len(self.rows), "on_sweeps": on_sweeps, "on_last_map": last,
                "beyond_liquipedias_games": beyond,
                "excess_series": len(self.excess), "excess_on_sweeps": sum(1 for e in self.excess if e.sweep),
                "excess_held_ambiguous": sum(1 for e in self.excess if e.link_tier == "ambiguous"),
                "extra_map_names": sorted({m for e in self.excess for m in e.extra_maps})}


def linked_excess(conn: psycopg.Connection, run: Run, team_map_path: str) -> tuple[list[Excess], int]:
    """Every exact or confirmed link where FACEIT has more maps, or a higher score, than Liquipedia."""
    decided = TeamMap(team_map_path)
    resolver = make_resolver(decided, {p.key: p for p in run.proposals}, use_proposals=True,
                             team_windows=load_team_windows(conn))
    by_id = {f.match_id: f for f in run.faceit}
    # every record that names a FACEIT id we hold, or was linked to one: a phantom-inflated FACEIT score is exactly
    # what makes an exact id "disagree on score" and land in the ambiguous tier, so the tier is reported, not filtered
    pairs = []
    for lk in run.result.links:
        if lk.decision == "rejected":
            continue
        fid = lk.faceit_id if (lk.tier == EXACT or lk.decision == "confirmed") and not lk.provisional else lk.lp.faceit_match_id
        if fid and by_id.get(fid):
            pairs.append((lk.lp, by_id[fid], lk.tier if lk.decision != "confirmed" else "confirmed"))
    if not pairs:
        return [], 0
    ids = [f.match_id for _, f, _t in pairs]
    with conn.cursor() as cur:
        cur.execute("""SELECT match_id, round_number, map_name, source FROM match_rounds
                        WHERE match_id = ANY(%s) ORDER BY match_id, round_number""", (ids,))
        rounds: dict[str, list[dict]] = {}
        for r in cur.fetchall():
            rounds.setdefault(r["match_id"], []).append(r)
        cur.execute("SELECT match_id, best_of, faction1_score, faction2_score FROM matches WHERE match_id = ANY(%s)", (ids,))
        stored = {r["match_id"]: r for r in cur.fetchall()}
    out: list[Excess] = []
    for lp, f, tier in pairs:
        faceit_rounds = [r for r in rounds.get(f.match_id, []) if r["source"] != "liquipedia"]
        flip, basis = orient(lp, f, resolver)
        lp_s1, lp_s2 = (lp.score1, lp.score2) if not flip else (lp.score2, lp.score1)
        st = stored.get(f.match_id, {})
        f_s1, f_s2 = st.get("faction1_score"), st.get("faction2_score")
        lp_games = len(lp.games) if lp.games else (lp.n_games or 0)
        more_maps = lp_games and len(faceit_rounds) > lp_games
        more_score = (None not in (lp_s1, lp_s2, f_s1, f_s2)
                      and (max(f_s1, f_s2) > max(lp_s1, lp_s2) or f_s1 + f_s2 > lp_s1 + lp_s2))
        if not (more_maps or more_score):
            continue
        lp_names = [g.map or "?" for g in lp.games]
        f_names = [r["map_name"] or "?" for r in faceit_rounds]
        remaining = list(lp_names)
        extra = []
        for n in f_names:
            if n in remaining:
                remaining.remove(n)
            else:
                extra.append(n)
        out.append(Excess(f.match_id, lp.objectname, lp.page_url, f.competition, f"{f.name1} vs {f.name2}", tier,
                          f"{f_s1}-{f_s2}", f"{lp_s1}-{lp_s2}", len(faceit_rounds), lp_games, f_names, lp_names, extra,
                          st.get("best_of"), lp.best_of,
                          sweep=(None not in (lp_s1, lp_s2) and min(lp_s1, lp_s2) == 0), orientation=basis if flip is not None else "unknown"))
    return out, len(pairs)


def placeholder_rows(conn: psycopg.Connection, lp_games_by_match: Optional[dict[str, int]] = None) -> tuple[list[PlaceholderRow], int, int]:
    """Every FACEIT map row with a placeholder shape, over every in-scope match."""
    lp_games_by_match = lp_games_by_match or {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.match_id, r.round_number, r.map_name, r.game_mode, r.team1_score, r.team2_score,
                   r.winner_team_id, r.team1_team_id,
                   (SELECT count(*) FROM match_players mp WHERE mp.match_id = r.match_id AND mp.round_number = r.round_number) AS player_rows,
                   (SELECT count(*) FROM match_players mp WHERE mp.match_id = r.match_id) AS match_player_rows,
                   (SELECT max(round_number) FROM match_rounds x WHERE x.match_id = r.match_id) AS last_round,
                   m.best_of, m.faction1_score, m.faction2_score, c.name AS competition
              FROM match_rounds r
              JOIN matches m ON m.match_id = r.match_id
              JOIN championships c ON c.championship_id = m.championship_id
             WHERE c.include AND m.ingest_state IN ('complete', 'result_only') AND coalesce(r.source, 'faceit') <> 'liquipedia'
             ORDER BY r.match_id, r.round_number""")
        rows = cur.fetchall()
        cur.execute("""SELECT count(*) AS n FROM matches m JOIN championships c ON c.championship_id = m.championship_id
                        WHERE c.include AND m.ingest_state IN ('complete', 'result_only')
                          AND least(m.faction1_score, m.faction2_score) = 0 AND greatest(m.faction1_score, m.faction2_score) > 0""")
        sweeps = int(cur.fetchone()["n"])
    out: list[PlaceholderRow] = []
    for r in rows:
        reasons = []
        s1, s2 = r["team1_score"], r["team2_score"]
        if r["winner_team_id"] and r["player_rows"] == 0 and r["match_player_rows"] > 0:
            reasons.append("win with no player rows while the match has player rows on other maps")
        if not r["map_name"]:
            reasons.append("no map name")
        mode = (r["game_mode"] or "").strip().lower()
        if mode in MODE_SHAPES and None not in (s1, s2) and r["winner_team_id"]:
            win_s, lose_s = (s1, s2) if r["winner_team_id"] == r["team1_team_id"] else (s2, s1)
            need, cap = MODE_SHAPES[mode]
            if win_s != need or lose_s > cap or lose_s >= win_s:
                reasons.append(f"{r['game_mode']} scored {s1}-{s2}: a played {r['game_mode']} map ends {need}-x with x <= {cap}")
        elif r["winner_team_id"] and (s1, s2) == (0, 0):
            reasons.append("a winner with a 0-0 score")
        if not reasons:
            continue
        f1, f2 = r["faction1_score"], r["faction2_score"]
        lp_n = lp_games_by_match.get(r["match_id"])
        out.append(PlaceholderRow(r["match_id"], r["round_number"], r["map_name"], r["game_mode"], f"{s1}-{s2}", reasons,
                                  last_map=r["round_number"] == r["last_round"],
                                  sweep=(None not in (f1, f2) and min(f1, f2) == 0 and max(f1, f2) > 0),
                                  stored_best_of=r["best_of"], competition=r["competition"], player_rows=int(r["player_rows"]),
                                  linked=lp_n is not None, beyond_liquipedia=(r["round_number"] > lp_n) if lp_n else None))
    return out, len(rows), sweeps


def find(conn: psycopg.Connection, run: Run, team_map_path: str) -> PhantomReport:
    rep = PhantomReport()
    rep.excess, rep.linked_checked = linked_excess(conn, run, team_map_path)
    by_id = {f.match_id: f for f in run.faceit}
    lp_games = {}
    for lk in run.result.links:
        fid = lk.faceit_id if (lk.tier == EXACT or lk.decision == "confirmed") and not lk.provisional else lk.lp.faceit_match_id
        if fid in by_id and lk.decision != "rejected":
            lp_games[fid] = len(lk.lp.games) or lk.lp.n_games or 0
    rep.rows, rep.faceit_maps_checked, rep.sweeps_checked = placeholder_rows(conn, lp_games)
    return rep


def render(rep: PhantomReport) -> str:
    c = rep.clustering()
    L = ["# Phantom maps: FACEIT map rows for maps that were never played", "",
         "FACEIT keeps a fixed number of map slots per series format and, when a sweep closes a series early, logs a "
         "default win for the winner on the next map in the rotation. Nothing here is applied: this is the extent, from "
         "stored data only, for a person to read before the precedence rule changes.", "",
         f"Linked series compared against Liquipedia: {rep.linked_checked}. FACEIT map rows examined: "
         f"{rep.faceit_maps_checked} over every in-scope series ({rep.sweeps_checked} of those series are sweeps by "
         f"FACEIT's stored score).", "",
         "## 1. Linked series where FACEIT exceeds Liquipedia", ""]
    if not rep.excess:
        L.append("None.")
    else:
        L += ["| FACEIT match | link | competition | teams | FACEIT score / maps | Liquipedia score / games | FACEIT maps Liquipedia lacks | stored bo | LP bo | sweep | oriented by |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for e in rep.excess:
            L.append(f"| {e.match_id} | {e.link_tier} | {e.competition} | {e.teams} | {e.faceit_score} / {e.faceit_maps} | {e.lp_score} / {e.lp_games} | "
                     f"{', '.join(e.extra_maps) or '-'} | {e.stored_best_of} | {e.lp_best_of} | {'yes' if e.sweep else 'no'} | {e.orientation} |")
        L.append("")
        L.append("`ambiguous` here is an exact FACEIT id whose two records disagree on the score: with a phantom map that is "
                 "the expected shape, and the stricter link rule (Stage 3) withholds the link until a person confirms it.")
        L.append("")
        for e in rep.excess:
            L.append(f"- {e.match_id}: FACEIT maps {e.faceit_map_names}; Liquipedia games {e.lp_map_names}; {e.page_url}")
    L += ["", "## 2. FACEIT map rows with a placeholder shape", ""]
    if not rep.rows:
        L.append("None.")
    else:
        L += ["| FACEIT match | map # | map | mode | score | player rows | last map | sweep | stored bo | linked | beyond LP games | why |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rep.rows:
            L.append(f"| {r.match_id} | {r.round_number} | {r.map_name or '?'} | {r.game_mode or '?'} | {r.score} | {r.player_rows} | "
                     f"{'yes' if r.last_map else 'no'} | {'yes' if r.sweep else 'no'} | {r.stored_best_of} | {'yes' if r.linked else 'no'} | "
                     f"{'-' if r.beyond_liquipedia is None else ('yes' if r.beyond_liquipedia else 'no')} | {'; '.join(r.reasons)} |")
    L += ["", "## 3. Clustering", "",
          f"- placeholder-shaped rows: {c['placeholder_rows']}; on sweeps: {c['on_sweeps']}; on the series' last map: "
          f"{c['on_last_map']}; beyond Liquipedia's game count: {c['beyond_liquipedias_games']}",
          f"- series where FACEIT exceeds Liquipedia: {c['excess_series']}; of those, sweeps: {c['excess_on_sweeps']}",
          f"- the extra maps' names: {', '.join(c['extra_map_names']) or '-'}",
          "", "A phantom map by the mechanism is: on a sweep, the series' last map, beyond Liquipedia's game count, a win "
          "with no player rows (or player rows FACEIT fabricated along with it). Rows matching all of that are the "
          "systematic case; the rest need a look."]
    return "\n".join(L) + "\n"
