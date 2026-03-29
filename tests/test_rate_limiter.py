"""Tests for vaulls.rate_limiter — token bucket rate limiting."""

import time

from vaulls.rate_limiter import TokenBucketLimiter


class TestTokenBucketLimiter:
    def test_allows_within_capacity(self):
        limiter = TokenBucketLimiter(max_tokens=5, refill_rate=1.0)
        for _ in range(5):
            assert limiter.allow("caller")

    def test_rejects_after_exhaustion(self):
        limiter = TokenBucketLimiter(max_tokens=3, refill_rate=0.0)
        for _ in range(3):
            assert limiter.allow("caller")
        assert not limiter.allow("caller")

    def test_refills_over_time(self):
        limiter = TokenBucketLimiter(max_tokens=2, refill_rate=20.0)  # 20 tokens/sec
        # Exhaust the bucket
        assert limiter.allow("caller")
        assert limiter.allow("caller")
        assert not limiter.allow("caller")
        # Wait for refill
        time.sleep(0.1)  # should refill ~2 tokens
        assert limiter.allow("caller")

    def test_separate_callers_independent(self):
        limiter = TokenBucketLimiter(max_tokens=1, refill_rate=0.0)
        assert limiter.allow("alice")
        assert not limiter.allow("alice")
        # Bob has his own bucket
        assert limiter.allow("bob")
        assert not limiter.allow("bob")

    def test_does_not_exceed_max_tokens(self):
        limiter = TokenBucketLimiter(max_tokens=3, refill_rate=100.0)
        time.sleep(0.1)  # would over-refill without cap
        # Should only get max_tokens calls
        results = [limiter.allow("caller") for _ in range(5)]
        assert results.count(True) == 3

    def test_reset_clears_all(self):
        limiter = TokenBucketLimiter(max_tokens=1, refill_rate=0.0)
        assert limiter.allow("caller")
        assert not limiter.allow("caller")
        limiter.reset()
        # After reset, fresh bucket
        assert limiter.allow("caller")
