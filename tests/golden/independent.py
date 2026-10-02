"""Ground truth for the golden suite, computed from the raw FACEIT payloads and nothing else.

This module imports nothing from owcsmuse - no parser, no warehouse, no query
layer - so it cannot inherit a bug from them. It reads the captured JSON in
tests/golden/payloads and counts. When an answer disagrees with it, one of the
two is wrong, and the raw payload is the tie-break.

Definitions (the README's, restated so they can be checked against it):
  map won        the round's round_stats.Winner is the player's/team's team id
  series won     detail.results.winner names the team's faction
  series score   detail.results.score, per faction (this is what map_wins/map_losses on a
                 team record are: series score, so a series with no map stats still counts)
  maps (team)    rounds that exist in the stats payload
  a bye          a faction whose id or name is 'bye'; not a series
  kills          FACEIT's "Eliminations" ("kills" is what people say)
  kd_ratio       total Eliminations / total Deaths
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

GOLDEN = Path(__file__).parent


def load():
    manifest = json.loads((GOLDEN / "matches.json").read_text(encoding="utf-8"))
    return {m["match_id"]: json.loads((GOLDEN / "payloads" / f"{m['match_id']}.json").read_text(encoding="utf-8"))
            for m in manifest["matches"]}


def championships():
    return {c["championship_id"]: c for c in json.loads((GOLDEN / "championships.json").read_text(encoding="utf-8"))["championships"]}


def is_bye(f) -> bool:
    return f["faction_id"].lower() == "bye" or (f.get("name") or "").strip().lower() == "bye"


class Series:
    """One series, straight from a detail payload (+ its stats payload when there is one)."""

    def __init__(self, match_id, raw):
        d = raw["detail"]
        champ = championships()[d["competition_id"]]
        self.match_id = match_id
        self.detail = d
        self.champ = d["competition_id"]
        self.region = champ["scope_region"]
        self.season = champ["season"]
        self.f = {k: d["teams"][k] for k in ("faction1", "faction2")}
        self.team = {k: v["faction_id"] for k, v in self.f.items()}
        self.name = {k: v["name"] for k, v in self.f.items()}
        self.bye = any(is_bye(v) for v in self.f.values())
        self.finished = d["status"] == "FINISHED"
        self.winner_faction = d["results"]["winner"]
        self.score = {k: d["results"]["score"][k] for k in ("faction1", "faction2")}
        self.has_maps = raw["stats"] is not None
        self.roster = {p["player_id"]: p for f in self.f.values() for p in f.get("roster", [])}
        self.rounds = []
        if raw["stats"]:
            names = {e["guid"]: e["name"] for e in d["voting"]["map"]["entities"]}
            for r in raw["stats"]["rounds"]:
                rs = r["round_stats"]
                teams = {}
                players = []
                for t in r["teams"]:
                    teams[t["team_id"]] = t["team_stats"].get("Team")
                    for p in t["players"]:
                        players.append({"player_id": p["player_id"], "team_id": t["team_id"], "stats": p["player_stats"],
                                        "nickname": p.get("nickname")})
                self.rounds.append({"map": names.get(rs["Map"], rs["Map"]), "mode": rs.get("OW2 Mode"),
                                    "winner": rs.get("Winner"), "teams": teams, "players": players})

    @property
    def counts_as_series(self):
        return self.finished and not self.bye


def all_series():
    return [Series(mid, raw) for mid, raw in load().items()]


# ------------------------------------------------------------- Liquipedia (Stage 2)

def load_liquipedia_matches() -> dict:
    """faceit_match_id -> the captured Liquipedia match2 record, straight from JSON. Empty if the fixture is absent."""
    path = GOLDEN / "liquipedia_matches.json"
    if not path.exists():
        return {}
    return {m["faceit_match_id"]: m["record"] for m in json.loads(path.read_text(encoding="utf-8"))["matches"]}


LIQUIPEDIA = load_liquipedia_matches()


def liquipedia_rounds(match_id: str, faceit_team_for_lp_team1: str, faceit_team_for_lp_team2: str) -> list[dict]:
    """A result_only match's maps, reconstructed from Liquipedia's own match2games only - never from owcsmuse's
    enrichment code, which is exactly what this is meant to check independently. The caller supplies which FACEIT
    team id is Liquipedia's team1/team2 (read off the captured FACEIT payload's own faction names), rather than
    this module re-deriving that orientation itself."""
    out = []
    for g in LIQUIPEDIA[match_id]["match2games"]:
        w = g.get("winner")
        winner = faceit_team_for_lp_team1 if w == "1" else faceit_team_for_lp_team2 if w == "2" else None
        out.append({"map": g.get("map"), "winner": winner})
    return out


def liquipedia_series(match_id: str, faceit_name_of_lp_team1: str) -> dict:
    """A linked series as Liquipedia records it, from the captured record alone: its series score and best-of, oriented
    to the FACEIT faction the caller names for Liquipedia's team1, the games actually played (a slot marked not played
    is no game; a drawn game is), and the scheduled time. Liquipedia is the source of record for a linked series'
    result (migration 034), so this is what the warehouse must present - FACEIT's stored score is never consulted."""
    from datetime import datetime, timezone
    r = LIQUIPEDIA[match_id]
    o = r["match2opponents"]
    played = [g for g in r["match2games"] if g.get("map") and not (g.get("status") == "notplayed" or g.get("resulttype") == "np")]
    return {"lp_team1": o[0]["name"], "lp_team2": o[1]["name"], "faceit_name_of_lp_team1": faceit_name_of_lp_team1,
            "score1": int(o[0]["score"]), "score2": int(o[1]["score"]), "best_of": int(r["bestof"]),
            "games": [{"map": g["map"], "winner": {"1": 1, "2": 2}.get(str(g.get("winner")))} for g in played],
            "played_at": datetime.fromtimestamp(int(r["extradata"]["timestamp"]), timezone.utc)}


