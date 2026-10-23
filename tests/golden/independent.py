"""Ground truth for the golden suite, computed from the raw FACEIT payloads and nothing else.

This module imports nothing from owcsmuse - no parser, no warehouse, no query
layer - so it cannot inherit a bug from them. It reads the captured JSON in
tests/golden/payloads and counts. When an answer disagrees with it, one of the
two is wrong, and the raw payload is the tie-break.

Definitions (docs/testing.md's, restated so they can be checked against it):
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
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

GOLDEN = Path(__file__).parent
# the manifest, championships and Liquipedia records being derived from: the main warehouse, or tests/golden/pairs
# (one pairing's every series) via use_fixtures(). Payloads are always GOLDEN / "payloads".
FIXTURES = GOLDEN


def use_fixtures(path: Path) -> None:
    global FIXTURES, LIQUIPEDIA
    FIXTURES = Path(path)
    LIQUIPEDIA = load_liquipedia_matches()


def load():
    manifest = json.loads((FIXTURES / "matches.json").read_text(encoding="utf-8"))
    return {m["match_id"]: json.loads((GOLDEN / "payloads" / f"{m['match_id']}.json").read_text(encoding="utf-8"))
            for m in manifest["matches"]}


def championships():
    return {c["championship_id"]: c for c in json.loads((FIXTURES / "championships.json").read_text(encoding="utf-8"))["championships"]}


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
    path = FIXTURES / "liquipedia_matches.json"
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
    the FACEIT nickname - as docs/liquipedia.md states."""
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


# ------------------------------------------------------------------- Stage 4: Liquipedia-only events
# Read straight from tests/golden/liquipedia_events.json (records copied verbatim from raw_payloads). A placing is a
# prize-pool row with a team and a position; an award (an MVP, a team award with no position) is not one.

def load_events() -> dict:
    return json.loads((GOLDEN / "liquipedia_events.json").read_text(encoding="utf-8"))


def _place_range(text: str):
    parts = [int(x) for x in str(text or "").replace(" ", "").split("-") if x.isdigit()]
    return (parts[0], parts[-1]) if parts else None


def placed(page: str, position: int) -> list[str]:
    """Liquipedia's names of every team whose placing at `page` covers `position` (7 finds a team placed 7-8)."""
    out = []
    for p in load_events()["placements"]:
        rng = _place_range(p.get("placement"))
        if p["pagename"] == page and p.get("opponenttype") == "team" and rng and rng[0] <= position <= rng[1]:
            out.append(p["opponentname"])
    return sorted(out)


def placing_text(page: str, team: str) -> str:
    return next(p["placement"] for p in load_events()["placements"]
                if p["pagename"] == page and p.get("opponenttype") == "team" and p["opponentname"] == team)


def event_series(page: str, team_a: str, team_b: str) -> list[dict]:
    """Every finished series between two teams on one event page: (date, score for a, score for b), from the records."""
    out = []
    for m in load_events()["matches"]:
        names = [o["name"] for o in m["match2opponents"]]
        if m["pagename"] != page or sorted(names) != sorted([team_a, team_b]) or not m.get("finished"):
            continue
        sa, sb = (m["match2opponents"][0]["score"], m["match2opponents"][1]["score"])
        if names[0] != team_a:
            sa, sb = sb, sa
        out.append({"date": m["date"], "a": int(sa), "b": int(sb), "maps": len(m.get("match2games") or [])})
    return sorted(out, key=lambda x: x["date"])


def last_series_winner(page: str) -> str:
    m = max((m for m in load_events()["matches"] if m["pagename"] == page and m.get("finished")),
            key=lambda m: (m["date"], m["objectname"]))
    return m["match2opponents"][int(m["winner"]) - 1]["name"]


def team_series_record(page: str, team: str) -> dict:
    """A team's series won-lost on one event page, counting each record once."""
    w = l = 0
    for m in load_events()["matches"]:
        names = [o["name"] for o in m["match2opponents"]]
        if m["pagename"] != page or team not in names or not m.get("finished"):
            continue
        won = names[int(m["winner"]) - 1] == team
        w, l = w + won, l + (not won)
    return {"matches": w + l, "wins": w, "losses": l}


def page_region(page: str) -> str:
    """A Liquipedia-only event page's region, by its path: a regional stage is that region, anything else international."""
    parts = page.split("/")
    return "na" if "North_America" in parts else "emea" if "EMEA" in parts else "international"


