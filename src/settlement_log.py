import json
import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path("settlements.jsonl")


def log_settlement(
    tool: str,
    price: str,
    payer: str,
    tx_hash: str,
    network: str,
    latency_ms: float,
    log_path: Path = DEFAULT_LOG_PATH,
) -> dict:
    """Log a settlement to JSONL file.

    Returns the logged entry dict.
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
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        logger.exception("Failed to write settlement log")
    return entry
