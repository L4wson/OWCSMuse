"""What this warehouse does not know, stated in one place.

Coverage numbers answer "how much of this stat exists". They do not answer "why
is it missing", and the why matters: the gaps here are not random. FACEIT
records no per-map stats for offline days, so the missing maps cluster on
playoffs and LAN - the highest-stakes series in the dataset. 2024 carries 9 stat
keys where later seasons carry 47. Scope is NA + EMEA only.

Each limitation is data, not prose scattered through the code: the README
documents the same objects, and the ask layer surfaces one when a question lands
in the slice it affects, so an answer that is quietly partial says so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import psycopg

from .logging import get_logger, log_event

log = get_logger("owcsmuse.limitations")

# Stat keys FACEIT recorded in 2024. Everything else in the modern 47-key set
# arrived with the 2025 stats revision.
SEASON_2024_STAT_KEYS = frozenset({
    "Assists", "Damage Dealt", "Damage Mitigated", "Deaths", "Eliminations",
    "Healing Done", "K/D Ratio", "Result", "Role",
})

# Numeric keys the modern payloads carry. Used only to tell "this metric is
# missing in 2024" from "this metric never existed".
_MODERN_STAT_KEYS = frozenset({
    "Final Blows", "Solo Kills", "Multi Kills", "Environmental Kills", "Objective Time", "Time Played",
    "Eliminations/10m", "Final Blows/10m", "Deaths/10m", "Assists/10m", "Damage Dealt/10m", "Healing Done/10m",
    "Damage Mitigated/10m", "Solo Kills/10m", "Multi Kills/10m", "Objective Time/10m", "Environmental Kills/10m",
    "(Eliminations + Assists)/Deaths", "Final Blows/Eliminations", "Solo Kills/Eliminations Ratio",
    "Solo Kills/Deaths Ratio", "Healing Done/Deaths", "Damage Mitigated/Deaths", "Damage Dealt/Eliminations",
    "Healing Done/Eliminations", "Damage Mitigated/Eliminations",
})


# Metrics that ask about how long a map took, one way or another.
DURATION_METRICS = frozenset({"Time Played", "duration", "map_duration", "Objective Time"})

# Seasons whose main series is reachable only through the history crawl.
CRAWLED_SEASONS = (2025, 2026)


@dataclass(frozen=True)
class Limitation:
    id: str
    title: str
    detail: str

    def as_dict(self, note: Optional[str] = None) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "note": note or self.detail}


LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        "offline_map_stats",
        "Offline and LAN days have series results but no map stats",
        "FACEIT records a result for an offline series without per-map player stats, so those series land in "
        "`result_only`: the winner and series score are known, the maps are not. 100 of 509 finished series in "
        "scope are result_only, and they are not spread evenly - 52 of 118 series in playoff and LAN "
        "competitions have no map stats against 48 of 391 elsewhere, and all 14 Dreamhack Dallas matches are "
        "result_only. Map-grain answers therefore under-represent exactly the matches that mattered most. "
        "Series-grain answers (`record`, `series record against`) still count them.",
    ),
    Limitation(
        "stats_2024",
        "2024 carries 9 stat keys; 2025 and 2026 carry 47",
        "FACEIT's 2024 OWCS payloads expose only Eliminations, Deaths, Assists, Damage Dealt, Healing Done, "
        "Damage Mitigated, K/D Ratio, Result and Role. Per-10-minute rates, Final Blows, Solo Kills, "
        "Objective Time and Time Played do not exist for that season at all. An all-seasons leaderboard for any "
        "of those is a 2025+ leaderboard wearing an all-time label.",
    ),
    Limitation(
        "map_duration",
        "Map duration is derived, and only from 2025 onward",
        "No payload carries a map duration field. It is derived from the per-player `Time Played` stat, which "
        "2024 does not have. 1004 of 1482 ingested maps carry a duration: all 748 of 2025 and all 256 of 2026, "
        "and none of 2024's 478.",
    ),
    Limitation(
        "scope_na_emea",
        "Scope is OWCS NA + EMEA main competition",
        "Korea, China, Japan and the Pacific regions are not ingested, nor are open qualifiers, community cups "
        "or the relegation brackets held outside the main series. A leaderboard here is a leaderboard of NA and "
        "EMEA main-competition play, not of OWCS worldwide.",
    ),
    Limitation(
        "main_series_2025_2026",
        "The 2025 and 2026 main series is reconstructed from player history",
        "FACEIT publishes the 2025/2026 OWCS Central divisions on no championship, hub or league endpoint and "
        "in no search result; they are reachable only through `/players/{id}/history`. Those seasons were "
        "assembled by a roster-seeded crawl that ran to convergence, so a series played entirely by players "
        "the crawl never reached would be absent with nothing to indicate it. 2024 comes from the championship "
        "endpoints directly and does not have this caveat.",
    ),
)

BY_ID: dict[str, Limitation] = {lim.id: lim for lim in LIMITATIONS}


def entity_match_filter(role_id: str, role_type: Optional[str]) -> tuple[str, list[Any]]:
    """SQL restricting `matches m` to the series one entity took part in."""
    if role_type == "player":
        return ("EXISTS (SELECT 1 FROM match_rosters r WHERE r.match_id = m.match_id AND r.player_id = %s)", [role_id])
    if role_type == "org":
        return ("EXISTS (SELECT 1 FROM team_identity ti WHERE ti.org_id = %s"
                " AND ti.team_id IN (m.faction1_team_id, m.faction2_team_id))", [role_id])
    return ("%s IN (m.faction1_team_id, m.faction2_team_id)", [role_id])


def _seasons_in_slice(season: Optional[int]) -> tuple[int, ...]:
    """Which seasons an answer can draw on. No filter means all of them."""
    return (season,) if season else (2024, *CRAWLED_SEASONS)


def result_only_in_slice(conn: psycopg.Connection, season: Optional[int] = None,
                         championship_id: Optional[str] = None,
                         entities: Optional[list[tuple[str, Optional[str]]]] = None) -> dict[str, Any]:
    """Series in this slice whose maps FACEIT never recorded."""
    where = ["c.include", "m.ingest_state = 'result_only'"]
    params: list[Any] = []
    if season:
        where.append("c.season = %s")
        params.append(season)
    if championship_id:
        where.append("m.championship_id = %s")
        params.append(championship_id)
    for entity_id, entity_type in entities or []:
        sql, p = entity_match_filter(entity_id, entity_type)
        where.append(sql)
        params += p
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT count(*) AS matches,
                           array_agg(DISTINCT c.season ORDER BY c.season) AS seasons,
                           count(DISTINCT m.championship_id) AS competitions
                      FROM matches m JOIN championships c USING (championship_id)
                     WHERE {' AND '.join(where)}""",
                params,
            )
            row = dict(cur.fetchone() or {})
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "limitation_probe_failed", exc_info=True)
        return {"matches": 0}
    return row


