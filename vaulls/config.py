"""Global configuration for VAULLS.

MCP developers call ``configure()`` once at startup, or set environment
variables. The library reads config lazily on first ``@paywall`` call.
"""

from __future__ import annotations

import os
import threading

from vaulls.types import VaullsConfig

_lock = threading.Lock()
_config: VaullsConfig | None = None


def configure(
    pay_to: str | None = None,
    facilitator_url: str | None = None,
    network: str | None = None,
) -> VaullsConfig:
    """Set global VAULLS configuration.

    Args:
        pay_to: Wallet address to receive payments (or ``VAULLS_PAY_TO`` env var).
        facilitator_url: x402 facilitator URL (or ``VAULLS_FACILITATOR_URL``).
        network: Default network — ``"base"`` or ``"base-sepolia"``
                 (or ``VAULLS_NETWORK``).

    Returns:
        The active :class:`VaullsConfig`.
    """
    global _config
    with _lock:
        _config = VaullsConfig(
            pay_to=pay_to or os.getenv("VAULLS_PAY_TO", ""),
            facilitator_url=facilitator_url
            or os.getenv("VAULLS_FACILITATOR_URL", "https://x402.org/facilitator"),
            network=network or os.getenv("VAULLS_NETWORK", "base-sepolia"),
        )
        return _config


def get_config() -> VaullsConfig:
    """Return the current config, auto-configuring from env vars if needed."""
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                _config = VaullsConfig(
                    pay_to=os.getenv("VAULLS_PAY_TO", ""),
                    facilitator_url=os.getenv(
                        "VAULLS_FACILITATOR_URL", "https://x402.org/facilitator"
                    ),
                    network=os.getenv("VAULLS_NETWORK", "base-sepolia"),
                )
    return _config


def reset_config() -> None:
    """Reset config to None. Primarily for testing."""
    global _config
    with _lock:
        _config = None
