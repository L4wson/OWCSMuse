"""Match payloads (championship listing items and /matches/{id}) -> records.

The listing item and the detail payload share a shape, so one parser serves
both. The important difference is semantic: the listing's `results` can
describe only the first map, while /matches/{id} `results` is the series
result. The collector treats a parsed listing item as a provisional stub and
always overwrites its result from the detail payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .common import faceit_url, to_int, ts_from_epoch

FACTIONS = ("faction1", "faction2")


@dataclass(frozen=True)
class SeriesResult:
    winner_faction: Optional[str]
    faction1_score: Optional[int]
    faction2_score: Optional[int]

    @property
    def is_known(self) -> bool:
        return self.winner_faction is not None


BYE_TEAM_ID = "bye"
BYE_NOTE = "bye: a bracket slot filled by a placeholder opponent, not a played series"


@dataclass
class TeamRef:
    team_id: str
    name: Optional[str]
    avatar: Optional[str] = None

    @property
    def is_bye(self) -> bool:
        """FACEIT fills an empty bracket slot with a placeholder faction whose id and name are both 'bye'."""
        return self.team_id.lower() == BYE_TEAM_ID or (self.name or "").strip().lower() == BYE_TEAM_ID


@dataclass
class RosterEntry:
    faction: str
    team_id: Optional[str]
    player_id: str
    nickname: Optional[str]
    game_player_id: Optional[str]
    game_player_name: Optional[str]
    avatar: Optional[str]
    is_substitute: bool


@dataclass
class MapPick:
    pick_order: int
    map_guid: str
    map_name: Optional[str]


@dataclass
class MatchRecord:
    match_id: str
    championship_id: Optional[str]
    competition_name: Optional[str]
    organizer_id: Optional[str]
    game_id: Optional[str]
    region: Optional[str]
    best_of: Optional[int]
    status: Optional[str]
    round: Optional[int]
    group: Optional[int]
    scheduled_at: Optional[datetime]
    configured_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    faceit_url: Optional[str]
    faction1: Optional[TeamRef]
    faction2: Optional[TeamRef]
    result: SeriesResult
    roster: list[RosterEntry] = field(default_factory=list)
    picks: list[MapPick] = field(default_factory=list)
    map_names: dict[str, str] = field(default_factory=dict)  # guid -> name
    detailed_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def involves_bye(self) -> bool:
        """A bracket bye is not a played series: the placeholder "wins" 0-1, and the real team is credited a 1-0."""
        return any(f is not None and f.is_bye for f in (self.faction1, self.faction2))

    @property
    def winner_team_id(self) -> Optional[str]:
        w = self.result.winner_faction
        if w == "faction1" and self.faction1:
            return self.faction1.team_id
        if w == "faction2" and self.faction2:
            return self.faction2.team_id
        return None

    @property
    def event_time(self) -> Optional[datetime]:
        """Best available timestamp for "when this match happened"."""
        return self.started_at or self.configured_at or self.scheduled_at or self.finished_at

    def team_for_faction(self, faction: str) -> Optional[TeamRef]:
        return self.faction1 if faction == "faction1" else self.faction2


def parse_results(results: Optional[dict[str, Any]]) -> SeriesResult:
    if not results:
        return SeriesResult(None, None, None)
    winner = results.get("winner")
    if winner not in FACTIONS:
        winner = None
    score = results.get("score") or {}
    return SeriesResult(
        winner_faction=winner,
        faction1_score=to_int(score.get("faction1")),
        faction2_score=to_int(score.get("faction2")),
    )


def results_differ(a: SeriesResult, b: SeriesResult) -> bool:
    return (a.winner_faction, a.faction1_score, a.faction2_score) != (
        b.winner_faction, b.faction1_score, b.faction2_score
    )


def winner_flipped(list_result: SeriesResult, detail_result: SeriesResult) -> bool:
    """True when LIST and DETAIL name different winners (the first-map quirk)."""
    return (
        list_result.winner_faction is not None
        and detail_result.winner_faction is not None
        and list_result.winner_faction != detail_result.winner_faction
    )


def _parse_team(faction: str, team: Optional[dict[str, Any]]) -> Optional[TeamRef]:
    if not team:
        return None
    team_id = team.get("faction_id") or team.get("team_id") or team.get("id")
    if not team_id:
        return None
    return TeamRef(team_id=team_id, name=team.get("name"), avatar=team.get("avatar") or None)


def _parse_roster(faction: str, team: Optional[dict[str, Any]], team_ref: Optional[TeamRef]) -> list[RosterEntry]:
    out: list[RosterEntry] = []
    if not team:
        return out
    for key, is_sub in (("roster", False), ("substitutes", True)):
        for p in team.get(key) or []:
            pid = p.get("player_id") or p.get("id")
            if not pid:
                continue
            out.append(
                RosterEntry(
                    faction=faction,
                    team_id=team_ref.team_id if team_ref else None,
                    player_id=pid,
                    nickname=p.get("nickname"),
                    game_player_id=p.get("game_player_id"),
                    game_player_name=p.get("game_player_name"),
                    avatar=p.get("avatar") or None,
                    is_substitute=is_sub,
                )
            )
    return out


def parse_map_entities(payload: dict[str, Any]) -> dict[str, str]:
    """guid -> display name from voting.map.entities (needed because stats give GUIDs)."""
    names: dict[str, str] = {}
    entities = (((payload.get("voting") or {}).get("map") or {}).get("entities")) or []
    for e in entities:
        guid = e.get("guid") or e.get("game_map_id")
        name = e.get("name") or e.get("class_name")
        if guid and name:
            names[guid] = name
    return names


def parse_match(payload: dict[str, Any]) -> MatchRecord:
    teams = payload.get("teams") or {}
    f1 = _parse_team("faction1", teams.get("faction1"))
    f2 = _parse_team("faction2", teams.get("faction2"))
    map_names = parse_map_entities(payload)
    picks_raw = (((payload.get("voting") or {}).get("map") or {}).get("pick")) or []
    picks = [MapPick(i + 1, guid, map_names.get(guid)) for i, guid in enumerate(picks_raw) if guid]

    return MatchRecord(
        match_id=payload["match_id"],
        championship_id=payload.get("competition_id"),
        competition_name=payload.get("competition_name"),
        organizer_id=payload.get("organizer_id"),
        game_id=payload.get("game"),
        region=payload.get("region"),
        best_of=to_int(payload.get("best_of")),
        status=payload.get("status"),
        round=to_int(payload.get("round")),
        group=to_int(payload.get("group")),
        scheduled_at=ts_from_epoch(payload.get("scheduled_at")),
        configured_at=ts_from_epoch(payload.get("configured_at")),
        started_at=ts_from_epoch(payload.get("started_at")),
        finished_at=ts_from_epoch(payload.get("finished_at")),
        faceit_url=faceit_url(payload.get("faceit_url")),
        faction1=f1,
        faction2=f2,
        result=parse_results(payload.get("results")),
        roster=_parse_roster("faction1", teams.get("faction1"), f1) + _parse_roster("faction2", teams.get("faction2"), f2),
        picks=picks,
        map_names=map_names,
        detailed_results=list(payload.get("detailed_results") or []),
    )


def parse_history_item(item: dict[str, Any]) -> MatchRecord:
    """A /players/{id}/history item -> MatchRecord stub.

    History items have a different team shape from championship listings
    (teams.faction1.nickname / .players[]) and, like listings, their `results`
    can describe only the first map. The DETAIL phase overwrites the result.
    """
    teams = item.get("teams") or {}

    def team_ref(faction: str) -> Optional[TeamRef]:
        t = teams.get(faction) or {}
        tid = t.get("team_id") or t.get("faction_id")
        return TeamRef(team_id=tid, name=t.get("nickname") or t.get("name"), avatar=t.get("avatar") or None) if tid else None

    f1, f2 = team_ref("faction1"), team_ref("faction2")
    roster: list[RosterEntry] = []
    for faction, ref in (("faction1", f1), ("faction2", f2)):
        for p in (teams.get(faction) or {}).get("players") or []:
            pid = p.get("player_id")
            if pid:
                roster.append(RosterEntry(faction=faction, team_id=ref.team_id if ref else None, player_id=pid,
                                          nickname=p.get("nickname"), game_player_id=p.get("game_player_id"),
                                          game_player_name=p.get("game_player_name"), avatar=p.get("avatar") or None,
                                          is_substitute=False))
    return MatchRecord(
        match_id=item["match_id"],
        championship_id=item.get("competition_id"),
        competition_name=item.get("competition_name"),
        organizer_id=item.get("organizer_id"),
        game_id=item.get("game_id") or item.get("game"),
        region=item.get("region"),
        best_of=to_int(item.get("best_of")),
        status=(item.get("status") or "").upper() or None,
        round=None,
        group=None,
        scheduled_at=None,
        configured_at=None,
        started_at=ts_from_epoch(item.get("started_at")),
        finished_at=ts_from_epoch(item.get("finished_at")),
        faceit_url=faceit_url(item.get("faceit_url")),
        faction1=f1,
        faction2=f2,
        result=parse_results(item.get("results")),
        roster=roster,
    )


# Explicit aliases so call sites read as the phase they belong to.
parse_match_stub = parse_match     # LIST phase: provisional, result may be first-map only
parse_match_detail = parse_match  # DETAIL phase: authoritative series result
