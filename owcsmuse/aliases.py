"""Community shorthand for an entity ("SSG" for SpaceStation Gaming): decide, review, apply.

FACEIT's own nickname and team-name history already resolves an abbreviation
that a team really was named at some point (`entity_names` covers that; nothing
here is needed for it). This module is for the abbreviations FACEIT never
recorded, and community usage invented - a human decision, not something
derivable from the data, so it goes through the same reviewed-decisions-file
pattern as `scope.py` and `orgs.py` rather than a hardcoded guess table.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg

from .log import get_logger, log_event
from .resolve import fold

log = get_logger("owcsmuse.aliases")

DEFAULT_ALIAS_DECISIONS_PATH = Path("scope") / "alias_decisions.json"
ENTITY_TYPES = frozenset({"player", "team", "org"})


@dataclass
class Alias:
    alias: str          # folded
    entity_type: str
    entity_id: str
    note: Optional[str] = None
    decided_at: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AliasDecisions:
    """Reviewed alias -> entity mappings. Same shape as OrgDecisions / scope Decisions."""

    # the note written at the top of the decisions file; a subclass with its own file says what that file is
    FILE_NOTE = ("Reviewed community shorthand ('SSG' -> SpaceStation Gaming) that FACEIT's own name history "
                 "does not cover. Keys are the folded alias. An alias absent from this file resolves however "
                 "the fuzzy matcher in resolve.py already would - there is no fallback guess table. "
                 "Edit by hand or with `python -m owcsmuse alias set`.")

    def __init__(self, path: str | Path = DEFAULT_ALIAS_DECISIONS_PATH) -> None:
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                self.data = dict(json.load(f).get("aliases") or {})

    def get(self, alias: str) -> Optional[dict[str, Any]]:
        return self.data.get(fold(alias))

    def set(self, alias: str, entity_type: str, entity_id: str, note: Optional[str] = None) -> dict[str, Any]:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(ENTITY_TYPES)}, got {entity_type!r}")
        key = fold(alias)
        if not key:
            raise ValueError(f"alias folds to nothing: {alias!r}")
        d = {"entity_type": entity_type, "entity_id": entity_id, "note": note,
             "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.data[key] = {k: v for k, v in d.items() if v is not None}
        return self.data[key]

    def unset(self, alias: str) -> bool:
        return self.data.pop(fold(alias), None) is not None

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "note": self.FILE_NOTE,
            "aliases": dict(sorted(self.data.items())),
        }
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path


def load_decisions(conn: psycopg.Connection, decisions: AliasDecisions) -> dict[str, int]:
    """Write the decided aliases into entity_aliases. Only decided aliases are written."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM entity_aliases")
        written = 0
        for alias, d in decisions.data.items():
            cur.execute(
                "INSERT INTO entity_aliases (alias, entity_type, entity_id, note) VALUES (%s, %s, %s, %s)",
                (alias, d["entity_type"], d["entity_id"], d.get("note")),
            )
            written += 1
    conn.commit()
    out = {"aliases_written": written}
    log_event(log, logging.INFO, "alias_decisions_loaded", **out)
    return out


def list_aliases(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Aliases as loaded, joined to the entity's current display name, for `alias status`."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ea.alias, ea.entity_type, ea.entity_id, ea.note,
                   coalesce(en.current_name, ea.entity_id) AS current_name,
                   coalesce(en.matches, 0) AS matches
            FROM entity_aliases ea
            LEFT JOIN LATERAL (
                SELECT current_name, matches FROM entity_names n
                 WHERE n.entity_type = ea.entity_type AND n.entity_id = ea.entity_id
                 ORDER BY (n.name_kind = 'current_nickname' OR n.name_kind = 'current_name') DESC LIMIT 1
            ) en ON true
            ORDER BY ea.alias
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows
