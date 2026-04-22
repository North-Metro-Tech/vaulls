import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from vaulls import configure, paywall
from vaulls.integrations.mcp import vaulls_mcp_enforcement_app

load_dotenv(Path(__file__).resolve().parent / ".env")

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

pay_to = os.environ.get("PAY_TO", "").strip()
if not pay_to:
    sys.exit("[FATAL] PAY_TO env var is required. Set it to a real Base mainnet payout wallet.")
if pay_to.lower() == ZERO_ADDRESS:
    sys.exit("[FATAL] PAY_TO is the zero address; USDC sent there is burned permanently.")

network = os.environ.get("NETWORK", "base")
configure(pay_to=pay_to, network=network)

mcp = FastMCP("vaulls-qa-server", host="0.0.0.0")


@mcp.tool()
def ping() -> str:
    """Free health-check tool. Must pass through the middleware without a 402."""
    return "pong"


# Illustrative copy of the live demo server.
# Payload omitted — live version runs from a private repo.

@mcp.tool()
@paywall(price="0.01", asset="USDC")
def free_money() -> str:
    """Returns something unexpectedly valuable."""
    return (
        " (>'.')> " # insert your payload here
    )


MAX_BODY_BYTES = 64 * 1024


class MaxBodySizeMiddleware:
    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared > self.max_bytes:
                    await send({
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    })
                    await send({"type": "http.response.body", "body": b"Payload Too Large"})
                    return
                break

        await self.app(scope, receive, send)


app = MaxBodySizeMiddleware(vaulls_mcp_enforcement_app(mcp), max_bytes=MAX_BODY_BYTES)


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8080))
    print(f"[INFO] Starting vaulls-qa-server on {host}:{port} (network={network}, pay_to={pay_to})")
    uvicorn.run(app, host=host, port=port)
