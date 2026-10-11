"""The request planner: batch conditions into as few queries as possible, and say what a run will cost before it runs.

Sixty requests an hour is a budget to plan against, not a rate to hit and back off
from. So nothing here sends anything: it decides, from what is already held, which
requests are still needed, and reports the count first.

  1. Values already in the coverage ledger are dropped: what is held is never re-requested,
     however the set of wanted values changes between runs. The one exception is a held value whose answer still
     has an unfinished match on it (a stage in progress, a bracket still to be filled): that is re-requested, past
     the response cache, every run until Liquipedia shows all of it finished.
  2. The remaining values are OR-ed into as few conditions as the URL length allows.
  3. Each batch is paged at `limit` rows. Its expected row count comes from the caller
     (for the cross-check, how many matches FACEIT has for each competition), so
     `projected_requests` is a number, not a hope.
  4. The budget left this hour is subtracted, and what does not fit is reported as
     deferred, not failed: it resumes when earlier requests age out of the window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from .store import Store

# A conservative ceiling on the length of one `conditions` value. It travels in a GET URL, and percent-encoding
# roughly doubles it (brackets, colons and slashes), so this keeps a URL around 5 KB, under the usual 8 KB limit. All 20
# Stage 1 pages fit one batch at this size; if the server rejects a long URL (414), lower it and the plan splits.
MAX_CONDITION_CHARS = 2400


class ConditionError(ValueError):
    pass


def condition_for(field_name: str, value: str) -> str:
    if any(t in value for t in ("[[", "]]", "::", "\n", "\r")) or not value.strip():
        raise ConditionError(f"value cannot be used in a LiquipediaDB condition: {value!r}")
    return f"[[{field_name}::{value}]]"


def or_conditions(field_name: str, values: Iterable[str], extra: Optional[str] = None) -> str:
    """([[f::a]] OR [[f::b]]) [AND extra]"""
    body = " OR ".join(condition_for(field_name, v) for v in values)
    out = f"({body})"
    return f"{out} AND {extra}" if extra else out


@dataclass
class Batch:
    values: tuple[str, ...]
    conditions: str
    expected_rows: int
    pages: int                                  # projected requests for this batch
    fresh: bool = False                         # a re-fetch of held values: asked of Liquipedia, never the cache

    def as_dict(self) -> dict[str, Any]:
        return {"values": list(self.values), "condition_chars": len(self.conditions),
                "expected_rows": self.expected_rows, "projected_requests": self.pages, "refetch": self.fresh}


@dataclass
class Plan:
    endpoint: str
    field: str
    limit: int
    order: Optional[str]
    query: Optional[str]
    batches: list[Batch] = field(default_factory=list)
    held: list[str] = field(default_factory=list)         # values already covered: not re-requested
    refetch: list[str] = field(default_factory=list)      # covered, but with unfinished matches: re-requested
    budget: dict[str, Any] = field(default_factory=dict)
    extra: Optional[str] = None
    wiki: str = "overwatch"

    @property
    def projected_requests(self) -> int:
        return sum(b.pages for b in self.batches)

    @property
    def runnable_now(self) -> int:
        return min(self.projected_requests, self.budget.get("remaining", self.projected_requests))

    @property
    def deferred(self) -> int:
        return self.projected_requests - self.runnable_now

    def params_for(self, batch: Batch, offset: int = 0) -> dict[str, Any]:
        p: dict[str, Any] = {"conditions": batch.conditions, "limit": self.limit}
        if offset:
            p["offset"] = offset
        if self.order:
            p["order"] = self.order
        if self.query:
            p["query"] = self.query
        return p

    def as_dict(self) -> dict[str, Any]:
        return {"endpoint": self.endpoint, "field": self.field, "limit": self.limit, "wiki": self.wiki,
                "values_held_already": len(self.held), "values_refetched_unfinished": len(self.refetch),
                "values_to_fetch": sum(len(b.values) for b in self.batches),
                "batches": [b.as_dict() for b in self.batches], "projected_requests": self.projected_requests,
                "budget": {k: (v.isoformat(timespec="seconds") if isinstance(v, datetime) else v)
                           for k, v in self.budget.items()},
                "runnable_now": self.runnable_now, "deferred_to_later_hours": self.deferred}

    def render(self) -> str:
        b = self.budget
        lines = [
            f"Liquipedia plan: GET /{self.endpoint} on the {self.wiki} wiki, filtered by {self.field}, {self.limit} rows per request",
            f"  values wanted already held (not re-requested): {len(self.held)}",
            f"  values held but re-fetched (unfinished matches on them): {len(self.refetch)}",
            f"  values to fetch: {sum(len(x.values) for x in self.batches)} in {len(self.batches)} batch(es)",
        ]
        for i, x in enumerate(self.batches, 1):
            lines.append(f"    batch {i}: {len(x.values)} values, ~{x.expected_rows} rows expected, "
                         f"{len(x.conditions)} condition chars -> {x.pages} request(s)")
        lines.append(f"  PROJECTED REQUESTS: {self.projected_requests}")
        if b:
            lines.append(f"  budget: {b.get('used', 0)} of {b.get('budget')} used in the last hour, {b.get('remaining')} left")
            if self.deferred:
                lines.append(f"  {self.runnable_now} can run now; {self.deferred} would wait for the next window"
                             + (f" (a request ages out {b['resumes_at']:%H:%M}Z)" if b.get("resumes_at") else ""))
        return "\n".join(lines)


def plan_requests(store: Store, *, endpoint: str, field_name: str, wants: dict[str, int], limit: int,
                  wiki: str = "overwatch", order: Optional[str] = None, query: Optional[str] = None,
                  extra: Optional[str] = None, budget: Optional[dict[str, Any]] = None, refresh: bool = False,
                  max_condition_chars: int = MAX_CONDITION_CHARS) -> Plan:
    """Plan the requests to fetch every value in `wants` ({value: expected_rows}).

    Pure with respect to Liquipedia: reads the coverage ledger, sends nothing.
    """
    plan = Plan(endpoint=endpoint, field=field_name, limit=limit, order=order, query=query, extra=extra,
                budget=dict(budget or {}), wiki=wiki)
    covered = {} if refresh else store.covered(endpoint, field_name, wants)
    open_ = store.unfinished(endpoint, field_name, covered) if covered else set()
    plan.held = sorted(v for v in covered if v not in open_)
    plan.refetch = sorted(open_)
    todo = sorted(v for v in wants if v not in covered)

    def add(values: list[str], fresh: bool) -> None:
        batch: list[str] = []
        rows = 0

        def close() -> None:
            nonlocal batch, rows
            if batch:
                plan.batches.append(Batch(tuple(batch), or_conditions(field_name, batch, extra), rows,
                                          max(1, math.ceil(rows / limit)), fresh))
            batch, rows = [], 0

        for v in values:
            trial = batch + [v]
            if batch and len(or_conditions(field_name, trial, extra)) > max_condition_chars:
                close()
                trial = [v]
            batch = trial
            rows += max(0, wants[v])
        close()

    add(todo, False)
    add(plan.refetch, True)
    return plan