def team_h2h_maps(series_list, team_ids, opponent_ids, liquipedia_overrides: Optional[dict] = None) -> dict[str, Any]:
    """Map-grain head-to-head between two identities: every map of every qualifying series, from FACEIT's own
    rounds when it has them, else from `liquipedia_overrides[match_id]` (see liquipedia_rounds) when given - never
    both for the same match, matching the "FACEIT wins for map stats" rule by construction."""
    liquipedia_overrides = liquipedia_overrides or {}
    ids, opp = set(team_ids), set(opponent_ids)
    matches: set = set()
    maps: list[dict] = []
    for s in series_list:
        if not s.counts_as_series:
            continue
        for k, o in (("faction1", "faction2"), ("faction2", "faction1")):
            if s.team[k] not in ids or s.team[o] not in opp:
                continue
            matches.add(s.match_id)
            if s.rounds:
                for r in s.rounds:
                    maps.append({"won": r["winner"] == s.team[k], "drawn": not r["winner"]})
            elif s.match_id in liquipedia_overrides:
                for r in liquipedia_overrides[s.match_id]:
                    maps.append({"won": r["winner"] == s.team[k], "drawn": r["winner"] is None})
    return {"matches": len(matches), "maps": len(maps), "map_wins": sum(x["won"] for x in maps),
            "map_losses": sum((not x["won"]) and (not x["drawn"]) for x in maps)}


def num(stats, key):
    v = stats.get(key)
    if v is None or v == "":
        return None
    return Decimal(str(v))


def owner_display_names():
    """player GUID -> display name the owner decided (scope/player_identity_decisions.json, `display`)."""
    path = GOLDEN.parent.parent / "scope" / "player_identity_decisions.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {d["entity_id"]: d["display"] for d in doc.get("decisions", {}).values() if d.get("entity_id") and d.get("display")}


def display_name(series_list, player_id):
    """The owner's display name when decided, else the in-game name (game_player_name) when the roster has one, else
    the FACEIT nickname - as the README states."""
    decided = owner_display_names().get(player_id)
    if decided:
        return decided
    for s in series_list:
        p = s.roster.get(player_id)
        if p:
            return p.get("game_player_name") or p["nickname"]
    # not declared on any roster (a substitute named only in the stats): the stats' own nickname
    for s in series_list:
        for r in s.rounds:
            for p in r["players"]:
                if p["player_id"] == player_id and p.get("nickname"):
                    return p["nickname"]
    raise KeyError(player_id)


def player_id_by_nickname(series_list, nickname):
    for s in series_list:
        for pid, p in s.roster.items():
            if p["nickname"] == nickname:
                return pid
    raise KeyError(nickname)


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------- players

def player_maps(series_list, player_id, season=None, role=None):
    """Every map (round) the player appeared in, with what they did and whether their team won."""
    out = []
    for s in series_list:
        if not s.counts_as_series or (season and s.season != season):
            continue
        for r in s.rounds:
            for p in r["players"]:
                if p["player_id"] != player_id:
                    continue
                if role and p["stats"].get("Role") != role:
                    continue
                opp = [t for t in r["teams"] if t != p["team_id"]]
                out.append({"match_id": s.match_id, "region": s.region, "season": s.season, "map": r["map"],
                            "won": r["winner"] == p["team_id"], "drawn": not r["winner"], "team_id": p["team_id"],
                            "opp_team_id": opp[0] if opp else None, "stats": p["stats"], "round": r})
    return out


