"""Stage 4: events with no FACEIT competition - the subpage probe, the planner's wants, and `lp:` championships."""

from __future__ import annotations

import json
import os

import psycopg
import pytest

from owcsmuse.liquipedia import events, pipeline, stage1

ROOT = "Overwatch_Champions_Series/2025/World_Finals"
MSC = "Overwatch Champions Series/2025/Midseason Championship"


def write_events(path, **override):
    e = {"display_name": "OWCS 2025 World Finals", "season": 2025, "region": "international", "tier": "main",
         "include": True, "pages": {f"{ROOT}/Group_Stage": 12, f"{ROOT}/Playoffs": 7}, **override}
    path.write_text(json.dumps({"events": {ROOT: e}}), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------------------ the probe

def test_the_probe_matches_each_root_as_the_page_or_as_the_parent_in_one_condition():
    p = events.subpage_probe_params([ROOT, MSC])
    msc = MSC.replace(" ", "_")
    assert p["conditions"] == (f"([[pagename::{ROOT}]] OR [[pagename::{msc}]] OR "
                               f"[[parent::{ROOT}]] OR [[parent::{msc}]])")
    assert p["query"] == "pagename,parent"


def test_the_probe_summary_places_subpages_under_their_root_and_reports_what_it_could_not():
    rows = [{"pagename": f"{ROOT}/Group_Stage", "parent": ROOT}] * 3 + [
        {"pagename": ROOT, "parent": "Overwatch_Champions_Series/2025"},          # matches on the root page itself
        {"pagename": f"{ROOT.lower()}/playoffs", "parent": ROOT.lower()},         # case differs: still this root
        {"pagename": "Somewhere_Else", "parent": "Other"}]
    out = events.summarise_subpage_probe([ROOT, MSC], rows, limit=500, raw_id=7)
    assert out["found"] == {ROOT: {ROOT: 1, f"{ROOT}/Group_Stage": 3, f"{ROOT.lower()}/playoffs": 1}}
    assert out["not_found"] == [MSC.replace(" ", "_")]
    assert out["unplaced_rows"] == {"Somewhere_Else (parent Other)": 1}
    assert out["truncated"] is False and out["raw_id"] == 7


def test_a_probe_that_returns_its_limit_says_it_was_truncated():
    rows = [{"pagename": ROOT, "parent": ""}] * 5
    assert events.summarise_subpage_probe([ROOT], rows, limit=5)["truncated"] is True


# ---------------------------------------------------------------------------------- the file and its readers

def test_event_pages_feed_the_planner_and_store_under_the_lp_championship(tmp_path):
    path = write_events(tmp_path / "events.json")
    assert events.event_wants(path) == {f"{ROOT}/Group_Stage": 12, f"{ROOT}/Playoffs": 7}
    comps, names = events.event_comps(path)
    assert comps == {f"{ROOT}/Group_Stage": {f"lp:{ROOT}"}, f"{ROOT}/Playoffs": {f"lp:{ROOT}"}}
    assert names[f"{ROOT}/Playoffs"] == "OWCS 2025 World Finals"


def test_an_event_with_no_probed_pages_wants_nothing(tmp_path):
    path = write_events(tmp_path / "events.json", pages={})
    assert events.event_wants(path) == {}
    assert events.event_comps(path) == ({}, {})


def test_a_missing_file_is_no_events(tmp_path):
    assert events.load_events(tmp_path / "absent.json") == {}


def test_an_event_outside_the_declared_region_or_missing_a_field_is_refused(tmp_path):
    with pytest.raises(ValueError, match="region 'korea'"):
        events.load_events(write_events(tmp_path / "a.json", region="korea"))
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"events": {ROOT: {"display_name": "x", "region": "international", "tier": "main"}}}))
    with pytest.raises(ValueError, match="season, include"):
        events.load_events(path)


def test_stage1_wants_include_the_event_pages_at_their_probed_counts(tmp_path, monkeypatch):
    ev = write_events(tmp_path / "events.json")
    monkeypatch.setattr(events, "EVENTS_PATH", str(ev))
    (tmp_path / "map.json").write_text(json.dumps({"pages": {}}), encoding="utf-8")

    class NoFaceit:            # no FACEIT competitions in the map: the query must not even be needed for events
        def cursor(self):
            class C:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def execute(s, *a): pass
                def fetchall(s): return []
            return C()

    wants = stage1.stage1_wants(NoFaceit(), str(tmp_path / "map.json"), str(ev))
    assert wants == {f"{ROOT}/Group_Stage": 12, f"{ROOT}/Playoffs": 7}


# ------------------------------------------------------------------------------------------- the database

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")


