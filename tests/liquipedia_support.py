"""Test doubles for the Liquipedia layer: an in-memory Store and a mock transport that records every request."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from owcsmuse.liquipedia import LiquipediaClient


class MemoryStore:
    """Same contract as PgStore, in a list. Cache hits leave no row, exactly as with the real one."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.coverage: dict[tuple[str, str, str], dict[str, Any]] = {}

    def cached(self, endpoint, params):
        for r in reversed(self.rows):
            p = r["payload"]
            if (r["endpoint"] == endpoint and r["params"] == params and r["status"] == 200 and p is not None
                    and not (isinstance(p, dict) and p.get("error"))):
                return {"id": r["id"], "payload": p, "headers": r["headers"], "fetched_at": r["fetched_at"]}
        return None

    def save(self, endpoint, params, status, payload, body_text, headers, fetched_at):
        rid = len(self.rows) + 1
        self.rows.append({"id": rid, "endpoint": endpoint, "params": dict(params), "status": status, "payload": payload,
                          "body_text": body_text, "headers": dict(headers), "fetched_at": fetched_at})
        return rid

    def used_in_window(self, now, window):
        inside = [r["fetched_at"] for r in self.rows if r["fetched_at"] > now - window]
        return len(inside), (min(inside) if inside else None)

    def last_rate_limit(self):
        hits = [r for r in self.rows if r["status"] == 429]
        if not hits:
            return None
        r = hits[-1]
        try:
            ra = float(r["headers"].get("retry-after"))
        except (TypeError, ValueError):
            ra = None
        return r["fetched_at"], ra

    def covered(self, endpoint, field, values):
        return {v: self.coverage[(endpoint, field, v)] for v in values if (endpoint, field, v) in self.coverage}

    def unfinished(self, endpoint, field, values):
        out = set()
        for v in values:
            cov = self.coverage.get((endpoint, field, v))
            for r in self.rows:
                if cov and r["id"] in cov["raw_ids"] and isinstance(r["payload"], dict):
                    if any(str(x.get(field, "")).replace(" ", "_") == v and "finished" in x
                           and str(x["finished"]) not in ("1", "true") for x in r["payload"].get("result") or []):
                        out.add(v)
        return out

    def mark_covered(self, endpoint, field, entries, raw_ids):
        for e in entries:
            self.coverage[(endpoint, field, e["value"])] = {"value": e["value"], "rows_seen": e.get("rows_seen"),
                                                            "raw_ids": list(raw_ids)}


class Clock:
    def __init__(self, start: Optional[datetime] = None) -> None:
        self.now = start or datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        self.slept: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: Any) -> None:
        self.now += timedelta(**kw)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


class Wire:
    """A mock Liquipedia. `respond(request) -> httpx.Response`; every request that reaches it is recorded."""

    def __init__(self, respond: Optional[Callable[[httpx.Request], httpx.Response]] = None) -> None:
        self.requests: list[httpx.Request] = []
        self.respond = respond or (lambda req: httpx.Response(200, json={"result": []}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def rows_response(n: int, **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"result": [{"match2id": f"m{i}", **extra} for i in range(n)]},
                          headers={"x-ratelimit-remaining": "50"})


def make_client(wire: Wire, store: Optional[MemoryStore] = None, clock: Optional[Clock] = None, *,
                key: Optional[str] = "SECRET-KEY-123", budget: int = 60, min_interval: float = 0.0):
    store = store if store is not None else MemoryStore()
    clock = clock or Clock()
    client = LiquipediaClient(key, store, hourly_budget=budget, min_interval=min_interval, http=wire.client(),
                              clock=clock, sleep=clock.sleep)
    return client, store, clock


def query_of(req: httpx.Request) -> dict[str, str]:
    return dict(req.url.params)


def body_of(x: Any) -> str:
    return json.dumps(x, default=str)


# ---------------------------------------------------------------------- reconciliation builders

from owcsmuse.liquipedia.matches import parse_row  # noqa: E402
from owcsmuse.liquipedia.model import FaceitSide  # noqa: E402
from owcsmuse.resolve import fold  # noqa: E402

T0 = datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc)
NA_PAGE = "Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season"
EMEA_PAGE = "Overwatch_Champions_Series/2026/EMEA/Stage_2/Regular_Season"


