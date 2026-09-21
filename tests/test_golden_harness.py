"""The golden harness itself, offline: it must fail loudly and say expected against actual.

A golden suite that cannot fail, or fails with a message nobody can read, is the
same silent-wrong-answer problem one level up. These use fake answers, so no
database is needed.
"""

import json
from decimal import Decimal
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent / "golden"))
import harness  # noqa: E402

CASES_PATH = Path(__file__).parent / "golden" / "cases.json"


def _answer(**kw):
    base = dict(status="ok", code=None, reason=None, entities={}, rows=[], evidence=None, limitations=[], candidates={},
                alternatives=[], sentence={"text": "an answer"})
    base.update(kw)
    return SimpleNamespace(**base)


CASE = {"id": "T1", "title": "t", "kind": "exact", "question": "q", "derivation": "counted by hand",
        "expect": {"status": "ok", "rows": [{"wins": 4, "kd_ratio": "3.17"}]}}


def test_agreement_passes_and_numbers_compare_as_numbers():
    from decimal import Decimal
    o = harness.evaluate(CASE, lambda q: _answer(rows=[{"wins": 4, "kd_ratio": Decimal("3.1700")}]))
    assert o.ok, harness.render(o)


def test_a_changed_number_fails_and_the_message_shows_expected_and_actual():
    o = harness.evaluate(CASE, lambda q: _answer(rows=[{"wins": 3, "kd_ratio": Decimal("3.17")}]))
    text = harness.render(o)
    assert not o.ok
    assert "FAIL rows[0].wins" in text and "expected: 4" in text and "actual  : 3" in text
    assert "counted by hand" in text and "an answer" in text     # the derivation and the answer that was given


def test_an_answer_that_raises_is_a_failure_with_a_reason_not_a_crash():
    def boom(q):
        raise RuntimeError("db went away")
    o = harness.evaluate(CASE, boom)
    assert not o.ok and "RuntimeError" in harness.render(o)


def test_an_only_players_invariant_catches_a_stray_row():
    case = dict(CASE, expect={"rows_only_players": ["A", "B"]})
    assert harness.evaluate(case, lambda q: _answer(rows=[{"nickname": "A"}, {"nickname": "B"}])).ok
    o = harness.evaluate(case, lambda q: _answer(rows=[{"nickname": "A"}, {"nickname": "C"}]))
    assert not o.ok and "['C']" in harness.render(o)


def test_a_clarify_candidate_is_asked_verbatim():
    asked = []
    case = dict(CASE, expect={"answer_candidate": {"id": "x1", "expect": {"status": "ok"}}})

    def ask_fn(q):
        asked.append(q)
        if q == "q":
            return _answer(status="clarify", candidates={"subject": [{"entity_id": "x1", "question": "team:x1 record"}]})
        return _answer()
    assert harness.evaluate(case, ask_fn).ok
    assert asked == ["q", "team:x1 record"]     # the candidate's own question, unedited


def test_no_case_is_confirmed_without_a_derivation_and_a_kind():
    for c in json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]:
        assert c["derivation"].strip() and c["kind"] in ("exact", "invariant"), c["id"]
        assert c["status"] in ("proposed", "confirmed"), c["id"]


def test_at_least_half_the_cases_assert_exact_numbers():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    assert sum(c["kind"] == "exact" for c in cases) * 2 >= len(cases)
