"""Hero bans (049) in a real warehouse: the golden one, whose Liquipedia records carry bans (the 2025 international
events, Liquipedia-only, and one 2026 EMEA record linked to a FACEIT series). Needs OWCS_TEST_DATABASE_URL."""

from __future__ import annotations

import os

import pytest

from owcsmuse import heroes
from owcsmuse.consistency import check_fact_view_reconciliation, check_hero_bans
from owcsmuse.nlq.pipeline import ask

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")

LINKED = "faceit:1-a823bbde-de66-4928-8527-54f4e8882293"     # Twisted Minds 3-2 Geekay Esports, 2026 EMEA Stage 2


@pytest.fixture(scope="module")
def warehouse():
    from golden_support import build_golden_db
    conn, raw_conn = build_golden_db(DB_URL, "owcs_hero_bans")
    yield conn
    conn.close()
    raw_conn.close()


@pytest.fixture
def db(warehouse):
    """The warehouse, with whatever a test changes rolled back."""
    yield warehouse
    warehouse.rollback()


def _attribution(conn) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute("SELECT round_number, hero, display_name, opponent_display_name FROM fact_hero_bans "
                    "WHERE series_id = %s ORDER BY round_number, hero", (LINKED,))
        return [tuple(r.values()) for r in cur.fetchall()]


def _lp_flip(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT lp_flip FROM series WHERE series_id = %s", (LINKED,))
        return cur.fetchone()["lp_flip"]


def test_the_ban_view_is_materialized_and_refreshed_with_the_aggregates(db):
    from owcsmuse.aggregates import MATERIALIZED_VIEWS
    with db.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pg_matviews WHERE matviewname = 'fact_hero_bans' AND schemaname = current_schema()")
        assert cur.fetchone()["n"] == 1
    assert "fact_hero_bans" in MATERIALIZED_VIEWS


def test_every_ban_is_stored_once_known_and_attributed(db):
    assert check_hero_bans(db).ok, check_hero_bans(db).discrepancies
    fv = check_fact_view_reconciliation(db)
    assert fv.ok and fv.counts["fact_hero_bans"]["actual"] == fv.counts["fact_hero_bans"]["expected"] > 0


def test_a_linked_series_bans_follow_its_sides_whichever_order_liquipedia_lists_them(db):
    before = _attribution(db)
    assert before and _lp_flip(db) is False
    assert {(r[1], r[2]) for r in before if r[0] == 1} == {("Mizuki", "Twisted Minds"), ("Bastion", "Geekay Esports")}
    # the same record with Liquipedia's teams the other way round: names, scores, winner, rounds and ban sides
    with db.cursor() as cur:
        cur.execute("SELECT lp_objectname FROM series WHERE series_id = %s", (LINKED,))
        obj = cur.fetchone()["lp_objectname"]
        cur.execute("""UPDATE liquipedia_matches SET team1_name = team2_name, team2_name = team1_name,
                              score1 = score2, score2 = score1, winner = 3 - winner WHERE objectname = %s""", (obj,))
        cur.execute("UPDATE liquipedia_rounds SET score1 = score2, score2 = score1, winner = (3 - winner) %% 3 "
                    "WHERE lp_objectname = %s", (obj,))
        cur.execute("UPDATE liquipedia_bans SET side = 3 - side WHERE lp_objectname = %s", (obj,))
        cur.execute("REFRESH MATERIALIZED VIEW fact_hero_bans")     # 051: as the nightly refresh does
    assert _lp_flip(db) is True
    assert _attribution(db) == before


def test_a_ban_in_another_spelling_or_of_an_unknown_hero_fails_the_check(db):
    with db.cursor() as cur:
        cur.execute("SELECT lp_objectname, round_number FROM liquipedia_bans WHERE hero = 'D.Va' LIMIT 1")
        r = cur.fetchone()
        cur.execute("UPDATE liquipedia_bans SET hero = 'DVa' WHERE (lp_objectname, round_number, hero) = (%s, %s, 'D.Va')",
                    (r["lp_objectname"], r["round_number"]))
        cur.execute("REFRESH MATERIALIZED VIEW fact_hero_bans")
    kinds = {d["kind"] for d in check_hero_bans(db).discrepancies}
    assert {"unknown_hero", "spelling_variants"} <= kinds


def test_a_ban_before_its_heros_available_from_fails_the_check(db):
    # Wuyang's first golden ban is at the 2025 World Finals; a later available_from contradicts the record
    with db.cursor() as cur:
        cur.execute("UPDATE heroes SET available_from = '2025-12-31' WHERE hero = 'Wuyang'")
    found = [d for d in check_hero_bans(db).discrepancies if d["kind"] == "banned_before_available"]
    assert [d["hero"] for d in found] == ["Wuyang"]


def test_a_map_without_one_ban_per_team_fails_the_check(db):
    with db.cursor() as cur:
        cur.execute("DELETE FROM liquipedia_bans WHERE ctid = (SELECT ctid FROM liquipedia_bans WHERE side = 2 LIMIT 1)")
        cur.execute("REFRESH MATERIALIZED VIEW fact_hero_bans")
    assert any(d["kind"] == "not_one_ban_per_team" for d in check_hero_bans(db).discrepancies)


def test_a_hero_released_after_the_slice_is_not_never_banned_and_not_available(db):
    a = ask(db, "which heroes were never banned in 2026")
    assert a.status == "ok"
    never = {r["hero"] for r in a.rows}
    assert "D.Mon" not in never and "Doctrine" not in never          # available from 2026-10-10, after these maps
    assert "Soldier: 76" in never
    b = ask(db, "vendetta bans at the 2025 world finals")
    assert b.status == "cannot_answer" and "not available" in b.reason


def test_a_ban_question_before_bans_says_when_they_began(db):
    a = ask(db, "most banned hero in 2024")
    assert a.status == "cannot_answer" and a.code == "no_data"
    assert "Hero bans were introduced in 2025" in a.reason
    assert "most banned hero in 2025" in a.alternatives


def test_the_answer_credits_every_liquipedia_page_and_shows_the_ban_rows(db):
    a = ask(db, "which heroes does twisted minds ban most in 2026")
    assert a.status == "ok"
    assert a.attribution and any("2026/EMEA/Stage_2" in p for p in a.attribution["pages"])
    ev = a.evidence
    assert ev["available"] and ev["grain"] == "map"
    assert {r["team"] for r in ev["rows"]} == {"Twisted Minds"} and {r["opponent"] for r in ev["rows"]} == {"Geekay Esports"}


def test_a_player_bans_nothing(db):
    a = ask(db, "which heroes does sug2rfree ban most")
    assert a.status == "cannot_answer" and "hero bans are made by teams" in a.reason


def test_reloading_the_list_is_idempotent(db):
    first = heroes.load(db)
    assert heroes.load(db) == first
    assert heroes.from_db(db).canonical("Lucio") == "Lúcio"
