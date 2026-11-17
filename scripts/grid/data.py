"""The four fact sets the cell counter reads, each loaded once with a time-aware query.

Every row carries canonical ids only: `player_id` (a FACEIT GUID or `lp:player:<page>`) and `org_key` (a reviewed
org id, or `team:<id>` for a team id no org decision covers). A team id becomes an `org_key` through
`team_identity_at(team_id, <the series' own time>)`, the function every Muse fact view uses, so a recycled or
acquired team id resolves to whoever held it on the day. Nothing here reads a current team, a current role or a
display name to decide an answer.

Grains:

- `Appearance`: player x series, from `series_lineups` (FACEIT's declared line-up, or Liquipedia's line-up for a
  Liquipedia-only series). Covers every series in scope. No role, no stats.
- `MapRow`: player x map played, from `fact_player_maps` (FACEIT `/stats`). Carries the role played on that map and
  the stat components. Exists only where FACEIT recorded map stats.
- `TeamSeries`: team identity x series, from `series`. One row per side.
- `Placement`: team identity x event, from `placements` (Liquipedia prize pools).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psycopg

ROLES = ("Tank", "Damage", "Support")


@dataclass(frozen=True)
class Appearance:
    player_id: str
    series_id: str
    played_at: datetime
    season: int
    region: str
    championship_id: str
    org_key: str
    lineup_source: str      # 'faceit' | 'liquipedia'


@dataclass(frozen=True)
class MapRow:
    player_id: str
    match_id: str
    round_number: int
    played_at: datetime
    season: int
    region: str
    championship_id: str
    org_key: str
    role: Optional[str]     # Tank | Damage | Support; None when FACEIT's value is not one of the three
    eliminations: Optional[int]
    deaths: Optional[int]
    damage_dealt: Optional[float]
    healing_done: Optional[float]
    damage_mitigated: Optional[float]
    time_played: Optional[float]    # seconds; absent for every 2024 map


@dataclass(frozen=True)
class TeamSeries:
    org_key: str
    opponent_org_key: str
    series_id: str
    played_at: datetime
    season: int
    region: str
    championship_id: str
    won: bool


@dataclass(frozen=True)
class Placement:
    org_key: str
    championship_id: str
    season: int
    place_high: int         # best position of the range: 7 for "7-8"
    place_low: int


@dataclass(frozen=True)
class Championship:
    championship_id: str
    name: str               # the reviewed display name
    season: int
    region: str
    tier: str
    player_stats: bool      # does any source give this competition per-map player stats


@dataclass
class Warehouse:
    appearances: list[Appearance]
    map_rows: list[MapRow]
    team_series: list[TeamSeries]
    placements: list[Placement]
    championships: dict[str, Championship]
    player_names: dict[str, str]
    org_names: dict[str, str]


APPEARANCES_SQL = """
    SELECT l.player_id, s.series_id, s.played_at, c.season, c.scope_region AS region, s.championship_id,
           ti.org_key, l.source AS lineup_source
      FROM series s
      JOIN championships c ON c.championship_id = s.championship_id AND c.include
      JOIN series_lineups l ON l.match_id = s.match_id
      JOIN LATERAL team_identity_at(l.team_id, s.played_at) ti ON true      -- who the team was on that day
"""

MAP_ROWS_SQL = """
    SELECT player_id, match_id, round_number, started_at AS played_at, season, region, championship_id, org_key,
           role, eliminations, deaths, damage_dealt, healing_done, damage_mitigated, time_played
      FROM fact_player_maps
"""

TEAM_SERIES_SQL = """
    SELECT a.org_key, b.org_key AS opponent_org_key, s.series_id, s.played_at, c.season, c.scope_region AS region,
           s.championship_id, (s.winner_side = side.n) AS won
      FROM series s
      JOIN championships c ON c.championship_id = s.championship_id AND c.include
      CROSS JOIN LATERAL (VALUES (1, s.side1_team_id, s.side2_team_id),
                                 (2, s.side2_team_id, s.side1_team_id)) side(n, team_id, opponent_team_id)
      JOIN LATERAL team_identity_at(side.team_id, s.played_at) a ON true
      JOIN LATERAL team_identity_at(side.opponent_team_id, s.played_at) b ON true
"""

PLACEMENTS_SQL = """
    SELECT org_key, championship_id, season, place_high, place_low
      FROM placements
     WHERE org_key IS NOT NULL          -- an undecided Liquipedia name is nobody's answer
"""

CHAMPIONSHIPS_SQL = """
    SELECT c.championship_id, championship_display_name(c.name) AS name, c.season, c.scope_region AS region, c.tier,
           COALESCE(sc.player_stats, false) AS player_stats
      FROM championships c
      LEFT JOIN source_capabilities sc ON sc.championship_id = c.championship_id
     WHERE c.include
"""

PLAYER_NAMES_SQL = "SELECT player_id, player_display_name(display_name, nickname, game_player_name) AS name FROM players"
ORG_NAMES_SQL = "SELECT org_key, display_name AS name FROM identity_keys"


def _num(value) -> Optional[float]:
    return None if value is None else float(value)


def load(conn: psycopg.Connection) -> Warehouse:
    """Everything the counter needs, in seven SELECTs."""
    def rows(sql: str) -> list[dict]:
        result = conn.execute(sql).fetchall()
        conn.rollback()         # nothing to commit; never hold a transaction open between reads
        return result

    appearances = [Appearance(**r) for r in rows(APPEARANCES_SQL)]
    map_rows = [
        MapRow(
            player_id=r["player_id"], match_id=r["match_id"], round_number=r["round_number"],
            played_at=r["played_at"], season=r["season"], region=r["region"],
            championship_id=r["championship_id"], org_key=r["org_key"],
            role=r["role"] if r["role"] in ROLES else None,
            eliminations=r["eliminations"], deaths=r["deaths"], damage_dealt=_num(r["damage_dealt"]),
            healing_done=_num(r["healing_done"]), damage_mitigated=_num(r["damage_mitigated"]),
            time_played=_num(r["time_played"]),
        )
        for r in rows(MAP_ROWS_SQL)
    ]
    team_series = [TeamSeries(**r) for r in rows(TEAM_SERIES_SQL)]
    placements = [Placement(**r) for r in rows(PLACEMENTS_SQL)]
    championships = {r["championship_id"]: Championship(**r) for r in rows(CHAMPIONSHIPS_SQL)}
    player_names = {r["player_id"]: r["name"] for r in rows(PLAYER_NAMES_SQL)}
    org_names = {r["org_key"]: r["name"] for r in rows(ORG_NAMES_SQL)}
    return Warehouse(appearances, map_rows, team_series, placements, championships, player_names, org_names)
