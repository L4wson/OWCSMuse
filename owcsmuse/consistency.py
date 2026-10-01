"""Warehouse invariants, asserted against the live database.

Four bugs in this project had the same shape: a join or key mismatch that
returned a plausible, smaller answer instead of failing. A NULL season made a
coverage join false and erased rows; `started_at` was NULL for 30 matches and
every date-keyed view dropped them; the team aggregates stayed keyed on
`team_id` after the resolver began returning org ids; and two org merges joined
an NA roster to an EMEA one, so a player's record showed another region's
matches. None of them raised anything. Each produced a wrong answer that looked exactly like a right one.

These checks exist to make that class of failure loud. They are deliberately not
fixture tests: they run against whatever data is loaded and reconcile each
derived object against the source it claims to summarise, so a stale
materialized view, a silently dropped row or an unreachable stat becomes a
failure with the specific discrepancy attached.

    python -m owcsmuse check

Exit status is 1 when any check fails.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

import psycopg

from .log import get_logger, log_event

log = get_logger("owcsmuse.consistency")

# Counters carried on both agg_player_stats and fact_player_maps. Hardcoded
# names, never interpolated from data.
COUNTABLE_COLUMNS: tuple[str, ...] = (
    "eliminations", "final_blows", "deaths", "assists", "solo_kills", "multi_kills",
    "environmental_kills", "damage_dealt", "healing_done", "damage_mitigated",
    "objective_time", "time_played",
)

MAX_DISCREPANCIES = 20  # shown per check; the count is always exact


@dataclass
class CheckResult:
    name: str
    ok: bool
    summary: str
    counts: dict[str, Any] = field(default_factory=dict)
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    discrepancy_count: int = 0
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rows(conn: psycopg.Connection, sql: str, params: Optional[list] = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        # params stays None when there are none: an empty sequence makes psycopg
        # parse the statement for placeholders, and these queries contain LIKE '%'.
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _scalar(conn: psycopg.Connection, sql: str, params: Optional[list] = None) -> Any:
    rows = _rows(conn, sql, params)
    return list(rows[0].values())[0] if rows else None


def _result(name: str, discrepancies: list[dict[str, Any]], summary_ok: str, summary_bad: str,
            counts: dict[str, Any]) -> CheckResult:
    ok = not discrepancies
    return CheckResult(name=name, ok=ok, summary=summary_ok if ok else summary_bad, counts=counts,
                       discrepancies=discrepancies[:MAX_DISCREPANCIES], discrepancy_count=len(discrepancies))


# --------------------------------------------------------------- 1. fact views

# Each fact view with the count its source tables say it must have. The
# expressions mirror the view's own WHERE clause; if the two drift, that drift
# is the bug being looked for.
_FACT_EXPECTATIONS: tuple[tuple[str, str, str], ...] = (
    ("fact_player_maps", "one row per player per map played",
     """SELECT count(*) FROM match_players mp
          JOIN matches m ON m.match_id = mp.match_id
          JOIN championships c ON c.championship_id = m.championship_id
         WHERE m.ingest_state = 'complete' AND c.include"""),
    ("fact_team_maps", "two rows per map, one per side",
     """SELECT coalesce(sum((r.team1_team_id IS NOT NULL)::int + (r.team2_team_id IS NOT NULL)::int), 0)
          FROM match_rounds r
          JOIN matches m ON m.match_id = r.match_id
          JOIN championships c ON c.championship_id = m.championship_id
         WHERE m.ingest_state IN ('complete', 'result_only') AND c.include"""),
    ("fact_team_matches", "two rows per finished series, one per side",
     """SELECT coalesce(sum((m.faction1_team_id IS NOT NULL)::int + (m.faction2_team_id IS NOT NULL)::int), 0)
          FROM matches m
          JOIN championships c ON c.championship_id = m.championship_id
         WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include"""),
    ("fact_player_versus", "one row per player per map per opposing player",
     """WITH per AS (
            SELECT match_id, round_number, team_id, count(*) AS n
              FROM fact_player_maps GROUP BY match_id, round_number, team_id
        ), tot AS (
            SELECT match_id, round_number, sum(n) AS total, sum(n * n) AS same_side
              FROM per GROUP BY match_id, round_number
        ) SELECT coalesce(sum(total * total - same_side), 0) FROM tot"""),
)


def check_fact_view_reconciliation(conn: psycopg.Connection) -> CheckResult:
    """Every fact view's row count reconciles against its source table."""
    discrepancies: list[dict[str, Any]] = []
    counts: dict[str, Any] = {}
    for view, grain, expected_sql in _FACT_EXPECTATIONS:
        expected = int(_scalar(conn, expected_sql) or 0)
        actual = int(_scalar(conn, f"SELECT count(*) FROM {view}") or 0)
        counts[view] = {"expected": expected, "actual": actual, "grain": grain}
        if expected != actual:
            d: dict[str, Any] = {"view": view, "grain": grain, "expected": expected, "actual": actual,
                                 "difference": actual - expected}
            if view == "fact_player_maps" and actual < expected:
                # the usual cause: a player row whose map has no match_rounds row,
                # dropped by an inner join that behaves like an unannounced filter
                d["orphan_player_rows"] = _rows(conn, """
                    SELECT mp.match_id, mp.round_number, count(*) AS player_rows
                      FROM match_players mp
                      JOIN matches m ON m.match_id = mp.match_id
                      JOIN championships c ON c.championship_id = m.championship_id
                      LEFT JOIN match_rounds r ON (r.match_id, r.round_number) = (mp.match_id, mp.round_number)
                     WHERE m.ingest_state = 'complete' AND c.include AND r.match_id IS NULL
                     GROUP BY mp.match_id, mp.round_number LIMIT 10""")
            if view == "fact_player_versus":
                d["hint"] = "a materialized view: run `python -m owcsmuse refresh` before treating this as a bug"
            discrepancies.append(d)
    return _result("fact_view_reconciliation", discrepancies,
                   f"{len(_FACT_EXPECTATIONS)} fact views reconcile against their source tables",
                   f"{len(discrepancies)} fact view(s) do not match their source tables", counts)


