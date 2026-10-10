"""The HTTP layer, and the property that matters most about it: the evidence adds up.

An aggregate nobody can check is a claim. These tests page through the evidence
rows of a real answer and reconcile them against the aggregate they were
supposed to explain, then cover the three endpoints and their failure modes.
"""

import os

import pytest

fastapi = pytest.importorskip("fastapi", reason="the api extra is not installed")
from fastapi.testclient import TestClient  # noqa: E402

from owcsmuse.api import ConnectionPool, create_app, json_safe  # noqa: E402
from owcsmuse.config import Settings  # noqa: E402
from owcsmuse.web import normalize_question, slug_for  # noqa: E402


@pytest.fixture(scope="module")
def client(agg_db):
    """An app pointed at the same scratch schema the fixtures were ingested into."""
    settings = Settings(_env_file=None, faceit_api_key="not-used",
                        database_url=os.environ["OWCS_TEST_DATABASE_URL"],
                        db_schema=os.environ.get("OWCS_TEST_SCHEMA", "owcs_test"))
    app = create_app(settings, ConnectionPool(settings, size=2))
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def pairing(agg_db):
    """Two players who actually faced each other in the fixtures, most-played pair first."""
    with agg_db.cursor() as cur:
        cur.execute("""
            SELECT a.nickname AS a, b.nickname AS b, count(*) AS maps
              FROM fact_player_versus v
              JOIN players a ON a.player_id = v.player_id
              JOIN players b ON b.player_id = v.opponent_player_id
             GROUP BY a.nickname, b.nickname ORDER BY count(*) DESC, a.nickname LIMIT 1""")
        row = cur.fetchone()
    agg_db.commit()
    if not row:
        pytest.skip("the fixtures have no player-vs-player maps")
    return row["a"], row["b"]


@pytest.fixture(scope="module")
def never_met(agg_db):
    """Two players with no map in common: the fixtures span two competitions."""
    with agg_db.cursor() as cur:
        cur.execute("""
            SELECT a.nickname AS a, b.nickname AS b
              FROM (SELECT DISTINCT player_id FROM fact_player_maps) x
              CROSS JOIN (SELECT DISTINCT player_id FROM fact_player_maps) y
              JOIN players a ON a.player_id = x.player_id
              JOIN players b ON b.player_id = y.player_id
             WHERE x.player_id <> y.player_id
               AND NOT EXISTS (SELECT 1 FROM fact_player_versus v
                                WHERE v.player_id = x.player_id AND v.opponent_player_id = y.player_id)
             ORDER BY a.nickname, b.nickname LIMIT 1""")
        row = cur.fetchone()
    agg_db.commit()
    if not row:
        pytest.skip("every fixture player faced every other")
    return row["a"], row["b"]


def _ask(client, question, **body):
    r = client.post("/ask", json={"question": question, **body})
    assert r.status_code == 200, r.text
    return r.json()


def _all_evidence(client, question, **body):
    """Every evidence row, page by page, so the totals can be checked."""
    first = _ask(client, question, page=1, page_size=25, **body)
    ev = first["evidence"] or {"rows": []}
    rows = list(ev["rows"])
    page = 1
    while ev.get("has_more"):
        page += 1
        nxt = _ask(client, question, page=page, page_size=25, **body)
        ev = nxt["evidence"]
        rows += ev["rows"]
    return first, rows


# ------------------------------------------------------- evidence reconciliation

def test_versus_evidence_rows_add_up_to_the_versus_record(client, pairing):
    a, b = pairing
    answer, rows = _all_evidence(client, f"{a} map record against {b}")
    assert answer["status"] == "ok", answer.get("reason")
    assert answer["evidence"]["grain"] == "map"
    agg = answer["aggregate"]["rows"][0]
    assert len(rows) == agg["maps"] == answer["evidence"]["total_rows"]
    assert sum(1 for r in rows if r["result"] == "won") == agg["map_wins"]
    assert sum(1 for r in rows if r["result"] == "lost") == agg["map_losses"]
    assert len({r["match_id"] for r in rows}) == agg["matches"]
    assert {r["season"] for r in rows} <= set(agg["seasons"])


