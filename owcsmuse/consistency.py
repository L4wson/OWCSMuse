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
import re
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
LISTED = 100           # rows a count's companion list shows; the count itself is always taken from every row
# No query that feeds a discrepancy or a count carries a LIMIT: an undercounting check reported 10 failures where there
# were 15. A LIMIT is allowed only on a diagnostic sample, marked `# sample:` on its line (tests/test_consistency_limits.py).


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
    ("fact_team_maps", "two rows per map, one per side (FACEIT rounds, and a Liquipedia-only series' games)",
     """SELECT (SELECT coalesce(sum((r.team1_team_id IS NOT NULL)::int + (r.team2_team_id IS NOT NULL)::int), 0)
                  FROM match_rounds r
                  JOIN matches m ON m.match_id = r.match_id
                  JOIN championships c ON c.championship_id = m.championship_id
                 WHERE m.ingest_state IN ('complete', 'result_only') AND c.include)
             + (SELECT coalesce(sum((s.side1_team_id IS NOT NULL)::int + (s.side2_team_id IS NOT NULL)::int), 0)
                  FROM liquipedia_rounds lr
                  JOIN series s ON s.lp_objectname = lr.lp_objectname AND s.sources = ARRAY['liquipedia'::text])"""),
    ("fact_team_matches", "two rows per series, one per side",
     """SELECT coalesce(sum((side1_team_id IS NOT NULL)::int + (side2_team_id IS NOT NULL)::int), 0) FROM series"""),
    # 045: one row per player per played map - his own row where a player row exists, else one per declared line-up
    # player of that map's side (series_lineups); counted here from the sources, not from the view's own branches
    ("fact_player_map_results", "one row per player per played map",
     """SELECT (SELECT count(*) FROM fact_player_maps)
             + (SELECT count(*) FROM fact_team_maps t JOIN series_lineups l ON l.match_id = t.match_id AND l.team_id = t.team_id
                 WHERE NOT EXISTS (SELECT 1 FROM match_players mp
                                    WHERE mp.match_id = t.match_id AND mp.round_number = t.round_number))"""),
    ("fact_player_versus", "one row per player per map per opposing player",
     """WITH per AS (
            SELECT match_id, round_number, team_id, count(*) AS n
              FROM fact_player_map_results GROUP BY match_id, round_number, team_id
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
                     GROUP BY mp.match_id, mp.round_number LIMIT 10""")   # sample: a diagnostic inside one discrepancy, counted by `difference`
            if view in ("fact_player_versus", "fact_player_map_results"):
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
            SELECT DISTINCT team_id FROM {view} WHERE org_key IS NULL AND team_id IS NOT NULL""")
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
             WHERE NOT EXISTS (SELECT 1 FROM {fact} f WHERE f.team_id = a.team_id AND f.org_key = a.org_key)""")
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
    # an org the owner decided spans regions (SpaceStation Gaming: EMEA in 2024, an NA partner team from 2025) carries
    # the token in every window's evidence (scope/org_decisions.json); it is reported, not failed
    # Liquipedia-born windows (`lp:team:`) are derived from the team map by `identity load`, not merge decisions, so
    # they are not judged against the token: loading SpaceStation Gaming's team-map name once failed this check
    decided_cross = {r["org_id"] for r in _rows(conn, """
        SELECT org_id FROM team_orgs WHERE team_id NOT LIKE 'lp:team:%' GROUP BY org_id
        HAVING bool_and(EXISTS (SELECT 1 FROM jsonb_array_elements_text(evidence) e WHERE e LIKE 'cross_region_ok%'))""")}
    for key_col, kind in (("org_key", "org_spans_regions"), ("team_id", "team_id_spans_regions")):
        for r in _rows(conn, f"""
            SELECT {key_col} AS key, array_agg(DISTINCT region ORDER BY region) AS regions,
                   array_agg(DISTINCT team_id) AS team_ids, count(DISTINCT match_id) AS matches
              FROM fact_team_matches
             WHERE region IN ('na', 'emea') AND {key_col} IS NOT NULL
             GROUP BY {key_col} HAVING count(DISTINCT region) > 1"""):
            if key_col == "org_key" and r["key"] in decided_cross:
                continue
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
        "decided_cross_region_orgs": sorted(decided_cross),
    }
    return _result("region_consistency", discrepancies,
                   f"none of {counts['orgs_checked']} orgs ({counts['mapped_orgs_checked']} merged) or "
                   f"{counts['team_ids_checked']} team ids has matches in both na and emea",
                   f"{len(discrepancies)} org(s) or team id(s) span na and emea", counts)


# ------------------------------------------------------------- series integrity

