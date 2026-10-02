"""No consistency check undercounts its own failures.

A LIMIT on a query that feeds discrepancies or a count caps the count without saying so: series_integrity once
reported 10 linked_sides_disagree where there were 15. `_result` already caps what is shown (MAX_DISCREPANCIES), and a
count's companion list is capped in Python (LISTED) after the count is taken. A LIMIT survives only on a diagnostic
sample, marked `# sample:` on the same line.
"""

import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "owcsmuse" / "consistency.py"


def test_no_limit_outside_a_marked_sample():
    offenders = []
    for n, line in enumerate(SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        if re.search(r"\bLIMIT\s+\d+", code) and "# sample:" not in line:
            offenders.append(f"{n}: {line.strip()}")
    assert not offenders, "a LIMIT feeds a count:\n" + "\n".join(offenders)