# ------------------------------------------------------------ 2. date visibility

def check_date_visibility(conn: psycopg.Connection) -> CheckResult:
    """No match is invisible to any date-keyed view.

    `match_time()` is the single definition of when a match happened. A match in
    scope with no usable time, or a fact row with a NULL date, drops out of every
    season and date filter without raising anything.
    """
    discrepancies: list[dict[str, Any]] = []
    undated = _rows(conn, """
        SELECT m.match_id, m.championship_id, m.ingest_state
          FROM matches m JOIN championships c ON c.championship_id = m.championship_id
         WHERE c.include AND m.status = 'FINISHED' AND m.ingest_state IN ('complete', 'result_only')
           AND match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) IS NULL""")
    for r in undated:
        discrepancies.append({"kind": "match_with_no_usable_time", **r})

    for view in ("fact_team_matches", "fact_team_maps", "fact_player_maps"):
        n = int(_scalar(conn, f"SELECT count(*) FROM {view} WHERE started_at IS NULL") or 0)
        if n:
            discrepancies.append({"kind": "fact_rows_with_null_date", "view": view, "rows": n})

    missing = _rows(conn, """
        SELECT m.match_id, m.championship_id, m.ingest_state,
               m.faction1_team_id, m.faction2_team_id
          FROM matches m JOIN championships c ON c.championship_id = m.championship_id
         WHERE c.include AND m.status = 'FINISHED' AND m.ingest_state IN ('complete', 'result_only')
           AND NOT EXISTS (SELECT 1 FROM fact_team_matches f WHERE f.match_id = m.match_id)""")
    for r in missing:
        discrepancies.append({"kind": "finished_match_absent_from_fact_team_matches", **r})

    counts = {
        "matches_in_scope": int(_scalar(conn, """
            SELECT count(*) FROM matches m JOIN championships c ON c.championship_id = m.championship_id
             WHERE c.include AND m.status = 'FINISHED' AND m.ingest_state IN ('complete', 'result_only')""") or 0),
        "matches_dated_only_by_fallback": int(_scalar(conn, """
            SELECT count(*) FROM matches m JOIN championships c ON c.championship_id = m.championship_id
             WHERE c.include AND m.status = 'FINISHED' AND m.ingest_state IN ('complete', 'result_only')
               AND m.started_at IS NULL""") or 0),
    }
    return _result("date_visibility", discrepancies,
                   f"all {counts['matches_in_scope']} in-scope matches are dated and visible to the date-keyed views"
                   + (f" ({counts['matches_dated_only_by_fallback']} of them only via the match_time() fallback)"
                      if counts["matches_dated_only_by_fallback"] else ""),
                   f"{len(discrepancies)} date-visibility problem(s)", counts)


