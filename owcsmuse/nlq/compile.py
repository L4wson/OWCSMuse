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
    """Entity ids after resolution, keyed by filter role.

    `subject_type` / `opponent_type` are 'player', 'org' or 'team', which is what
    decides whether a versus question is answered from the player-vs-player, the
    player-vs-org or the org-vs-org fact.
    """
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    opponent_id: Optional[str] = None
    subject_type: Optional[str] = None
    opponent_type: Optional[str] = None
    names: dict[str, str] = field(default_factory=dict)  # role -> display name

    def org_key(self, entity_id: Optional[str], entity_type: Optional[str]) -> Optional[str]:
        """How an org or unmapped team id is keyed in the fact views.

        None when there is no entity: the old version turned a missing team into
        the literal key "team:None", which is a filter nothing matches, so every
        player record and K/D question quietly returned no_data.
        """
        if not entity_id:
            return None
        return entity_id if entity_type == "org" else f"team:{entity_id}"


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
            sql="SELECT season, stat_key, stat_kind, rows_with_stat, rows_total, coverage_pct, "
                f"championships_with_stat, championships_total FROM stat_coverage_season{where} "
                "ORDER BY season, stat_key",
            params=params, description="stat availability per season", coverage_stat=None, sample_columns=("rows_total",),
        )

    # ------------------------------------------------------------------ versus
    # Map grain: the question "map record against X" is about maps, not series.
    if q.intent == "versus":
        if not (r.opponent_id and (r.player_id or r.team_id)):
            return Unanswerable(code="invalid_query", reason="a versus question needs both sides resolved")
        subject_is_player = r.subject_type == "player"
        opponent_is_player = r.opponent_type == "player"
        clauses, params = [], []
        _where(clauses, params, "season", f.season)
        _where(clauses, params, "championship_id", champ)
        _where(clauses, params, "map_name", v.map_name)
        _where(clauses, params, "game_mode", v.mode_name)

        if subject_is_player and opponent_is_player:
            head = ["player_id = %s", "opponent_player_id = %s"]
            lead = [r.player_id, r.opponent_id]
            table, desc = "fact_player_versus", "player vs player, map grain"
        elif subject_is_player and not opponent_is_player:
            head = ["player_id = %s", "opponent_org_key = %s"]
            lead = [r.player_id, r.org_key(r.opponent_id, r.opponent_type)]
            table, desc = "fact_player_versus", "player vs org, map grain"
        elif not subject_is_player and opponent_is_player:
            head = ["opponent_org_key = %s", "player_id = %s"]
            lead = [r.org_key(r.team_id, r.subject_type), r.opponent_id]
            table, desc = "fact_player_versus", "org vs player, map grain"
        else:
            head = ["org_key = %s", "opponent_org_key = %s"]
            lead = [r.org_key(r.team_id, r.subject_type), r.org_key(r.opponent_id, r.opponent_type)]
            table, desc = "fact_team_maps", "org vs org, map grain"

        if table == "fact_player_versus" and not (subject_is_player and opponent_is_player):
            # one row per map, not per opposing player, or a map counts five times
            distinct = "DISTINCT (match_id, round_number)"
        else:
            distinct = None
        where = " WHERE " + " AND ".join(head + clauses)
        if table == "fact_player_versus":
            base = (f"SELECT DISTINCT match_id, round_number, season, map_name, game_mode, won, drawn, started_at "
                    f"FROM {table}{where}") if distinct else (
                   f"SELECT match_id, round_number, season, map_name, game_mode, won, drawn, started_at "
                   f"FROM {table}{where}")
        else:
            base = (f"SELECT match_id, round_number, season, map_name, game_mode, won, drawn, started_at "
                    f"FROM {table}{where}")
        sql = (
            "WITH m AS (" + base + ") "
            "SELECT %s AS subject, %s AS opponent, "
            "count(*) AS maps, count(DISTINCT match_id) AS matches, "
            "count(*) FILTER (WHERE won) AS map_wins, "
            "count(*) FILTER (WHERE NOT won AND NOT drawn) AS map_losses, "
            "count(*) FILTER (WHERE drawn) AS draws, "
            "round(100.0 * count(*) FILTER (WHERE won) / nullif(count(*), 0), 1) AS map_win_pct, "
            "array_agg(DISTINCT season ORDER BY season) AS seasons, "
            "min(started_at) AS first_map_at, max(started_at) AS last_map_at "
            "FROM m"
        )
        return Compiled(sql=sql, params=lead + params + [r.names.get("subject") or r.names.get("player") or r.names.get("team"),
                                                          r.names.get("opponent")],
                        description=desc, coverage_season=f.season, coverage_championship=single_champ,
                        sample_columns=("maps", "matches"))

    # ------------------------------------------------- one entity, two seasons
    if q.intent == "season_compare":
        if not (r.team_id or r.player_id):
            return Unanswerable(code="invalid_query", reason="a season comparison needs the entity resolved")
        seasons = [f.subject_season, f.opponent_season]
        if not all(seasons):
            return Unanswerable(code="invalid_query", reason="a season comparison needs a season on each side")
        if r.player_id and r.subject_type == "player":
            sql = ("SELECT season, %s AS entity, count(*) AS maps, count(DISTINCT match_id) AS matches, "
                   "count(*) FILTER (WHERE map_won) AS map_wins, "
                   "count(*) FILTER (WHERE NOT map_won AND NOT map_drawn) AS map_losses, "
                   "round(100.0 * count(*) FILTER (WHERE map_won) / nullif(count(*), 0), 1) AS map_win_pct, "
                   "sum(eliminations) AS eliminations, sum(deaths) AS deaths, "
                   "round(sum(eliminations)::numeric / nullif(sum(deaths), 0), 2) AS kd_ratio, "
                   "min(started_at) AS first_map_at, max(started_at) AS last_map_at "
                   "FROM fact_player_maps WHERE player_id = %s AND season = ANY(%s) GROUP BY season ORDER BY season")
            params = [r.names.get("subject") or r.names.get("player"), r.player_id, seasons]
        else:
            sql = ("SELECT season, %s AS entity, count(*) AS maps, count(DISTINCT match_id) AS matches, "
                   "count(*) FILTER (WHERE won) AS map_wins, "
                   "count(*) FILTER (WHERE NOT won AND NOT drawn) AS map_losses, "
                   "round(100.0 * count(*) FILTER (WHERE won) / nullif(count(*), 0), 1) AS map_win_pct, "
                   "sum(score) AS points_for, sum(opp_score) AS points_against, "
                   "min(started_at) AS first_map_at, max(started_at) AS last_map_at "
                   "FROM fact_team_maps WHERE org_key = %s AND season = ANY(%s) GROUP BY season ORDER BY season")
            params = [r.names.get("subject") or r.names.get("team"), r.org_key(r.team_id, r.subject_type), seasons]
        return Compiled(sql=sql, params=params, description="the same entity compared across seasons",
                        sample_columns=("maps", "matches"))

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
            _where(clauses, params, "t.org_key", r.org_key(r.team_id, r.subject_type))
        _where(clauses, params, "t.season", f.season)
        _where(clauses, params, "t.championship_id", champ)
        _where(clauses, params, "t.region", f.region)
        use_maps = bool(v.map_name or v.mode_name) or q.metric in ("map_wins", "map_losses", "map_win_rate", "maps")
        if use_maps:
            _where(clauses, params, "t.map_name", v.map_name)
            _where(clauses, params, "t.game_mode", v.mode_name)
            select = ("t.org_key, t.display_name AS team, sum(t.maps) AS maps, sum(t.matches) AS matches, sum(t.wins) AS map_wins, "
                      "sum(t.losses) AS map_losses, sum(t.draws) AS draws, "
                      "round(100.0 * sum(t.wins) / nullif(sum(t.maps), 0), 1) AS map_win_pct, "
                      "array_agg(DISTINCT t.season ORDER BY t.season) AS seasons")
            table, order_key = "agg_team_maps", {"map_win_rate": "map_win_pct", "map_wins": "map_wins", "map_losses": "map_losses"}.get(q.metric, "maps")
        else:
            select = ("t.org_key, t.display_name AS team, sum(t.matches) AS matches, sum(t.wins) AS wins, sum(t.losses) AS losses, "
                      "sum(t.map_wins) AS map_wins, sum(t.map_losses) AS map_losses, sum(t.maps) AS maps, "
                      "round(100.0 * sum(t.wins) / nullif(sum(t.matches), 0), 1) AS win_pct, "
                      "min(t.first_match_at) AS first_match_at, max(t.last_match_at) AS last_match_at, "
                      "array_agg(DISTINCT t.season ORDER BY t.season) AS seasons")
            table, order_key = "agg_team_matches", {"win_rate": "win_pct", "wins": "wins", "losses": "losses", "matches": "matches"}.get(q.metric, "win_pct")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT {select} FROM {table} t{where} GROUP BY t.org_key, t.display_name"
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
            _where(clauses, params, "org_key", r.org_key(r.team_id, r.subject_type))
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
            _where(clauses, params, "a.org_key", r.org_key(r.team_id, r.subject_type))
        _where(clauses, params, "a.season", f.season)
        _where(clauses, params, "a.championship_id", champ)
        _where(clauses, params, "a.region", f.region)
        _where(clauses, params, "a.map_name", v.map_name)
        _where(clauses, params, "a.game_mode", v.mode_name)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (f"SELECT a.org_key, coalesce(ti.display_name, a.org_key) AS team, sum(a.sum_{col}) AS total, "
               f"sum(a.maps_with_{col}) AS player_map_rows, "
               f"round(sum(a.sum_{col}) / nullif(sum(a.maps_with_{col}), 0), 1) AS avg_per_player_map, "
               f"array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
               f"FROM agg_player_stats a LEFT JOIN identity_keys ti ON ti.org_key = a.org_key{where} "
               f"GROUP BY a.org_key, ti.display_name")
        if q.intent == "leaderboard":
            sql += f" HAVING sum(a.maps_with_{col}) >= %s ORDER BY {'avg_per_player_map' if q.aggregation == 'avg_per_map' else 'total'} {_dir(q.sort)} NULLS LAST LIMIT %s"
            params += [q.min_maps, q.limit]
        return Compiled(sql=sql, params=params, description=f"team {stat}", coverage_stat=stat, coverage_season=f.season,
                        coverage_championship=single_champ, sample_columns=("player_map_rows",))

    if q.metric == "kd_ratio" or (q.metric in ("maps", "matches", "map_wins", "map_losses", "map_win_rate", "wins", "losses") and q.entity == "player"):
        clauses, params = [], []
        alias = "fp" if f.role else "a"
        if q.intent == "entity_stat":
            if not r.player_id:
                return Unanswerable(code="invalid_query", reason="needs a resolved player")
            _where(clauses, params, f"{alias}.player_id", r.player_id)
        _where(clauses, params, f"{alias}.season", f.season)
        _where(clauses, params, f"{alias}.championship_id", champ)
        _where(clauses, params, f"{alias}.region", f.region)
        _where(clauses, params, f"{alias}.org_key", r.org_key(r.team_id, r.subject_type))
        _where(clauses, params, f"{alias}.map_name", v.map_name)
        _where(clauses, params, f"{alias}.game_mode", v.mode_name)
        _where(clauses, params, f"{alias}.role", f.role)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        if f.role:
            # fact_player_maps has role but no pre-aggregated sums; the same
            # shape, computed from the raw rows instead of agg_player_stats.
            sql = ("SELECT fp.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, count(*) AS maps, count(*) FILTER (WHERE fp.map_won) AS map_wins, "
                   "count(*) FILTER (WHERE NOT fp.map_won AND NOT fp.map_drawn) AS map_losses, "
                   "round(100.0 * count(*) FILTER (WHERE fp.map_won) / nullif(count(*), 0), 1) AS map_win_pct, "
                   "sum(fp.eliminations) AS eliminations, sum(fp.deaths) AS deaths, "
                   "round(sum(fp.eliminations)::numeric / nullif(sum(fp.deaths), 0), 2) AS kd_ratio, "
                   "array_agg(DISTINCT fp.season ORDER BY fp.season) AS seasons "
                   f"FROM fact_player_maps fp JOIN players p ON p.player_id = fp.player_id{where} GROUP BY fp.player_id, player_display_name(p.nickname, p.game_player_name)")
        else:
            # No sum(a.matches) here: the aggregate is grouped per map and mode, so a
            # series would be counted once per map played in it.
            sql = ("SELECT a.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, sum(a.maps) AS maps, sum(a.maps_won) AS map_wins, "
                   "sum(a.maps) - sum(a.maps_won) - sum(a.maps_drawn) AS map_losses, "
                   "round(100.0 * sum(a.maps_won) / nullif(sum(a.maps), 0), 1) AS map_win_pct, "
                   "sum(a.sum_eliminations) AS eliminations, sum(a.sum_deaths) AS deaths, "
                   "round(sum(a.sum_eliminations)::numeric / nullif(sum(a.sum_deaths), 0), 2) AS kd_ratio, "
                   "array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
                   f"FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id{where} GROUP BY a.player_id, player_display_name(p.nickname, p.game_player_name)")
        order_key = {"kd_ratio": "kd_ratio", "maps": "maps", "matches": "matches", "map_wins": "map_wins", "map_losses": "map_losses",
                     "map_win_rate": "map_win_pct", "wins": "map_wins", "losses": "map_losses"}[q.metric]
        if q.intent == "leaderboard":
            sql += f" HAVING count(*) >= %s ORDER BY {order_key} {_dir(q.sort)} NULLS LAST, maps DESC LIMIT %s" if f.role else \
                   f" HAVING sum(a.maps) >= %s ORDER BY {order_key} {_dir(q.sort)} NULLS LAST, maps DESC LIMIT %s"
            params += [q.min_maps, q.limit]
        return Compiled(sql=sql, params=params, description=f"player {q.metric}" + (f" ({f.role})" if f.role else ""),
                        coverage_stat="Eliminations" if q.metric == "kd_ratio" else None,
                        coverage_season=f.season, coverage_championship=single_champ)

    if not stat:
        return Unanswerable(code="unsupported_metric", reason=f"cannot compute '{q.metric}' for {q.entity}")

    sliced = bool(v.map_name or v.mode_name or r.team_id or f.region)
    has_role = f.role is not None
    order_expr = "avg_per_map" if q.aggregation == "avg_per_map" else "total"

    if q.intent == "entity_stat":
        if not r.player_id:
            return Unanswerable(code="invalid_query", reason="needs a resolved player")
        if sliced or has_role:
            # agg_player_stat_long and agg_player_stats carry no role column, so a
            # role filter always reads the raw per-map rows instead. validate.py
            # guarantees `col` is set (a typed stat) whenever role is present.
            alias = "fp" if has_role else "a"
            clauses, params = [f"{alias}.player_id = %s"], [r.player_id]
            _where(clauses, params, f"{alias}.season", f.season)
            _where(clauses, params, f"{alias}.championship_id", champ)
            _where(clauses, params, f"{alias}.region", f.region)
            _where(clauses, params, f"{alias}.org_key", r.org_key(r.team_id, r.subject_type))
            _where(clauses, params, f"{alias}.map_name", v.map_name)
            _where(clauses, params, f"{alias}.game_mode", v.mode_name)
            _where(clauses, params, f"{alias}.role", f.role)
            if has_role:
                sql = (f"SELECT fp.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, count(fp.{col}) AS maps_with_stat, count(*) AS maps_played, "
                       f"round(100.0 * count(fp.{col}) / nullif(count(*), 0), 1) AS coverage_pct, "
                       f"sum(fp.{col}) AS total, round(sum(fp.{col}) / nullif(count(fp.{col}), 0), 2) AS avg_per_map, "
                       "array_agg(DISTINCT fp.season ORDER BY fp.season) AS seasons "
                       f"FROM fact_player_maps fp JOIN players p ON p.player_id = fp.player_id "
                       f"WHERE {' AND '.join(clauses)} GROUP BY fp.player_id, player_display_name(p.nickname, p.game_player_name)")
            else:
                sql = (f"SELECT a.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, sum(a.maps_with_{col}) AS maps_with_stat, sum(a.maps) AS maps_played, "
                       f"round(100.0 * sum(a.maps_with_{col}) / nullif(sum(a.maps), 0), 1) AS coverage_pct, "
                       f"sum(a.sum_{col}) AS total, round(sum(a.sum_{col}) / nullif(sum(a.maps_with_{col}), 0), 2) AS avg_per_map, "
                       "array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
                       f"FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id WHERE {' AND '.join(clauses)} GROUP BY a.player_id, player_display_name(p.nickname, p.game_player_name)")
        else:
            clauses, params = ["l.player_id = %s", "l.stat_key = %s"], [r.player_id, stat]
            _where(clauses, params, "l.season", f.season)
            _where(clauses, params, "l.championship_id", champ)
            s_clauses, s_params = ["s.player_id = %s"], [r.player_id]
            _where(s_clauses, s_params, "s.season", f.season)
            _where(s_clauses, s_params, "s.championship_id", champ)
            sql = ("WITH played AS (SELECT s.player_id, sum(s.maps) AS maps_played FROM agg_player_stats s WHERE "
                   + " AND ".join(s_clauses) + " GROUP BY s.player_id) "
                   "SELECT l.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, sum(l.maps_with_stat) AS maps_with_stat, max(played.maps_played) AS maps_played, "
                   "round(100.0 * sum(l.maps_with_stat) / nullif(max(played.maps_played), 0), 1) AS coverage_pct, "
                   "sum(l.total) AS total, round(sum(l.total) / nullif(sum(l.maps_with_stat), 0), 2) AS avg_per_map, "
                   "min(l.min_per_map) AS min_per_map, max(l.max_per_map) AS max_per_map, "
                   "array_agg(DISTINCT l.season ORDER BY l.season) AS seasons "
                   "FROM agg_player_stat_long l JOIN players p ON p.player_id = l.player_id "
                   "LEFT JOIN played ON played.player_id = l.player_id WHERE " + " AND ".join(clauses) + " GROUP BY l.player_id, player_display_name(p.nickname, p.game_player_name)")
            params = s_params + params  # the CTE's placeholders come first in the statement
        return Compiled(sql=sql, params=params, description=f"{stat} for one player", coverage_stat=stat,
                        coverage_season=f.season, coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))

    # leaderboard over a stat key
    if not sliced and not has_role and len(champ or []) <= 1:
        # reuse the SQL function; asc sort needs a wrapper because the function ranks descending
        if q.sort == "asc":
            sql = (f"SELECT * FROM stat_leaderboard(%s, %s, %s, %s, 10000, %s) ORDER BY {order_expr} ASC NULLS LAST LIMIT %s")
            params = [stat, f.season, single_champ, q.min_maps, "avg" if q.aggregation == "avg_per_map" else "total", q.limit]
        else:
            sql = "SELECT * FROM stat_leaderboard(%s, %s, %s, %s, %s, %s)"
            params = [stat, f.season, single_champ, q.min_maps, q.limit, "avg" if q.aggregation == "avg_per_map" else "total"]
        return Compiled(sql=sql, params=params, description=f"{stat} leaderboard", coverage_stat=stat, coverage_season=f.season,
                        coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))

    if not sliced and has_role and len(champ or []) <= 1:
        # role-only (no map/mode/team/region): still the fast SQL-function path,
        # generic over any numeric stat key, just with p_role passed through.
        if q.sort == "asc":
            sql = (f"SELECT * FROM stat_leaderboard(%s, %s, %s, %s, 10000, %s, %s) ORDER BY {order_expr} ASC NULLS LAST LIMIT %s")
            params = [stat, f.season, single_champ, q.min_maps, "avg" if q.aggregation == "avg_per_map" else "total", f.role, q.limit]
        else:
            sql = "SELECT * FROM stat_leaderboard(%s, %s, %s, %s, %s, %s, %s)"
            params = [stat, f.season, single_champ, q.min_maps, q.limit, "avg" if q.aggregation == "avg_per_map" else "total", f.role]
        return Compiled(sql=sql, params=params, description=f"{stat} leaderboard ({f.role})", coverage_stat=stat, coverage_season=f.season,
                        coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))

    if not col:
        reason = f"'{stat}' cannot be sliced by map/mode/team/region"
        if has_role:
            reason = f"'{stat}' cannot be filtered by role; role is only tracked for these stats: {', '.join(TYPED_STATS)}"
        return Unanswerable(code="unsupported_metric", reason=reason)
    # agg_player_stats has no role column, so a role filter reads the raw
    # per-map rows instead (fact_player_maps), everything else unchanged.
    alias = "fp" if has_role else "a"
    clauses, params = [], []
    _where(clauses, params, f"{alias}.season", f.season)
    _where(clauses, params, f"{alias}.championship_id", champ)
    _where(clauses, params, f"{alias}.region", f.region)
    _where(clauses, params, f"{alias}.org_key", r.org_key(r.team_id, r.subject_type))
    _where(clauses, params, f"{alias}.map_name", v.map_name)
    _where(clauses, params, f"{alias}.game_mode", v.mode_name)
    _where(clauses, params, f"{alias}.role", f.role)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    if has_role:
        sql = (f"SELECT fp.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, count(fp.{col}) AS maps_with_stat, count(*) AS maps_played, "
               f"round(100.0 * count(fp.{col}) / nullif(count(*), 0), 1) AS coverage_pct, "
               f"sum(fp.{col}) AS total, round(sum(fp.{col}) / nullif(count(fp.{col}), 0), 2) AS avg_per_map, "
               "array_agg(DISTINCT fp.season ORDER BY fp.season) AS seasons "
               f"FROM fact_player_maps fp JOIN players p ON p.player_id = fp.player_id{where} GROUP BY fp.player_id, player_display_name(p.nickname, p.game_player_name) "
               f"HAVING count(fp.{col}) >= %s ORDER BY {order_expr} {_dir(q.sort)} NULLS LAST, maps_with_stat DESC LIMIT %s")
    else:
        sql = (f"SELECT a.player_id, player_display_name(p.nickname, p.game_player_name) AS nickname, sum(a.maps_with_{col}) AS maps_with_stat, sum(a.maps) AS maps_played, "
               f"round(100.0 * sum(a.maps_with_{col}) / nullif(sum(a.maps), 0), 1) AS coverage_pct, "
               f"sum(a.sum_{col}) AS total, round(sum(a.sum_{col}) / nullif(sum(a.maps_with_{col}), 0), 2) AS avg_per_map, "
               "array_agg(DISTINCT a.season ORDER BY a.season) AS seasons "
               f"FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id{where} GROUP BY a.player_id, player_display_name(p.nickname, p.game_player_name) "
               f"HAVING sum(a.maps_with_{col}) >= %s ORDER BY {order_expr} {_dir(q.sort)} NULLS LAST, maps_with_stat DESC LIMIT %s")
    params += [q.min_maps, q.limit]
    return Compiled(sql=sql, params=params, description=f"{stat} leaderboard (sliced)" + (f" ({f.role})" if f.role else ""),
                    coverage_stat=stat, coverage_season=f.season,
                    coverage_championship=single_champ, sample_columns=("maps_with_stat", "maps_played"))
