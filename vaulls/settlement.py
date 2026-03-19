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

logger = logging.getLogger(__name__)


def enable_settlement_log(
    path: str | Path | None = None,
    callback: Callable[[dict], None] | None = None,
) -> None:
    """Enable settlement logging.

    Args:
        path: File path for JSONL settlement log.
        callback: A callable that receives the settlement dict.
    """
    cfg = get_config()
    if path is not None:
        cfg.settlement_log_path = str(path)
    if callback is not None:
        cfg.settlement_callback = callback


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
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "tool": tool,
        "price": price,
        "payer": payer,
        "tx_hash": tx_hash,
        "network": network,
        "latency_ms": round(latency_ms, 1),
    }

    cfg = get_config()

    if cfg.settlement_log_path:
        try:
            with open(cfg.settlement_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            logger.exception("Failed to write settlement log to %s", cfg.settlement_log_path)

    if cfg.settlement_callback:
        try:
            cfg.settlement_callback(entry)
        except Exception:
            logger.exception("Settlement callback raised an exception")

    return entry
