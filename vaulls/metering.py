"""Metering for free-tier support.

Tracks per-tool call counts to support ``@paywall(free_calls=10)``
which gives callers N free calls before requiring payment.

The default backend is an in-memory counter that resets on server
restart. For persistence across restarts and shared state across
instances, use :func:`set_meter` with a :class:`RedisCallMeter`
from ``vaulls.metering_redis``.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Protocol, runtime_checkable


@runtime_checkable
class MeterBackend(Protocol):
    """Protocol that all meter backends must satisfy."""

    def record_call(self, tool_name: str, caller_id: str) -> int: ...
    def get_count(self, tool_name: str, caller_id: str) -> int: ...
    def is_free(self, tool_name: str, caller_id: str, free_limit: int) -> bool: ...
    def reset(self) -> None: ...


class CallMeter:
    """Thread-safe in-memory per-tool, per-caller call counter."""

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
_meter: MeterBackend = CallMeter()
_meter_lock = threading.Lock()


def get_meter() -> MeterBackend:
    """Return the global call meter."""
    with _meter_lock:
        return _meter


def set_meter(meter: MeterBackend) -> None:
    """Replace the global call meter (e.g. with a Redis-backed backend).

    Example::

        from vaulls.metering_redis import RedisCallMeter
        import redis

        set_meter(RedisCallMeter(redis.Redis()))
    """
    global _meter
    with _meter_lock:
        _meter = meter
