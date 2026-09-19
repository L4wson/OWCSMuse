"""The rows behind an answer: the aggregate is the claim, these are the proof.

Every answer that summarises something carries the individual rows that produce
it, at the grain the claim was made at - a map record returns each map, a series
record returns each series - newest first, paged. The rows come from the same
fact views the aggregate was computed from and carry the same filters, so a
reader can add them up and get the number back.

Only this module and `compile.py` produce SQL, and every value here is a bound
parameter.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import psycopg

from .columns import describe
from .compile import Resolved
from .validate import Validated

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

# A match room on FACEIT: the primary source for any row shown.
MATCH_URL = "'https://www.faceit.com/en/ow2/room/' || {col}"


@dataclass
class EvidenceQuery:
    sql: str
    params: list[Any]
    grain: str                       # map | series
    description: str
    subject_kind: Optional[str] = None
    subject_id: Optional[str] = None


@dataclass
class Evidence:
    available: bool = False
    grain: Optional[str] = None
    description: Optional[str] = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    total_rows: int = 0
    total_pages: int = 0
    has_more: bool = False
    columns: list[dict[str, Any]] = field(default_factory=list)   # {key, label, type} per shown column
    expanded_for: Optional[dict[str, Any]] = None   # which ranked row these rows belong to
    expandable_by: Optional[str] = None             # the column a UI passes back as evidence_for
    reason: Optional[str] = None                    # why there are no rows

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp_page(page: Optional[int], page_size: Optional[int]) -> tuple[int, int]:
    p = max(1, int(page or 1))
    size = int(page_size or DEFAULT_PAGE_SIZE)
    return p, max(1, min(size, MAX_PAGE_SIZE))


# --------------------------------------------------------------- row templates

_PLAYER_MAP_COLUMNS = """
    s.match_id, s.round_number, s.started_at AS played_at, s.season,
    s.championship_id, championship_display_name(c.name) AS competition,
    s.display_name AS team, s.opponent_display_name AS opponent,
    s.map_name, s.game_mode,
    tm.score AS score, tm.opp_score AS opponent_score,
    CASE WHEN s.map_won THEN 'won' WHEN s.map_drawn THEN 'drawn' ELSE 'lost' END AS result,
    s.role, s.eliminations, s.deaths, s.assists, s.damage_dealt, s.healing_done, s.damage_mitigated
"""

_TEAM_MAP_COLUMNS = """
    s.match_id, s.round_number, s.started_at AS played_at, s.season,
    s.championship_id, championship_display_name(c.name) AS competition,
    s.display_name AS team, s.opponent_display_name AS opponent,
    s.map_name, s.game_mode,
    s.score AS score, s.opp_score AS opponent_score,
    CASE WHEN s.won THEN 'won' WHEN s.drawn THEN 'drawn' ELSE 'lost' END AS result
"""

_TEAM_SERIES_COLUMNS = """
    s.match_id, NULL::int AS round_number, s.started_at AS played_at, s.season,
    s.championship_id, championship_display_name(c.name) AS competition,
    s.display_name AS team, s.opponent_display_name AS opponent,
    s.best_of, s.map_wins AS score, s.map_losses AS opponent_score,
    CASE WHEN s.won THEN 'won' ELSE 'lost' END AS result,
    (s.ingest_state = 'complete') AS map_stats_recorded
"""

# A map row belonging to no one in particular: one row per map rather than one
# per side, so a warehouse-wide breakdown can still be read back map by map.
_NEUTRAL_MAP_INNER = """
    SELECT DISTINCT ON (s.match_id, s.round_number)
        s.match_id, s.round_number, s.started_at AS played_at, s.season,
        s.championship_id, championship_display_name(c.name) AS competition,
        s.display_name AS team, s.opponent_display_name AS opponent,
        s.map_name, s.game_mode, s.score, s.opp_score AS opponent_score,
        CASE WHEN s.drawn THEN 'draw' WHEN s.won THEN s.display_name ELSE s.opponent_display_name END AS winner
      FROM fact_team_maps s JOIN championships c ON c.championship_id = s.championship_id
     WHERE {where}
     ORDER BY s.match_id, s.round_number, s.team_id
