"""One deterministic sentence per answer, built from templates and the returned rows.

No model writes this text. Every number in a sentence is read out of a row the
database returned, formatted and placed into a fixed template, so the same
question against the same data always produces the same words. If a template
needs a value the rows do not carry, it degrades to a shorter sentence rather
than inventing one.

Entity mentions are marked with character offsets (`Sentence.spans`) so a UI can
link a name to the entity it resolved to without re-parsing the text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Optional, Sequence

# What a span points at. `stat` and `season` are not entities in the warehouse
# but a UI still wants to link them to a filtered view.
SpanKind = str  # player | team | org | championship | stat | season | map | mode


@dataclass
class Span:
    start: int
    end: int
    kind: SpanKind
    text: str
    entity_id: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Sentence:
    text: str
    spans: list[Span] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "spans": [s.as_dict() for s in self.spans]}


class _Builder:
    """Accumulates text while recording where each entity mention landed."""

    def __init__(self) -> None:
        self.text = ""
        self.spans: list[Span] = []

    def add(self, text: str) -> "_Builder":
        self.text += text
        return self

    def mark(self, text: str, kind: SpanKind, entity_id: Optional[str] = None) -> "_Builder":
        start = len(self.text)
        self.text += text
        self.spans.append(Span(start=start, end=len(self.text), kind=kind, text=text, entity_id=entity_id))
        return self

    def done(self) -> Sentence:
        text = self.text.strip()
        if text and not text.endswith((".", "?", "!")):
            text += "."
        return Sentence(text=text, spans=self.spans)


# ------------------------------------------------------------------ formatting

def num(value: Any) -> str:
    """A number as a person would write it: thousands separated, no false precision."""
    if value is None:
        return "0"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int,)):
        return f"{value:,}"
    if isinstance(value, (float, Decimal)):
        d = Decimal(str(value))
        if d == d.to_integral_value():
            return f"{int(d):,}"
        return f"{float(round(d, 2)):,.2f}"
    return str(value)


def pct(value: Any) -> str:
    if value is None:
        return "0%"
    d = Decimal(str(value))
    return (f"{int(d)}%" if d == d.to_integral_value() else f"{float(round(d, 1))}%")


def _clean_seasons(seasons: Any) -> list[int]:
    if not seasons:
        return []
    if isinstance(seasons, (list, tuple)):
        return sorted({int(s) for s in seasons if s is not None})
    return [int(seasons)]


def seasons_phrase(seasons: Any, prefix_single: str = "in ", prefix_many: str = "across ") -> str:
    """'in 2025', 'across 2024-2026', 'across 2024 and 2026'. Empty when unknown."""
    ss = _clean_seasons(seasons)
    if not ss:
        return ""
    if len(ss) == 1:
        return f"{prefix_single}{ss[0]}"
    contiguous = ss == list(range(ss[0], ss[-1] + 1))
    if contiguous:
        return f"{prefix_many}{ss[0]}-{ss[-1]}"
    if len(ss) == 2:
        return f"{prefix_many}{ss[0]} and {ss[1]}"
    return f"{prefix_many}{', '.join(str(s) for s in ss[:-1])} and {ss[-1]}"


def _maps_phrase(row: dict[str, Any]) -> str:
    maps = row.get("maps") or row.get("maps_played") or row.get("maps_with_stat")
    matches = row.get("matches")
    if maps and matches:
        return f"{num(maps)} map{'' if maps == 1 else 's'} in {num(matches)} series"
    if maps:
        return f"{num(maps)} map{'' if maps == 1 else 's'}"
    if matches:
        return f"{num(matches)} series"
    return ""


def _role_entity(entities: dict[str, dict], *roles: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(display name, entity id, entity type) for the first role that resolved."""
    for role in roles:
        e = entities.get(role)
        if e:
            return e.get("current_name") or e.get("matched_name"), e.get("entity_id"), e.get("entity_type")
    return None, None, None


def _metric_label(metric: Optional[str]) -> str:
    return {
        "kd_ratio": "K/D ratio", "win_rate": "series win rate", "map_win_rate": "map win rate",
        "map_wins": "map wins", "map_losses": "map losses", "maps": "maps played",
        "matches": "series played", "wins": "series won", "losses": "series lost", "record": "record",
    }.get(metric or "", metric or "")


# -------------------------------------------------------------------- templates

