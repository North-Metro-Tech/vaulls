"""Tests for vaulls.config."""

import os
import pytest
from unittest.mock import patch

from vaulls.config import configure, get_config, reset_config

VALID_WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"
VALID_WALLET_2 = "0x1234567890abcdef1234567890abcdef12345678"


class TestConfigure:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_configure_sets_values(self):
        cfg = configure(pay_to=VALID_WALLET, facilitator_url="http://test", network="base")
        assert cfg.pay_to == VALID_WALLET
        assert cfg.facilitator_url == "http://test"
        assert cfg.network == "base"

    def test_configure_from_env_vars(self):
        env = {
            "VAULLS_PAY_TO": VALID_WALLET,
            "VAULLS_FACILITATOR_URL": "http://env-facilitator",
            "VAULLS_NETWORK": "base",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_config()
            cfg = get_config()
        assert cfg.pay_to == VALID_WALLET
        assert cfg.facilitator_url == "http://env-facilitator"
        assert cfg.network == "base"

    def test_explicit_args_override_env(self):
        with patch.dict(os.environ, {"VAULLS_PAY_TO": VALID_WALLET}, clear=False):
            cfg = configure(pay_to=VALID_WALLET_2)
        assert cfg.pay_to == VALID_WALLET_2

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
        configure(pay_to=VALID_WALLET)
        a = get_config()
        b = get_config()
        assert a is b

    def test_chain_id_resolution(self):
        cfg = configure(network="base-sepolia")
        assert cfg.chain_id() == "eip155:84532"
        assert cfg.chain_id("base") == "eip155:8453"
        # Unknown networks pass through as-is
        assert cfg.chain_id("eip155:99999") == "eip155:99999"

    def test_invalid_wallet_raises(self):
        with pytest.raises(ValueError, match="Invalid wallet address"):
            configure(pay_to="not-a-wallet")

    def test_short_address_raises(self):
        with pytest.raises(ValueError, match="Invalid wallet address"):
            configure(pay_to="0xABC")

    def test_empty_wallet_allowed(self):
        # Empty string is allowed — validation happens at middleware level
        cfg = configure(pay_to="")
        assert cfg.pay_to == ""

    def test_valid_wallet_accepted(self):
        cfg = configure(pay_to=VALID_WALLET)
        assert cfg.pay_to == VALID_WALLET
