"""OWCS Grid's HTTP routes. Stateless and database-free: every answer comes from `GridStore`'s two JSON files.

Conventions follow the rest of the API: a wrong guess is a 200 with the result in the body, 404 is a puzzle that is
not published, 422 a request that names a cell or player that does not exist. The server keeps nothing about who is
playing, so the nine-guess budget and the one-cell-per-player rule are the client's to enforce (docs/grid/BETA.md).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .store import BadGuess, GridStore, UnknownPuzzle


class GuessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell: int = Field(ge=0, le=8, description="row * 3 + column")
    player_id: str = Field(min_length=1, max_length=200, description="an id from /api/grid/players, never a name")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_router(store: Optional[GridStore] = None, throttled: Optional[Callable[..., Any]] = None,
                 clock: Callable[[], datetime] = _utc_now) -> APIRouter:
    """The Grid router. `throttled` is the app's per-client dependency, applied to guesses and reveals: the two
    routes that say anything about answers. `clock` exists so a test can stand on either side of midnight UTC."""
    store = store or GridStore()
    router = APIRouter(prefix="/api/grid", tags=["grid"])
    limited = [Depends(throttled)] if throttled else []

    def published(number: int) -> dict[str, Any]:
        try:
            return store.get(number, clock())
        except UnknownPuzzle as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

    @router.get("/today", summary="today's puzzle: the clues, no answers")
    def today() -> dict[str, Any]:
        now = clock()
        try:
            return GridStore.public(store.today(now), now)
        except UnknownPuzzle as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

    @router.get("/archive", summary="every published puzzle, newest first")
    def archive() -> dict[str, Any]:
        now = clock()
        return {"puzzles": [
            {"number": p["number"], "date": p["date"], "is_today": view["is_today"],
             "difficulty": view["difficulty"], "kind": view["kind"],
             "rows": [r["label"] for r in p["rows"]], "cols": [c["label"] for c in p["cols"]]}
            for p in store.published(now) for view in (GridStore.public(p, now),)
        ]}

    @router.get("/players", summary="name search for the guess box")
    def players(q: str = Query(default="", max_length=60)) -> dict[str, Any]:
        return {"query": q, "players": store.search(q)}

    @router.get("/{number}", summary="a published puzzle: the clues, no answers")
    def puzzle(number: int) -> dict[str, Any]:
        return GridStore.public(published(number), clock())

    @router.post("/{number}/guess", summary="check one player in one cell", dependencies=limited)
    def guess(number: int, body: GuessRequest) -> dict[str, Any]:
        published(number)
        try:
            return store.guess(number, body.cell, body.player_id, clock())
        except BadGuess as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

    @router.get("/{number}/reveal", summary="a few example answers per cell, for the end of a game",
                dependencies=limited)
    def reveal(number: int) -> dict[str, Any]:
        published(number)
        return store.reveal(number, clock())

    return router
