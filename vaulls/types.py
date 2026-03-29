"""Shared types for VAULLS."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_STRICT = os.getenv("VAULLS_STRICT_VALIDATION", "1").lower() not in ("0", "false", "no")


def _validate(condition: bool, message: str) -> None:
    """Raise ValueError if strict validation is on and condition fails."""
    if _STRICT and not condition:
        raise ValueError(message)


@dataclass
class PaywallConfig:
    """Configuration for a single paywalled tool."""

    price: str
    asset: str = "USDC"
    network: str | list[str] = ""
    description: str = ""
    free_calls: int = 0

    def __post_init__(self) -> None:
        # Validate price is a parseable non-negative number (strip leading $)
        raw = self.price.lstrip("$")
        try:
            val = float(raw)
            _validate(val >= 0, f"Price must be non-negative, got '{self.price}'")
        except ValueError:
            _validate(False, f"Price must be numeric, got '{self.price}'")

        _validate(bool(self.asset), "Asset must not be empty")
        _validate(self.free_calls >= 0, f"free_calls must be >= 0, got {self.free_calls}")

    def networks_list(self) -> list[str]:
        """Return network(s) as a list, regardless of input format."""
        if isinstance(self.network, list):
            return self.network
        return [self.network] if self.network else []


@dataclass
class VaullsConfig:
    """Global VAULLS configuration."""

    pay_to: str = ""
    facilitator_url: str = "https://x402.org/facilitator"
    network: str = "base-sepolia"
    facilitator_timeout: float = 30.0
    settlement_log_path: str | None = None
    settlement_callback: Callable | None = None

    # Circuit breaker settings
    circuit_breaker_enabled: bool = False
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery: float = 60.0

    # Observability
    metrics_callback: Callable[[str, dict], None] | None = None

    # Settlement retry settings
    settlement_max_retries: int = 0
    settlement_retry_delay: float = 1.0

    # Rate limiting
    rate_limit_rpm: int | None = None

    # Maps network shorthand to EIP-155 chain IDs
    NETWORK_MAP: dict[str, str] = field(default_factory=lambda: {
        "base": "eip155:8453",
        "base-sepolia": "eip155:84532",
    })

    def __post_init__(self) -> None:
        if self.pay_to:
            _validate(
                bool(_EVM_ADDRESS_RE.match(self.pay_to)),
                f"Invalid wallet address: '{self.pay_to}'. "
                "Must be 0x followed by 40 hex characters.",
            )
        _validate(
            self.facilitator_url.startswith(("http://", "https://")),
            f"facilitator_url must start with http:// or https://, got '{self.facilitator_url}'",
        )
        _validate(
            self.facilitator_timeout > 0,
            f"facilitator_timeout must be positive, got {self.facilitator_timeout}",
        )

    def chain_id(self, network: str | None = None) -> str:
        """Resolve a network name to its EIP-155 chain ID."""
        net = network or self.network
        return self.NETWORK_MAP.get(net, net)
