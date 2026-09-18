"""History-crawl tests: history-item parsing, competition classification, gap flags, Liquipedia parsing (offline),
plus a DB test that the first-map result from /players/{id}/history is overridden by the DETAIL phase."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

from owcsmuse.crawl import _gap_flags
from owcsmuse.liquipedia import parse_matches
from owcsmuse.parsers.matches import parse_history_item, parse_match_detail, results_differ, winner_flipped
from owcsmuse.parsers.stats import parse_match_stats
from owcsmuse.scope import Decisions, classify_history_competition

TWISTED_MINDS = "2b9f2e7a-f91a-4597-b2fa-d413eaed605e"
QADSIAH = "97ef2653-81b3-45e4-b57f-4df4c27d3ea0"
S9_PLAYOFFS = "f2f36b25-2979-4681-bc74-6a4d869cd1d5"


# ---------------------------------------------------------------- history item parsing

def test_history_item_parses_to_stub_with_first_map_result(fx):
    item = fx("history_item_first_map_result.json")
    rec = parse_history_item(item)
    assert rec.match_id == "1-2e89a222-e0f2-40c3-bd87-6b4d268d8495"
    assert rec.championship_id == S9_PLAYOFFS and rec.competition_name == "S9 EMEA OWCS Central - Playoffs"
    assert rec.organizer_id == "f0e8a591-08fd-4619-9d59-d97f0571842e"
    assert rec.faction1.team_id == TWISTED_MINDS and rec.faction1.name == "Twisted Minds"
    assert rec.faction2.team_id == QADSIAH and rec.faction2.name == "qadsiah"
    assert len(rec.roster) == 10 and {e.faction for e in rec.roster} == {"faction1", "faction2"}
    assert rec.status == "FINISHED" and rec.started_at.year == 2026
    # the quirk: history says 2-1 (map 1), detail says 3-0 (series)
    assert (rec.result.winner_faction, rec.result.faction1_score, rec.result.faction2_score) == ("faction1", 2, 1)
    detail = parse_match_detail(fx("match_detail_history_flip.json"))
    assert (detail.result.winner_faction, detail.result.faction1_score, detail.result.faction2_score) == ("faction1", 3, 0)
    assert results_differ(rec.result, detail.result) and not winner_flipped(rec.result, detail.result)


def test_history_page_items_all_parse(fx):
    page = fx("player_history_page_2026.json")
    recs = [parse_history_item(i) for i in page["items"]]
    assert len(recs) == 4 and all(r.faction1 and r.faction2 and r.roster for r in recs)
    assert {r.competition_name for r in recs} == {"S9 EMEA OWCS Central - Playoffs", "S9 EMEA OWCS Central - Regular Season"}


def test_2026_stats_full_key_set_and_time_played(fx):
    detail = parse_match_detail(fx("match_detail_history_flip.json"))
    rounds = parse_match_stats(fx("match_stats_history_flip.json"), detail.map_names, detail.match_id)
    assert len(rounds) == 3 and len(detail.picks) == 5
    keys = set()
    for r in rounds:
        for p in r.players:
            keys |= set(p.stats)
            assert p.time_played and p.time_played > 0
            assert p.final_blows is not None and p.eliminations is not None
    assert len(keys) == 47
    assert [r.game_mode for r in rounds] == ["Control", "Hybrid", "Flashpoint"] or all(r.game_mode for r in rounds)
    assert all(r.map_name for r in rounds)


# ---------------------------------------------------------------- classification

def test_history_competition_classification():
    jan = datetime(2025, 1, 31, tzinfo=timezone.utc)
    jun26 = datetime(2026, 6, 13, tzinfo=timezone.utc)
    c = classify_history_competition("S4 EMEA OWCS Central - Regular Season", jan)
    assert (c.region, c.tier, c.season, c.include) == ("emea", "main", 2025, True)
    c = classify_history_competition("S9 NA OWCS Central - Playoffs", jun26)
    assert (c.region, c.tier, c.season, c.include) == ("na", "main", 2026, True)
    c = classify_history_competition("OWCS Midseason Championship: Last Chance Qualifier at EWC (R", datetime(2025, 7, 17, tzinfo=timezone.utc))
    assert (c.region, c.tier, c.include) == ("international", "main", True)
    c = classify_history_competition("S8 EMEA OWCS Relegation S9 - Season 9", datetime(2026, 5, 25, tzinfo=timezone.utc))
    assert (c.region, c.tier, c.include) == ("emea", "relegation", True)
    c = classify_history_competition("S5 NA OWCS Relegation Central - Relegations", datetime(2025, 7, 13, tzinfo=timezone.utc))
    assert (c.tier, c.include) == ("relegation", False)
    c = classify_history_competition("S4 NA OWCS P&R Central - S4", datetime(2025, 4, 13, tzinfo=timezone.utc))
    assert (c.tier, c.include) == ("relegation", False)
    c = classify_history_competition("S10 NA OWCS P", datetime(2026, 8, 10, tzinfo=timezone.utc))
    assert (c.tier, c.include) == ("unknown", False) and any("review" in e for e in c.evidence)
    c = classify_history_competition("OWCS Obs Test", datetime(2025, 4, 11, tzinfo=timezone.utc))
    assert c.include is False and any("test" in e for e in c.evidence)
    c = classify_history_competition("S3 EMEA OWCS Central - Regular Season", datetime(2024, 10, 1, tzinfo=timezone.utc))
    assert c.include is False and any("outside" in e for e in c.evidence)
    c = classify_history_competition("Competitive - Elimination", jun26)
    assert c.include is False and c.tier == "unknown"


def test_decisions_override_history_classification(tmp_path):
    d = Decisions(tmp_path / "d.json")
    d.set("abc", include=True, tier="main", note="promotion counts this season")
    proposed = classify_history_competition("S10 NA OWCS P", datetime(2026, 8, 10, tzinfo=timezone.utc))
    final = d.apply("abc", proposed)
    assert final.include is True and final.tier == "main" and final.source == "manual"


# ---------------------------------------------------------------- gap flags

def test_gap_flags_detect_empty_and_thin_weeks_and_round_robin_shortfall():
    weeks = [{"week": date(2026, 6, 15), "n": 20}, {"week": date(2026, 6, 22), "n": 22}, {"week": date(2026, 7, 6), "n": 3}]
    flags = _gap_flags(weeks, {"name": "S9 EMEA OWCS Central - Regular Season", "teams": 12, "matches": 45})
    assert any("empty week" in f and "2026-06-29" in f for f in flags)
    assert any("single round robin of 12 teams (66)" in f for f in flags)
    ok = _gap_flags([{"week": date(2026, 6, 15), "n": 22}, {"week": date(2026, 6, 22), "n": 22}, {"week": date(2026, 6, 29), "n": 22}],
                    {"name": "S9 EMEA OWCS Central - Regular Season", "teams": 12, "matches": 66})
    assert ok == []
    assert _gap_flags([], {"name": "x"}) == ["no matches"]
    odd = _gap_flags([{"week": date(2026, 6, 15), "n": 5}], {"name": "S9 NA OWCS Central - Playoffs", "teams": 7, "matches": 5})
    assert any("odd team count" in f for f in odd)


# ---------------------------------------------------------------- liquipedia parsing

WIKITEXT = """
{{Matchlist|id=abc|title=Week 1
|M1={{Match
    |date=June 13, 2026 - 18:00 {{Abbr/CEST}}
    |opponent1={{TeamOpponent|Twisted Minds}}
    |opponent2={{TeamOpponent|Al Qadsiah}}
    |map1={{Map|map=Lijiang Tower|score1=2|score2=1|winner=1}}
    |map2={{Map|map=King's Row|winner=1}}
    |map3={{Map|map=Suravasa|winner=1}}
}}
|M2={{Match
    |date=June 14, 2026
    |opponent1={{TeamOpponent|Virtus.pro}}
    |opponent2={{TeamOpponent|Telacy}}
    |winner=2
    |map1={{Map|winner=2}}
    |map2={{Map|winner=1}}
    |map3={{Map|winner=2}}
}}
|M3={{Match
    |opponent1={{TeamOpponent|TBD}}
    |opponent2={{TeamOpponent|ENCE}}
}}
}}
"""


def test_liquipedia_wikitext_parsing():
    ms = parse_matches(WIKITEXT)
    assert len(ms) == 2  # the TBD match is skipped
    a, b = ms
    assert (a.team1, a.team2, a.date, a.score1, a.score2, a.winner) == ("Twisted Minds", "Al Qadsiah", "2026-06-13", 3, 0, 1)
    assert (b.team1, b.team2, b.date, b.score1, b.score2, b.winner) == ("Virtus.pro", "Telacy", "2026-06-14", 1, 2, 2)


# ---------------------------------------------------------------- DB: the override fires for history stubs

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")


@pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")
def test_history_stub_result_is_overridden_by_detail(fx):
    from owcsmuse.collector import Collector
    from owcsmuse.config import Settings
    from owcsmuse.db import RawPayloadStore, connect, migrate
    from owcsmuse.faceit.client import FetchResult
    from datetime import datetime as _dt
    from agg_support import MIGRATIONS

    schema = os.environ.get("OWCS_TEST_SCHEMA", "owcs_test")
    admin = connect(DB_URL, autocommit=True, schema=schema)
    admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    admin.close()
    conn = connect(DB_URL, schema=schema)
    raw_conn = connect(DB_URL, autocommit=True, schema=schema)
    migrate(conn, MIGRATIONS, schema)
    sink = RawPayloadStore(raw_conn)
    settings = Settings(_env_file=None, faceit_api_key="x", database_url=DB_URL)

    class FakeClient:
        def get_match(self, mid):
            payload = fx("match_detail_history_flip.json")
            rid = sink.store(endpoint=f"/matches/{mid}", params={}, http_status=200, payload=payload, body_text=None,
                             fetched_at=_dt.now(timezone.utc), match_id=mid)
            return FetchResult(f"/matches/{mid}", {}, 200, payload, rid, _dt.now(timezone.utc))

        def get_match_stats(self, mid):
            payload = fx("match_stats_history_flip.json")
            rid = sink.store(endpoint=f"/matches/{mid}/stats", params={}, http_status=200, payload=payload, body_text=None,
                             fetched_at=_dt.now(timezone.utc), match_id=mid)
            return FetchResult(f"/matches/{mid}/stats", {}, 200, payload, rid, _dt.now(timezone.utc))

    col = Collector(conn, FakeClient(), settings, sink)
    rec = parse_history_item(fx("history_item_first_map_result.json"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizers (organizer_id, name) VALUES (%s, 'FACEIT League - Overwatch')", (rec.organizer_id,))
        cur.execute(
            "INSERT INTO championships (championship_id, organizer_id, name, include, source, scope_region, tier, season, classification_source) "
            "VALUES (%s, %s, %s, true, 'history', 'emea', 'main', 2026, 'manual')",
            (rec.championship_id, rec.organizer_id, rec.competition_name),
        )
        col._upsert_teams(cur, rec)
        assert col._upsert_stub(cur, rec, rec.championship_id) is True
        cur.execute("UPDATE matches SET discovered_via = 'history', discovered_generation = 0 WHERE match_id = %s", (rec.match_id,))
    conn.commit()

    row = conn.execute("SELECT * FROM matches WHERE match_id = %s", (rec.match_id,)).fetchone()
    conn.commit()
    assert (row["winner_faction"], row["faction1_score"], row["faction2_score"], row["result_source"]) == ("faction1", 2, 1, "list")

    ds = col.run_detail()
    assert ds.complete == 1 and ds.result_changes == 1  # the override fired and was counted
    row = conn.execute("SELECT * FROM matches WHERE match_id = %s", (rec.match_id,)).fetchone()
    conn.commit()
    assert (row["winner_faction"], row["faction1_score"], row["faction2_score"], row["result_source"]) == ("faction1", 3, 0, "detail")
    assert (row["list_winner_faction"], row["list_faction1_score"], row["list_faction2_score"]) == ("faction1", 2, 1)
    assert row["result_flipped"] is False  # same winner, different score: a change, not a flip
    assert row["maps_played"] == 3 and row["maps_picked"] == 5 and row["discovered_via"] == "history"

    # full 2026 key set landed, and map durations populate from Time Played
    n_keys = conn.execute("SELECT count(DISTINCT k) AS n FROM match_players, jsonb_object_keys(stats) k WHERE match_id = %s", (rec.match_id,)).fetchone()["n"]
    dur = conn.execute("SELECT count(*) AS n, min(duration_seconds) AS lo FROM map_durations WHERE match_id = %s", (rec.match_id,)).fetchone()
    conn.commit()
    assert n_keys == 47 and dur["n"] == 3 and dur["lo"] > 0
    conn.close()
    raw_conn.close()
