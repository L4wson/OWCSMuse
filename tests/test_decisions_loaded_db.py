"""decisions_loaded: a decision in scope/ that never reached its table, or a loaded row no decision explains, fails.

Each test writes its own small scope directory, loads it with the real loaders into the three-match fixture warehouse,
then breaks one side and asserts the exact discrepancy - kind, file and key - that the break must produce.
"""

from __future__ import annotations

import json
import os

import pytest

from agg_support import CH_2024, CH_2026, build_scratch_db
from owcsmuse import aliases, decisions_loaded, orgs
from owcsmuse.consistency import check_decisions_loaded
from owcsmuse.liquipedia import identity
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.scope import Decisions

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = "owcs_test_decisions_loaded"
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

UNKNOWN_TEAM = "00000000-0000-0000-0000-000000000000"


@pytest.fixture()
def loaded(tmp_path):
    conn, raw = build_scratch_db(DB_URL, SCHEMA)
    with conn.cursor() as cur:
        cur.execute("SELECT team_id FROM teams ORDER BY team_id LIMIT 2")
        t1, t2 = (r["team_id"] for r in cur.fetchall())
        cur.execute("SELECT player_id FROM players ORDER BY player_id LIMIT 1")
        p1 = cur.fetchone()["player_id"]
    conn.commit()
    scope = tmp_path / "scope"
    scope.mkdir()
    # the fixture's two championships are labelled 'manual': the file says so, with the values the rows carry
    sd = Decisions(scope / "decisions.json")
    sd.set(CH_2024, region="emea", tier="main", include=True, season=2024)
    sd.set(CH_2026, region="emea", tier="qualifier", include=True, season=2026)
    sd.save()
    od = orgs.OrgDecisions(scope / "org_decisions.json")
    od.set(t1, "org-a", "Org A")
    od.set(UNKNOWN_TEAM, "org-b", "Org B")                     # a team id this warehouse does not hold
    od.save()
    ad = aliases.AliasDecisions(scope / "alias_decisions.json")
    ad.set("oa", "org", "org-a")
    ad.save()
    tm = TeamMap(scope / "liquipedia_team_map.json")
    tm.decide("Team Two", "team", t2, "test")
    tm.save()
    pd = identity.PlayerDecisions(scope / "player_identity_decisions.json")
    pd.set("Some_Page", p1, "Some", "test")
    pd.save()
    (scope / "liquipedia_map.json").write_text(json.dumps({"pages": {}}), encoding="utf-8")
    orgs.load_decisions(conn, od)
    aliases.load_decisions(conn, ad)
    identity.load_identity(conn, pd, tm)
    yield conn, scope, {"t1": t1, "t2": t2, "p1": p1}
    conn.close()
    raw.close()


def _found(conn, scope):
    out, counts = decisions_loaded.check(conn, scope)
    conn.commit()
    return {(d["kind"], d["file"], json.dumps(d["key"])) for d in out}, counts


def _sql(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()


def test_everything_decided_and_loaded_passes_and_an_unknown_team_is_not_applicable(loaded):
    conn, scope, _ = loaded
    found, counts = _found(conn, scope)
    assert found == set()
    assert counts["files"]["org_decisions.json"] == {"decisions": 2, "not_applicable_here": 1}
    assert counts["files"]["player_identity_decisions.json"] == {"decisions": 1, "not_applicable_here": 0}


def test_a_decision_never_loaded_is_decided_not_loaded(loaded):
    conn, scope, ids = loaded
    _sql(conn, "DELETE FROM entity_anchors WHERE anchor_kind = 'player_page'")         # 166 identities, production
    _sql(conn, "DELETE FROM entity_aliases")
    found, _ = _found(conn, scope)
    assert found == {("decided_not_loaded", "scope/player_identity_decisions.json", '"Some_Page"'),
                     ("decided_not_loaded", "scope/alias_decisions.json", '"oa"')}


def test_a_loaded_row_no_decision_explains_is_loaded_not_decided(loaded):
    conn, scope, ids = loaded
    _sql(conn, "INSERT INTO entity_aliases (alias, entity_type, entity_id) VALUES ('ghost', 'team', %s)", (ids["t2"],))
    _sql(conn, "INSERT INTO team_orgs (team_id, org_id, source) VALUES (%s, 'org-a', 'manual')", (ids["t2"],))
    found, _ = _found(conn, scope)
    assert found == {("loaded_not_decided", "scope/alias_decisions.json", '"ghost"'),
                     ("loaded_not_decided", "scope/org_decisions.json", json.dumps([ids["t2"], "org-a"]))}


def test_a_stale_anchor_naming_another_entity_is_loaded_differs(loaded):
    # the production shape: `timeless` still anchored to an org after the file moved it to a team id
    conn, scope, ids = loaded
    _sql(conn, "UPDATE entity_anchors SET entity_type = 'org', entity_id = 'org-a' WHERE anchor = 'team two'")
    found, _ = _found(conn, scope)
    assert found == {("loaded_differs", "scope/liquipedia_team_map.json", '["team two", "", null]')}


def test_a_scope_decision_the_championship_row_does_not_carry_is_loaded_differs(loaded):
    conn, scope, _ = loaded
    _sql(conn, "UPDATE championships SET tier = 'main' WHERE championship_id = %s", (CH_2026,))
    found, _ = _found(conn, scope)
    assert found == {("loaded_differs", "scope/decisions.json", json.dumps(CH_2026))}


def test_the_check_names_the_loader_and_fails_through_check(loaded, monkeypatch):
    conn, scope, _ = loaded
    _sql(conn, "DELETE FROM entity_aliases")
    monkeypatch.setattr(decisions_loaded, "SCOPE", scope)
    monkeypatch.setattr(decisions_loaded.check, "__defaults__", (scope,))
    r = check_decisions_loaded(conn)
    conn.commit()
    assert not r.ok and r.discrepancy_count == 1
    assert r.discrepancies[0]["hint"] == "reload: python -m owcsmuse alias load"
