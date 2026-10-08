"""Which team a player is on, and which teams they have been on.

Answered from `match_rosters`, the line-ups FACEIT declares on each series, not from per-map stats: a series
FACEIT recorded no map stats for (an offline or LAN day) still names who played, so a stint is not shortened
by the gap the `offline_map_stats` limitation describes. A stint is a run of consecutive series for the same
organisation; leaving and coming back is two stints, not one long one.

There is no roster feed behind this. "Current" means the team in the player's most recent series in scope,
and the answer says so with the date.
"""

from __future__ import annotations

from typing import Any, Optional

import psycopg

# the series a player was rostered in, dated as answers date them (a Liquipedia date where linked)
PLAYED_SQL = """
    SELECT DISTINCT m.match_id, ti.org_key, ti.org_id, ti.team_id, ti.display_name, x.at, c.season, r.is_substitute
      FROM match_rosters r
      JOIN matches m ON m.match_id = r.match_id
      JOIN championships c ON c.championship_id = m.championship_id
      CROSS JOIN LATERAL (SELECT COALESCE(m.liquipedia_played_at,
                                          match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at)) AS at) x
      JOIN LATERAL team_identity_at(r.team_id, x.at) ti ON true    -- who the team was on that day
     WHERE r.player_id = %s AND c.include
       AND m.ingest_state IN ('complete', 'result_only') AND m.status = 'FINISHED'
       AND (%s::int IS NULL OR c.season = %s)
"""

STINTS_SQL = """
WITH played AS (""" + PLAYED_SQL + """), marked AS (
    SELECT *, CASE WHEN org_key IS DISTINCT FROM lag(org_key) OVER w THEN 1 ELSE 0 END AS new_stint
      FROM played WINDOW w AS (ORDER BY at, match_id)
), stinted AS (
    SELECT *, sum(new_stint) OVER (ORDER BY at, match_id) AS stint FROM marked
)
SELECT org_key,
       (array_agg(org_id ORDER BY at DESC))[1] AS org_id,
       (array_agg(team_id ORDER BY at DESC))[1] AS team_id,
       (array_agg(display_name ORDER BY at DESC))[1] AS team,
       min(at) AS from_at, max(at) AS to_at,
       count(DISTINCT match_id) AS matches,
       count(DISTINCT match_id) FILTER (WHERE is_substitute) AS as_substitute,
       array_agg(DISTINCT season ORDER BY season) AS seasons
  FROM stinted GROUP BY stint, org_key ORDER BY min(at) DESC, stint DESC
"""


def history_matches(conn: psycopg.Connection, player_id: str, season: Optional[int] = None) -> list[str]:
    """The series a team history is built from: what its attribution must cover (a stint's dates can be Liquipedia's)."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT match_id FROM (" + PLAYED_SQL + ") p", [player_id, season, season])
        ids = [r["match_id"] for r in cur.fetchall()]
    conn.commit()
    return ids


def team_history(conn: psycopg.Connection, player_id: str, season: Optional[int] = None) -> list[dict[str, Any]]:
    """The player's stints, newest first; the first row is the current team (their latest series in scope)."""
    with conn.cursor() as cur:
        cur.execute(STINTS_SQL, [player_id, season, season])
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    for i, row in enumerate(rows):
        row["status"] = "current" if i == 0 else "former"
        row["seasons"] = [s for s in row["seasons"] if s is not None]
    return rows