# ------------------------------------------------------------ 3. org resolution

def check_org_key_resolution(conn: psycopg.Connection) -> CheckResult:
    """Every team id resolves to an org key, and unmapped ids are counted, not hidden.

    An unmapped team id is not a failure: it keys as `team:<id>` and stays
    queryable as itself. A NULL org_key is a failure, because it means a team id
    in play is missing from `teams` and disappears from every org-level grouping.
    """
    discrepancies: list[dict[str, Any]] = []
    for view in ("fact_team_matches", "fact_team_maps", "fact_player_maps"):
        rows = _rows(conn, f"""
            SELECT DISTINCT team_id FROM {view} WHERE org_key IS NULL AND team_id IS NOT NULL LIMIT 20""")
        if rows:
            discrepancies.append({"kind": "null_org_key", "view": view,
                                  "team_ids": [r["team_id"] for r in rows]})
    unknown = _rows(conn, """
        SELECT DISTINCT t.team_id
          FROM matches m
          JOIN championships c ON c.championship_id = m.championship_id
          CROSS JOIN LATERAL (VALUES (m.faction1_team_id), (m.faction2_team_id)) AS t(team_id)
         WHERE c.include AND t.team_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM teams x WHERE x.team_id = t.team_id)""")
    for r in unknown:
        discrepancies.append({"kind": "team_id_played_but_absent_from_teams", **r})
    for r in _rows(conn, "SELECT org_id FROM orgs WHERE org_id LIKE 'team:%'"):
        discrepancies.append({"kind": "org_id_collides_with_unmapped_key_prefix", **r})
    # A materialized aggregate keeps the org_key it was built with. After a merge
    # (or a window) is decided and loaded, an unrefreshed aggregate still answers
    # at the old identity, which reads as a complete answer for a team that no
    # longer exists. Identity is per series time, so the comparison is against
    # the fact view the aggregate was built from: every (team_id, org_key) the
    # aggregate carries must still occur there.
    for view, fact in (("agg_team_matches", "fact_team_matches"), ("agg_team_maps", "fact_team_maps"),
                       ("agg_player_stats", "fact_player_maps")):
        stale = _rows(conn, f"""
            SELECT a.team_id, a.org_key AS aggregate_org_key,
                   (SELECT array_agg(DISTINCT f.org_key) FROM {fact} f WHERE f.team_id = a.team_id) AS current_org_keys
              FROM (SELECT DISTINCT team_id, org_key FROM {view}) a
             WHERE NOT EXISTS (SELECT 1 FROM {fact} f WHERE f.team_id = a.team_id AND f.org_key = a.org_key)
             LIMIT 20""")
        for r in stale:
            discrepancies.append({"kind": "stale_org_key_in_materialized_view", "view": view, **r,
                                  "hint": "run `python -m owcsmuse refresh` after loading org decisions"})

    counts = {
        "orgs": int(_scalar(conn, "SELECT count(*) FROM orgs") or 0),
        "team_ids_total": int(_scalar(conn, "SELECT count(*) FROM team_identity") or 0),
        "team_ids_mapped": int(_scalar(conn, "SELECT count(*) FROM team_identity WHERE mapped") or 0),
        "team_ids_unmapped": int(_scalar(conn, "SELECT count(*) FROM team_identity WHERE NOT mapped") or 0),
        "unmapped_team_ids_with_matches": int(_scalar(conn, """
            SELECT count(DISTINCT team_id) FROM fact_team_matches WHERE org_key LIKE 'team:%'""") or 0),
        "bounded_windows": int(_scalar(conn, """
            SELECT count(*) FROM team_orgs WHERE valid_from <> '-infinity' OR valid_to <> 'infinity'""") or 0),
    }
    return _result("org_key_resolution", discrepancies,
                   f"{counts['team_ids_total']} team ids all resolve: {counts['team_ids_mapped']} mapped to "
                   f"{counts['orgs']} orgs, {counts['team_ids_unmapped']} unmapped and queryable as themselves "
                   f"({counts['unmapped_team_ids_with_matches']} of those have matches)",
                   f"{len(discrepancies)} team identity problem(s)", counts)


