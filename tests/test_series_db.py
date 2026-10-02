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
        lp_row("Crazy Raccoon", "Future Name", 3, 0, when=T0 + timedelta(days=3), page=DB_PAGE, idx=4),   # before that name's window
    ], T0)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO orgs (org_id, name) VALUES ('crazy-raccoon', 'Crazy Raccoon'), ('team-falcons', 'Team Falcons')")
    conn.commit()
    team_map = TeamMap(d / "team_map.json")
    team_map.decide("Dallas Fuel", "team", DB_TEAM1, "test")
    team_map.decide("Team Liquid", "team", DB_TEAM2, "test")
    team_map.decide("Crazy Raccoon", "org", "crazy-raccoon", "Korean org, Liquipedia-anchored")
    team_map.decide("Team Falcons", "org", "team-falcons", "test")
    team_map.decide("Future Name", "org", "team-falcons", "a name that holds only from later", valid_from=(T0 + timedelta(days=30)).isoformat())
    team_map.save()
    run = pipeline.run_reconciliation(conn, team_map_path=str(team_map.path), decisions_path=str(d / "links.json"),
                                      map_path=str(map_path))
    pipeline.store_run(conn, run)
    out = ident.load_identity(conn, ident.PlayerDecisions(d / "players.json"), team_map)
    assert out["liquipedia_born_teams_mapped"] == 3
    yield conn, raw, run, team_map, d, map_path
    conn.close()
    raw.close()


def test_loading_identity_twice_is_idempotent(warehouse):
    # the second load once raised: its upsert onto an existing born team's window tripped team_orgs' overlap trigger
    conn, _, _, team_map, d, _ = warehouse
    def born_windows():
        with conn.cursor() as cur:
            cur.execute("SELECT team_id, org_id, valid_from::text, valid_to::text FROM team_orgs WHERE team_id LIKE 'lp:team:%' ORDER BY team_id")
            rows = [tuple(r.values()) for r in cur.fetchall()]
        conn.commit()
        return rows
    before = born_windows()
    assert ident.load_identity(conn, ident.PlayerDecisions(d / "players.json"), team_map)["liquipedia_born_teams_mapped"] == 3
    assert born_windows() == before and len(before) == 3


def _series(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT series_id, faceit_match_id, lp_objectname, sources, source_url, side1_team_id, side2_team_id, "
                    "played_at_source, result_source, state, score1, score2, score_source, best_of, best_of_source FROM series ORDER BY series_id")
        return {r["series_id"]: r for r in cur.fetchall()}


def test_a_match_on_both_sources_is_one_series_carrying_both(warehouse):
    conn, *_ = warehouse
    s = _series(conn)
    linked = s["faceit:" + DB_FACEIT_ID]
    assert linked["sources"] == ["faceit", "liquipedia"] and linked["lp_objectname"] == "1_B1_0001"
    # Liquipedia is the source of record for a linked series' result and best-of (034); FACEIT only where it has nothing
    assert linked["source_url"].endswith(DB_FACEIT_ID) and linked["result_source"] == "liquipedia"
    assert linked["score_source"] == "liquipedia" and linked["best_of_source"] == "liquipedia" and linked["best_of"] == 5
    assert sum(1 for r in s.values() if r["faceit_match_id"] == DB_FACEIT_ID) == 1          # once


def test_a_liquipedia_only_record_is_a_series_only_when_both_teams_are_decided(warehouse):
    conn, *_ = warehouse
    s = _series(conn)
    only = s["lp:1_B1_0002"]
    assert only["faceit_match_id"] is None and only["sources"] == ["liquipedia"]
    assert only["source_url"].startswith("https://liquipedia.net/") and only["played_at_source"] == "liquipedia"
    assert (only["side1_team_id"], only["side2_team_id"]) == ("lp:team:crazy raccoon", "lp:team:team falcons")
    assert "lp:1_B1_0003" not in s                                                           # 'Nobody Knows' is undecided
    assert "lp:1_B1_0004" not in s                                                           # 'Future Name' is undecided at that time
    with conn.cursor() as cur:
        cur.execute("SELECT org_key, display_name, opponent_org_key, won, sources FROM fact_team_matches WHERE series_id = 'lp:1_B1_0002' ORDER BY faction")
        rows = [tuple(r.values()) for r in cur.fetchall()]
    conn.commit()
    assert rows == [("crazy-raccoon", "Crazy Raccoon", "team-falcons", True, ["liquipedia"]),
                    ("team-falcons", "Team Falcons", "crazy-raccoon", False, ["liquipedia"])]   # keyed to the orgs
    r = {c.name: c for c in run_checks(conn, ["series_integrity", "fact_view_reconciliation"])}
    assert r["series_integrity"].ok and r["fact_view_reconciliation"].ok
    assert r["series_integrity"].counts == {"series": 2, "faceit": 1, "linked_pairs": 1, "liquipedia_only": 1,
                                            "liquipedia_unresolved_not_in_series": 2}


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


