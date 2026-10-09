"""The structured query object. Everything downstream consumes this, never free text."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "leaderboard",        # rank players/teams by a metric
    "entity_stat",        # one player's or team's number(s)
    "team_record",        # a team's series / map record
    "head_to_head",       # two teams against each other (series grain)
    "versus",             # any two entities against each other, at MAP grain
    "season_compare",     # one entity in one season against itself in another
    "map_stats",          # rows are maps or modes
    "stat_availability",  # which stats exist for which season
    "team_membership",    # which team a player is on now, and the teams they have been on
    "placement",          # where teams finished at one event (Liquipedia's prize pool)
]
EntityType = Literal["player", "team", "org", "map", "mode"]
Aggregation = Literal["total", "avg_per_map", "count", "rate"]
Region = Literal["na", "emea", "international", "korea"]
# FACEIT's own three values (match_players.role). Recorded per player per map,
# not per player: a flex player who played 10 maps tank and 5 maps DPS
# contributes to the tank leaderboard for those 10 and the DPS leaderboard for
# those 5. Nothing here picks a "primary" role or merges the two.
Role = Literal["Tank", "Damage", "Support"]

# Derived metrics the compiler knows how to compute. Anything else must be a
# FACEIT stat key that exists in stat_coverage (validated against the schema).
DERIVED_METRICS: dict[str, str] = {
    "kd_ratio": "eliminations divided by deaths",
    "win_rate": "series won / series played",
    "map_win_rate": "maps won / maps played",
    "wins": "series won",
    "losses": "series lost",
    "matches": "series played",
    "maps": "maps played",
    "map_wins": "maps won",
    "map_losses": "maps lost",
    "record": "wins-losses record",
}

ReasonCode = Literal[
    "unsupported_metric",
    "unsupported_question",
    "out_of_scope",
    "ambiguous_entity",
    "unknown_entity",
    "no_data",
    "invalid_query",
    "results_only",       # the slice has results but no source records player stats there
]


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player: Optional[str] = None       # a player name as typed (resolved later)
    team: Optional[str] = None         # a team name as typed
    opponent: Optional[str] = None     # second team for head-to-head
    subject: Optional[str] = None      # a name whose kind (player/team/org) is not stated
    subject_season: Optional[int] = Field(default=None, ge=2020, le=2035)   # per-side season, for "2024 X vs 2026 X"
    opponent_season: Optional[int] = Field(default=None, ge=2020, le=2035)
    championship: Optional[str] = None # free text, matched against championship names
    season: Optional[int] = Field(default=None, ge=2020, le=2035)
    map: Optional[str] = None
    mode: Optional[str] = None
    region: Optional[Region] = None
    role: Optional[Role] = None         # Tank | Damage | Support, per map (see Role above)
    # "this year", "last stage": resolved against the data by validate(), which says in a note what it read it as
    period: Optional[Literal["this_season", "last_season", "this_stage", "last_stage"]] = None
    place: Optional[int] = Field(default=None, ge=1, le=64)   # a finishing position at an event: 1 is the winner

    def names(self) -> list[tuple[str, str]]:
        """(role, name) pairs that need entity resolution."""
        out = []
        for role in ("player", "team", "opponent", "subject"):
            v = getattr(self, role)
            if v:
                out.append((role, v))
        return out


class StructuredQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    entity: EntityType
    metric: Optional[str] = None
    filters: Filters = Field(default_factory=Filters)
    aggregation: Aggregation = "total"
    sort: Literal["desc", "asc"] = "desc"
    limit: int = Field(default=10, ge=1, le=100)
    min_maps: Optional[int] = Field(default=None, ge=1, le=1000)   # None: not asked for; the compiler picks the floor

    def compact(self) -> dict:
        """Dict without None / default noise, for tests and logs."""
        d = self.model_dump(exclude_none=True)
        f = {k: v for k, v in d.get("filters", {}).items() if v is not None}
        d["filters"] = f
        return d


class Unanswerable(BaseModel):
    """First-class "can't answer" with a specific reason."""

    model_config = ConfigDict(extra="forbid")

    code: ReasonCode
    reason: str
    suggestions: list[str] = Field(default_factory=list)
