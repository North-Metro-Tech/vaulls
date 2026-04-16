"""Example: FastMCP server with VAULLS pricing metadata.

This shows how an MCP developer using the standard MCP Python SDK
would add pricing info to their tools via VAULLS.

Run:
    pip install "vaulls[mcp]"
    export VAULLS_PAY_TO=0xYourWalletAddress
    export VAULLS_CDP_API_KEY_ID=your_key_id
    export VAULLS_CDP_API_KEY_SECRET=your_key_secret
    python examples/fastmcp_server.py
"""

from mcp.server.fastmcp import FastMCP

import vaulls
from vaulls import paywall
from vaulls.integrations.mcp import vaulls_mcp_setup

# 1. Configure VAULLS
vaulls.configure(network="base-sepolia")

# 2. Create your MCP server as normal
mcp = FastMCP("my-tools")


# 3. Free tools — no change
@mcp.tool()
def ping() -> str:
    """Check if the server is alive."""
    return "pong"


# 4. Paid tools — add @paywall for pricing metadata
@mcp.tool()
@paywall(price="0.05", description="Weather forecast lookup")
def get_weather(city: str) -> str:
    """Get the weather forecast for a city."""
    return f"Weather in {city}: Sunny, 24C"


@mcp.tool()
@paywall(
    price="0.15",
    description="Deep research query",
    network=["base", "base-sepolia"],
)
def deep_research(topic: str) -> str:
    """Deep research on a topic — costs $0.15. Accepts Base or Base Sepolia."""
    return f"In-depth analysis of {topic}: [detailed results]"


# 5. Freemium tool — first 10 calls free
@mcp.tool()
@paywall(price="0.01", description="Quick fact check", free_calls=10)
def fact_check(claim: str) -> str:
    """Check if a claim is accurate. First 10 calls free."""
    return f"Fact check for '{claim}': Verified"


# 6. Enrich tool descriptions with VAULLS pricing
vaulls_mcp_setup(mcp)

if __name__ == "__main__":
    mcp.run()