"""

_ORDER = " ORDER BY played_at DESC NULLS LAST, match_id DESC, round_number NULLS FIRST"


def _paged(select: str, from_where: str, select_params: list[Any], where_params: list[Any],
           page: int, page_size: int) -> tuple[str, list[Any]]:
    """One statement that returns the page and the size of the whole set."""
    sql = (f"SELECT {select}, {MATCH_URL.format(col='s.match_id')} AS match_url, "
           f"count(*) OVER () AS total_rows FROM {from_where}{_ORDER} LIMIT %s OFFSET %s")
    return sql, select_params + where_params + [page_size, (page - 1) * page_size]


def _filters(v: Validated, alias: str, *, season: bool = True, champ: bool = True,
             map_mode: bool = True, region: bool = True) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    f = v.query.filters
    if season and f.season:
        clauses.append(f"{alias}.season = %s")
        params.append(f.season)
    if champ and v.championship_ids:
        clauses.append(f"{alias}.championship_id = ANY(%s)")
        params.append(list(v.championship_ids))
    if map_mode and v.map_name:
        clauses.append(f"{alias}.map_name = %s")
        params.append(v.map_name)
    if map_mode and v.mode_name:
        clauses.append(f"{alias}.game_mode = %s")
        params.append(v.mode_name)
    if region and f.region:
        clauses.append(f"{alias}.region = %s")
        params.append(f.region)
    return clauses, params


def _player_maps(v: Validated, player_id: str, extra: list[str], extra_params: list[Any],
                 page: int, page_size: int, stat_key: Optional[str] = None) -> tuple[str, list[Any]]:
    select = _PLAYER_MAP_COLUMNS
    select_params: list[Any] = []
    if stat_key:
        select = select + ", stat_num(s.stats ->> %s) AS stat_value, %s AS stat_key"
        select_params = [stat_key, stat_key]
    clauses, params = _filters(v, "s")
    clauses = ["s.player_id = %s"] + clauses + extra
    params = [player_id] + params + extra_params
    from_where = ("fact_player_maps s "
                  "JOIN championships c ON c.championship_id = s.championship_id "
                  "LEFT JOIN fact_team_maps tm ON tm.match_id = s.match_id "
                  "AND tm.round_number = s.round_number AND tm.team_id = s.team_id "
                  "WHERE " + " AND ".join(clauses))
    return _paged(select, from_where, select_params, params, page, page_size)


def _team_maps(v: Validated, org_key: str, extra: list[str], extra_params: list[Any],
               page: int, page_size: int) -> tuple[str, list[Any]]:
    clauses, params = _filters(v, "s")
    clauses = ["s.org_key = %s"] + clauses + extra
    params = [org_key] + params + extra_params
    from_where = ("fact_team_maps s JOIN championships c ON c.championship_id = s.championship_id "
                  "WHERE " + " AND ".join(clauses))
    return _paged(_TEAM_MAP_COLUMNS, from_where, [], params, page, page_size)


def _neutral_maps(v: Validated, extra: list[str], extra_params: list[Any],
                  page: int, page_size: int) -> tuple[str, list[Any]]:
    clauses, params = _filters(v, "s")
    clauses = (clauses + extra) or ["true"]
    inner = _NEUTRAL_MAP_INNER.format(where=" AND ".join(clauses))
    return _paged("s.*", f"({inner}) s", [], params + extra_params, page, page_size)


def _team_series(v: Validated, column: str, value: str, extra: list[str], extra_params: list[Any],
                 page: int, page_size: int) -> tuple[str, list[Any]]:
    clauses, params = _filters(v, "s", map_mode=False)
    clauses = [f"s.{column} = %s"] + clauses + extra
    params = [value] + params + extra_params
    from_where = ("fact_team_matches s JOIN championships c ON c.championship_id = s.championship_id "
                  "WHERE " + " AND ".join(clauses))
    return _paged(_TEAM_SERIES_COLUMNS, from_where, [], params, page, page_size)


_ON_ROSTER = ("EXISTS (SELECT 1 FROM match_rosters mr WHERE mr.match_id = s.match_id"
              " AND mr.player_id = %s AND mr.team_id = s.{side})")


def _side_clause(entity_id: str, entity_type: Optional[str], r: Resolved, side: str) -> tuple[str, list[Any]]:
    """Restrict a series row to one side being this entity, player or org."""
    if entity_type == "player":
        return _ON_ROSTER.format(side=side), [entity_id]
    column = "org_key" if side == "team_id" else "opponent_org_key"
    return f"s.{column} = %s", [r.org_key(entity_id, entity_type)]


def compile_missing_series(v: Validated, r: Resolved, page: int, page_size: int) -> Optional[EvidenceQuery]:
    """The series two entities played whose maps FACEIT never recorded.

    When a map record comes back empty because the stats are missing rather than
    because the pairing never happened, these rows are the proof of that: real
    series, real results, no maps.
    """
    subject_id = r.player_id if r.subject_type == "player" else r.team_id
    if not (subject_id and r.opponent_id):
        return None
    a_sql, a_params = _side_clause(subject_id, r.subject_type, r, "team_id")
    b_sql, b_params = _side_clause(r.opponent_id, r.opponent_type, r, "opponent_team_id")
    clauses, params = _filters(v, "s", map_mode=False)
    clauses = ["s.ingest_state = 'result_only'", a_sql, b_sql] + clauses
    params = a_params + b_params + params
    from_where = ("fact_team_matches s JOIN championships c ON c.championship_id = s.championship_id "
                  "WHERE " + " AND ".join(clauses))
    sql, all_params = _paged(_TEAM_SERIES_COLUMNS, from_where, [], params, page, page_size)
    return EvidenceQuery(sql, all_params, "series",
                         "series they played whose maps FACEIT never recorded", r.subject_type, subject_id)


# ------------------------------------------------------------------ compilation

# Metrics whose claim is about maps rather than series. Mirrors the aggregate
# compiler's choice of agg_team_maps over agg_team_matches.
_MAP_GRAIN_METRICS = frozenset({"map_wins", "map_losses", "map_win_rate", "maps"})


def is_map_grain(v: Validated) -> bool:
    """Whether the claim is about maps rather than series."""
    return bool(v.map_name or v.mode_name) or (v.query.metric in _MAP_GRAIN_METRICS)


def _subject_from(v: Validated, r: Resolved, expand: Optional[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    """(kind, id) of whoever the rows should be about: the ranked row when expanding, else the subject."""
    if expand and expand.get("id") and expand.get("type") in ("player", "org", "team"):
        return expand.get("type") or ("player" if v.query.entity == "player" else "org"), expand["id"]
    if r.player_id and r.subject_type == "player":
        return "player", r.player_id
    if r.team_id:
        return "org", r.org_key(r.team_id, r.subject_type)
    return None, None


def compile_evidence(v: Validated, r: Resolved, expand: Optional[dict[str, Any]] = None,
                     page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
                     stat_key: Optional[str] = None) -> Optional[EvidenceQuery]:
    """The rows behind this answer, or None when the answer has no row grain."""
    q = v.query
    intent = q.intent
    if intent == "stat_availability":
        return None

    kind, subject_id = _subject_from(v, r, expand)

    if intent == "versus":
        if not (r.opponent_id and subject_id):
            return None
        opponent_is_player = r.opponent_type == "player"
        if kind == "player":
            if opponent_is_player:
                extra = ["EXISTS (SELECT 1 FROM fact_player_maps o WHERE o.match_id = s.match_id"
                         " AND o.round_number = s.round_number AND o.player_id = %s"
                         " AND o.team_id IS DISTINCT FROM s.team_id)"]
                extra_params: list[Any] = [r.opponent_id]
            else:
                extra = ["s.opponent_org_key = %s"]
                extra_params = [r.org_key(r.opponent_id, r.opponent_type)]
            sql, params = _player_maps(v, subject_id, extra, extra_params, page, page_size, stat_key)
            return EvidenceQuery(sql, params, "map", "every map behind this record", kind, subject_id)
        if opponent_is_player:
            # org vs player: the maps where that player faced this org, from the org's side
            extra = ["EXISTS (SELECT 1 FROM fact_player_maps o WHERE o.match_id = s.match_id"
                     " AND o.round_number = s.round_number AND o.player_id = %s"
                     " AND o.team_id IS DISTINCT FROM s.team_id)"]
            extra_params = [r.opponent_id]
        else:
            extra = ["s.opponent_org_key = %s"]
            extra_params = [r.org_key(r.opponent_id, r.opponent_type)]
        sql, params = _team_maps(v, subject_id, extra, extra_params, page, page_size)
        return EvidenceQuery(sql, params, "map", "every map behind this record", kind, subject_id)

    if intent == "head_to_head":
        if not (r.team_id and r.opponent_id):
            return None
        sql, params = _team_series(v, "team_id", r.team_id, ["s.opponent_team_id = %s"], [r.opponent_id],
                                   page, page_size)
        return EvidenceQuery(sql, params, "series", "every series behind this record", "team", r.team_id)

    if intent == "season_compare":
        seasons = [s for s in (q.filters.subject_season, q.filters.opponent_season) if s]
        if not (subject_id and seasons):
            return None
        if kind == "player":
            sql, params = _player_maps(v, subject_id, ["s.season = ANY(%s)"], [seasons], page, page_size, stat_key)
        else:
            sql, params = _team_maps(v, subject_id, ["s.season = ANY(%s)"], [seasons], page, page_size)
        return EvidenceQuery(sql, params, "map", "every map in both seasons", kind, subject_id)

    if intent == "map_stats":
        extra, extra_params = [], []
        if expand and expand.get("type") in ("map", "mode") and expand.get("id"):
            column = "map_name" if expand["type"] == "map" else "game_mode"
            extra, extra_params = [f"s.{column} = %s"], [expand["id"]]
        if kind == "player" and subject_id:
            sql, params = _player_maps(v, subject_id, extra, extra_params, page, page_size, stat_key)
        elif subject_id:
            sql, params = _team_maps(v, subject_id, extra, extra_params, page, page_size)
        else:
            sql, params = _neutral_maps(v, extra, extra_params, page, page_size)
        label = (expand or {}).get("id")
        return EvidenceQuery(sql, params, "map",
                             f"every map played on {label}" if label else "every map in this breakdown",
                             kind, subject_id)

    if not subject_id:
        return None

    # An org's series record is a series-grain claim, whether it was asked of one
    # team or ranked across many, so its evidence is series either way.
    if kind != "player" and (intent == "team_record" or q.entity == "team") and not is_map_grain(v):
        sql, params = _team_series(v, "org_key", subject_id, [], [], page, page_size)
        return EvidenceQuery(sql, params, "series", "every series behind this record", kind, subject_id)

    # entity_stat, leaderboard row expansion, map_stats with a subject
    if kind == "player":
        sql, params = _player_maps(v, subject_id, [], [], page, page_size, stat_key)
        return EvidenceQuery(sql, params, "map", "every map behind this number", kind, subject_id)
    sql, params = _team_maps(v, subject_id, [], [], page, page_size)
    return EvidenceQuery(sql, params, "map", "every map behind this number", kind, subject_id)


# ------------------------------------------------------------------- execution

def entity_of(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The entity a ranked row is about: its id, its kind and its name.

    Carried on the row itself so expansion is mechanical - no client has to work
    out that a leaderboard is keyed on `player_id` and labelled by `nickname`.
    """
    if row.get("player_id"):
        return {"id": row["player_id"], "type": "player", "name": row.get("nickname"), "column": "player_id"}
    if row.get("org_key"):
        return {"id": row["org_key"], "type": "org", "name": row.get("team") or row.get("display_name"),
                "column": "org_key"}
    if row.get("map_name"):
        return {"id": row["map_name"], "type": "map", "name": row["map_name"], "column": "map_name"}
    if row.get("game_mode"):
        return {"id": row["game_mode"], "type": "mode", "name": row["game_mode"], "column": "game_mode"}
    return None