def test_a_stat_answer_carries_the_maps_that_sum_to_it(client):
    answer, rows = _all_evidence(client, "KSAA eliminations")
    if answer["status"] != "ok":
        pytest.skip(answer.get("reason") or "no data for the fixture player")
    agg = answer["aggregate"]["rows"][0]
    assert len(rows) == answer["evidence"]["total_rows"]
    assert sum(r["eliminations"] or 0 for r in rows) == agg["total"]
    assert all(r.get("stat_key") == "Eliminations" for r in rows)
    assert sum(1 for r in rows if r.get("stat_value") is not None) == agg["maps_with_stat"]


def test_a_team_record_is_evidenced_at_series_grain(client):
    answer, rows = _all_evidence(client, "Twisted Minds record")
    if answer["status"] != "ok":
        pytest.skip("no team data in the fixtures")
    agg = answer["aggregate"]["rows"][0]
    assert answer["evidence"]["grain"] == "series"
    assert len(rows) == agg["matches"]
    assert sum(1 for r in rows if r["result"] == "won") == agg["wins"]
    assert all(r["round_number"] is None for r in rows)          # a series row is not a map row
    assert all("map_stats_recorded" in r for r in rows)          # result_only series are visible as such


def test_evidence_is_newest_first_and_paged(client):
    answer = _ask(client, "KSAA eliminations", page=1, page_size=2)
    ev = answer["evidence"]
    assert ev["available"] and ev["page_size"] == 2 and len(ev["rows"]) <= 2
    dates = [r["played_at"] for r in ev["rows"] if r["played_at"]]
    assert dates == sorted(dates, reverse=True)
    if ev["total_rows"] > 2:
        assert ev["has_more"] and ev["total_pages"] >= 2
        second = _ask(client, "KSAA eliminations", page=2, page_size=2)["evidence"]
        assert {r["match_id"] + str(r["round_number"]) for r in second["rows"]} != \
               {r["match_id"] + str(r["round_number"]) for r in ev["rows"]}


def test_every_evidence_row_links_to_its_faceit_match(client):
    answer = _ask(client, "KSAA eliminations", page_size=5)
    rows = answer["evidence"]["rows"]
    assert rows
    for r in rows:
        assert r["match_url"].endswith(r["match_id"])
        assert r["competition"] and r["played_at"]


def test_a_leaderboard_row_expands_to_the_maps_behind_it(client):
    answer = _ask(client, "who had the most eliminations", page_size=5)
    ev = answer["evidence"]
    assert ev["expandable_by"] == "player_id"
    top = answer["aggregate"]["rows"][0]
    assert ev["expanded_for"]["id"] == top["player_id"]          # the claim's own row by default
    other = answer["aggregate"]["rows"][-1]
    if other["player_id"] != top["player_id"]:
        expanded = _ask(client, "who had the most eliminations", evidence_for=other["player_id"], page_size=5)
        assert expanded["evidence"]["expanded_for"]["id"] == other["player_id"]
        assert expanded["evidence"]["total_rows"] == other["maps_played"]


def test_a_pairing_that_never_met_says_so_and_offers_no_rows(client, never_met):
    a, b = never_met
    answer = _ask(client, f"{a} map record against {b}")
    assert answer["status"] == "cannot_answer" and answer["code"] == "no_data"
    # these two were teammates (2 series on one line-up), never opposed: said as that since 042, not "never faced"
    assert "never on opposite sides" in answer["reason"]
    assert answer["notes"] == []                       # nothing was excluded, so nothing is claimed
    assert not (answer["evidence"] or {}).get("rows")


