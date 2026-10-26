"""The query log: what a row holds, that writing one never costs an answer, and the report.

Offline: the API is driven with a fake connection pool and a stubbed `ask`, so
the property that matters - a log insert that fails must not fail the request -
is checked without a database.
"""

from contextlib import contextmanager

import pytest

from owcsmuse import querylog
from owcsmuse.nlq.pipeline import Answer
from owcsmuse.querylog import Logged, build_report, cluster, row_for, template


# ------------------------------------------------------------------ rows

def test_row_for_ok_answer():
    a = Answer(status="ok", question="zeruhh record", parser="rules",
               query={"intent": "entity_stat", "filters": {"player": "zeruhh"}},
               entities={"player": {"entity_type": "player", "entity_id": "p1", "current_name": "Zeruhh",
                                    "matches": 40, "seasons": [2025, 2026]}},
               rows=[{"maps": 3}, {"maps": 4}])
    r = row_for("zeruhh record", "ask", 120, a)
    assert r["status"] == "ok" and r["reason_code"] is None and r["row_count"] == 2
    assert r["structured_query"] == a.query
    # only which entity it was: no match counts, seasons or rewritten questions
    assert r["entities"] == {"player": {"type": "player", "id": "p1", "name": "Zeruhh"}}
    assert r["latency_ms"] == 120 and r["source"] == "ask"


def test_row_for_refusal_is_called_refusal():
    a = Answer(status="cannot_answer", question="who is the least picked hero", code="unsupported_question")
    r = row_for(a.question, "ask", 5, a)
    assert r["status"] == "refusal" and r["reason_code"] == "unsupported_question"
    assert r["structured_query"] is None and r["row_count"] is None and r["entities"] is None


def test_row_for_clarify_keeps_the_candidates():
    a = Answer(status="clarify", question="tea record", code="ambiguous_entity", query={"filters": {"subject": "tea"}},
               candidates={"subject": [{"entity_type": "team", "entity_id": "t1", "current_name": "Team A"},
                                       {"entity_type": "player", "entity_id": "p9", "current_name": "Tea"}]})
    r = row_for(a.question, "shared", 5, a)
    assert r["status"] == "clarify" and r["source"] == "shared"
    assert [c["id"] for c in r["entities"]["subject"]["candidates"]] == ["t1", "p9"]


def test_row_for_error():
    r = row_for("x", "ask", 9, error=TimeoutError("boom"))
    assert r["status"] == "error" and r["reason_code"] == "TimeoutError" and r["parser"] is None


def test_a_row_carries_nothing_about_the_asker():
    a = Answer(status="ok", question="q", rows=[{}])
    assert set(row_for("q", "ask", 1, a)) == {
        "source", "question", "parser", "status", "reason_code", "structured_query", "entities",
        "row_count", "latency_ms"}


# ---------------------------------------------------------------- record

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if "query_log" in sql and self.conn.fail_log:
            raise RuntimeError("relation \"query_log\" does not exist")
        self.conn.executed.append((sql, params))

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class FakeConn:
    closed = False
    broken = False

    def __init__(self, fail_log=False):
        self.fail_log = fail_log
        self.executed = []
        self.rolled_back = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        self.rolled_back += 1

    def logged(self):
        return [p for sql, p in self.executed if "INSERT INTO query_log" in sql]


def test_record_never_raises_and_rolls_back():
    conn = FakeConn(fail_log=True)
    assert querylog.record(conn, row_for("q", "ask", 1, error=ValueError())) is False
    assert conn.rolled_back == 1


def test_record_writes_one_row():
    conn = FakeConn()
    assert querylog.record(conn, row_for("  q  ", "ask", 1, Answer(status="ok", question="q", rows=[{}])))
    (params,) = conn.logged()
    assert params[0] == "ask" and params[1] == "q" and params[3] == "ok"


# ------------------------------------------------------------------- api

fastapi = pytest.importorskip("fastapi", reason="the api extra is not installed")
from fastapi.testclient import TestClient  # noqa: E402

from owcsmuse import api  # noqa: E402
from owcsmuse.config import Settings  # noqa: E402


class FakePool:
    def __init__(self, fail_log=False):
        self.conn = FakeConn(fail_log)

    @contextmanager
    def connection(self):
        yield self.conn

    def close(self):
        pass


@pytest.fixture
def app_with(monkeypatch):
    monkeypatch.setattr(api.SchemaInfo, "from_db", classmethod(lambda cls, conn: object()))
    monkeypatch.setattr(api, "remember_question", lambda conn, q, p, s: "slug1234")

    def make(answer_or_exc, fail_log=False):
        def fake_ask(conn, question, **kw):
            if isinstance(answer_or_exc, BaseException):
                raise answer_or_exc
            return answer_or_exc
        monkeypatch.setattr(api, "ask", fake_ask)
        pool = FakePool(fail_log)
        settings = Settings(_env_file=None, database_url="postgresql://unused")
        return TestClient(api.create_app(settings, pool), raise_server_exceptions=False), pool
    return make


def test_every_ask_is_logged_including_refusals(app_with):
    client, pool = app_with(Answer(status="cannot_answer", question="most banned hero", code="unsupported_question",
                                   reason="no hero bans"))
    r = client.post("/ask", json={"question": "most banned hero"})
    assert r.status_code == 200 and r.json()["status"] == "cannot_answer"
    (params,) = pool.conn.logged()
    assert params[1] == "most banned hero" and params[3] == "refusal" and params[4] == "unsupported_question"


