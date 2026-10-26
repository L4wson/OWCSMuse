"""The HTTP API's protection: a token bucket per client IP, and a cap on database connections for everyone together."""

from __future__ import annotations

import os
import threading

import pytest

from owcsmuse.throttle import BUSY_MESSAGE, Throttle, client_key, rate_limited_message


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_a_client_gets_its_burst_then_waits_for_the_refill():
    clock = Clock()
    t = Throttle(burst=3, per_minute=30, clock=clock)            # one token every 2 s
    assert [t.check("a").allowed for _ in range(3)] == [True, True, True]
    v = t.check("a")
    assert not v.allowed and v.retry_after == 2
    clock.t += 2.0
    assert t.check("a").allowed and not t.check("a").allowed


def test_clients_are_counted_separately():
    t = Throttle(burst=1, per_minute=1, clock=Clock())
    assert t.check("a").allowed and not t.check("a").allowed
    assert t.check("b").allowed


def test_a_bucket_never_holds_more_than_the_burst_however_long_the_client_was_away():
    clock = Clock()
    t = Throttle(burst=2, per_minute=60, clock=clock)
    clock.t += 3600
    assert [t.check("a").allowed for _ in range(3)] == [True, True, False]


def test_idle_clients_are_forgotten_once_there_are_many():
    clock = Clock()
    t = Throttle(burst=1, per_minute=60, clock=clock, idle_forget_seconds=10, max_clients=3)
    for c in "abc":
        t.check(c)
    clock.t += 11
    t.check("d")
    t.check("e")
    assert set(t._buckets) <= {"d", "e"}


def test_the_client_is_fly_s_client_ip_and_otherwise_the_socket_peer():
    assert client_key({"fly-client-ip": "203.0.113.7"}, "10.0.0.1") == "203.0.113.7"
    assert client_key({}, "127.0.0.1") == "127.0.0.1"
    assert client_key({"fly-client-ip": " "}, None) == "unknown"


def test_the_messages_say_what_to_do():
    assert rate_limited_message(1) == "You are asking faster than OWCS Muse answers one person: wait 1 second and ask again."
    assert "wait 5 seconds" in rate_limited_message(5)
    assert "Try again in a few seconds" in BUSY_MESSAGE


# ------------------------------------------------------------------------------------------- through the app

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from owcsmuse.api import ConnectionPool, create_app  # noqa: E402
from owcsmuse.config import Settings  # noqa: E402


def _settings(**kw) -> Settings:
    url = os.environ.get("OWCS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("OWCS_TEST_DATABASE_URL not set")
    return Settings(_env_file=None, faceit_api_key="not-used", database_url=url,
                    db_schema=os.environ.get("OWCS_TEST_SCHEMA", "owcs_test"), **kw)


def test_a_client_over_its_limit_gets_a_429_that_says_how_long_to_wait(agg_db):
    s = _settings(api_rate_burst=2, api_rate_per_minute=6)
    with TestClient(create_app(s, ConnectionPool(s, size=1))) as c:
        me = {"Fly-Client-IP": "198.51.100.1"}
        assert [c.get("/suggestions", headers=me).status_code for _ in range(2)] == [200, 200]
        r = c.get("/suggestions", headers=me)
        assert r.status_code == 429
        assert r.headers["Retry-After"] == "10"
        assert r.json()["detail"] == rate_limited_message(10)
        # another client is unaffected, and so are liveness and the service description
        assert c.get("/suggestions", headers={"Fly-Client-IP": "198.51.100.2"}).status_code == 200
        assert all(c.get(p, headers=me).status_code == 200 for p in ("/healthz", "/", "/healthz"))
        # /ask and shared links draw on the same bucket
        assert c.post("/ask", json={"question": "Toronto Defiant record"}, headers=me).status_code == 429
        assert c.get("/query/abcdef", headers=me).status_code == 429


def test_when_every_connection_is_in_use_a_question_is_told_the_service_is_busy_and_liveness_stays_up(agg_db):
    s = _settings(api_rate_burst=100, api_db_max_connections=1, api_db_wait_seconds=0)
    pool = ConnectionPool(s, size=1)
    with TestClient(create_app(s, pool)) as c:
        held, release = threading.Event(), threading.Event()

        def hold():
            with pool.connection():
                held.set()
                release.wait(10)
        worker = threading.Thread(target=hold)
        worker.start()
        try:
            assert held.wait(10)
            r = c.post("/ask", json={"question": "Toronto Defiant record"})
            assert r.status_code == 503 and r.headers["Retry-After"] == "5"
            assert r.json()["detail"] == BUSY_MESSAGE and r.json()["reason"] == "busy"
            # busy is not down: Fly would restart a machine whose check failed
            h = c.get("/healthz")
            assert h.status_code == 200 and h.json()["busy"] is True
        finally:
            release.set()
            worker.join()
        assert c.get("/healthz").json() == {"ok": True, "version": c.get("/").json()["version"]}


def test_a_connection_that_failed_gives_its_slot_back(agg_db):
    s = _settings(api_db_max_connections=1, api_db_wait_seconds=0)
    pool = ConnectionPool(s, size=1)
    with pytest.raises(RuntimeError):
        with pool.connection():
            raise RuntimeError("the request failed")
    with pool.connection() as conn:            # the one slot is free again
        assert conn.execute("SELECT 1 AS x").fetchone()["x"] == 1
    pool.close()
