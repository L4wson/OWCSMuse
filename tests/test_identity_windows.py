"""Date-bounded team-to-org mapping: a team id is an org only inside its window, and itself outside it."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from owcsmuse.limitations import entity_match_filter
from owcsmuse.nlq.membership import team_history
from owcsmuse.orgs import OrgDecisions, TeamFacts, load_decisions, propose_window

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

T = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ------------------------------------------------------------------ pure: the proposal and the decision file

def _team(names):
    return TeamFacts(team_id="t1", name=names[-1][0], names=[(n, T + timedelta(days=a), T + timedelta(days=b))
                                                           for n, a, b in names])


def test_a_window_is_proposed_from_the_first_sighting_of_the_orgs_name():
    team = _team([("Ex Oblivione", 0, 100), ("Virtuspro", 400, 500)])
    w = propose_window(team, "Virtus pro")
    assert w and w["valid_from"] == (T + timedelta(days=400)).isoformat(timespec="seconds") and w["valid_to"] is None
    assert "Ex Oblivione" in w["basis"] and "Virtuspro" in w["basis"]


def test_no_window_when_every_name_was_the_orgs():
    assert propose_window(_team([("Team Peps", 0, 100), ("Peps", 200, 300)]), "Team Peps") is None   # generic token
    assert propose_window(_team([("Dhillducks", 0, 100), ("DhillDucks", 200, 300)]), "Dhillducks") is None


def test_a_later_foreign_name_does_not_cut_the_window():
    """The rule is about what came BEFORE the org's name; what comes after is a rename the org made."""
    assert propose_window(_team([("Virtuspro", 0, 100), ("Something Else", 200, 300)]), "Virtus pro") is None


def test_decisions_carry_windows_and_round_trip(tmp_path):
    d = OrgDecisions(tmp_path / "d.json")
    d.set("t1", "virtus-pro", "Virtus pro", valid_from="2025-01-01T00:00:00+00:00")
    d.set("t2", "virtus-pro", "Virtus pro")
    d.save()
    again = OrgDecisions(tmp_path / "d.json")
    assert again.get("t1")["valid_from"] == "2025-01-01T00:00:00+00:00" and again.get("t1").get("valid_to") is None
    assert again.get("t2").get("valid_from") is None


def test_the_committed_virtus_pro_window_is_the_one_g11_and_g13_rest_on():
    d = json.load(open("scope/org_decisions.json", encoding="utf-8"))["decisions"]
    bb = next(v for k, v in d.items() if k.startswith("bb5dd404"))
    assert bb["org_id"] == "virtus-pro" and bb["valid_from"] == "2025-01-31T19:17:07+00:00"
    assert bb["valid_from_name"] == "Virtuspro"                                  # sourced from the first sighting, not chosen
    ext = {k[:8]: v for k, v in d.items() if v["org_id"] == "extinction"}
    assert ext["2b7f8ef6"]["valid_from_name"] == "Extinction" and ext["2b7f8ef6"].get("valid_to_name") is None
    assert (ext["a35f8d47"]["valid_from_name"], ext["a35f8d47"]["valid_to_name"]) == ("Extinction", "The Kafe")
    others = [v for k, v in d.items() if not k.startswith("bb5dd404") and v["org_id"] != "extinction"]
    assert not any(v.get("valid_from") or v.get("valid_to") or v.get("valid_from_name") for v in others)   # the rest are unbounded


# ------------------------------------------------------------------ the warehouse