def player_record(series_list, player_id, season=None):
    m = player_maps(series_list, player_id, season)
    elim = sum(num(x["stats"], "Eliminations") or 0 for x in m)
    deaths = sum(num(x["stats"], "Deaths") or 0 for x in m)
    return {"maps": len(m), "map_wins": sum(x["won"] for x in m),
            "map_losses": sum((not x["won"]) and (not x["drawn"]) for x in m),
            "eliminations": int(elim), "deaths": int(deaths), "kd_ratio": q2(elim / deaths) if deaths else None,
            "regions": sorted({x["region"] for x in m}), "matches": len({x["match_id"] for x in m})}


def player_avg(series_list, player_id, key, season=None):
    vals = [num(x["stats"], key) for x in player_maps(series_list, player_id, season)]
    vals = [v for v in vals if v is not None]
    return {"maps_with_stat": len(vals), "total": int(sum(vals)), "avg_per_map": q2(sum(vals) / len(vals))}


def leaderboard(series_list, key, season=None, role=None, top=5):
    """Players ranked by the total of `key`, over the maps that carry it (and the role, when given)."""
    tot, maps = defaultdict(Decimal), defaultdict(int)
    for s in series_list:
        if not s.counts_as_series or (season and s.season != season):
            continue
        for r in s.rounds:
            for p in r["players"]:
                if role and p["stats"].get("Role") != role:
                    continue
                v = num(p["stats"], key)
                if v is not None:
                    tot[p["player_id"]] += v
                    maps[p["player_id"]] += 1
    ranked = sorted(tot, key=lambda k: (-tot[k], k))
    return [{"player_id": k, "total": int(tot[k]), "maps_with_stat": maps[k]} for k in ranked[:top]], len(tot)


def stat_seasons(series_list, key):
    """Seasons in which any player-map carries the stat."""
    return sorted({s.season for s in series_list if s.counts_as_series
                   for r in s.rounds for p in r["players"] if num(p["stats"], key) is not None})


# ----------------------------------------------------------------------- teams

def team_record(series_list, team_ids, season=None, opponent_ids=None, exclude_names=(), liquipedia_overrides=None):
    """Series record for one identity (one or more team ids: an org), at series grain.

    `exclude_names` drops series in which the identity's faction carried one of those names in the payload: the
    way to say "not the Ex Oblivione era of this team id" without any date logic to get wrong.

    `liquipedia_overrides` (see liquipedia_rounds): a result_only series (`not s.has_maps`) still counts as
    result_only here - FACEIT truly has no stats for it - but Stage 2 gives `maps` a per-map count for it anyway,
    from Liquipedia's own game-by-game results, since that is what the actual system's `matches.maps_played` now
    reflects too.
    """
    liquipedia_overrides = liquipedia_overrides or {}
    ids = set(team_ids)
    opp = set(opponent_ids) if opponent_ids else None
    rows = []
    for s in series_list:
        if not s.counts_as_series or (season and s.season != season):
            continue
        for k, o in (("faction1", "faction2"), ("faction2", "faction1")):
            if s.team[k] in ids and s.name[k] not in exclude_names and (opp is None or s.team[o] in opp):
                rows.append((s, k, o))

    def n_maps(s):
        if s.rounds:
            return len(s.rounds)
        return len(liquipedia_overrides.get(s.match_id, ()))

    return {"matches": len(rows), "wins": sum(s.winner_faction == k for s, k, _ in rows),
            "losses": sum(s.winner_faction == o for s, _, o in rows),
            "map_wins": sum(s.score[k] for s, k, _ in rows), "map_losses": sum(s.score[o] for s, _, o in rows),
            "maps": sum(n_maps(s) for s, _, _ in rows),
            "result_only_series": sum(not s.has_maps for s, _, _ in rows),
            "regions": sorted({s.region for s, _, _ in rows}), "match_ids": [s.match_id for s, _, _ in rows]}


# ---------------------------------------------------------------------- versus

def versus_maps(series_list, player_id, opponent_player_id=None, opponent_team_ids=None):
    """Maps the player played where the other side had the given player / any of the given team ids."""
    out = []
    for x in player_maps(series_list, player_id):
        on = {p["player_id"]: p["team_id"] for p in x["round"]["players"]}
        if opponent_player_id is not None:
            if opponent_player_id in on and on[opponent_player_id] != x["team_id"]:
                out.append(x)
        elif opponent_team_ids and x["opp_team_id"] in opponent_team_ids:
            out.append(x)
    return {"maps": len(out), "map_wins": sum(x["won"] for x in out),
            "map_losses": sum((not x["won"]) and (not x["drawn"]) for x in out),
            "matches": len({x["match_id"] for x in out})}
