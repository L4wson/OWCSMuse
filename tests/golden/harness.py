"""Run a golden case through ask() and say, field by field, where the answer differs from what was expected.

The expectations are data (cases.json), not code, so a reviewer reads the number
and not a test body. A case's "expect" is a vocabulary, and every key is optional:

  status / code            the answer's status and refusal code
  entity                   {role, type, id, name}: who the question resolved to
  rows                     list of {field: value}; row i must have those fields (numbers compare as numbers)
  rows_only_players        every ranked row's player must be one of these
  evidence                 {total_rows, regions_only, roles_only}: the rows behind the answer
  limitations              limitation ids the answer must carry
  candidate_ids            a clarify's candidates, as a set
  answer_candidate         {id, expect}: ask that candidate's own question, verbatim, and check the result
  alternative              a refusal's offered questions: one must be a listed template that answers as expected

This module never computes an expected value. That is independent.py's job.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

GOLDEN = Path(__file__).parent
CHAMPIONSHIPS = {c["championship_id"]: c for c in
                 json.loads((GOLDEN / "championships.json").read_text(encoding="utf-8"))["championships"]}
EVIDENCE_PAGE = 500          # large enough that "all evidence rows" really is all of them for these questions


@dataclass
class Check:
    path: str
    expected: Any
    actual: Any
    ok: bool


@dataclass
class Outcome:
    case: dict
    checks: list[Check] = field(default_factory=list)
    sentence: str = ""
    error: str = ""

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def ok(self) -> bool:
        return not self.error and not self.failures


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str) and actual is not None and not isinstance(actual, str):
        try:
            return Decimal(expected) == Decimal(str(actual)).quantize(Decimal(expected))
        except Exception:
            return str(actual) == expected
    if isinstance(actual, Decimal) and isinstance(expected, (int, float)):
        return actual == Decimal(str(expected))
    return expected == actual


def _evidence_rows(answer) -> list[dict]:
    ev = answer.evidence or {}
    return list(ev.get("rows") or [])


def _sentence(answer) -> str:
    s = answer.sentence or {}
    return s.get("text") or answer.reason or ""


def evaluate(case: dict, ask_fn: Callable[[str], Any]) -> Outcome:
    """`ask_fn(question)` returns an Answer with the evidence page large enough to hold every row."""
    out = Outcome(case=case)
    try:
        answer = ask_fn(case["question"])
        out.sentence = _sentence(answer)
        _apply(out, case["expect"], answer, ask_fn, prefix="")
    except Exception as exc:  # an answer that raises is a failure with a reason, not a crash of the suite
        out.error = f"{type(exc).__name__}: {exc}"
    return out


def _check(out: Outcome, path: str, expected: Any, actual: Any, ok: bool | None = None) -> None:
    out.checks.append(Check(path, expected, actual, _same(expected, actual) if ok is None else ok))


def _apply(out: Outcome, exp: dict, a, ask_fn, prefix: str) -> None:
    p = prefix
    if "status" in exp:
        _check(out, f"{p}status", exp["status"], a.status)
    if "code" in exp:
        _check(out, f"{p}code", exp["code"], a.code)
    if "entity" in exp:
        e = exp["entity"]
        role = e.get("role", "subject")
        got = (a.entities or {}).get(role) or {}
        for key, field_name in (("type", "entity_type"), ("id", "entity_id"), ("name", "current_name")):
            if key in e:
                _check(out, f"{p}entity[{role}].{key}", e[key], got.get(field_name))
    if "rows" in exp:
        rows = a.rows or []
        _check(out, f"{p}rows returned (at least)", len(exp["rows"]), len(rows), ok=len(rows) >= len(exp["rows"]))
        for i, want in enumerate(exp["rows"]):
            have = rows[i] if i < len(rows) else {}
            for k, v in want.items():
                _check(out, f"{p}rows[{i}].{k}", v, have.get(k))
    if "rows_only_players" in exp:
        allowed = set(exp["rows_only_players"])
        stray = [r.get("nickname") for r in (a.rows or []) if r.get("nickname") not in allowed]
        _check(out, f"{p}every ranked player is in the expected set", [], stray, ok=not stray)
    if "evidence" in exp:
        ev = exp["evidence"]
        rows = _evidence_rows(a)
        if "total_rows" in ev:
            _check(out, f"{p}evidence total_rows", ev["total_rows"], (a.evidence or {}).get("total_rows"))
            _check(out, f"{p}evidence rows returned == total_rows", ev["total_rows"], len(rows))
        if "regions_only" in ev:
            regions = sorted({(CHAMPIONSHIPS.get(r.get("championship_id")) or {}).get("scope_region") for r in rows})
            _check(out, f"{p}regions of the evidence rows", sorted(ev["regions_only"]), regions)
        if "roles_only" in ev:
            _check(out, f"{p}roles of the evidence rows", sorted(ev["roles_only"]), sorted({r.get("role") for r in rows}))
    if "limitations" in exp:
        have = [x.get("id") for x in (a.limitations or [])]
        missing = [x for x in exp["limitations"] if x not in have]
        _check(out, f"{p}limitations carried", exp["limitations"], have, ok=not missing)
    if "candidate_ids" in exp:
        cands = [c["entity_id"] for cs in (a.candidates or {}).values() for c in cs]
        _check(out, f"{p}clarify candidates", sorted(exp["candidate_ids"]), sorted(cands))
    if "answer_candidate" in exp:
        want = exp["answer_candidate"]
        cand = next((c for cs in (a.candidates or {}).values() for c in cs if c["entity_id"] == want["id"]), None)
        _check(out, f"{p}candidate {want['id'][:8]} offered", want["id"], cand and cand["entity_id"], ok=cand is not None)
        if cand:
            _apply(out, want["expect"], ask_fn(cand["question"]), ask_fn, prefix=f"{p}[{cand['question']!r}] ")
    if "alternative" in exp:
        alt = exp["alternative"]
        offered = list(a.alternatives or [])
        pairs = [(s, alt["question_template"].format(season=s)) for s in alt["seasons_with_stat"]]
        hit = next(((s, q) for s, q in pairs if q in offered), None)
        _check(out, f"{p}an offered alternative is one of", [q for _, q in pairs], offered, ok=hit is not None)
        if hit:
            s, q = hit
            b = ask_fn(q)
            _check(out, f"{p}alternative {q!r} answers", "ok", b.status)
            if alt.get("top1_by_season"):
                _apply(out, {"rows": [alt["top1_by_season"][str(s)]]}, b, ask_fn, prefix=f"{p}[{q!r}] ")
            if alt.get("then_rows"):
                _apply(out, {"rows": alt["then_rows"]}, b, ask_fn, prefix=f"{p}[{q!r}] ")


def render(o: Outcome) -> str:
    c = o.case
    head = f"GOLDEN {c['id']} [{c['kind']}] {c['title']}"
    lines = [head, f"  question   : {c['question']}"]
    if c.get("regression"):
        lines.append(f"  regression : {c['regression']}")
    if o.error:
        lines.append(f"  ERROR      : {o.error}")
    for f in o.failures:
        lines.append(f"  FAIL {f.path}")
        lines.append(f"       expected: {f.expected!r}")
        lines.append(f"       actual  : {f.actual!r}")
    passed = len(o.checks) - len(o.failures)
    lines.append(f"  {passed}/{len(o.checks)} checks agree")
    if o.sentence:
        lines.append(f"  answered   : {o.sentence}")
    lines.append(f"  expected because: {c['derivation']}")
    if not o.ok:
        lines.append("  An answer changed. If the new answer is a bug, fix the code. If it is a correct improvement, "
                     "change the value in tests/golden/cases.json and say why in the commit; the value must still "
                     "come from independent.py, not from this output.")
    return "\n".join(lines)
