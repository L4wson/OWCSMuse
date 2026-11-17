"""The published Grid puzzles and the player index, read from two JSON files. No database, no state.

`scope/grid_puzzles.json` and `scope/grid_players.json` are written by `scripts/grid/generate_puzzles.py`. This
module only reads them: which puzzle is today's, whether a guess is right, a few example answers once a game is
over, and name search for the guess box. Nothing here returns a cell's full answer set.

A puzzle is published from 00:00 UTC on its date. Before that it does not exist as far as any caller can tell.

Two puzzle formats live in the file. A beta puzzle (no `format`) is role x column: its answers carry maps-in-role and
its can't-verify lists are per column. A mixed-clue puzzle (`"format": 2`) carries, per clue, a definition and the
sentence for a guess it cannot check, and per cell every answer's reason and which clue cannot judge each
unverifiable player. Both are served through the same routes.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..resolve import fold

# Relative to the working directory, like every other reviewed file in scope/ (heroes.py, aliases.py): the
# repository root in development, the image's WORKDIR in production, which copies scope/ beside the package.
PUZZLES_PATH = Path("scope") / "grid_puzzles.json"
PLAYERS_PATH = Path("scope") / "grid_players.json"

REVEAL_PER_CELL = 5
SEARCH_LIMIT = 8
ROLE_WORDS = {"tank": "Tank", "dps": "DPS", "support": "Support"}


class UnknownPuzzle(LookupError):
    """No published puzzle has that number (it may exist for a later date)."""


class BadGuess(ValueError):
    """The guess names a cell or a player that does not exist."""


def utc_date(now: datetime) -> date:
    """The puzzle day a moment falls in: the UTC calendar date. A naive datetime is taken as UTC."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).date()


def _key(text: str) -> str:
    """What a typed name is matched by. `fold()` strips everything from a name in a non-Latin script, so such a
    name falls back to its case-folded self rather than matching nothing (or everything)."""
    return fold(text) or text.casefold().strip()


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    names: tuple[str, ...]      # other names on record: earlier in-game names, FACEIT nicknames, Liquipedia handles
    team: str                   # the team of their latest series, as a label
    seasons: tuple[int, ...]

    @property
    def detail(self) -> str:
        """What tells two players with one name apart: "Team Liquid, 2025-2026"."""
        if not self.seasons:
            span = ""
        elif self.seasons[0] == self.seasons[-1]:
            span = str(self.seasons[0])
        else:
            span = f"{self.seasons[0]}-{self.seasons[-1]}"
        return ", ".join(part for part in (self.team, span) if part)