def expansion_target(rows: list[dict[str, Any]], evidence_for: Optional[str]) -> Optional[dict[str, Any]]:
    """Which ranked row to show proof for: the one asked for, else the top one.

    A leaderboard's claim is about every row, so one page of evidence can only
    ever be about one of them; saying which is part of the answer.
    """
    if not rows:
        return None
    target = entity_of
    if evidence_for:
        for row in rows:
            if evidence_for in (row.get("player_id"), row.get("org_key"), row.get("map_name"), row.get("game_mode")):
                return target(row)
        # an id that is not in this page is still a legitimate ask
        kind = "org" if evidence_for.startswith("team:") or "-" not in evidence_for else "player"
        return {"id": evidence_for, "type": kind, "name": None, "column": f"{kind}_id"}
    return target(rows[0])


def _run(conn: psycopg.Connection, compiled: EvidenceQuery, page: int, page_size: int,
         expand: Optional[dict[str, Any]] = None, expandable_by: Optional[str] = None) -> Evidence:
    try:
        with conn.cursor() as cur:
            cur.execute(compiled.sql, compiled.params)
            fetched = [dict(x) for x in cur.fetchall()]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    total = int(fetched[0]["total_rows"]) if fetched else 0
    for row in fetched:
        row.pop("total_rows", None)
    return Evidence(
        available=True, grain=compiled.grain, description=compiled.description, rows=fetched,
        columns=describe(fetched),
        page=page, page_size=page_size, total_rows=total,
        total_pages=(total + page_size - 1) // page_size if total else 0,
        has_more=page * page_size < total,
        expanded_for=expand, expandable_by=expandable_by,
        reason=None if fetched else "no rows match this slice",
    )