def event_record(lp_names, season=None) -> dict:
    """A team's series record at the captured Liquipedia-only events, by the names Liquipedia gives it there.

    Same definitions as team_record: map_wins / map_losses are series scores, and 'maps' counts the maps the record
    lists as played - Stage 2's rule for a result_only series (team_record's `liquipedia_overrides`), where Liquipedia's
    game-by-game results are the maps. A slot marked not played is not a map. Each record is one series.
    """
    names = set(lp_names)
    out = {"matches": 0, "wins": 0, "losses": 0, "map_wins": 0, "map_losses": 0, "maps": 0, "result_only_series": 0,
           "regions": set()}
    for m in load_events()["matches"]:
        if not m.get("finished") or (season and int(m["date"][:4]) != season):
            continue
        opp = m["match2opponents"]
        for i, j in ((0, 1), (1, 0)):
            if opp[i]["name"] in names:
                out["matches"] += 1
                out["wins"] += int(m["winner"]) == i + 1
                out["losses"] += int(m["winner"]) == j + 1
                out["map_wins"] += int(opp[i]["score"])
                out["map_losses"] += int(opp[j]["score"])
                out["maps"] += sum(1 for g in m.get("match2games") or []
                                   if g.get("status") != "notplayed" and g.get("resulttype") != "np")
                out["result_only_series"] += 1
                out["regions"].add(page_region(m["pagename"]))
    out["regions"] = sorted(out["regions"])
    return out


def plus(a: dict, b: dict) -> dict:
    """Two records of one identity, from disjoint series (FACEIT payloads and Liquipedia-only events)."""
    out = {k: a[k] + b[k] for k in ("matches", "wins", "losses", "map_wins", "map_losses", "maps", "result_only_series")}
    out["regions"] = sorted(set(a.get("regions", [])) | set(b.get("regions", [])))
    return out


def event_maps(team_a: str, team_b: str, page: Optional[str] = None) -> dict:
    """team_a's map record against team_b at the captured Liquipedia-only events: each played game once (a slot
    marked not played is no game), won by the side Liquipedia's game `winner` names, a 0 winner a draw."""
    out = {"maps": 0, "map_wins": 0, "map_losses": 0, "draws": 0, "series": 0}
    for m in load_events()["matches"]:
        names = [o["name"] for o in m["match2opponents"]]
        if sorted(names) != sorted([team_a, team_b]) or not m.get("finished") or (page and m["pagename"] != page):
            continue
        me = names.index(team_a) + 1
        out["series"] += 1
        for g in m.get("match2games") or []:
            if g.get("status") == "notplayed" or g.get("resulttype") == "np":
                continue
            out["maps"] += 1
            w = int(g.get("winner") or 0)
            out["map_wins"] += w == me
            out["map_losses"] += w not in (0, me)
            out["draws"] += w == 0
    return out


# ------------------------------------------------------------------- who was on which side of a series
# A player is on a side by being on its declared line-up (the detail payload's `roster`; `substitutes` is the bench).
# A team or org is on a side by its team id. Players do not win series, their teams do: a player's series record
# against someone is the series they were on opposite sides of, scored from his side.

def _on(s, side, who):
    kind, ids = who
    if kind == "player":
        return any(p["player_id"] in ids for p in s.f[side].get("roster", []))
    return s.team[side] in ids


def opposed_series(series_list, a, b, season=None):
    """[(series, a's faction, b's faction)] for every counted series with `a` on one side and `b` on the other.
    `a` / `b` are ("player", {player_id}) or ("team", {team ids of one identity})."""
    out = []
    for s in series_list:
        if not s.counts_as_series or (season and s.season != season):
            continue
        for k, o in (("faction1", "faction2"), ("faction2", "faction1")):
            if _on(s, k, a) and _on(s, o, b):
                out.append((s, k, o))
                break
    return out


def opposed_record(series_list, a, b, season=None) -> dict:
    rows = opposed_series(series_list, a, b, season)
    return {"matches": len(rows), "wins": sum(s.winner_faction == k for s, k, _ in rows),
            "losses": sum(s.winner_faction == o for s, _, o in rows), "match_ids": [s.match_id for s, _, _ in rows]}


def same_side_series(series_list, a, b, season=None) -> int:
    """Series in which `a` and `b` were on the same side: a player and his own team, or two teammates."""
    return sum(1 for s in series_list if s.counts_as_series and (not season or s.season == season)
               and any(_on(s, k, a) and _on(s, k, b) for k in ("faction1", "faction2")))


