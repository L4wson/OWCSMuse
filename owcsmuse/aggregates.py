"""Refresh and read helpers for the aggregation layer (migrations/003_aggregates.sql)."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import psycopg

from .logging import get_logger, log_event

log = get_logger("owcsmuse.aggregates")

# Refresh order matters only in that entity_names is independent; the rest read
# the fact views directly. Kept explicit so the runbook and the code agree.
MATERIALIZED_VIEWS: tuple[str, ...] = (
    "agg_player_stats",
    "agg_player_season",
    "agg_player_stat_long",
    "stat_coverage",
    "stat_coverage_season",
    "agg_team_matches",
    "agg_team_maps",
    "agg_head_to_head",
    "agg_map_modes",
    "entity_names",
)


def refresh(conn: psycopg.Connection, views: Optional[list[str]] = None) -> dict[str, float]:
    """REFRESH MATERIALIZED VIEW for each aggregate; returns seconds per view."""
    timings: dict[str, float] = {}
    for name in views or MATERIALIZED_VIEWS:
        if name not in MATERIALIZED_VIEWS:
            raise ValueError(f"unknown materialized view: {name}")
        t0 = time.perf_counter()
        try:
            with conn.cursor() as cur:
                cur.execute(f"REFRESH MATERIALIZED VIEW {name}")
            conn.commit()
        except Exception:
            conn.rollback()
            log_event(log, logging.ERROR, "refresh_failed", view=name, exc_info=True)
            raise
        timings[name] = round(time.perf_counter() - t0, 3)
        log_event(log, logging.INFO, "refreshed", view=name, seconds=timings[name])
    return timings


def stat_coverage_summary(conn: psycopg.Connection, stat: str, season: Optional[int] = None,
                          championship_id: Optional[str] = None) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM stat_coverage_summary(%s, %s, %s)", (stat, season, championship_id))
        row = cur.fetchone()
    conn.commit()
    return dict(row) if row else {}


def stat_leaderboard(conn: psycopg.Connection, stat: str, season: Optional[int] = None,
                     championship_id: Optional[str] = None, min_maps: int = 1, limit: int = 20,
                     order: str = "total") -> dict[str, Any]:
    """Leaderboard rows plus the coverage summary for the same slice, always together."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM stat_leaderboard(%s, %s, %s, %s, %s, %s)",
                    (stat, season, championship_id, min_maps, limit, order))
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    summary = stat_coverage_summary(conn, stat, season, championship_id)
    return {"stat": stat, "season": season, "championship_id": championship_id, "coverage": summary, "rows": rows}


def available_stats(conn: psycopg.Connection, season: Optional[int] = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT season, stat_key, rows_with_stat, rows_total, coverage_pct, championships_with_stat, championships_total
            FROM stat_coverage_season
            WHERE %s::int IS NULL OR season = %s
            ORDER BY season, stat_key
            """,
            (season, season),
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows
