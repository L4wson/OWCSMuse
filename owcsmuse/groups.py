"""Season-scoped team groups (043): the OWCS partner teams, reviewed in scope/partner_teams.json.

Membership is per season and per region and changes year to year. It comes only from the reviewed file - Liquipedia's
own record of a Stage 1 prize-pool row whose qualifier is "Partner Team" - never from inference. `load` writes the file
into team_groups (the file is the whole truth); the team_group_members view resolves each Liquipedia name through the
decided anchors at its own date.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import psycopg

GROUPS_PATH = "scope/partner_teams.json"
GROUP_KEYS = ("partner",)


def load_file(path: Optional[str | Path] = None) -> list[dict[str, Any]]:
    """Every member row of the reviewed file, flattened: group, season, region, name, page, date."""
    p = Path(path or GROUPS_PATH)
    if not p.exists():
        return []
    doc = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for group, seasons in (doc.get("groups") or {}).items():
        if group not in GROUP_KEYS:
            raise ValueError(f"{p}: unknown group {group!r}")
        for season, regions in seasons.items():
            for region, members in regions.items():
                for m in members:
                    out.append({"group_key": group, "season": int(season), "region": region,
                                "liquipedia_name": m["liquipedia_name"], "page": m["page"], "placed_at": m["placed_at"],
                                "raw_id": doc.get("source_raw_id")})
    return out


def load(conn: psycopg.Connection, path: Optional[str | Path] = None) -> dict[str, Any]:
    rows = load_file(path)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM team_groups")
        cur.executemany(
            """INSERT INTO team_groups (group_key, season, region, liquipedia_name, page, placed_at, raw_id)
               VALUES (%(group_key)s, %(season)s, %(region)s, %(liquipedia_name)s, %(page)s, %(placed_at)s, %(raw_id)s)""",
            rows)
        cur.execute("SELECT liquipedia_name, season, region FROM team_group_members WHERE org_key IS NULL ORDER BY 2, 3, 1")
        unresolved = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return {"members": len(rows), "unresolved": unresolved}
