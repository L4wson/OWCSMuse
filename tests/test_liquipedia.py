"""The Liquipedia client, planner, runner and attribution, offline: a mock transport records every request, so a test
can assert not only what was sent but that nothing else was.
"""

from __future__ import annotations

import httpx
import pytest
from liquipedia_support import MemoryStore, Wire, body_of, make_client, query_of, rows_response

from owcsmuse import liquipedia as LP
from owcsmuse.liquipedia import (BudgetExhausted, LiquipediaDisabled, LiquipediaHalted, LiquipediaHTTPError,
                                 LiquipediaNotConfigured, LiquipediaRateLimited, MissingAttribution, Sourced,
                                 attribution_block, page_url, plan_requests, run_plan)
from owcsmuse.liquipedia.planner import ConditionError, or_conditions
from owcsmuse.liquipedia.stage1 import describe_shape

KEY = "SECRET-KEY-123"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv(LP.ENABLE_ENV, "1")


# ---------------------------------------------------------------------- the guard

def test_nothing_is_sent_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv(LP.ENABLE_ENV, raising=False)
    wire = Wire()
    client, store, _ = make_client(wire)
    with pytest.raises(LiquipediaDisabled) as ei:
        client.get("match", {"limit": 1})
    assert LP.ENABLE_ENV in str(ei.value)
    assert wire.requests == [] and store.rows == []
    monkeypatch.setenv(LP.ENABLE_ENV, "1")
    assert LP.requests_enabled()
    client.get("match", {"limit": 1})
    assert len(wire.requests) == 1


def test_a_missing_key_is_refused_before_anything_is_sent():
    wire = Wire()
    client, _, _ = make_client(wire, key=None)
    with pytest.raises(LiquipediaNotConfigured):
        client.get("match", {"limit": 1})
    assert wire.requests == []


def test_only_the_api_is_ever_contacted_and_no_html_is_parsed():
    wire = Wire()
    client, _, _ = make_client(wire)
    client.get("match", {"limit": 1})
    assert {r.url.host for r in wire.requests} == {"api.liquipedia.net"}
    assert wire.requests[0].url.path == "/api/v3/match"
    src = "".join(open(p, encoding="utf-8").read() for p in
                  (LP.client.__file__, LP.planner.__file__, LP.runner.__file__, LP.store.__file__))
    for bad in ("BeautifulSoup", "html.parser", "lxml", "action=parse", "index.php"):
        assert bad not in src


# ---------------------------------------------------------------------- credentials

def test_the_key_is_sent_as_the_authorization_header_and_never_stored():
    wire = Wire(lambda req: httpx.Response(200, json={"result": [{"a": 1}]}, headers={"x-ratelimit-remaining": "9"}))
    client, store, _ = make_client(wire)
    client.get("match", {"conditions": "[[date::>2026-01-01]]", "limit": 3})
    req = wire.requests[0]
    assert req.headers["authorization"] == f"Apikey {KEY}"
    assert KEY not in str(req.url)                                   # not in the URL
    assert "gmail" not in req.headers["user-agent"] and "OWCSMuse" in req.headers["user-agent"]
    stored = body_of(store.rows)
    assert KEY not in stored and "authorization" not in stored.lower()   # nor in anything kept
    assert store.rows[0]["headers"]["x-ratelimit-remaining"] == "9"      # response headers ARE kept
    assert query_of(req) == {"wiki": "overwatch", "conditions": "[[date::>2026-01-01]]", "limit": "3"}


# ---------------------------------------------------------------------- never re-request

def test_a_request_already_held_is_answered_from_the_store_and_costs_nothing():
    wire = Wire(lambda req: rows_response(2))
    client, store, _ = make_client(wire)
    first = client.get("match", {"limit": 2})
    again = client.get("match", {"limit": 2})
    assert not first.from_cache and again.from_cache and again.raw_id == first.raw_id
    assert len(wire.requests) == 1 and len(store.rows) == 1
    client.get("match", {"limit": 3})                                 # different question: a real request
    assert len(wire.requests) == 2


