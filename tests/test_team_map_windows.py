"""A Liquipedia team name resolves at the series' own time; a team-to-org window can be sourced from a name's first sighting."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from owcsmuse.liquipedia.teams import TeamMap, make_resolver
from owcsmuse.orgs import OrgDecisions, load_decisions

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
T = datetime(2026, 1, 1, tzinfo=timezone.utc)
STAGE2 = datetime(2026, 6, 13, tzinfo=timezone.utc)


def _map(tmp_path):
    m = TeamMap(tmp_path / "map.json")
    m.decide("Extinction", "org", "extinction", "one org, two team ids over time")
    m.decide("The Kafe", "team", "a35f8d47", "its own era", valid_from=STAGE2.isoformat())
    m.data["old name"] = {"entity_type": "team", "note": "two team ids over time",
                          "eras": [{"entity_type": "team", "entity_id": "t2025", "valid_from": None, "valid_to": T.isoformat()},
                                   {"entity_type": "team", "entity_id": "t2026", "valid_from": T.isoformat(), "valid_to": None}]}
    m.save()
    return TeamMap(tmp_path / "map.json")


def test_a_name_resolves_to_the_era_covering_the_series_time(tmp_path):
    m = _map(tmp_path)
    assert m.find("Old Name", at=T - timedelta(days=1))["entity_id"] == "t2025"
    assert m.find("Old Name", at=T + timedelta(days=1))["entity_id"] == "t2026"
    assert m.find("Old Name", at=None)["entity_id"] == "t2025"           # no time to test: the first era
    assert m.find("The Kafe", at=STAGE2 - timedelta(days=1)) is None     # before its window the name is undecided
    assert m.find("The Kafe", at=STAGE2)["entity_id"] == "a35f8d47"
    assert m.find("Extinction", at=T)["entity_id"] == "extinction"       # an org: the same at any time


def test_a_name_decided_to_a_team_id_keys_as_that_ids_org_at_the_time(tmp_path):
    """The resolver must key a name the way the fact views key the team id: the org inside its window, itself outside."""
    m = _map(tmp_path)
    windows = {"a35f8d47": [(None, STAGE2, "extinction")]}                # a35f8d47 is Extinction until Stage 2
    resolve = make_resolver(m, None, False, team_windows=windows)
    assert resolve("The Kafe", None, STAGE2 + timedelta(days=1)) == ("team:a35f8d47", "decided")
    assert resolve("The Kafe", None, STAGE2 - timedelta(days=1)) is None
    assert resolve("Extinction", None, STAGE2 - timedelta(days=1)) == ("extinction", "decided")
    # a name decided to a team id inside that id's org window keys to the org - the five Extinction disagreements
    m.decide("Extinction", "team", "a35f8d47")
    resolve = make_resolver(m, None, False, team_windows=windows)
    assert resolve("Extinction", None, STAGE2 - timedelta(days=30)) == ("extinction", "decided")
    assert resolve("Extinction", None, STAGE2 + timedelta(days=30)) == ("team:a35f8d47", "decided")


def test_decisions_carry_name_sourced_windows(tmp_path):
    d = OrgDecisions(tmp_path / "d.json")
    d.set("t1", "extinction", "Extinction", valid_from_name="Extinction", valid_to_name="The Kafe")
    d.save()
    again = OrgDecisions(tmp_path / "d.json").get("t1")
    assert (again["valid_from_name"], again["valid_to_name"]) == ("Extinction", "The Kafe") and again.get("valid_from") is None


@pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")
def test_a_name_sourced_window_resolves_from_team_names_at_load_and_an_unknown_name_applies_nothing(agg_db, tmp_path):
    with agg_db.cursor() as cur:
        cur.execute("SELECT team_id, name, first_seen_at FROM team_names ORDER BY first_seen_at LIMIT 1")
        row = cur.fetchone()
    agg_db.commit()
    d = OrgDecisions(tmp_path / "d.json")
    d.set(row["team_id"], "test-sourced", "Sourced", valid_from_name=row["name"])
    try:
        out = load_decisions(agg_db, d)
        assert out["team_ids_mapped"] == 1 and out["windows_unresolved"] == []
        with agg_db.cursor() as cur:
            cur.execute("SELECT valid_from, evidence FROM team_orgs WHERE team_id = %s", [row["team_id"]])
            got = cur.fetchone()
        assert got["valid_from"] == row["first_seen_at"]
        assert any("first sighting of" in e for e in got["evidence"])
        # a name the team id never carried: the mapping is not applied, and the load says so
        d.set(row["team_id"], "test-sourced", "Sourced", valid_from_name="No Such Name Ever")
        out = load_decisions(agg_db, d)
        assert out["team_ids_mapped"] == 0 and out["windows_unresolved"][0]["valid_from"] == "No Such Name Ever"
        with agg_db.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM team_orgs")
            assert cur.fetchone()["n"] == 0
    finally:
        load_decisions(agg_db, OrgDecisions(tmp_path / "empty.json"))
        agg_db.commit()