# ------------------------------------------------------------- 4. aggregate sums

def check_aggregate_sums(conn: psycopg.Connection) -> CheckResult:
    """Aggregate sums match source sums, per stat, per season.

    Covers both shapes an aggregate takes here: the wide counters on
    `agg_player_stats` and the long format's per-key totals. A stale
    materialized view or a GROUP BY that lost a key surfaces as an exact numeric
    difference for one season.
    """
    discrepancies: list[dict[str, Any]] = []

    wide_cols = ", ".join(f"sum(sum_{c}) AS {c}" for c in COUNTABLE_COLUMNS)
    src_cols = ", ".join(f"sum({c}) AS {c}" for c in COUNTABLE_COLUMNS)
    agg = {r["season"]: r for r in _rows(conn, f"SELECT season, {wide_cols} FROM agg_player_stats GROUP BY season")}
    src = {r["season"]: r for r in _rows(conn, f"SELECT season, {src_cols} FROM fact_player_maps GROUP BY season")}
    for season in sorted(set(agg) | set(src), key=lambda s: (s is None, s)):
        a, b = agg.get(season, {}), src.get(season, {})
        for col in COUNTABLE_COLUMNS:
            av, bv = a.get(col), b.get(col)
            if (av or 0) != (bv or 0):
                discrepancies.append({"kind": "agg_player_stats_sum", "season": season, "stat": col,
                                      "aggregate": str(av), "source": str(bv)})

    long_rows = {(r["season"], r["stat_key"]): r["total"] for r in _rows(conn, """
        SELECT season, stat_key, sum(total) AS total FROM agg_player_stat_long
         WHERE stat_kind = 'countable' GROUP BY season, stat_key""")}
    src_rows = {(r["season"], r["stat_key"]): r["total"] for r in _rows(conn, """
        SELECT f.season, kv.key AS stat_key, sum(stat_num(kv.value)) AS total
          FROM fact_player_maps f CROSS JOIN LATERAL jsonb_each_text(f.stats) AS kv
         WHERE stat_num(kv.value) IS NOT NULL AND stat_kind(kv.key) = 'countable'
         GROUP BY f.season, kv.key""")}
    for key in sorted(set(long_rows) | set(src_rows), key=lambda k: (k[0] is None, k[0], k[1])):
        a_total, b_total = long_rows.get(key), src_rows.get(key)
        if (a_total or Decimal(0)) != (b_total or Decimal(0)):
            discrepancies.append({"kind": "agg_player_stat_long_total", "season": key[0], "stat": key[1],
                                  "aggregate": str(a_total), "source": str(b_total)})

    for agg_view, agg_expr, fact_view in (("agg_team_maps", "sum(maps)", "fact_team_maps"),
                                          ("agg_team_matches", "sum(matches)", "fact_team_matches"),
                                          ("agg_player_stats", "sum(maps)", "fact_player_maps")):
        a_rows = {r["season"]: r["n"] for r in
                  _rows(conn, f"SELECT season, {agg_expr} AS n FROM {agg_view} GROUP BY season")}
        b_rows = {r["season"]: r["n"] for r in
                  _rows(conn, f"SELECT season, count(*) AS n FROM {fact_view} GROUP BY season")}
        for season in sorted(set(a_rows) | set(b_rows), key=lambda s: (s is None, s)):
            if (a_rows.get(season) or 0) != (b_rows.get(season) or 0):
                discrepancies.append({"kind": "row_count_per_season", "season": season, "aggregate_view": agg_view,
                                      "aggregate": str(a_rows.get(season)), "source_view": fact_view,
                                      "source": str(b_rows.get(season))})

    counts = {"seasons": sorted(s for s in set(agg) | set(src) if s is not None),
              "stat_columns": len(COUNTABLE_COLUMNS), "long_format_pairs": len(src_rows)}
    return _result("aggregate_sums", discrepancies,
                   f"{len(COUNTABLE_COLUMNS)} counters and {len(src_rows)} season/stat pairs sum identically "
                   "in the aggregates and in the facts",
                   f"{len(discrepancies)} aggregate sum(s) disagree with the source", counts)


