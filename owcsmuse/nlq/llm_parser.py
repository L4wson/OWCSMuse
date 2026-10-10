"""Optional Claude-backed parser: question -> StructuredQuery via structured outputs.

The model only ever fills the StructuredQuery / Unanswerable object; it never
sees the database and never writes SQL. The result goes through the same
validator and compiler as the rule-based parser.

Requires the `anthropic` SDK (not a project dependency: install it explicitly
to enable `ask --parser llm`) and credentials resolved by the SDK
(ANTHROPIC_API_KEY or an `ant auth login` profile).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .parser import MAPS, MODES
from .schema import DERIVED_METRICS, StructuredQuery, Unanswerable

MODEL = "claude-opus-5"

SYSTEM = f"""You convert questions about Overwatch Champions Series (OWCS) statistics into a structured query object.
You never write SQL. Fill `query` when the question fits one of the supported shapes, otherwise fill `unanswerable`.

Supported intents:
- leaderboard: rank players (entity=player) or teams (entity=team) by a metric; use sort=asc for lowest/fewest.
- entity_stat: one named player's (or team's) number for a metric. Put the name in filters.subject unless the
  question says it is a player (filters.player) or a team (filters.team).
- team_record: a named team's series/map record; metric one of record, win_rate, wins, losses, matches, maps, map_wins, map_losses, map_win_rate.
- head_to_head: two teams; filters.team and filters.opponent; metric=record.
- map_stats: rows are maps (entity=map) or game modes (entity=mode), optionally for one player/team in filters.subject.
- stat_availability: which stats exist for which season; metric optional.
- placement: where teams finished at one event (entity=team, metric=placement); filters.championship names the event
  (required), filters.place a position (1 for "who won", 2 for runner-up), filters.subject a team ("where did X place").
- team_group: the members of a group of teams (entity=team, metric=members, filters.group="partner"): "which teams are the
  partner teams", optionally filters.season and filters.region. Any team question about partner teams ("which partner team
  won the most series in 2026") keeps its own intent and sets filters.group="partner".

Metrics are FACEIT stat keys exactly as spelled: Eliminations, Final Blows, Deaths, Assists, Damage Dealt, Healing Done,
Damage Mitigated, Solo Kills, Multi Kills, Environmental Kills, Objective Time, Time Played (append "/10m" for per-10-minute
rates), or derived metrics: {', '.join(DERIVED_METRICS)}.
Filters: season (year), championship (free text such as "stage 1", "main event", "dreamhack dallas", "world finals",
"midseason championship", "champions clash", "esports world cup"), map (one of {', '.join(MAPS)}),
mode (one of {', '.join(MODES.values())}), region (na, emea, international). aggregation: total or avg_per_map.
Keep entity names exactly as the user typed them; do not guess ids.

Unanswerable codes: unsupported_metric (hero picks, accuracy, ultimates, ratings, prize money and other untracked stats),
out_of_scope (Korea/Asia/Japan/China/Pacific, Overwatch League, qualifiers, relegation, ranked/hubs, schedules, predictions),
unsupported_question (anything else). Give a one-sentence reason."""


class ParsedQuestion(BaseModel):
    query: Optional[StructuredQuery] = None
    unanswerable: Optional[Unanswerable] = None


def parse_with_claude(question: str, model: str = MODEL):
    try:
        import anthropic  # optional dependency
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("the Claude parser needs the `anthropic` package: pip install anthropic") from exc

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=2048,
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{"role": "user", "content": question}],
        output_format=ParsedQuestion,
    )
    if response.stop_reason == "refusal":
        return Unanswerable(code="unsupported_question", reason="the model declined to interpret this question")
    parsed: ParsedQuestion = response.parsed_output
    if parsed.query is not None:
        return parsed.query
    if parsed.unanswerable is not None:
        return parsed.unanswerable
    return Unanswerable(code="unsupported_question", reason="the model returned neither a query nor a reason")
