"""Carry out a plan: the only place that loops over requests.

A run ends in exactly one of four ways, and says which:

  complete      every batch fetched (or was already held)
  budget        the hour's allowance ran out; the remainder is deferred, and rerunning later resumes
  rate_limited  Liquipedia said 429: the run stopped on that request, without retrying it
  failed        any other error: the run stopped on it, without retrying it

Coverage is recorded only when a whole batch (every page of it) has come back, so
the ledger never claims a page is held when only part of it is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from ..log import get_logger, log_event
from .attribution import page_url
from .client import (BudgetExhausted, LiquipediaClient, LiquipediaError, LiquipediaHalted, LiquipediaRateLimited)
from .planner import Plan

log = get_logger("owcsmuse.liquipedia")


@dataclass
class RunResult:
    outcome: str = "complete"
    requests_sent: int = 0
    cache_hits: int = 0
    batches_done: int = 0
    batches_total: int = 0
    rows: int = 0
    raw_ids: list[int] = field(default_factory=list)
    stopped_by: Optional[str] = None
    detail: Optional[str] = None
    short_batches: list[dict[str, Any]] = field(default_factory=list)   # fewer rows than expected: worth a look

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("outcome", "requests_sent", "cache_hits", "batches_done", "batches_total",
                                              "rows", "stopped_by", "detail", "short_batches")}


def _count(rows: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(field_name)
        if v is not None:
            out[str(v)] = out.get(str(v), 0) + 1
    return out


class StageCeiling(LiquipediaError):
    """The run's own request ceiling (`--max-requests`) is reached; the hourly budget is not involved."""


def run_plan(client: LiquipediaClient, plan: Plan, max_pages_per_batch: int = 50,
             max_requests: Optional[int] = None) -> RunResult:
    """Carry out `plan`. `max_requests` caps what this run may send (cache hits are free), below the hourly budget:
    a batch that keeps returning full pages stops there rather than paging on until the budget runs out."""
    res = RunResult(batches_total=len(plan.batches))
    sent_before = client.sent
    for batch in plan.batches:
        rows: list[dict[str, Any]] = []
        raw_ids: list[int] = []
        offset = 0
        try:
            for _ in range(max_pages_per_batch):
                if max_requests is not None and client.sent - sent_before >= max_requests:
                    raise StageCeiling(f"this run's ceiling of {max_requests} request(s) is reached")
                got = client.get(plan.endpoint, plan.params_for(batch, offset))
                res.cache_hits += got.from_cache
                raw_ids.append(got.raw_id)
                page = got.rows
                rows += page
                if len(page) < plan.limit:
                    break
                offset += plan.limit
            else:
                raise LiquipediaError(f"batch still returning full pages after {max_pages_per_batch} requests")
        except LiquipediaRateLimited as exc:
            res.outcome, res.stopped_by, res.detail = "rate_limited", "429", str(exc)
            break
        except (BudgetExhausted, LiquipediaHalted, StageCeiling) as exc:
            res.outcome, res.stopped_by, res.detail = "budget", type(exc).__name__, str(exc)
            break
        except LiquipediaError as exc:
            res.outcome, res.stopped_by, res.detail = "failed", type(exc).__name__, str(exc)
            break
        counts = _count(rows, plan.field)
        client.store.mark_covered(plan.endpoint, plan.field,
                                  [{"value": v, "rows_seen": counts.get(v.replace("_", " ")) or counts.get(v)}
                                   for v in batch.values], raw_ids)
        res.batches_done += 1
        res.rows += len(rows)
        res.raw_ids += raw_ids
        if batch.expected_rows and len(rows) < 0.7 * batch.expected_rows:
            res.short_batches.append({"values": len(batch.values), "expected": batch.expected_rows, "got": len(rows)})
    res.requests_sent = client.sent - sent_before
    log_event(log, logging.INFO if res.outcome in ("complete", "budget") else logging.ERROR, "liquipedia_run",
              **{k: v for k, v in res.as_dict().items() if k != "short_batches"})
    return res


def page_urls_for(values) -> list[str]:
    return [page_url(v) for v in values]
