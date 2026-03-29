"""Token bucket rate limiter for VAULLS.

Provides per-caller rate limiting to protect against abuse.
The default is an in-memory implementation; a Redis-backed variant
is available with ``pip install vaulls[redis]``.
"""

from __future__ import annotations

import threading
import time


class TokenBucketLimiter:
    """Thread-safe in-memory token bucket rate limiter.

    Args:
        max_tokens: Burst capacity per caller.
        refill_rate: Tokens added per second per caller.
    """

    def __init__(self, max_tokens: float, refill_rate: float) -> None:
        self._max_tokens = max_tokens
        self._refill_rate = refill_rate
        self._buckets: dict[str, tuple[float, float]] = {}  # caller -> (tokens, last_refill)
        self._lock = threading.Lock()

    def allow(self, caller_id: str) -> bool:
        """Check if a request from ``caller_id`` is allowed.

        Returns True and consumes a token if allowed, False otherwise.
        """
        now = time.monotonic()
        with self._lock:
            if caller_id in self._buckets:
                tokens, last_refill = self._buckets[caller_id]
                elapsed = now - last_refill
                tokens = min(self._max_tokens, tokens + elapsed * self._refill_rate)
            else:
                tokens = self._max_tokens
                last_refill = now

            if tokens >= 1.0:
                self._buckets[caller_id] = (tokens - 1.0, now)
                return True
            else:
                self._buckets[caller_id] = (tokens, now)
                return False

    def reset(self) -> None:
        """Clear all buckets. Primarily for testing."""
        with self._lock:
            self._buckets.clear()