def test_the_missing_series_query_runs_against_the_real_schema(agg_db, pairing):
    """The proof for an empty map record: executed here, exercised on a pairing in the report.

    The fixtures hold no result_only series, so this asserts the query is valid
    and returns nothing rather than erroring - a column typo in it would show up
    as a failure here, not in production.
    """
    from owcsmuse.nlq.evidence import fetch_missing_series
    from owcsmuse.nlq.pipeline import resolve_entities
    from owcsmuse.nlq.parser import parse_question
    from owcsmuse.nlq.validate import SchemaInfo, validate

    q = parse_question(f"{pairing[0]} map record against {pairing[1]}")
    r, _ = resolve_entities(agg_db, q)
    v = validate(q, SchemaInfo.from_db(agg_db))
    ev = fetch_missing_series(agg_db, v, r)
    assert ev.available and ev.rows == [] and ev.grain == "series"
    assert ev.total_rows == 0 and ev.reason == "no rows match this slice"


def test_stat_availability_says_why_it_has_no_rows(client):
    answer = _ask(client, "what stats are available")
    assert answer["status"] == "ok" and answer["aggregate"]["rows"]
    assert answer["evidence"]["available"] is False
    assert "listing" in answer["evidence"]["reason"]


def test_evidence_can_be_switched_off(client):
    answer = _ask(client, "KSAA eliminations", with_evidence=False)
    assert answer["evidence"] is None and answer["aggregate"]["rows"]


# -------------------------------------------------------------------- endpoints

def test_ask_returns_a_sentence_an_aggregate_and_the_query_it_understood(client):
    answer = _ask(client, "who had the most eliminations in 2024")
    assert answer["status"] == "ok"
    assert answer["sentence"]["text"].endswith(".")
    assert answer["query"]["intent"] == "leaderboard"
    assert answer["query"]["filters"]["season"] == 2024
    assert answer["aggregate"]["columns"] and answer["aggregate"]["rows"]
    assert answer["slug"] and answer["url"] == f"/query/{answer['slug']}"
    assert isinstance(answer["limitations"], list)


def test_a_refusal_is_a_two_hundred_with_a_reason_and_a_sentence(client):
    answer = _ask(client, "who has the best hero pool")
    assert answer["status"] == "cannot_answer"
    assert answer["code"] == "unsupported_metric"
    assert answer["sentence"]["text"] and answer["reason"]
    assert answer["evidence"] is None


def test_the_slug_is_deterministic_and_shareable(client):
    first = _ask(client, "who had the most eliminations in 2024")
    again = _ask(client, "  WHO had the most  eliminations in 2024 ")
    assert first["slug"] == again["slug"] == slug_for("who had the most eliminations in 2024")
    assert normalize_question(" A  B ") == "a b"

    shared = client.get(f"/query/{first['slug']}")
    assert shared.status_code == 200
    body = shared.json()
    assert body["question"].lower().strip() == "who had the most eliminations in 2024"
    assert body["sentence"] == first["sentence"]                  # same data, same words
    assert body["shared"]["times_asked"] >= 1
    assert body["shared"]["parsed_when_saved"]["intent"] == "leaderboard"


def test_a_shared_link_takes_paging_parameters(client):
    slug = _ask(client, "KSAA eliminations")["slug"]
    r = client.get(f"/query/{slug}", params={"page": 1, "page_size": 3})
    assert r.status_code == 200
    assert r.json()["evidence"]["page_size"] == 3


def test_an_unknown_slug_is_a_404(client):
    r = client.get("/query/notaslug1234")
    assert r.status_code == 404 and "notaslug1234" in r.json()["detail"]


def test_suggestions_are_questions_that_have_data(client):
    r = client.get("/suggestions")
    assert r.status_code == 200
    body = r.json()
    assert body["groups"] and len(body["suggestions"]) >= 5
    for s in body["suggestions"]:
        assert s["question"] and s["group"] in body["groups"] and s["slug"]
    # the promise: a suggestion resolves to something, not to no_data
    answered = [_ask(client, s["question"])["status"] for s in body["suggestions"][:6]]
    assert all(status in ("ok", "clarify") for status in answered), answered


