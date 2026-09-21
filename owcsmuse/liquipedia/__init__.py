"""Liquipedia integration: the LiquipediaDB API client, its request planner, and CC-BY-SA attribution.

    client.py       opt-in, budgeted (60/hour), cache-first, one strike on a 429
    planner.py      batch conditions, report the projected request count before any run
    runner.py       carry a plan out; a run stops on 429 or when the hour's budget is spent
    store.py        raw_payloads (source='liquipedia') + the coverage ledger
    attribution.py  every Liquipedia-sourced value carries its page URL
    stage1.py       the plan for the FACEIT-match-id completeness cross-check
"""

from .attribution import (CREDIT, LICENSE, LICENSE_URL, MissingAttribution, Sourced, attribution_block, page_url,
                          render_lines)
from .client import (API_BASE, ENABLE_ENV, BudgetExhausted, Fetched, LiquipediaClient, LiquipediaDisabled,
                     LiquipediaError, LiquipediaHalted, LiquipediaHTTPError, LiquipediaNotConfigured,
                     LiquipediaRateLimited, requests_enabled)
from .planner import MAX_CONDITION_CHARS, Batch, Plan, plan_requests
from .runner import RunResult, run_plan
from .store import PgStore, Store

__all__ = [
    "API_BASE", "ENABLE_ENV", "MAX_CONDITION_CHARS", "CREDIT", "LICENSE", "LICENSE_URL", "Batch", "BudgetExhausted",
    "Fetched", "LiquipediaClient", "LiquipediaDisabled", "LiquipediaError", "LiquipediaHTTPError", "LiquipediaHalted",
    "LiquipediaNotConfigured", "LiquipediaRateLimited", "MissingAttribution", "PgStore", "Plan", "RunResult", "Sourced",
    "Store", "attribution_block", "page_url", "plan_requests", "render_lines", "requests_enabled", "run_plan",
]
