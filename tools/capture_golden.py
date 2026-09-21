"""Capture the golden warehouse's inputs from payloads already stored in raw_payloads.

The golden suite (tests/test_golden_answers.py) asks real questions of a real,
small warehouse built from real FACEIT payloads. This copies those payloads, and
the scope decisions of the championships they belong to, out of the production
database once, so CI needs neither the database nor the network. No request is
made to FACEIT or Liquipedia.

    python tools/capture_golden.py            # reads DATABASE_URL, writes tests/golden/

The match list lives in tests/golden/matches.json and says why each match is
there. Payloads are stored verbatim; nothing is edited.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from owcsmuse.config import load_settings  # noqa: E402
from owcsmuse.db import connect  # noqa: E402

GOLDEN = ROOT / "tests" / "golden"


def main() -> int:
    settings = load_settings()
    manifest = json.loads((GOLDEN / "matches.json").read_text(encoding="utf-8"))
    ids = [m["match_id"] for m in manifest["matches"]]
    (GOLDEN / "payloads").mkdir(exist_ok=True)
    conn = connect(settings.database_url, schema=os.environ.get("OWCS_DB_SCHEMA", settings.db_schema))
    champs: dict[str, dict] = {}
    with conn.cursor() as cur:
        for mid in ids:
            cur.execute("""SELECT payload FROM raw_payloads WHERE endpoint = %s AND http_status = 200
                            ORDER BY fetched_at DESC, id DESC LIMIT 1""", (f"/matches/{mid}",))
            row = cur.fetchone()
            if not row:
                print(f"no stored detail payload for {mid}", file=sys.stderr)
                return 1
            detail = row["payload"]
            cur.execute("""SELECT http_status, payload FROM raw_payloads WHERE endpoint = %s
                            ORDER BY fetched_at DESC, id DESC LIMIT 1""", (f"/matches/{mid}/stats",))
            srow = cur.fetchone()
            stats = srow["payload"] if srow and srow["http_status"] == 200 else None
            (GOLDEN / "payloads" / f"{mid}.json").write_text(
                json.dumps({"detail": detail, "stats": stats, "stats_http_status": srow["http_status"] if srow else None},
                           indent=1, sort_keys=True), encoding="utf-8")
            champs[detail["competition_id"]] = {}
        cur.execute("SELECT * FROM championships WHERE championship_id = ANY(%s)", (list(champs),))
        rows = {r["championship_id"]: r for r in cur.fetchall()}
        cur.execute("SELECT organizer_id, name FROM organizers")
        organizers = {r["organizer_id"]: r["name"] for r in cur.fetchall()}
    out = []
    for cid in sorted(champs):
        r = rows[cid]
        out.append({k: r[k] for k in ("championship_id", "organizer_id", "name", "include", "scope_region", "tier",
                                      "season", "classification_source", "decision_note")})
    (GOLDEN / "championships.json").write_text(
        json.dumps({"championships": out, "organizers": {c["organizer_id"]: organizers.get(c["organizer_id"])
                                                          for c in out if c["organizer_id"]}}, indent=1),
        encoding="utf-8")
    print(f"captured {len(ids)} matches across {len(out)} championships into {GOLDEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
