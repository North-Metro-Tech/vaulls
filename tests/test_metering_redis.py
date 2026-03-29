"""Tests for vaulls.metering_redis — Redis-backed call meter via fakeredis."""

import pytest

try:
    import fakeredis
except ImportError:
    pytest.skip("fakeredis not installed", allow_module_level=True)

from vaulls.metering import CallMeter, get_meter, set_meter
from vaulls.metering_redis import RedisCallMeter


class TestRedisCallMeter:
    def setup_method(self):
        self.redis = fakeredis.FakeRedis()
        self.meter = RedisCallMeter(self.redis)

    def teardown_method(self):
        self.redis.flushall()

    def test_initial_count_is_zero(self):
        assert self.meter.get_count("tool", "caller") == 0

    def test_record_increments_count(self):
        assert self.meter.record_call("tool", "caller") == 1
        assert self.meter.record_call("tool", "caller") == 2
        assert self.meter.get_count("tool", "caller") == 2

    def test_separate_callers_tracked_independently(self):
        self.meter.record_call("tool", "alice")
        self.meter.record_call("tool", "alice")
        self.meter.record_call("tool", "bob")

        assert self.meter.get_count("tool", "alice") == 2
        assert self.meter.get_count("tool", "bob") == 1

    def test_separate_tools_tracked_independently(self):
        self.meter.record_call("tool_a", "caller")
        self.meter.record_call("tool_b", "caller")

        assert self.meter.get_count("tool_a", "caller") == 1
        assert self.meter.get_count("tool_b", "caller") == 1

    def test_is_free_within_limit(self):
        assert self.meter.is_free("tool", "caller", free_limit=3)
        self.meter.record_call("tool", "caller")
        assert self.meter.is_free("tool", "caller", free_limit=3)
        self.meter.record_call("tool", "caller")
        assert self.meter.is_free("tool", "caller", free_limit=3)
        self.meter.record_call("tool", "caller")
        assert not self.meter.is_free("tool", "caller", free_limit=3)

    def test_is_free_zero_limit_always_false(self):
        assert not self.meter.is_free("tool", "caller", free_limit=0)

    def test_reset_clears_all(self):
        self.meter.record_call("tool", "caller")
        self.meter.reset()
        assert self.meter.get_count("tool", "caller") == 0

    def test_ttl_sets_expiry(self):
        meter = RedisCallMeter(self.redis, ttl=3600)
        meter.record_call("tool", "caller")
        ttl = self.redis.ttl("vaulls:meter:tool")
        assert ttl > 0

    def test_custom_prefix(self):
        meter = RedisCallMeter(self.redis, prefix="myapp:meter")
        meter.record_call("tool", "caller")
        assert self.redis.hget("myapp:meter:tool", "caller") == b"1"


class TestSetMeter:
    def setup_method(self):
        self._original = get_meter()

    def teardown_method(self):
        set_meter(self._original)

    def test_set_meter_swaps_global(self):
        redis = fakeredis.FakeRedis()
        redis_meter = RedisCallMeter(redis)
        set_meter(redis_meter)
        assert get_meter() is redis_meter

    def test_set_meter_back_to_in_memory(self):
        redis = fakeredis.FakeRedis()
        set_meter(RedisCallMeter(redis))
        in_memory = CallMeter()
        set_meter(in_memory)
        assert get_meter() is in_memory
