"""The consistency checks, on the fixture warehouse.

Two halves, and the second matters more: every check must pass on a correctly
built warehouse, and every check must FAIL when the thing it guards is broken.
A check that cannot fail is the same silent-wrong-answer problem one level up.
Each negative case damages the scratch schema inside a transaction and rolls it
back, so the fixtures stay intact for whatever runs next.
"""

import importlib.util
import os
from pathlib import Path

import pytest

from owcsmuse.consistency import CHECKS, render_text, run_checks

pytestmark = pytest.mark.usefixtures("agg_db")

M2026 = "1-c2fc412d-fe01-4bce-ada5-99b5a6dc9e67"


def _by_name(results):
    return {r.name: r for r in results}


def test_every_check_passes_on_the_fixture_warehouse(agg_db):
    # agg_db loads no scope/ decision file by design (the shared fixture other suites count against), so
    # decisions_loaded is judged on the CI warehouse below, which loads them all
    names = [n for n in CHECKS if n != "decisions_loaded"]
    results = run_checks(agg_db, names)
    assert len(results) == len(CHECKS) - 1
    failed = [r for r in results if not r.ok]
    assert not failed, render_text(results)


def test_every_check_passes_on_the_warehouse_ci_checks():
    """The `consistency checks` CI job's own warehouse: the fixtures with every scope/ decision file loaded."""
    db_url = os.environ.get("OWCS_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("OWCS_TEST_DATABASE_URL not set")
    path = Path(__file__).resolve().parent.parent / "tools" / "build_fixture_db.py"
    spec = importlib.util.spec_from_file_location("build_fixture_db", path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    conn, raw = tool.build_scratch_db(db_url, "owcs_test_ci_fixture")
    try:
        tool.ingest_window_opener(conn, raw, db_url)
        tool.load_decisions(conn)
        results = run_checks(conn)
        conn.commit()
        assert len(results) == len(CHECKS)
        assert not [r for r in results if not r.ok], render_text(results)
        assert _by_name(results)["decisions_loaded"].counts["files"]["org_decisions.json"]["not_applicable_here"] > 0
    finally:
        conn.close()
        raw.close()


def test_counts_are_reported_even_when_everything_passes(agg_db):
    """A check that passes still has to say what it checked, or it proves nothing."""
    r = _by_name(run_checks(agg_db))["fact_view_reconciliation"]
    assert r.ok and r.counts
    for view, c in r.counts.items():
        assert c["expected"] == c["actual"], view
        assert c["actual"] > 0, f"{view} is empty; the fixtures should populate every fact view"


def test_unmapped_team_ids_are_counted_not_hidden(agg_db):
    r = _by_name(run_checks(agg_db, ["org_key_resolution"]))["org_key_resolution"]
    assert r.ok
    assert r.counts["team_ids_total"] == r.counts["team_ids_mapped"] + r.counts["team_ids_unmapped"]
    assert "unmapped" in r.summary


def test_unknown_check_name_is_refused(agg_db):
    with pytest.raises(ValueError, match="unknown check"):
        run_checks(agg_db, ["no_such_check"])


# ------------------------------------------------------------ negative cases

def test_a_match_with_no_usable_time_fails_date_visibility(agg_db):
    """The started_at bug, reproduced: an undated match vanishes from every date view."""
    try:
        with agg_db.cursor() as cur:
            cur.execute("""UPDATE matches SET started_at = NULL, finished_at = NULL,
                                              configured_at = NULL, scheduled_at = NULL
                            WHERE match_id = %s""", (M2026,))
        r = _by_name(run_checks(agg_db, ["date_visibility"]))["date_visibility"]
        assert not r.ok
        kinds = {d["kind"] for d in r.discrepancies}
        assert "match_with_no_usable_time" in kinds
        assert "fact_rows_with_null_date" in kinds
        assert M2026 in {d.get("match_id") for d in r.discrepancies}
    finally:
        agg_db.rollback()


def test_a_stat_edited_under_a_stale_aggregate_fails_aggregate_sums(agg_db):
    try:
        with agg_db.cursor() as cur:
            cur.execute("""UPDATE match_players SET eliminations = eliminations + 1000
                            WHERE match_id = %s AND round_number = 1
                              AND player_id = (SELECT player_id FROM match_players
                                                WHERE match_id = %s AND round_number = 1 LIMIT 1)""",
                        (M2026, M2026))
        r = _by_name(run_checks(agg_db, ["aggregate_sums"]))["aggregate_sums"]
        assert not r.ok
        off = [d for d in r.discrepancies if d["kind"] == "agg_player_stats_sum" and d["stat"] == "eliminations"]
        assert off, r.discrepancies
        assert int(off[0]["source"]) - int(off[0]["aggregate"]) == 1000  # the exact discrepancy, not just "differs"
    finally:
        agg_db.rollback()


def test_a_deleted_player_row_fails_fact_view_reconciliation(agg_db):
    try:
        with agg_db.cursor() as cur:
            cur.execute("""DELETE FROM match_players
                            WHERE (match_id, round_number, player_id) IN (
                                SELECT match_id, round_number, player_id FROM match_players
                                 WHERE match_id = %s LIMIT 1)""", (M2026,))
        r = _by_name(run_checks(agg_db, ["fact_view_reconciliation"]))["fact_view_reconciliation"]
        assert not r.ok
        # fact_player_maps follows the delete; the materialized versus view does not
        views = {d["view"] for d in r.discrepancies}
        assert "fact_player_versus" in views, r.discrepancies
        assert any("refresh" in (d.get("hint") or "") for d in r.discrepancies)
    finally:
        agg_db.rollback()


def test_an_unrefreshed_org_merge_fails_org_key_resolution(agg_db):
    """A merge decided but not refreshed keeps answering at the old identity."""
    try:
        with agg_db.cursor() as cur:
            cur.execute("SELECT team_id FROM fact_team_matches LIMIT 1")
            team_id = cur.fetchone()["team_id"]
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('test-org', 'Test Org')")
            cur.execute("INSERT INTO team_orgs (team_id, org_id) VALUES (%s, 'test-org')", (team_id,))
        r = _by_name(run_checks(agg_db, ["org_key_resolution"]))["org_key_resolution"]
        assert not r.ok
        stale = [d for d in r.discrepancies if d["kind"] == "stale_org_key_in_materialized_view"]
        assert stale and "test-org" in stale[0]["current_org_keys"]
    finally:
        agg_db.rollback()


def test_an_org_id_that_collides_with_the_unmapped_prefix_fails(agg_db):
    try:
        with agg_db.cursor() as cur:
            cur.execute("INSERT INTO orgs (org_id, name) VALUES ('team:abc', 'Collides')")
        r = _by_name(run_checks(agg_db, ["org_key_resolution"]))["org_key_resolution"]
        assert not r.ok
        assert any(d["kind"] == "org_id_collides_with_unmapped_key_prefix" for d in r.discrepancies)
    finally:
        agg_db.rollback()


def test_a_team_id_in_both_regions_fails_region_consistency(agg_db):
    """The sug2rfree bug, reproduced: one identity holding matches in na and in emea."""
    try:
        assert _by_name(run_checks(agg_db, ["region_consistency"]))["region_consistency"].ok
        with agg_db.cursor() as cur:
            cur.execute("SELECT team_id, region FROM fact_team_matches WHERE region IN ('na', 'emea') LIMIT 1")
            row = cur.fetchone()
            assert row, "the fixtures should carry region-locked matches"
            other = "emea" if row["region"] == "na" else "na"
            cur.execute("INSERT INTO championships (championship_id, name, include, scope_region, season) "
                        "VALUES ('c-other-region', 'other region', true, %s, 2026)", (other,))
            cur.execute("""INSERT INTO matches (match_id, championship_id, status, ingest_state, faction1_team_id,
                                                faction2_team_id, faction1_score, faction2_score, started_at)
                           VALUES ('m-other-region', 'c-other-region', 'FINISHED', 'result_only', %s, %s, 1, 0, now())""",
                        (row["team_id"], row["team_id"]))
        r = _by_name(run_checks(agg_db, ["region_consistency"]))["region_consistency"]
        assert not r.ok
        assert any(d["kind"] == "team_id_spans_regions" and d["key"] == row["team_id"] for d in r.discrepancies)
        assert any(d["kind"] == "org_spans_regions" for d in r.discrepancies)
    finally:
        agg_db.rollback()


def test_a_player_row_on_a_liquipedia_sourced_map_fails_liquipedia_map_isolation(agg_db):
    """Stage 2 must never invent player stats: a match_players row joined to a source='liquipedia' round is
    exactly the silent merge the source-per-field rule exists to prevent."""
    try:
        assert _by_name(run_checks(agg_db, ["liquipedia_map_isolation"]))["liquipedia_map_isolation"].ok
        with agg_db.cursor() as cur:
            cur.execute("SELECT match_id, round_number FROM match_players LIMIT 1")
            row = cur.fetchone()
            assert row, "the fixtures should carry at least one player-map row"
            cur.execute("UPDATE match_rounds SET source = 'liquipedia' WHERE match_id = %s AND round_number = %s",
                        (row["match_id"], row["round_number"]))
        r = _by_name(run_checks(agg_db, ["liquipedia_map_isolation"]))["liquipedia_map_isolation"]
        assert not r.ok
        assert any(d["match_id"] == row["match_id"] and d["round_number"] == row["round_number"]
                  for d in r.discrepancies)
    finally:
        agg_db.rollback()


def test_render_text_names_the_failing_check(agg_db):
    try:
        with agg_db.cursor() as cur:
            cur.execute("UPDATE matches SET started_at = NULL, finished_at = NULL, configured_at = NULL, "
                        "scheduled_at = NULL WHERE match_id = %s", (M2026,))
        text = render_text(run_checks(agg_db, ["date_visibility", "org_key_resolution"]))
        assert "FAILED: date_visibility" in text
        assert "[FAIL] date_visibility" in text and "[PASS] org_key_resolution" in text
    finally:
        agg_db.rollback()


def _copies(agg_db, n: int, records_per_copy: int, names: tuple[str, str]) -> None:
    """n copies of one fixture series, each linked to `records_per_copy` Liquipedia records named `names`."""
    with agg_db.cursor() as cur:
        cur.execute("SELECT id FROM raw_payloads ORDER BY id LIMIT 1")
        raw_id = cur.fetchone()["id"]
        for i in range(n):
            mid = f"{M2026}-copy{i}"
            cur.execute("""INSERT INTO matches SELECT (jsonb_populate_record(NULL::matches,
                                to_jsonb(m) || jsonb_build_object('match_id', %s::text))).* FROM matches m WHERE match_id = %s""", (mid, M2026))
            for j in range(records_per_copy):
                obj = f"test-{i}-{j}"
                cur.execute("""INSERT INTO liquipedia_matches (objectname, raw_id, match2id, bracket_id, pagename, page_url, region,
                                                               played_at, team1_name, team2_name, score1, score2, finished)
                               SELECT %s, %s, %s, 'B', 'P', 'https://liquipedia.net/overwatch/P', '',
                                      match_time(started_at, finished_at, configured_at, scheduled_at), %s, %s, 3, 0, true
                                 FROM matches WHERE match_id = %s""", (obj, raw_id, obj, names[0], names[1], mid))
                cur.execute("INSERT INTO liquipedia_links (lp_objectname, faceit_match_id, tier) VALUES (%s, %s, 'exact')", (obj, mid))


def test_series_integrity_counts_every_disagreement_past_ten(agg_db):
    """12 linked pairs whose Liquipedia names resolve to two other teams: 12 discrepancies, not a LIMIT's 10."""
    try:
        with agg_db.cursor() as cur:
            cur.execute("""SELECT team_id FROM teams WHERE team_id NOT IN (SELECT faction1_team_id FROM matches WHERE match_id = %s
                             UNION SELECT faction2_team_id FROM matches WHERE match_id = %s) ORDER BY team_id LIMIT 2""", (M2026, M2026))
            x, y = (r["team_id"] for r in cur.fetchall())
            for name, tid in (("aaa", x), ("bbb", y)):
                cur.execute("""INSERT INTO entity_anchors (entity_type, entity_id, source, anchor_kind, anchor, basis)
                               VALUES ('team', %s, 'liquipedia', 'team_name', %s, 'team_map')""", (tid, name))
        _copies(agg_db, 12, 1, ("Aaa", "Bbb"))
        r = _by_name(run_checks(agg_db, ["series_integrity"]))["series_integrity"]
        kinds = [d["kind"] for d in r.discrepancies]
        assert kinds.count("linked_sides_disagree") == 12 and r.discrepancy_count == 12
    finally:
        agg_db.rollback()


def test_series_integrity_counts_every_series_claimed_twice_past_ten(agg_db):
    """12 FACEIT matches each claimed by two Liquipedia records: each is in two series, and all 12 are counted.

    A unique index forbids the second link today; the check exists for the day that guarantee is lost, so the test
    drops it inside the transaction it rolls back."""
    try:
        with agg_db.cursor() as cur:
            cur.execute("DROP INDEX liquipedia_links_faceit_once_idx")
        _copies(agg_db, 12, 2, ("Unanchored One", "Unanchored Two"))
        r = _by_name(run_checks(agg_db, ["series_integrity"]))["series_integrity"]
        kinds = [d["kind"] for d in r.discrepancies]
        assert kinds.count("faceit_match_in_two_series") == 12
    finally:
        agg_db.rollback()
