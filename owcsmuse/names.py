"""One spelling per map and per mode: FACEIT's.

Liquipedia's records spell some maps and modes differently from FACEIT and from themselves: "control" beside
"Control", "Watchpoint: Gibraltar" beside "Watchpoint Gibraltar", "Paraíso" beside "Paraiso". Every answer filters by
the exact stored value, and the validator picked one spelling out of a set - in an order Python's per-process hash seed
decides - so for the life of a process "on Control maps" read either 1,218 maps or 2 ("Twisted Minds has no series on
Control maps"), and two runs of the same question disagreed.

A name's canonical spelling is the one FACEIT's own rounds use most for its fold; failing that, the most common one.
Liquipedia's maps and modes are written in that spelling (enrich, the liquipedia_rounds rebuild), migration 048
rewrote what was stored, and the consistency check `name_variants` fails if two stored spellings ever fold together.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

import psycopg

from .resolve import fold


@dataclass
class Canon:
    maps: dict[str, str] = field(default_factory=dict)    # fold -> spelling
    modes: dict[str, str] = field(default_factory=dict)

    def map(self, name: Optional[str]) -> Optional[str]:
        return self.maps.get(fold(name), name) if name else name

    def mode(self, name: Optional[str]) -> Optional[str]:
        return self.modes.get(fold(name), name) if name else name


def _pick(rows: list[tuple[str, bool, int]]) -> dict[str, str]:
    """{fold: spelling}: the most-used FACEIT spelling of each fold, else the most-used one, ties by name."""
    faceit: dict[str, Counter] = defaultdict(Counter)
    every: dict[str, Counter] = defaultdict(Counter)
    for name, is_faceit, n in rows:
        if not name:
            continue
        k = fold(name)
        every[k][name] += n
        if is_faceit:
            faceit[k][name] += n
    out = {}
    for k, counts in every.items():
        pool = faceit.get(k) or counts
        out[k] = sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return out


def load(conn: psycopg.Connection) -> Canon:
    """The canonical spellings, from every stored round (match_rounds, and liquipedia_rounds for the maps only
    Liquipedia-only series have)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT map_name, game_mode, source = 'faceit' AS faceit, count(*) AS n FROM match_rounds
                        GROUP BY map_name, game_mode, source""")
        rows = cur.fetchall()
        cur.execute("SELECT to_regclass('liquipedia_rounds') IS NOT NULL AS present")
        if cur.fetchone()["present"]:
            cur.execute("SELECT map_name, game_mode, false AS faceit, count(*) AS n FROM liquipedia_rounds GROUP BY 1, 2")
            rows += cur.fetchall()
    return Canon(maps=_pick([(r["map_name"], r["faceit"], r["n"]) for r in rows]),
                 modes=_pick([(r["game_mode"], r["faceit"], r["n"]) for r in rows]))