def _one_team(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT f.team_id, t.name, min(f.started_at) AS first_at, max(f.started_at) AS last_at,
                   count(DISTINCT f.match_id) AS matches
              FROM fact_team_matches f JOIN teams t ON t.team_id = f.team_id
             GROUP BY f.team_id, t.name ORDER BY count(*) DESC, f.team_id LIMIT 1""")
        return cur.fetchone()


def _keys(conn, team_id):
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT org_key, display_name FROM fact_team_matches WHERE team_id = %s", [team_id])
        return {(r["org_key"], r["display_name"]) for r in cur.fetchall()}


def _series_for(conn, role_id, role_type):
    sql, params = entity_match_filter(role_id, role_type)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM matches m WHERE {sql}", params)
        return cur.fetchone()["n"]


@needs_db
def test_outside_its_window_a_team_id_is_itself_by_the_name_it_carried(agg_db):
    team = _one_team(agg_db)
    after = team["last_at"] + timedelta(days=1)
    try:
        with agg_db.cursor() as cur:
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('test-era', 'Test Era Org')")
            cur.execute("INSERT INTO team_orgs (team_id, org_id, valid_from) VALUES (%s, 'test-era', %s)",
                        [team["team_id"], after])
        # every series predates the window: the org gets none of them, the team keeps them under its own name
        assert _keys(agg_db, team["team_id"]) == {(f"team:{team['team_id']}", team["name"])}
        assert _series_for(agg_db, "test-era", "org") == 0
        assert _series_for(agg_db, team["team_id"], "team") == team["matches"]
        with agg_db.cursor() as cur:                                   # identity NOW says mapped: the window is open-ended
            cur.execute("SELECT mapped, org_key FROM team_identity WHERE team_id = %s", [team["team_id"]])
            assert cur.fetchone()["mapped"] is True
            cur.execute("SELECT display_name FROM identity_keys WHERE org_key = %s", [f"team:{team['team_id']}"])
            assert cur.fetchone()["display_name"] == team["name"]
            cur.execute("REFRESH MATERIALIZED VIEW entity_names")
            cur.execute("SELECT entity_type, name_kind, matches FROM entity_names WHERE entity_id = %s", [team["team_id"]])
            rows = cur.fetchall()
        assert any(r["entity_type"] == "team" and r["name_kind"] == "current_name" and r["matches"] == team["matches"]
                   for r in rows), rows                                 # searchable as a team of its own era
        # move the window to cover everything: now the org owns the series and the team entity disappears
        with agg_db.cursor() as cur:
            cur.execute("UPDATE team_orgs SET valid_from = %s WHERE team_id = %s", [team["first_at"] - timedelta(days=1), team["team_id"]])
        assert _keys(agg_db, team["team_id"]) == {("test-era", "Test Era Org")}
        assert _series_for(agg_db, "test-era", "org") == team["matches"]
        assert _series_for(agg_db, team["team_id"], "team") == 0
        with agg_db.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW entity_names")
            cur.execute("SELECT count(*) AS n FROM entity_names WHERE entity_id = %s AND entity_type = 'team'", [team["team_id"]])
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT matches FROM entity_names WHERE entity_type = 'org' AND entity_id = 'test-era' AND name_kind = 'current_name'")
            assert cur.fetchone()["matches"] == team["matches"]
    finally:
        agg_db.rollback()


@needs_db
def test_a_team_id_cannot_belong_to_two_orgs_at_once(agg_db):
    team = _one_team(agg_db)
    try:
        with agg_db.cursor() as cur:
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('test-a', 'A'), ('test-b', 'B')")
            cur.execute("INSERT INTO team_orgs (team_id, org_id, valid_from, valid_to) VALUES (%s, 'test-a', '2024-01-01', '2025-01-01')",
                        [team["team_id"]])
            with pytest.raises(Exception, match="overlaps"):
                cur.execute("INSERT INTO team_orgs (team_id, org_id, valid_from) VALUES (%s, 'test-b', '2024-06-01')", [team["team_id"]])
    finally:
        agg_db.rollback()
    try:                                                                # adjacent windows are fine
        with agg_db.cursor() as cur:
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('test-a', 'A'), ('test-b', 'B')")
            cur.execute("INSERT INTO team_orgs (team_id, org_id, valid_from, valid_to) VALUES (%s, 'test-a', '2024-01-01', '2025-01-01')",
                        [team["team_id"]])
            cur.execute("INSERT INTO team_orgs (team_id, org_id, valid_from) VALUES (%s, 'test-b', '2025-01-01')", [team["team_id"]])
    finally:
        agg_db.rollback()


@needs_db
def test_team_membership_is_read_at_series_time(agg_db):
    team = _one_team(agg_db)
    with agg_db.cursor() as cur:
        cur.execute("SELECT player_id FROM match_rosters WHERE team_id = %s LIMIT 1", [team["team_id"]])
        player = cur.fetchone()["player_id"]
    try:
        with agg_db.cursor() as cur:
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('test-era', 'Test Era Org')")
            cur.execute("INSERT INTO team_orgs (team_id, org_id, valid_from) VALUES (%s, 'test-era', %s)",
                        [team["team_id"], team["last_at"] + timedelta(days=1)])
        stints = team_history(agg_db, player)
        assert all(s["team"] != "Test Era Org" for s in stints if s["team_id"] == team["team_id"])
        with agg_db.cursor() as cur:
            cur.execute("UPDATE team_orgs SET valid_from = '2000-01-01' WHERE team_id = %s", [team["team_id"]])
        stints = team_history(agg_db, player)
        assert any(s["team"] == "Test Era Org" for s in stints)
    finally:
        agg_db.rollback()


@needs_db
def test_load_writes_windows_and_the_check_flags_a_window_that_covers_nothing(agg_db, tmp_path):
    from owcsmuse.consistency import run_checks

    team = _one_team(agg_db)
    d = OrgDecisions(tmp_path / "d.json")
    d.set(team["team_id"], "test-load", "Test Load", valid_from=(team["last_at"] + timedelta(days=30)).isoformat())
    try:
        out = load_decisions(agg_db, d)
        assert out["team_ids_mapped"] == 1
        with agg_db.cursor() as cur:
            cur.execute("SELECT valid_from, valid_to::text AS valid_to FROM team_orgs WHERE team_id = %s", [team["team_id"]])
            row = cur.fetchone()
        assert row["valid_from"] == team["last_at"] + timedelta(days=30) and row["valid_to"] == "infinity"
        r = {c.name: c for c in run_checks(agg_db, ["identity_windows"])}["identity_windows"]
        assert not r.ok and any(x["kind"] == "window_covers_no_series" for x in r.discrepancies)
        d.set(team["team_id"], "test-load", "Test Load", valid_from=(team["first_at"] - timedelta(days=1)).isoformat())
        load_decisions(agg_db, d)
        r = {c.name: c for c in run_checks(agg_db, ["identity_windows"])}["identity_windows"]
        assert r.ok and r.counts["bounded"] == 1
    finally:
        load_decisions(agg_db, OrgDecisions(tmp_path / "empty.json"))     # back to no mappings, orphan org removed
        with agg_db.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM team_orgs")
            assert cur.fetchone()["n"] == 0
        agg_db.commit()
