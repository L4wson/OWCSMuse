"""Compile a validated StructuredQuery into parameterized SQL over the agg_* layer.

Only this module produces SQL. Every WHERE value is a bound parameter; column
names come from a fixed whitelist (TYPED_STATS). The compiler reuses
stat_leaderboard() / stat_coverage_summary() wherever they fit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .schema import DERIVED_METRICS, Unanswerable
from .validate import TYPED_STATS, Validated


@dataclass
class Resolved:
    """Entity ids after resolution, keyed by filter role."""
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    opponent_id: Optional[str] = None
    names: dict[str, str] = field(default_factory=dict)  # role -> display name


@dataclass
class Compiled:
    sql: str
    params: list[Any]
    description: str
    coverage_stat: Optional[str] = None          # stat key whose coverage should accompany the answer
    coverage_season: Optional[int] = None
    coverage_championship: Optional[str] = None  # only when exactly one championship is in play
    sample_columns: tuple[str, ...] = ("maps", "matches")


CompileResult = Union[Compiled, Unanswerable]


def _where(clauses: list[str], params: list[Any], col: str, value: Any, op: str = "=") -> None:
    if value is None:
        return
    if isinstance(value, list):
        clauses.append(f"{col} = ANY(%s)")
        params.append(value)
    else:
        clauses.append(f"{col} {op} %s")
        params.append(value)


def _dir(sort: str) -> str:
    return "ASC" if sort == "asc" else "DESC"


def compile_query(v: Validated, r: Resolved) -> CompileResult:
    q = v.query
    f = q.filters
    champ = v.championship_ids or None
    single_champ = champ[0] if champ and len(champ) == 1 else None
    stat = None if (q.metric in DERIVED_METRICS or q.metric is None) else q.metric
    col = TYPED_STATS.get(stat) if stat else None

    # ------------------------------------------------------------- availability
    if q.intent == "stat_availability":
        clauses, params = [], []
        _where(clauses, params, "stat_key", q.metric)
        _where(clauses, params, "season", f.season)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return Compiled(
            sql=f"SELECT season, stat_key, rows_with_stat, rows_total, coverage_pct, championships_with_stat, championships_total "
                f"FROM stat_coverage_season{where} ORDER BY season, stat_key",
            params=params, description="stat availability per season", coverage_stat=None, sample_columns=("rows_total",),
        )

    # ------------------------------------------------------------- head to head
    if q.intent == "head_to_head":
        if not (r.team_id and r.opponent_id):
            return Unanswerable(code="invalid_query", reason="head-to-head needs two resolved teams")
        a, b = sorted([r.team_id, r.opponent_id])
        clauses, params = ["team_a = %s", "team_b = %s"], [a, b]
        _where(clauses, params, "season", f.season)
        _where(clauses, params, "championship_id", champ)
        _where(clauses, params, "region", f.region)
        # present from the perspective of the first-named team
        first_is_a = r.team_id == a
        sql = (
            "SELECT %s AS team, %s AS opponent, "
            + ("sum(a_wins)" if first_is_a else "sum(b_wins)") + " AS wins, "
            + ("sum(b_wins)" if first_is_a else "sum(a_wins)") + " AS losses, "
            + ("sum(a_map_wins)" if first_is_a else "sum(b_map_wins)") + " AS map_wins, "
            + ("sum(b_map_wins)" if first_is_a else "sum(a_map_wins)") + " AS map_losses, "
            "sum(matches) AS matches, sum(maps) AS maps, min(first_match_at) AS first_match_at, max(last_match_at) AS last_match_at, "
            "array_agg(DISTINCT season ORDER BY season) AS seasons "
            "FROM agg_head_to_head WHERE " + " AND ".join(clauses)
        )
        return Compiled(sql=sql, params=[r.names.get("team"), r.names.get("opponent")] + params,
                        description="head-to-head series record", coverage_season=f.season, coverage_championship=single_champ)

    # ------------------------------------------------------------- team record
    if q.intent == "team_record" or (q.intent in ("entity_stat", "leaderboard") and q.entity == "team" and q.metric in DERIVED_METRICS):
        per_team = q.intent == "leaderboard"
        clauses, params = [], []
        if not per_team:
            if not r.team_id:
                return Unanswerable(code="invalid_query", reason="team record needs a resolved team")
            _where(clauses, params, "t.team_id", r.team_id)
        _where(clauses, params, "t.season", f.season)
        _where(clauses, params, "t.championship_id", champ)
        _where(clauses, params, "t.region", f.region)
        use_maps = bool(v.map_name or v.mode_name) or q.metric in ("map_wins", "map_losses", "map_win_rate", "maps")
        if use_maps:
            _where(clauses, params, "t.map_name", v.map_name)
            _where(clauses, params, "t.game_mode", v.mode_name)
            select = ("t.team_id, tm.name AS team, sum(t.maps) AS maps, sum(t.matches) AS matches, sum(t.wins) AS map_wins, "
                      "sum(t.losses) AS map_losses, sum(t.draws) AS draws, "
                      "round(100.0 * sum(t.wins) / nullif(sum(t.maps), 0), 1) AS map_win_pct, "
                      "array_agg(DISTINCT t.season ORDER BY t.season) AS seasons")
            table, order_key = "agg_team_maps", {"map_win_rate": "map_win_pct", "map_wins": "map_wins", "map_losses": "map_losses"}.get(q.metric, "maps")
        else:
            select = ("t.team_id, tm.name AS team, sum(t.matches) AS matches, sum(t.wins) AS wins, sum(t.losses) AS losses, "
                      "sum(t.map_wins) AS map_wins, sum(t.map_losses) AS map_losses, sum(t.maps) AS maps, "
                      "round(100.0 * sum(t.wins) / nullif(sum(t.matches), 0), 1) AS win_pct, "
                      "min(t.first_match_at) AS first_match_at, max(t.last_match_at) AS last_match_at, "
                      "array_agg(DISTINCT t.season ORDER BY t.season) AS seasons")
            table, order_key = "agg_team_matches", {"win_rate": "win_pct", "wins": "wins", "losses": "losses", "matches": "matches"}.get(q.metric, "win_pct")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT {select} FROM {table} t JOIN teams tm ON tm.team_id = t.team_id{where} GROUP BY t.team_id, tm.name"
        if per_team:
            sql += f" HAVING sum(t.matches) >= %s ORDER BY {order_key} {_dir(q.sort)} NULLS LAST, matches DESC LIMIT %s"
            params += [q.min_maps, q.limit]
        return Compiled(sql=sql, params=params, description=f"team {'leaderboard' if per_team else 'record'} ({q.metric})",
                        coverage_season=f.season, coverage_championship=single_champ)

    # ------------------------------------------------------------- map / mode rows
    if q.intent == "map_stats":
        group = "map_name" if q.entity == "map" else "game_mode"
        clauses, params = [], []
        _where(clauses, params, "season", f.season)
        _where(clauses, params, "championship_id", champ)
        _where(clauses, params, "region", f.region)
        if q.entity == "map":
            _where(clauses, params, "game_mode", v.mode_name)
        else:
            _where(clauses, params, "map_name", v.map_name)
        if r.team_id:
            _where(clauses, params, "team_id", r.team_id)
            select = (f"{group}, sum(maps) AS maps, sum(matches) AS matches, sum(wins) AS wins, sum(losses) AS losses, sum(draws) AS draws, "
                      "round(100.0 * sum(wins) / nullif(sum(maps), 0), 1) AS win_pct")
            table, order_key = "agg_team_maps", "win_pct" if q.metric in ("map_win_rate", "win_rate") else "maps"
        elif r.player_id:
            _where(clauses, params, "player_id", r.player_id)
            extra = ""
            if col:
                extra = f", sum(sum_{col}) AS {col}_total, round(sum(sum_{col}) / nullif(sum(maps_with_{col}), 0), 1) AS {col}_per_map"
            select = (f"{group}, sum(maps) AS maps, sum(matches) AS matches, sum(maps_won) AS wins, sum(maps) - sum(maps_won) - sum(maps_drawn) AS losses, "
                      f"round(100.0 * sum(maps_won) / nullif(sum(maps), 0), 1) AS win_pct{extra}")
            table = "agg_player_stats"
            order_key = f"{col}_per_map" if (col and q.aggregation == "avg_per_map") else (f"{col}_total" if col else ("win_pct" if q.metric in ("map_win_rate", "win_rate") else "maps"))
        else:
            select = (f"{group}, sum(maps) AS maps, sum(matches) AS matches, sum(team1_wins) AS team1_wins, sum(team2_wins) AS team2_wins, "
                      "sum(draws) AS draws, sum(maps_with_duration) AS maps_with_duration, "
                      "round(avg(avg_duration_seconds)) AS avg_duration_seconds")
            table, order_key = "agg_map_modes", "maps"
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT {select} FROM {table}{where} GROUP BY {group} HAVING sum(maps) >= %s ORDER BY {order_key} {_dir(q.sort)} NULLS LAST, maps DESC LIMIT %s"
        params += [q.min_maps, q.limit]
        return Compiled(sql=sql, params=params, description=f"{q.entity} breakdown ({q.metric})", coverage_stat=stat,
                        coverage_season=f.season, coverage_championship=single_champ)

    # ------------------------------------------------------------- player stat / leaderboard
    if q.entity == "team" and stat:
        # team-level totals of a typed stat
        if not col:
            return Unanswerable(code="unsupported_metric", reason=f"'{stat}' is not available at team level; typed stats only: {', '.join(TYPED_STATS)}")
        clauses, params = [], []
        if q.intent == "entity_stat":
            if not r.team_id:
                return Unanswerable(code="invalid_query", reason="needs a resolved team")
            _where(clauses, params, "a.team_id", r.team_id)
        _where(clauses, params, "a.season", f.season)
        _where(clauses, params, "a.championship_id", champ)
        _where(clauses, params, "a.region", f.region)
        _where(clauses, params, "a.map_name", v.map_name)
        _where(clauses, params, "a.game_mode", v.mode_name)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (f"SELECT a.team_id, tm.name AS team, sum(a.sum_{col}) AS total, sum(a.maps_with_{col}) AS player_map_rows, "
               f"round(sum(a.sum_{col}) / nullif(sum(a.maps_with_{col}), 0), 1) AS avg_per_player_map, "
               f"array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
               f"FROM agg_player_stats a JOIN teams tm ON tm.team_id = a.team_id{where} GROUP BY a.team_id, tm.name")
        if q.intent == "leaderboard":
            sql += f" HAVING sum(a.maps_with_{col}) >= %s ORDER BY {'avg_per_player_map' if q.aggregation == 'avg_per_map' else 'total'} {_dir(q.sort)} NULLS LAST LIMIT %s"
            params += [q.min_maps, q.limit]
        return Compiled(sql=sql, params=params, description=f"team {stat}", coverage_stat=stat, coverage_season=f.season,
                        coverage_championship=single_champ, sample_columns=("player_map_rows",))

    if q.metric == "kd_ratio" or (q.metric in ("maps", "matches", "map_wins", "map_losses", "map_win_rate", "wins", "losses") and q.entity == "player"):
        clauses, params = [], []
        if q.intent == "entity_stat":
            if not r.player_id:
                return Unanswerable(code="invalid_query", reason="needs a resolved player")
            _where(clauses, params, "a.player_id", r.player_id)
        _where(clauses, params, "a.season", f.season)
        _where(clauses, params, "a.championship_id", champ)
        _where(clauses, params, "a.region", f.region)
        _where(clauses, params, "a.team_id", r.team_id)
        _where(clauses, params, "a.map_name", v.map_name)
        _where(clauses, params, "a.game_mode", v.mode_name)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = ("SELECT a.player_id, p.nickname, sum(a.maps) AS maps, sum(a.matches) AS matches, sum(a.maps_won) AS map_wins, "
               "sum(a.maps) - sum(a.maps_won) - sum(a.maps_drawn) AS map_losses, "
               "round(100.0 * sum(a.maps_won) / nullif(sum(a.maps), 0), 1) AS map_win_pct, "
               "sum(a.sum_eliminations) AS eliminations, sum(a.sum_deaths) AS deaths, "
               "round(sum(a.sum_eliminations)::numeric / nullif(sum(a.sum_deaths), 0), 2) AS kd_ratio, "
               "array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
               f"FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id{where} GROUP BY a.player_id, p.nickname")
        order_key = {"kd_ratio": "kd_ratio", "maps": "maps", "matches": "matches", "map_wins": "map_wins", "map_losses": "map_losses",
                     "map_win_rate": "map_win_pct", "wins": "map_wins", "losses": "map_losses"}[q.metric]
        if q.intent == "leaderboard":
            sql += f" HAVING sum(a.maps) >= %s ORDER BY {order_key} {_dir(q.sort)} NULLS LAST, maps DESC LIMIT %s"
            params += [q.min_maps, q.limit]
        return Compiled(sql=sql, params=params, description=f"player {q.metric}", coverage_stat="Eliminations" if q.metric == "kd_ratio" else None,
                        coverage_season=f.season, coverage_championship=single_champ)

    if not stat:
        return Unanswerable(code="unsupported_metric", reason=f"cannot compute '{q.metric}' for {q.entity}")

    sliced = bool(v.map_name or v.mode_name or r.team_id or f.region)
    order_expr = "avg_per_map" if q.aggregation == "avg_per_map" else "total"

    if q.intent == "entity_stat":
        if not r.player_id:
            return Unanswerable(code="invalid_query", reason="needs a resolved player")
        if sliced:
            clauses, params = ["a.player_id = %s"], [r.player_id]
            _where(clauses, params, "a.season", f.season)
            _where(clauses, params, "a.championship_id", champ)
            _where(clauses, params, "a.region", f.region)
            _where(clauses, params, "a.team_id", r.team_id)
            _where(clauses, params, "a.map_name", v.map_name)
            _where(clauses, params, "a.game_mode", v.mode_name)
            sql = (f"SELECT a.player_id, p.nickname, sum(a.maps_with_{col}) AS maps_with_stat, sum(a.maps) AS maps_played, "
                   f"round(100.0 * sum(a.maps_with_{col}) / nullif(sum(a.maps), 0), 1) AS coverage_pct, "
                   f"sum(a.sum_{col}) AS total, round(sum(a.sum_{col}) / nullif(sum(a.maps_with_{col}), 0), 2) AS avg_per_map, "
                   "array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
                   f"FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id WHERE {' AND '.join(clauses)} GROUP BY a.player_id, p.nickname")
        else:
            clauses, params = ["l.player_id = %s", "l.stat_key = %s"], [r.player_id, stat]
            _where(clauses, params, "l.season", f.season)
            _where(clauses, params, "l.championship_id", champ)
            s_clauses, s_params = ["s.player_id = %s"], [r.player_id]
            _where(s_clauses, s_params, "s.season", f.season)
            _where(s_clauses, s_params, "s.championship_id", champ)
            sql = ("WITH played AS (SELECT s.player_id, sum(s.maps) AS maps_played FROM agg_player_stats s WHERE "
                   + " AND ".join(s_clauses) + " GROUP BY s.player_id) "
                   "SELECT l.player_id, p.nickname, sum(l.maps_with_stat) AS maps_with_stat, max(played.maps_played) AS maps_played, "
                   "round(100.0 * sum(l.maps_with_stat) / nullif(max(played.maps_played), 0), 1) AS coverage_pct, "
                   "sum(l.total) AS total, round(sum(l.total) / nullif(sum(l.maps_with_stat), 0), 2) AS avg_per_map, "
                   "min(l.min_per_map) AS min_per_map, max(l.max_per_map) AS max_per_map, "
                   "array_agg(DISTINCT l.season ORDER BY l.season) AS seasons "
                   "FROM agg_player_stat_long l JOIN players p ON p.player_id = l.player_id "
                   "LEFT JOIN played ON played.player_id = l.player_id WHERE " + " AND ".join(clauses) + " GROUP BY l.player_id, p.nickname")
            params = s_params + params  # the CTE's placeholders come first in the statement
        return Compiled(sql=sql, params=params, description=f"{stat} for one player", coverage_stat=stat,
                        coverage_season=f.season, coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))

    # leaderboard over a stat key
    if not sliced and len(champ or []) <= 1:
        # reuse the SQL function; asc sort needs a wrapper because the function ranks descending
        if q.sort == "asc":
            sql = (f"SELECT * FROM stat_leaderboard(%s, %s, %s, %s, 10000, %s) ORDER BY {order_expr} ASC NULLS LAST LIMIT %s")
            params = [stat, f.season, single_champ, q.min_maps, "avg" if q.aggregation == "avg_per_map" else "total", q.limit]
        else:
            sql = "SELECT * FROM stat_leaderboard(%s, %s, %s, %s, %s, %s)"
            params = [stat, f.season, single_champ, q.min_maps, q.limit, "avg" if q.aggregation == "avg_per_map" else "total"]
        return Compiled(sql=sql, params=params, description=f"{stat} leaderboard", coverage_stat=stat, coverage_season=f.season,
                        coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))

    if not col:
        return Unanswerable(code="unsupported_metric", reason=f"'{stat}' cannot be sliced by map/mode/team/region")
    clauses, params = [], []
    _where(clauses, params, "a.season", f.season)
    _where(clauses, params, "a.championship_id", champ)
    _where(clauses, params, "a.region", f.region)
    _where(clauses, params, "a.team_id", r.team_id)
    _where(clauses, params, "a.map_name", v.map_name)
    _where(clauses, params, "a.game_mode", v.mode_name)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (f"SELECT a.player_id, p.nickname, sum(a.maps_with_{col}) AS maps_with_stat, sum(a.maps) AS maps_played, "
           f"round(100.0 * sum(a.maps_with_{col}) / nullif(sum(a.maps), 0), 1) AS coverage_pct, "
           f"sum(a.sum_{col}) AS total, round(sum(a.sum_{col}) / nullif(sum(a.maps_with_{col}), 0), 2) AS avg_per_map, "
           "array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
           f"FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id{where} GROUP BY a.player_id, p.nickname "
           f"HAVING sum(a.maps_with_{col}) >= %s ORDER BY {order_expr} {_dir(q.sort)} NULLS LAST, maps_with_stat DESC LIMIT %s")
    params += [q.min_maps, q.limit]
    return Compiled(sql=sql, params=params, description=f"{stat} leaderboard (sliced)", coverage_stat=stat, coverage_season=f.season,
                    coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))
