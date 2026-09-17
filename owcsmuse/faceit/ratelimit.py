"""Adaptive rate limiting and retry backoff for the FACEIT Data API.

FACEIT currently answers with IETF-style headers::

    ratelimit-limit: 20, 20;w=1
    ratelimit-remaining: 18
    ratelimit-reset: 0

Older documentation describes ``X-RateLimit-Limit`` / ``X-RateLimit-Remaining``
/ ``X-RateLimit-Reset``. Both forms are parsed. The limiter paces requests to
``window / limit`` and pauses until the window resets whenever ``remaining``
drops to the configured headroom. 429 and 5xx responses use exponential backoff
with full jitter, honouring ``Retry-After`` when present.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

_INT_RE = re.compile(r"-?\d+")
_WINDOW_RE = re.compile(r"w=(\d+)")


@dataclass(frozen=True)
class RateLimitInfo:
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_seconds: Optional[float] = None  # seconds until the window resets
    window_seconds: float = 1.0
    retry_after: Optional[float] = None

    @property
    def has_data(self) -> bool:
        return self.limit is not None or self.remaining is not None


def _first_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    m = _INT_RE.search(value)
    return int(m.group()) if m else None


def _reset_to_seconds(value: Optional[str], now: float) -> Optional[float]:
    """Reset headers are either seconds-until-reset or an epoch timestamp."""
    n = _first_int(value)
    if n is None:
        return None
    if n > 1_000_000_000_000:  # epoch milliseconds
        return max(0.0, n / 1000.0 - now)
    if n > 1_000_000_000:  # epoch seconds
        return max(0.0, n - now)
    return float(max(0, n))


def parse_rate_limit_headers(headers: Mapping[str, str], now: Optional[float] = None) -> RateLimitInfo:
    now = time.time() if now is None else now
    lower = {k.lower(): v for k, v in headers.items()}

    limit_raw = lower.get("x-ratelimit-limit", lower.get("ratelimit-limit"))
    remaining_raw = lower.get("x-ratelimit-remaining", lower.get("ratelimit-remaining"))
    reset_raw = lower.get("x-ratelimit-reset", lower.get("ratelimit-reset"))

    window = 1.0
    if limit_raw:
        wm = _WINDOW_RE.search(limit_raw)
        if wm:
            window = float(wm.group(1))

    retry_after = None
    ra = lower.get("retry-after")
    if ra:
        n = _first_int(ra)
        if n is not None:
            retry_after = float(n)

    return RateLimitInfo(
        limit=_first_int(limit_raw),
        remaining=_first_int(remaining_raw),
        reset_seconds=_reset_to_seconds(reset_raw, now),
        window_seconds=window,
        retry_after=retry_after,
    )


def backoff_delay(
    attempt: int,
    base: float = 0.5,
    cap: float = 60.0,
    rng: Callable[[], float] = random.random,
) -> float:
    """Exponential backoff with full jitter: uniform(0, min(cap, base * 2**attempt))."""
    ceiling = min(cap, base * (2 ** max(0, attempt)))
    return ceiling * rng()


class AdaptiveRateLimiter:
    """Paces requests from observed rate-limit headers.

    `clock` and `sleep` are injectable for tests.
    """

    def __init__(
        self,
        headroom: int = 2,
        default_per_second: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.headroom = headroom
        self.clock = clock
        self.sleep = sleep
        self.min_interval = 1.0 / default_per_second if default_per_second > 0 else 0.0
        self.last_request_at: Optional[float] = None
        self.blocked_until: Optional[float] = None
        self.last_info: Optional[RateLimitInfo] = None

    def wait(self) -> float:
        """Block until a request may be sent. Returns seconds slept."""
        now = self.clock()
        target = now
        if self.blocked_until is not None and self.blocked_until > target:
            target = self.blocked_until
        if self.last_request_at is not None:
            target = max(target, self.last_request_at + self.min_interval)
        slept = 0.0
        if target > now:
            slept = target - now
            self.sleep(slept)
        self.last_request_at = self.clock()
        self.blocked_until = None
        return slept

    def observe(self, info: RateLimitInfo, status_code: int) -> None:
        """Update pacing from a response's headers."""
        self.last_info = info
        if info.limit and info.limit > 0:
            self.min_interval = info.window_seconds / info.limit
        now = self.clock()
        if status_code == 429:
            delay = info.retry_after if info.retry_after is not None else (info.reset_seconds or info.window_seconds)
            self.blocked_until = now + max(delay, info.window_seconds)
        elif info.remaining is not None and info.remaining <= self.headroom:
            delay = info.reset_seconds if info.reset_seconds is not None else info.window_seconds
            # reset=0 means "this window"; wait the whole window out to be safe.
            self.blocked_until = now + max(delay, info.window_seconds)