def test_a_failing_log_insert_does_not_fail_the_answer(app_with):
    client, pool = app_with(Answer(status="ok", question="q", rows=[{"n": 1}]), fail_log=True)
    r = client.post("/ask", json={"question": "q"})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert pool.conn.logged() == [] and pool.conn.rolled_back == 1


def test_an_exception_is_logged_before_the_error_goes_out(app_with):
    client, pool = app_with(RuntimeError("compiler bug"))
    r = client.post("/ask", json={"question": "q"})
    assert r.status_code == 500
    (params,) = pool.conn.logged()
    assert params[3] == "error" and params[4] == "RuntimeError"


def test_a_dead_database_is_not_logged_and_still_answers_503(app_with):
    import psycopg
    client, pool = app_with(psycopg.OperationalError("server closed the connection"))
    pool.conn.broken = True
    r = client.post("/ask", json={"question": "q"})
    assert r.status_code == 503 and pool.conn.logged() == []


def test_a_shared_link_is_logged_as_shared(app_with, monkeypatch):
    from owcsmuse.web import SavedQuery
    monkeypatch.setattr(api, "load_question", lambda conn, slug: SavedQuery(slug=slug, question="q"))
    client, pool = app_with(Answer(status="ok", question="q", rows=[{}]))
    assert client.get("/query/slug1234").status_code == 200
    (params,) = pool.conn.logged()
    assert params[0] == "shared"


# ---------------------------------------------------------------- report

def _sq(**filters):
    return {"intent": "head_to_head", "filters": filters}


def test_template_masks_names_seasons_and_ids():
    it = Logged("Zeruhh series record against Sugarfree in 2026", "refusal", "no_data",
                _sq(player="zeruhh", opponent="sugarfree", season=2026))
    assert template(it) == "<player> series record against <opponent> in <season>"
    assert template(Logged("SSG vs player:7e75-ab", "clarify")) == "ssg vs <player>"


def test_cluster_groups_variants_of_one_failure():
    items = [
        Logged("who was the 2025 world champion", "refusal", "unsupported_question", asks=2),
        Logged("who was the 2025 world champ", "refusal", "unsupported_question"),
        Logged("who won the 2025 world finals", "refusal", "unsupported_question"),
        Logged("most banned hero in 2026", "refusal", "unsupported_question"),
        Logged("zeruhh record", "ok", row_count=1),
    ]
    clusters = cluster(items)
    top = clusters[0]
    assert top.asks == 4 and set(top.questions) == {
        "who was the 2025 world champion", "who was the 2025 world champ", "who won the 2025 world finals"}
    assert any(set(c.questions) == {"most banned hero in 2026"} for c in clusters)
    # an ok answer is never in a failure cluster
    assert all("zeruhh record" not in c.questions for c in clusters)


def test_cluster_never_mixes_reason_codes():
    items = [Logged("a b c", "refusal", "no_data"), Logged("a b c", "refusal", "unknown_entity")]
    assert len(cluster(items)) == 2


def test_report_sections():
    items = [
        Logged("Zeruhh record", "ok", row_count=1, asks=5),
        Logged("who is the least picked hero", "refusal", "unsupported_question", asks=3),
        Logged("ssg vs df in 20265", "refusal", "no_data", _sq(team="ssg", opponent="df"), asks=1),
        Logged("tea record", "clarify", "ambiguous_entity", _sq(subject="tea"), asks=2),
    ]
    r = build_report(items)
    assert r["asks"] == 11 and r["distinct_questions"] == 4
    assert r["by_status"] == {"ok": 5, "refusal": 4, "clarify": 2}
    assert [f["reason_code"] for f in r["failures_by_code"]] == ["unsupported_question", "ambiguous_entity", "no_data"]
    assert r["parsed_to_nothing"] == [{"question": "who is the least picked hero", "asks": 3}]
    assert r["no_rows"] == [{"question": "ssg vs df in 20265", "asks": 1}]
    assert r["most_asked"][0] == {"question": "zeruhh record", "asks": 5}
    assert r["most_asked_failed"][0] == {"question": "who is the least picked hero", "asks": 3}
    assert "Failures by reason code" in querylog.render_report(r)


def test_empty_report():
    assert querylog.render_report(build_report([])) == "no questions logged in this window"


def test_retention_keeps_failures_longer_than_answers(agg_db):
    """90 days for an answered question, a year for anything: failures are what the log is for."""
    from owcsmuse import querylog
    db = agg_db
    with db.cursor() as cur:
        cur.execute("DELETE FROM query_log")
        for status, days in (("ok", 10), ("ok", 100), ("refusal", 100), ("error", 400), ("ok", 400)):
            cur.execute("INSERT INTO query_log (asked_at, source, question, status, latency_ms) "
                        "VALUES (now() - make_interval(days => %s), 'ask', %s, %s, 1)", (days, f"{status} {days}", status))
    db.commit()
    out = querylog.prune(db)
    assert (out["ok_deleted"], out["older_deleted"]) == (2, 1)
    with db.cursor() as cur:
        cur.execute("SELECT question FROM query_log ORDER BY question")
        assert [r["question"] for r in cur.fetchall()] == ["ok 10", "refusal 100"]
