"""FaceitClient behaviour with a mocked transport: retries, raw sink, pagination."""

import json

import httpx
import pytest

from owcsmuse.config import Settings
from owcsmuse.faceit.client import FaceitClient, FaceitClientError, FaceitNotFound, FaceitRetryExhausted
from owcsmuse.faceit.ratelimit import AdaptiveRateLimiter


class ListSink:
    def __init__(self):
        self.rows = []

    def store(self, **kw):
        self.rows.append(kw)
        return len(self.rows)


def make_settings(**kw) -> Settings:
    base = dict(faceit_api_key="test-key", database_url="postgresql://unused", max_retries=3, backoff_base_seconds=0.01, backoff_cap_seconds=0.02)
    base.update(kw)
    return Settings(_env_file=None, **base)


def make_client(handler, settings=None, sink=None):
    settings = settings or make_settings()
    slept = []   # backoff sleeps only; the limiter's pacing sleeps are kept separate
    limiter = AdaptiveRateLimiter(clock=lambda: 0.0, sleep=lambda s: None)
    client = FaceitClient(settings, sink=sink, transport=httpx.MockTransport(handler), limiter=limiter,
                          sleep=lambda s: slept.append(s))
    return client, slept


RL = {"ratelimit-limit": "20, 20;w=1", "ratelimit-remaining": "19", "ratelimit-reset": "0"}


def test_retries_429_and_5xx_then_succeeds_and_stores_every_response():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        n = len(calls)
        if n == 1:
            return httpx.Response(429, headers={**RL, "ratelimit-remaining": "0", "Retry-After": "0"}, json={"e": 1})
        if n == 2:
            return httpx.Response(502, headers=RL, text="bad gateway")
        return httpx.Response(200, headers=RL, json={"match_id": "m1"})

    sink = ListSink()
    client, slept = make_client(handler, sink=sink)
    res = client.get("/matches/m1", match_id="m1")

    assert res.status == 200 and res.payload == {"match_id": "m1"} and res.raw_id == 3
    assert calls[0].headers["Authorization"] == "Bearer test-key"
    assert [r["http_status"] for r in sink.rows] == [429, 502, 200]
    assert sink.rows[1]["payload"] is None and sink.rows[1]["body_text"] == "bad gateway"
    assert all(r["match_id"] == "m1" and r["endpoint"] == "/matches/m1" for r in sink.rows)
    assert len(slept) >= 2  # backed off after each failure


def test_404_raises_not_found_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404, headers=RL, json={"errors": [{"message": "not found"}]})

    client, _ = make_client(handler)
    with pytest.raises(FaceitNotFound):
        client.get("/matches/nope")
    assert len(calls) == 1


def test_other_4xx_raises_client_error_without_retry():
    def handler(request):
        return httpx.Response(400, headers=RL, json={"errors": [{"code": "err_br0"}]})

    client, _ = make_client(handler)
    with pytest.raises(FaceitClientError) as ei:
        client.get("/championships/x/matches", {"offset": 600, "limit": 100})
    assert ei.value.status == 400 and not isinstance(ei.value, FaceitNotFound)


def test_retries_exhausted():
    def handler(request):
        return httpx.Response(503, headers=RL)

    client, slept = make_client(handler, settings=make_settings(max_retries=2))
    with pytest.raises(FaceitRetryExhausted):
        client.get("/matches/m1")
    assert len(slept) == 2


def test_pagination_stops_at_short_page():
    def handler(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        assert limit == 100
        items = [{"i": offset + k} for k in range(100 if offset < 200 else 14)]
        return httpx.Response(200, headers=RL, json={"items": items, "start": offset, "end": offset + limit})

    client, _ = make_client(handler)
    res = client.list_all("/championships/c1/matches", {"type": "all"})
    assert len(res.items) == 214 and res.pages == 3 and res.truncated is False


def test_pagination_respects_offset_cap_and_flags_truncation():
    seen = []

    def handler(request):
        offset = int(request.url.params["offset"])
        seen.append(offset)
        assert offset <= 500, "client must never request past FACEIT's offset cap"
        return httpx.Response(200, headers=RL, json={"items": [{"i": offset + k} for k in range(100)]})

    client, _ = make_client(handler)
    res = client.list_all("/championships/big/matches", {"type": "all"})
    assert seen == [0, 100, 200, 300, 400, 500]
    assert len(res.items) == 600 and res.truncated is True


def test_pagination_uses_configured_page_size():
    def handler(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        assert limit == 20 and offset % limit == 0
        return httpx.Response(200, headers=RL, json={"items": [] if offset >= 40 else [{"i": 1}] * 20})

    client, _ = make_client(handler, settings=make_settings(page_size=20, max_offset=500))
    res = client.list_all("/x")
    assert len(res.items) == 40 and res.pages == 3 and res.truncated is False


def test_request_log_is_structured(caplog):
    def handler(request):
        return httpx.Response(200, headers=RL, json={"ok": True})

    client, _ = make_client(handler)
    with caplog.at_level("INFO", logger="owcsmuse.faceit"):
        client.get("/organizers/o1")
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "faceit_request")
    fields = rec.fields
    assert fields["endpoint"] == "/organizers/o1" and fields["status"] == 200
    assert fields["ratelimit_remaining"] == 19 and fields["ratelimit_limit"] == 20
    assert isinstance(fields["latency_ms"], float)
    json.dumps(fields, default=str)  # serialisable for the JSON formatter