def lp_row(team1, team2, s1, s2, when=T0, *, page=NA_PAGE, faceit_id=None, bo=5, idx=1, bracket="B1", finished=True,
           status="S", winner=None, n_games=None, opp_type="team", games=None, players1=None, players2=None,
           templates=None):
    """A Liquipedia match record in the shape the API returns (only the fields the parser reads).

    `games`, when given, replaces the auto-generated match2games list outright: a list of
    {"map", "mode", "winner", "scores"} dicts, exactly the sub-keys parse_row reads.
    """
    w = winner if winner is not None else (1 if (s1 or 0) > (s2 or 0) else 2 if (s2 or 0) > (s1 or 0) else 0)
    n = n_games if n_games is not None else (s1 or 0) + (s2 or 0)
    return {"objectname": f"1_{bracket}_{idx:04d}", "match2id": f"{bracket}_{idx:04d}", "match2bracketid": bracket,
            "pagename": page, "parent": page.rsplit("/", 1)[0], "date": when.strftime("%Y-%m-%d %H:%M:%S"),
            "extradata": {"timestamp": int(when.timestamp())}, "bestof": bo, "finished": 1 if finished else 0,
            "winner": str(w), "walkover": "", "section": "Week 1",
            "links": {"faceit": f"https://www.faceit.com/en/ow2/room/{faceit_id}"} if faceit_id else [],
            "match2opponents": [{"name": team1, "score": s1, "status": status, "type": opp_type,
                                 "match2players": [{"name": n, "displayname": d, "flag": f} for n, d, f in (players1 or [])],
                                 **({"teamtemplate": {"template": templates[0], "page": team1}} if templates else {})},
                                {"name": team2, "score": s2, "status": status, "type": opp_type,
                                 "match2players": [{"name": n, "displayname": d, "flag": f} for n, d, f in (players2 or [])],
                                 **({"teamtemplate": {"template": templates[1], "page": team2}} if templates else {})}],
            "match2games": games if games is not None else
                          [{"map": f"Map{i}", "mode": "Control", "winner": "1", "scores": [1, 0]} for i in range(n)]}


def lp(team1, team2, s1, s2, when=T0, raw_id=1, **kw):
    return parse_row(lp_row(team1, team2, s1, s2, when, **kw), raw_id)


def fs(match_id, name1, name2, s1, s2, when=T0 + timedelta(minutes=45), *, org1=None, org2=None, region="na", bo=5,
       comp="c-na", state="complete", maps=None, reliable=True, winner=None):
    """A FACEIT series. org keys default to a slug of the name, so 'SpaceStation Gaming' is 'spacestation-gaming'."""
    slug = lambda n: fold(n).replace(" ", "-")  # noqa: E731
    w = winner if winner is not None else (1 if s1 > s2 else 2 if s2 > s1 else 0)
    return FaceitSide(match_id, comp, comp, region, 2026, when, bo, org1 or slug(name1), org2 or slug(name2), name1, name2,
                      s1, s2, w, state, (s1 + s2 if state == "complete" else 0) if maps is None else maps, reliable)


def resolver(mapping):
    """{(lp name, region|None): org key} or {lp name: org key}; source 'decided' unless the value is ('key', 'proposed')."""
    def resolve(name, region=None, at=None):
        for k in ((fold(name), region), (fold(name), None)):
            hit = mapping.get(k) or mapping.get(name)
            if hit:
                return hit if isinstance(hit, tuple) else (hit, "decided")
        return None
    return resolve


# ---------------------------------------------------------------------- DB round-trip scratch schema

import json as _json  # noqa: E402
from owcsmuse.db import RawPayloadStore, connect, migrate  # noqa: E402

MIGRATIONS = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "migrations")

DB_CHAMPIONSHIP = "lp-test-champ"
DB_TEAM1, DB_TEAM2 = "team-dallas", "team-liquid"
DB_FACEIT_ID = "1-11111111-1111-1111-1111-111111111111"
DB_PAGE = "Overwatch_Champions_Series/2026/NA/Stage_2/Regular_Season"