def event_rows(lp_name: str) -> list[dict]:
    """Every finished series a team played at the captured Liquipedia-only events, by the name Liquipedia gives it,
    scored from the record alone: the same series event_record counts, one row each."""
    out = []
    for m in load_events()["matches"]:
        opp = m["match2opponents"]
        names = [o["name"] for o in opp]
        if lp_name not in names or not m.get("finished"):
            continue
        i = names.index(lp_name)
        out.append({"objectname": m["objectname"], "page": m["pagename"], "for": int(opp[i]["score"]),
                    "against": int(opp[1 - i]["score"]), "won": int(m["winner"]) == i + 1})
    return out


# A Liquipedia-only series has no FACEIT roster: a player is on its side by Liquipedia's line-up (match2players), read
# through the owner's reviewed page -> FACEIT player decisions (scope/player_identity_decisions.json). A page with no
# decision is on no side: unknown, never guessed. Liquipedia does not say who played which map, so the line-up is on
# every map of its side (docs/answers.md's every-played-map rule for a map without player rows).

def lp_player_ids() -> dict[str, str]:
    """Liquipedia player page -> FACEIT player id, from the owner's decisions (a Liquipedia-born player has none)."""
    path = GOLDEN.parent.parent / "scope" / "player_identity_decisions.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {page: d["entity_id"] for page, d in doc["decisions"].items() if d.get("entity_id")}


def _event_lineups(m) -> list[set]:
    ids = lp_player_ids()
    return [{ids[p["name"]] for p in o.get("match2players") or [] if p.get("name") in ids} for o in m["match2opponents"]]


def event_opposed(a_player: str, b_player: str) -> list[tuple[dict, int]]:
    """[(record, a's side index)] for every finished Liquipedia-only event series with the two players on opposite
    line-ups."""
    out = []
    for m in load_events()["matches"]:
        if not m.get("finished"):
            continue
        sides = _event_lineups(m)
        for i in (0, 1):
            if a_player in sides[i] and b_player in sides[1 - i]:
                out.append((m, i))
                break
    return out


def event_opposed_record(a_player: str, b_player: str) -> dict:
    """A player's series record against a player over the Liquipedia-only event series, from a's team's side."""
    rows = event_opposed(a_player, b_player)
    return {"matches": len(rows), "wins": sum(int(m["winner"]) == i + 1 for m, i in rows),
            "losses": sum(int(m["winner"]) == 2 - i for m, i in rows), "match_ids": [m["objectname"] for m, _ in rows]}


def event_opposed_maps(a_player: str, b_player: str) -> dict:
    """Every played game of those series (a slot marked not played is no game), from a's side; a 0 winner a draw."""
    out = {"maps": 0, "map_wins": 0, "map_losses": 0, "matches": 0}
    for m, i in event_opposed(a_player, b_player):
        out["matches"] += 1
        for g in m.get("match2games") or []:
            if not g.get("map") or g.get("status") == "notplayed" or g.get("resulttype") == "np":
                continue
            w = int(g.get("winner") or 0)
            out["maps"] += 1
            out["map_wins"] += w == i + 1
            out["map_losses"] += w not in (0, i + 1)
    return out


def team_maps_against_player(series_list, team_ids, player_id, season=None) -> dict:
    """A team's map record in the maps a given opposing player played (his round rows), from the team's side."""
    out = {"maps": 0, "map_wins": 0, "map_losses": 0}
    for s in series_list:
        if not s.counts_as_series or (season and s.season != season):
            continue
        for r in s.rounds:
            mine = [p for p in r["players"] if p["player_id"] == player_id]
            if not mine or mine[0]["team_id"] in team_ids or not any(t in team_ids for t in r["teams"]):
                continue
            out["maps"] += 1
            out["map_wins"] += r["winner"] in team_ids
            out["map_losses"] += r["winner"] == mine[0]["team_id"]
    return out



# ------------------------------------------------------------------- partner teams (043)
# From tests/golden/partner_placements.json: Liquipedia's Stage 1 prize-pool rows whose qualifier is "Partner Team",
# copied verbatim. A season's partners are the rows dated in it.

def partner_names(season: int) -> list[str]:
    rows = json.loads((GOLDEN / "partner_placements.json").read_text(encoding="utf-8"))["placements"]
    return sorted(r["opponentname"] for r in rows if int(r["date"][:4]) == season)


def partner_seasons() -> list[int]:
    rows = json.loads((GOLDEN / "partner_placements.json").read_text(encoding="utf-8"))["placements"]
    return sorted({int(r["date"][:4]) for r in rows})


