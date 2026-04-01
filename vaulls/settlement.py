"""Settlement logging for VAULLS.

Opt-in logging of successful x402 settlements. Developers can log to a
JSONL file, provide a custom callback, or both.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Callable

from vaulls.config import get_config
from vaulls.logging import VaullsEvent, log_event

logger = logging.getLogger(__name__)


def enable_settlement_log(
    path: str | Path | None = None,
    callback: Callable[[dict], None] | None = None,
    max_retries: int | None = None,
    retry_delay: float | None = None,
) -> None:
    """Enable settlement logging.

    Args:
        path: File path for JSONL settlement log.
        callback: A callable that receives the settlement dict.
        max_retries: Max retry attempts for failed file writes (default 0 = no retry).
        retry_delay: Base delay in seconds between retries (exponential backoff).
    """
    cfg = get_config()
    if path is not None:
        cfg.settlement_log_path = str(path)
    if callback is not None:
        cfg.settlement_callback = callback
    if max_retries is not None:
        cfg.settlement_max_retries = max_retries
    if retry_delay is not None:
        cfg.settlement_retry_delay = retry_delay


def _write_with_retry(path: str, line: str, max_retries: int, base_delay: float) -> None:
    """Write a line to a file with optional exponential backoff retry."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with open(path, "a") as f:
                f.write(line)
            return
        except OSError as exc:
            last_exc = exc
            if attempt < max_retries:
                import time
                time.sleep(base_delay * (2 ** attempt))

    log_event(VaullsEvent.SETTLEMENT_FAILED, path=path, error=str(last_exc))
    logger.exception("Failed to write settlement log to %s after %d attempt(s)", path, max_retries + 1)


def log_settlement(
    tool: str,
    price: str,
    payer: str,
    tx_hash: str,
    network: str,
    latency_ms: float,
) -> dict:
    """Record a settlement event.

    Writes to JSONL file and/or invokes the callback depending on what
    the developer enabled via :func:`enable_settlement_log`.

    Returns:
        The settlement entry dict.
    """
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": tool,
        "price": price,
        "payer": payer,
        "tx_hash": tx_hash,
        "network": network,
        "latency_ms": round(latency_ms, 1),
    }

    cfg = get_config()

    if cfg.settlement_log_path:
        _write_with_retry(
            cfg.settlement_log_path,
            json.dumps(entry) + "\n",
            cfg.settlement_max_retries,
            cfg.settlement_retry_delay,
        )

    if cfg.settlement_callback:
        try:
            cfg.settlement_callback(entry)
        except Exception:
            log_event(VaullsEvent.SETTLEMENT_FAILED, tool=tool, error="callback_exception")
            logger.exception("Settlement callback raised an exception")

    log_event(VaullsEvent.SETTLEMENT_LOGGED, tool=tool, price=price, payer=payer)
    return entry