def fetch_missing_series(conn: psycopg.Connection, v: Validated, r: Resolved,
                         page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> Evidence:
    """Evidence for an empty map record: the series that have no maps."""
    page, page_size = clamp_page(page, page_size)
    compiled = compile_missing_series(v, r, page, page_size)
    if compiled is None:
        return Evidence(reason="this pairing has no series to show")
    return _run(conn, compiled, page, page_size)


def fetch_evidence(conn: psycopg.Connection, v: Validated, r: Resolved, rows: list[dict[str, Any]],
                   evidence_for: Optional[str] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
                   stat_key: Optional[str] = None) -> Evidence:
    """Run the evidence query for an answer and wrap it with its paging state."""
    page, page_size = clamp_page(page, page_size)
    q = v.query
    if q.intent == "stat_availability":
        return Evidence(reason="stat availability is already a per-season listing; there are no rows behind it")

    expand = None
    ranked = q.intent in ("leaderboard", "map_stats")
    if ranked:
        expand = expansion_target(rows, evidence_for)
        if not expand:
            return Evidence(reason="this ranking has no row that can be expanded")
    elif evidence_for:
        expand = expansion_target(rows, evidence_for)

    compiled = compile_evidence(v, r, expand, page, page_size, stat_key)
    if compiled is None:
        return Evidence(reason="this answer has no per-row grain")

    return _run(conn, compiled, page, page_size,
                expand=expand if (ranked or evidence_for) else None,
                expandable_by=(expand or {}).get("column") if ranked else None)