# --------------------------------------------------------- 5. stat reachability

def check_stat_reachability(conn: psycopg.Connection) -> CheckResult:
    """Every stat in stat_coverage_season is reachable by a leaderboard query.

    Availability a leaderboard cannot serve is a lie: the ask layer says the stat
    exists and then returns nothing. The other direction matters too, so a
    non-numeric label must return no rows at all.
    """
    rows = _rows(conn, """
        SELECT s.season, s.stat_key, s.stat_kind, s.rows_with_stat,
               (SELECT count(*) FROM stat_leaderboard(s.stat_key, s.season, NULL, 1, 1)) AS leaderboard_rows
          FROM stat_coverage_season s
         ORDER BY s.season, s.stat_key""")
    discrepancies: list[dict[str, Any]] = []
    for r in rows:
        if r["stat_kind"] == "non_numeric":
            if r["leaderboard_rows"]:
                discrepancies.append({"kind": "label_is_rankable", "season": r["season"], "stat": r["stat_key"],
                                      "leaderboard_rows": r["leaderboard_rows"]})
        elif not r["leaderboard_rows"]:
            discrepancies.append({"kind": "available_but_unreachable", "season": r["season"], "stat": r["stat_key"],
                                  "rows_with_stat": r["rows_with_stat"], "stat_kind": r["stat_kind"]})
    numeric = [r for r in rows if r["stat_kind"] != "non_numeric"]
    counts = {"season_stat_pairs": len(rows), "numeric_pairs": len(numeric),
              "non_numeric_pairs": len(rows) - len(numeric)}
    return _result("stat_reachability", discrepancies,
                   f"all {len(numeric)} available numeric season/stat pairs return a leaderboard, and "
                   f"{counts['non_numeric_pairs']} label pairs correctly return none",
                   f"{len(discrepancies)} stat(s) are advertised but not reachable", counts)


# ------------------------------------------------------------ 6. region locking

