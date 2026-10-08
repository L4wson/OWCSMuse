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


# ------------------------------------------------------------------ every expectation is evaluated

def _expectation_paths(node, at: str = "") -> tuple[set[str], set[str]]:
    """(leaves, every node) of an expect tree, walked without the harness's vocabulary: a key the harness does not
    know is a leaf like any other, and so is reported unevaluated rather than silently ignored. An empty list or dict
    is a leaf: it expects nothing to be there."""
    leaves, nodes = set(), {at} if at else set()
    children = (node.items() if isinstance(node, dict) else
                ((f"[{i}]", v) for i, v in enumerate(node)) if isinstance(node, list) else ())
    children = [(k if str(k).startswith("[") else (f".{k}" if at else str(k)), v) for k, v in children]
    if not children:
        return {at}, nodes
    for k, v in children:
        sub_leaves, sub_nodes = _expectation_paths(v, f"{at}{k}")
        leaves |= sub_leaves
        nodes |= sub_nodes
    return leaves, nodes


def _gates(exp: dict) -> tuple[list[str], list[str]]:
    """Every clarify candidate id and every alternative question a case names, nested ones included, so a stub answer
    can open every gate and reach every expectation behind it."""
    cands, alts = [], []
    for key, v in exp.items():
        if key == "answer_candidate":
            cands.append(v["id"])
            c, a = _gates(v["expect"])
            cands += c
            alts += a
        elif key == "alternative":
            alts += [v["question_template"].format(season=s) for s in v["seasons_with_stat"]]
    return cands, alts


def _unevaluated(case: dict) -> tuple[list[str], list[str]]:
    """(expectations no check evaluated, check sources that name no expectation) for a case run against a stub answer
    that opens every gate. Values are not the point here: a check that ran and failed still evaluated its expectation."""
    cands, alts = _gates(case["expect"])

    def ask_fn(q):
        return _answer(candidates={"subject": [{"entity_id": i, "question": f"candidate {i}"} for i in cands]},
                       alternatives=alts)
    o = harness.evaluate(case, ask_fn)
    assert not o.error, f"{case['id']}: {o.error}"
    leaves, nodes = _expectation_paths(case["expect"])
    covered = {s for c in o.checks for s in c.sources}
    return sorted(leaves - covered), sorted(covered - nodes)


def test_every_expectation_in_every_case_is_evaluated():
    """A harness that silently skips an assertion makes every golden case untrustworthy: a rebound `exp` once skipped
    every check after by_match for G32-G34, and G24's 2025 leader was never compared. Proposed cases too: confirming
    one must not be the moment its expectations start being read."""
    problems = {}
    for case in json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]:
        skipped, unknown = _unevaluated(case)
        if skipped or unknown:
            problems[case["id"]] = {"never evaluated": skipped, "checks naming no expectation": unknown}
    assert not problems, problems


def test_an_expectation_the_harness_does_not_know_is_reported_not_ignored():
    case = dict(CASE, expect={"status": "ok", "rowz": [{"wins": 4}], "sentence_contains": ["4"]})
    skipped, _ = _unevaluated(case)
    assert skipped == ["rowz[0].wins"]


def test_every_kind_of_expectation_is_evaluated_after_by_match():
    # by_match first, then every key the vocabulary has: what the rebound `exp` used to skip
    exp = {"evidence": {"by_match": {"m1": {"score": "3-1", "sources": ["faceit"]}}, "total_rows": 2,
                        "regions_only": ["na"], "roles_only": ["Tank"]},
           "status": "ok", "code": None, "entity": {"role": "subject", "type": "player", "id": "p1", "name": "A"},
           "rows": [{"wins": 4}], "rows_only_players": ["A"], "limitations": ["offline_map_stats"],
           "candidate_ids": ["c1"], "sentence_contains": ["A"], "sentence_lacks": ["B"], "spans_match_text": True,
           "answer_candidate": {"id": "c1", "expect": {"status": "ok", "rows": [{"wins": 1}]}},
           "alternative": {"question_template": "q {season}", "seasons_with_stat": [2025, 2026],
                           "top1_by_season": {"2025": {"nickname": "A"}, "2026": {"nickname": "B"}},
                           "then_rows": [{"total": 9}]}}
    assert _unevaluated(dict(CASE, expect=exp)) == ([], [])


def test_a_malformed_spans_expectation_fails_rather_than_passing_unread():
    o = harness.evaluate(dict(CASE, expect={"spans_match_text": False}), lambda q: _answer())
    assert not o.ok