def _versus(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    row = rows[0]
    subject, subject_id, subject_type = _role_entity(entities, "subject", "player", "team")
    opponent, opponent_id, opponent_type = _role_entity(entities, "opponent")
    subject = row.get("subject") or subject
    opponent = row.get("opponent") or opponent
    if not (subject and opponent):
        return None
    wins, losses, draws = row.get("map_wins"), row.get("map_losses"), row.get("draws") or 0
    if wins is None or losses is None:
        return None
    record = f"{num(wins)}-{num(losses)}" + (f"-{num(draws)}" if draws else "")
    b = _Builder()
    b.mark(str(subject), subject_type or "player", subject_id)
    b.add(f" is {record} in maps against ")
    b.mark(str(opponent), opponent_type or "player", opponent_id)
    seasons = seasons_phrase(row.get("seasons") or query.get("filters", {}).get("season"))
    if seasons:
        b.add(f" {seasons}")
    return b.done()


def _season_compare(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    if len(rows) < 2:
        return None
    a, z = rows[0], rows[-1]
    name, entity_id, entity_type = _role_entity(entities, "subject", "team", "player")
    name = a.get("entity") or name
    if not name:
        return None
    b = _Builder()
    b.mark(str(name), entity_type or "team", entity_id)
    b.add(" went ")
    b.add(f"{num(a.get('map_wins'))}-{num(a.get('map_losses'))} in maps in ")
    b.mark(str(a.get("season")), "season")
    b.add(" and ")
    b.add(f"{num(z.get('map_wins'))}-{num(z.get('map_losses'))} in ")
    b.mark(str(z.get("season")), "season")
    ap, zp = a.get("map_win_pct"), z.get("map_win_pct")
    if ap is not None and zp is not None:
        b.add(f" ({pct(ap)} to {pct(zp)})")
    return b.done()


def _head_to_head(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    row = rows[0]
    subject, subject_id, subject_type = _role_entity(entities, "team", "subject")
    opponent, opponent_id, opponent_type = _role_entity(entities, "opponent")
    subject, opponent = row.get("team") or subject, row.get("opponent") or opponent
    if not (subject and opponent) or row.get("wins") is None:
        return None
    b = _Builder()
    b.mark(str(subject), subject_type or "team", subject_id)
    b.add(f" is {num(row.get('wins'))}-{num(row.get('losses'))} in series against ")
    b.mark(str(opponent), opponent_type or "team", opponent_id)
    seasons = seasons_phrase(row.get("seasons") or query.get("filters", {}).get("season"))
    if seasons:
        b.add(f" {seasons}")
    if row.get("map_wins") is not None:
        b.add(f", {num(row.get('map_wins'))}-{num(row.get('map_losses'))} in maps")
    return b.done()


def _team_record(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    row = rows[0]
    name, entity_id, entity_type = _role_entity(entities, "subject", "team")
    name = row.get("team") or name
    if not name:
        return None
    b = _Builder()
    b.mark(str(name), entity_type or "team", entity_id)
    if row.get("wins") is not None and row.get("losses") is not None:
        b.add(f" is {num(row['wins'])}-{num(row['losses'])} in series")
        if row.get("map_wins") is not None:
            b.add(f" and {num(row['map_wins'])}-{num(row['map_losses'])} in maps")
    elif row.get("map_wins") is not None:
        b.add(f" is {num(row['map_wins'])}-{num(row['map_losses'])} in maps")
    else:
        return None
    seasons = seasons_phrase(row.get("seasons") or query.get("filters", {}).get("season"))
    if seasons:
        b.add(f" {seasons}")
    win_pct = row.get("win_pct") if row.get("win_pct") is not None else row.get("map_win_pct")
    if win_pct is not None:
        b.add(f", a {pct(win_pct)} win rate")
    return b.done()


def _entity_stat(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    row = rows[0]
    metric = query.get("metric")
    name, entity_id, entity_type = _role_entity(entities, "subject", "player", "team")
    name = row.get("nickname") or row.get("team") or name
    if not name:
        return None
    b = _Builder()
    b.mark(str(name), entity_type or "player", entity_id)

    if metric == "kd_ratio" and row.get("kd_ratio") is not None:
        b.add(" has a ")
        b.mark("K/D ratio", "stat", "kd_ratio")
        b.add(f" of {num(row['kd_ratio'])}")
        b.add(f" from {num(row.get('eliminations'))} eliminations and {num(row.get('deaths'))} deaths"
              if row.get("eliminations") is not None else "")
    elif metric in ("maps", "matches", "map_wins", "map_losses", "map_win_rate", "wins", "losses"):
        if row.get("map_wins") is None:
            return None
        b.add(f" is {num(row['map_wins'])}-{num(row['map_losses'])} in maps")
        if row.get("map_win_pct") is not None:
            b.add(f", a {pct(row['map_win_pct'])} map win rate")
    else:
        total, avg = row.get("total"), row.get("avg_per_map")
        if query.get("aggregation") == "avg_per_map" and avg is not None:
            b.add(" averages ")
            b.add(f"{num(avg)} ")
            b.mark(str(metric), "stat", str(metric))
            b.add(" per map")
        elif total is not None:
            b.add(f" has {num(total)} ")
            b.mark(str(metric), "stat", str(metric))
        else:
            return None
    phrase = _maps_phrase(row)
    if phrase:
        b.add(f" across {phrase}")
    seasons = seasons_phrase(row.get("seasons") or query.get("filters", {}).get("season"))
    if seasons:
        b.add(f" {seasons}")
    return b.done()


# The column that holds a metric's own value. A leaderboard row carries several numbers (a K/D row also has map_win_pct,
# a series-won row also has win_pct), so the sentence must name the metric's column, never the first one present: taking
# the first printed Attack's 77.80 map win % as his K/D (5.00).
METRIC_COLUMN = {"kd_ratio": "kd_ratio", "map_win_rate": "map_win_pct", "win_rate": "win_pct", "maps": "maps",
                 "matches": "matches", "map_wins": "map_wins", "map_losses": "map_losses"}


def value_column(query: dict, row: dict) -> Optional[str]:
    metric = query.get("metric")
    if metric in METRIC_COLUMN:
        return METRIC_COLUMN[metric]
    if metric in ("wins", "losses"):                    # series won / lost for a team; maps won / lost for a player
        return metric if metric in row else ("map_wins" if metric == "wins" else "map_losses")
    return "avg_per_map" if query.get("aggregation") == "avg_per_map" else "total"


def _leaderboard(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    row = rows[0]
    metric = query.get("metric")
    name = row.get("nickname") or row.get("team") or row.get("display_name")
    entity_id = row.get("player_id") or row.get("org_key")
    entity_type = "player" if row.get("player_id") else "org"
    if not name:
        return None
    b = _Builder()
    b.mark(str(name), entity_type, entity_id)
    ascending = query.get("sort") == "asc"
    # the verb is chosen before any span is marked: rewriting " leads " afterwards shifted every later span by 9 characters,
    # so the stat link landed on "e lowe" inside "the lowest"
    b.add(" has the lowest " if ascending else " leads ")
    b.mark(_metric_label(metric) or str(metric), "stat", str(metric))
    key = value_column(query, row)
    value = row.get(key) if key else None
    if value is None:
        return None
    is_rate = query.get("aggregation") == "avg_per_map" or metric in ("win_rate", "map_win_rate")
    if metric in ("win_rate", "map_win_rate"):
        b.add(f" at {pct(value)}")
    elif is_rate:
        b.add(f" at {num(value)} per map")
    else:
        b.add(f" with {num(value)}")
    phrase = _maps_phrase(row)
    if phrase:
        b.add(f" across {phrase}")
    seasons = seasons_phrase(row.get("seasons") or query.get("filters", {}).get("season"))
    if seasons:
        b.add(f" {seasons}")
    if len(rows) > 1:
        b.add(f", out of {len(rows)} shown" if ascending else
              f", ahead of {len(rows) - 1} other{'' if len(rows) == 2 else 's'} shown")
    floor = query.get("min_maps_floor")
    if floor:
        # say why a player is missing: the floor left out everyone under it
        b.add(f" (players with at least {floor} maps)")
    return b.done()


def _map_stats(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    row = rows[0]
    what = "map" if query.get("entity") == "map" else "mode"
    label = row.get("map_name") or row.get("game_mode")
    if not label:
        return None
    name, entity_id, entity_type = _role_entity(entities, "subject", "team", "player")
    b = _Builder()
    if name:
        b.mark(str(name), entity_type or "team", entity_id)
        if row.get("wins") is not None and row.get("losses") is not None:
            b.add(" wins most on ")
            b.mark(str(label), what, str(label))
            b.add(f": {num(row['wins'])}-{num(row['losses'])} in maps")
            if row.get("win_pct") is not None:
                b.add(f" ({pct(row['win_pct'])})")
        else:
            b.add(" plays ")
            b.mark(str(label), what, str(label))
            b.add(f" most, {num(row.get('maps'))} times")
    else:
        b.add(f"The most played {what} is ")
        b.mark(str(label), what, str(label))
        b.add(f", {num(row.get('maps'))} maps in {num(row.get('matches'))} series"
              if row.get("matches") else f", {num(row.get('maps'))} maps")
    seasons = seasons_phrase(query.get("filters", {}).get("season"))
    if seasons:
        b.add(f" {seasons}")
    return b.done()


def _stat_availability(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    metric = query.get("metric")
    by_season: dict[int, list[str]] = {}
    for r in rows:
        by_season.setdefault(r.get("season"), []).append(r.get("stat_key"))
    b = _Builder()
    if metric:
        seasons = sorted(s for s in by_season if s is not None)
        if not seasons:
            b.mark(str(metric), "stat", str(metric))
            b.add(" is not recorded in any season in scope")
            return b.done()
        b.mark(str(metric), "stat", str(metric))
        b.add(f" is recorded {seasons_phrase(seasons)}")
        return b.done()
    parts = [f"{len(keys)} in {season}" for season, keys in sorted(by_season.items(), key=lambda kv: (kv[0] is None, kv[0]))
             if season is not None]
    if not parts:
        return None
    b.add("Stat keys available: " + ", ".join(parts))
    return b.done()


def _day(value: Any) -> str:
    return str(value)[:10] if value else "an unknown date"


def _team_membership(rows: list[dict], entities: dict[str, dict], query: dict) -> Optional[Sentence]:
    """'X last played for T on <date>, having previously played for A (from to) and B (from to).'"""
    player, player_id, _ = _role_entity(entities, "subject", "player")
    if not player or not rows:
        return None
    now = rows[0]
    kind = "org" if now.get("org_id") else "team"
    b = _Builder()
    b.mark(str(player), "player", player_id)
    b.add(" last played for ")
    b.mark(str(now["team"]), kind, now.get("org_id") or now.get("team_id"))
    b.add(f" on {_day(now.get('to_at'))}")
    earlier = rows[1:]
    if earlier:
        b.add(", having previously played for ")
        for i, row in enumerate(earlier[:4]):
            if i:
                b.add(", and " if i == len(earlier[:4]) - 1 and len(earlier) <= 4 else ", ")
            b.mark(str(row["team"]), "org" if row.get("org_id") else "team", row.get("org_id") or row.get("team_id"))
            b.add(f" ({_day(row.get('from_at'))} to {_day(row.get('to_at'))})")
        if len(earlier) > 4:
            b.add(f" and {len(earlier) - 4} more")
    return b.done()


_TEMPLATES = {
    "team_membership": _team_membership,
    "versus": _versus,
    "season_compare": _season_compare,
    "head_to_head": _head_to_head,
    "team_record": _team_record,
    "entity_stat": _entity_stat,
    "leaderboard": _leaderboard,
    "map_stats": _map_stats,
    "stat_availability": _stat_availability,
}


def render_sentence(query: dict, rows: Sequence[dict], entities: Optional[dict[str, dict]] = None,
                    description: Optional[str] = None) -> Optional[Sentence]:
    """The one-sentence claim for an answer, or None when no template fits its rows."""
    if not rows:
        return None
    template = _TEMPLATES.get(query.get("intent") or "")
    if not template:
        return None
    try:
        return template(list(rows), entities or {}, query or {})
    except (KeyError, TypeError, ValueError, ArithmeticError):
        # A template must never be the reason an answer fails. Falling back to no
        # sentence keeps the aggregate and the evidence rows intact.
        return None


def render_unanswerable(reason: str, entities: Optional[dict[str, dict]] = None) -> Sentence:
    """A refusal is a sentence too, with its entities marked where they resolved."""
    b = _Builder()
    b.add(reason)
    text = b.text
    for e in (entities or {}).values():
        name = e.get("current_name")
        if not name:
            continue
        at = text.find(name)
        if at >= 0:
            b.spans.append(Span(start=at, end=at + len(name), kind=e.get("entity_type") or "player",
                                text=name, entity_id=e.get("entity_id")))
    return b.done()
