"""The golden answer suite: real questions, asked end to end through ask(), against a real (small) warehouse.

Each case's expected answer was derived from the raw FACEIT payloads by
tests/golden/independent.py and confirmed by a person; none was copied from what
the code printed. A failure here therefore means an answer changed, and the
message shows expected against actual so the change can be judged: a bug, or a
correct improvement (in which case update cases.json and say why).

Only cases with "status": "confirmed" are asserted. "proposed" cases are reviewed
with `python tools/golden_report.py` and do not gate CI.

    OWCS_TEST_DATABASE_URL=... pytest -m golden tests/test_golden_answers.py
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

DB_URL = os.environ.get("OWCS_TEST_DATABASE_URL")
pytestmark = [pytest.mark.golden, pytest.mark.skipif(not DB_URL, reason="OWCS_TEST_DATABASE_URL not set")]

CASES = json.loads((Path(__file__).parent / "golden" / "cases.json").read_text(encoding="utf-8"))["cases"]
CONFIRMED = [c for c in CASES if c["status"] == "confirmed"]


@pytest.fixture(scope="module")
def golden_db():
    from golden_support import build_golden_db, golden_schema

    conn, raw_conn = build_golden_db(DB_URL, golden_schema())
    yield conn
    conn.close()
    raw_conn.close()


def test_the_warehouse_holds_exactly_the_golden_matches(golden_db):
    """If this fails, the fixture set moved and every expected value needs re-deriving."""
    manifest = json.loads((Path(__file__).parent / "golden" / "matches.json").read_text(encoding="utf-8"))
    with golden_db.cursor() as cur:
        cur.execute("SELECT match_id FROM matches")
        loaded = {r["match_id"] for r in cur.fetchall()}
    assert loaded == {m["match_id"] for m in manifest["matches"]}


@pytest.mark.parametrize("case", CONFIRMED, ids=[c["id"] for c in CONFIRMED])
def test_golden_answer(golden_db, case):
    def ask_fn(question):
        return ask(golden_db, question, with_evidence=True, evidence_page_size=harness.EVIDENCE_PAGE)

    outcome = harness.evaluate(case, ask_fn)
    known = case.get("known_bug")
    if known:
        # The expectation is right and the code is wrong today. The case stays visible instead of being deleted or
        # loosened, and CI stays green; the day the bug is fixed this fails, and the known_bug must be removed.
        if outcome.ok:
            pytest.fail(f"{case['id']} now agrees with its expectation: delete its known_bug ({known!r}).")
        pytest.xfail(f"known bug: {known}")
    assert outcome.ok, "\n" + harness.render(outcome)



def test_attribution_does_not_depend_on_evidence_being_asked_for(golden_db):
    """The values were presented whether or not the rows behind them were: an answer asked without evidence once
    carried no attribution at all. Every attribution case must credit the same pages with evidence off."""
    cases = [c for c in CONFIRMED if c["expect"].get("attribution_pages")]
    assert cases, "no golden case asserts attribution"
    for case in cases:
        a = ask(golden_db, case["question"], with_evidence=False)
        have = (a.attribution or {}).get("pages") or []
        assert set(case["expect"]["attribution_pages"]) <= set(have), (case["id"], have)
