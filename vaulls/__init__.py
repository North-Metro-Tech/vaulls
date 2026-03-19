"""VAULLS — Value-Wall Monetisation Layer for MCP Tools.

Add x402 payments to your MCP server in one line:

    from vaulls import paywall

    @mcp.tool()
    @paywall(price="0.05", asset="USDC", network="base")
    def my_tool(query: str) -> str:
        return "this cost $0.05"
"""

from vaulls.config import configure
from vaulls.decorator import paywall
from vaulls.settlement import enable_settlement_log

__all__ = ["configure", "paywall", "enable_settlement_log"]
__version__ = "0.3.0"
