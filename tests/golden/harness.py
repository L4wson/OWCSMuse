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
  sentence_contains        substrings the answer's sentence must contain
  sentence_lacks           substrings it must not contain
  spans_match_text         every entity span's text equals the sentence text at its offsets

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
    # the expectation(s) it evaluates, as paths into the case's "expect" (rows[0].wins, evidence.regions_only[1]); a
    # set comparison evaluates every element of its list at once
    sources: tuple[str, ...] = ()


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
        _apply(out, case["expect"], answer, ask_fn, prefix="", src="")
    except Exception as exc:  # an answer that raises is a failure with a reason, not a crash of the suite
        out.error = f"{type(exc).__name__}: {exc}"
    return out


def _check(out: Outcome, path: str, expected: Any, actual: Any, ok: bool | None = None, *, source: str | list[str]) -> None:
    sources = (source,) if isinstance(source, str) else tuple(source)
    out.checks.append(Check(path, expected, actual, _same(expected, actual) if ok is None else ok, sources))


def _each(src: str, items: list) -> list[str]:
    """The source paths of a list's elements: a check over the whole list evaluates each of them."""
    return [f"{src}[{i}]" for i in range(len(items))]


def _check_rows(out: Outcome, path: str, wants: list[dict], a, src: str) -> None:
    """Row i of the answer has the fields of wants[i]; `src` is where wants sits in the case's expect."""
    rows = a.rows or []
    _check(out, f"{path}rows returned (at least)", len(wants), len(rows), ok=len(rows) >= len(wants), source=src)
    for i, want in enumerate(wants):
        have = rows[i] if i < len(rows) else {}
        for k, v in want.items():
            _check(out, f"{path}rows[{i}].{k}", v, have.get(k), source=f"{src}[{i}].{k}")


def _check_row(out: Outcome, path: str, want: dict, a, src: str) -> None:
    """The answer's first row has the fields of `want` (a dict, not a list of rows)."""
    rows = a.rows or []
    have = rows[0] if rows else {}
    _check(out, f"{path}a row returned", True, bool(rows), ok=bool(rows), source=src)
    for k, v in want.items():
        _check(out, f"{path}rows[0].{k}", v, have.get(k), source=f"{src}.{k}")


def _text(a) -> str:
    return (a.sentence or {}).get("text", "") if isinstance(a.sentence, dict) else str(a.sentence or "")


