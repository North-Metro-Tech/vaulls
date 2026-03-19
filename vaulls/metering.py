"""In-memory metering for free-tier support.

Tracks per-tool call counts to support ``@paywall(free_calls=10)``
which gives callers N free calls before requiring payment.

This is intentionally simple — in-memory counters that reset on
server restart. Not a billing system.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class CallMeter:
    """Thread-safe per-tool, per-caller call counter."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = threading.Lock()

    def record_call(self, tool_name: str, caller_id: str) -> int:
        """Record a call and return the new count (1-indexed)."""
        with self._lock:
            self._counts[tool_name][caller_id] += 1
            return self._counts[tool_name][caller_id]

    def get_count(self, tool_name: str, caller_id: str) -> int:
        """Return the current call count for a tool/caller pair."""
        with self._lock:
            return self._counts[tool_name][caller_id]

    def is_free(self, tool_name: str, caller_id: str, free_limit: int) -> bool:
        """Check if the next call would be within the free tier.

        Returns True if current count is below the free limit.
        """
        if free_limit <= 0:
            return False
        with self._lock:
            return self._counts[tool_name][caller_id] < free_limit

    def reset(self) -> None:
        """Clear all counters. Primarily for testing."""
        with self._lock:
            self._counts.clear()


# Global meter instance
_meter = CallMeter()


def get_meter() -> CallMeter:
    """Return the global call meter."""
    return _meter