@pytest.fixture()
def db():
    if not DB_URL:
        pytest.skip("OWCS_TEST_DATABASE_URL not set")
    from agg_support import build_scratch_db

    conn, raw = build_scratch_db(DB_URL, "owcs_test_lp_events")
    yield conn
    conn.close()
    raw.close()


def _champ(conn, cid):
    with conn.cursor() as cur:
        cur.execute("SELECT name, source, liquipedia_page, scope_region, tier, season, include, classification_source "
                    "FROM championships WHERE championship_id = %s", (cid,))
        return cur.fetchone()


def test_load_writes_one_included_lp_championship_per_event_and_removes_one_the_file_dropped(db, tmp_path):
    path = write_events(tmp_path / "events.json")
    assert events.load_championships(db, path) == {"events": 1, "included": 1, "removed": 0}
    row = _champ(db, f"lp:{ROOT}")
    assert dict(row) == {"name": "OWCS 2025 World Finals", "source": "liquipedia", "liquipedia_page": ROOT,
                         "scope_region": "international", "tier": "main", "season": 2025, "include": True,
                         "classification_source": "manual"}
    assert events.load_championships(db, path)["removed"] == 0           # idempotent
    path.write_text(json.dumps({"events": {}}), encoding="utf-8")
    assert events.load_championships(db, path)["removed"] == 1
    assert _champ(db, f"lp:{ROOT}") is None


def test_an_lp_id_is_only_ever_a_liquipedia_championship(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute("INSERT INTO championships (championship_id, name, source) VALUES ('lp:x', 'x', 'history')")
    db.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute("INSERT INTO championships (championship_id, name, source) VALUES ('abc', 'x', 'liquipedia')")
    db.rollback()


def test_records_on_an_event_page_store_under_its_lp_championship(tmp_path, monkeypatch):
    ev = write_events(tmp_path / "events.json")
    monkeypatch.setattr(events, "load_events", lambda path=events.EVENTS_PATH, _f=events.load_events: _f(ev))
    (tmp_path / "map.json").write_text(json.dumps({"pages": {}}), encoding="utf-8")
    comps, names = pipeline.load_map(str(tmp_path / "map.json"))
    assert comps[f"{ROOT}/Playoffs"] == {f"lp:{ROOT}"}
    assert names[f"{ROOT}/Group_Stage"] == "OWCS 2025 World Finals"


# ------------------------------------------------------------------------------------------------ placements

def _place(page, place, team, *, pool=1, kind="team", mode="", obj=None):
    return {"objectname": obj or f"{page}_{place}_{team}", "pagename": page, "placement": place, "opponentname": team,
            "opponenttype": kind, "mode": mode, "prizepoolindex": pool, "opponenttemplate": team.lower(),
            "qualifier": "q", "date": "2025-11-30 15:30:00"}


def test_a_placing_is_a_range_and_anything_else_is_not_one():
    assert events.parse_placement("1") == (1, 1)
    assert events.parse_placement("7-8") == (7, 8)
    assert events.parse_placement(" 3 - 4 ") == (3, 4)
    for bad in ("", "W", "DQ", "4-3", "0"):
        assert events.parse_placement(bad) is None


def test_placement_rows_keep_team_placings_on_the_root_page_and_leave_awards_out():
    recs = [_place(ROOT, "1", "Twisted Minds"), _place(ROOT, "2", "Al Qadsiah"),
            _place(ROOT, "", "Shu", kind="solo", mode="award_individual"),        # an MVP
            _place(ROOT, "", "Team Falcons", pool=2),                             # a team award: no placing
            _place(f"{ROOT}/Group_Stage", "1", "Somebody")]                      # not the root page
    kept, rep = events.placement_rows(recs, {ROOT: f"lp:{ROOT}"})
    assert [(k["team_name"], k["place_high"], k["place_low"]) for k in kept] == [("Twisted Minds", 1, 1), ("Al Qadsiah", 2, 2)]
    assert rep["skipped"] == {"individual award": 1, "no placing (a team award or an empty slot)": 1,
                              "not an event root page": 1}
    assert rep["ambiguous_prize_pools"] == {} and rep["pages_without_one_first_place"] == []


def test_team_placings_in_two_prize_pools_are_ambiguous_and_none_are_kept():
    recs = [_place(ROOT, "1", "A"), _place(ROOT, "2", "B"), _place(ROOT, "1", "C", pool=2)]   # an LCQ's pool, say
    kept, rep = events.placement_rows(recs, {ROOT: f"lp:{ROOT}"})
    assert kept == [] and rep["ambiguous_prize_pools"] == {ROOT: [1, 2]}


def test_an_event_with_two_winners_or_none_is_reported():
    kept, rep = events.placement_rows([_place(ROOT, "1", "A"), _place(ROOT, "1", "B", obj="x")], {ROOT: f"lp:{ROOT}"})
    assert rep["pages_without_one_first_place"] == [ROOT]
