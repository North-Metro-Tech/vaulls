"""MCP (FastMCP) integration for VAULLS.

Provides two levels of integration:

1. **Pricing discovery** (``vaulls_mcp_setup``): enriches ``@paywall``-decorated
   tool descriptions with pricing metadata so agents can see costs before calling.

2. **Payment enforcement** (``vaulls_mcp_enforcement_app``): wraps the FastMCP
   HTTP ASGI app with x402 middleware that intercepts ``tools/call`` JSON-RPC
   requests and gates paywalled tools behind real on-chain payment.

Usage — stdio (pricing discovery only)::

    from mcp.server.fastmcp import FastMCP
    from vaulls import configure, paywall
    from vaulls.integrations.mcp import vaulls_mcp_setup

    mcp = FastMCP("my-server")
    configure(pay_to="0x...")

    @mcp.tool()
    @paywall(price="0.05")
    def my_tool(query: str) -> str:
        return "paid result"

    vaulls_mcp_setup(mcp)
    mcp.run()  # stdio

Usage — HTTP (full enforcement)::

    from vaulls.integrations.mcp import vaulls_mcp_enforcement_app
    import uvicorn

    vaulls_mcp_setup(mcp)           # optional: enriches descriptions too
    app = vaulls_mcp_enforcement_app(mcp)
    uvicorn.run(app, host="0.0.0.0", port=8080)
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from x402 import x402ResourceServer
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import ExactEvmServerScheme

from vaulls.config import get_config
from vaulls.decorator import get_paywall_config
from vaulls.logging import VaullsEvent, log_event
from vaulls.metering import get_meter
from vaulls.settlement import log_settlement

logger = logging.getLogger(__name__)


def _build_pricing_block(
    price: str,
    asset: str,
    networks: list[str],
    pay_to: str,
    free_calls: int = 0,
) -> str:
    """Build a human+agent readable pricing block for tool descriptions."""
    networks_str = ", ".join(networks) if networks else "base-sepolia"
    lines = [
        f"\n\n---",
        f"PAYMENT: ${price} {asset} on {networks_str} via x402 protocol.",
        f"Pay to: {pay_to}",
    ]
    if free_calls > 0:
        lines.append(f"Free tier: first {free_calls} calls are free.")
    lines.append(f"Docs: https://x402.org")
    return "\n".join(lines)


def vaulls_mcp_setup(mcp: Any) -> None:
    """Enrich a FastMCP server's tool descriptions with VAULLS pricing.

    Iterates over registered tools and appends pricing metadata to their
    descriptions for any tool whose underlying function has ``@paywall``.

    Args:
        mcp: A ``FastMCP`` server instance.
    """
    cfg = get_config()

    # FastMCP stores tools in _tool_manager._tools (dict of name -> Tool)
    tool_manager = getattr(mcp, "_tool_manager", None)
    if tool_manager is None:
        logger.warning("Could not access FastMCP tool manager. Pricing metadata not added.")
        return

    tools = getattr(tool_manager, "_tools", {})
    enriched = 0

    for name, tool in tools.items():
        # FastMCP Tool wraps the original function
        fn = getattr(tool, "fn", None)
        if fn is None:
            continue

        pw = get_paywall_config(fn)
        if pw is None:
            continue

        networks = pw.networks_list() or [cfg.network]
        pricing_block = _build_pricing_block(
            price=pw.price,
            asset=pw.asset,
            networks=networks,
            pay_to=cfg.pay_to,
            free_calls=pw.free_calls,
        )

        # Append pricing to the tool's description
        if hasattr(tool, "description") and tool.description:
            tool.description += pricing_block
        else:
            tool.description = pricing_block.strip()

        enriched += 1
        logger.info("VAULLS pricing added to tool '%s': $%s %s", name, pw.price, pw.asset)

    if enriched:
        logger.info("VAULLS enriched %d MCP tool(s) with pricing metadata", enriched)
    else:
        logger.warning("No @paywall-decorated tools found in MCP server.")


def _get_fastmcp_http_app(mcp: Any) -> Any:
    """Extract the HTTP ASGI app from a FastMCP instance.

    Tries multiple attribute/method paths to support different versions of
    the ``mcp`` package and standalone ``fastmcp`` package.

    Raises:
        RuntimeError: If no ASGI app can be extracted.
    """
    # mcp package >=1.9 — streamable HTTP transport
    if hasattr(mcp, "streamable_http_app"):
        try:
            return mcp.streamable_http_app()
        except Exception:
            pass

    # alternate method name used in some mcp package versions
    if hasattr(mcp, "http_app"):
        try:
            return mcp.http_app()
        except Exception:
            pass

    # standalone fastmcp package exposes .app directly
    if hasattr(mcp, "app"):
        app = mcp.app
        if callable(app):
            return app

    raise RuntimeError(
        "Could not extract HTTP ASGI app from FastMCP instance. "
        "Ensure you are using mcp>=1.9 (mcp.server.fastmcp.FastMCP) or "
        "the standalone fastmcp package. "
        "Call mcp.run(transport='http') to verify HTTP transport is supported."
    )


def _build_mcp_routes(paywalled_tools: dict[str, Any], cfg: Any) -> dict[str, dict[str, Any]]:
    """Build virtual x402 route config for paywalled MCP tools.

    Uses virtual paths ``POST /mcp/tools/{name}`` so the x402
    ``payment_middleware`` can match and gate each tool independently.
    """
    routes: dict[str, dict[str, Any]] = {}
    for name, pw in paywalled_tools.items():
        networks = pw.networks_list() or [cfg.network]
        primary_network = networks[0]
        route_key = f"POST /mcp/tools/{name}"
        routes[route_key] = {
            "accepts": {
                "scheme": "exact",
                "payTo": cfg.pay_to,
                "price": f"${pw.price}" if not pw.price.startswith("$") else pw.price,
                "network": cfg.chain_id(primary_network),
            },
            "description": pw.description or f"MCP tool: {name}",
        }
    return routes


class VaullsMCPMiddleware:
    """Raw ASGI middleware that gates paywalled FastMCP tools via x402.

    Intercepts ``POST /mcp`` requests, parses the JSON-RPC body, and for
    any ``tools/call`` targeting a ``@paywall``-decorated tool either:

    - Returns a ``402 Payment Required`` response (no valid ``X-PAYMENT``), or
    - Verifies payment via the x402 facilitator and forwards to FastMCP.

    Non-``tools/call`` methods (e.g. ``initialize``, ``tools/list``) and
    calls to unpaywall tools pass through without inspection.
    """

    def __init__(
        self,
        app: Any,
        paywalled_tools: dict[str, Any],
        paywalled_routes: dict[str, dict[str, Any]],
        free_routes: dict[str, tuple[str, int]],
        server: x402ResourceServer,
        cfg: Any,
    ) -> None:
        self._app = app
        self._paywalled_tools = paywalled_tools
        self._free_routes = free_routes
        self._cfg = cfg
        self._mw = payment_middleware(paywalled_routes, server, sync_facilitator_on_start=False)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        if path != "/mcp" or method != "POST":
            await self._app(scope, receive, send)
            return

        # Buffer the full request body so we can re-replay it downstream
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            chunk = await receive()
            body_chunks.append(chunk.get("body", b""))
            more_body = chunk.get("more_body", False)
        body = b"".join(body_chunks)

        def _make_receive(b: bytes) -> Any:
            consumed = False

            async def _receive() -> dict:
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": b, "more_body": False}
                return {"type": "http.disconnect"}

            return _receive

        # Parse JSON-RPC — pass through anything we can't read
        try:
            rpc = json.loads(body)
        except Exception:
            await self._app(scope, _make_receive(body), send)
            return

        if rpc.get("method") != "tools/call":
            await self._app(scope, _make_receive(body), send)
            return

        tool_name: str = (rpc.get("params") or {}).get("name", "")
        if tool_name not in self._paywalled_tools:
            await self._app(scope, _make_receive(body), send)
            return

        # Free-tier bypass: skip payment for callers within their free quota
        pw = self._paywalled_tools[tool_name]
        if pw.free_calls > 0:
            caller_ip = (scope.get("client") or ("unknown", 0))[0]
            meter = get_meter()
            if meter.is_free(tool_name, caller_ip, pw.free_calls):
                meter.record_call(tool_name, caller_ip)
                log_event(VaullsEvent.FREE_CALL_USED, tool=tool_name, caller=caller_ip)
                await self._app(scope, _make_receive(body), send)
                return

        # Build a virtual-path request for x402 route matching
        virtual_path = f"/mcp/tools/{tool_name}"
        virtual_scope = {**scope, "path": virtual_path, "raw_path": virtual_path.encode()}
        virtual_request = Request(virtual_scope, _make_receive(body))

        async def mcp_call_next(_req: Request) -> StreamingResponse:
            """After payment passes, forward to FastMCP with the original path.

            Returns a StreamingResponse so that x402 payment_middleware can
            iterate over body_iterator to attach the settlement header.
            """
            status_code = 200
            resp_headers: list[tuple[bytes, bytes]] = []
            resp_body_parts: list[bytes] = []

            async def collect_send(message: dict) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    resp_headers.extend(message.get("headers", []))
                elif message["type"] == "http.response.body":
                    resp_body_parts.append(message.get("body", b""))

            start = time.perf_counter()
            await self._app(scope, _make_receive(body), collect_send)
            elapsed_ms = (time.perf_counter() - start) * 1000

            resp_body = b"".join(resp_body_parts)
            headers_dict = {
                k.decode(errors="replace"): v.decode(errors="replace")
                for k, v in resp_headers
                # Drop content-length — StreamingResponse will recalculate it
                if k.lower() != b"content-length"
            }

            # Log settlement if the MCP response carried a payment-response header
            pr_header = headers_dict.get("payment-response", "")
            if pr_header and status_code < 400:
                try:
                    settlement = json.loads(base64.b64decode(pr_header))
                    log_settlement(
                        tool=f"mcp:{tool_name}",
                        price=settlement.get("amount", "unknown"),
                        payer=settlement.get("payer", "unknown"),
                        tx_hash=settlement.get("transaction", "unknown"),
                        network=settlement.get("network", "unknown"),
                        latency_ms=elapsed_ms,
                    )
                except Exception:
                    pass

            # StreamingResponse exposes body_iterator, which x402 payment_middleware
            # iterates to attach the settlement header before returning to the client.
            async def _body_iter():
                yield resp_body

            return StreamingResponse(
                content=_body_iter(),
                status_code=status_code,
                headers=headers_dict,
                media_type=headers_dict.get("content-type", "application/json"),
            )

        log_event(VaullsEvent.PAYMENT_REQUIRED, path=f"/mcp[{tool_name}]")
        response = await self._mw(virtual_request, mcp_call_next)

        # Ship the response back via raw ASGI
        await response(scope, _make_receive(body), send)


def vaulls_mcp_enforcement_app(
    mcp: Any,
    server: x402ResourceServer | None = None,
) -> Any:
    """Wrap a FastMCP HTTP server with x402 payment enforcement.

    Builds the payment gating layer and returns an ASGI app that:

    - Intercepts ``tools/call`` JSON-RPC requests on ``POST /mcp``
    - Returns ``402 Payment Required`` for paywalled tools without payment
    - Verifies and settles payment for requests that include ``X-PAYMENT``
    - Passes all other requests through to FastMCP unchanged

    Args:
        mcp: A ``FastMCP`` server instance with ``@paywall``-decorated tools.
        server: Optional custom ``x402ResourceServer`` (useful for testing).

    Returns:
        An ASGI application to run with uvicorn or any ASGI server.

    Raises:
        ValueError: If ``pay_to`` wallet is not configured.
        RuntimeError: If the FastMCP HTTP app cannot be extracted.

    Example::

        app = vaulls_mcp_enforcement_app(mcp)
        uvicorn.run(app, host="0.0.0.0", port=8080)
    """
    from vaulls._cdp_jwt import build_cdp_jwt  # local import — optional dep
    from x402.http.facilitator_client_base import CreateHeadersAuthProvider

    cfg = get_config()

    if not cfg.pay_to:
        raise ValueError(
            "VAULLS pay_to wallet not configured. "
            "Call vaulls.configure(pay_to='0x...') or set VAULLS_PAY_TO env var."
        )

    # Enrich tool descriptions (pricing discovery)
    vaulls_mcp_setup(mcp)

    # Build paywalled tool registry from FastMCP tool manager
    tool_manager = getattr(mcp, "_tool_manager", None)
    tools_dict = getattr(tool_manager, "_tools", {}) if tool_manager else {}

    paywalled_tools: dict[str, Any] = {}
    for name, tool in tools_dict.items():
        fn = getattr(tool, "fn", None)
        if fn is None:
            continue
        pw = get_paywall_config(fn)
        if pw is not None:
            paywalled_tools[name] = pw

    if not paywalled_tools:
        logger.warning(
            "vaulls_mcp_enforcement_app: no @paywall-decorated tools found. "
            "Enforcement middleware will pass all requests through."
        )

    # Virtual x402 routes — one per paywalled tool
    paywalled_routes = _build_mcp_routes(paywalled_tools, cfg)

    # Free-tier route map
    free_routes: dict[str, tuple[str, int]] = {
        name: (name, pw.free_calls)
        for name, pw in paywalled_tools.items()
        if pw.free_calls > 0
    }

    # Build x402 resource server if not injected
    if server is None:
        # CDP JWT auth — only when keys are present (production path)
        auth_provider: CreateHeadersAuthProvider | None = None
        if cfg.cdp_api_key_id and cfg.cdp_api_key_secret:
            key_id = cfg.cdp_api_key_id
            key_secret = cfg.cdp_api_key_secret
            base_url = cfg.facilitator_url.rstrip("/")

            def _create_headers() -> dict[str, dict[str, str]]:
                return {
                    "verify": {"Authorization": f"Bearer {build_cdp_jwt(key_id, key_secret, 'POST', f'{base_url}/verify')}"},
                    "settle": {"Authorization": f"Bearer {build_cdp_jwt(key_id, key_secret, 'POST', f'{base_url}/settle')}"},
                    "supported": {"Authorization": f"Bearer {build_cdp_jwt(key_id, key_secret, 'GET', f'{base_url}/supported')}"},
                }

            auth_provider = CreateHeadersAuthProvider(_create_headers)

        facilitator = HTTPFacilitatorClient(
            FacilitatorConfig(
                url=cfg.facilitator_url,
                timeout=cfg.facilitator_timeout,
                auth_provider=auth_provider,
            )
        )
        server = x402ResourceServer(facilitator)

        # Register all networks used by paywalled tools
        registered: set[str] = set()
        for pw in paywalled_tools.values():
            for net in (pw.networks_list() or [cfg.network]):
                chain = cfg.chain_id(net)
                if chain not in registered:
                    server.register(chain, ExactEvmServerScheme())
                    registered.add(chain)

        default_chain = cfg.chain_id()
        if default_chain not in registered:
            server.register(default_chain, ExactEvmServerScheme())

    server.initialize()

    fastmcp_asgi = _get_fastmcp_http_app(mcp)

    middleware = VaullsMCPMiddleware(
        app=fastmcp_asgi,
        paywalled_tools=paywalled_tools,
        paywalled_routes=paywalled_routes,
        free_routes=free_routes,
        server=server,
        cfg=cfg,
    )

    logger.info(
        "VAULLS MCP enforcement active — gating %d tool(s) on POST /mcp",
        len(paywalled_tools),
    )
    for name, pw in paywalled_tools.items():
        networks = pw.networks_list() or [cfg.network]
        free_info = f" ({pw.free_calls} free calls)" if pw.free_calls > 0 else ""
        logger.info("  tools/call[%s] → $%s %s on %s%s", name, pw.price, pw.asset, networks[0], free_info)

    return middleware
