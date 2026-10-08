"""Deterministic rule-based question parser.

Turns a question into a StructuredQuery (or an Unanswerable) without any
model call, so the test suite runs offline. The optional Claude parser in
llm_parser.py produces the same object; both go through the same validator
and compiler afterwards.

The parser is deliberately conservative: when it cannot tell what is being
asked it returns `unsupported_question` with a hint rather than guessing.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Union

from ..resolve import fold
from .schema import DERIVED_METRICS, Filters, StructuredQuery, Unanswerable


def _ascii(text: str) -> str:
    """Lower-case and strip accents but keep apostrophes and punctuation (unlike fold)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()

ParseResult = Union[StructuredQuery, Unanswerable]

# --------------------------------------------------------------- vocabularies

# phrase -> canonical metric. Longest phrases first so "final blows" beats "blows".
METRIC_SYNONYMS: list[tuple[str, str]] = sorted(
    [
        ("final blows", "Final Blows"), ("final blow", "Final Blows"), ("fbs", "Final Blows"),
        ("eliminations", "Eliminations"), ("elimination", "Eliminations"), ("elims", "Eliminations"),
        ("kills", "Eliminations"), ("frags", "Eliminations"),
        ("deaths", "Deaths"), ("death", "Deaths"), ("died", "Deaths"),
        ("assists", "Assists"), ("assist", "Assists"),
        ("damage dealt", "Damage Dealt"), ("damage done", "Damage Dealt"), ("damage", "Damage Dealt"), ("dmg", "Damage Dealt"),
        ("healing done", "Healing Done"), ("healing", "Healing Done"), ("heals", "Healing Done"), ("healed", "Healing Done"),
        ("damage mitigated", "Damage Mitigated"), ("mitigation", "Damage Mitigated"), ("mitigated", "Damage Mitigated"),
        ("damage blocked", "Damage Mitigated"), ("blocked", "Damage Mitigated"),
        ("solo kills", "Solo Kills"), ("solo kill", "Solo Kills"),
        ("multi kills", "Multi Kills"), ("multikills", "Multi Kills"), ("multi kill", "Multi Kills"),
        ("environmental kills", "Environmental Kills"), ("env kills", "Environmental Kills"), ("environmentals", "Environmental Kills"),
        ("objective time", "Objective Time"), ("obj time", "Objective Time"), ("time on objective", "Objective Time"),
        ("time played", "Time Played"), ("playtime", "Time Played"),
        ("kill death ratio", "kd_ratio"), ("kd ratio", "kd_ratio"), ("kd", "kd_ratio"),
        ("map win rate", "map_win_rate"), ("map winrate", "map_win_rate"),
        ("map record", "map_win_rate"), ("maps record", "map_win_rate"),
        ("series record", "record"), ("match record", "record"), ("series win rate", "win_rate"),
        ("win rate", "win_rate"), ("winrate", "win_rate"), ("win percentage", "win_rate"), ("win pct", "win_rate"),
        ("map wins", "map_wins"), ("maps won", "map_wins"), ("map losses", "map_losses"), ("maps lost", "map_losses"),
        ("how many maps", "maps"), ("maps played", "maps"), ("how many matches", "matches"), ("how many series", "matches"),
        ("how many games", "matches"), ("matches played", "matches"), ("series played", "matches"), ("games played", "matches"),
        ("record", "record"), ("wins", "wins"), ("won", "wins"), ("losses", "losses"), ("lost", "losses"),
    ],
    key=lambda kv: -len(kv[0]),
)

