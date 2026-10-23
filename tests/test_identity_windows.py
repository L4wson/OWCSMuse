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
    ext = {k[:8]: v for k, v in d.items() if v.get("org_id") == "extinction"}
    assert ext["2b7f8ef6"]["valid_from_name"] == "Extinction" and ext["2b7f8ef6"].get("valid_to_name") is None
    assert (ext["a35f8d47"]["valid_from_name"], ext["a35f8d47"]["valid_to_name"]) == ("Extinction", "The Kafe")


def test_every_committed_window_is_sourced_from_a_sighting_and_named_in_the_window_verdicts():
    """Each bound of a mapping is open, a name's first sighting, or one of the owner's explicit timestamps; every team
    id that carries a bounded mapping is covered by the owner's verdict in scope/org_window_decisions.json."""
    d = json.load(open("scope/org_decisions.json", encoding="utf-8"))["decisions"]
    verdicts = json.load(open("scope/org_window_decisions.json", encoding="utf-8"))["decisions"]
    assert len(verdicts) == 18
    explicit = {"2025-01-31T19:17:07+00:00",       # Virtus pro: itself a sighting, kept as a timestamp
                "2025-05-01T00:00:00+00:00",       # Rad -> Sakura at the 2025 Stage 2 boundary: FACEIT's rename lagged a week
                "2026-10-09T00:00:00+00:00"}       # 2026 Stage 3: KAFE and NTMR (2026) on recycled ids (owner, 2026-10-23)
    for team_id, entry in d.items():
        for w in entry.get("windows") or [entry]:
            for side in ("valid_from", "valid_to"):
                assert not w.get(side) or w[side] in explicit, (team_id, side, w.get(side))
            if any(w.get(k) for k in ("valid_from", "valid_to", "valid_from_name", "valid_to_name")):
                assert team_id in verdicts, team_id
    # the ids whose names are several organisations' eras (owner, 2026-10-02)
    eras = {k[:8]: [(w["org_id"], w.get("valid_from_name") or w.get("valid_from"), w.get("valid_to_name") or w.get("valid_to"))
                    for w in v["windows"]]
            for k, v in d.items() if "windows" in v}
    assert eras == {
        "0464a373": [("rad", "Rad", "2025-05-01T00:00:00+00:00"), ("sakura", "2025-05-01T00:00:00+00:00", "LuneX"),
                     ("lunex", "LuneX", "2026-10-09T00:00:00+00:00"), ("kafe", "2026-10-09T00:00:00+00:00", None)],
        "d20d1868": [("supernova", "Supernova", "Team Z"), ("team-z", "Team Z", "2026-10-09T00:00:00+00:00"),
                     ("ntmr-2026", "2026-10-09T00:00:00+00:00", None)],
        "03869857": [("rocstars", "Umbrellaacademy", None)],          # the one 'Umbrellaacademy' series is ROCstars'
        "ebfd8060": [("quick-esports", None, "Ataraxia"), ("ataraxia", "Ataraxia", None)],
    }
    # Quick Esports: one org over ebfd8060's 2024 era and all of cb90edf6
    assert {k[:8] for k, v in d.items() if any(w.get("org_id") == "quick-esports" for w in v.get("windows") or [v])} == {"ebfd8060", "cb90edf6"}
    # NTMR: one org across two team ids, each only over its own NTMR era
    ntmr = {k[:8]: v for k, v in d.items() if v.get("org_id") == "ntmr"}
    assert {k: v["valid_from_name"] for k, v in ntmr.items()} == {"c5116cb3": "NTMR", "cefc3f72": "NTMR"}
    # the verdict kinds the owner used
    kinds = {v["verdict"] for v in verdicts.values()}
    assert kinds == {"rename_only", "placeholder", "placeholder_then_pickups", "pickup", "roster_drop", "org_changes", "recycled_id"}


def test_a_second_era_on_one_team_id_is_a_window_and_round_trips(tmp_path):
    d = OrgDecisions(tmp_path / "d.json")
    d.set("t1", "rad", "Rad", valid_from_name="Rad", valid_to_name="Sakura")
    d.add_window("t1", "sakura", "Sakura", valid_from_name="Sakura")
    with pytest.raises(ValueError):
        d.add_window("t1", "lunex", "LuneX")                                   # a second mapping must be windowed
    d.save()
    again = OrgDecisions(tmp_path / "d.json")
    assert [m["org_id"] for m in again.mappings("t1")] == ["rad", "sakura"]
    assert again.mappings("t1")[0]["valid_to_name"] == "Sakura" and "org_id" not in again.get("t1")
    assert again.mappings("none") == []


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


# ------------------------------------------------------------------ the signals on a name change

from owcsmuse.orgs import classify_name_change, stage_of  # noqa: E402


def _n(name, first, last):
    return (name, datetime.fromisoformat(first).replace(tzinfo=timezone.utc), datetime.fromisoformat(last).replace(tzinfo=timezone.utc))


def test_a_kept_handle_is_a_rename_even_across_a_stage_boundary():
    for old, new in (("SpaceStation", "SpaceStation Gaming"), ("GenG", "GenG Esports"), ("Goud Guys", "Goud Guys ANM"),
                     ("PIP", "PxG PiP"), ("Sakura", "Sakura Esports")):
        c = classify_name_change(_n(old, "2025-02-01", "2025-09-21"), _n(new, "2025-09-28", "2026-07-06"))
        assert c["verdict"] == "rename" and c["handle_kept"], c