def check_region_consistency(conn: psycopg.Connection) -> CheckResult:
    """No org, and no team id, has matches in both `na` and `emea`.

    OWCS is region-locked: a competing roster plays one of them. The org proposer
    refuses cross-region merges (`orgs.region_conflict`), but that only guards
    merges proposed from now on. This audits what is applied and loaded: two
    wrong merges got through before the guard existed, and the symptom was one
    player's record showing another region's matches, a plausible answer that
    raised nothing. `international` events never count as a second region.

    Players are deliberately not checked: a player changes region by changing
    team, and 13 do in the real data.
    """
    discrepancies: list[dict[str, Any]] = []
    for key_col, kind in (("org_key", "org_spans_regions"), ("team_id", "team_id_spans_regions")):
        for r in _rows(conn, f"""
            SELECT {key_col} AS key, array_agg(DISTINCT region ORDER BY region) AS regions,
                   array_agg(DISTINCT team_id) AS team_ids, count(DISTINCT match_id) AS matches
              FROM fact_team_matches
             WHERE region IN ('na', 'emea') AND {key_col} IS NOT NULL
             GROUP BY {key_col} HAVING count(DISTINCT region) > 1"""):
            discrepancies.append({"kind": kind, "key": r["key"], "regions": r["regions"],
                                  "team_ids": r["team_ids"], "matches": r["matches"],
                                  "hint": "an applied org merge crosses regions: unmap it in scope/org_decisions.json "
                                          "and record a rejection, then reload and refresh"})
    counts = {
        "orgs_checked": int(_scalar(conn, "SELECT count(DISTINCT org_key) FROM fact_team_matches "
                                          "WHERE region IN ('na', 'emea')") or 0),
        "mapped_orgs_checked": int(_scalar(conn, "SELECT count(DISTINCT org_key) FROM fact_team_matches "
                                                 "WHERE region IN ('na', 'emea') AND org_key NOT LIKE 'team:%'") or 0),
        "team_ids_checked": int(_scalar(conn, "SELECT count(DISTINCT team_id) FROM fact_team_matches "
                                              "WHERE region IN ('na', 'emea')") or 0),
    }
    return _result("region_consistency", discrepancies,
                   f"none of {counts['orgs_checked']} orgs ({counts['mapped_orgs_checked']} merged) or "
                   f"{counts['team_ids_checked']} team ids has matches in both na and emea",
                   f"{len(discrepancies)} org(s) or team id(s) span na and emea", counts)


# ------------------------------------------------------------ identity windows

def check_identity_windows(conn: psycopg.Connection) -> CheckResult:
    """A team-to-org window says something about real series, and a team id is never two orgs at once.

    A window that covers none of its team id's series is a decision that silently
    does nothing - most likely a date typed wrong - and a series that falls in two
    windows would belong to two orgs; the trigger forbids the second, this audits
    the first and re-asserts the second against what is loaded.
    """
    discrepancies: list[dict[str, Any]] = []
    for r in _rows(conn, """
        SELECT w.team_id, w.org_id, w.valid_from::text AS valid_from, w.valid_to::text AS valid_to
          FROM team_orgs w
         WHERE (w.valid_from <> '-infinity' OR w.valid_to <> 'infinity')
           AND NOT EXISTS (SELECT 1 FROM fact_team_matches f WHERE f.team_id = w.team_id
                             AND f.started_at >= w.valid_from AND f.started_at < w.valid_to)"""):
        discrepancies.append({"kind": "window_covers_no_series", **{k: str(v) for k, v in r.items()},
                              "hint": "the window dates match none of this team id's series; check them in "
                                      "scope/org_decisions.json"})
    for r in _rows(conn, """
        SELECT a.team_id, a.org_id AS org_a, b.org_id AS org_b
          FROM team_orgs a JOIN team_orgs b ON b.team_id = a.team_id AND b.valid_from > a.valid_from
         WHERE a.valid_from < b.valid_to AND b.valid_from < a.valid_to"""):
        discrepancies.append({"kind": "overlapping_windows", **r})
    for r in _rows(conn, """
        SELECT team_id, count(DISTINCT org_key) AS keys FROM fact_team_matches
         GROUP BY team_id, match_id HAVING count(DISTINCT org_key) > 1 LIMIT 5"""):
        discrepancies.append({"kind": "one_series_two_identities", **r})
    counts = {
        "windows": int(_scalar(conn, "SELECT count(*) FROM team_orgs") or 0),
        "bounded": int(_scalar(conn, "SELECT count(*) FROM team_orgs WHERE valid_from <> '-infinity' "
                                     "OR valid_to <> 'infinity'") or 0),
        "team_ids_with_an_era_of_their_own": int(_scalar(conn, """
            SELECT count(DISTINCT f.team_id) FROM fact_team_matches f
             WHERE f.org_id IS NULL AND EXISTS (SELECT 1 FROM team_orgs w WHERE w.team_id = f.team_id)""") or 0),
        "series_in_own_eras": int(_scalar(conn, """
            SELECT count(DISTINCT f.match_id) FROM fact_team_matches f
             WHERE f.org_id IS NULL AND EXISTS (SELECT 1 FROM team_orgs w WHERE w.team_id = f.team_id)""") or 0),
    }
    return _result("identity_windows", discrepancies,
                   f"{counts['windows']} team-to-org windows ({counts['bounded']} bounded) each cover real series; "
                   f"{counts['team_ids_with_an_era_of_their_own']} team id(s) keep an era of their own "
                   f"({counts['series_in_own_eras']} series)",
                   f"{len(discrepancies)} window problem(s)", counts)


