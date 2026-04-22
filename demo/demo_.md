# **VAULLS Live Demo:** **The $0.01 Free Money MCP**

This document is a live demonstration of the **VAULLS** package, showcasing how to seamlessly add onchain Web3 paywalls to a FastMCP server.

To prove it works in production, I’ve deployed a live MCP server on Google Cloud Run using the vaulls\_mcp\_enforcement\_app middleware. It features a free health check tool, and a premium tool that costs exactly 0.01 USDC on Base Mainnet to return “something unexpectedly valuable".

## **🚀 See it in action (No wallet required)**

You don't need a wallet, private keys, or a Python client to see the middleware working. You can verify the `VAULLS` 402 payment protocol intercepting requests right from your terminal.

### **1\. The Free Tool (Passes Through)**

Call the `ping` tool. Because it has no `@paywall` decorator, the VAULLS middleware lets it pass through instantly, returning a `200 OK`.

curl -X POST [https://vaulls-demo-server-43373392668.us-central1.run.app/mcp](https://vaulls-demo-server-43373392668.us-central1.run.app/mcp) \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ping", "arguments": {}}}'

### **2\. The Paywalled Tool (402 Challenge)**

Now try to call the `free_money` tool without paying. The server will intercept the request and reject it with an HTTP `402 Payment Required` status, returning a `payment-required` header with the cryptographic settlement challenge.

curl -X POST [https://vaulls-demo-server-43373392668.us-central1.run.app/mcp](https://vaulls-demo-server-43373392668.us-central1.run.app/mcp) \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "free_money", "arguments": {}}}' -i

## **🛠 How it works under the hood**

Check out `server/server.py` in this repo. Adding the paywall was as simple as decorating the FastMCP tool:

```py
@mcp.tool()
@paywall(price="0.01", asset="USDC")
def free_money() -> str:
    """Returns something unexpectedly valuable."""
    return (
        # ...
    )
```

The server is configured with my dev wallet on Base Mainnet. When a client correctly signs an x402 transaction satisfying the 402 challenge header, the middleware verifies the onchain settlement and releases the payload.

*Note: The live server is rate-limited to 80 calls per minute to prevent abuse. Please be kind to the endpoint\!*