def test_healthz_and_root(client):
    assert client.get("/healthz").json()["ok"] is True
    root = client.get("/").json()
    assert root["service"] == "owcsmuse" and "POST /ask" in root["endpoints"]
    assert [lim["id"] for lim in root["limitations"]]


def test_a_malformed_request_is_refused_before_any_query(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "x" * 5000}).status_code == 422
    assert client.post("/ask", json={"nope": "x"}).status_code == 422
    assert client.post("/ask", json={"question": "hi", "page_size": 100000}).status_code == 422
    assert client.post("/ask", json={"question": "hi", "parser": "wizard"}).status_code == 422


def test_numbers_are_serialized_as_numbers(client):
    answer = _ask(client, "KSAA eliminations", page_size=3)
    row = answer["evidence"]["rows"][0]
    assert isinstance(row["eliminations"], int)
    assert isinstance(row["damage_dealt"], (int, float))
    assert json_safe({"a": [{"b": 1}]}) == {"a": [{"b": 1}]}

# ------------------------------------------------------- what the client needs

def test_every_table_arrives_described(client):
    """Columns come with a label and a type, so no client re-derives either."""
    answer = _ask(client, "who had the most eliminations", page_size=3)
    for block in (answer["aggregate"], answer["evidence"]):
        assert block["columns"], block
        for column in block["columns"]:
            assert set(column) <= {"key", "label", "type", "pair_key"}
            assert column["label"] and column["type"]
    types = {c["key"]: c["type"] for c in answer["evidence"]["columns"]}
    assert types["played_at"] == "date"
    assert types["score"] == "score"
    assert types["result"] == "result"
    assert types["match_url"] == "link"
    score = next(c for c in answer["evidence"]["columns"] if c["key"] == "score")
    assert score["pair_key"] == "opponent_score"


def test_a_ranked_row_names_its_own_entity(client):
    answer = _ask(client, "who had the most eliminations", page_size=5)
    for row in answer["aggregate"]["rows"]:
        entity = row["entity"]
        assert entity["id"] and entity["type"] == "player" and entity["name"]
        assert entity["column"] == answer["evidence"]["expandable_by"]
    # and that id is what expands it
    second = answer["aggregate"]["rows"][1]["entity"]["id"]
    expanded = _ask(client, "who had the most eliminations", evidence_for=second, page_size=3)
    assert expanded["evidence"]["expanded_for"]["id"] == second


def test_an_entity_object_is_not_offered_as_a_column(client):
    answer = _ask(client, "who had the most eliminations", page_size=3)
    assert "entity" not in {c["key"] for c in answer["aggregate"]["columns"]}
    assert "entity" in answer["aggregate"]["rows"][0]


def test_a_refusal_offers_questions_that_work_not_only_advice(client, never_met):
    """A resolved entity with no data in this slice yields a question that has some."""
    a, b = never_met
    answer = _ask(client, f"{a} map record against {b}")
    assert answer["status"] == "cannot_answer"
    assert answer["alternatives"], answer["reason"]
    assert answer["alternatives"] != [f"{a} map record against {b}"]      # never the question that just failed

    for alternative in answer["alternatives"]:
        retried = _ask(client, alternative)
        assert retried["status"] == "ok", (alternative, retried["reason"])


def test_advice_stays_where_advice_is_the_right_answer(client):
    """A typo has no better question to offer, so it gets the tip and no alternatives."""
    answer = _ask(client, "who has the best hero pool")
    assert answer["suggestions"] and not answer["alternatives"]


def test_a_stat_missing_from_one_season_offers_the_season_that_has_it(client):
    answer = _ask(client, "who had the most final blows in 2024")
    if answer["status"] == "ok":
        pytest.skip("the fixtures do carry Final Blows in 2024")
    assert answer["alternatives"], answer["reason"]
    assert any("2026" in alternative or "2025" in alternative for alternative in answer["alternatives"])


