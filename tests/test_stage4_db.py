"""Stage 4 end to end on a scratch warehouse: a Liquipedia-only series at a Liquipedia-only event between two
Liquipedia-only orgs reaches answers, a player-stat question about that event refuses `results_only`, and the
alternative it offers works.

These are the two Stage 3 paths no real data had run through: Liquipedia-anchored identity for teams with no FACEIT id
(here created through `--new-org-name`) and the capability layer's results-only refusal.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from agg_support import build_scratch_db
from liquipedia_support import lp_row, write_map_file
from owcsmuse import orgs
from owcsmuse.aggregates import refresh
from owcsmuse.db import RawPayloadStore
from owcsmuse.liquipedia import events, identity, pipeline
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.nlq.pipeline import ask

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

WF = "Overwatch_Champions_Series/2025/World_Finals"
WHEN = datetime(2025, 11, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def stage4(tmp_path):
    # the three-match fixture warehouse: real FACEIT player stats, so a stat question reaches the capability check
    conn, raw = build_scratch_db(DB_URL, "owcs_test_stage4")
    # two series at the event, neither on FACEIT: T1 beat Weibo Gaming twice
    rows = [lp_row("T1", "Weibo Gaming", 3, 1, WHEN, page=WF, bracket="WF", idx=1),
            lp_row("Weibo Gaming", "T1", 2, 3, WHEN.replace(hour=15), page=WF, bracket="WF", idx=2)]
    raw_id = RawPayloadStore(raw).store(endpoint="match", params={}, http_status=200, payload={"result": rows},
                                        body_text=None, fetched_at=WHEN, source="liquipedia")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
                       VALUES ('match', 'pagename', %s, %s, 2, %s)""", (WF, f"https://liquipedia.net/overwatch/{WF}", [raw_id]))
    conn.commit()
    ev = tmp_path / "events.json"
    ev.write_text(json.dumps({"events": {WF: {"display_name": "OWCS 2025 World Finals", "season": 2025,
                                              "region": "international", "tier": "main", "include": True,
                                              "pages": {WF: 2}}}}), encoding="utf-8")
    tm = TeamMap(tmp_path / "team_map.json")
    tm.decide("T1", "org", "t1", "test", org_name="T1")
    tm.decide("Weibo Gaming", "org", "weibo-gaming", "test", org_name="Weibo Gaming")
    tm.save()
    places = [{"objectname": f"p{i}", "pagename": WF, "placement": pl, "opponentname": team, "opponenttype": "team",
               "mode": "", "prizepoolindex": 1, "opponenttemplate": team.lower(), "qualifier": "q",
               # a placing's date is that team's exit: the 3rd-4th team left first, so dates must not order standings
               "date": d} for i, (pl, team, d) in enumerate([("1", "T1", "2025-11-30 15:30:00"),
                                                             ("2", "Weibo Gaming", "2025-11-30 15:30:00"),
                                                             ("3-4", "Team Liquid", "2025-11-29 12:00:00")])]
    places.append({"objectname": "mvp", "pagename": WF, "placement": "", "opponentname": "Someone",
                   "opponenttype": "solo", "mode": "award_individual", "prizepoolindex": 2})
    p_id = RawPayloadStore(raw).store(endpoint="placement", params={}, http_status=200, payload={"result": places},
                                      body_text=None, fetched_at=WHEN, source="liquipedia")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
                       VALUES ('placement', 'pagename', %s, %s, 4, %s)""", (WF, f"https://liquipedia.net/overwatch/{WF}", [p_id]))
    conn.commit()
    events.load_championships(conn, ev)
    events.load_placements(conn, ev)
    identity.load_identity(conn, identity.PlayerDecisions(tmp_path / "players.json"), tm)
    run = pipeline.run_reconciliation(conn, team_map_path=str(tm.path), map_path=str(write_map_file(tmp_path / "map.json")),
                                      decisions_path=str(tmp_path / "links.json"), events_path=str(ev))
    pipeline.store_run(conn, run)
    refresh(conn)
    conn.commit()
    yield conn, tmp_path, tm
    conn.close()
    raw.close()


def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchall()
    conn.commit()
    return r


def test_the_event_records_store_under_the_lp_championship_and_become_liquipedia_only_series(stage4):
    conn, _, _ = stage4
    rows = _one(conn, """SELECT s.sources, o1.org_id AS org1, o2.org_id AS org2 FROM series s
                          JOIN team_orgs o1 ON o1.team_id = s.side1_team_id JOIN team_orgs o2 ON o2.team_id = s.side2_team_id
                         WHERE s.championship_id = %s ORDER BY s.played_at""", (f"lp:{WF}",))
    assert len(rows) == 2
    assert all(r["sources"] == ["liquipedia"] for r in rows)
    assert [(r["org1"], r["org2"]) for r in rows] == [("t1", "weibo-gaming"), ("weibo-gaming", "t1")]


def test_the_liquipedia_only_orgs_survive_an_orgs_load(stage4):
    conn, tmp_path, _ = stage4
    orgs.load_decisions(conn, orgs.OrgDecisions(tmp_path / "org_decisions.json"))      # no FACEIT mapping for either
    assert {r["org_id"] for r in _one(conn, "SELECT org_id FROM orgs")} >= {"t1", "weibo-gaming"}
    assert len(_one(conn, "SELECT 1 FROM team_orgs WHERE team_id LIKE 'lp:team:%%'")) == 2


def test_a_korean_teams_record_at_the_event_answers(stage4):
    conn, _, _ = stage4
    a = ask(conn, "T1 record at the 2025 world finals")
    assert a.status == "ok", (a.code, a.reason)
    assert "2-0 in series" in a.sentence["text"], a.sentence
    assert a.attribution and any(WF in u for u in a.attribution.get("pages", [])), a.attribution


def test_a_player_stat_question_about_the_event_refuses_results_only_with_a_working_alternative(stage4):
    conn, _, _ = stage4
    a = ask(conn, "most eliminations at the 2025 world finals")
    assert a.status != "ok" and a.code == "results_only", (a.status, a.code, a.reason)
    assert a.alternatives, "a results-only refusal must offer what the slice can answer"
    alt = ask(conn, a.alternatives[0])
    assert alt.status == "ok", (a.alternatives[0], alt.code, alt.reason)


def test_who_won_the_event_is_its_first_placing_credited_to_its_page(stage4):
    conn, _, _ = stage4
    a = ask(conn, "who won the 2025 world finals")
    assert a.status == "ok", (a.code, a.reason)
    assert a.sentence["text"] == "T1 won OWCS 2025 World Finals."
    assert [r["team"] for r in a.rows] == ["T1"]
    assert a.attribution["pages"] == [f"https://liquipedia.net/overwatch/{WF}"]


def test_a_shared_placing_and_an_undecided_name_are_said_as_they_are(stage4):
    conn, _, _ = stage4
    a = ask(conn, "who placed 4th at the 2025 world finals")
    assert a.status == "ok", (a.code, a.reason)
    assert a.sentence["text"] == "Team Liquid placed 3rd-4th at OWCS 2025 World Finals."
    assert a.rows[0]["identity"] == "undecided"
    assert any("no identity decided yet: Team Liquid" in n for n in a.notes)


def test_a_teams_own_placing_and_the_standings(stage4):
    conn, _, _ = stage4
    a = ask(conn, "where did weibo gaming place at the 2025 world finals")
    assert a.status == "ok" and a.sentence["text"] == "Weibo Gaming placed 2nd at OWCS 2025 World Finals.", a.sentence
    a = ask(conn, "2025 world finals standings")
    assert a.sentence["text"] == "T1 won OWCS 2025 World Finals, ahead of Weibo Gaming (2nd) and Team Liquid (3rd-4th)."
    assert len(a.rows) == 3                                    # the MVP award is not a placing


def test_placings_agree_with_the_bracket_and_a_winner_who_lost_the_final_fails(stage4):
    from owcsmuse.consistency import run_checks

    conn, _, _ = stage4
    r = run_checks(conn, ["placement_consistency"])[0]
    conn.commit()
    assert r.ok, r.discrepancies
    with conn.cursor() as cur:   # the shape a bracket reset or a mixed-in LCQ pool would leave
        cur.execute("UPDATE liquipedia_placements SET place_high = 1, place_low = 1 WHERE team_name = 'Weibo Gaming'")
        cur.execute("UPDATE liquipedia_placements SET place_high = 2, place_low = 2 WHERE team_name = 'T1'")
    conn.commit()
    r = run_checks(conn, ["placement_consistency"])[0]
    conn.commit()
    assert not r.ok and r.discrepancies[0]["kind"] == "winner_lost_the_last_series"


def test_a_name_that_was_one_org_then_another_maps_its_liquipedia_team_to_each_in_turn(stage4):
    # ROC Esports: the 2024 roster, then a separate China org from 2025 (owner, 2026-10-09)
    conn, tmp_path, _ = stage4
    tm = TeamMap(tmp_path / "team_map.json")
    tm.data["roc esports"] = {"note": "test", "eras": [
        {"entity_type": "org", "entity_id": "roc-old", "org_name": "ROC", "valid_to": "2025-01-01T00:00:00+00:00"},
        {"entity_type": "org", "entity_id": "roc-china", "org_name": "ROC Esports", "valid_from": "2025-01-01T00:00:00+00:00"}]}
    tm.save()
    identity.load_identity(conn, identity.PlayerDecisions(tmp_path / "players.json"), tm)
    conn.commit()
    at = {r["y"]: r["org_id"] for r in _one(conn, """SELECT y, (SELECT org_id FROM team_identity_at('lp:team:roc esports', make_timestamptz(y, 6, 1, 0, 0, 0, 'UTC'))) AS org_id
                                                       FROM unnest(ARRAY[2024, 2025]) AS y""")}
    assert at == {2024: "roc-old", 2025: "roc-china"}
    rows = _one(conn, "SELECT org_id FROM team_orgs WHERE team_id = 'lp:team:roc esports' ORDER BY valid_from")
    assert [r["org_id"] for r in rows] == ["roc-old", "roc-china"]


def test_a_head_to_head_between_two_orgs_counts_their_series(stage4):
    # agg_head_to_head is keyed by raw team id: with an org on either side it matched nothing and said "ok" with an
    # empty row (Twisted Minds v Al Qadsiah on production, 2026-10-09)
    conn, _, _ = stage4
    a = ask(conn, "t1 series record against weibo gaming at the 2025 world finals")
    assert a.status == "ok", (a.code, a.reason)
    assert (a.rows[0]["wins"], a.rows[0]["losses"], a.rows[0]["matches"]) == (2, 0, 2)
    assert a.sentence["text"].startswith("T1 is 2-0 in series against Weibo Gaming at OWCS 2025 World Finals")
    none = ask(conn, "t1 series record against weibo gaming in 2024")
    assert none.status == "cannot_answer", "no series is no data, never an ok answer with an empty row"


def test_a_liquipedia_only_series_counts_at_map_grain(stage4):
    # 041: the maps were on Liquipedia and in no map-grain answer ("met, but no map stats on FACEIT")
    conn, _, _ = stage4
    a = ask(conn, "t1 vs weibo gaming at the 2025 world finals")
    assert a.status == "ok", (a.code, a.reason)
    r = a.rows[0]
    # the fixture's games: T1 3-1 (4 maps, all won by Liquipedia's team 1 = T1) and Weibo 2-3 T1 (5 maps, all team 1 = Weibo)
    assert (r["maps"], r["map_wins"], r["map_losses"]) == (9, 4, 5)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM liquipedia_rounds")
        assert cur.fetchone()["n"] == 9          # the event's two records' played games
    conn.commit()


def test_the_faceit_collector_never_lists_a_liquipedia_only_championship(stage4):
    # the first scheduled ingest after Stage 4 asked FACEIT for /championships/lp:.../matches and its 404 failed backfill
    from owcsmuse.collector import Collector
    from owcsmuse.config import Settings

    conn, _, _ = stage4
    col = Collector(conn, None, Settings(database_url="postgresql://unused"))
    ids = [c["championship_id"] for c in col.included_championships()]
    assert ids and not any(i.startswith("lp:") for i in ids)
    assert col.included_championships([f"lp:{WF}"]) == []          # not even when named