# Things people ask about that the warehouse does not have. Each maps to a reason.
UNSUPPORTED_METRIC_TERMS: list[tuple[str, str]] = [
    ("hero", "hero picks are not in the FACEIT payloads"),
    ("heroes", "hero picks are not in the FACEIT payloads"),
    ("ultimate", "ultimate usage is not in the FACEIT payloads"),
    ("ults", "ultimate usage is not in the FACEIT payloads"),
    ("accuracy", "accuracy is not in the FACEIT payloads"),
    ("headshot", "headshot stats are not in the FACEIT payloads"),
    ("critical hits", "critical hit stats are not in the FACEIT payloads"),
    ("salary", "salaries are not tracked"),
    ("earnings", "prize money is not tracked"),
    ("prize", "prize money is not tracked"),
    ("mvp", "MVP awards are not tracked"),
    ("rating", "there is no rating metric; ask for a specific stat"),
    ("clutch", "clutches are not in the FACEIT payloads"),
    ("first blood", "first bloods are not in the FACEIT payloads"),
    ("mmr", "MMR is not tracked"),
]

OUT_OF_SCOPE_TERMS: list[tuple[str, str]] = [
    ("asia", "Asia is outside the NA + EMEA scope"),
    ("japan", "Japan is outside the NA + EMEA scope"),
    ("china", "China is outside the NA + EMEA scope"),
    ("pacific", "Pacific is outside the NA + EMEA scope"),
    ("owl", "the Overwatch League is not on FACEIT and outside scope"),
    ("overwatch league", "the Overwatch League is not on FACEIT and outside scope"),
    ("contenders", "Contenders is outside scope"),
    ("open qualifier", "open qualifiers are excluded from the warehouse scope"),
    ("qualifier", "qualifiers are excluded from the warehouse scope"),
    ("relegation", "relegation matches are excluded from the warehouse scope"),
    ("ranked", "ranked / competitive ladder play is outside scope"),
    ("hub", "FACEIT hubs are outside scope"),
    ("elo", "FACEIT ELO is outside scope"),
    ("faceit level", "FACEIT levels are outside scope"),
    ("next match", "the warehouse holds finished matches only, not schedules"),
    ("upcoming", "the warehouse holds finished matches only, not schedules"),
    ("schedule", "the warehouse holds finished matches only, not schedules"),
    ("tomorrow", "the warehouse holds finished matches only, not schedules"),
    ("predict", "no predictions, only recorded results"),
    ("prediction", "no predictions, only recorded results"),
    ("who will win", "no predictions, only recorded results"),
    ("odds", "no predictions, only recorded results"),
]

MODES = {"control": "Control", "hybrid": "Hybrid", "escort": "Escort", "push": "Push", "flashpoint": "Flashpoint", "clash": "Clash"}

# match_players.role, FACEIT's own three values. Only unambiguous shorthand is
# matched: "damage" and "healing" are metric words (Damage Dealt, Healing Done)
# and must not be stolen for role, so Damage/Support are recognised only by
# their unambiguous role-specific shorthand.
ROLES = {"tank": "Tank", "dps": "Damage", "support": "Support", "healer": "Support"}

# Current OW2 competitive map pool plus retired maps that appear in 2024 data.
MAPS = [
    "Lijiang Tower", "Ilios", "Nepal", "Oasis", "Busan", "Antarctic Peninsula", "Samoa",
    "King's Row", "Blizzard World", "Numbani", "Hollywood", "Eichenwalde", "Midtown", "Paraíso",
    "Dorado", "Junkertown", "Rialto", "Route 66", "Havana", "Watchpoint: Gibraltar", "Circuit Royal", "Shambali Monastery",
    "Colosseo", "Esperança", "New Queen Street", "Runasapi", "New Junk City", "Suravasa", "Aatlis", "Hanaoka", "Throne of Anubis",
]
_MAP_BY_FOLD = {fold(m): m for m in MAPS}
_MAP_BY_ASCII = {_ascii(m): m for m in MAPS}
_MAP_ALIASES = {"lijiang": "Lijiang Tower", "kings row": "King's Row", "gibraltar": "Watchpoint: Gibraltar", "watchpoint": "Watchpoint: Gibraltar",
                "bliz world": "Blizzard World", "route66": "Route 66", "shambali": "Shambali Monastery", "antarctic": "Antarctic Peninsula"}

