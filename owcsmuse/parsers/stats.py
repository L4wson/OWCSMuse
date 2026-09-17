"""/matches/{id}/stats -> one RoundRecord per map ACTUALLY PLAYED.

Rules encoded here (known FACEIT quirks):
  * rounds[] has one entry per map played. It is shorter than the pick list
    whenever a series ends early. Never derive map counts from picks.
  * round_stats["OW2 Mode"] carries the game mode. It is read directly; the map
    name is never used to infer the mode.
  * round_stats["Map"] is a map GUID on current payloads; the display name is
    resolved from the /matches/{id} voting entities passed in as `map_names`.
  * Players belong to a team via the team id on their row (falling back to the
    enclosing teams[] entry, which carries the same id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .common import to_float, to_int

MODE_KEYS = ("OW2 Mode", "Mode", "Game Mode")
MAP_KEYS = ("Map",)


@dataclass
class RoundTeam:
    team_id: str
    name: Optional[str]
    score: Optional[int]
    win: Optional[bool]
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundPlayer:
    player_id: str
    nickname: Optional[str]
    team_id: Optional[str]
    role: Optional[str]
    result: Optional[int]
    eliminations: Optional[int]
    final_blows: Optional[int]
    deaths: Optional[int]
    assists: Optional[int]
    solo_kills: Optional[int]
    multi_kills: Optional[int]
    environmental_kills: Optional[int]
    damage_dealt: Optional[float]
    healing_done: Optional[float]
    damage_mitigated: Optional[float]
    objective_time: Optional[float]
    time_played: Optional[float]
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundRecord:
    match_id: Optional[str]
    round_number: int
    map_guid: Optional[str]
    map_name: Optional[str]
    game_mode: Optional[str]
    score_summary: Optional[str]
    winner_team_id: Optional[str]
    best_of: Optional[int]
    game_format: Optional[str]  # stats "game_mode" field, e.g. "5v5" (not the OW2 mode)
    teams: list[RoundTeam] = field(default_factory=list)
    players: list[RoundPlayer] = field(default_factory=list)
    raw_round_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def team1(self) -> Optional[RoundTeam]:
        return self.teams[0] if self.teams else None

    @property
    def team2(self) -> Optional[RoundTeam]:
        return self.teams[1] if len(self.teams) > 1 else None


def _looks_like_guid(value: str) -> bool:
    return value.lower().startswith("0x")


def _first(stats: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for k in keys:
        v = stats.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def parse_round(round_payload: dict[str, Any], map_names: Optional[Mapping[str, str]] = None) -> RoundRecord:
    map_names = map_names or {}
    rs: dict[str, Any] = dict(round_payload.get("round_stats") or {})

    map_value = _first(rs, MAP_KEYS)
    map_guid: Optional[str] = None
    map_name: Optional[str] = None
    if map_value:
        if _looks_like_guid(map_value):
            map_guid = map_value
            map_name = map_names.get(map_value)
        else:
            map_name = map_value
            # reverse-resolve the guid when the round reports a name
            for guid, name in map_names.items():
                if name == map_value:
                    map_guid = guid
                    break

    teams: list[RoundTeam] = []
    players: list[RoundPlayer] = []
    for t in round_payload.get("teams") or []:
        team_id = t.get("team_id") or t.get("faction_id")
        ts: dict[str, Any] = dict(t.get("team_stats") or {})
        win_raw = to_int(ts.get("Team Win"))
        teams.append(
            RoundTeam(
                team_id=team_id,
                name=ts.get("Team") or t.get("name"),
                score=to_int(ts.get("Team Score")),
                win=None if win_raw is None else bool(win_raw),
                stats=ts,
            )
        )
        for p in t.get("players") or []:
            pid = p.get("player_id")
            if not pid:
                continue
            ps: dict[str, Any] = dict(p.get("player_stats") or {})
            players.append(
                RoundPlayer(
                    player_id=pid,
                    nickname=p.get("nickname"),
                    team_id=p.get("team_id") or team_id,
                    role=ps.get("Role"),
                    result=to_int(ps.get("Result")),
                    eliminations=to_int(ps.get("Eliminations")),
                    final_blows=to_int(ps.get("Final Blows")),
                    deaths=to_int(ps.get("Deaths")),
                    assists=to_int(ps.get("Assists")),
                    solo_kills=to_int(ps.get("Solo Kills")),
                    multi_kills=to_int(ps.get("Multi Kills")),
                    environmental_kills=to_int(ps.get("Environmental Kills")),
                    damage_dealt=to_float(ps.get("Damage Dealt")),
                    healing_done=to_float(ps.get("Healing Done")),
                    damage_mitigated=to_float(ps.get("Damage Mitigated")),
                    objective_time=to_float(ps.get("Objective Time")),
                    time_played=to_float(ps.get("Time Played")),
                    stats=ps,
                )
            )

    winner = rs.get("Winner") or None
    if winner is None:
        for t in teams:
            if t.win:
                winner = t.team_id
                break

    return RoundRecord(
        match_id=round_payload.get("match_id"),
        round_number=to_int(round_payload.get("match_round")) or 0,
        map_guid=map_guid,
        map_name=map_name,
        game_mode=_first(rs, MODE_KEYS),
        score_summary=rs.get("Score Summary"),
        winner_team_id=winner,
        best_of=to_int(round_payload.get("best_of")),
        game_format=round_payload.get("game_mode"),
        teams=teams,
        players=players,
        raw_round_stats=rs,
    )


def parse_match_stats(
    payload: dict[str, Any],
    map_names: Optional[Mapping[str, str]] = None,
    match_id: Optional[str] = None,
) -> list[RoundRecord]:
    """Parse the rounds actually played. Round numbers are made unique and 1-based."""
    rounds = [parse_round(r, map_names) for r in (payload.get("rounds") or [])]
    seen: set[int] = set()
    for i, r in enumerate(rounds, start=1):
        if match_id and not r.match_id:
            r.match_id = match_id
        if r.round_number <= 0 or r.round_number in seen:
            r.round_number = i
        seen.add(r.round_number)
    rounds.sort(key=lambda r: r.round_number)
    return rounds
