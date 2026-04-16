"""Global configuration for VAULLS.

MCP developers call ``configure()`` once at startup, or set environment
variables. The library reads config lazily on first ``@paywall`` call.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Callable

from vaulls.types import VaullsConfig, _CDP_FACILITATOR_URL

logger = logging.getLogger(__name__)

_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

_lock = threading.Lock()
_config: VaullsConfig | None = None


def configure(
    pay_to: str | None = None,
    facilitator_url: str | None = None,
    network: str | None = None,
    facilitator_timeout: float | None = None,
    cdp_api_key_id: str | None = None,
    cdp_api_key_secret: str | None = None,
    circuit_breaker_enabled: bool | None = None,
    circuit_breaker_threshold: int | None = None,
    circuit_breaker_recovery: float | None = None,
    metrics_callback: Callable[[str, dict], None] | None = None,
    settlement_max_retries: int | None = None,
    settlement_retry_delay: float | None = None,
) -> VaullsConfig:
    """Set global VAULLS configuration.

    Args:
        pay_to: Wallet address to receive payments (or ``VAULLS_PAY_TO`` env var).
        facilitator_url: x402 facilitator URL (or ``VAULLS_FACILITATOR_URL``).
                         Default: Coinbase CDP facilitator.
        network: Default network — ``"base"`` or ``"base-sepolia"``
                 (or ``VAULLS_NETWORK``).
        facilitator_timeout: Timeout in seconds for facilitator HTTP calls
                             (or ``VAULLS_FACILITATOR_TIMEOUT``). Default 30.
        cdp_api_key_id: CDP API key ID (or ``VAULLS_CDP_API_KEY_ID`` env var).
                        Required for the CDP facilitator.
        cdp_api_key_secret: CDP API key secret (or ``VAULLS_CDP_API_KEY_SECRET``).
                            Required for the CDP facilitator.
        circuit_breaker_enabled: Enable circuit breaker for facilitator calls
                                 (or ``VAULLS_CIRCUIT_BREAKER_ENABLED``).
        circuit_breaker_threshold: Failures before circuit opens
                                   (or ``VAULLS_CIRCUIT_BREAKER_THRESHOLD``). Default 5.
        circuit_breaker_recovery: Seconds before half-open retry
                                  (or ``VAULLS_CIRCUIT_BREAKER_RECOVERY``). Default 60.
        metrics_callback: Callback invoked on every VAULLS event for custom metrics.
        settlement_max_retries: Max retry attempts for failed settlement file writes.
        settlement_retry_delay: Base delay in seconds between retries (exponential backoff).

    Returns:
        The active :class:`VaullsConfig`.
    """
    resolved_pay_to = pay_to or os.getenv("VAULLS_PAY_TO", "")
    if resolved_pay_to and not _EVM_ADDRESS_RE.match(resolved_pay_to):
        raise ValueError(
            f"Invalid wallet address: '{resolved_pay_to}'. "
            "Must be a valid EVM address (0x followed by 40 hex characters)."
        )

    global _config
    with _lock:
        _config = VaullsConfig(
            pay_to=resolved_pay_to,
            facilitator_url=facilitator_url
            or os.getenv("VAULLS_FACILITATOR_URL", _CDP_FACILITATOR_URL),
            network=network or os.getenv("VAULLS_NETWORK", "base-sepolia"),
            facilitator_timeout=facilitator_timeout
            if facilitator_timeout is not None
            else float(os.getenv("VAULLS_FACILITATOR_TIMEOUT", "30.0")),
            cdp_api_key_id=cdp_api_key_id
            or os.getenv("VAULLS_CDP_API_KEY_ID", ""),
            cdp_api_key_secret=cdp_api_key_secret
            or os.getenv("VAULLS_CDP_API_KEY_SECRET", ""),
            circuit_breaker_enabled=circuit_breaker_enabled
            if circuit_breaker_enabled is not None
            else os.getenv("VAULLS_CIRCUIT_BREAKER_ENABLED", "").lower() in ("1", "true", "yes"),
            circuit_breaker_threshold=circuit_breaker_threshold
            if circuit_breaker_threshold is not None
            else int(os.getenv("VAULLS_CIRCUIT_BREAKER_THRESHOLD", "5")),
            circuit_breaker_recovery=circuit_breaker_recovery
            if circuit_breaker_recovery is not None
            else float(os.getenv("VAULLS_CIRCUIT_BREAKER_RECOVERY", "60.0")),
            metrics_callback=metrics_callback,
            settlement_max_retries=settlement_max_retries
            if settlement_max_retries is not None
            else int(os.getenv("VAULLS_SETTLEMENT_MAX_RETRIES", "0")),
            settlement_retry_delay=settlement_retry_delay
            if settlement_retry_delay is not None
            else float(os.getenv("VAULLS_SETTLEMENT_RETRY_DELAY", "1.0")),
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
                        "VAULLS_FACILITATOR_URL", _CDP_FACILITATOR_URL
                    ),
                    network=os.getenv("VAULLS_NETWORK", "base-sepolia"),
                    facilitator_timeout=float(
                        os.getenv("VAULLS_FACILITATOR_TIMEOUT", "30.0")
                    ),
                    cdp_api_key_id=os.getenv("VAULLS_CDP_API_KEY_ID", ""),
                    cdp_api_key_secret=os.getenv("VAULLS_CDP_API_KEY_SECRET", ""),
                    circuit_breaker_enabled=os.getenv(
                        "VAULLS_CIRCUIT_BREAKER_ENABLED", ""
                    ).lower() in ("1", "true", "yes"),
                    circuit_breaker_threshold=int(
                        os.getenv("VAULLS_CIRCUIT_BREAKER_THRESHOLD", "5")
                    ),
                    circuit_breaker_recovery=float(
                        os.getenv("VAULLS_CIRCUIT_BREAKER_RECOVERY", "60.0")
                    ),
                    settlement_max_retries=int(
                        os.getenv("VAULLS_SETTLEMENT_MAX_RETRIES", "0")
                    ),
                    settlement_retry_delay=float(
                        os.getenv("VAULLS_SETTLEMENT_RETRY_DELAY", "1.0")
                    ),
                )
    return _config


def reset_config() -> None:
    """Reset config to None. Primarily for testing."""
    global _config
    with _lock:
        _config = None
