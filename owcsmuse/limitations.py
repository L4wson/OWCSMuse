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

from .log import get_logger, log_event

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
        "Series-grain answers (`record`, `series record against`) still count them. Stage 2 of the Liquipedia "
        "integration fills in map, mode, score and winner for 33 of those series from Liquipedia's own match "
        "records, so those 33 now appear at map grain too, in team and player map records alike (045: a player's map "
        "record counts every map of a series he was on the line-up of) - still with no player stats, since Liquipedia "
        "has none either; `agg_player_stats` and `fact_player_maps` cannot gain a row from them. The remaining "
        "result_only series either sit on a page outside Liquipedia's covered stages or have no Liquipedia "
        "counterpart at all, and are still absent from every map-grain answer.",
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
        "The Korea, China, Japan and Pacific regional leagues are not ingested, nor are open qualifiers, community "
        "cups or the relegation brackets held outside the main series. A leaderboard here is a leaderboard of NA and "
        "EMEA main-competition play plus the international events (Dreamhack Dallas, EWC 2024, the World Finals, "
        "Midseason Championships and Champions Clash), not of OWCS worldwide. The international events other than "
        "Dallas come from Liquipedia alone: they answer records, head-to-heads and placings, never a player stat.",
    ),
    Limitation(
        "results_only_source",
        "A results-only slice has series results but no player stats, from any source",
        "Liquipedia records results, map scores, picks and placings and never a player stat; a FACEIT result_only "
        "competition (Dreamhack Dallas, all 14 series) has series results and no per-map stats either. Where a "
        "whole slice is like that, a player-stat question is refused with reason code results_only rather than "
        "answered with an empty or partial ranking; where only part of a slice is, the answer says which part "
        "it could not rank. Records, head-to-heads and placings are answerable there.",
    ),
    Limitation(
        "main_series_2025_2026",
        "The 2025 and 2026 main series is reconstructed from player history",
        "FACEIT lists the 2025/2026 OWCS Central divisions in no tournament, hub or league listing and "
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
    at = "coalesce(m.liquipedia_played_at, match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at))"
    if role_type == "org":
        # identity at the series' time: a team id counts for the org only inside its window
        return (f"EXISTS (SELECT 1 FROM team_orgs w WHERE w.org_id = %s"
                f" AND w.team_id IN (m.faction1_team_id, m.faction2_team_id)"
                f" AND {at} >= w.valid_from AND {at} < w.valid_to)", [role_id])
    # a team id as itself: its series outside any org window
    return (f"%s IN (m.faction1_team_id, m.faction2_team_id) AND NOT EXISTS (SELECT 1 FROM team_orgs w"
            f" WHERE w.team_id = %s AND {at} >= w.valid_from AND {at} < w.valid_to)", [role_id, role_id])


def _seasons_in_slice(season: Optional[int]) -> tuple[int, ...]:
    """Which seasons an answer can draw on. No filter means all of them."""
    return (season,) if season else (2024, *CRAWLED_SEASONS)


def result_only_in_slice(conn: psycopg.Connection, season: Optional[int] = None,
                         championship_id: Optional[str] = None,
                         entities: Optional[list[tuple[str, Optional[str]]]] = None) -> dict[str, Any]:
    """Series in this slice that still have no maps at all.

    `result_only` means FACEIT itself has none; Stage 2 of the Liquipedia
    integration fills a `match_rounds` row in for some of those (score, winner,
    still no player stats), so a series that has been enriched is no longer
    absent from a map-grain answer and must not be counted here as if it were.
    """
    where = ["c.include", "m.ingest_state = 'result_only'",
             "NOT EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = m.match_id)"]
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
               grain: str = "map", results_only_parts: Optional[list[str]] = None) -> list[dict[str, Any]]:
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

    # a Liquipedia-only event (an `lp:` championship) is neither NA/EMEA-scoped nor crawled from FACEIT player history
    lp_event = bool(championship_id and championship_id.startswith("lp:"))

    if intent in ("leaderboard", "map_stats") and not region and not lp_event:
        out.append(BY_ID["scope_na_emea"].as_dict())

    if results_only_parts:
        out.append(BY_ID["results_only_source"].as_dict(
            "No source records player stats for " + ", ".join(results_only_parts) + ": results only there. "
            + ("That part is not in this answer." if grain == "map" else "Series-grain answers still count it.")))

    if not lp_event and any(s in CRAWLED_SEASONS for s in seasons):
        out.append(BY_ID["main_series_2025_2026"].as_dict(
            "The "
            + " and ".join(str(s) for s in seasons if s in CRAWLED_SEASONS)
            + " part of this answer comes from the player-history crawl, not from FACEIT's tournament "
              "listings, which do not include those divisions."))
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
