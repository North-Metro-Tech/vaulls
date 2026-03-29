"""Circuit breaker for facilitator calls.

Prevents cascading failures when the x402 facilitator is unreachable.
After ``failure_threshold`` consecutive failures, the breaker opens and
rejects calls immediately for ``recovery_timeout`` seconds, then allows
a single probe call (half-open). Success resets; failure re-opens.
"""

from __future__ import annotations

import enum
import threading
import time


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and rejecting calls."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker open. Retry after {retry_after:.0f}s.")


class CircuitBreaker:
    """Thread-safe circuit breaker with three states.

    Args:
        failure_threshold: Consecutive failures before the circuit opens.
        recovery_timeout: Seconds to wait before allowing a half-open probe.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_in_progress = False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_progress = False
            return self._state

    def check(self) -> None:
        """Check whether a call is allowed. Raises :class:`CircuitOpenError` if not."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_progress = False
                else:
                    raise CircuitOpenError(retry_after=self._recovery_timeout - elapsed)

            # HALF_OPEN: allow one probe at a time
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_progress:
                    raise CircuitOpenError(retry_after=self._recovery_timeout)
                self._half_open_in_progress = True

    def record_success(self) -> None:
        """Record a successful call — resets the breaker to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_in_progress = False

    def record_failure(self) -> None:
        """Record a failed call — may trip the breaker to OPEN."""
        with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                self._half_open_in_progress = False
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