def test_the_cache_survives_a_new_client_and_still_works_with_the_budget_spent():
    wire = Wire(lambda req: rows_response(1))
    store = MemoryStore()
    a, _, clock = make_client(wire, store, budget=1)
    a.get("match", {"limit": 1})
    b, _, _ = make_client(wire, store, clock, budget=1)              # a fresh process, same database
    assert b.get("match", {"limit": 1}).from_cache                   # held: free even though 1/1 is spent
    with pytest.raises(BudgetExhausted):
        b.get("match", {"limit": 2})
    assert len(wire.requests) == 1


def test_an_error_answer_is_stored_but_never_reused_as_data():
    calls = iter([httpx.Response(200, json={"error": ["bad condition"]}), rows_response(1)])
    wire = Wire(lambda req: next(calls))
    client, store, _ = make_client(wire)
    with pytest.raises(LiquipediaHTTPError):
        client.get("match", {"limit": 1})
    assert len(store.rows) == 1                                      # the failure is recorded (it cost a request)
    assert not client.get("match", {"limit": 1}).from_cache          # and is not served as the answer
    assert len(wire.requests) == 2


# ---------------------------------------------------------------------- the budget

def test_the_hourly_budget_is_enforced_from_stored_history_and_frees_as_requests_age_out():
    wire = Wire(lambda req: rows_response(1))
    client, store, clock = make_client(wire, budget=3)
    for i in range(3):
        clock.advance(minutes=1)
        client.get("match", {"limit": i + 1})
    assert client.budget_state()["remaining"] == 0
    with pytest.raises(BudgetExhausted) as ei:
        client.get("match", {"limit": 99})
    assert ei.value.used == 3 and ei.value.budget == 3 and ei.value.resumes_at is not None
    assert len(wire.requests) == 3                                    # the fourth never left
    clock.advance(minutes=58)                                         # now the first request is an hour old, the others not
    assert client.budget_state()["remaining"] == 1
    client.get("match", {"limit": 99})
    assert len(wire.requests) == 4


def test_requests_are_spaced_by_the_minimum_interval_but_the_first_is_not_delayed():
    wire = Wire(lambda req: rows_response(1))
    client, _, clock = make_client(wire, min_interval=2.0)
    client.get("match", {"limit": 1})
    assert clock.slept == []
    client.get("match", {"limit": 2})
    assert len(clock.slept) == 1 and 0 < clock.slept[0] <= 2.0


def test_a_timeout_still_counts_against_the_budget():
    def boom(req):
        raise httpx.ConnectTimeout("timed out")
    wire = Wire(boom)
    client, store, _ = make_client(wire, budget=5)
    with pytest.raises(LiquipediaHTTPError) as ei:
        client.get("match", {"limit": 1})
    assert ei.value.status == 0 and store.rows[0]["status"] == 0
    assert client.budget_state()["used"] == 1                         # it may have reached them, so it is counted


# ---------------------------------------------------------------------- 429: one strike

def test_a_429_stops_immediately_with_no_retry_and_blocks_further_requests():
    wire = Wire(lambda req: httpx.Response(429, json={"error": "slow down"}, headers={"retry-after": "120"}))
    client, store, clock = make_client(wire)
    with pytest.raises(LiquipediaRateLimited):
        client.get("match", {"limit": 1})
    assert len(wire.requests) == 1                                    # exactly one: no retry, no backoff
    assert store.rows[0]["status"] == 429 and store.rows[0]["headers"]["retry-after"] == "120"
    assert clock.slept == []                                          # and it did not sleep and try again
    # while the 429 is in effect nothing is sent, for any question
    with pytest.raises(LiquipediaHalted):
        client.get("match", {"limit": 2})
    assert len(wire.requests) == 1
    clock.advance(seconds=121)                                        # Retry-After has passed
    wire.respond = lambda req: rows_response(1)
    assert client.get("match", {"limit": 2}).rows
    assert len(wire.requests) == 2


