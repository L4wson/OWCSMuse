"""The source-agnostic series on real Postgres: one match is one series whichever source holds it, a Liquipedia-only
record is a series only when both its teams are decided, and a disagreeing id merges nothing."""

from __future__ import annotations

import os
from datetime import timedelta

import pytest
from liquipedia_support import DB_FACEIT_ID, DB_PAGE, DB_TEAM1, DB_TEAM2, T0, build_liquipedia_scratch_db, lp_row, write_map_file

from owcsmuse.consistency import run_checks
from owcsmuse.db import RawPayloadStore
from owcsmuse.liquipedia import identity as ident
from owcsmuse.liquipedia import pipeline
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.nlq.pipeline import ask

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
SCHEMA = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test") + "_series"
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")


def _store_more(raw_conn, conn, rows, when):
    """A second stored Liquipedia response for the same page, as a later fetch would be."""
    raw_id = RawPayloadStore(raw_conn).store(endpoint="match", params={"n": 2}, http_status=200, payload={"result": rows},
                                             body_text=None, fetched_at=when, source="liquipedia")
    with conn.cursor() as cur:
        cur.execute("UPDATE liquipedia_coverage SET raw_ids = raw_ids || %s, rows_seen = rows_seen + %s WHERE value = %s",
                    ([raw_id], len(rows), DB_PAGE))
    conn.commit()


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    conn, raw = build_liquipedia_scratch_db(DB_URL, SCHEMA)
    d = tmp_path_factory.mktemp("series")
    map_path = write_map_file(d / "map.json")
    # three more Liquipedia records on the page, none with a FACEIT id:
    #   idx 2: Crazy Raccoon vs Team Falcons, both decided (org anchors)       -> a Liquipedia-only series
    #   idx 3: Crazy Raccoon vs Nobody Knows, one side undecided               -> waits, in no answer
    #   idx 4: Dallas Fuel vs Team Liquid with the SAME FACEIT id as the stored one but a different score -> disagrees
    _store_more(raw, conn, [
        lp_row("Crazy Raccoon", "Team Falcons", 3, 1, when=T0 + timedelta(days=1), page=DB_PAGE, idx=2),
        lp_row("Crazy Raccoon", "Nobody Knows", 3, 0, when=T0 + timedelta(days=2), page=DB_PAGE, idx=3),
    ], T0)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO orgs (org_id, name) VALUES ('crazy-raccoon', 'Crazy Raccoon'), ('team-falcons', 'Team Falcons')")
    conn.commit()
    team_map = TeamMap(d / "team_map.json")
    team_map.decide("Dallas Fuel", "team", DB_TEAM1, "test")
    team_map.decide("Team Liquid", "team", DB_TEAM2, "test")
    team_map.decide("Crazy Raccoon", "org", "crazy-raccoon", "Korean org, Liquipedia-anchored")
    team_map.decide("Team Falcons", "org", "team-falcons", "test")
    team_map.save()
    run = pipeline.run_reconciliation(conn, team_map_path=str(team_map.path), decisions_path=str(d / "links.json"),
                                      map_path=str(map_path))
    pipeline.store_run(conn, run)
    out = ident.load_identity(conn, ident.PlayerDecisions(d / "players.json"), team_map)
    assert out["liquipedia_born_teams_mapped"] == 2
    yield conn, raw, run, team_map, d, map_path
    conn.close()
    raw.close()


def _series(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT series_id, faceit_match_id, lp_objectname, sources, source_url, side1_team_id, side2_team_id, "
                    "played_at_source, result_source, state FROM series ORDER BY series_id")
        return {r["series_id"]: r for r in cur.fetchall()}


def test_a_match_on_both_sources_is_one_series_carrying_both(warehouse):
    conn, *_ = warehouse
    s = _series(conn)
    linked = s["faceit:" + DB_FACEIT_ID]
    assert linked["sources"] == ["faceit", "liquipedia"] and linked["lp_objectname"] == "1_B1_0001"
    assert linked["source_url"].endswith(DB_FACEIT_ID) and linked["result_source"] == "faceit"
    assert sum(1 for r in s.values() if r["faceit_match_id"] == DB_FACEIT_ID) == 1          # once


def test_a_liquipedia_only_record_is_a_series_only_when_both_teams_are_decided(warehouse):
    conn, *_ = warehouse
    s = _series(conn)
    only = s["lp:1_B1_0002"]
    assert only["faceit_match_id"] is None and only["sources"] == ["liquipedia"]
    assert only["source_url"].startswith("https://liquipedia.net/") and only["played_at_source"] == "liquipedia"
    assert (only["side1_team_id"], only["side2_team_id"]) == ("lp:team:crazy raccoon", "lp:team:team falcons")
    assert "lp:1_B1_0003" not in s                                                           # 'Nobody Knows' is undecided
    with conn.cursor() as cur:
        cur.execute("SELECT org_key, display_name, opponent_org_key, won, sources FROM fact_team_matches WHERE series_id = 'lp:1_B1_0002' ORDER BY faction")
        rows = [tuple(r.values()) for r in cur.fetchall()]
    conn.commit()
    assert rows == [("crazy-raccoon", "Crazy Raccoon", "team-falcons", True, ["liquipedia"]),
                    ("team-falcons", "Team Falcons", "crazy-raccoon", False, ["liquipedia"])]   # keyed to the orgs
    r = {c.name: c for c in run_checks(conn, ["series_integrity", "fact_view_reconciliation"])}
    assert r["series_integrity"].ok and r["fact_view_reconciliation"].ok
    assert r["series_integrity"].counts == {"series": 2, "faceit": 1, "linked_pairs": 1, "liquipedia_only": 1,
                                            "liquipedia_unresolved_not_in_series": 1}


def test_the_answer_counts_a_liquipedia_only_series_and_credits_the_page(warehouse):
    conn, *_ = warehouse
    from owcsmuse.aggregates import refresh
    refresh(conn)
    a = ask(conn, "Crazy Raccoon record")
    assert a.status == "ok", a.reason
    assert a.rows[0]["matches"] == 1 and a.rows[0]["wins"] == 1
    assert a.evidence["rows"][0]["sources"] == ["liquipedia"]
    assert a.evidence["rows"][0]["match_url"].startswith("https://liquipedia.net/")
    assert a.attribution and any("liquipedia.net" in u for u in a.attribution["pages"])


def test_a_disagreeing_faceit_id_merges_nothing(warehouse):
    conn, raw, _run, team_map, d, map_path = warehouse
    _store_more(raw, conn, [lp_row("Dallas Fuel", "Team Liquid", 3, 2, when=T0, page=DB_PAGE, idx=9, faceit_id=DB_FACEIT_ID)], T0)
    try:
        run = pipeline.run_reconciliation(conn, team_map_path=str(team_map.path), decisions_path=str(d / "links.json"),
                                          map_path=str(map_path))
        pipeline.store_run(conn, run)
        s = _series(conn)
        # the FACEIT id is now claimed twice: neither record links, the FACEIT series is a series of its own
        linked = s["faceit:" + DB_FACEIT_ID]
        assert linked["sources"] == ["faceit"] and linked["lp_objectname"] is None
        assert "lp:1_B1_0009" not in s and "lp:1_B1_0001" not in s                          # a record claiming an id waits
        r = {c.name: c for c in run_checks(conn, ["series_integrity"])}["series_integrity"]
        assert r.ok and r.counts["linked_pairs"] == 0
    finally:
        with conn.cursor() as cur:
            cur.execute("UPDATE liquipedia_coverage SET raw_ids = raw_ids[1:2] WHERE value = %s", (DB_PAGE,))
        conn.commit()
