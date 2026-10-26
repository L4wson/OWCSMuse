"""Per-client request throttling for the HTTP API.

One shared-cpu machine answers every question against a small Supabase instance, so one client looping on /ask must
not be able to take the service from everyone else. Each client (by IP) has a token bucket: `burst` requests at once,
refilled at `per_minute`. The limits are set far above what a person asking questions does: across all traffic in the
query log (62 questions, 2026-10-17..26), the busiest windows were 4 questions in 10 seconds, 7 in a minute, 14 in ten
minutes, and an answer takes 2 s at the median. Paging through evidence or flipping the grain toggle is a request each,
so the burst is generous.

This bounds one client. The connection cap in owcsmuse.api.ConnectionPool bounds everyone together, which is what
keeps the database up when many clients (or many IPs) arrive at once.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

# Fly's proxy sets this to the address it accepted the connection from, replacing any value a client sent; the
# socket's peer is the proxy itself. Off Fly (local runs, tests) there is no such header and the peer is the client.
CLIENT_IP_HEADER = "fly-client-ip"


@dataclass
class Verdict:
    allowed: bool
    retry_after: int = 0          # whole seconds until one request is allowed again (0 when allowed)


class Throttle:
    """Token buckets keyed by client. Thread-safe; in memory, so per process (one machine runs one)."""

    def __init__(self, burst: int, per_minute: float, clock: Callable[[], float] = time.monotonic,
                 idle_forget_seconds: float = 600.0, max_clients: int = 10_000) -> None:
        if burst < 1 or per_minute <= 0:
            raise ValueError("a throttle needs a burst of at least 1 and a positive refill rate")
        self.burst = burst
        self.rate = per_minute / 60.0             # tokens per second
        self.clock = clock
        self.idle_forget = idle_forget_seconds
        self.max_clients = max_clients
        self._buckets: dict[str, tuple[float, float]] = {}   # client -> (tokens, at)
        self._lock = threading.Lock()

    def check(self, client: str) -> Verdict:
        now = self.clock()
        with self._lock:
            tokens, at = self._buckets.get(client, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - at) * self.rate)
            if tokens >= 1.0:
                self._buckets[client] = (tokens - 1.0, now)
                allowed, wait = True, 0
            else:
                self._buckets[client] = (tokens, now)
                allowed, wait = False, max(1, math.ceil((1.0 - tokens) / self.rate))
            if len(self._buckets) > self.max_clients:
                self._forget_idle(now)
        return Verdict(allowed, wait)

    def _forget_idle(self, now: float) -> None:
        """A bucket idle long enough is full again: dropping it changes nothing for that client."""
        stale = [k for k, (_, at) in self._buckets.items() if now - at > self.idle_forget]
        for k in stale:
            del self._buckets[k]


def client_key(headers: dict[str, str], peer: Optional[str]) -> str:
    return (headers.get(CLIENT_IP_HEADER) or "").strip() or peer or "unknown"


def rate_limited_message(retry_after: int) -> str:
    return (f"You are asking faster than OWCS Muse answers one person: wait {retry_after} second"
            f"{'' if retry_after == 1 else 's'} and ask again.")


BUSY_MESSAGE = "OWCS Muse is busy answering other questions right now. Try again in a few seconds."