def test_a_429_without_retry_after_blocks_for_an_hour():
    wire = Wire(lambda req: httpx.Response(429, json={}))
    client, _, clock = make_client(wire)
    with pytest.raises(LiquipediaRateLimited):
        client.get("match", {"limit": 1})
    clock.advance(minutes=59)
    with pytest.raises(LiquipediaHalted):
        client.get("match", {"limit": 2})
    clock.advance(minutes=2)
    wire.respond = lambda req: rows_response(1)
    client.get("match", {"limit": 2})


def test_a_429_in_the_middle_of_a_plan_stops_the_whole_run():
    seen = []

    def respond(req):
        seen.append(req)
        return httpx.Response(429, json={}) if len(seen) == 2 else rows_response(1)
    wire = Wire(respond)
    client, store, _ = make_client(wire)
    plan = _plan(store, wants={"A": 1, "B": 1, "C": 1}, max_chars=30)           # three one-value batches
    assert plan.projected_requests == 3
    res = run_plan(client, plan)
    assert res.outcome == "rate_limited" and res.stopped_by == "429"
    assert len(wire.requests) == 2 and res.requests_sent == 2         # the third batch was never attempted
    assert res.batches_done == 1                                      # and the 429'd batch is not marked covered
    assert set(store.coverage) == {("match", "parent", "A")}


def test_any_other_failure_also_stops_the_run_without_retrying():
    wire = Wire(lambda req: httpx.Response(500, text="oops"))
    client, store, _ = make_client(wire)
    res = run_plan(client, _plan(store, wants={"A": 1, "B": 1}, max_chars=30))
    assert res.outcome == "failed" and len(wire.requests) == 1
    assert store.rows[0]["status"] == 500 and store.rows[0]["body_text"] == "oops"


# ---------------------------------------------------------------------- planning

def _plan(store, wants, limit=100, max_chars=1400, budget=None, **kw):
    return plan_requests(store, endpoint="match", field_name="parent", wants=wants, limit=limit, budget=budget,
                         max_condition_chars=max_chars, **kw)


def test_conditions_are_batched_into_as_few_queries_as_the_url_allows():
    wants = {f"Overwatch_Champions_Series/2026/Stage_{i}": 40 for i in range(1, 21)}
    one = _plan(MemoryStore(), wants, limit=1000, max_chars=100000)
    assert len(one.batches) == 1 and one.projected_requests == 1        # 800 rows fit one request
    assert set(one.batches[0].values) == set(wants)
    capped = _plan(MemoryStore(), wants, limit=1000, max_chars=400)
    assert len(capped.batches) > 1
    assert all(len(b.conditions) <= 400 for b in capped.batches)
    assert sorted(v for b in capped.batches for v in b.values) == sorted(wants)   # nothing lost, nothing repeated


def test_projected_requests_follow_expected_rows_and_the_page_limit():
    p = _plan(MemoryStore(), {"A": 250, "B": 300}, limit=100, max_chars=100000)
    assert p.batches[0].expected_rows == 550 and p.projected_requests == 6
    assert _plan(MemoryStore(), {"A": 0}, limit=100).projected_requests == 1     # a query is at least one request
    assert _plan(MemoryStore(), {}, limit=100).projected_requests == 0


def test_what_is_already_covered_is_not_planned_again_even_when_the_wanted_set_grows():
    store = MemoryStore()
    store.mark_covered("match", "parent", [{"value": "A"}, {"value": "B"}], [1])
    p = _plan(store, {"A": 50, "B": 50, "C": 50})
    assert p.held == ["A", "B"] and [b.values for b in p.batches] == [("C",)]
    assert p.projected_requests == 1
    assert _plan(store, {"A": 50, "B": 50, "C": 50}, refresh=True).projected_requests == 2   # 150 rows at 100 a page
    assert sorted(_plan(store, {"A": 50, "B": 50}, refresh=True).batches[0].values) == ["A", "B"]
    assert _plan(store, {"A": 50, "B": 50}).projected_requests == 0


