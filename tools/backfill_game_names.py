"""Backfill player_game_names from the stored FACEIT match payloads.

    python tools/backfill_game_names.py            # needs DATABASE_URL (and OWCS_DB_SCHEMA)

Every /matches/{id} detail payload in raw_payloads carries the roster with each player's in-game name as it was
at that match. The collector kept only the latest value until migration 035; this walks the stored payloads in
fetch order and records every (GUID, in-game name) with the match's time as its sighting, so a renamed player's
earlier names become searchable (entity_names, historical_game_name). Sends nothing; reads raw_payloads only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from owcsmuse.collector import GAME_NAME_UPSERT  # noqa: E402
from owcsmuse.config import Settings  # noqa: E402
from owcsmuse.db import connect  # noqa: E402
from owcsmuse.parsers.matches import parse_match_detail  # noqa: E402


def backfill(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT player_id FROM players")
        known = {r["player_id"] for r in cur.fetchall()}
        cur.execute("""SELECT id, payload, fetched_at FROM raw_payloads
                        WHERE source = 'faceit' AND endpoint LIKE '/matches/%' AND endpoint NOT LIKE '%/stats'
                        ORDER BY fetched_at""")
        payloads = cur.fetchall()
        seen = rows = unparsed = 0
        for r in payloads:
            try:
                rec = parse_match_detail(r["payload"])
            except Exception:                      # a stub or an error body: not a match record
                unparsed += 1
                continue
            at = rec.event_time or r["fetched_at"]
            for e in rec.roster:
                if e.game_player_name and e.player_id in known:
                    cur.execute(GAME_NAME_UPSERT, {"id": e.player_id, "name": e.game_player_name, "seen": at})
                    rows += 1
            seen += 1
        cur.execute("SELECT count(*) AS n FROM player_game_names")
        total = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM (SELECT player_id FROM player_game_names GROUP BY player_id HAVING count(*) > 1) x")
        renamed = cur.fetchone()["n"]
        cur.execute("""SELECT p.player_id, p.nickname, p.game_player_name AS current, array_agg(g.game_player_name ORDER BY g.first_seen_at) AS names
                         FROM player_game_names g JOIN players p ON p.player_id = g.player_id
                        GROUP BY p.player_id, p.nickname, p.game_player_name HAVING count(*) > 1 ORDER BY p.nickname""")
        renames = [dict(x) for x in cur.fetchall()]
    conn.commit()
    return {"payloads_read": seen, "payloads_not_match_records": unparsed, "sightings_recorded": rows,
            "game_names_total": total, "players_with_more_than_one_name": renamed, "renames": renames}


def main() -> int:
    settings = Settings()
    with connect(settings.database_url, schema=settings.db_schema) as conn:
        out = backfill(conn)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
