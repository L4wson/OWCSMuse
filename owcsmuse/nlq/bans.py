"""Hero-ban answers (049): which heroes were banned, by which teams, and which never were.

Bans come from Liquipedia only (owner, 2026-11-03): each map records one ban per team (team1ban1, team2ban1), so a ban
is per map and belongs to the team that made it. The grain is the map, as everywhere else: a hero is banned on a map
or it is not (Liquipedia never records both teams banning the same hero), so a hero's bans count maps, and its rate is
bans over the maps of the slice it was available on.

Availability is the hero list's (scope/heroes.json, `heroes`): a hero is available on a map played on or after its
`available_from` day. "Least banned" ranks the heroes available in the slice and banned at least once; "never banned"
is its own answer, the available heroes with no ban, because a hero never banned has zero and would otherwise lead every
"least" list (the "least deaths" problem). A hero not yet released is not "never banned": it was not available.

Bans were introduced in 2025. A ban question about a season before that says so (`hero_ban_settings`), rather than
returning an empty list that reads as "nobody banned anything".

Like compile.py and evidence.py, every value here is a bound parameter and every column name is fixed text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any, Optional

import psycopg

from .. import heroes as hero_list
from ..liquipedia.attribution import attribution_block
from .columns import describe
from .compile import Resolved
from .evidence import Evidence, clamp_page
from .schema import StructuredQuery, Unanswerable
from .sentence import Sentence, _Builder, num, pct
from .validate import SchemaInfo

AVAILABLE = "(h.available_from IS NULL OR (m.played_at AT TIME ZONE 'UTC')::date >= h.available_from)"
_REGION = {"na": "NA", "emea": "EMEA", "international": "international events", "korea": "Korea"}


@dataclass
class BanSlice:
    """A validated ban question: the hero, the competitions and the team, resolved."""
    query: StructuredQuery
    hero: Optional[str] = None                 # canonical
    championship_ids: list[str] = field(default_factory=list)
    championship_names: list[str] = field(default_factory=list)
    map_name: Optional[str] = None
    mode_name: Optional[str] = None
    team_key: Optional[str] = None             # the org key whose bans (or opponents' bans) count
    team_name: Optional[str] = None
    team_entity: Optional[dict] = None
    notes: list[str] = field(default_factory=list)


def introduced(conn: psycopg.Connection) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT min(bans_introduced_season) AS s FROM hero_ban_settings")
        row = cur.fetchone()
    conn.commit()
    return row["s"] if row else None


def _before_bans(season: int, intro: int, asked: str) -> Unanswerable:
    return Unanswerable(code="no_data",
                        reason=f"Hero bans were introduced in {intro}, so {asked} has none: no {season} map has a ban "
                               "to count.",
                        suggestions=[f"Ask about {intro} or later, e.g. `most banned hero in {intro}`."])


def validate_bans(conn: psycopg.Connection, q: StructuredQuery, r: Resolved, info: SchemaInfo,
                  entities: dict[str, dict]) -> BanSlice | Unanswerable:
    f = q.filters
    s = BanSlice(query=q)
    intro = introduced(conn)

    # --- the hero, against the reviewed list
    if f.hero:
        hl = hero_list.from_db(conn)
        canon = hl.by_key().get(hero_list.key(f.hero))
        if not canon:
            close = get_close_matches(f.hero, [h.name for h in hl.heroes], n=3, cutoff=0.6)
            return Unanswerable(code="unknown_entity", reason=f"no hero named '{f.hero}' in the hero list",
                                suggestions=[f"did you mean: {', '.join(close)}"] if close else
                                ["Heroes are named as Liquipedia names them, e.g. D.Va, Lúcio, Soldier: 76."])
        s.hero = canon
    if q.entity == "team" and not s.hero:
        return Unanswerable(code="invalid_query", reason="which hero? Every team bans once per map, so ranking teams "
                            "needs a hero, e.g. `which teams ban Tracer the most`")

    # --- the team: an org or team that bans; a player bans nothing
    if f.team:
        if r.player_id and not r.team_id:
            name = r.names.get("team") or f.team
            return Unanswerable(code="unsupported_question",
                                reason=f"{name} is a player; hero bans are made by teams",
                                suggestions=["Ask about the player's team, e.g. `which heroes does <team> ban most`."])
        s.team_key = r.org_key(r.team_id, r.subject_type)
        s.team_name = r.names.get("team")
        s.team_entity = entities.get("team")

    # --- the slice: what exists, as validate() checks it for every other answer
    if f.season is not None:
        if intro is not None and f.season < intro:
            return _before_bans(f.season, intro, str(f.season))
        if f.season not in info.seasons:
            have = ", ".join(str(x) for x in sorted(info.seasons)) or "none"
            return Unanswerable(code="no_data", reason=f"no data for the {f.season} season; seasons with data: {have}")
    if f.region is not None and info.regions and f.region not in info.regions:
        return Unanswerable(code="no_data", reason=f"no data for region '{f.region}'; regions with data: "
                                                   f"{', '.join(sorted(info.regions))}")
    if f.map:
        s.map_name = info.match_map(f.map)
        if not s.map_name:
            return Unanswerable(code="no_data", reason=f"no maps named '{f.map}' in the warehouse")
    if f.mode:
        s.mode_name = info.match_mode(f.mode)
        if not s.mode_name:
            return Unanswerable(code="no_data", reason=f"no game mode '{f.mode}' in the warehouse")
    if f.championship:
        matches = info.match_championships(f.championship, f.season, f.region)
        if not matches:
            return Unanswerable(code="no_data", reason=f"no tournament in scope matches '{f.championship}'")
        seasons = {info.championship_season.get(cid) for cid, _ in matches} - {None}
        if intro is not None and seasons and max(seasons) < intro:
            return _before_bans(max(seasons), intro, " and ".join(n for _, n in matches[:2]))
        s.championship_ids = [cid for cid, _ in matches]
        s.championship_names = [n for _, n in matches]
        if len(matches) > 1:
            s.notes.append(f"'{f.championship}' matched {len(matches)} tournaments; bans cover all of them: "
                           + "; ".join(n for _, n in matches)[:300])
    return s


# ------------------------------------------------------------------ SQL

def _slice(s: BanSlice, alias: str) -> tuple[list[str], list[Any]]:
    """The slice's filters on a row of hero_ban_maps or fact_hero_bans (`alias`)."""
    f = s.query.filters
    clauses, params = [], []
    for col, val in (("season", f.season), ("region", f.region), ("map_name", s.map_name), ("game_mode", s.mode_name)):
        if val is not None:
            clauses.append(f"{alias}.{col} = %s")
            params.append(val)
    if s.championship_ids:
        clauses.append(f"{alias}.championship_id = ANY(%s)")
        params.append(s.championship_ids)
    return clauses, params


