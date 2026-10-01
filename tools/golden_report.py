"""Compare every golden case, proposed or confirmed, to what ask() answers. Asserts nothing.

    OWCS_TEST_DATABASE_URL=... python tools/golden_report.py [--only G01,G05] [--failures]

This is how a proposed case is reviewed before it is confirmed: the expected
value comes from independent.py, the actual from the code, and a disagreement
means either the code or the derivation is wrong. Resolve it against the raw
payload; do not edit the expected value to match the answer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "golden"))

import harness  # noqa: E402
from golden_support import build_golden_db, golden_schema  # noqa: E402

from owcsmuse.nlq.pipeline import ask  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--failures", action="store_true", help="print only the cases that disagree")
    args = ap.parse_args()
    url = os.environ.get("OWCS_TEST_DATABASE_URL")
    if not url:
        print("OWCS_TEST_DATABASE_URL is required (a scratch schema is rebuilt)", file=sys.stderr)
        return 2
    cases = json.loads((ROOT / "tests" / "golden" / "cases.json").read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    conn, raw_conn = build_golden_db(url, golden_schema())

    def ask_fn(question):
        return ask(conn, question, with_evidence=True, evidence_page_size=harness.EVIDENCE_PAGE)

    bad = 0
    for case in cases:
        o = harness.evaluate(case, ask_fn)
        bad += not o.ok
        if o.ok and args.failures:
            continue
        print(("AGREE " if o.ok else "DIFFER ") + case["status"].upper() + "\n" + harness.render(o) + "\n")
    print(f"{len(cases) - bad}/{len(cases)} cases agree with the independent derivation")
    conn.close()
    raw_conn.close()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