# ------------------------------------------------------------------- every played map (045)
# A record against someone counts every map of every series the two were on opposite sides of: a map FACEIT has player
# rows for when both played it; a map FACEIT's /stats dropped when Liquipedia's game at that position is the same map;
# a results-only series' maps from Liquipedia's own games. Read from the payloads and the captured Liquipedia records
# alone - the orientation of Liquipedia's sides to FACEIT's is decided here by name, not by owcsmuse.

def _fold(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s.lower() if c.isalnum())


def _lp_side_of(s, lp_record) -> dict:
    """{FACEIT faction: Liquipedia side number}, by folded name (one may extend the other: 'SpaceStation' v
    'Spacestation Gaming'). Asserts exactly one orientation fits."""
    lp = [_fold(o["name"]) for o in lp_record["match2opponents"]]
    fc = {k: _fold(s.name[k]) for k in ("faction1", "faction2")}

    def fits(a, b):
        return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))
    straight = fits(fc["faction1"], lp[0]) and fits(fc["faction2"], lp[1])
    crossed = fits(fc["faction1"], lp[1]) and fits(fc["faction2"], lp[0])
    assert straight != crossed, (s.match_id, s.name, [o["name"] for o in lp_record["match2opponents"]])
    return {"faction1": 1, "faction2": 2} if straight else {"faction1": 2, "faction2": 1}


def _lp_games(lp_record):
    return [g for g in lp_record["match2games"]
            if g.get("map") and not (g.get("status") == "notplayed" or g.get("resulttype") == "np")]


def _on_map(s, side, who, round_players) -> bool:
    """`who` on `side` of one map: by the map's player rows when it has them, else by the series' declared line-up."""
    kind, ids = who
    if kind == "team":
        return s.team[side] in ids
    if round_players is not None:
        return any(p["player_id"] in ids and p["team_id"] == s.team[side] for p in round_players)
    return _on(s, side, who)


def opposed_maps(series_list, a, b, season=None) -> dict:
    """Every played map of every series `a` and `b` were on opposite sides of, from `a`'s side."""
    maps = []
    for s, k, o in opposed_series(series_list, a, b, season):
        lp = LIQUIPEDIA.get(s.match_id)
        side = _lp_side_of(s, lp) if lp else None
        stats_rounds = {}
        if s.rounds:
            raw_rounds = json.loads((GOLDEN / "payloads" / f"{s.match_id}.json").read_text(encoding="utf-8"))["stats"]["rounds"]
            stats_rounds = {int(rr["match_round"]): r for rr, r in zip(raw_rounds, s.rounds, strict=True)}
            for n, r in stats_rounds.items():
                if _on_map(s, k, a, r["players"]) and _on_map(s, o, b, r["players"]):
                    maps.append({"match_id": s.match_id, "n": n, "won": r["winner"] == s.team[k], "drawn": not r["winner"],
                                 "from": "faceit stats"})
            games = _lp_games(lp) if lp else []
            picks = s.detail["voting"]["map"]["pick"]
            names = {e["guid"]: e["name"] for e in s.detail["voting"]["map"]["entities"]}
            for n, e in enumerate(s.detail.get("detailed_results") or [], start=1):
                if n in stats_rounds or e.get("winner") not in ("faction1", "faction2"):
                    continue
                g = games[n - 1] if n <= len(games) else None
                if g is None or _fold(g["map"]) != _fold(names.get(picks[n - 1]) if n <= len(picks) else ""):
                    continue      # not a game on Liquipedia's record of this series
                assert str(g.get("winner")) == str(side[e["winner"]]), (s.match_id, n)
                if _on_map(s, k, a, None) and _on_map(s, o, b, None):
                    maps.append({"match_id": s.match_id, "n": n, "won": e["winner"] == k, "drawn": False,
                                 "from": "faceit detailed_results, on Liquipedia"})
        elif lp:
            for n, g in enumerate(_lp_games(lp), start=1):
                w = str(g.get("winner"))
                won = w == str(side[k])
                maps.append({"match_id": s.match_id, "n": n, "won": won, "drawn": w not in ("1", "2"),
                             "from": "liquipedia"})
    return {"maps": len(maps), "map_wins": sum(x["won"] for x in maps),
            "map_losses": sum((not x["won"]) and (not x["drawn"]) for x in maps),
            "matches": len({x["match_id"] for x in maps}), "by_source": dict(Counter(x["from"] for x in maps)),
            "detail": maps}