def _maps_cte(s: BanSlice) -> tuple[str, list[Any]]:
    """`m`: the slice's maps with bans; with a team, the maps that team played (it banned on every one)."""
    clauses, params = _slice(s, "hm")
    if s.team_key:
        clauses.append("EXISTS (SELECT 1 FROM fact_hero_bans x WHERE x.series_id = hm.series_id "
                       "AND x.round_number = hm.round_number AND x.org_key = %s)")
        params.append(s.team_key)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return (f"m AS (SELECT hm.series_id, hm.round_number, hm.played_at, hm.season, hm.liquipedia_page_url "
            f"FROM hero_ban_maps hm{where})"), params


def _side(s: BanSlice) -> tuple[str, list[Any]]:
    """Whose bans count on the slice's maps: the team's own, its opponents', or everyone's."""
    if not s.team_key:
        return "", []
    col = "fb.opponent_org_key" if s.query.filters.ban_side == "against" else "fb.org_key"
    return f" AND {col} = %s", [s.team_key]


def hero_rows_sql(s: BanSlice) -> tuple[str, list[Any]]:
    """One row per hero available in the slice: its bans, the maps it was available on, its ban rate."""
    q = s.query
    maps, params = _maps_cte(s)
    side, side_params = _side(s)
    if q.metric == "never_banned":
        keep, order = "coalesce(n.bans, 0) = 0", "hero"
    else:
        # one named hero answers even at zero ("Tracer was never banned in ..."); a ranking holds the heroes banned at
        # least once, never-banned being its own question
        keep = "coalesce(a.hero, n.hero) = %s" if s.hero else "coalesce(n.bans, 0) >= 1"
        d = "ASC" if q.sort == "asc" else "DESC"
        order = f"bans {d}, ban_pct {d} NULLS LAST, hero"
    sql = (f"WITH {maps}, "
           f"b AS (SELECT fb.hero FROM fact_hero_bans fb JOIN m USING (series_id, round_number) WHERE true{side}), "
           "n AS (SELECT hero, count(*) AS bans FROM b GROUP BY hero), "
           f"a AS (SELECT h.hero, h.available_from, count(*) AS maps, array_agg(DISTINCT m.season ORDER BY m.season) AS seasons "
           f"      FROM heroes h JOIN m ON {AVAILABLE} GROUP BY h.hero, h.available_from) "
           "SELECT x.*, count(*) OVER (PARTITION BY x.bans) AS tied FROM ("
           "SELECT coalesce(a.hero, n.hero) AS hero, coalesce(n.bans, 0) AS bans, a.maps, "
           "round(100.0 * coalesce(n.bans, 0) / nullif(a.maps, 0), 1) AS ban_pct, a.available_from, a.seasons "
           "FROM a FULL JOIN n ON n.hero = a.hero "
           f"WHERE {keep}) x ORDER BY {order} LIMIT %s")
    return sql, params + side_params + ([s.hero] if s.hero and q.metric != "never_banned" else []) + [q.limit]


