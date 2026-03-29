"""Tests for facilitator timeout propagation through config."""

from vaulls.config import configure, get_config, reset_config


class TestFacilitatorTimeout:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_default_timeout(self):
        cfg = configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        assert cfg.facilitator_timeout == 30.0

    def test_custom_timeout(self):
        cfg = configure(
            pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b",
            facilitator_timeout=5.0,
        )
        assert cfg.facilitator_timeout == 5.0

    def test_timeout_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULLS_FACILITATOR_TIMEOUT", "10.0")
        reset_config()
        cfg = get_config()
        assert cfg.facilitator_timeout == 10.0

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("VAULLS_FACILITATOR_TIMEOUT", "10.0")
        cfg = configure(
            pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b",
            facilitator_timeout=2.0,
        )
        assert cfg.facilitator_timeout == 2.0


class TestCircuitBreakerConfig:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_circuit_breaker_disabled_by_default(self):
        cfg = configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        assert cfg.circuit_breaker_enabled is False

    def test_circuit_breaker_enabled(self):
        cfg = configure(
            pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b",
            circuit_breaker_enabled=True,
            circuit_breaker_threshold=10,
            circuit_breaker_recovery=120.0,
        )
        assert cfg.circuit_breaker_enabled is True
        assert cfg.circuit_breaker_threshold == 10
        assert cfg.circuit_breaker_recovery == 120.0

    def test_circuit_breaker_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULLS_CIRCUIT_BREAKER_ENABLED", "true")
        monkeypatch.setenv("VAULLS_CIRCUIT_BREAKER_THRESHOLD", "3")
        monkeypatch.setenv("VAULLS_CIRCUIT_BREAKER_RECOVERY", "30.0")
        reset_config()
        cfg = get_config()
        assert cfg.circuit_breaker_enabled is True
        assert cfg.circuit_breaker_threshold == 3
        assert cfg.circuit_breaker_recovery == 30.0


class TestSettlementRetryConfig:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_settlement_retry_defaults(self):
        cfg = configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        assert cfg.settlement_max_retries == 0
        assert cfg.settlement_retry_delay == 1.0

    def test_settlement_retry_custom(self):
        cfg = configure(
            pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b",
            settlement_max_retries=3,
            settlement_retry_delay=0.5,
        )
        assert cfg.settlement_max_retries == 3
        assert cfg.settlement_retry_delay == 0.5

    def test_settlement_retry_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULLS_SETTLEMENT_MAX_RETRIES", "5")
        monkeypatch.setenv("VAULLS_SETTLEMENT_RETRY_DELAY", "2.0")
        reset_config()
        cfg = get_config()
        assert cfg.settlement_max_retries == 5
        assert cfg.settlement_retry_delay == 2.0
