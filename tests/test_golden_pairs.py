"""Golden answers for one pairing's every series, in a warehouse of its own (tests/golden/pairs).

sug2rfree v zeruhh, 11 series 2024-2026: 9 with FACEIT player stats (one of them missing a map /stats dropped), 2 with
results only and Liquipedia's maps. The map record and the series record must count the same 50 maps (Option A,
2026-10-17). Expected values: tests/golden/pairs/derive.py, from the raw payloads.

    OWCS_TEST_DATABASE_URL=... pytest -m golden tests/test_golden_pairs.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "golden"))
import harness  # noqa: E402

from owcsmuse.nlq.pipeline import ask  # noqa: E402

PAIRS = Path(__file__).parent / "golden" / "pairs"
DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = [pytest.mark.golden, pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")]

CASES = json.loads((PAIRS / "cases.json").read_text(encoding="utf-8"))["cases"]
CONFIRMED = [c for c in CASES if c["status"] == "confirmed"]


@pytest.fixture(scope="module")
def pairs_db():
    from golden_support import build_golden_db

    conn, raw_conn = build_golden_db(DB_URL, os.environ.get("OWCS_GOLDEN_PAIRS_SCHEMA", "owcs_golden_pairs"), PAIRS)
    yield conn
    conn.close()
    raw_conn.close()


def test_the_warehouse_holds_exactly_the_pairing(pairs_db):
    manifest = json.loads((PAIRS / "matches.json").read_text(encoding="utf-8"))
    with pairs_db.cursor() as cur:
        cur.execute("SELECT match_id FROM matches")
        loaded = {r["match_id"] for r in cur.fetchall()}
    assert loaded == {m["match_id"] for m in manifest["matches"]}


@pytest.mark.parametrize("case", CONFIRMED, ids=[c["id"] for c in CONFIRMED])
def test_golden_answer(pairs_db, case):
    outcome = harness.evaluate(case, lambda q: ask(pairs_db, q, with_evidence=True,
                                                   evidence_page_size=harness.EVIDENCE_PAGE))
    assert outcome.ok, "\n" + harness.render(outcome)


def test_both_grains_count_the_same_maps(pairs_db):
    by_id = {c["id"]: c for c in CASES}
    series = ask(pairs_db, by_id["G93"]["question"], with_evidence=False).rows[0]
    maps = ask(pairs_db, by_id["G94"]["question"], with_evidence=False).rows[0]
    assert (series["map_wins"], series["map_losses"], series["maps"]) == (maps["map_wins"], maps["map_losses"], maps["maps"])


def test_the_dropped_map_is_recovered_and_the_unplayed_entry_is_not(pairs_db):
    with pairs_db.cursor() as cur:
        cur.execute("""SELECT round_number, map_name, source FROM match_rounds
                        WHERE match_id = '1-1d2eaf73-7387-4f1f-b6c8-659dae4ca25f' ORDER BY round_number""")
        rounds = [(r["round_number"], r["map_name"], r["source"]) for r in cur.fetchall()]
        cur.execute("SELECT maps_played FROM matches WHERE match_id = '1-1d2eaf73-7387-4f1f-b6c8-659dae4ca25f'")
        played = cur.fetchone()["maps_played"]
    pairs_db.commit()
    assert rounds[0] == (1, "Ilios", "faceit_results") and [r[2] for r in rounds[1:]] == ["faceit"] * 3
    assert played == 4