def test_a_shared_link_says_for_itself_whether_the_parse_changed(client):
    slug = _ask(client, "who had the most eliminations in 2024")["slug"]
    shared = client.get(f"/query/{slug}").json()["shared"]
    assert shared["parse_changed"] is False and shared["parse_change"] == []
    assert "parsed_when_saved" in shared      # still there, for anyone who wants the detail


def test_a_database_outage_is_a_503_on_every_endpoint():
    """Up but unable to read is not a refused question, and must not look like one."""
    from owcsmuse.api import ConnectionPool, create_app
    from owcsmuse.config import Settings

    dead = Settings(_env_file=None, faceit_api_key="not-used",
                    database_url="postgresql://nobody:nobody@127.0.0.1:59999/none", db_schema="public")
    app = create_app(dead, ConnectionPool(dead, size=1))
    with TestClient(app, raise_server_exceptions=False) as broken:
        for response in (broken.get("/healthz"),
                         broken.post("/ask", json={"question": "who had the most eliminations"}),
                         broken.get("/query/abcd1234")):
            assert response.status_code == 503, (response.request.url, response.status_code)
            assert "database" in response.json()["detail"]


def test_result_is_a_label_and_cannot_be_ranked(client):
    answer = _ask(client, "who had the most result")
    assert answer["status"] == "cannot_answer"
    assert answer["code"] in ("unsupported_metric", "no_data")
    availability = _ask(client, "what stats are available")
    kinds = {row["stat_key"]: row.get("stat_kind") for row in availability["aggregate"]["rows"]}
    if "Result" in kinds:
        assert kinds["Result"] == "non_numeric"


def test_no_suggestion_offers_a_label_as_a_metric(client):
    for suggestion in client.get("/suggestions").json()["suggestions"]:
        assert "result" not in suggestion["question"].lower()


@pytest.fixture(scope="module")
def two_players_in_different_matches(agg_db):
    """Two players with no match in common, so any shared evidence row is a leak."""
    with agg_db.cursor() as cur:
        cur.execute("""
            SELECT p.nickname, array_agg(DISTINCT f.match_id) AS matches
              FROM fact_player_maps f JOIN players p ON p.player_id = f.player_id
             GROUP BY p.nickname ORDER BY p.nickname""")
        rows = cur.fetchall()
    agg_db.commit()
    for a in rows:
        for b in rows:
            if a["nickname"] != b["nickname"] and not set(a["matches"]) & set(b["matches"]):
                return a["nickname"], set(a["matches"]), b["nickname"], set(b["matches"])
    pytest.skip("the fixtures have no two players who never shared a match")


def _evidence_matches(body: dict) -> set:
    return {row["match_id"] for row in (body["evidence"] or {}).get("rows", [])}


def test_one_answers_evidence_never_appears_in_the_next(client, two_players_in_different_matches):
    """Ask about one player, then another: the second answer holds only the second player's rows."""
    first, first_matches, second, second_matches = two_players_in_different_matches
    one = client.post("/ask", json={"question": f"{first}'s record", "page_size": 200}).json()
    two = client.post("/ask", json={"question": f"{second}'s record", "page_size": 200}).json()
    again = client.post("/ask", json={"question": f"{second}'s record", "page_size": 200}).json()

    assert one["status"] == two["status"] == "ok"
    assert _evidence_matches(one) and _evidence_matches(one) <= first_matches
    assert _evidence_matches(two) and _evidence_matches(two) <= second_matches
    assert not _evidence_matches(two) & first_matches
    # asking again, after the other player, gives the same rows as asking cold
    assert two["evidence"]["rows"] == again["evidence"]["rows"]
    assert two["evidence"]["total_rows"] == again["evidence"]["total_rows"]
