"""Build a warehouse from the captured fixtures, so CI has something to check.

The consistency checks are not fixture tests - they run against whatever is
loaded - but CI needs *something* loaded. This ingests the same three captured
matches the integration tests use into a scratch schema, applies every reviewed
decision file in scope/ through its own loader, and refreshes, leaving a small but real warehouse for
`python -m owcsmuse check`.

    DATABASE_URL=... OWCS_DB_SCHEMA=owcs_test python tools/build_fixture_db.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))          # owcsmuse, when it is not pip-installed
sys.path.insert(0, str(ROOT / "tests"))

from agg_support import CH_2026, build_scratch_db  # noqa: E402  (needs the path above)
from golden_support import GOLDEN, GoldenClient, load_matches  # noqa: E402

from owcsmuse.collector import Collector  # noqa: E402
from owcsmuse.config import Settings  # noqa: E402
from owcsmuse.db import RawPayloadStore  # noqa: E402

from owcsmuse import aliases, orgs  # noqa: E402
from owcsmuse import groups as team_groups  # noqa: E402
from owcsmuse.aggregates import refresh  # noqa: E402
from owcsmuse.liquipedia import competition_names, identity  # noqa: E402
from owcsmuse.liquipedia import events as lp_events  # noqa: E402
from owcsmuse.liquipedia.teams import TeamMap  # noqa: E402


# Virtus pro's window on team id bb5dd404 opens at this series (2025-01-31, the first sighting of 'Virtuspro'); the
# three base matches hold only that id's 2024 Ex Oblivione series, so without it identity_windows would see a decided
# window covering nothing in the sample. The payload is the golden suite's own capture from production.
VP_WINDOW_OPENER = "1-36219ab4-6c07-4a9b-9321-89e1fd1a6d61"


def ingest_window_opener(conn, raw_conn, db_url: str) -> None:
    match = {VP_WINDOW_OPENER: load_matches()[VP_WINDOW_OPENER]}
    cid = match[VP_WINDOW_OPENER]["detail"]["competition_id"]
    scope = json.loads((GOLDEN / "championships.json").read_text(encoding="utf-8"))
    c = next(c for c in scope["championships"] if c["championship_id"] == cid)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizers (organizer_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (c["organizer_id"], scope["organizers"][c["organizer_id"]]))
        cur.execute(
            """INSERT INTO championships (championship_id, organizer_id, name, include, scope_region, tier, season,
                                          classification_source, decision_note)
               VALUES (%(championship_id)s, %(organizer_id)s, %(name)s, %(include)s, %(scope_region)s, %(tier)s,
                       %(season)s, %(classification_source)s, %(decision_note)s)""", c)
    conn.commit()
    sink = RawPayloadStore(raw_conn)
    col = Collector(conn, GoldenClient(sink, match), Settings(_env_file=None, faceit_api_key="x", database_url=db_url), sink)
    col.run_list([cid])
    col.run_detail()


def load_decisions(conn) -> dict:
    """Every scope/ file through its own loader, as production runs them, so `check` (decisions_loaded) sees a
    warehouse where the reviewed decisions are applied. A decision about a team, player or record the fixture does
    not hold is skipped by its loader exactly as it would be in production. Liquipedia link decisions need stored
    Liquipedia records, which the fixture has none of, so none of them applies here."""
    scope = ROOT / "scope"
    out = {"orgs": orgs.load_decisions(conn, orgs.OrgDecisions(scope / "org_decisions.json")),
           "aliases": aliases.load_decisions(conn, aliases.AliasDecisions(scope / "alias_decisions.json")),
           "identity": identity.load_identity(conn, identity.PlayerDecisions(scope / "player_identity_decisions.json"),
                                              TeamMap(scope / "liquipedia_team_map.json")),
           "competition_names": competition_names.load(
               conn, competition_names.CompetitionDecisions(scope / "competition_names.json"),
               competition_names.propose(scope / "liquipedia_map.json", scope / "decisions.json",
                                         scope / "competition_pages.json")),
           "events": lp_events.load_championships(conn, scope / "liquipedia_events.json"),
           "groups": team_groups.load(conn, scope / "partner_teams.json")}
    with conn.cursor() as cur:
        # the shared fixture labels its 2026 qualifier 'manual', but no decision in scope/decisions.json covers it:
        # it is the classifier's call here, as it would be in production
        cur.execute("UPDATE championships SET classification_source = 'auto' WHERE championship_id = %s", (CH_2026,))
    conn.commit()
    refresh(conn)
    return out


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
    ingest_window_opener(conn, raw_conn, db_url)
    loaded = load_decisions(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM fact_player_maps")
        maps = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM matches")
        matches = cur.fetchone()["n"]
    conn.commit()
    conn.close()
    raw_conn.close()
    print(f"built {schema}: {matches} matches, {maps} player-map rows; decisions loaded: {loaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
