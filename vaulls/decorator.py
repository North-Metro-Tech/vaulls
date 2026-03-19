"""The ``@paywall`` decorator — the core of VAULLS.

Wraps any MCP tool function so that callers must pay via x402 before
the function executes. Works with both sync and async functions.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

from vaulls.types import PaywallConfig


def paywall(
    price: str,
    asset: str = "USDC",
    network: str | None = None,
    description: str = "",
) -> Callable:
    """Decorator that adds an x402 paywall to an MCP tool function.

    Usage::

        @mcp.tool()
        @paywall(price="0.05")
        def my_tool(query: str) -> str:
            return "paid result"

    The decorator attaches a ``__vaulls__`` attribute to the function
    containing the :class:`PaywallConfig`. Integration adapters
    (FastAPI, MCP) inspect this attribute to wire up the x402 middleware.

    Args:
        price: Price in USD (e.g. ``"0.05"``). Do not include ``$`` sign.
        asset: Payment asset — default ``"USDC"``.
        network: Network override (``"base"``, ``"base-sepolia"``).
                 Falls back to global config if ``None``.
        description: Optional description of what the payment is for.
    """
    pw_config = PaywallConfig(
        price=price,
        asset=asset,
        network=network or "",
        description=description,
    )

    def decorator(func: Callable) -> Callable:
        # Attach paywall metadata so integrations can discover it
        func.__vaulls__ = pw_config  # type: ignore[attr-defined]

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Execution gating is handled by the integration layer
                # (FastAPI middleware or MCP adapter), not here.
                # By the time this wrapper runs, payment has been verified.
                return await func(*args, **kwargs)

            async_wrapper.__vaulls__ = pw_config  # type: ignore[attr-defined]
            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            sync_wrapper.__vaulls__ = pw_config  # type: ignore[attr-defined]
            return sync_wrapper

    return decorator


def is_paywalled(func: Callable) -> bool:
    """Check whether a function has a ``@paywall`` decorator."""
    return hasattr(func, "__vaulls__")


def get_paywall_config(func: Callable) -> PaywallConfig | None:
    """Return the :class:`PaywallConfig` for a paywalled function, or ``None``."""
    return getattr(func, "__vaulls__", None)