def build_liquipedia_scratch_db(db_url: str, schema: str, *, rosters=None, lp_players=None):
    """Drop + recreate `schema`, migrate, and seed one FACEIT match plus one matching stored Liquipedia response.

    Minimal by hand (no Collector/FakeClient): reconciliation only reads matches, match_rounds, team_identity and
    championships, so those are inserted directly rather than replayed through ingest.
    """
    assert schema != "public"
    admin = connect(db_url, autocommit=True, schema=schema)
    admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    admin.close()
    conn = connect(db_url, schema=schema)
    raw_conn = connect(db_url, autocommit=True, schema=schema)
    migrate(conn, MIGRATIONS, schema)
    when = T0 + timedelta(minutes=45)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizers (organizer_id, name) VALUES ('org-lp', 'OWCS')")
        cur.execute(
            """INSERT INTO championships (championship_id, organizer_id, name, include, scope_region, tier, season, classification_source)
               VALUES (%s, 'org-lp', 'OWCS 2026 NA Stage 2', true, 'na', 'main', 2026, 'manual')""",
            (DB_CHAMPIONSHIP,))
        cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, 'Dallas Fuel'), (%s, 'Team Liquid')",
                    (DB_TEAM1, DB_TEAM2))
        cur.execute(
            """INSERT INTO matches (match_id, championship_id, best_of, status, started_at, faction1_team_id,
                                     faction2_team_id, faction1_name, faction2_name, faction1_score, faction2_score,
                                     winner_faction, ingest_state)
               VALUES (%s, %s, 5, 'FINISHED', %s, %s, %s, 'Dallas Fuel', 'Team Liquid', 3, 1, 'faction1', 'complete')""",
            (DB_FACEIT_ID, DB_CHAMPIONSHIP, when, DB_TEAM1, DB_TEAM2))
        for i in range(4):
            cur.execute(
                """INSERT INTO match_rounds (match_id, round_number, map_name, team1_team_id, team1_score,
                                              team2_team_id, team2_score, winner_team_id)
                   VALUES (%s, %s, %s, %s, 1, %s, 0, %s)""",
                (DB_FACEIT_ID, i + 1, f"Map{i}", DB_TEAM1, DB_TEAM2, DB_TEAM1))
        # rosters: {team_id: [(player_id, nickname, game_name)]}, declared on the FACEIT side of the one match
        for team_id, players in (rosters or {}).items():
            for pid, nick, game in players:
                cur.execute("INSERT INTO players (player_id, nickname, game_player_name) VALUES (%s, %s, %s) "
                            "ON CONFLICT (player_id) DO NOTHING", (pid, nick, game))
                cur.execute("INSERT INTO match_rosters (match_id, player_id, faction, team_id, nickname_at_match, game_player_name) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (DB_FACEIT_ID, pid, "faction1" if team_id == DB_TEAM1 else "faction2", team_id, nick, game))
    conn.commit()
    sink = RawPayloadStore(raw_conn)
    p1, p2 = (lp_players or (None, None))
    row = lp_row("Dallas Fuel", "Team Liquid", 3, 1, when=T0, page=DB_PAGE, faceit_id=DB_FACEIT_ID,
                 players1=p1, players2=p2, templates=("dallas fuel 2026", "team liquid 2026") if lp_players else None)
    raw_id = sink.store(endpoint="match", params={}, http_status=200, payload={"result": [row]}, body_text=None,
                        fetched_at=when, source="liquipedia")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
               VALUES ('match', 'pagename', %s, %s, 1, %s)""",
            (DB_PAGE, f"https://liquipedia.net/overwatch/{DB_PAGE}", [raw_id]))
    conn.commit()
    return conn, raw_conn


def write_map_file(path, championship_id: str = DB_CHAMPIONSHIP, page: str = DB_PAGE, name: str = "OWCS 2026 NA Stage 2"):
    path.write_text(_json.dumps({"pages": {championship_id: {"page": page, "name": name}}}), encoding="utf-8")
    return path


DB_FACEIT_ID_RO = "1-22222222-2222-2222-2222-222222222222"
GAMES_RO = [
    {"map": "Lijiang Tower", "mode": "Control", "winner": "1", "scores": [2, 1]},
    {"map": "Colosseo", "mode": "Push", "winner": "2", "scores": [64.2, 88.9]},   # FACEIT scores push as a 1/0 indicator
    {"map": "Dorado", "mode": "Escort", "winner": "1", "scores": [3, 1]},
]


def build_result_only_scratch_db(db_url: str, schema: str):
    """Like build_liquipedia_scratch_db, but the FACEIT match is `result_only` with zero match_rounds: exactly
    what owcsmuse.liquipedia.enrich is for. Liquipedia's games include a Push map, to exercise the score
    normalisation (FACEIT's own round_stats never carries the push distance, only a 1/0 win indicator)."""
    assert schema != "public"
    admin = connect(db_url, autocommit=True, schema=schema)
    admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    admin.close()
    conn = connect(db_url, schema=schema)
    raw_conn = connect(db_url, autocommit=True, schema=schema)
    migrate(conn, MIGRATIONS, schema)
    when = T0 + timedelta(minutes=45)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizers (organizer_id, name) VALUES ('org-lp2', 'OWCS')")
        cur.execute(
            """INSERT INTO championships (championship_id, organizer_id, name, include, scope_region, tier, season, classification_source)
               VALUES (%s, 'org-lp2', 'OWCS 2026 NA Stage 2', true, 'na', 'main', 2026, 'manual')""",
            (DB_CHAMPIONSHIP,))
        cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, 'Dallas Fuel'), (%s, 'Team Liquid')",
                    (DB_TEAM1, DB_TEAM2))
        cur.execute(
            """INSERT INTO matches (match_id, championship_id, best_of, status, configured_at, faction1_team_id,
                                     faction2_team_id, faction1_name, faction2_name, faction1_score, faction2_score,
                                     winner_faction, ingest_state)
               VALUES (%s, %s, 5, 'FINISHED', %s, %s, %s, 'Dallas Fuel', 'Team Liquid', 2, 1, 'faction1', 'result_only')""",
            (DB_FACEIT_ID_RO, DB_CHAMPIONSHIP, when + timedelta(hours=90), DB_TEAM1, DB_TEAM2))
    conn.commit()
    sink = RawPayloadStore(raw_conn)
    row = lp_row("Dallas Fuel", "Team Liquid", 2, 1, when=T0, page=DB_PAGE, faceit_id=DB_FACEIT_ID_RO, bo=5,
                games=GAMES_RO)
    raw_id = sink.store(endpoint="match", params={}, http_status=200, payload={"result": [row]}, body_text=None,
                        fetched_at=when, source="liquipedia")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
               VALUES ('match', 'pagename', %s, %s, 1, %s)""",
            (DB_PAGE, f"https://liquipedia.net/overwatch/{DB_PAGE}", [raw_id]))
    conn.commit()
    return conn, raw_conn