REGION_TERMS = {"north america": "na", "na": "na", "emea": "emea", "europe": "emea", "european": "emea", "eu": "emea",
                "international": "international", "korea": "korea", "korean": "korea", "south korea": "korea"}

CHAMPIONSHIP_TERMS = [
    "stage 1", "stage 2", "stage 3", "stage 4", "stage one", "stage two", "main event", "group stage", "group a", "group b",
    "group c", "group d", "playoffs", "playoff", "regular season", "relegation", "dreamhack dallas", "dreamhack",
    "midseason championship", "midseason", "world finals", "champions clash", "major",
]

VERSUS_CUES = ["map record against", "record against", "against", " vs ", " vs. ", "versus", "head to head", "h2h",
               "matchup", "when they played", "when they met"]
MAP_RECORD_CUES = ["map record", "map wins", "map win rate", "maps against", "record against", "head to head", "h2h", "vs", "versus", "against"]
# What actually asks for the series-grain record ("Twisted Minds series record
# against ENCE"), as opposed to a bare "record"/"wins"/"win rate" alongside
# "vs" - both collapse to the same METRIC_SYNONYMS entry (e.g. "series record"
# and "record" both become metric "record"), so the distinction has to be read
# from the raw text, not from the metric already extracted from it. "matches"
# has no map-grain reading at all ("how many matches" can only mean series),
# so it is series-grain on its own without needing one of these phrases too.
SERIES_GRAIN_CUES = ["series record", "match record", "series win rate", "series wins", "match wins",
                     "series loss", "match loss", "series matchup", "match history"]

LEADERBOARD_CUES = ["most", "top", "highest", "best", "leader", "leaderboard", "who has", "who had", "who have", "who got",
                    "rank", "ranking", "lowest", "fewest", "least", "worst", "which player", "which team", "who leads", "who led",
                    "who is leading", "bottom"]
ASC_CUES = ["lowest", "fewest", "least", "worst", "bottom"]
AVG_CUES = ["average", "avg", "per map", "mean", "on average"]
PLAYER_CUES = ["player"]
AVAIL_CUES = ["what stats", "which stats", "what stat", "what data", "what metrics", "available", "coverage", "do you have", "do you track",
              "can you tell me about", "what can you", "what do you know", "stats exist", "which seasons", "what seasons"]
MAP_ENTITY_CUES = ["which map", "what map", "best map", "worst map", "most played map", "maps does", "maps did", "on which map",
                   "per map breakdown", "map breakdown", "by map", "map pool", "map for", "maps for", "favorite map", "favourite map"]
MODE_ENTITY_CUES = ["which mode", "what mode", "best mode", "worst mode", "by mode", "game mode", "per mode", "mode for"]

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "fifteen": 15, "twenty": 20, "fifty": 50}

_LEAD_STOP = {"what", "was", "is", "did", "does", "do", "has", "have", "had", "the", "how", "show", "me", "of", "for", "by", "and",
              "many", "much", "are", "were", "who", "which", "a", "an", "team", "player", "give", "tell", "about", "with", "to",
              "whats", "in", "on", "at", "from", "as", "playing"}
_TRAIL_STOP = {"do", "did", "does", "have", "has", "play", "played", "go", "went", "fare", "fared", "perform", "performed", "record",
               "standings", "results", "result", "stats", "stat", "numbers", "team", "player", "in", "on", "at", "for", "the", "of",
               "as", "playing"}
_BAD_NAME_WORDS = {"most", "top", "highest", "best", "lowest", "fewest", "least", "worst", "map", "maps", "mode", "modes",
                   "average", "total", "who", "which", "what", "there", "it", "they", "he", "she", "anyone", "someone", "everyone",
                   "season", "overall", "leaderboard", "ranking", "rank", "many", "much", "tank", "tanks", "dps", "support",
                   "supports", "healer", "healers"}