def team_rows_sql(s: BanSlice) -> tuple[str, list[Any]]:
    """One row per team in the slice: how often it banned the hero, over its maps the hero was available on."""
    q = s.query
    maps, params = _maps_cte(s)
    if q.metric == "never_banned":
        keep, order = "= 0", "team"
    else:
        d = "ASC" if q.sort == "asc" else "DESC"
        keep, order = ">= 1", f"bans {d}, ban_pct {d} NULLS LAST, team"
    sql = (f"WITH {maps}, "
           "t AS (SELECT fb.org_key, fb.display_name, fb.hero, m.played_at, m.season, "
           f"            {AVAILABLE} AS available "
           "       FROM fact_hero_bans fb JOIN m USING (series_id, round_number) JOIN heroes h ON h.hero = %s "
           "      WHERE fb.org_key IS NOT NULL) "
           "SELECT x.*, count(*) OVER (PARTITION BY x.bans) AS tied FROM ("
           "SELECT org_key, (array_agg(display_name ORDER BY played_at DESC))[1] AS team, "
           "count(*) FILTER (WHERE hero = %s) AS bans, count(*) FILTER (WHERE available) AS maps, "
           "round(100.0 * count(*) FILTER (WHERE hero = %s) / nullif(count(*) FILTER (WHERE available), 0), 1) AS ban_pct, "
           "array_agg(DISTINCT season ORDER BY season) AS seasons "
           "FROM t GROUP BY org_key "
           f"HAVING count(*) FILTER (WHERE available) > 0 AND count(*) FILTER (WHERE hero = %s) {keep}"
           f") x ORDER BY {order} LIMIT %s")
    return sql, params + [s.hero, s.hero, s.hero, s.hero, q.limit]


def _rows(conn: psycopg.Connection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(x) for x in cur.fetchall()]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rows


