"""Structured logging events for VAULLS.

Provides a standardised way to log payment-related events with structured
context. All events go through Python's ``logging`` module (so existing
handlers, formatters, and filters work) and optionally invoke a user-provided
metrics callback for integration with Prometheus, StatsD, Datadog, etc.

Usage::

    from vaulls.logging import log_event, VaullsEvent

    log_event(VaullsEvent.PAYMENT_VERIFIED, tool="/tools/my-tool", price="0.05")
"""

from __future__ import annotations

import enum
import logging

logger = logging.getLogger("vaulls")


class VaullsEvent(enum.Enum):
    """Events emitted by the VAULLS payment layer."""

    PAYMENT_REQUIRED = "payment_required"
    PAYMENT_VERIFIED = "payment_verified"
    PAYMENT_FAILED = "payment_failed"
    SETTLEMENT_LOGGED = "settlement_logged"
    SETTLEMENT_FAILED = "settlement_failed"
    CIRCUIT_OPENED = "circuit_opened"
    CIRCUIT_CLOSED = "circuit_closed"
    FREE_CALL_USED = "free_call_used"
    RATE_LIMITED = "rate_limited"


def log_event(event: VaullsEvent, **context: object) -> None:
    """Log a structured VAULLS event.

    The event is logged via Python's ``logging`` module with the context
    as ``extra`` fields. If a ``metrics_callback`` is configured in
    :class:`~vaulls.types.VaullsConfig`, it is also invoked.

    Args:
        event: The event type.
        **context: Arbitrary key-value context (tool, price, caller, etc.).
    """
    logger.info(
        "vaulls.%s %s",
        event.value,
        " ".join(f"{k}={v}" for k, v in context.items()),
        extra={"vaulls_event": event.value, **context},
    )

    # Fire metrics callback if configured
    try:
        from vaulls.config import get_config

        cfg = get_config()
        cb = getattr(cfg, "metrics_callback", None)
        if cb is not None:
            cb(event.value, context)
    except Exception:
        pass