ENTITY_TOKEN = re.compile(
    r"^(?:(?:player|team|org):)?"
    r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-z0-9][a-z0-9-]*)$", re.I)


def is_entity_token(text: Optional[str]) -> bool:
    """A prefixed id (`org:team-peps`) names exactly one entity, so it is a name."""
    t = (text or "").strip()
    return bool(t) and ":" in t and bool(ENTITY_TOKEN.match(t))


def _clean_name(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    if is_entity_token(s):
        return s.strip()      # never stop-worded, stripped or metric-matched
    s = re.sub(r"\s+", " ", s).strip(" ?.,!'\"")
    s = re.sub(r"'s$", "", s)
    for phrase, _ in METRIC_SYNONYMS:
        s = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", s)
    words = [w for w in s.split() if w]
    while words and words[0] in _LEAD_STOP:
        words.pop(0)
    while words and words[-1] in _TRAIL_STOP:
        words.pop()
    if not words or len(words) > 5 or any(w in _BAD_NAME_WORDS for w in words):
        return None
    name = " ".join(words).strip(" ?.,!'\"")
    return name or None


# ------------------------------------------------------------------ extraction

def _normalize(q: str) -> str:
    q = _ascii(q.strip()).replace("’", "'")
    q = q.replace("k/d", "kd").replace("k / d", "kd")
    q = re.sub(r"[?!.]+$", "", q)
    return re.sub(r"\s+", " ", q).strip()


def _has(q: str, cues: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(c) + r"(?:s|es)?\b", q) for c in cues)


def _find_metric(q: str) -> tuple[Optional[str], str]:
    """Return (metric, question with the metric phrase removed)."""
    per10 = bool(re.search(r"per (10|ten) ?(min|mins|minutes)|/10m|per 10m", q))
    for phrase, metric in METRIC_SYNONYMS:
        m = re.search(r"\b" + re.escape(phrase) + r"\b", q)
        if m:
            if metric == "matches" and re.search(r"\b(win|won)\b", q):
                metric = "wins"
            elif metric == "matches" and re.search(r"\b(lose|lost)\b", q):
                metric = "losses"
            if per10 and metric not in DERIVED_METRICS:
                metric = metric + "/10m"
            rest = re.sub(r"per (10|ten) ?(min|mins|minutes)|/10m|per 10m", " ", q[: m.start()] + " " + q[m.end():])
            return metric, re.sub(r"\s+", " ", rest).strip()
    return None, q


def _find_season(q: str) -> Optional[int]:
    m = re.search(r"\b(20[2-3]\d)\b", q)
    return int(m.group(1)) if m else None


def _find_mode(q: str) -> Optional[str]:
    for k, v in MODES.items():
        if re.search(r"\b" + k + r"\b", q):
            return v
    return None


def _find_role(q: str) -> Optional[str]:
    for k, v in ROLES.items():
        if re.search(r"\b" + k + r"s?\b", q):
            return v
    return None


def _find_map(q: str) -> Optional[str]:
    fq = fold(q)
    for fm, name in sorted(_MAP_BY_FOLD.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(fm) + r"\b", fq):
            return name
    for alias, name in _MAP_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", fq):
            return name
    return None


def _find_region(q: str) -> Optional[str]:
    for term, region in sorted(REGION_TERMS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(term) + r"\b", q):
            return region
    return None


def _find_championship(q: str) -> Optional[str]:
    """Every competition term in the question, together: "stage 2 playoffs" is one competition, not two filters.

    Keeping only the longest term turned "OWCS 2026 NA Stage 2 Playoffs" into "playoffs", which matches both
    stages' playoffs and answers for the wrong set without saying so. A term inside a longer one found is dropped
    ("dreamhack" within "dreamhack dallas").
    """
    found: list[tuple[int, str]] = []
    for term in sorted(CHAMPIONSHIP_TERMS, key=len, reverse=True):
        m = re.search(r"\b" + re.escape(term) + r"\b", q)
        if m and not any(term in kept for _, kept in found):
            found.append((m.start(), term))
    return " ".join(term for _, term in sorted(found)) or None