def check_series_integrity(conn: psycopg.Connection) -> CheckResult:
    """A match is one series whichever source holds it, and a linked pair's two records name the same teams.

    series_once: no FACEIT match id and no Liquipedia record appears in two series; series_reconciliation: the
    series count equals FACEIT's in-scope finished series plus the Liquipedia-only ones both of whose teams a
    decided anchor resolves; linked_sides_disagree: for a linked pair whose Liquipedia teams are decided, the two
    records' sides are the same identities. A link that stopped agreeing after an identity decision fails here
    rather than staying.
    """
    discrepancies: list[dict[str, Any]] = []
    for col, kind in (("faceit_match_id", "faceit_match_in_two_series"), ("lp_objectname", "liquipedia_record_in_two_series")):
        # no LIMIT on any query that feeds discrepancies: _result caps what is shown, the count must stay exact (a LIMIT
        # here once reported 10 linked_sides_disagree where there were 15)
        for r in _rows(conn, f"SELECT {col} AS id, count(*) AS n FROM series WHERE {col} IS NOT NULL GROUP BY {col} HAVING count(*) > 1"):
            discrepancies.append({"kind": kind, **r})
    faceit_n = int(_scalar(conn, """
        SELECT count(*) FROM matches m JOIN championships c ON c.championship_id = m.championship_id
         WHERE m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED' AND c.include""") or 0)
    lp_only = int(_scalar(conn, "SELECT count(*) FROM series WHERE faceit_match_id IS NULL") or 0)
    linked = int(_scalar(conn, "SELECT count(*) FROM series WHERE faceit_match_id IS NOT NULL AND lp_objectname IS NOT NULL") or 0)
    total = int(_scalar(conn, "SELECT count(*) FROM series") or 0)
    if total != faceit_n + lp_only:
        discrepancies.append({"kind": "series_count_does_not_reconcile", "series": total, "faceit": faceit_n, "liquipedia_only": lp_only})
    for r in _rows(conn, """
        WITH sides AS (
            SELECT s.series_id, s.lp_objectname,
                   (SELECT array_agg(ti.org_key ORDER BY ti.org_key) FROM unnest(ARRAY[s.side1_team_id, s.side2_team_id]) t(id)
                     CROSS JOIN LATERAL team_identity_at(t.id, s.played_at) ti) AS faceit_keys,
                   (SELECT array_agg(k ORDER BY k) FROM (
                        SELECT CASE a.entity_type WHEN 'org' THEN a.entity_id
                                    ELSE (SELECT ti.org_key FROM team_identity_at(a.entity_id, s.played_at) ti) END AS k
                          FROM liquipedia_matches lm
                          CROSS JOIN LATERAL (VALUES (lm.team1_name), (lm.team2_name)) n(name)
                          JOIN entity_anchors a ON a.anchor_kind = 'team_name' AND a.anchor = fold_name(n.name)
                                               AND (a.region = '' OR a.region = coalesce(lm.region, ''))
                                               AND lm.played_at >= a.valid_from AND lm.played_at < a.valid_to
                         WHERE lm.objectname = s.lp_objectname) x) AS lp_keys
              FROM series s WHERE s.faceit_match_id IS NOT NULL AND s.lp_objectname IS NOT NULL)
        SELECT series_id, lp_objectname, faceit_keys, lp_keys FROM sides
         WHERE lp_keys IS NOT NULL AND array_length(lp_keys, 1) = 2 AND faceit_keys IS DISTINCT FROM lp_keys"""):
        discrepancies.append({"kind": "linked_sides_disagree", **r,
                              "hint": "an identity decision no longer agrees with this link: review the link "
                                      "(liquipedia links decide) or the team mapping"})
    unresolved = int(_scalar(conn, """
        SELECT count(*) FROM liquipedia_matches lm JOIN championships c ON c.championship_id = lm.championship_id AND c.include
         WHERE lm.finished AND NOT lm.placeholder
           AND NOT EXISTS (SELECT 1 FROM liquipedia_links lk WHERE lk.lp_objectname = lm.objectname AND lk.faceit_match_id IS NOT NULL)
           AND NOT EXISTS (SELECT 1 FROM series s WHERE s.lp_objectname = lm.objectname)""") or 0)
    counts = {"series": total, "faceit": faceit_n, "linked_pairs": linked, "liquipedia_only": lp_only,
              "liquipedia_unresolved_not_in_series": unresolved}
    return _result("series_integrity", discrepancies,
                   f"{total} series: {faceit_n} from FACEIT ({linked} also on Liquipedia), {lp_only} Liquipedia-only; "
                   f"{unresolved} unlinked Liquipedia record(s) wait on a team decision and are in no answer",
                   f"{len(discrepancies)} series problem(s)", counts)


# ------------------------------------------------------------ score plausibility