def test_the_plan_reports_what_the_budget_allows_now_and_what_waits():
    p = _plan(MemoryStore(), {"A": 900}, limit=100, budget={"budget": 60, "used": 55, "remaining": 5})
    assert p.projected_requests == 9 and p.runnable_now == 5 and p.deferred == 4
    text = p.render()
    assert "PROJECTED REQUESTS: 9" in text and "4 would wait" in text
    assert p.as_dict()["projected_requests"] == 9


def test_a_value_that_could_break_a_condition_is_refused():
    for bad in ("a]]b", "a::b", "", "a\nb", "[[x"):
        with pytest.raises(ConditionError):
            or_conditions("parent", [bad])
    assert or_conditions("parent", ["A", "B"]) == "([[parent::A]] OR [[parent::B]])"
    assert or_conditions("parent", ["A"], "[[date::>2025-01-01]]") == "([[parent::A]]) AND [[date::>2025-01-01]]"


# ---------------------------------------------------------------------- running

def test_a_run_pages_until_a_short_page_and_records_coverage_only_when_the_batch_is_whole():
    pages = iter([rows_response(2, parent="A"), rows_response(2, parent="B"), rows_response(1, parent="B")])
    wire = Wire(lambda req: next(pages))
    client, store, _ = make_client(wire)
    plan = _plan(store, {"A": 3, "B": 2}, limit=2, max_chars=100000)
    res = run_plan(client, plan)
    assert res.outcome == "complete" and res.requests_sent == 3 and res.rows == 5
    assert [query_of(r).get("offset") for r in wire.requests] == [None, "2", "4"]
    assert store.coverage[("match", "parent", "A")]["rows_seen"] == 2
    assert store.coverage[("match", "parent", "B")]["rows_seen"] == 3
    # replanned, nothing is left to fetch: the ledger is what makes "never re-request" true across runs
    assert _plan(store, {"A": 3, "B": 2}).projected_requests == 0


def test_a_rerun_after_the_budget_ran_out_resumes_and_repeats_nothing():
    wire = Wire(lambda req: rows_response(1))
    client, store, clock = make_client(wire, budget=2)
    plan = _plan(store, {"A": 1, "B": 1, "C": 1, "D": 1}, max_chars=30)
    first = run_plan(client, plan)
    assert first.outcome == "budget" and first.batches_done == 2 and len(wire.requests) == 2
    clock.advance(hours=1, minutes=1)
    plan2 = _plan(store, {"A": 1, "B": 1, "C": 1, "D": 1}, max_chars=30, budget=client.budget_state())
    assert plan2.held == ["A", "B"] and plan2.projected_requests == 2
    second = run_plan(client, plan2)
    assert second.outcome == "complete" and len(wire.requests) == 4     # 2 + 2, not 2 + 4


def test_a_batch_that_returns_far_fewer_rows_than_expected_is_flagged():
    wire = Wire(lambda req: rows_response(1))
    client, store, _ = make_client(wire)
    res = run_plan(client, _plan(store, {"A": 100}))
    assert res.short_batches == [{"values": 1, "expected": 100, "got": 1}]


# ---------------------------------------------------------------------- attribution

def test_page_urls_are_built_from_the_page_name_and_never_guessed():
    assert page_url("Overwatch Champions Series/2026/EMEA/Stage 2") == \
        "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2"
    assert page_url("Team_Liquid") == "https://liquipedia.net/overwatch/Team_Liquid"
    assert page_url("Bjørn Ålesund?", wiki="overwatch").startswith("https://liquipedia.net/overwatch/Bj%C3%B8rn_")
    for missing in (None, "", "   "):
        with pytest.raises(MissingAttribution):
            page_url(missing)