def _find_limit(q: str) -> Optional[int]:
    m = re.search(r"\b(?:top|best|first|bottom|worst)\s+(\d{1,3})\b", q)
    if m:
        return max(1, min(100, int(m.group(1))))
    m = re.search(r"\b(?:top|best|first|bottom|worst)\s+(" + "|".join(_NUM_WORDS) + r")\b", q)
    if m:
        return _NUM_WORDS[m.group(1)]
    return None


def _find_min_maps(q: str) -> Optional[int]:
    m = re.search(r"\b(?:at least|min(?:imum)?)\s+(\d{1,4})\s+maps?\b", q)
    return int(m.group(1)) if m else None


def _strip_filters(q: str, keep_years: bool = False) -> str:
    """Remove filter phrases so they are not captured as entity names.

    `keep_years` leaves years alone for versus parsing, where "2024 X vs 2026 X"
    binds a year to each side rather than to the whole question.
    """
    if not keep_years:
        q = re.sub(r"\b(in|during|for|of|from|the)\s+(the\s+)?20[2-3]\d(\s+season)?\b", " ", q)
        q = re.sub(r"\b20[2-3]\d\b", " ", q)
    q = re.sub(r"\b(on|in|at)\s+(control|hybrid|escort|push|flashpoint|clash)(\s+maps?)?\b", " ", q)
    q = re.sub(r"\b(control|hybrid|escort|push|flashpoint|clash)(\s+maps?)?\b", " ", q)
    q = re.sub(r"\b(?:as (?:a |an )?|playing )(tank|dps|support|healer)s?\b", " ", q)
    q = re.sub(r"\b(tank|dps|support|healer)s?\b", " ", q)
    for term in sorted(CHAMPIONSHIP_TERMS, key=len, reverse=True):
        q = re.sub(r"\b(in|at|during|of)?\s*(the\s+)?" + re.escape(term) + r"\b", " ", q)
    for am in sorted(_MAP_BY_ASCII, key=len, reverse=True):
        q = re.sub(r"\b(on|at)?\s*" + re.escape(am) + r"(?![a-z0-9])", " ", q)
    for alias in _MAP_ALIASES:
        q = re.sub(r"\b(on|at)?\s*" + re.escape(alias) + r"\b", " ", q)
    q = re.sub(r"\bowcs\b", " ", q)   # the brand word in "OWCS 2026 NA Stage 2" names no one
    q = re.sub(r"\b(in|for)\s+(na|emea|eu|europe|north america|international|korea|south korea)\b", " ", q)
    q = re.sub(r"\bkorean\b", " ", q)
    q = re.sub(r"\b(at least|min(?:imum)?)\s+\d{1,4}\s+maps?\b", " ", q)
    q = re.sub(r"\bthis season\b|\blast season\b|\ball time\b|\boverall\b|\bso far\b|\bever\b|\bper map\b|\bon average\b", " ", q)
    return re.sub(r"\s+", " ", q).strip()


_H2H = [
    re.compile(r"^(?:how (?:did|does|do|has|have)\s+)?(?P<a>.+?)\s+(?:vs\.?|versus|against|v)\s+(?P<b>.+?)(?:\s+(?:record|head to head|h2h|results?|matchup))?$"),
    re.compile(r"^(?:head to head|h2h|record|matchup)\s+(?:between|for|of)\s+(?P<a>.+?)\s+and\s+(?P<b>.+)$"),
    re.compile(r"^(?:.*\bbetween\s+)(?P<a>.+?)\s+and\s+(?P<b>.+)$"),
    re.compile(r"^(?P<a>.+?)\s+(?:head to head|h2h|matchup)\s+(?:with\s+|against\s+|vs\.?\s+)?(?P<b>.+)$"),
]

