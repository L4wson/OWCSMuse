"""Column descriptors: what a column is called and what kind of thing it holds.

Rows go out as raw values - a date is a timestamp, a percentage is a number - so
anything reading them can sort, sum or plot. What every client then has to invent
is the other half: that `played_at` is a date called "Date", that `score` and
`opponent_score` are one fact, that `coverage_pct` is a percentage and
`match_url` is a link. Four of the six gaps the frontend reported were that
re-derivation, so it is answered here, next to the schema that knows.

A descriptor is `{key, label, type}`, plus `pair_key` for the one case where two
columns are a single fact. `type` is the formatting contract:

    date      an ISO timestamp, rendered as a day
    score     this side's number, with `pair_key` holding the other side's
    percent   0-100, already scaled
    integer   a count
    decimal   a measured number, two places is plenty
    text      a name, a label, an id shown deliberately
    link      an absolute URL
    flag      a boolean where false is the interesting case
    result    won / lost / drawn
    list      an array of scalars, such as seasons
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

# Columns a reader cannot use: join keys and the ids behind a link. The values
# stay in the rows (a client needs match_id to key a list), they are simply not
# described as columns to show.
UNDESCRIBED = frozenset({
    "match_id", "championship_id", "player_id", "org_key", "org_id", "team_id",
    "opponent_team_id", "total_rows", "entity",
})

LABELS: dict[str, str] = {
    "played_at": "Date",
    "round_number": "Map #",
    "map_name": "Map",
    "game_mode": "Mode",
    "opponent_score": "Opp",
    "best_of": "Best of",
    "map_stats_recorded": "Map stats",
    "match_url": "Source",
    "damage_dealt": "Damage",
    "healing_done": "Healing",
    "damage_mitigated": "Mitigated",
    "objective_time": "Objective time",
    "time_played": "Time played",
    "kd_ratio": "K/D",
    "map_win_pct": "Map win %",
    "win_pct": "Win %",
    "coverage_pct": "Coverage %",
    "maps_with_stat": "Maps with stat",
    "maps_played": "Maps played",
    "avg_per_map": "Per map",
    "min_per_map": "Lowest",
    "max_per_map": "Highest",
    "first_map_at": "First",
    "last_map_at": "Last",
    "first_match_at": "First",
    "last_match_at": "Last",
    "first_at": "First",
    "from_at": "From",
    "to_at": "To",
    "as_substitute": "As substitute",
    "status": "Status",
    "last_at": "Last",
    "nickname": "Player",
    "stat_value": "Value",
    "stat_key": "Stat",
    "rows_with_stat": "Rows with stat",
    "rows_total": "Rows",
    "championships_with_stat": "Competitions with stat",
    "championships_total": "Competitions",
    "map_wins": "Map wins",
    "map_losses": "Map losses",
    "points_for": "Points for",
    "points_against": "Points against",
    "maps_won": "Maps won",
    "maps_drawn": "Maps drawn",
    "team1_wins": "Team 1 wins",
    "team2_wins": "Team 2 wins",
    "maps_with_duration": "Maps with duration",
    "avg_duration_seconds": "Avg duration (s)",
}

# Explicit types where the name alone would guess wrong.
TYPES: dict[str, str] = {
    "score": "score",
    "opponent_score": "integer",
    "result": "result",
    "match_url": "link",
    "map_stats_recorded": "flag",
    "round_number": "integer",
    "season": "identifier",
    "year": "identifier",
    "best_of": "integer",
    "seasons": "list",
    "stat_key": "text",
    "stat_kind": "text",
    "avg_per_map": "decimal",
    "kd_ratio": "decimal",
    "stat_value": "decimal",
}


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: str
    pair_key: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def label_for(key: str) -> str:
    return LABELS.get(key) or key.replace("_", " ").capitalize()


def type_for(key: str, values: list[Any]) -> str:
    """The kind of thing a column holds, from its name first and its values second."""
    if key in TYPES:
        return TYPES[key]
    # A season or a year names something; it is not a quantity, so it is never thousand-separated.
    if key.endswith(("_season", "_year")):
        return "identifier"
    if key.endswith("_at"):
        return "date"
    if key.endswith("_pct") or key.endswith("_percent"):
        return "percent"
    if key.endswith("_url"):
        return "link"
    present = [v for v in values if v is not None]
    if not present:
        return "text"
    sample = present[0]
    if isinstance(sample, bool):
        return "flag"
    if isinstance(sample, (datetime, date)):
        return "date"
    if isinstance(sample, (list, tuple)):
        return "list"
    if isinstance(sample, (int, float, Decimal)):
        # Postgres numeric arrives as Decimal whether or not it has a fraction, so
        # the values decide: a whole-number column is an integer column, and a
        # damage total must not print as 9730.00.
        return "integer" if all(
            isinstance(v, (int, float, Decimal)) and Decimal(str(v)) == Decimal(str(v)).to_integral_value()
            for v in present
        ) else "decimal"
    return "text"


def describe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe the columns of a set of rows, in the order the query produced them.

    A column that is empty on every row of this page is left out: a series row has
    no map number, and an always-blank column is noise rather than information.
    """
    if not rows:
        return []
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys and key not in UNDESCRIBED:
                keys.append(key)

    columns: list[Column] = []
    for key in keys:
        values = [row.get(key) for row in rows]
        if all(v is None or v == "" for v in values):
            continue
        columns.append(Column(key=key, label=label_for(key), type=type_for(key, values)))

    # Two columns, one fact: a score reads as "3-1", never as two numbers that
    # happen to sit next to each other.
    by_key = {c.key: c for c in columns}
    if "score" in by_key and "opponent_score" in by_key:
        columns = [
            Column(key="score", label="Score", type="score", pair_key="opponent_score")
            if c.key == "score"
            else c
            for c in columns
            if c.key != "opponent_score"
        ]

    # A link belongs at the end of a row wherever it arrived in the query.
    link = next((c for c in columns if c.type == "link"), None)
    if link:
        columns = [c for c in columns if c is not link] + [link]
    return [c.as_dict() for c in columns]
