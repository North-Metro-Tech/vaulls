"""Tests for vaulls.circuit_breaker — state transitions and recovery."""

import time

import pytest

from vaulls.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


class TestCircuitBreakerTransitions:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_check_raises_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()
        with pytest.raises(CircuitOpenError) as exc_info:
            cb.check()
        assert exc_info.value.retry_after > 0

    def test_check_passes_when_closed(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.check()  # Should not raise

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After reset, need 3 more failures to open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_open_to_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_one_probe(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        # First check should pass (half-open probe)
        cb.check()
        # Second check should fail (probe already in progress)
        with pytest.raises(CircuitOpenError):
            cb.check()

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        cb.check()  # half-open probe
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        cb.check()  # half-open probe
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_circuit_open_error_has_retry_after(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)
        cb.record_failure()
        with pytest.raises(CircuitOpenError) as exc_info:
            cb.check()
        assert 0 < exc_info.value.retry_after <= 30.0