def test_liquipedia_is_the_source_of_record_for_a_linked_result_and_a_phantom_map_is_out(warehouse):
    """FACEIT keeps a fixed number of map slots per format and logs a default win when a sweep ends early (034).
    Here FACEIT says 4-1 over five maps; Liquipedia, linked by id, says 3-1 over four games. The series presents
    Liquipedia's result, the fifth FACEIT map is a phantom in no fact view, and its player rows are counted, not used."""
    conn, *_ = warehouse
    from liquipedia_support import DB_FACEIT_ID, DB_TEAM1, DB_TEAM2
    from owcsmuse.consistency import run_checks
    with conn.cursor() as cur:
        # the module's earlier tests leave two Liquipedia records claiming this id (ambiguous): a person confirms one
        cur.execute("UPDATE liquipedia_links SET faceit_match_id = %s, decision = 'confirmed' WHERE lp_objectname = '1_B1_0001'", (DB_FACEIT_ID,))
        cur.execute("UPDATE liquipedia_links SET decision = 'rejected' WHERE lp_objectname = '1_B1_0009'")
        cur.execute("UPDATE matches SET faction1_score = 4 WHERE match_id = %s", (DB_FACEIT_ID,))
        cur.execute("""INSERT INTO match_rounds (match_id, round_number, map_name, game_mode, team1_team_id, team1_score,
                                                  team2_team_id, team2_score, winner_team_id)
                       VALUES (%s, 5, 'Dorado', 'Escort', %s, 3, %s, 0, %s)""", (DB_FACEIT_ID, DB_TEAM1, DB_TEAM2, DB_TEAM1))
        cur.execute("INSERT INTO players (player_id, nickname) VALUES ('p-phantom', 'ghost') ON CONFLICT DO NOTHING")
        cur.execute("""INSERT INTO match_players (match_id, round_number, player_id, team_id, nickname_at_match, stats)
                       VALUES (%s, 5, 'p-phantom', %s, 'ghost', '{}'::jsonb)""", (DB_FACEIT_ID, DB_TEAM1))
    try:
        s = _series(conn)["faceit:" + DB_FACEIT_ID]
        assert (s["score1"], s["score2"], s["score_source"], s["result_source"], s["best_of"], s["best_of_source"]) == (3, 1, "liquipedia", "liquipedia", 5, "liquipedia")
        with conn.cursor() as cur:
            cur.execute("SELECT round_number, map_name, player_rows FROM phantom_maps WHERE match_id = %s", (DB_FACEIT_ID,))
            assert [tuple(r.values()) for r in cur.fetchall()] == [(5, "Dorado", 1)]
            cur.execute("SELECT max(round_number) AS n FROM fact_team_maps WHERE match_id = %s", (DB_FACEIT_ID,))
            assert cur.fetchone()["n"] == 4
            cur.execute("SELECT count(*) AS n FROM fact_player_maps WHERE match_id = %s AND round_number = 5", (DB_FACEIT_ID,))
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT map_wins, map_losses FROM fact_team_matches WHERE match_id = %s AND team_id = %s", (DB_FACEIT_ID, DB_TEAM1))
            assert tuple(cur.fetchone().values()) == (3, 1)
        r = {c.name: c for c in run_checks(conn, ["phantom_map_isolation", "score_plausibility", "series_integrity"])}
        assert r["phantom_map_isolation"].ok and r["phantom_map_isolation"].counts["phantom_maps"] == 1
        assert r["phantom_map_isolation"].counts["phantom_maps_with_player_rows"] == 1 and r["phantom_map_isolation"].counts["phantom_player_rows_excluded"] == 1
        assert r["score_plausibility"].ok and r["score_plausibility"].counts["results_from_liquipedia"] == 1
        assert r["series_integrity"].ok
    finally:
        conn.rollback()
