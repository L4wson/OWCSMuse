"""Build the golden warehouse: real FACEIT payloads, real scope, real identity decisions.

Unlike agg_support (three fixture matches, no NA data, no org decisions), this
warehouse holds the twenty real matches in tests/golden/matches.json and applies
the repository's own scope/org_decisions.json and scope/alias_decisions.json, so
a question about sug2rfree or "SSG" runs through the same identity decisions
production does. Nothing here contacts FACEIT or Liquipedia.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from owcsmuse.aggregates import refresh
from owcsmuse.aliases import AliasDecisions
from owcsmuse.aliases import load_decisions as load_alias_decisions
from owcsmuse.collector import Collector
from owcsmuse.config import Settings
from owcsmuse.db import RawPayloadStore, connect, migrate
from owcsmuse.faceit.client import FaceitNotFound, FetchResult, ListResult
from owcsmuse.liquipedia import competition_names as lp_names
from owcsmuse.liquipedia import enrich as lp_enrich
from owcsmuse.liquipedia import events as lp_events
from owcsmuse.liquipedia import identity as lp_identity
from owcsmuse.liquipedia.teams import TeamMap
from owcsmuse.liquipedia import pipeline as lp_pipeline
from owcsmuse.orgs import OrgDecisions
from owcsmuse.orgs import load_decisions as load_org_decisions

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).parent / "golden"
MIGRATIONS = str(ROOT / "migrations")


def load_matches() -> dict[str, dict]:
    """match_id -> {"detail", "stats", "stats_http_status"}, exactly as captured."""
    manifest = json.loads((GOLDEN / "matches.json").read_text(encoding="utf-8"))
    return {m["match_id"]: json.loads((GOLDEN / "payloads" / f"{m['match_id']}.json").read_text(encoding="utf-8"))
            for m in manifest["matches"]}


class GoldenClient:
    """Serves the captured payloads through the FaceitClient interface the collector uses."""

    def __init__(self, sink: RawPayloadStore, matches: dict[str, dict]):
        self.sink = sink
        self.matches = matches

    def _fetch(self, endpoint, payload, match_id=None, championship_id=None, status=200):
        now = datetime.now(timezone.utc)
        raw_id = self.sink.store(endpoint=endpoint, params={}, http_status=status, payload=payload, body_text=None,
                                 fetched_at=now, match_id=match_id, championship_id=championship_id)
        return FetchResult(endpoint, {}, status, payload, raw_id, now)

    def list_championship_matches(self, championship_id, match_type="all"):
        items = [m["detail"] for m in self.matches.values() if m["detail"]["competition_id"] == championship_id]
        self._fetch(f"/championships/{championship_id}/matches", {"items": items}, championship_id=championship_id)
        return ListResult(items=items, pages=1, truncated=False)

    def get_match(self, match_id):
        return self._fetch(f"/matches/{match_id}", self.matches[match_id]["detail"], match_id=match_id)

    def get_match_stats(self, match_id):
        m = self.matches[match_id]
        if m["stats"] is None:
            self._fetch(f"/matches/{match_id}/stats", {"errors": [{"message": "not found"}]}, match_id=match_id, status=404)
            raise FaceitNotFound(404, f"/matches/{match_id}/stats")
        return self._fetch(f"/matches/{match_id}/stats", m["stats"], match_id=match_id)


def build_golden_db(db_url: str, schema: str):
    """Drop + recreate `schema`, ingest the golden matches, apply identity decisions, refresh."""
    assert schema != "public"
    admin = connect(db_url, autocommit=True, schema=schema)
    admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    admin.close()
    conn = connect(db_url, schema=schema)
    raw_conn = connect(db_url, autocommit=True, schema=schema)
    migrate(conn, MIGRATIONS, schema)

    scope = json.loads((GOLDEN / "championships.json").read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for oid, name in scope["organizers"].items():
            cur.execute("INSERT INTO organizers (organizer_id, name) VALUES (%s, %s)", (oid, name))
        for c in scope["championships"]:
            cur.execute(
                """INSERT INTO championships (championship_id, organizer_id, name, include, scope_region, tier, season,
                                              classification_source, decision_note)
                   VALUES (%(championship_id)s, %(organizer_id)s, %(name)s, %(include)s, %(scope_region)s, %(tier)s,
                           %(season)s, %(classification_source)s, %(decision_note)s)""", c)
    conn.commit()

    matches = load_matches()
    sink = RawPayloadStore(raw_conn)
    settings = Settings(_env_file=None, faceit_api_key="x", database_url=db_url)
    col = Collector(conn, GoldenClient(sink, matches), settings, sink)
    col.run_list()
    col.run_detail()

    load_org_decisions(conn, OrgDecisions(str(ROOT / "scope" / "org_decisions.json")))
    load_alias_decisions(conn, AliasDecisions(str(ROOT / "scope" / "alias_decisions.json")))
    # the reviewed OWCS competition names, as `migrate` loads them in production
    lp_names.load(conn, lp_names.CompetitionDecisions(ROOT / lp_names.DEFAULT_DECISIONS_PATH),
                  lp_names.propose(ROOT / lp_names.DEFAULT_MAP_PATH, ROOT / lp_names.DEFAULT_SCOPE_PATH,
                                   ROOT / lp_names.DEFAULT_EXTRA_PATH))
    load_liquipedia_enrichment(conn, raw_conn)
    # Stage 3: the reviewed cross-source anchors (team names from the team map, players from their decisions file)
    lp_identity.load_identity(conn, lp_identity.PlayerDecisions(ROOT / "scope" / "player_identity_decisions.json"),
                              TeamMap(ROOT / "scope" / "liquipedia_team_map.json"))
    refresh(conn)
    return conn, raw_conn


def load_liquipedia_enrichment(conn, raw_conn) -> None:
    """The captured Liquipedia records (tests/golden/liquipedia_matches.json), reconciled, stored and enriched exactly
    as production does it - offline, no request, same run_reconciliation() + store_run() + enrich.enrich()."""
    path = GOLDEN / "liquipedia_matches.json"
    if not path.exists():
        return
    records = json.loads(path.read_text(encoding="utf-8"))["matches"]
    sink = RawPayloadStore(raw_conn)
    now = datetime.now(timezone.utc)
    raw_id = sink.store(endpoint="match", params={}, http_status=200,
                        payload={"result": [r["record"] for r in records]}, body_text=None, fetched_at=now,
                        source="liquipedia")
    pages = json.loads((GOLDEN / "liquipedia_map.json").read_text(encoding="utf-8"))["pages"]
    with conn.cursor() as cur:
        for page in {e["page"] for e in pages.values()}:
            cur.execute(
                """INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
                   VALUES ('match', 'pagename', %s, %s, %s, %s)""",
                (page, f"https://liquipedia.net/overwatch/{page}", len(records), [raw_id]))
    conn.commit()
    events_path = ROOT / "scope" / "liquipedia_events.json"
    load_stage4_events(conn, sink, now, events_path)
    # the repository's own reviewed team map and link decisions, as production reconciles: the 2024 NA records carry no
    # FACEIT id and link only through decided team names; the grand final and the Dallas series through link decisions
    run = lp_pipeline.run_reconciliation(conn, team_map_path=str(ROOT / "scope" / "liquipedia_team_map.json"),
                                         decisions_path=str(ROOT / "scope" / "liquipedia_link_decisions.json"),
                                         map_path=str(GOLDEN / "liquipedia_map.json"), events_path=str(events_path))
    lp_pipeline.store_run(conn, run)
    lp_enrich.enrich(conn, run, str(ROOT / "scope" / "liquipedia_team_map.json"))
    lp_events.load_placements(conn, events_path)


def load_stage4_events(conn, sink, now, events_path) -> None:
    """Stage 4's captured records (tests/golden/liquipedia_events.json): stored as responses with their coverage, and
    the repository's own scope/liquipedia_events.json loaded as `lp:` championships, as production does it."""
    path = GOLDEN / "liquipedia_events.json"
    if not path.exists():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    # The event series wait on the owner's identity decisions (the file's `load_matches`): loaded before them, a
    # team's record would count its event series against decided opponents and silently drop the rest (Twisted
    # Minds: 2 of its 5 2025 World Finals series). Placings resolve nothing into a record, so they load now.
    loads = [("placement", doc["placements"])] + ([("match", doc["matches"])] if doc.get("load_matches") else [])
    with conn.cursor() as cur:
        for endpoint, records in loads:
            raw_id = sink.store(endpoint=endpoint, params={}, http_status=200, payload={"result": records},
                                body_text=None, fetched_at=now, source="liquipedia")
            for page in sorted({r["pagename"] for r in records}):
                cur.execute("""INSERT INTO liquipedia_coverage (endpoint, field, value, page_url, rows_seen, raw_ids)
                               VALUES (%s, 'pagename', %s, %s, %s, %s)""",
                            (endpoint, page, f"https://liquipedia.net/overwatch/{page}",
                             sum(r["pagename"] == page for r in records), [raw_id]))
    conn.commit()
    lp_events.load_championships(conn, events_path)


def golden_schema() -> str:
    return os.environ.get("OWCS_GOLDEN_SCHEMA", "owcs_golden")