def applicable(conn: Optional[psycopg.Connection], intent: str, metric: Optional[str],
               season: Optional[int] = None, championship_id: Optional[str] = None,
               region: Optional[str] = None,
               entities: Optional[list[tuple[str, Optional[str]]]] = None,
               grain: str = "map") -> list[dict[str, Any]]:
    """The limitations that bear on one query's slice, each with a note for that slice.

    Takes the pieces of a query rather than the query object so the CLI, a test
    or a future API can ask the same question without building one.
    """
    out: list[dict[str, Any]] = []
    seasons = _seasons_in_slice(season)

    if intent != "stat_availability" and conn is not None:
        ro = result_only_in_slice(conn, season, championship_id, entities)
        if ro.get("matches"):
            n = ro["matches"]
            where = f" in {', '.join(map(str, ro.get('seasons') or []))}" if ro.get("seasons") else ""
            effect = ("Those series carry a result but no maps, so they are absent from this map-grain answer."
                      if grain == "map" else
                      "Those series carry a result but no per-map stats; this answer is series grain, so it "
                      "still counts them.")
            out.append(BY_ID["offline_map_stats"].as_dict(
                f"{n} series in this slice{where} have no map stats on FACEIT, which is what offline and LAN "
                f"days look like here. {effect}"))

    if metric and 2024 in seasons and metric not in SEASON_2024_STAT_KEYS and metric in _MODERN_STAT_KEYS:
        out.append(BY_ID["stats_2024"].as_dict(
            f"'{metric}' does not exist in 2024's 9-key stat set, so this covers 2025 and 2026 only even "
            "though no season filter says so." if not season else
            f"'{metric}' does not exist in 2024's 9-key stat set."))

    if metric in DURATION_METRICS and 2024 in seasons:
        out.append(BY_ID["map_duration"].as_dict(
            "Map duration is derived from per-player Time Played, which 2024 does not carry, so 2024 maps "
            "contribute nothing here."))

    if intent in ("leaderboard", "map_stats") and not region:
        out.append(BY_ID["scope_na_emea"].as_dict())

    if any(s in CRAWLED_SEASONS for s in seasons):
        out.append(BY_ID["main_series_2025_2026"].as_dict(
            "The "
            + " and ".join(str(s) for s in seasons if s in CRAWLED_SEASONS)
            + " part of this answer comes from the player-history crawl, not from FACEIT's championship "
              "endpoints, which do not publish those divisions."))
    return out


def render_text() -> str:
    """The whole list, for `python -m owcsmuse limitations` and for the README."""
    lines = []
    for lim in LIMITATIONS:
        lines.append(f"### {lim.title}")
        lines.append("")
        lines.append(f"`{lim.id}` - {lim.detail}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
