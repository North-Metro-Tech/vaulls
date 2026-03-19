"""Shared types for VAULLS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PaywallConfig:
    """Configuration for a single paywalled tool."""

    price: str
    asset: str = "USDC"
    network: str = "base-sepolia"
    description: str = ""


@dataclass
class VaullsConfig:
    """Global VAULLS configuration."""

    pay_to: str = ""
    facilitator_url: str = "https://x402.org/facilitator"
    network: str = "base-sepolia"
    settlement_log_path: str | None = None
    settlement_callback: Callable | None = None

    # Maps network shorthand to EIP-155 chain IDs
    NETWORK_MAP: dict[str, str] = field(default_factory=lambda: {
        "base": "eip155:8453",
        "base-sepolia": "eip155:84532",
    })

    def chain_id(self, network: str | None = None) -> str:
        """Resolve a network name to its EIP-155 chain ID."""
        net = network or self.network
        return self.NETWORK_MAP.get(net, net)
