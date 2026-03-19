"""MCP (FastMCP) integration for VAULLS.

Enriches ``@paywall``-decorated MCP tool descriptions with pricing
metadata so agents can discover costs before calling tools.

Usage::

    from mcp.server.fastmcp import FastMCP
    from vaulls import configure, paywall
    from vaulls.integrations.mcp import vaulls_mcp_setup

    mcp = FastMCP("my-server")
    configure(pay_to="0x...")

    @mcp.tool()
    @paywall(price="0.05")
    def my_tool(query: str) -> str:
        return "paid result"

    # Enrich tool descriptions with pricing info
    vaulls_mcp_setup(mcp)

.. note::

    MCP tool execution over stdio does not use HTTP, so the x402
    402-response flow works differently than in FastAPI. For MCP
    servers using SSE/HTTP transport, the FastAPI integration handles
    the payment gate. For stdio transport, pricing metadata is
    embedded in tool descriptions so agents know what to expect,
    and the payment verification happens at the transport layer.

    This integration focuses on **pricing discovery** — making sure
    agents see the cost *before* calling a tool.
"""

from __future__ import annotations

import logging
from typing import Any

from vaulls.config import get_config
from vaulls.decorator import get_paywall_config

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