def slice_facts(conn: psycopg.Connection, s: BanSlice) -> dict[str, Any]:
    """The slice's size, its Liquipedia pages, the maps the warehouse has there with no recorded bans, and the bans no
    team holds (a linked series Liquipedia's record could not be oriented against)."""
    maps, params = _maps_cte(s)
    side, side_params = _side(s)
    row = _rows(conn, f"""WITH {maps}
        SELECT (SELECT count(*) FROM m) AS maps, (SELECT min(played_at) FROM m) AS first_at,
               (SELECT max(played_at) FROM m) AS last_at,
               (SELECT array_agg(DISTINCT liquipedia_page_url) FROM m WHERE liquipedia_page_url IS NOT NULL) AS pages,
               (SELECT count(*) FROM fact_hero_bans fb JOIN m USING (series_id, round_number)
                 WHERE fb.org_key IS NULL{side}) AS unattributed,
               (SELECT array_agg(DISTINCT fb.hero) FROM fact_hero_bans fb JOIN m USING (series_id, round_number)
                 WHERE NOT EXISTS (SELECT 1 FROM heroes h WHERE h.hero = fb.hero)) AS unknown_heroes""",
                params + side_params)[0]
    # maps the warehouse holds in the same slice, in seasons with bans, that have none recorded: series Liquipedia does
    # not record (a FACEIT-only relegation series), or a linked record whose games carry no bans
    f = s.query.filters
    clauses, wparams = [], []
    for col, val in (("season", f.season), ("region", f.region), ("map_name", s.map_name), ("game_mode", s.mode_name)):
        if val is not None:
            clauses.append(f"t.{col} = %s")
            wparams.append(val)
    if s.championship_ids:
        clauses.append("t.championship_id = ANY(%s)")
        wparams.append(s.championship_ids)
    if s.team_key:
        clauses.append("t.org_key = %s")
        wparams.append(s.team_key)
    clauses.append("t.season >= (SELECT min(bans_introduced_season) FROM hero_ban_settings)")
    clauses.append("NOT EXISTS (SELECT 1 FROM hero_ban_maps hm WHERE hm.series_id = t.series_id "
                   "AND hm.round_number = t.round_number)")
    row["maps_without_bans"] = _rows(conn, "SELECT count(DISTINCT (t.series_id, t.round_number)) AS n FROM fact_team_maps t "
                                           "WHERE " + " AND ".join(clauses), wparams)[0]["n"]
    return row


def evidence(conn: psycopg.Connection, s: BanSlice, rows: list[dict], evidence_for: Optional[str], page: int,
             page_size: int) -> Evidence:
    """The ban rows behind the first row (or the row `evidence_for` names): one per map, newest first."""
    q = s.query
    if q.metric == "never_banned":
        return Evidence(reason="a hero that was never banned has no ban rows; the maps it was available on are the "
                               "slice's maps")
    page, page_size = clamp_page(page, page_size)
    by = "org_key" if q.entity == "team" else "hero"
    target = next((x for x in rows if evidence_for and str(x.get(by)) == evidence_for), rows[0] if rows else None)
    if not target or not target.get("bans"):
        return Evidence(reason="no ban rows to show")
    maps, params = _maps_cte(s)
    if q.entity == "team":
        cond, cparams = "fb.org_key = %s AND fb.hero = %s", [target["org_key"], s.hero]
    else:
        side, side_params = _side(s)
        cond, cparams = "fb.hero = %s" + side, [target["hero"]] + side_params
    sql = (f"WITH {maps} SELECT fb.match_id, fb.round_number, fb.played_at, fb.season, fb.championship_id, "
           "championship_display_name(c.name) AS competition, fb.hero, fb.display_name AS team, "
           "fb.opponent_display_name AS opponent, fb.map_name, fb.game_mode, fb.banned_first, "
           "fb.liquipedia_page_url AS match_url, count(*) OVER () AS total_rows "
           "FROM fact_hero_bans fb JOIN m USING (series_id, round_number) "
           "JOIN championships c ON c.championship_id = fb.championship_id "
           f"WHERE {cond} ORDER BY fb.played_at DESC, fb.match_id DESC, fb.round_number LIMIT %s OFFSET %s")
    found = _rows(conn, sql, params + cparams + [page_size, (page - 1) * page_size])
    total = int(found[0]["total_rows"]) if found else 0
    for x in found:
        x.pop("total_rows", None)
    label = f"{target['team']}'s bans of {s.hero}" if q.entity == "team" else f"the maps {target['hero']} was banned on"
    return Evidence(available=bool(found), grain="map", description=label, rows=found, page=page, page_size=page_size,
                    total_rows=total, total_pages=(total + page_size - 1) // page_size, has_more=page * page_size < total,
                    columns=describe(found), expanded_for={"id": target.get(by), "name": target.get("team") or target.get("hero")},
                    expandable_by=by)