def _apply(out: Outcome, exp: dict, a, ask_fn, prefix: str, src: str) -> None:
    """Every check names its source: the expectation it evaluates, so tests/test_golden_harness.py can prove that no
    expectation in any case goes unevaluated (a rebound `exp` once skipped every check after by_match for G32-G34)."""
    p = prefix
    if "status" in exp:
        _check(out, f"{p}status", exp["status"], a.status, source=f"{src}status")
    if "code" in exp:
        _check(out, f"{p}code", exp["code"], a.code, source=f"{src}code")
    if "entity" in exp:
        e = exp["entity"]
        role = e.get("role", "subject")
        got = (a.entities or {}).get(role) or {}
        _check(out, f"{p}entity[{role}] present", True, bool(got), ok=bool(got), source=f"{src}entity.role")
        for key, field_name in (("type", "entity_type"), ("id", "entity_id"), ("name", "current_name")):
            if key in e:
                _check(out, f"{p}entity[{role}].{key}", e[key], got.get(field_name), source=f"{src}entity.{key}")
    if "rows" in exp:
        _check_rows(out, p, exp["rows"], a, f"{src}rows")
    if "rows_only_players" in exp:
        allowed = set(exp["rows_only_players"])
        stray = [r.get("nickname") for r in (a.rows or []) if r.get("nickname") not in allowed]
        _check(out, f"{p}every ranked player is in the expected set", [], stray, ok=not stray,
               source=_each(f"{src}rows_only_players", exp["rows_only_players"]) or f"{src}rows_only_players")
    if "evidence" in exp:
        ev = exp["evidence"]
        rows = _evidence_rows(a)
        if "total_rows" in ev:
            _check(out, f"{p}evidence total_rows", ev["total_rows"], (a.evidence or {}).get("total_rows"),
                   source=f"{src}evidence.total_rows")
            _check(out, f"{p}evidence rows returned == total_rows", ev["total_rows"], len(rows),
                   source=f"{src}evidence.total_rows")
        if "regions_only" in ev:
            regions = sorted({(CHAMPIONSHIPS.get(r.get("championship_id")) or {}).get("scope_region") for r in rows})
            _check(out, f"{p}regions of the evidence rows", sorted(ev["regions_only"]), regions,
                   source=_each(f"{src}evidence.regions_only", ev["regions_only"]))
        if "roles_only" in ev:
            _check(out, f"{p}roles of the evidence rows", sorted(ev["roles_only"]), sorted({r.get("role") for r in rows}),
                   source=_each(f"{src}evidence.roles_only", ev["roles_only"]))
        for mid, want in (ev.get("by_match") or {}).items():
            # the row(s) behind one named series; for a map-grain answer, every map row of it must agree
            mine = [r for r in rows if r.get("match_id") == mid]
            _check(out, f"{p}evidence rows for {mid[:10]}", True, bool(mine), ok=bool(mine),
                   source=f"{src}evidence.by_match.{mid}")
            for k, v in want.items():
                got = sorted({str(r.get(k)) for r in mine}) if k != "sources" else sorted({tuple(r.get(k) or ()) for r in mine})
                wanted = [str(v)] if k != "sources" else [tuple(v)]     # never rebind `exp`: later checks read it
                at = f"{src}evidence.by_match.{mid}.{k}"
                _check(out, f"{p}evidence[{mid[:10]}].{k}", wanted, got, source=_each(at, v) if isinstance(v, list) else at)
    if "spans_match_text" in exp:
        sent = a.sentence if isinstance(a.sentence, dict) else {}
        text = sent.get("text", "")
        bad = [(sp.get("text"), text[sp["start"]:sp["end"]]) for sp in sent.get("spans") or []
               if text[sp["start"]:sp["end"]] != sp.get("text")]
        # only `true` means anything; any other value is a malformed case, and fails rather than passing unread
        ok = exp["spans_match_text"] is True and not bad and bool(sent.get("spans"))
        _check(out, f"{p}every entity span covers its own text", [], bad, ok=ok, source=f"{src}spans_match_text")
    for i, want in enumerate(exp.get("sentence_contains") or []):
        _check(out, f"{p}sentence contains {want!r}", want, _text(a), ok=want in _text(a),
               source=f"{src}sentence_contains[{i}]")
    for i, unwanted in enumerate(exp.get("sentence_lacks") or []):
        text = _text(a)
        _check(out, f"{p}sentence lacks {unwanted!r}", unwanted, text, ok=bool(text) and unwanted not in text,
               source=f"{src}sentence_lacks[{i}]")
    if "limitations" in exp:
        have = [x.get("id") for x in (a.limitations or [])]
        for i, want in enumerate(exp["limitations"]):
            _check(out, f"{p}limitation {want!r} carried", want, have, ok=want in have, source=f"{src}limitations[{i}]")
    if "candidate_ids" in exp:
        cands = sorted(c["entity_id"] for cs in (a.candidates or {}).values() for c in cs)
        _check(out, f"{p}clarify candidates", sorted(exp["candidate_ids"]), cands,
               source=_each(f"{src}candidate_ids", exp["candidate_ids"]))
    if "answer_candidate" in exp:
        want = exp["answer_candidate"]
        cand = next((c for cs in (a.candidates or {}).values() for c in cs if c["entity_id"] == want["id"]), None)
        _check(out, f"{p}candidate {want['id'][:8]} offered", want["id"], cand and cand["entity_id"], ok=cand is not None,
               source=f"{src}answer_candidate.id")
        if cand:
            _apply(out, want["expect"], ask_fn(cand["question"]), ask_fn, prefix=f"{p}[{cand['question']!r}] ",
                   src=f"{src}answer_candidate.expect.")
    if "alternative" in exp:
        alt = exp["alternative"]
        at = f"{src}alternative"
        offered = list(a.alternatives or [])
        pairs = [(s, alt["question_template"].format(season=s)) for s in alt["seasons_with_stat"]]
        hit = next(((s, q) for s, q in pairs if q in offered), None)
        _check(out, f"{p}an offered alternative is one of", [q for _, q in pairs], offered, ok=hit is not None,
               source=[f"{at}.question_template"] + _each(f"{at}.seasons_with_stat", alt["seasons_with_stat"]))
        if hit:
            s, q = hit
            b = ask_fn(q)
            _check(out, f"{p}alternative {q!r} answers", "ok", b.status, source=f"{at}.question_template")
            if alt.get("then_rows"):
                _check_rows(out, f"{p}[{q!r}] ", alt["then_rows"], b, f"{at}.then_rows")
        # every season's leader, not only the offered season's: each is the template's answer for that season
        for season, top in (alt.get("top1_by_season") or {}).items():
            q = alt["question_template"].format(season=season)
            _check_row(out, f"{p}[{q!r}] ", top, ask_fn(q), f"{at}.top1_by_season.{season}")


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