def test_a_wholly_different_name_on_a_stage_boundary_is_a_pickup():
    c = classify_name_change(_n("Avidity", "2025-02-01", "2025-03-02"), _n("Extinction", "2025-05-11", "2025-10-12"))
    assert c["verdict"] == "pickup" and c["stage_boundary"] and c["stages"] == ["2025 Stage 1", "2025 Stage 2"]
    c = classify_name_change(_n("Extinction", "2026-03-22", "2026-05-29"), _n("The Kafe", "2026-06-13", "2026-07-01"))
    assert c["verdict"] == "pickup"


def test_the_signals_disagree_when_the_ranges_overlap_or_the_change_is_mid_stage():
    c = classify_name_change(_n("Quick Esports", "2025-05-11", "2025-10-12"), _n("1DIPv100GORILLA", "2025-06-01", "2025-06-15"))
    assert c["verdict"] == "disagree" and "alternated" in c["why"]
    c = classify_name_change(_n("Anyones Legend", "2026-03-22", "2026-05-25"), _n("1234", "2026-05-25", "2026-07-01"))
    assert c["verdict"] == "disagree"                                               # same day, same stage, different name
    assert stage_of(_n("x", "2026-06-13", "2026-06-13")[1]) == "2026 Stage 2"


def test_propose_window_does_not_split_a_rename():
    from owcsmuse.orgs import propose_window
    team = _team([("SpaceStation", 0, 200), ("SpaceStation Gaming", 240, 500)])
    assert propose_window(team, "SpaceStation Gaming") is None


def test_a_registration_placeholder_is_the_same_organisation_without_a_window():
    """The third signal: a `team_` name, or one that lived only in a stage's opening days, replaced inside that stage."""
    c = classify_name_change(_n("team_chiime", "2024-03-08", "2024-03-10"), _n("Dreamland", "2024-03-17", "2024-03-17"))
    assert c["verdict"] == "placeholder" and c["placeholder"] and "team_" in c["why"]
    c = classify_name_change(_n("BuboSprayCheck", "2024-03-08", "2024-03-21"), _n("ENCE", "2024-03-22", "2024-06-02"))
    assert c["verdict"] == "placeholder" and "opening 14 day(s)" in c["why"]
    # it needs the same stage: a `team_` name replaced in a later stage is still a pickup
    c = classify_name_change(_n("team_x", "2024-03-08", "2024-03-10"), _n("Other", "2024-04-12", "2024-04-20"))
    assert c["verdict"] == "pickup" and not c["placeholder"]
    # and the old name must be gone early: a name that lasted the stage is not a placeholder
    c = classify_name_change(_n("Rad", "2025-02-01", "2025-05-10"), _n("Sakura", "2025-05-17", "2025-09-21"))
    assert c["verdict"] == "disagree" and not c["placeholder"]


@pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")
def test_a_name_sourced_window_starts_at_the_series_time_as_the_facts_read_it(agg_db, tmp_path):
    """team_names.first_seen_at is FACEIT's timestamp; a result_only series' FACEIT time is when the result was
    entered, hours after Liquipedia dates it. The window must start at the earliest time any source gives the
    first series under that name, or Liquipedia's record of that series resolves to the previous era (the 17
    'disagree on teams' links on production, 2026-10-02)."""
    from datetime import timedelta
    with agg_db.cursor() as cur:
        cur.execute("""SELECT m.match_id, m.faction1_team_id AS team_id, m.faction1_name AS name,
                              match_time(m.started_at, m.finished_at, m.configured_at, m.scheduled_at) AS t
                         FROM matches m WHERE m.ingest_state = 'complete' AND m.faction1_name IS NOT NULL ORDER BY 4 LIMIT 1""")
        m = cur.fetchone()
        cur.execute("SELECT first_seen_at FROM team_names WHERE team_id = %s AND name = %s", (m["team_id"], m["name"]))
        faceit_first = cur.fetchone()["first_seen_at"]
        earlier = m["t"] - timedelta(hours=2)
        cur.execute("UPDATE matches SET liquipedia_played_at = %s WHERE match_id = %s", (earlier, m["match_id"]))
    agg_db.commit()
    d = OrgDecisions(tmp_path / "d.json")
    d.set(m["team_id"], "test-sourced", "Sourced", valid_from_name=m["name"])
    try:
        out = load_decisions(agg_db, d)
        assert out["team_ids_mapped"] == 1 and out["windows_unresolved"] == []
        with agg_db.cursor() as cur:
            cur.execute("SELECT valid_from FROM team_orgs WHERE team_id = %s", (m["team_id"],))
            got = cur.fetchone()["valid_from"]
        assert got == min(earlier, faceit_first) and got <= earlier < faceit_first or got == earlier
    finally:
        load_decisions(agg_db, OrgDecisions(tmp_path / "empty.json"))
        with agg_db.cursor() as cur:
            cur.execute("UPDATE matches SET liquipedia_played_at = NULL WHERE match_id = %s", (m["match_id"],))
        agg_db.commit()