def check_score_plausibility(conn: psycopg.Connection) -> CheckResult:
    """No series presents a score its best-of cannot hold, and no map is both won and drawn.

    FACEIT counts a drawn map as a win for the series winner and stored Dreamhack Dallas as best-of-1; the series
    view corrects the first from map results and derives a best-of the score fits. What reaches an answer is what
    this asserts; the corrections themselves are counted, not failed, so a rise in them is visible.
    """
    discrepancies: list[dict[str, Any]] = []
    for r in _rows(conn, """
        SELECT series_id, score1, score2, best_of, score_source, best_of_source FROM series
         WHERE best_of IS NOT NULL AND GREATEST(score1, score2) > (best_of + 1) / 2"""):   # an unknown best-of holds anything
        discrepancies.append({"kind": "score_impossible_for_best_of", **r})
    for r in _rows(conn, "SELECT match_id, round_number FROM fact_team_maps WHERE won AND drawn"):
        discrepancies.append({"kind": "map_both_won_and_drawn", **r})
    for r in _rows(conn, """
        SELECT s.series_id, t.name AS side1_team, s.score1 AS side1_series_score,
               (SELECT count(*) FROM match_rounds r
                 WHERE r.match_id = s.match_id
                   AND map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = s.side1_team_id
                   AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number))) AS side1_map_wins
          FROM series s LEFT JOIN teams t ON t.team_id = s.side1_team_id
         WHERE s.faceit_match_id IS NOT NULL AND s.score_source = 'faceit'
           AND EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = s.match_id)
           AND (SELECT count(*) FROM match_rounds r
                 WHERE r.match_id = s.match_id
                   AND map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = s.side1_team_id
                   AND NOT EXISTS (SELECT 1 FROM phantom_maps p WHERE (p.match_id, p.round_number) = (r.match_id, r.round_number))) > s.score1"""):
        # read as: side 1 (named) won more maps, by the scores, than the series score credits it with
        discrepancies.append({"kind": "map_wins_exceed_series_score", **r})
    # every FACEIT series whose presented best-of is not the stored one: the rule is general (032), so the list is
    # the report of what it corrects; a lowered best-of (stored bo5, won 2-x) is the kind worth a second look
    corrections = _rows(conn, """
        SELECT s.series_id, m.best_of AS stored, s.best_of AS derived, s.score1, s.score2, s.best_of_source, s.state
          FROM series s JOIN matches m ON m.match_id = s.faceit_match_id
         WHERE s.best_of_source <> 'faceit' ORDER BY s.played_at""")
    counts = {
        "scores_corrected_from_maps": int(_scalar(conn, "SELECT count(*) FROM series WHERE score_source = 'maps'") or 0),
        "best_of_derived_from_score": int(_scalar(conn, "SELECT count(*) FROM series WHERE best_of_source = 'derived from score'") or 0),
        "best_of_derived_from_map_wins": int(_scalar(conn, "SELECT count(*) FROM series WHERE best_of_source = 'derived from map wins'") or 0),
        "best_of_from_liquipedia": int(_scalar(conn, "SELECT count(*) FROM series WHERE best_of_source = 'liquipedia'") or 0),
        "best_of_unknown": int(_scalar(conn, "SELECT count(*) FROM series WHERE best_of_source = 'unknown'") or 0),
        "best_of_implausible": int(_scalar(conn, "SELECT count(*) FROM series WHERE best_of_source = 'implausible'") or 0),
        "results_from_liquipedia": int(_scalar(conn, "SELECT count(*) FROM series WHERE result_source = 'liquipedia' AND faceit_match_id IS NOT NULL") or 0),
        "best_of_raised": sum(1 for c in corrections if c["stored"] is not None and c["derived"] is not None and c["derived"] > c["stored"]),
        "best_of_lowered": sum(1 for c in corrections if c["stored"] is not None and c["derived"] is not None and c["derived"] < c["stored"]),
        "drawn_maps": int(_scalar(conn, "SELECT count(*) FROM fact_team_maps WHERE drawn") / 2 if _scalar(conn, "SELECT count(*) FROM fact_team_maps WHERE drawn") else 0),
        "best_of_corrections_total": len(corrections),
        "best_of_corrections": [{"series_id": c["series_id"], "stored": c["stored"], "derived": c["derived"],
                                 "score": f"{c['score1']}-{c['score2']}", "source": c["best_of_source"], "state": c["state"]}
                                for c in corrections[:LISTED]],
    }
    return _result("score_plausibility", discrepancies,
                   f"every series fits its best-of ({counts['scores_corrected_from_maps']} score(s) corrected from map results, "
                   f"{counts['best_of_derived_from_score'] + counts['best_of_derived_from_map_wins']} best-of derived from the "
                   f"winning score: {counts['best_of_raised']} raised, {counts['best_of_lowered']} lowered; "
                   f"{counts['drawn_maps']} drawn map(s))",
                   f"{len(discrepancies)} implausible score(s)", counts)


# ------------------------------------------------------------ map winners and phantom maps

