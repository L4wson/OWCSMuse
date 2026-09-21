"""Test doubles for the Liquipedia layer: an in-memory Store and a mock transport that records every request."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from owcsmuse.liquipedia import LiquipediaClient


class MemoryStore:
    """Same contract as PgStore, in a list. Cache hits leave no row, exactly as with the real one."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.coverage: dict[tuple[str, str, str], dict[str, Any]] = {}

    def cached(self, endpoint, params):
        for r in reversed(self.rows):
            p = r["payload"]
            if (r["endpoint"] == endpoint and r["params"] == params and r["status"] == 200 and p is not None
                    and not (isinstance(p, dict) and p.get("error"))):
                return {"id": r["id"], "payload": p, "headers": r["headers"], "fetched_at": r["fetched_at"]}
        return None

    def save(self, endpoint, params, status, payload, body_text, headers, fetched_at):
        rid = len(self.rows) + 1
        self.rows.append({"id": rid, "endpoint": endpoint, "params": dict(params), "status": status, "payload": payload,
                          "body_text": body_text, "headers": dict(headers), "fetched_at": fetched_at})
        return rid

    def used_in_window(self, now, window):
        inside = [r["fetched_at"] for r in self.rows if r["fetched_at"] > now - window]
        return len(inside), (min(inside) if inside else None)

    def last_rate_limit(self):
        hits = [r for r in self.rows if r["status"] == 429]
        if not hits:
            return None
        r = hits[-1]
        try:
            ra = float(r["headers"].get("retry-after"))
        except (TypeError, ValueError):
            ra = None
        return r["fetched_at"], ra

    def covered(self, endpoint, field, values):
        return {v: self.coverage[(endpoint, field, v)] for v in values if (endpoint, field, v) in self.coverage}

    def mark_covered(self, endpoint, field, entries, raw_ids):
        for e in entries:
            self.coverage[(endpoint, field, e["value"])] = {"value": e["value"], "rows_seen": e.get("rows_seen"),
                                                            "raw_ids": list(raw_ids)}


class Clock:
    def __init__(self, start: Optional[datetime] = None) -> None:
        self.now = start or datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        self.slept: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: Any) -> None:
        self.now += timedelta(**kw)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


class Wire:
    """A mock Liquipedia. `respond(request) -> httpx.Response`; every request that reaches it is recorded."""

    def __init__(self, respond: Optional[Callable[[httpx.Request], httpx.Response]] = None) -> None:
        self.requests: list[httpx.Request] = []
        self.respond = respond or (lambda req: httpx.Response(200, json={"result": []}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def rows_response(n: int, **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"result": [{"match2id": f"m{i}", **extra} for i in range(n)]},
                          headers={"x-ratelimit-remaining": "50"})


def make_client(wire: Wire, store: Optional[MemoryStore] = None, clock: Optional[Clock] = None, *,
                key: Optional[str] = "SECRET-KEY-123", budget: int = 60, min_interval: float = 0.0):
    store = store if store is not None else MemoryStore()
    clock = clock or Clock()
    client = LiquipediaClient(key, store, hourly_budget=budget, min_interval=min_interval, http=wire.client(),
                              clock=clock, sleep=clock.sleep)
    return client, store, clock


def query_of(req: httpx.Request) -> dict[str, str]:
    return dict(req.url.params)


def body_of(x: Any) -> str:
    return json.dumps(x, default=str)
