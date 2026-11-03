"""The hero list (049): one canonical spelling per hero, and the day each became available to ban.

Hero bans come from Liquipedia only (owner, 2026-11-03), so a hero's canonical name is Liquipedia's spelling. FACEIT
and Liquipedia spell four heroes differently ("DVa" / "D.Va", "LifeWeaver" / "Lifeweaver", "Lucio" / "Lúcio",
"Torbjorn" / "Torbjörn"), and fold() alone does not join the first ("dva" against "d va"): a hero's key is its fold
with the spaces taken out, and the reviewed file's aliases cover the rest. The rebuild writes every ban in its canonical
spelling, and the consistency check `hero_bans` fails on a stored name the list does not hold (a new hero, or a new
spelling), the way `name_variants` does for maps and modes.

`available_from` decides "never banned": a hero is available on a map played on or after that day (UTC), and a hero
with no date was available before bans began. Without it, a hero released last month would be "never banned" in a
season it did not exist for.

`load` writes scope/heroes.json into `heroes`; the file is the whole truth. `migrate` runs it on every deploy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import psycopg

from .resolve import fold

HEROES_PATH = "scope/heroes.json"
ROOT = Path(__file__).resolve().parent.parent


def key(name: Optional[str]) -> str:
    """The spelling-blind key of a hero name: "D.Va", "DVa" and "d va" are one hero."""
    return fold(name).replace(" ", "")


@dataclass(frozen=True)
class Hero:
    name: str
    aliases: tuple[str, ...]
    available_from: Optional[date]
    basis: str


@dataclass
class HeroList:
    heroes: list[Hero] = field(default_factory=list)
    bans_introduced_season: Optional[int] = None

    def by_key(self) -> dict[str, str]:
        """key -> canonical name, for every name and alias."""
        out: dict[str, str] = {}
        for h in self.heroes:
            for n in (h.name, *h.aliases):
                out[key(n)] = h.name
        return out

    def canonical(self, name: Optional[str]) -> Optional[str]:
        """The canonical spelling, or the name unchanged when the list does not know it (the check then fails on it)."""
        if not name:
            return name
        return self.by_key().get(key(name), name)


def _path(path: Optional[str | Path]) -> Path:
    p = Path(path or HEROES_PATH)
    return p if p.is_absolute() or p.exists() else ROOT / p


def load_file(path: Optional[str | Path] = None) -> HeroList:
    p = _path(path)
    if not p.exists():
        return HeroList()
    doc = json.loads(p.read_text(encoding="utf-8"))
    heroes = []
    seen: dict[str, str] = {}
    for h in doc.get("heroes") or []:
        when = date.fromisoformat(h["available_from"]) if h.get("available_from") else None
        hero = Hero(h["name"], tuple(h.get("aliases") or ()), when, h.get("basis") or "")
        for n in (hero.name, *hero.aliases):
            k = key(n)
            if k in seen and seen[k] != hero.name:
                raise ValueError(f"{p}: '{n}' names both {seen[k]} and {hero.name}")
            seen[k] = hero.name
        heroes.append(hero)
    return HeroList(heroes, doc.get("bans_introduced_season"))


def load(conn: psycopg.Connection, path: Optional[str | Path] = None) -> dict[str, Any]:
    """Write the reviewed hero list into `heroes` and `hero_aliases` (the file is the whole truth). A missing file is an
    error, never an empty list: run from a directory without scope/, it would otherwise delete every hero."""
    if not _path(path).exists():
        raise FileNotFoundError(f"{_path(path)} not found")
    hl = load_file(path)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hero_aliases")
        cur.execute("DELETE FROM heroes")
        cur.executemany("INSERT INTO heroes (hero, available_from, basis) VALUES (%s, %s, %s)",
                        [(h.name, h.available_from, h.basis) for h in hl.heroes])
        cur.executemany("INSERT INTO hero_aliases (alias_key, hero) VALUES (%s, %s)",
                        [(k, name) for k, name in sorted(hl.by_key().items())])
        cur.execute("DELETE FROM hero_ban_settings")
        if hl.bans_introduced_season is not None:
            cur.execute("INSERT INTO hero_ban_settings (bans_introduced_season) VALUES (%s)", (hl.bans_introduced_season,))
    conn.commit()
    return {"heroes": len(hl.heroes), "dated": sum(h.available_from is not None for h in hl.heroes),
            "bans_introduced_season": hl.bans_introduced_season}


def from_db(conn: psycopg.Connection) -> HeroList:
    """The loaded list, for writing bans in canonical spelling. Empty before the first load (bans are then stored as
    Liquipedia spells them, and `hero_bans` fails until the list is loaded and the rebuild re-run)."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('heroes') IS NOT NULL AS present")
        if not cur.fetchone()["present"]:
            return HeroList()
        cur.execute("SELECT hero, available_from, basis FROM heroes ORDER BY hero")
        rows = cur.fetchall()
        cur.execute("SELECT alias_key, hero FROM hero_aliases")
        aliases: dict[str, list[str]] = {}
        for r in cur.fetchall():
            aliases.setdefault(r["hero"], []).append(r["alias_key"])
        cur.execute("SELECT bans_introduced_season FROM hero_ban_settings LIMIT 1")
        s = cur.fetchone()
    return HeroList([Hero(r["hero"], tuple(aliases.get(r["hero"], ())), r["available_from"], r["basis"]) for r in rows],
                    s["bans_introduced_season"] if s else None)