def check_map_winner_consistency(conn: psycopg.Connection) -> CheckResult:
    """The map winner is derived from the scores; winner_team_id is advisory.

    1-3e78e269 map 5 is scored 0-3 for one team and credits the other as winner. The scores decide (map_winner), a
    tied map has no winner, and the stored winner is used only when a score is missing. The contradictions are
    listed, not failed - they are FACEIT's data - but a fact row that still follows the stored winner fails.
    """
    contradictions = _rows(conn, """
        SELECT r.match_id, r.round_number, r.map_name, r.game_mode, r.team1_score, r.team2_score,
               t1.name AS team1, t2.name AS team2, w.name AS stored_winner,
               dw.name AS derived_winner
          FROM match_rounds r
          JOIN matches m ON m.match_id = r.match_id JOIN championships c ON c.championship_id = m.championship_id
          LEFT JOIN teams t1 ON t1.team_id = r.team1_team_id LEFT JOIN teams t2 ON t2.team_id = r.team2_team_id
          LEFT JOIN teams w ON w.team_id = r.winner_team_id
          LEFT JOIN teams dw ON dw.team_id = map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id)
         WHERE c.include AND r.team1_score IS NOT NULL AND r.team2_score IS NOT NULL
           AND r.winner_team_id IS DISTINCT FROM map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id)
         ORDER BY r.match_id, r.round_number""")
    discrepancies: list[dict[str, Any]] = []
    for r in _rows(conn, """
        SELECT f.match_id, f.round_number, f.team_id FROM fact_team_maps f JOIN match_rounds r ON (r.match_id, r.round_number) = (f.match_id, f.round_number)
         WHERE f.won <> coalesce(map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = f.team_id, false)
            OR f.drawn <> map_is_drawn(r.team1_score, r.team2_score, r.winner_team_id)"""):
        discrepancies.append({"kind": "team_map_fact_follows_stored_winner", **r})
    for r in _rows(conn, """
        SELECT f.match_id, f.round_number, f.player_id FROM fact_player_maps f JOIN match_rounds r ON (r.match_id, r.round_number) = (f.match_id, f.round_number)
         WHERE f.map_won <> coalesce(map_winner(r.team1_team_id, r.team1_score, r.team2_team_id, r.team2_score, r.winner_team_id) = f.team_id, false)"""):
        discrepancies.append({"kind": "player_map_fact_follows_stored_winner", **r})
    counts = {"winner_contradicts_scores": len(contradictions),
              "contradictions": [{k: v for k, v in c.items()} for c in contradictions[:LISTED]]}
    return _result("map_winner_consistency", discrepancies,
                   f"every fact row follows the winner the scores give ({len(contradictions)} stored winner(s) contradict their scores and are overridden)",
                   f"{len(discrepancies)} fact row(s) follow a stored winner the scores contradict", counts)


