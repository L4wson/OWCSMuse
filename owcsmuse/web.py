"""Shareable question links and suggestion lists: the non-HTTP half of the web layer.

Kept out of `api.py` so it can be tested without an HTTP client, and so a slug
means the same thing wherever it is produced.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import psycopg

from .log import get_logger, log_event

log = get_logger("owcsmuse.web")

SLUG_LENGTH = 12
_SPACES = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    """What counts as the same question: case and whitespace do not, wording does."""
    return _SPACES.sub(" ", (question or "").strip()).lower()


def slug_for(question: str, parser: str = "rules") -> str:
    """A deterministic id for a question, so the same ask always shares the same link."""
    digest = hashlib.sha256(f"{parser}\x00{normalize_question(question)}".encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:SLUG_LENGTH]


@dataclass
class SavedQuery:
    slug: str
    question: str
    parser: str = "rules"
    structured_query: Optional[dict] = None
    times_asked: int = 1

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def remember_question(conn: psycopg.Connection, question: str, parser: str = "rules",
                      structured_query: Optional[dict] = None) -> str:
    """Record the question behind a slug. Answers are never cached, only the question."""
    slug = slug_for(question, parser)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO saved_queries (slug, question, parser, structured_query)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE
                   SET last_asked_at = now(),
                       times_asked = saved_queries.times_asked + 1,
                       structured_query = COALESCE(EXCLUDED.structured_query, saved_queries.structured_query)
                """,
                (slug, question.strip(), parser, psycopg.types.json.Jsonb(structured_query) if structured_query else None),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        # A link that could not be recorded must not fail the answer it belongs to.
        log_event(log, logging.WARNING, "slug_not_recorded", slug=slug, exc_info=True)
    return slug


def load_question(conn: psycopg.Connection, slug: str) -> Optional[SavedQuery]:
    with conn.cursor() as cur:
        cur.execute("SELECT slug, question, parser, structured_query, times_asked FROM saved_queries WHERE slug = %s",
                    (slug,))
        row = cur.fetchone()
    conn.commit()
    if not row:
        return None
    return SavedQuery(slug=row["slug"], question=row["question"], parser=row["parser"],
                      structured_query=row["structured_query"], times_asked=row["times_asked"])


# A filter, an order, or the whole shape of the question: what a reader of a
# shared link would want to be told has changed since it was made.
_PARSE_FIELDS = ("intent", "entity", "metric", "aggregation", "sort", "limit", "min_maps")


def describe_parse_change(before: Optional[dict], after: Optional[dict]) -> list[str]:
    """How today's reading of a shared question differs from the one saved with it.

    A shared link re-runs against current data by design, and the parser may have
    learned something in between. Answering a different question without saying so
    is the failure this prevents; the client should not have to diff two objects
    to find out.
    """
    if not before or not after or before == after:
        return []
    changes: list[str] = []
    for key in _PARSE_FIELDS:
        old, new = before.get(key), after.get(key)
        if old != new:
            changes.append(f"{key.replace('_', ' ')}: {old if old is not None else 'none'} "
                           f"-> {new if new is not None else 'none'}")
    old_filters = before.get("filters") or {}
    new_filters = after.get("filters") or {}
    for key in sorted(set(old_filters) | set(new_filters)):
        old, new = old_filters.get(key), new_filters.get(key)
        if old != new:
            changes.append(f"{key}: {old if old is not None else 'none'} -> {new if new is not None else 'none'}")
    return changes


# ---------------------------------------------------------------- suggestions

@dataclass
class Suggestion:
    question: str
    group: str
    slug: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"question": self.question, "group": self.group, "slug": self.slug or slug_for(self.question)}


@dataclass
class Suggestions:
    groups: list[str] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"groups": self.groups, "suggestions": self.suggestions}


# Questions that hold for any loaded data, so a suggestion list is never empty.
STATIC_SUGGESTIONS: tuple[tuple[str, str], ...] = (
    ("what stats are available", "Coverage"),
    ("which seasons have final blows", "Coverage"),
    ("what are the most played maps", "Maps and modes"),
)


def suggestions(conn: psycopg.Connection, per_group: int = 4) -> Suggestions:
    """Example questions built from entities that actually have data.

    A suggestion that returns `no_data` teaches the wrong thing about the
    warehouse, so every name here comes out of the aggregates.
    """
    out: list[Suggestion] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT player_display_name(p.display_name, p.nickname, p.game_player_name) AS nickname, sum(a.maps) AS maps
                  FROM agg_player_stats a JOIN players p ON p.player_id = a.player_id
                 GROUP BY p.display_name, p.nickname, p.game_player_name ORDER BY sum(a.maps) DESC LIMIT %s
                """,
                (per_group,),
            )
            players = [r["nickname"] for r in cur.fetchall()]
            cur.execute(
                """
                SELECT display_name, sum(matches) AS matches
                  FROM agg_team_matches WHERE display_name IS NOT NULL
                 GROUP BY display_name ORDER BY sum(matches) DESC LIMIT %s
                """,
                (per_group + 1,),
            )
            teams = [r["display_name"] for r in cur.fetchall()]
            cur.execute(
                """
                SELECT stat_key FROM stat_coverage_season
                 WHERE stat_kind = 'countable' GROUP BY stat_key
                 ORDER BY sum(rows_with_stat) DESC LIMIT %s
                """,
                (per_group,),
            )
            stats = [r["stat_key"] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT season FROM agg_player_stats WHERE season IS NOT NULL ORDER BY season DESC")
            seasons = [r["season"] for r in cur.fetchall()]
        conn.commit()
    except Exception:
        conn.rollback()
        log_event(log, logging.WARNING, "suggestions_failed", exc_info=True)
        players, teams, stats, seasons = [], [], [], []

    latest = seasons[0] if seasons else None
    for stat in stats[:per_group]:
        out.append(Suggestion(f"who had the most {stat.lower()}" + (f" in {latest}" if latest else ""), "Leaderboards"))
    for team in teams[:per_group]:
        out.append(Suggestion(f"{team} record", "Teams"))
    if len(teams) >= 2:
        out.append(Suggestion(f"{teams[0]} vs {teams[1]}", "Head to head"))
    if len(teams) >= 4:
        out.append(Suggestion(f"{teams[2]} vs {teams[3]}", "Head to head"))
    if len(players) >= 2:
        out.append(Suggestion(f"{players[0]} map record against {players[1]}", "Head to head"))
    for player in players[:per_group]:
        stat = stats[0] if stats else "eliminations"
        out.append(Suggestion(f"{player} {stat.lower()}", "Players"))
    if teams and len(seasons) >= 2:
        out.append(Suggestion(f"{seasons[-1]} {teams[0]} vs {seasons[0]} {teams[0]}", "Across seasons"))
    for question, group in STATIC_SUGGESTIONS:
        out.append(Suggestion(question, group))

    groups: list[str] = []
    for s in out:
        if s.group not in groups:
            groups.append(s.group)
    return Suggestions(groups=groups, suggestions=[s.as_dict() for s in out])