_NAME = r"[a-z0-9_.:\-' ]+?"
_SUBJECT_PATTERNS = [
    re.compile(r"\b(?:did|does|do|has|have|had|is|was|are|were)\s+(?P<n>" + _NAME + r")\s+(?:have|get|got|score|scored|record|recorded|play|played|average|averaged|win|won|lose|lost|deal|dealt|heal|healed|do|done|die|died|post|posted|put up|finish|finished|go|gone|fare|perform)\b"),
    re.compile(r"(?:^|\s)(?P<n>(?:[a-z0-9_.\-']+\s+)?[a-z0-9_.\-']+)'s\b"),
    re.compile(r"\b(?:for|by|of|from)\s+(?P<n>[a-z0-9_.:\-' ]+)$"),
    re.compile(r"^(?:show|show me|give me|get|what is|what's|what are|whats|tell me|tell me about)\s+(?P<n>" + _NAME + r")(?:\s+(?:stats?|numbers?|totals?|averages?))?$"),
    re.compile(r"^(?P<n>" + _NAME + r")\s+(?:stats?|numbers?|totals?|averages?)$"),
    re.compile(r"^(?P<n>[a-z0-9_.:\-' ]{2,72})$"),   # a bare name, or an entity id
]


# "what team is X on", "who does X play for", "X's team": a player's team now, and the teams before it.
_MEMBERSHIP = [
    re.compile(r"^(?:what|which)\s+(?:team|org|organi[sz]ation)\s+(?:is|was|does|did)\s+(?P<n>.+?)\s+(?:currently\s+|now\s+)?(?:on|play(?:s|ed)?\s+(?:for|on|with)|belong(?:s)?\s+to)(?:\s+(?:now|currently))?$"),
    re.compile(r"^(?:what|which)\s+(?:team|org)\s+(?:is|was)\s+(?P<n>.+?)\s+(?:currently\s+)?(?:signed\s+(?:to|with)|with)$"),
    re.compile(r"^who\s+(?:does|did|is|was)\s+(?P<n>.+?)\s+(?:currently\s+|now\s+)?(?:play(?:s|ed|ing)?\s+(?:for|on|with)|on|signed\s+(?:to|with)|with)(?:\s+(?:now|currently))?$"),
    re.compile(r"^(?P<n>[a-z0-9_.\-' ]+?)'s\s+(?:current\s+|previous\s+|former\s+|past\s+)?(?:team|teams|roster|org|team history)$"),
    re.compile(r"^(?P<n>[a-z0-9_.\-' ]+?)\s+(?:team history|teams|previous teams|former teams|team)$"),
    re.compile(r"^(?:team history|teams|previous teams|former teams|current team)\s+(?:of|for)\s+(?P<n>.+)$"),
]


def _find_membership_subject(q: str) -> Optional[str]:
    for rx in _MEMBERSHIP:
        m = rx.match(q)
        if m:
            name = _clean_name(m.group("n"))
            if name:
                return name
    return None


_SIDE_SEASON = re.compile(r"^\s*(?P<y>20[2-3]\d)\s+(?P<rest>.+)$|^(?P<rest2>.+?)\s+(?:in\s+)?(?P<y2>20[2-3]\d)\s*$")


def _side_season(text: str) -> tuple[Optional[int], str]:
    """Split a leading or trailing year off one side of a versus question."""
    m = _SIDE_SEASON.match((text or "").strip())
    if not m:
        return None, text
    if m.group("y"):
        return int(m.group("y")), m.group("rest")
    return int(m.group("y2")), m.group("rest2")


def _find_subject(q: str) -> Optional[str]:
    for rx in _SUBJECT_PATTERNS:
        m = rx.search(q)
        if m:
            name = _clean_name(m.group("n"))
            if name:
                return name
    return None