def check_phantom_map_isolation(conn: psycopg.Connection) -> CheckResult:
    """A FACEIT map row beyond Liquipedia's game count for a linked series is a phantom: in no fact view, no
    aggregate, no series score. The player rows that rode on one are counted so a person can see them."""
    discrepancies: list[dict[str, Any]] = []
    for r in _rows(conn, "SELECT f.match_id, f.round_number FROM fact_team_maps f JOIN phantom_maps p ON (p.match_id, p.round_number) = (f.match_id, f.round_number)"):
        discrepancies.append({"kind": "phantom_in_team_map_fact", **r})
    for r in _rows(conn, "SELECT f.match_id, f.round_number FROM fact_player_maps f JOIN phantom_maps p ON (p.match_id, p.round_number) = (f.match_id, f.round_number)"):
        discrepancies.append({"kind": "phantom_in_player_map_fact", **r})
    phantoms = _rows(conn, "SELECT match_id, round_number, map_name, liquipedia_games, player_rows FROM phantom_maps ORDER BY 1, 2")
    counts = {"phantom_maps": len(phantoms), "phantom_maps_with_player_rows": sum(1 for p in phantoms if p["player_rows"]),
              "phantom_player_rows_excluded": sum(int(p["player_rows"]) for p in phantoms), "phantoms": phantoms[:LISTED]}
    return _result("phantom_map_isolation", discrepancies,
                   f"{len(phantoms)} phantom map(s) ({counts['phantom_maps_with_player_rows']} with player rows, {counts['phantom_player_rows_excluded']} excluded) are in no fact view",
                   f"{len(discrepancies)} fact row(s) sit on a phantom map", counts)


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
           AND w.team_id NOT LIKE 'lp:team:%'   -- a team-map era, checked by lp_name_resolution, not an org decision
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
         GROUP BY team_id, match_id HAVING count(DISTINCT org_key) > 1"""):
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


def check_dropped_stats_maps(conn: psycopg.Connection) -> CheckResult:
    """Every map a complete series' detailed_results records is a stored round, or is shown not to be a game.

    FACEIT's /stats dropped a map from 9 of 409 complete series (1-1d2eaf73 map 1, Ilios, among them) while the match's
    own detailed_results kept its winner, so the series counted one map fewer than it played and a player's map record
    missed it. `liquipedia enrich` recovers such a map where Liquipedia's record of the series has the same game (045).
    What is left is either explained - a position past the end of Liquipedia's game list, an entry no game stands
    behind (the phantom 1-0 "map 5" of Toronto Defiant v Timeless, TM v ENCE's 0-0 "map 6") - or a discrepancy: a map
    with a winner that no stored round and no Liquipedia evidence accounts for.
    """
    rows = _rows(conn, """
        WITH dr AS (
            SELECT m.match_id, e.n::int AS round_number, e.val->>'winner' AS winner,
                   (e.val->'factions'->'faction1'->>'score') || '-' || (e.val->'factions'->'faction2'->>'score') AS score
              FROM matches m
              JOIN championships c ON c.championship_id = m.championship_id
              JOIN raw_payloads d ON d.id = m.detail_raw_id
              CROSS JOIN LATERAL jsonb_array_elements(
                  CASE WHEN jsonb_typeof(d.payload->'detailed_results') = 'array' THEN d.payload->'detailed_results'
                       ELSE '[]'::jsonb END) WITH ORDINALITY AS e(val, n)
             WHERE c.include AND m.ingest_state = 'complete' AND m.status = 'FINISHED'
               AND e.val->>'winner' IN ('faction1', 'faction2'))
        SELECT dr.match_id, dr.round_number, dr.winner, dr.score, max(lm.n_games) AS liquipedia_games
          FROM dr
          LEFT JOIN match_rounds r ON r.match_id = dr.match_id AND r.round_number = dr.round_number
          LEFT JOIN liquipedia_links lk ON lk.faceit_match_id = dr.match_id AND NOT lk.provisional
                                       AND coalesce(lk.decision, '') <> 'rejected'
          LEFT JOIN liquipedia_matches lm ON lm.objectname = lk.lp_objectname
         WHERE r.match_id IS NULL
         GROUP BY dr.match_id, dr.round_number, dr.winner, dr.score
         ORDER BY dr.match_id, dr.round_number""")
    explained = [r for r in rows if r["liquipedia_games"] and r["round_number"] > r["liquipedia_games"]]
    discrepancies = [dict(r, kind="dropped_map_not_recovered",
                          hint="Liquipedia has a game at this position: run `python -m owcsmuse liquipedia enrich`"
                          if r["liquipedia_games"] else "no linked Liquipedia record to say whether this was a game")
                     for r in rows if r not in explained]
    counts = {
        "recovered_maps": int(_scalar(conn, "SELECT count(*) FROM match_rounds WHERE source = 'faceit_results'") or 0),
        "not_a_game_entries": [{"match_id": r["match_id"], "round_number": r["round_number"], "score": r["score"],
                               "liquipedia_games": r["liquipedia_games"]} for r in explained],
    }
    return _result("dropped_stats_maps", discrepancies,
                   f"every detailed_results map is a stored round ({counts['recovered_maps']} recovered from it), "
                   f"or past the end of Liquipedia's game list ({len(explained)} entr"
                   f"{'y' if len(explained) == 1 else 'ies'} no game stands behind)",
                   f"{len(discrepancies)} map(s) in detailed_results are neither a stored round nor explained", counts)


def check_name_variants(conn: psycopg.Connection) -> CheckResult:
    """One stored spelling per map and per mode (048).

    Answers filter on the exact stored value and the validator picks a spelling out of a set, so two spellings that
    fold together ("Control" and "control") split a filter's maps - and which half an answer read depended on the
    process's hash seed: "Twisted Minds has no series on Control maps" from one process, 57-28 from the next.
    """
    from .resolve import fold
    discrepancies: list[dict[str, Any]] = []
    counts: dict[str, Any] = {}
    for source in ("match_rounds", "liquipedia_rounds", "fact_team_maps", "fact_player_maps"):
        for col in ("map_name", "game_mode"):
            rows = _rows(conn, f"SELECT {col} AS v, count(*) AS n FROM {source} WHERE {col} IS NOT NULL GROUP BY 1")
            by_fold: dict[str, list] = {}
            for r in rows:
                by_fold.setdefault(fold(r["v"]), []).append((r["v"], int(r["n"])))
            counts[f"{source}.{col}"] = len(by_fold)
            for k, spellings in sorted(by_fold.items()):
                if len(spellings) > 1:
                    discrepancies.append({"kind": "spelling_variants", "where": f"{source}.{col}", "fold": k,
                                          "spellings": sorted(spellings, key=lambda x: -x[1])})
    return _result("name_variants", discrepancies,
                   "every map and mode has one stored spelling", f"{len(discrepancies)} name(s) stored in more than one spelling",
                   counts)


# ------------------------------------------------------------ answer rates

# Questions whose answer is a derived rate, asked through the real parser and pipeline for every season and for all of
# them. A rate is never summed or averaged (it is recomputed from its components), but an answer can still print the
# wrong column: "highest NA kd in 2026" said Attack's K/D was 77.80 - his map win % - while the row held 5.00.
RATE_QUESTIONS = (("highest kd", "kd_ratio"), ("most eliminations per map", "avg_per_map"),
                  ("best map win rate", "map_win_rate"), ("which team has the best series win rate", "win_rate"),
                  ("most deaths per 10 minutes", "Deaths/10m"))
# A per-10-minutes rate is FACEIT's own per-map figure, time-weighted: it lies between the player's smallest and largest
# per-map value. Every "/10m" rate was once per second ("Snowl leads Deaths/10m with 0.01" for about 8), which no
# bound on the row alone caught.
PER10_RATES = {"Deaths/10m"}
KD_BOUND = 15            # a season K/D above this over 3+ maps is not a real Overwatch number


def check_answer_rates(conn: psycopg.Connection) -> CheckResult:
    """Every rate an answer presents is plausible, and the sentence quotes the rate the row holds.

    Per row: K/D at most KD_BOUND over 3+ maps, a percentage within 0-100, a per-map average at most its total, a team's
    series at most its maps. Per answer: the sentence's number is the metric's own column, formatted as the sentence
    formats it.
    """
    from .nlq.pipeline import ask
    from .nlq.sentence import num, pct

    # the metric's own column, stated here rather than imported from the sentence code this checks
    own = {"kd_ratio": "kd_ratio", "map_win_rate": "map_win_pct", "win_rate": "win_pct", "avg_per_map": "avg_per_map",
           "Deaths/10m": "total"}

    seasons = [r["season"] for r in _rows(conn, "SELECT DISTINCT season FROM fact_player_maps WHERE season IS NOT NULL ORDER BY 1")]
    discrepancies: list[dict[str, Any]] = []
    asked = floored = 0
    with_key = {k: {r["season"] for r in _rows(conn, "SELECT DISTINCT season FROM stat_coverage_season WHERE stat_key = %s", [k])}
                for k in PER10_RATES}
    for season in seasons + [None]:
        for text, metric in RATE_QUESTIONS:
            if metric in with_key and season is not None and season not in with_key[metric]:
                continue   # a season that never recorded the stat (2024 has 9 keys) is refused, rightly
            question = f"{text} in {season}" if season else text
            a = ask(conn, question, with_evidence=False)
            conn.rollback()
            asked += 1
            unfloored = f"{question} with at least 1 map"
            if a.status != "ok" and unfloored in (a.alternatives or []):
                # nobody in the slice clears the leaderboard map floor (a small warehouse): the refusal says so and offers
                # the question without it, whose rates are still to be checked
                a = ask(conn, unfloored, with_evidence=False)
                conn.rollback()
                floored += 1
            rows = a.rows or []
            if a.status != "ok" or not rows:
                discrepancies.append({"kind": "rate_question_unanswered", "question": question, "status": a.status})
                continue
            for r in rows:
                maps = float(r.get("maps") or 0)
                bad = None
                if r.get("kd_ratio") is not None and maps >= 3 and float(r["kd_ratio"]) > KD_BOUND:
                    bad = f"K/D {r['kd_ratio']} over {int(maps)} maps"
                for k in ("win_pct", "map_win_pct"):
                    if r.get(k) is not None and not 0 <= float(r[k]) <= 100:
                        bad = f"{k} {r[k]}"
                if r.get("avg_per_map") is not None and r.get("total") is not None and float(r["avg_per_map"]) > float(r["total"]):
                    bad = f"average per map {r['avg_per_map']} exceeds the total {r['total']}"
                if r.get("matches") is not None and r.get("maps") is not None and float(r["matches"]) > float(r["maps"]):
                    bad = f"{r['matches']} series over {r['maps']} maps"
                if metric in PER10_RATES and r.get("total") is not None and r.get("player_id"):
                    lo, hi = (_rows(conn, """SELECT min(stat_num(stats ->> %s)) AS lo, max(stat_num(stats ->> %s)) AS hi
                                               FROM fact_player_maps WHERE player_id = %s AND stats ? %s
                                                AND (%s::int IS NULL OR season = %s)""",
                                    (metric, metric, r["player_id"], metric, season, season)) or [{}])[0].values()
                    if lo is not None and not float(lo) - 0.01 <= float(r["total"]) <= float(hi) + 0.01:
                        bad = f"{metric} {r['total']} outside FACEIT's own per-map values {lo}..{hi}"
                if bad:
                    discrepancies.append({"kind": "implausible_rate", "question": question,
                                          "row": r.get("nickname") or r.get("team"), "why": bad})
            q = (a.query or {})
            col = own[metric]
            v = rows[0].get(col)
            text_ = (a.sentence or {}).get("text", "")
            shown = pct(v) if q.get("metric") in ("win_rate", "map_win_rate") else num(v)
            if v is None or shown not in text_:
                discrepancies.append({"kind": "sentence_misquotes_rate", "question": question, "column": col,
                                      "row_value": str(v), "expected_in_sentence": shown, "sentence": text_})
    return _result("answer_rates", discrepancies,
                   f"{asked} rate answers across {len(seasons)} season(s) and all seasons: every rate plausible and quoted from its own column",
                   f"{len(discrepancies)} rate answer problem(s)",
                   {"questions_asked": asked, "asked_again_without_the_map_floor": floored, "seasons": seasons})


# ------------------------------------------------- Liquipedia name resolution

def check_lp_name_resolution(conn: psycopg.Connection) -> CheckResult:
    """Every Liquipedia team name resolves, in search, to the entity its linked series are keyed to.

    A team-map name anchored to a bare team id is searchable as that team id's own entity. When the series of that
    name's era sit in an org window on the id, search answers with the wrong era: "LuneX Gaming" answered with UNC inc's
    2024 record while every key was correctly split, and nothing flagged it. Per anchor era: the linked series in which
    a side carries the name, and whether the entity the name resolves to holds any of them (a team anchor: the named
    side's org_key is the id itself; an org anchor: a side is keyed to the org). None held fails, as does an anchor to
    an entity that does not exist.
    """
    from .decisions_loaded import SCOPE
    from .orgs import OrgDecisions
    discrepancies: list[dict[str, Any]] = []
    # An id that cannot exist anywhere, as opposed to one this warehouse does not hold (CI's sample holds four series):
    # a team id that is not a FACEIT id ('ec69a520-04', a truncated paste `teams decide` accepted), or an org no org
    # decision defines.
    od = OrgDecisions(SCOPE / "org_decisions.json")
    decided_orgs = {m["org_id"] for t in od.data for m in od.mappings(t)}
    # a Liquipedia-only org (Stage 4) is defined by the team map itself (`org_name`): no FACEIT team id can carry it
    from .liquipedia.teams import TeamMap
    for v in TeamMap(SCOPE / "liquipedia_team_map.json").data.values():
        for e in v.get("eras") or [v]:
            if e.get("entity_type") == "org" and (e.get("org_name") or v.get("org_name")):
                decided_orgs.add(e["entity_id"])
    guid = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    for r in _rows(conn, "SELECT anchor, region, entity_type, entity_id FROM entity_anchors WHERE anchor_kind = 'team_name'"):
        if (r["entity_type"] == "team" and not guid.match(r["entity_id"])) or \
           (r["entity_type"] == "org" and r["entity_id"] not in decided_orgs):
            discrepancies.append({"kind": "lp_name_points_at_missing_entity", **r,
                                  "hint": "the team map names an id or org that does not exist; correct the entry"})
    eras = _rows(conn, """
        WITH named AS (
            SELECT a.anchor, a.region, a.entity_type, a.entity_id, a.valid_from, s.match_id,
                   CASE a.entity_type WHEN 'team' THEN 'team:' || a.entity_id ELSE a.entity_id END AS resolves_to,
                   CASE a.entity_type
                        WHEN 'team' THEN (SELECT f.org_key FROM fact_team_matches f WHERE f.match_id = s.match_id AND f.team_id = a.entity_id)
                        ELSE CASE WHEN EXISTS (SELECT 1 FROM fact_team_matches f WHERE f.match_id = s.match_id AND f.org_key = a.entity_id)
                                  THEN a.entity_id END
                   END AS named_side_key
              FROM entity_anchors a
              JOIN liquipedia_matches lm ON a.anchor IN (fold_name(lm.team1_name), fold_name(lm.team2_name))
                                        AND (a.region = '' OR a.region = coalesce(lm.region, ''))
                                        AND lm.played_at >= a.valid_from AND lm.played_at < a.valid_to
              JOIN series s ON s.lp_objectname = lm.objectname AND s.faceit_match_id IS NOT NULL
             WHERE a.anchor_kind = 'team_name')
        SELECT anchor, region, entity_type, entity_id, valid_from::text AS valid_from, resolves_to,
               count(*) AS series, count(*) FILTER (WHERE named_side_key = resolves_to) AS held,
               array_agg(DISTINCT coalesce(named_side_key, '-')) FILTER (WHERE named_side_key IS DISTINCT FROM resolves_to) AS keyed_to
          FROM named GROUP BY 1, 2, 3, 4, 5, 6 ORDER BY 1""")
    for e in eras:
        if e["held"] == 0:
            discrepancies.append({"kind": "lp_name_resolves_to_no_series", "anchor": e["anchor"], "region": e["region"],
                                  "resolves_to": e["resolves_to"], "series": e["series"], "series_keyed_to": e["keyed_to"],
                                  "hint": "point the team-map entry at the org these series are keyed to"})
    counts = {"anchor_eras_with_linked_series": len(eras),
              "partly_held": [{"anchor": e["anchor"], "resolves_to": e["resolves_to"], "held": e["held"], "series": e["series"],
                               "keyed_to": e["keyed_to"]} for e in eras if 0 < e["held"] < e["series"]]}
    return _result("lp_name_resolution", discrepancies,
                   f"all {len(eras)} Liquipedia team-name era(s) resolve to an entity holding their series",
                   f"{len(discrepancies)} Liquipedia team name(s) resolve to the wrong entity", counts)


# ------------------------------------------------------- display names are searchable

def check_display_names_searchable(conn: psycopg.Connection) -> CheckResult:
    """Every entity's shown name is one of its own search names: a name a reader sees is a name they can ask by.

    An owner's display name (035) was shown everywhere and searchable nowhere until 037: "ZZZ record" found nobody
    while "zss" worked, and "Astro" resolved only as a prefix of the nickname Astronexz. A shown name shared by two
    entities is not a failure (it asks which, as the two Geekay Esports do); it is counted.
    """
    bad = _rows(conn, """
        WITH shown AS (SELECT DISTINCT entity_type, entity_id, current_name FROM entity_names WHERE current_name IS NOT NULL)
        SELECT s.entity_type, s.entity_id, s.current_name
          FROM shown s
         WHERE NOT EXISTS (SELECT 1 FROM entity_names n WHERE n.entity_type = s.entity_type AND n.entity_id = s.entity_id
                             AND n.name_folded = fold_name(s.current_name))
         ORDER BY 1, 3""")
    counts = _rows(conn, """
        WITH shown AS (SELECT DISTINCT entity_type, entity_id, current_name FROM entity_names WHERE current_name IS NOT NULL)
        SELECT count(*) AS entities,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM shown o WHERE fold_name(o.current_name) = fold_name(s.current_name)
                                                AND (o.entity_type, o.entity_id) <> (s.entity_type, s.entity_id))) AS shown_name_shared
          FROM shown s""")[0]
    discrepancies = [{"kind": "shown_name_not_searchable", "entity_type": b["entity_type"], "entity_id": b["entity_id"],
                      "shown_as": b["current_name"], "hint": "entity_names needs a search row for the name it shows"}
                     for b in bad]
    return _result("display_names_searchable", discrepancies,
                   f"all {counts['entities']} entities can be asked for by the name they are shown as "
                   f"({counts['shown_name_shared']} share that name with another entity and ask which)",
                   f"{len(discrepancies)} entit(ies) are shown by a name nobody can search for", dict(counts))


# ------------------------------------------------------- decisions loaded

def check_decisions_loaded(conn: psycopg.Connection) -> CheckResult:
    """Every reviewed decision in scope/ is in the tables its loader writes, and nothing loaded lacks a decision.

    A decision recorded and never loaded is invisible to every answer: production once held 166 decided player
    identities with no anchor and a stale team anchor that failed five series_integrity rows. See
    owcsmuse/decisions_loaded.py for each file's rule.
    """
    from . import decisions_loaded

    discrepancies, counts = decisions_loaded.check(conn)
    n = sum(c["decisions"] for c in counts["files"].values())
    return _result("decisions_loaded", discrepancies,
                   f"all {n} decision(s) across {len(counts['files'])} scope file(s) are loaded, and nothing loaded "
                   "lacks one",
                   f"{counts['decided_not_loaded']} decided but not loaded, {counts['loaded_not_decided']} loaded "
                   f"but not decided, {counts['loaded_differs']} loaded with a different value", counts)


# ------------------------------------------------------------ placements

def check_placement_consistency(conn: psycopg.Connection) -> CheckResult:
    """Every event with placings has exactly one winner, and it won the event's last series.

    Both sides are Liquipedia's own record (the prize pool and the bracket), compared by Liquipedia's names, so this
    holds whether or not the teams are decided. A bracket reset, an LCQ's prize pool mixed into the event's, or a
    placing entered before the final was played would each break it, and a winner is never picked between two.
    """
    discrepancies: list[dict[str, Any]] = []
    for r in _rows(conn, """
        WITH last AS (   -- each event's last finished series, and who won it
            SELECT DISTINCT ON (championship_id) championship_id,
                   CASE winner WHEN '1' THEN team1_name WHEN '2' THEN team2_name END AS won
              FROM liquipedia_matches WHERE finished
             ORDER BY championship_id, played_at DESC, objectname DESC)
        SELECT p.championship_id, count(*) FILTER (WHERE p.place_low = 1) AS winners,
               min(p.team_name) FILTER (WHERE p.place_low = 1) AS placed_first, min(l.won) AS won_last_series
          FROM liquipedia_placements p LEFT JOIN last l USING (championship_id) GROUP BY p.championship_id"""):
        r["placed_first_folded"] = _scalar(conn, "SELECT fold_name(%s)", (r["placed_first"],)) if r["placed_first"] else None
        r["won_last_folded"] = _scalar(conn, "SELECT fold_name(%s)", (r["won_last_series"],)) if r["won_last_series"] else None
        if r["winners"] != 1:
            discrepancies.append({"kind": "not_one_winner", **r})
        elif r["won_last_series"] is not None and r["won_last_folded"] != r["placed_first_folded"]:
            discrepancies.append({"kind": "winner_lost_the_last_series", **r})
    n = int(_scalar(conn, "SELECT count(DISTINCT championship_id) FROM liquipedia_placements") or 0)
    return _result("placement_consistency", discrepancies,
                   f"{n} event(s) with placings: each has one winner, and it won the event's last series",
                   f"{len(discrepancies)} event(s) whose placings do not agree with their bracket",
                   {"events": n})


CHECKS: dict[str, Callable[[psycopg.Connection], CheckResult]] = {
    "fact_view_reconciliation": check_fact_view_reconciliation,
    "date_visibility": check_date_visibility,
    "org_key_resolution": check_org_key_resolution,
    "aggregate_sums": check_aggregate_sums,
    "stat_reachability": check_stat_reachability,
    "region_consistency": check_region_consistency,
    "identity_windows": check_identity_windows,
    "series_integrity": check_series_integrity,
    "score_plausibility": check_score_plausibility,
    "liquipedia_map_isolation": check_liquipedia_map_isolation,
    "dropped_stats_maps": check_dropped_stats_maps,
    "name_variants": check_name_variants,
    "map_winner_consistency": check_map_winner_consistency,
    "phantom_map_isolation": check_phantom_map_isolation,
    "display_names_searchable": check_display_names_searchable,
    "decisions_loaded": check_decisions_loaded,
    "lp_name_resolution": check_lp_name_resolution,
    "placement_consistency": check_placement_consistency,
    "answer_rates": check_answer_rates,
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