# ------------------------------------------------------------------ the sentence

def where_phrase(s: BanSlice) -> str:
    """' in NA 2025 on Ilios', ' at OWCS 2025 World Finals': the slice, as a reader would say it."""
    f = s.query.filters
    out = ""
    if s.championship_names and len(s.championship_names) <= 2:
        out += " at " + " and ".join(s.championship_names)
    else:
        bits = [_REGION.get(f.region, f.region or "")] if f.region else []
        if f.season:
            bits.append(str(f.season))
        if bits:
            out += " in " + " ".join(b for b in bits if b)
    if s.map_name:
        out += f" on {s.map_name}"
    elif s.mode_name:
        out += f" on {s.mode_name} maps"
    return out


def _team(b: _Builder, s: BanSlice) -> None:
    e = s.team_entity or {}
    b.mark(str(s.team_name or s.query.filters.team), e.get("entity_type") or "team", e.get("entity_id"))


def _names(b: _Builder, names: list[str], kind: str, more: int = 0) -> None:
    """'A', 'A and B', 'A, B and C', or 'A, B, C and 7 more' when more share the place than are named."""
    for i, n in enumerate(names):
        last = i == len(names) - 1 and not more
        b.add(("" if not i else " and " if last else ", "))
        b.mark(n, kind)
    if more:
        b.add(f" and {num(more)} more")


def sentence(s: BanSlice, rows: list[dict], facts: dict) -> Sentence:
    q = s.query
    where = where_phrase(s)
    against = q.filters.ban_side == "against"
    b = _Builder()
    if q.metric == "never_banned":
        if q.entity == "team":
            if not rows:
                return b.add(f"Every team with a map{where} where {s.hero} was available banned it at least once").done()
            b.add(f"{num(len(rows))} team{'s' if len(rows) != 1 else ''} never banned ").mark(s.hero, "hero")
            b.add(f"{where}: ")
            _names(b, [r["team"] for r in rows], "team")
            return b.done()
        who = ""
        if s.team_key:
            b.add("Heroes ")
            _team(b, s)
            who = " never banned" if not against else " never had banned against them"
        if not rows:
            b.text = ""
            b.spans = []
            b.add("Every hero available")
            if s.team_key:
                b.add(" on ")
                _team(b, s)
                b.add("'s maps")
            return b.add(f"{where} was banned at least once").done()
        if not s.team_key:
            b.add(f"{num(len(rows))} hero{'es' if len(rows) != 1 else ''} available{where} {'were' if len(rows) != 1 else 'was'} never banned: ")
        else:
            b.add(f"{who}{where} ({num(len(rows))}): ")
        _names(b, [r["hero"] for r in rows], "hero")
        return b.done()

    top = rows[0]
    tied = [r for r in rows if r["bans"] == top["bans"]][:3]
    more = max(int(facts.get("tied") or len(tied)) - len(tied), 0)
    if q.entity == "team":
        _names(b, [str(r["team"]) for r in tied], "team", more)
        b.add(" banned ").mark(s.hero, "hero")
        b.add(" the least" if q.sort == "asc" else " the most")
        b.add(f"{where}{' among teams that banned it' if q.sort == 'asc' else ''}: ")
        if len(tied) == 1 and not more:
            return b.add(f"on {num(top['bans'])} of its {num(top['maps'])} maps ({pct(top['ban_pct'])})").done()
        return b.add(f"{num(top['bans'])} time{'s' if top['bans'] != 1 else ''} each").done()

    if s.hero:   # one named hero
        if s.team_key:
            if against:
                b.mark(s.hero, "hero").add(" was banned against ")
                _team(b, s)
            else:
                _team(b, s)
                b.add(" banned ").mark(s.hero, "hero")
            if not top["bans"]:
                return b.add(f" on none of {num(top['maps'])} maps{where}" if top.get("maps") else f" on no map{where}").done()
            return b.add(f" on {num(top['bans'])} of {num(top['maps'])} maps{where} ({pct(top['ban_pct'])})").done()
        b.mark(s.hero, "hero")
        if not top["bans"]:
            return b.add(f" was never banned{where}, on any of the {num(top['maps'])} maps it was available on").done()
        return b.add(f" was banned on {num(top['bans'])} of the {num(top['maps'])} maps it was available on{where} "
                     f"({pct(top['ban_pct'])})").done()

    word = "least" if q.sort == "asc" else "most"
    several = len(tied) > 1 or more
    if s.team_key and not against:
        _team(b, s)
        b.add(" banned ")
        _names(b, [r["hero"] for r in tied], "hero", more)
        b.add(f" {word}{where}: ")
    else:
        _names(b, [r["hero"] for r in tied], "hero", more)
        b.add(f" {'were' if several else 'was'} the {word} banned hero{'es' if several else ''}")
        if s.team_key:
            b.add(" against ")
            _team(b, s)
        b.add(where)
        if q.sort == "asc":
            b.add(" among those banned at least once")
        b.add(": ")
    if not several:
        b.add(f"banned on {num(top['bans'])} of the {num(top['maps'])} maps it was available on ({pct(top['ban_pct'])})")
    else:
        b.add(f"{num(top['bans'])} ban{'s' if top['bans'] != 1 else ''} each")
    return b.done()


