"""FACEIT Data API v4 client.

Responsibilities:
  * bearer auth, base URL, timeouts (httpx)
  * adaptive rate limiting from response headers
  * exponential backoff with jitter on 429 / 5xx / transport errors
  * structured log line for every request (endpoint, status, latency, remaining)
  * hand every response to a raw-payload sink so nothing has to be re-fetched
  * offset pagination that respects FACEIT's offset cap and reports truncation
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional, Protocol

import httpx

from ..config import Settings
from ..logging import get_logger, log_event
from .ratelimit import AdaptiveRateLimiter, backoff_delay, parse_rate_limit_headers

log = get_logger("owcsmuse.faceit")


class FaceitClientError(Exception):
    def __init__(self, status: int, endpoint: str, body: Any = None):
        super().__init__(f"FACEIT {status} on {endpoint}")
        self.status = status
        self.endpoint = endpoint
        self.body = body


class FaceitNotFound(FaceitClientError):
    pass


class FaceitRetryExhausted(FaceitClientError):
    pass


@dataclass
class FetchResult:
    endpoint: str
    params: dict[str, Any]
    status: int
    payload: Any
    raw_id: Optional[int]
    fetched_at: datetime


@dataclass
class ListResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    pages: int = 0
    truncated: bool = False
    raw_ids: list[int] = field(default_factory=list)


class RawPayloadSink(Protocol):
    def store(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        http_status: int,
        payload: Any,
        body_text: Optional[str],
        fetched_at: datetime,
        match_id: Optional[str] = None,
        championship_id: Optional[str] = None,
    ) -> Optional[int]: ...


class FaceitClient:
    def __init__(
        self,
        settings: Settings,
        sink: Optional[RawPayloadSink] = None,
        transport: Optional[httpx.BaseTransport] = None,
        limiter: Optional[AdaptiveRateLimiter] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.sink = sink
        self.sleep = sleep
        self.limiter = limiter or AdaptiveRateLimiter(
            headroom=settings.rate_limit_headroom,
            default_per_second=settings.default_rate_limit_per_second,
            sleep=sleep,
        )
        self.http = httpx.Client(
            base_url=settings.faceit_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.faceit_api_key.get_secret_value()}",
                "Accept": "application/json",
                "User-Agent": "owcsmuse/0.1",
            },
            timeout=settings.request_timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "FaceitClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ core

    def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        *,
        match_id: Optional[str] = None,
        championship_id: Optional[str] = None,
    ) -> FetchResult:
        params = dict(params or {})
        max_attempts = self.settings.max_retries + 1
        last_status: Optional[int] = None
        last_body: Any = None

        for attempt in range(max_attempts):
            self.limiter.wait()
            t0 = time.perf_counter()
            try:
                resp = self.http.get(endpoint, params=params)
            except httpx.TransportError as exc:
                latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                log_event(
                    log, logging.WARNING, "faceit_request_error",
                    endpoint=endpoint, params=params, attempt=attempt, latency_ms=latency_ms,
                    error=repr(exc),
                )
                if attempt + 1 >= max_attempts:
                    raise FaceitRetryExhausted(0, endpoint, repr(exc)) from exc
                self.sleep(self._backoff(attempt))
                continue

            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            fetched_at = datetime.now(timezone.utc)
            info = parse_rate_limit_headers(resp.headers)
            self.limiter.observe(info, resp.status_code)

            payload, body_text = _decode_body(resp)
            raw_id = None
            if self.sink is not None:
                raw_id = self.sink.store(
                    endpoint=endpoint,
                    params=params,
                    http_status=resp.status_code,
                    payload=payload,
                    body_text=body_text,
                    fetched_at=fetched_at,
                    match_id=match_id,
                    championship_id=championship_id,
                )

            log_event(
                log,
                logging.INFO if resp.status_code < 400 else logging.WARNING,
                "faceit_request",
                endpoint=endpoint,
                params=params,
                status=resp.status_code,
                latency_ms=latency_ms,
                attempt=attempt,
                ratelimit_limit=info.limit,
                ratelimit_remaining=info.remaining,
                ratelimit_reset=info.reset_seconds,
                raw_id=raw_id,
            )

            status = resp.status_code
            last_status, last_body = status, payload if payload is not None else body_text
            if status == 200:
                return FetchResult(endpoint, params, status, payload, raw_id, fetched_at)
            if status == 404:
                raise FaceitNotFound(status, endpoint, last_body)
            if status == 429 or status >= 500:
                if attempt + 1 >= max_attempts:
                    break
                delay = self._backoff(attempt)
                if info.retry_after is not None:
                    delay = max(delay, info.retry_after)
                log_event(log, logging.WARNING, "faceit_backoff", endpoint=endpoint, status=status,
                          attempt=attempt, sleep_seconds=round(delay, 3))
                self.sleep(delay)
                continue
            raise FaceitClientError(status, endpoint, last_body)

        raise FaceitRetryExhausted(last_status or 0, endpoint, last_body)

    def _backoff(self, attempt: int) -> float:
        return backoff_delay(attempt, self.settings.backoff_base_seconds, self.settings.backoff_cap_seconds)

    # ------------------------------------------------------------ pagination

    def iter_pages(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        *,
        championship_id: Optional[str] = None,
    ) -> Iterator[tuple[FetchResult, list[dict[str, Any]]]]:
        """Yield (fetch_result, items) per page until a short page or the offset cap."""
        limit = self.settings.page_size
        offset = 0
        while True:
            q = dict(params or {})
            q.update({"offset": offset, "limit": limit})
            res = self.get(endpoint, q, championship_id=championship_id)
            items = (res.payload or {}).get("items") or []
            yield res, items
            if len(items) < limit:
                return
            offset += limit
            if offset > self.settings.max_offset:
                log_event(log, logging.WARNING, "faceit_listing_truncated", endpoint=endpoint,
                          params=params, reached=offset)
                return

    def list_all(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        *,
        championship_id: Optional[str] = None,
    ) -> ListResult:
        out = ListResult()
        limit = self.settings.page_size
        last_len = 0
        for res, items in self.iter_pages(endpoint, params, championship_id=championship_id):
            out.items.extend(items)
            out.pages += 1
            if res.raw_id is not None:
                out.raw_ids.append(res.raw_id)
            last_len = len(items)
        # A full final page at the cap means there may be more we cannot reach.
        out.truncated = last_len == limit and (out.pages * limit) > self.settings.max_offset
        return out

    # ------------------------------------------------------------ endpoints

    def search_organizers(self, name: str) -> ListResult:
        return self.list_all("/search/organizers", {"name": name})

    def get_organizer(self, organizer_id: str) -> FetchResult:
        return self.get(f"/organizers/{organizer_id}")

    def list_organizer_championships(self, organizer_id: str) -> ListResult:
        return self.list_all(f"/organizers/{organizer_id}/championships")

    def search_championships(self, name: str, game: str = "ow2") -> ListResult:
        return self.list_all("/search/championships", {"name": name, "game": game})

    def get_championship(self, championship_id: str) -> FetchResult:
        return self.get(f"/championships/{championship_id}", championship_id=championship_id)

    def list_championship_matches(self, championship_id: str, match_type: str = "all") -> ListResult:
        return self.list_all(
            f"/championships/{championship_id}/matches",
            {"type": match_type},
            championship_id=championship_id,
        )

    def get_match(self, match_id: str) -> FetchResult:
        return self.get(f"/matches/{match_id}", match_id=match_id)

    def get_match_stats(self, match_id: str) -> FetchResult:
        return self.get(f"/matches/{match_id}/stats", match_id=match_id)


def _decode_body(resp: httpx.Response) -> tuple[Any, Optional[str]]:
    text = resp.text
    if not text:
        return None, None
    try:
        return json.loads(text), None
    except ValueError:
        return None, text