# --------------------------------------------------- 7. Liquipedia map isolation

def check_liquipedia_map_isolation(conn: psycopg.Connection) -> CheckResult:
    """No player row was ever created from a Liquipedia-sourced map.

    Stage 2 enriches `result_only` series with Liquipedia's map-level results
    (score, winner), never player stats - there are none to have. A
    `match_players` row joined to a `source = 'liquipedia'` round would mean
    something wrote player stats FACEIT never provided, which is exactly the
    kind of silent merge the source-per-field rule exists to prevent.
    """
    discrepancies = _rows(conn, """
        SELECT mp.match_id, mp.round_number, count(*) AS player_rows
          FROM match_players mp
          JOIN match_rounds r ON (r.match_id, r.round_number) = (mp.match_id, mp.round_number)
         WHERE r.source = 'liquipedia'
         GROUP BY mp.match_id, mp.round_number""")
    for d in discrepancies:
        d["kind"] = "player_row_on_liquipedia_only_map"
    counts = {
        "liquipedia_sourced_maps": int(_scalar(conn, "SELECT count(*) FROM match_rounds WHERE source = 'liquipedia'") or 0),
        "liquipedia_enriched_matches": int(_scalar(conn, """
            SELECT count(DISTINCT match_id) FROM match_rounds WHERE source = 'liquipedia'""") or 0),
    }
    return _result("liquipedia_map_isolation", discrepancies,
                   f"{counts['liquipedia_sourced_maps']} Liquipedia-sourced map(s) across "
                   f"{counts['liquipedia_enriched_matches']} match(es) carry no player rows",
                   f"{len(discrepancies)} Liquipedia-sourced map(s) have a player row that should not exist", counts)


CHECKS: dict[str, Callable[[psycopg.Connection], CheckResult]] = {
    "fact_view_reconciliation": check_fact_view_reconciliation,
    "date_visibility": check_date_visibility,
    "org_key_resolution": check_org_key_resolution,
    "aggregate_sums": check_aggregate_sums,
    "stat_reachability": check_stat_reachability,
    "region_consistency": check_region_consistency,
    "identity_windows": check_identity_windows,
    "liquipedia_map_isolation": check_liquipedia_map_isolation,
}


def run_checks(conn: psycopg.Connection, only: Optional[list[str]] = None) -> list[CheckResult]:
    """Run the invariants. Read-only; the caller owns the transaction."""
    names = only or list(CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        raise ValueError(f"unknown check(s): {', '.join(unknown)}; known: {', '.join(CHECKS)}")
    out = []
    for name in names:
        t0 = time.perf_counter()
        result = CHECKS[name](conn)
        result.seconds = round(time.perf_counter() - t0, 3)
        log_event(log, logging.INFO if result.ok else logging.ERROR, "consistency_check",
                  check=name, ok=result.ok, discrepancies=result.discrepancy_count, seconds=result.seconds)
        out.append(result)
    return out


def render_text(results: list[CheckResult]) -> str:
    lines = []
    for r in results:
        lines.append(f"[{'PASS' if r.ok else 'FAIL'}] {r.name} ({r.seconds}s): {r.summary}")
        for k, v in r.counts.items():
            lines.append(f"         {k}: {v}")
        for d in r.discrepancies:
            lines.append(f"    !    {d}")
        if r.discrepancy_count > len(r.discrepancies):
            lines.append(f"    !    ... {r.discrepancy_count - len(r.discrepancies)} more")
    failed = [r for r in results if not r.ok]
    lines.append("")
    lines.append(f"{len(results) - len(failed)}/{len(results)} checks passed"
                 + (f"; FAILED: {', '.join(r.name for r in failed)}" if failed else ""))
    return "\n".join(lines)