def test_a_liquipedia_value_cannot_exist_without_its_page_url():
    ok = Sourced(value=3, page_url=page_url("Team_Liquid"), raw_id=7)
    assert ok.value == 3 and ok.page_url.startswith("https://liquipedia.net/")
    for bad in ("", None, "https://example.com/Team_Liquid", "liquipedia.net/overwatch/x"):
        with pytest.raises(MissingAttribution):
            Sourced(value=3, page_url=bad)


def test_attribution_is_sorted_deduplicated_and_names_the_licence():
    a, b = page_url("B_Page"), page_url("A_Page")
    block = attribution_block([a, b, a, ""])
    assert block["pages"] == [b, a] and block["source"] == "Liquipedia" and block["license"] == "CC-BY-SA 3.0"
    assert attribution_block([]) is None                              # an answer that used none carries none
    with pytest.raises(MissingAttribution):
        attribution_block(["https://example.com/x"])
    text = "\n".join(LP.render_lines(block))
    assert "CC-BY-SA 3.0" in text and b in text and LP.render_lines(None) == []


# ---------------------------------------------------------------------- the verification report

def test_the_shape_report_finds_the_faceit_id_and_where_it_sits():
    fid = "1-7553f194-b7d7-4bc9-bda4-3484592e014f"
    payload = {"result": [{"match2id": "x", "pagename": "Some_Page", "links": {"faceit": f"https://faceit.com/room/{fid}"},
                           "extradata": {"other": 1}}]}
    shape = describe_shape(payload, 200, {"x-ratelimit-remaining": "58", "server": "s"}, 5, 400)
    assert shape["faceit_match_ids_found"] == [fid] and shape["where_faceit_id_appears"] == ["links"]
    assert shape["rows_returned"] == 1 and shape["response_headers"] == {"x-ratelimit-remaining": "58"}


# ---------------------------------------------------------------------- answers carry the credit

def test_an_answer_built_from_liquipedia_values_prints_and_serialises_its_credit():
    from owcsmuse.nlq.pipeline import Answer, render_text
    plain = Answer(status="ok", question="q", description="d", sentence={"text": "s", "spans": []})
    assert plain.attribution is None and "Liquipedia" not in render_text(plain)   # no Liquipedia value, no credit line
    block = attribution_block([page_url("Overwatch_Champions_Series/2026/EMEA/Stage_2")])
    a = Answer(status="ok", question="q", description="d", sentence={"text": "s", "spans": []}, attribution=block)
    text = render_text(a)
    assert "Liquipedia (CC-BY-SA 3.0" in text and "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/EMEA/Stage_2" in text
    assert a.as_dict()["attribution"]["pages"] == block["pages"]


# ---------------------------------------------------------------------- the key is never kept

def test_a_response_that_quotes_the_key_back_is_scrubbed_before_it_is_stored_raised_or_logged(caplog):
    """Liquipedia's 403 says: API key "<the key>" is not valid. That once landed in raw_payloads and on screen."""
    def respond(req):
        return httpx.Response(403, json={"error": [f'API key "{KEY}" is not valid.'], "result": []},
                              headers={"x-echo": f"key={KEY}"})
    wire = Wire(respond)
    client, store, _ = make_client(wire)
    with caplog.at_level("DEBUG"):
        with pytest.raises(LiquipediaHTTPError) as ei:
            client.get("match", {"limit": 1})
    assert ei.value.status == 403 and "not valid" in str(ei.value)
    assert KEY not in str(ei.value)                                    # not in what is raised (and so not on screen)
    assert KEY not in body_of(store.rows) and LP.client.REDACTED in body_of(store.rows)   # nor in what is stored
    assert KEY not in caplog.text                                      # nor in the logs
    assert store.rows[0]["status"] == 403                              # the failure itself is still recorded
    # a non-JSON body is scrubbed the same way
    wire.respond = lambda req: httpx.Response(500, text=f"boom {KEY}")
    with pytest.raises(LiquipediaHTTPError) as ei2:
        client.get("match", {"limit": 2})
    assert KEY not in str(ei2.value) and KEY not in body_of(store.rows)
