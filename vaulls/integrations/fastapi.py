"""FastAPI integration for VAULLS.

Provides middleware that automatically gates ``@paywall``-decorated
FastAPI route handlers behind x402 payment verification.

Usage::

    from fastapi import FastAPI
    from vaulls import configure, paywall
    from vaulls.integrations.fastapi import vaulls_middleware

    app = FastAPI()
    configure(pay_to="0x...")

    @app.post("/tools/my-tool")
    @paywall(price="0.05")
    def my_tool(data: dict):
        return {"result": "paid"}

    # Wire up x402 payment gating for all @paywall routes
    vaulls_middleware(app)
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from x402 import x402ResourceServer
from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import ExactEvmServerScheme

from vaulls.config import get_config
from vaulls.decorator import get_paywall_config
from vaulls.settlement import log_settlement

logger = logging.getLogger(__name__)


def _discover_paywalled_routes(app: FastAPI) -> dict[str, dict[str, Any]]:
    """Scan the FastAPI app for routes whose handler has ``__vaulls__``."""
    cfg = get_config()
    routes: dict[str, dict[str, Any]] = {}

    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue

        pw = get_paywall_config(endpoint)
        if pw is None:
            continue

        # Build route key like "POST /tools/my-tool"
        methods = getattr(route, "methods", set())
        path = getattr(route, "path", "")
        network = pw.network or cfg.network

        for method in methods:
            route_key = f"{method} {path}"
            routes[route_key] = {
                "accepts": {
                    "scheme": "exact",
                    "payTo": cfg.pay_to,
                    "price": f"${pw.price}" if not pw.price.startswith("$") else pw.price,
                    "network": cfg.chain_id(network),
                },
                "description": pw.description or f"Paywalled tool: {path}",
            }

    return routes


def vaulls_middleware(
    app: FastAPI,
    facilitator: HTTPFacilitatorClient | None = None,
    server: x402ResourceServer | None = None,
) -> FastAPI:
    """Add x402 payment middleware to a FastAPI app.

    Scans the app for ``@paywall``-decorated route handlers and
    configures x402 middleware to gate those routes.

    Args:
        app: The FastAPI application.
        facilitator: Optional custom facilitator client.
        server: Optional custom x402 resource server (useful for testing).

    Returns:
        The same ``app``, with middleware added.
    """
    cfg = get_config()

    if not cfg.pay_to:
        raise ValueError(
            "VAULLS pay_to wallet not configured. "
            "Call vaulls.configure(pay_to='0x...') or set VAULLS_PAY_TO env var."
        )

    routes = _discover_paywalled_routes(app)
    if not routes:
        logger.warning("No @paywall-decorated routes found. Middleware has nothing to gate.")
        return app

    if server is None:
        facilitator = facilitator or HTTPFacilitatorClient({"url": cfg.facilitator_url})
        server = x402ResourceServer(facilitator)
        chain_id = cfg.chain_id()
        server.register(chain_id, ExactEvmServerScheme())

    mw = payment_middleware(routes, server, sync_facilitator_on_start=False)

    @app.middleware("http")
    async def _vaulls_x402(request: Request, call_next):
        start = time.perf_counter()
        response = await mw(request, call_next)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Log settlement on successful paid requests
        if response.status_code < 400 and "payment-response" in response.headers:
            _log_from_response(request, response, elapsed_ms)

        return response

    logger.info("VAULLS middleware active — gating %d route(s)", len(routes))
    for route_key, route_cfg in routes.items():
        logger.info(
            "  %s → %s %s",
            route_key,
            route_cfg["accepts"]["price"],
            route_cfg["accepts"]["network"],
        )

    return app


def _log_from_response(request: Request, response: Any, elapsed_ms: float) -> None:
    """Extract settlement details from x402 response headers and log them."""
    try:
        raw = response.headers.get("payment-response", "")
        if not raw:
            return
        settlement = json.loads(base64.b64decode(raw))
        log_settlement(
            tool=f"{request.method} {request.url.path}",
            price=settlement.get("amount", "unknown"),
            payer=settlement.get("payer", "unknown"),
            tx_hash=settlement.get("transaction", "unknown"),
            network=settlement.get("network", "unknown"),
            latency_ms=elapsed_ms,
        )
    except Exception:
        logger.exception("Failed to log settlement")
