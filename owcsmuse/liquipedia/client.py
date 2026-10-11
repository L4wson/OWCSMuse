"""LiquipediaDB API v3 client: opt-in, budgeted, cached, and one strike on a 429.

The approved allowance is 60 requests per hour, so this client is built around
spending that allowance deliberately rather than politely retrying:

  * OWCS_LIQUIPEDIA_ENABLED must be set, or nothing is sent (the key alone is not
    consent to spend the budget);
  * a request already held in raw_payloads is answered from there and costs nothing;
  * the hourly budget is counted from raw_payloads itself, so it survives restarts
    and cannot be reset by starting a new process;
  * every response - success, error or 429 - is stored with its headers before
    anything else happens to it;
  * a 429 stops the run: no retry, no backoff, and while the last 429 is still
    inside its window (Retry-After, else an hour) nothing more is sent;
  * any other failure also stops the run. There is no automatic retry anywhere,
    because a retry spends budget on a request that just failed.

Only the API is used (`api.liquipedia.net`). Liquipedia's terms forbid automated
access to rendered pages, so nothing here fetches or parses HTML.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from ..log import get_logger, log_event
from .store import Store

log = get_logger("owcsmuse.liquipedia")

API_BASE = "https://api.liquipedia.net/api/v3"
USER_AGENT = "OWCSMuse/0.1 (https://github.com/L4wson/OWCSMuse; Overwatch stats warehouse)"
ENABLE_ENV = "OWCS_LIQUIPEDIA_ENABLED"
SOURCE = "liquipedia"
REDACTED = "[REDACTED-API-KEY]"
WINDOW = timedelta(hours=1)
DEFAULT_RATE_LIMIT_PAUSE = WINDOW       # how long a 429 blocks further requests when it names no Retry-After


class LiquipediaError(RuntimeError):
    """Base for everything this client refuses or fails at."""


class LiquipediaDisabled(LiquipediaError):
    """A request was attempted without the opt-in environment flag."""


class LiquipediaNotConfigured(LiquipediaError):
    """No API key is configured."""


class BudgetExhausted(LiquipediaError):
    """The hourly allowance is spent. Not a failure: the rest of a plan resumes when a request ages out."""

    def __init__(self, used: int, budget: int, resumes_at: Optional[datetime]):
        self.used, self.budget, self.resumes_at = used, budget, resumes_at
        when = resumes_at.isoformat(timespec="seconds") if resumes_at else "later"
        super().__init__(f"hourly budget spent ({used}/{budget} requests in the last hour); resumes {when}")


class LiquipediaRateLimited(LiquipediaError):
    """Liquipedia answered 429. The run stops; nothing is retried."""

    def __init__(self, raw_id: Optional[int], retry_after: Optional[float], blocked_until: datetime):
        self.raw_id, self.retry_after, self.blocked_until = raw_id, retry_after, blocked_until
        super().__init__(f"Liquipedia returned 429 (stored as raw_payloads.id={raw_id}); stopping without retry, "
                         f"nothing more is sent until {blocked_until.isoformat(timespec='seconds')}")


class LiquipediaHalted(LiquipediaError):
    """A previous 429 is still inside its window."""

    def __init__(self, blocked_until: datetime):
        self.blocked_until = blocked_until
        super().__init__(f"a previous 429 is still in effect until {blocked_until.isoformat(timespec='seconds')}; "
                         "no request was sent")


class LiquipediaHTTPError(LiquipediaError):
    def __init__(self, status: int, raw_id: Optional[int], detail: str):
        self.status, self.raw_id = status, raw_id
        super().__init__(f"Liquipedia returned HTTP {status} (stored as raw_payloads.id={raw_id}): {detail}")


def requests_enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled(what: str) -> None:
    if not requests_enabled():
        raise LiquipediaDisabled(
            f"refusing to send {what} to Liquipedia: set {ENABLE_ENV}=1 to allow requests. "
            "Every request spends part of a 60-per-hour allowance.")


@dataclass
class Fetched:
    """One answer: from the cache or from the wire, and the stored row it lives in."""

    endpoint: str
    params: dict[str, Any]
    payload: Any
    raw_id: int
    from_cache: bool
    status: int
    headers: dict[str, str]
    fetched_at: datetime

    @property
    def rows(self) -> list[dict[str, Any]]:
        return list((self.payload or {}).get("result") or [])


def _retry_after_seconds(headers: dict[str, str]) -> Optional[float]:
    v = headers.get("retry-after")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


class LiquipediaClient:
    def __init__(self, api_key: Optional[str], store: Store, *, base_url: str = API_BASE, wiki: str = "overwatch",
                 hourly_budget: int = 60, min_interval: float = 2.0, http: Optional[httpx.Client] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._key = api_key
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.wiki = wiki
        self.hourly_budget = hourly_budget
        self.min_interval = min_interval
        # The key travels only in the Authorization header, and response headers (never request headers) are what is
        # stored. The User-Agent is set per request too, so a caller-supplied client cannot send the API a default one.
        self.http = http or httpx.Client(timeout=60)   # a 500-row page is ~3 MB of JSON
        self._clock, self._sleep = clock, sleep
        self._last_sent: Optional[float] = None
        self.sent = 0                       # requests this process actually put on the wire

    # ---------------------------------------------------------------- budget

    def budget_state(self) -> dict[str, Any]:
        used, oldest = self.store.used_in_window(self._clock(), WINDOW)
        remaining = max(0, self.hourly_budget - used)
        return {"budget": self.hourly_budget, "used": used, "remaining": remaining,
                "resumes_at": (oldest + WINDOW) if (remaining == 0 and oldest) else None}

    def blocked_until(self) -> Optional[datetime]:
        last = self.store.last_rate_limit()
        if not last:
            return None
        at, retry_after = last
        until = at + (timedelta(seconds=retry_after) if retry_after else DEFAULT_RATE_LIMIT_PAUSE)
        return until if until > self._clock() else None

    def _scrub(self, value: Any) -> Any:
        """`value` with the API key replaced by a marker, wherever in it the key appears."""
        if not self._key or value is None:
            return value
        if isinstance(value, str):
            return value.replace(self._key, REDACTED)
        text = json.dumps(value, ensure_ascii=False)
        return json.loads(text.replace(self._key, REDACTED)) if self._key in text else value

    # ---------------------------------------------------------------- request

    def get(self, endpoint: str, params: dict[str, Any], fresh: bool = False) -> Fetched:
        """GET /{endpoint} with `params` (wiki is added). Cache first; otherwise one request, stored.

        `fresh` skips the cache: a page re-fetched because its matches were unfinished would otherwise be answered
        with the very response that showed them unfinished."""
        _require_enabled(f"GET /{endpoint}")
        params = {"wiki": self.wiki, **{k: v for k, v in params.items() if v is not None}}
        key_endpoint = endpoint.strip("/")

        held = None if fresh else self.store.cached(key_endpoint, params)
        if held:
            log_event(log, logging.INFO, "liquipedia_cache_hit", endpoint=key_endpoint, raw_id=held["id"])
            return Fetched(key_endpoint, params, held["payload"], held["id"], True, 200, held.get("headers") or {},
                           held["fetched_at"])

        if not self._key:
            raise LiquipediaNotConfigured("LIQUIPEDIA_API_KEY is not set")
        blocked = self.blocked_until()
        if blocked:
            raise LiquipediaHalted(blocked)
        state = self.budget_state()
        if state["remaining"] <= 0:
            raise BudgetExhausted(state["used"], state["budget"], state["resumes_at"])

        if self._last_sent is not None:
            wait = self.min_interval - (time.monotonic() - self._last_sent)
            if wait > 0:
                self._sleep(wait)

        url = f"{self.base_url}/{key_endpoint}"
        started = time.monotonic()
        self._last_sent = started
        self.sent += 1
        now = self._clock()
        try:
            resp = self.http.get(url, params=params, headers={"Authorization": f"Apikey {self._key}",
                                                                "User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        except httpx.HTTPError as exc:
            # It may have reached Liquipedia, so it counts against the budget: record it as status 0.
            raw_id = self.store.save(key_endpoint, params, 0, None, f"{type(exc).__name__}: {exc}", {}, now)
            raise LiquipediaHTTPError(0, raw_id, f"{type(exc).__name__}: {exc}") from exc

        # Liquipedia's own 403 body quotes the key back ('API key "..." is not valid'), so nothing that came off the wire
        # is stored, raised or logged before the key has been taken out of it.
        headers = {k.lower(): self._scrub(v) for k, v in resp.headers.items()}
        try:
            payload = self._scrub(resp.json())
            body_text = None
        except ValueError:
            payload, body_text = None, self._scrub(resp.text[:20000])
        raw_id = self.store.save(key_endpoint, params, resp.status_code, payload, body_text, headers, now)
        log_event(log, logging.INFO if resp.status_code == 200 else logging.ERROR, "liquipedia_request",
                  endpoint=key_endpoint, status=resp.status_code, latency_ms=int((time.monotonic() - started) * 1000),
                  raw_id=raw_id, bytes=len(resp.content),
                  ratelimit={k: v for k, v in headers.items() if "ratelimit" in k or k == "retry-after"})

        if resp.status_code == 429:
            retry_after = _retry_after_seconds(headers)
            raise LiquipediaRateLimited(raw_id, retry_after,
                                        now + (timedelta(seconds=retry_after) if retry_after else DEFAULT_RATE_LIMIT_PAUSE))
        if resp.status_code != 200:
            raise LiquipediaHTTPError(resp.status_code, raw_id, _error_text(payload, body_text))
        if isinstance(payload, dict) and payload.get("error"):
            # a 200 that says it failed: stored, but not cacheable (Store.cached ignores it)
            raise LiquipediaHTTPError(200, raw_id, _error_text(payload, body_text))
        return Fetched(key_endpoint, params, payload, raw_id, False, resp.status_code, headers, now)


def _error_text(payload: Any, body_text: Optional[str]) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])[:500]
    return (body_text or str(payload) or "")[:500]