def notes(conn: psycopg.Connection, s: BanSlice, rows: list[dict], facts: dict) -> list[str]:
    q = s.query
    out = list(s.notes)
    out.append("Bans are Liquipedia's (one per team per map); FACEIT's room vote is not used.")
    if s.team_key and q.entity == "hero":
        out.append(f"Counted on the {num(facts['maps'])} maps with bans that {s.team_name} played: "
                   + ("the bans its opponents made against it." if q.filters.ban_side == "against" else "the bans it made."))
    if facts.get("maps_without_bans"):
        n = facts["maps_without_bans"]
        out.append(f"{num(n)} map{'s' if n != 1 else ''} in this slice {'are' if n != 1 else 'is'} in series whose "
                   "bans Liquipedia's records do not hold, so "
                   f"{'their bans are' if n != 1 else 'its bans are'} unknown and not counted.")
    if facts.get("unattributed"):
        out.append(f"{num(facts['unattributed'])} bans in this slice could not be given to a team (a linked series "
                   "whose Liquipedia record was not oriented) and count for no team.")
    if facts.get("unknown_heroes"):
        out.append("Bans name heroes the hero list does not hold (" + ", ".join(sorted(facts["unknown_heroes"]))
                   + "); add them to scope/heroes.json.")
    if q.entity == "hero" and q.metric != "never_banned" and not s.hero and facts.get("maps"):
        partial = [r for r in rows if r.get("maps") is not None and r["maps"] < facts["maps"]]
        if partial:
            out.append("Not available on every map in this slice, so counted over the maps they were: "
                       + "; ".join(f"{r['hero']} (from {r['available_from']}, {num(r['maps'])} of {num(facts['maps'])})"
                                   for r in partial[:6]) + ".")
    if q.metric != "never_banned" and q.sort == "asc" and not s.hero:
        out.append("Heroes never banned here are not ranked: ask which heroes were never banned.")
    return out


def run(conn: psycopg.Connection, s: BanSlice) -> tuple[list[dict], dict]:
    sql, params = team_rows_sql(s) if s.query.entity == "team" else hero_rows_sql(s)
    rows = _rows(conn, sql, params)
    facts = slice_facts(conn, s)
    # how many rows share the first row's count, over every row the ranking kept (not the page): a sentence naming
    # three of ten heroes tied at one ban must say there are ten
    facts["tied"] = int(rows[0]["tied"]) if rows else 0
    for row in rows:
        row.pop("tied", None)
    return rows, facts


def attribution(s: BanSlice, facts: dict) -> Optional[dict]:
    return attribution_block(facts.get("pages") or [])


def sql_of(s: BanSlice) -> tuple[str, list[Any]]:
    return team_rows_sql(s) if s.query.entity == "team" else hero_rows_sql(s)
