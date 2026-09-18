"""Build a warehouse from the captured fixtures, so CI has something to check.

The consistency checks are not fixture tests - they run against whatever is
loaded - but CI needs *something* loaded. This ingests the same three captured
matches the integration tests use into a scratch schema, applies the reviewed
scope and org decisions, and refreshes, leaving a small but real warehouse for
`python -m owcsmuse check`.

    DATABASE_URL=... OWCS_DB_SCHEMA=owcs_test python tools/build_fixture_db.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))          # owcsmuse, when it is not pip-installed
sys.path.insert(0, str(ROOT / "tests"))

from agg_support import build_scratch_db  # noqa: E402  (needs the path above)


def main() -> int:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("OWCS_DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    schema = os.environ.get("OWCS_DB_SCHEMA", "owcs_test")
    if schema == "public":
        print("refusing to build fixtures into public; set OWCS_DB_SCHEMA", file=sys.stderr)
        return 2
    conn, raw_conn = build_scratch_db(db_url, schema)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM fact_player_maps")
        maps = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM matches")
        matches = cur.fetchone()["n"]
    conn.commit()
    conn.close()
    raw_conn.close()
    print(f"built {schema}: {matches} matches, {maps} player-map rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
