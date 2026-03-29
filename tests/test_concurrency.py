"""Concurrency stress tests for thread-safe VAULLS components."""

import threading

from vaulls.circuit_breaker import CircuitBreaker, CircuitState
from vaulls.metering import CallMeter
from vaulls.rate_limiter import TokenBucketLimiter


class TestCallMeterConcurrency:
    def test_concurrent_record_calls(self):
        """50 threads x 100 calls = 5000 total."""
        meter = CallMeter()
        threads_count = 50
        calls_per_thread = 100

        def worker():
            for _ in range(calls_per_thread):
                meter.record_call("tool", "caller")

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert meter.get_count("tool", "caller") == threads_count * calls_per_thread


class TestCircuitBreakerConcurrency:
    def test_concurrent_failures_trip_correctly(self):
        """Multiple threads recording failures should cleanly transition to OPEN."""
        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=60.0)
        threads_count = 20

        def worker():
            cb.record_failure()

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 20 failures > threshold of 10, so should be OPEN
        assert cb.state == CircuitState.OPEN

    def test_concurrent_success_resets(self):
        """Multiple threads recording success after failure should reset cleanly."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        threads_count = 20

        def worker():
            cb.record_success()

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert cb.state == CircuitState.CLOSED


class TestTokenBucketConcurrency:
    def test_concurrent_allows_no_over_issue(self):
        """With 10 tokens and 50 threads, at most 10 should be allowed."""
        limiter = TokenBucketLimiter(max_tokens=10, refill_rate=0.0)
        results = []
        lock = threading.Lock()

        def worker():
            result = limiter.allow("caller")
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 10
        assert results.count(False) == 40