class GridStore:
    """Loads the two files on first use and again whenever either changes on disk."""

    def __init__(self, puzzles_path: Path | str | None = None, players_path: Path | str | None = None):
        self.puzzles_path = Path(puzzles_path if puzzles_path is not None else PUZZLES_PATH)
        self.players_path = Path(players_path if players_path is not None else PLAYERS_PATH)
        self._lock = threading.Lock()
        self._stamp: Optional[tuple] = None
        self._puzzles: dict[int, dict[str, Any]] = {}
        self._players: dict[str, Player] = {}
        self._search: list[tuple[str, str, Player]] = []    # (match key, the name as written, player)

    # ---- loading ------------------------------------------------------------------------------------------------

    @staticmethod
    def _mtime(path: Path) -> Optional[int]:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def _load(self) -> None:
        stamp = (self._mtime(self.puzzles_path), self._mtime(self.players_path))
        if stamp == self._stamp:
            return
        with self._lock:
            puzzles: dict[int, dict[str, Any]] = {}
            if stamp[0] is not None:
                for p in json.loads(self.puzzles_path.read_text(encoding="utf-8"))["puzzles"]:
                    puzzles[int(p["number"])] = p
            players: dict[str, Player] = {}
            if stamp[1] is not None:
                for p in json.loads(self.players_path.read_text(encoding="utf-8"))["players"]:
                    players[p["id"]] = Player(p["id"], p["name"], tuple(p.get("names") or ()), p.get("team") or "",
                                              tuple(p.get("seasons") or ()))
            search = []
            for player in players.values():
                for name in dict.fromkeys((player.name, *player.names)):
                    search.append((_key(name), name, player))
            self._puzzles, self._players, self._search, self._stamp = puzzles, players, search, stamp

    # ---- puzzles ------------------------------------------------------------------------------------------------

    def published(self, now: datetime) -> list[dict[str, Any]]:
        """Every puzzle whose day has begun, newest first."""
        self._load()
        today = utc_date(now)
        live = [p for p in self._puzzles.values() if date.fromisoformat(p["date"]) <= today]
        return sorted(live, key=lambda p: p["date"], reverse=True)

    def today(self, now: datetime) -> dict[str, Any]:
        self._load()
        today = utc_date(now).isoformat()
        for p in self._puzzles.values():
            if p["date"] == today:
                return p
        raise UnknownPuzzle(f"no puzzle is published for {today}")

    def get(self, number: int, now: datetime) -> dict[str, Any]:
        """A published puzzle by number. One dated tomorrow is as unknown as one that was never made."""
        self._load()
        p = self._puzzles.get(number)
        if p is None or date.fromisoformat(p["date"]) > utc_date(now):
            raise UnknownPuzzle(f"puzzle {number} is not published")
        return p

    # ---- what a client may see ----------------------------------------------------------------------------------

    @staticmethod
    def public(puzzle: dict[str, Any], now: datetime) -> dict[str, Any]:
        """The puzzle as a player sees it before guessing: the clues, the rules, the coverage. No answers, no ids."""
        mixed = is_mixed(puzzle)

        def header(clue: dict[str, Any], place: str, default_help: str) -> dict[str, Any]:
            # A mixed clue's stored key and params can name a player id (a teammate clue's anchor), so the page gets
            # a positional key instead, with the family, the label and the definition.
            return {"key": place if mixed else clue["key"], "family": clue.get("family"),
                    "label": clue["label"], "help": clue.get("help") or default_help}

        floor = puzzle["rules"].get("min_maps")
        role_help = f"{floor}+ maps in this role inside the column (FACEIT map stats)." if floor else ""
        return {
            "number": puzzle["number"],
            "date": puzzle["date"],
            "is_today": puzzle["date"] == utc_date(now).isoformat(),
            "kind": puzzle.get("kind", "role"),
            "difficulty": puzzle.get("difficulty"),
            "rows": [header(r, f"row{i}", role_help) for i, r in enumerate(puzzle["rows"])],
            "cols": [header(c, f"col{i}", "") for i, c in enumerate(puzzle["cols"])],
            "guesses": puzzle["rules"]["guesses"],
            "min_maps": floor,
            "coverage": coverage_note(puzzle),
        }

    def player(self, player_id: str) -> Optional[Player]:
        self._load()
        return self._players.get(player_id)

    def guess(self, number: int, cell: int, player_id: str, now: datetime) -> dict[str, Any]:
        """correct | wrong | cannot_verify for one player in one cell. Reveals nothing beyond that player."""
        puzzle = self.get(number, now)
        if not 0 <= cell <= 8:
            raise BadGuess("a cell is 0 to 8: row * 3 + column")
        player = self.player(player_id)
        if player is None:
            raise BadGuess("that player id is not in the player list")
        row, col = divmod(cell, 3)
        answer = puzzle["cells"][cell]["answers"].get(player_id)
        out: dict[str, Any] = {"puzzle": number, "cell": cell, "player": {"id": player.id, "name": player.name}}
        if is_mixed(puzzle):
            # the reason and the can't-verify sentence are the clue's own, written when the puzzle was generated
            if answer is not None:
                return {**out, "result": "correct", "uses_guess": True, "explanation": answer["why"], "link": None}
            side = puzzle["cells"][cell].get("unverifiable", {}).get(player_id)
            if side is not None:
                clue = puzzle["rows"][row] if side == "row" else puzzle["cols"][col]
                return {**out, "result": "cannot_verify", "uses_guess": False, "clue": clue["label"],
                        "explanation": f"{clue['cannot_verify']} It didn't use a guess."}
            return {**out, "result": "wrong", "uses_guess": True}
        if answer is not None:
            role = ROLE_WORDS.get(puzzle["rows"][row]["key"], puzzle["rows"][row]["label"])
            reason = puzzle["cols"][col]["explain"].format(maps=answer["maps"], role=role)
            source = "FACEIT map stats and series line-ups" if puzzle["cols"][col]["key"] == "all3" else "FACEIT map stats"
            # no link: Muse has no player page and no prefilled-question URL, and a /q/<slug> link resolves only
            # once that question has been asked. A link that might not resolve is worse than none.
            return {**out, "result": "correct", "uses_guess": True, "maps": answer["maps"],
                    "explanation": f"{reason} ({source})", "link": None}
        if player_id in puzzle["unverifiable"][col]:
            where = puzzle["cols"][col]["label"]
            return {**out, "result": "cannot_verify", "uses_guess": False,
                    "explanation": f"There is no role data for {player.name} in this column ({where}), so the guess "
                                   "can't be checked. It didn't use a guess."}
        return {**out, "result": "wrong", "uses_guess": True}

    def reveal(self, number: int, now: datetime) -> dict[str, Any]:
        """A few example answers per cell, for the end screen, and how many answers each cell had. Never the full set.

        A beta puzzle shows its players with the most maps in the role. A mixed-clue puzzle has no one number to rank
        by, so it shows the best-known answers: those who appear most across OWCS (the most seasons, then by name).
        """
        puzzle = self.get(number, now)
        mixed = is_mixed(puzzle)
        cells = []
        for cell in puzzle["cells"]:
            if mixed:
                def fame(item: tuple[str, dict[str, Any]]) -> tuple:
                    known = self._players.get(item[0])
                    return (-len(known.seasons) if known else 0, item[1]["name"].casefold(), item[0])
                ranked = sorted(cell["answers"].items(), key=fame)
                examples = [{"id": pid, "name": a["name"], "why": a["why"]} for pid, a in ranked[:REVEAL_PER_CELL]]
            else:
                ranked = sorted(cell["answers"].items(), key=lambda kv: (-kv[1]["maps"], kv[1]["name"].casefold(), kv[0]))
                examples = [{"id": pid, "name": a["name"], "maps": a["maps"]} for pid, a in ranked[:REVEAL_PER_CELL]]
            cells.append({"cell": cell["row"] * 3 + cell["col"], "count": len(cell["answers"]), "examples": examples})
        return {"puzzle": number, "per_cell": REVEAL_PER_CELL, "cells": cells}

    # ---- name search --------------------------------------------------------------------------------------------

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        """Players whose current or earlier name matches: exact, then starts-with, then contains.

        One row per player, never per name, and each carries the id a guess must send and a `detail` that separates
        players who share a name. When an earlier name is what matched, `matched` says which.
        """
        self._load()
        key = _key(query or "")
        if not key:
            return []
        best: dict[str, tuple[int, int, str, Player]] = {}
        for name_key, written, player in self._search:
            if name_key == key:
                rank = 0
            elif name_key.startswith(key):
                rank = 1
            elif key in name_key:
                rank = 2
            else:
                continue
            is_alias = 0 if written == player.name else 1
            candidate = (rank, is_alias, written, player)
            if player.id not in best or candidate[:2] < best[player.id][:2]:
                best[player.id] = candidate
        ordered = sorted(best.values(), key=lambda b: (b[0], b[1], b[3].name.casefold(), -len(b[3].seasons), b[3].id))
        return [
            {"id": player.id, "name": player.name, "detail": player.detail,
             "matched": written if is_alias else None}
            for _rank, is_alias, written, player in ordered[:limit]
        ]


