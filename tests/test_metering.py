"""Tests for vaulls.metering — free-tier call tracking."""

from vaulls.metering import CallMeter


class TestCallMeter:
    def setup_method(self):
        self.meter = CallMeter()

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
        # Now at 3 calls — should NOT be free anymore
        assert not self.meter.is_free("tool", "caller", free_limit=3)

    def test_is_free_zero_limit_always_false(self):
        assert not self.meter.is_free("tool", "caller", free_limit=0)

    def test_reset_clears_all(self):
        self.meter.record_call("tool", "caller")
        self.meter.reset()
        assert self.meter.get_count("tool", "caller") == 0
