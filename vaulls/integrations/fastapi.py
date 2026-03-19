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
from fastapi.responses import JSONResponse
from x402 import x402ResourceServer
from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import ExactEvmServerScheme

from vaulls.config import get_config
from vaulls.decorator import get_paywall_config
from vaulls.metering import get_meter
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

        methods = getattr(route, "methods", set())
        path = getattr(route, "path", "")

        # Resolve network(s) — use first network for primary x402 config
        networks = pw.networks_list() or [cfg.network]
        primary_network = networks[0]

        for method in methods:
            route_key = f"{method} {path}"
            routes[route_key] = {
                "accepts": {
                    "scheme": "exact",
                    "payTo": cfg.pay_to,
                    "price": f"${pw.price}" if not pw.price.startswith("$") else pw.price,
                    "network": cfg.chain_id(primary_network),
                },
                "description": pw.description or f"Paywalled tool: {path}",
            }

    return routes


def _build_free_call_routes(app: FastAPI) -> dict[str, tuple[str, int]]:
    """Map route paths to (tool_name, free_calls) for metering."""
    free_routes: dict[str, tuple[str, int]] = {}

    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        pw = get_paywall_config(endpoint)
        if pw is None or pw.free_calls <= 0:
            continue

        path = getattr(route, "path", "")
        tool_name = getattr(endpoint, "__name__", path)
        free_routes[path] = (tool_name, pw.free_calls)

    return free_routes


def _pricing_endpoint_factory(app: FastAPI) -> None:
    """Add a GET /vaulls/pricing endpoint that lists all paywalled tools."""

    @app.get("/vaulls/pricing")
    def vaulls_pricing():
        """Discover pricing for all paywalled tools on this server."""
        cfg = get_config()
        tools = []

        for route in app.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            pw = get_paywall_config(endpoint)
            if pw is None:
                continue

            path = getattr(route, "path", "")
            methods = list(getattr(route, "methods", set()))
            networks = pw.networks_list() or [cfg.network]

            tool_info: dict[str, Any] = {
                "path": path,
                "methods": methods,
                "price": pw.price,
                "asset": pw.asset,
                "networks": networks,
                "pay_to": cfg.pay_to,
                "protocol": "x402",
            }
            if pw.description:
                tool_info["description"] = pw.description
            if pw.free_calls > 0:
                tool_info["free_calls"] = pw.free_calls

            tools.append(tool_info)

        return {
            "server": app.title or "VAULLS-enabled server",
            "tools": tools,
            "payment_protocol": "x402",
            "facilitator": cfg.facilitator_url,
        }


def vaulls_middleware(
    app: FastAPI,
    facilitator: HTTPFacilitatorClient | None = None,
    server: x402ResourceServer | None = None,
) -> FastAPI:
    """Add x402 payment middleware to a FastAPI app.

    Scans the app for ``@paywall``-decorated route handlers and
    configures x402 middleware to gate those routes. Also adds:

    - ``GET /vaulls/pricing`` — pricing discovery endpoint
    - Free-tier metering for tools with ``free_calls > 0``
    - Agent-friendly 402 error bodies

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

    # Add pricing discovery endpoint
    _pricing_endpoint_factory(app)

    routes = _discover_paywalled_routes(app)
    if not routes:
        logger.warning("No @paywall-decorated routes found. Middleware has nothing to gate.")
        return app

    # Build free-call route map
    free_routes = _build_free_call_routes(app)
    meter = get_meter()

    if server is None:
        facilitator = facilitator or HTTPFacilitatorClient({"url": cfg.facilitator_url})
        server = x402ResourceServer(facilitator)

        # Register all networks used by paywalled routes
        registered: set[str] = set()
        for route in app.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            pw = get_paywall_config(endpoint)
            if pw is None:
                continue
            networks = pw.networks_list() or [cfg.network]
            for net in networks:
                chain = cfg.chain_id(net)
                if chain not in registered:
                    server.register(chain, ExactEvmServerScheme())
                    registered.add(chain)

        # Ensure at least the default network is registered
        default_chain = cfg.chain_id()
        if default_chain not in registered:
            server.register(default_chain, ExactEvmServerScheme())

    mw = payment_middleware(routes, server, sync_facilitator_on_start=False)

    @app.middleware("http")
    async def _vaulls_x402(request: Request, call_next):
        path = request.url.path

        # Free-tier bypass: if this route has free_calls, check the meter
        if path in free_routes:
            tool_name, free_limit = free_routes[path]
            # Use client IP as caller ID (best effort without wallet)
            caller_id = request.client.host if request.client else "unknown"
            if meter.is_free(tool_name, caller_id, free_limit):
                meter.record_call(tool_name, caller_id)
                response = await call_next(request)
                return response

        start = time.perf_counter()
        response = await mw(request, call_next)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Log settlement on successful paid requests
        if response.status_code < 400 and "payment-response" in response.headers:
            _log_from_response(request, response, elapsed_ms)

        # Enrich 402 responses with agent-friendly guidance
        if response.status_code == 402:
            return _enrich_402_response(request, response)

        return response

    logger.info("VAULLS middleware active — gating %d route(s)", len(routes))
    for route_key, route_cfg in routes.items():
        free_info = ""
        # Check if this route has free calls
        for fp, (_, fc) in free_routes.items():
            if fp in route_key:
                free_info = f" ({fc} free calls)"
                break
        logger.info(
            "  %s → %s %s%s",
            route_key,
            route_cfg["accepts"]["price"],
            route_cfg["accepts"]["network"],
            free_info,
        )

    return app


def _enrich_402_response(request: Request, response: Any) -> JSONResponse:
    """Wrap the 402 response with agent-friendly guidance in the body."""
    cfg = get_config()

    guidance = {
        "error": "payment_required",
        "message": (
            f"This tool requires payment via the x402 protocol. "
            f"Your AI agent needs a Coinbase Smart Wallet with USDC on Base to proceed."
        ),
        "how_to_pay": {
            "protocol": "x402",
            "step_1": "Read the PAYMENT-REQUIRED header (base64-encoded JSON) for payment details",
            "step_2": "Sign an EIP-712 payment message with your wallet",
            "step_3": "Retry the request with the signed payment in the X-PAYMENT header",
        },
        "pay_to": cfg.pay_to,
        "facilitator": cfg.facilitator_url,
        "docs": "https://x402.org",
    }

    # Preserve the original x402 headers
    headers = dict(response.headers)

    return JSONResponse(
        status_code=402,
        content=guidance,
        headers=headers,
    )


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
