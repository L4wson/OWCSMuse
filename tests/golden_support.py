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
    refresh(conn)
    return conn, raw_conn


def golden_schema() -> str:
    return os.environ.get("OWCS_GOLDEN_SCHEMA", "owcs_golden")
