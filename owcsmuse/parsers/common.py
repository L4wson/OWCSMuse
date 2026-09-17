"""Small tolerant conversions shared by the parsers. FACEIT sends stats as strings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def ts_from_epoch(value: Any) -> Optional[datetime]:
    """Match payloads use epoch seconds; championship payloads use epoch milliseconds."""
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 1_000_000_000_000:  # milliseconds
        n /= 1000.0
    return datetime.fromtimestamp(n, tz=timezone.utc)


def to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def faceit_url(value: Optional[str], lang: str = "en") -> Optional[str]:
    return value.replace("{lang}", lang) if isinstance(value, str) else None