def is_mixed(puzzle: dict[str, Any]) -> bool:
    """A mixed-clue puzzle (format 2), as against a beta role x column one."""
    return puzzle.get("format") == 2


MIXED_COVERAGE = (
    "Unless a clue says otherwise, answers come from FACEIT map stats for OWCS North America and EMEA main series "
    "(stages and playoffs), 2024-2026: relegation and international events are not counted, and \"a map\" is one "
    "with player stats on record. There are none for 2024 Stages 3-4 or 2026 Stage 3, and several playoff finals. "
    "\"Rostered at\" clues use Liquipedia's line-ups, which list a roster, not who played. When the data that "
    "would settle a guess is missing, the guess \"can't be verified\" and costs nothing. Tap a clue to see exactly "
    "what it means."
)


def coverage_note(puzzle: dict[str, Any]) -> str:
    """One paragraph under the board: what the answers were counted from, and what they cannot see."""
    if is_mixed(puzzle):
        return MIXED_COVERAGE
    floor = puzzle["rules"]["min_maps"]
    return (
        f"Answers are players with {floor} or more maps in the role inside the column, from FACEIT map stats for "
        "OWCS North America and EMEA main series (stages and playoffs). Roles are on record for 2024 Stages 1-2, "
        "2025 Stages 1-3 and 2026 Stages 1-2. There is none for 2024 Stages 3-4, 2026 Stage 3, relegation or "
        "international events, so a player known only from those returns \"can't verify\" and costs no guess."
    )