# --------------------------------------------------------------------- parse

def parse_question(question: str) -> ParseResult:
    if not question or not question.strip():
        return Unanswerable(code="invalid_query", reason="empty question")
    q = _normalize(question)

    # --- hard stops first: things we know we cannot answer
    for term, why in OUT_OF_SCOPE_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", q):
            return Unanswerable(code="out_of_scope", reason=why,
                                suggestions=["Scope is OWCS NA + EMEA main competition on FACEIT: regional stages, playoffs and international events."])
    for term, why in UNSUPPORTED_METRIC_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", q):
            return Unanswerable(code="unsupported_metric", reason=why,
                                suggestions=["Ask `what stats are available` to see the tracked stat keys."])

    filters = Filters(
        season=_find_season(q), mode=_find_mode(q), map=_find_map(q), region=_find_region(q), championship=_find_championship(q),
        role=_find_role(q),
    )
    metric, q_wo_metric = _find_metric(q)
    limit = _find_limit(q)
    min_maps = _find_min_maps(q)
    sort = "asc" if _has(q, ASC_CUES) else "desc"
    aggregation = "avg_per_map" if _has(q, AVG_CUES) else "total"

    # --- which team is a player on, and which have they been on
    team_subject = _find_membership_subject(_strip_filters(q))
    if team_subject:
        return StructuredQuery(intent="team_membership", entity="player", metric="team",
                               filters=Filters(subject=team_subject, season=filters.season))

    # --- stat availability
    if _has(q, AVAIL_CUES) and not _has(q, ["who", "most", "top"]):
        return StructuredQuery(intent="stat_availability", entity="player",
                               metric=metric if metric and metric not in DERIVED_METRICS else None,
                               filters=Filters(season=filters.season))

    body = _strip_filters(q_wo_metric if metric else q)
    versus_body = _strip_filters(q_wo_metric if metric else q, keep_years=True)
    q_cue = re.sub(r"\bper map\b|\bon average\b", " ", q_wo_metric if metric else q)

    # --- versus / head to head / season comparison
    for rx in _H2H:
        m = rx.match(versus_body)
        if m:
            left_raw, right_raw = m.group("a"), m.group("b")
            a_season, a = _side_season(left_raw)
            b_season, b = _side_season(right_raw)
            a, b = _clean_name(a), _clean_name(b)
            if a and b:
                # A year binds to one side only when BOTH sides carry one
                # ("2024 X vs 2026 X"). A single trailing year in "X vs Y in 2025"
                # scopes the whole matchup instead.
                if a_season and b_season:
                    global_season = None  # each side carries its own
                else:
                    global_season = filters.season or a_season or b_season
                    a_season = b_season = None
                f = filters.model_copy(update={"subject": a, "opponent": b, "season": global_season,
                                               "subject_season": a_season, "opponent_season": b_season})
                # the same entity named on both sides with different seasons is a
                # comparison of an org against its later self, not a fixture
                if fold(a) == fold(b) and (a_season or b_season) and a_season != b_season:
                    return StructuredQuery(intent="season_compare", entity="team", metric=metric or "map_win_rate",
                                           filters=f, aggregation=aggregation)
                # "series record against X" is the series-grain question; everything
                # else at this shape is a map record. "series record" and a bare
                # "record" both collapse to the same metric via METRIC_SYNONYMS, so
                # the distinction has to come from the raw text (SERIES_GRAIN_CUES),
                # not from `metric` - relying on `metric` alone made every "X record
                # vs Y" series-grain, which only ever resolves for two teams, so
                # "zeruhh record vs sugarfree" (both players) failed outright.
                if metric == "matches" or _has(q, SERIES_GRAIN_CUES):
                    return StructuredQuery(intent="head_to_head", entity="team", metric="record",
                                           filters=f.model_copy(update={"team": a, "opponent": b, "subject": None}))
                return StructuredQuery(intent="versus", entity="player" if _has(q, PLAYER_CUES) else "team",
                                       metric=metric or "map_win_rate", filters=f, aggregation=aggregation)

    # --- map / mode as the row entity
    if _has(q_cue, MAP_ENTITY_CUES) or _has(q_cue, MODE_ENTITY_CUES):
        entity = "mode" if _has(q_cue, MODE_ENTITY_CUES) else "map"
        subject = _find_subject(re.sub(r"\b(by|per)\s+(map|mode)s?\b|\bmap breakdown\b|\bmap pool\b", " ", body).strip())
        f = filters.model_copy(update={"map": None if entity == "map" else filters.map,
                                       "mode": None if entity == "mode" else filters.mode})
        if subject:
            f = f.model_copy(update={"subject": subject})
        met = metric if metric else ("map_win_rate" if (subject or _has(q, ["win rate", "winrate", "best", "worst"])) else "maps")
        return StructuredQuery(intent="map_stats", entity=entity, metric=met, filters=f, aggregation=aggregation, sort=sort,
                               limit=limit or 10, min_maps=min_maps)

    # --- leaderboard
    if _has(q, LEADERBOARD_CUES):
        if metric is None:
            return Unanswerable(code="unsupported_metric", reason="a leaderboard needs a stat (e.g. eliminations, healing, K/D, win rate)",
                                suggestions=["Ask `what stats are available`."])
        subject = _find_subject(body)  # "most eliminations for Twisted Minds" -> team slice
        entity = "team" if (_has(q, ["team"]) or metric in ("win_rate", "record", "wins", "losses", "map_wins", "map_losses", "map_win_rate")) else "player"
        f = filters.model_copy(update={"team": subject}) if (subject and entity == "player") else filters
        return StructuredQuery(intent="leaderboard", entity=entity, metric=metric, filters=f, aggregation=aggregation,
                               sort=sort, limit=limit or 10, min_maps=min_maps)

    # --- team record / counts for a named entity (kind resolved later)
    if metric in ("record", "win_rate", "wins", "losses", "matches", "maps", "map_wins", "map_losses", "map_win_rate") or _has(q, ["record", "standings"]):
        subject = _find_subject(body)
        if not subject:
            return Unanswerable(code="unsupported_question", reason="which team? name the team, e.g. `Twisted Minds record in 2024`")
        return StructuredQuery(intent="team_record", entity="team", metric=metric or "record",
                               filters=filters.model_copy(update={"subject": subject}))

    # --- a single entity's stat
    subject = _find_subject(body)
    if metric and subject:
        role = "team" if _has(q, ["team"]) else ("player" if _has(q, PLAYER_CUES) else "subject")
        agg = aggregation if metric not in DERIVED_METRICS else "total"
        return StructuredQuery(intent="entity_stat", entity="team" if role == "team" else "player", metric=metric,
                               filters=filters.model_copy(update={role: subject}), aggregation=agg)
    if metric and not subject:
        # "eliminations in 2024" -> nobody named: rank everyone
        return StructuredQuery(intent="leaderboard", entity="player", metric=metric, filters=filters, aggregation=aggregation,
                               sort=sort, limit=limit or 10, min_maps=min_maps)
    if subject and not metric:
        return Unanswerable(code="unsupported_metric", reason=f"which stat for '{subject}'? e.g. eliminations, healing, K/D, record",
                            suggestions=["Ask `what stats are available`."])
    return Unanswerable(code="unsupported_question",
                        reason="could not map this question to a supported shape (leaderboard, a player's stat, a team's record, "
                               "head-to-head, map/mode stats, stat availability)",
                        suggestions=["Examples: `who had the most eliminations in 2024`, `KSAA average healing on control maps`, "
                                     "`Twisted Minds vs ENCE`, `what stats are available`"])
