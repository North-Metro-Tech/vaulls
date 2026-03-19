"""Tests for vaulls.config."""

import os
from unittest.mock import patch

from vaulls.config import configure, get_config, reset_config


class TestConfigure:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_configure_sets_values(self):
        cfg = configure(pay_to="0xABC", facilitator_url="http://test", network="base")
        assert cfg.pay_to == "0xABC"
        assert cfg.facilitator_url == "http://test"
        assert cfg.network == "base"

    def test_configure_from_env_vars(self):
        env = {
            "VAULLS_PAY_TO": "0xENV",
            "VAULLS_FACILITATOR_URL": "http://env-facilitator",
            "VAULLS_NETWORK": "base",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_config()
            cfg = get_config()
        assert cfg.pay_to == "0xENV"
        assert cfg.facilitator_url == "http://env-facilitator"
        assert cfg.network == "base"

    def test_explicit_args_override_env(self):
        with patch.dict(os.environ, {"VAULLS_PAY_TO": "0xENV"}, clear=False):
            cfg = configure(pay_to="0xEXPLICIT")
        assert cfg.pay_to == "0xEXPLICIT"

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VAULLS_PAY_TO", None)
            os.environ.pop("VAULLS_FACILITATOR_URL", None)
            os.environ.pop("VAULLS_NETWORK", None)
            reset_config()
            cfg = get_config()
        assert cfg.pay_to == ""
        assert cfg.facilitator_url == "https://x402.org/facilitator"
        assert cfg.network == "base-sepolia"

    def test_get_config_returns_same_instance(self):
        configure(pay_to="0x1")
        a = get_config()
        b = get_config()
        assert a is b

    def test_chain_id_resolution(self):
        cfg = configure(network="base-sepolia")
        assert cfg.chain_id() == "eip155:84532"
        assert cfg.chain_id("base") == "eip155:8453"
        # Unknown networks pass through as-is
        assert cfg.chain_id("eip155:99999") == "eip155:99999"
