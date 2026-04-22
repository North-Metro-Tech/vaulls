# VAULLS

**Value-Wall Monetisation Layer for MCP Tools**

**Add x402 payments to your MCP server in one line.**

VAULLS is a Python package that lets MCP server developers monetise their tools using the [x402 payment protocol](https://x402.org) and USDC on Base. It's a value wall, not a paywall — your tools are worth paying for, and agents pay because the value is real. Like adding a payment plugin to a WordPress site — you own the server, you set the prices, agents pay to use your tools.

[![Tests](https://github.com/North-Metro-Tech/vaulls/actions/workflows/test.yml/badge.svg)](https://github.com/North-Metro-Tech/vaulls/actions/workflows/test.yml)
[![Mainnet Verified](https://img.shields.io/badge/Base_Mainnet-verified-blue)](https://basescan.org/tx/0xbd4084737f7b54b5f96af23195010c1851c1b2bfff8cf0b77b169bd199068811)

```
                          Your MCP Server
                    ┌────────────────────────┐
                    │                        │
                    │  @paywall(price="0.05") │
                    │  def my_tool(args):     │
                    │      return result      │
                    │                        │
                    │  VAULLS handles:        │
                    │  ├─ 402 responses       │
                    │  ├─ payment verify      │
                    │  ├─ settlement logging  │
                    │  └─ pricing discovery   │
                    └───────────┬────────────┘
                                │
                    Agent calls tool, pays via x402
                                │
                    ┌───────────┴────────────┐
                    │  AI Agent              │
                    │  (Claude, Cursor, etc.) │
                    │  + Coinbase Smart      │
                    │    Wallet with USDC    │
                    └────────────────────────┘
```

## Quickstart

### 1. Install

```bash
pip install "vaulls[fastapi,cdp]"
```

The `[cdp]` extra pulls in `PyJWT[crypto]`, which VAULLS uses to sign the
`Authorization: Bearer` JWT that the Coinbase CDP facilitator requires.
This is needed for both testnet (Base Sepolia) and mainnet (Base).

### 2. Configure

```bash
export VAULLS_PAY_TO=0xYourBaseWalletAddress
export VAULLS_CDP_API_KEY_ID=your_key_id
export VAULLS_CDP_API_KEY_SECRET=your_key_secret
```

Get CDP API keys at [portal.cdp.coinbase.com](https://portal.cdp.coinbase.com).
The secret may be either a PEM-encoded EC P-256 key (signed as ES256) or a
base64-encoded 64-byte Ed25519 key (signed as EdDSA) — VAULLS auto-detects
which one you have.

### 3. Decorate

```python
from fastapi import FastAPI
from vaulls import configure, paywall
from vaulls.integrations.fastapi import vaulls_middleware

app = FastAPI()
configure(pay_to="0xYourWallet")

# Free tool — no change needed
@app.post("/tools/free-lookup")
def free_lookup(data: dict):
    return {"result": "free"}

# Paid tool — one line added
@app.post("/tools/premium-analysis")
@paywall(price="0.10")
def premium_analysis(data: dict):
    return {"analysis": "detailed result", "confidence": 0.95}

# Freemium — first 5 calls free, then paid
@app.post("/tools/quick-check")
@paywall(price="0.02", free_calls=5)
def quick_check(data: dict):
    return {"valid": True}

vaulls_middleware(app)
```

That's it. Run your server and agents can discover prices at `GET /vaulls/pricing`.

## How It Works

```
Agent calls tool ──► 402 Payment Required
                         (x402 payment details in header)
                              │
Agent signs payment ◄─────────┘
with smart wallet
                              │
Agent retries with ───────────┘
X-PAYMENT header
        │
        ▼
Server verifies via facilitator ──► Tool executes ──► Result returned
                                         │
                                    Settlement logged
```

1. **You** own an MCP server with tools you've built
2. **You** `pip install vaulls` and add `@paywall` to the tools you want to monetise
3. **Agents** connect to your MCP server as normal
4. When an agent calls a paywalled tool, it gets a `402` with payment requirements
5. The agent's x402 client signs a USDC payment and retries — your tool executes
6. Settlement happens on Base via the [Coinbase CDP facilitator](https://docs.cdp.coinbase.com/x402/quickstart-for-sellers)

The agent doesn't need to know about VAULLS. It just sees standard x402 payment requirements and responds with a signed payment. Any x402-compatible agent wallet works.

## API Reference

### `@paywall` decorator

```python
from vaulls import paywall

@paywall(
    price="0.05",                          # price in USD
    asset="USDC",                          # payment asset (default: USDC)
    network="base-sepolia",                # or "base" for mainnet
    network=["base", "base-sepolia"],      # accept multiple networks
    description="My premium tool",         # shown in pricing endpoint
    free_calls=10,                         # first N calls free per caller
)
def my_tool(args):
    return result
```

### `configure()`

```python
import vaulls

vaulls.configure(
    pay_to="0xYourWallet",                # your Base wallet address
    network="base-sepolia",               # default network
    cdp_api_key_id="your_key_id",         # CDP API key ID
    cdp_api_key_secret="your_key_secret", # CDP API key secret
)
```

> **Warning:** Never set `pay_to` to the zero address (`0x000...000`). It passes validation but any USDC that settles will be permanently burned. Always use a real wallet address you control.

```python
```

Or use environment variables — no code needed:

| Variable | Description | Default |
|---|---|---|
| `VAULLS_PAY_TO` | Your wallet address | *(required)* |
| `VAULLS_CDP_API_KEY_ID` | CDP API key ID | *(required)* |
| `VAULLS_CDP_API_KEY_SECRET` | CDP API key secret | *(required)* |
| `VAULLS_NETWORK` | `"base-sepolia"` or `"base"` | `base-sepolia` |
| `VAULLS_FACILITATOR_URL` | x402 facilitator URL | Coinbase CDP |

### `enable_settlement_log()`

```python
from vaulls import enable_settlement_log

# Log to JSONL file
enable_settlement_log("settlements.jsonl")

# Log via callback (send to your own DB, webhook, etc.)
enable_settlement_log(callback=lambda entry: print(entry))

# Both
enable_settlement_log("settlements.jsonl", callback=my_logger)
```

Each settlement entry contains:

```json
{
  "timestamp": "2026-03-19T04:00:00.000Z",
  "tool": "POST /tools/premium-analysis",
  "price": "$0.10",
  "payer": "0xAgentWalletAddress",
  "tx_hash": "0x...",
  "network": "eip155:84532",
  "latency_ms": 1.8
}
```

### Pricing Discovery

VAULLS automatically adds `GET /vaulls/pricing` to your FastAPI app:

```json
{
  "server": "My Tool Server",
  "tools": [
    {
      "path": "/tools/premium-analysis",
      "methods": ["POST"],
      "price": "0.10",
      "asset": "USDC",
      "networks": ["base-sepolia"],
      "pay_to": "0xYourWallet",
      "protocol": "x402",
      "description": "Premium data analysis"
    },
    {
      "path": "/tools/quick-check",
      "methods": ["POST"],
      "price": "0.02",
      "asset": "USDC",
      "networks": ["base-sepolia"],
      "pay_to": "0xYourWallet",
      "protocol": "x402",
      "free_calls": 5
    }
  ],
  "payment_protocol": "x402",
  "facilitator": "https://api.cdp.coinbase.com/platform/v2/x402"
}
```

Agents can query this endpoint to discover tool costs before calling anything.

## Integrations

### Compatibility matrix

| Framework | Transport | Enforcement | Discovery |
|---|---|---|---|
| FastAPI | HTTP | ✅ Full x402 enforcement | ✅ `GET /vaulls/pricing` |
| FastMCP | HTTP (`uvicorn`) | ✅ Full x402 enforcement | ✅ Tool descriptions |
| FastMCP | stdio | ❌ Not applicable | ✅ Tool descriptions |

**Enforcement** means the server returns `402 Payment Required` and verifies payment before executing the tool. **Discovery** means agents can see pricing before calling.

### FastAPI

The primary integration. Adds x402 middleware to gate `@paywall`-decorated routes.

```python
from vaulls.integrations.fastapi import vaulls_middleware
vaulls_middleware(app)
```

### MCP Python SDK (FastMCP) — HTTP enforcement

Full x402 payment enforcement over FastMCP's HTTP transport. Use `vaulls_mcp_enforcement_app` instead of `mcp.run()`:

```python
import uvicorn
from mcp.server.fastmcp import FastMCP
from vaulls import configure, paywall
from vaulls.integrations.mcp import vaulls_mcp_enforcement_app

mcp = FastMCP("my-tools")
configure(pay_to="0xYourWallet")

@mcp.tool()
@paywall(price="0.05")
def my_tool(query: str) -> str:
    return "result"

app = vaulls_mcp_enforcement_app(mcp)
uvicorn.run(app, host="0.0.0.0", port=8080)
```

Agents calling `tools/call` on paywalled tools will receive a `402 Payment Required` response with x402 payment details. `initialize`, `tools/list`, and unpaywalled tools pass through untouched.

### MCP Python SDK (FastMCP) — stdio (pricing discovery only)

For stdio transport, VAULLS enriches tool descriptions with pricing metadata so agents see costs in tool listings. Enforcement is not applicable over stdio — use HTTP transport if you need payment gating.

```python
from mcp.server.fastmcp import FastMCP
from vaulls import paywall
from vaulls.integrations.mcp import vaulls_mcp_setup

mcp = FastMCP("my-tools")

@mcp.tool()
@paywall(price="0.05")
def my_tool(query: str) -> str:
    return "result"

vaulls_mcp_setup(mcp)  # adds pricing to tool descriptions
mcp.run()              # stdio
```

## Examples

Working examples in the [`examples/`](examples/) directory:

- **[`fastapi_server.py`](examples/fastapi_server.py)** — FastAPI server with free, paid, and freemium tools. The canonical confirmed-working enforcement reference.
- **[`fastmcp_server.py`](examples/fastmcp_server.py)** — FastMCP server. Run with `--http` for full enforcement, or without for stdio pricing-discovery mode.
- **[`smoke_test.py`](examples/smoke_test.py)** — End-to-end payment flow test against a live server.

Run the FastAPI example:

```bash
export VAULLS_PAY_TO=0xYourWallet
export VAULLS_CDP_API_KEY_ID=your_key_id
export VAULLS_CDP_API_KEY_SECRET=your_key_secret
uvicorn examples.fastapi_server:app --reload
# Visit http://localhost:8000/vaulls/pricing
```

Run the FastMCP example with HTTP enforcement:

```bash
export VAULLS_PAY_TO=0xYourWallet
export VAULLS_CDP_API_KEY_ID=your_key_id
export VAULLS_CDP_API_KEY_SECRET=your_key_secret
python examples/fastmcp_server.py --http
# Agents connect to http://localhost:8080/mcp
```

## Why VAULLS?

**The problem:** MCP servers give AI agents access to powerful tools, but there's no standard way for tool developers to get paid. The x402 protocol solves the payment mechanics, but integrating it requires understanding EIP-712 signatures, facilitator APIs, and middleware patterns.

**The solution:** VAULLS wraps all that complexity into a single decorator. You set a price, VAULLS handles the rest. Your tools, your server, your wallet, your revenue.

**The analogy:** x402 is the payment protocol (like credit card networks). VAULLS is the developer SDK (like Stripe). You don't need to understand the protocol — you just set a price.

## Related Projects

- **[x402](https://docs.cdp.coinbase.com/x402/overview)** — The payment protocol VAULLS builds on
- **[Carbon-Contractors](https://github.com/North-Metro-Tech/carbon-contractors)** — A Human-as-a-Service MCP with x402 baked in (by the same team)
- **[MCP](https://modelcontextprotocol.io)** — Model Context Protocol specification

## Stack

- **Payment:** [x402 protocol](https://x402.org) (EIP-712 signatures)
- **Settlement:** USDC on [Base](https://base.org)
- **Facilitator:** [Coinbase CDP](https://docs.cdp.coinbase.com/x402/quickstart-for-sellers)
- **Integrations:** FastAPI, MCP Python SDK (FastMCP)
- **License:** MIT

## Contributing

VAULLS is open source under the MIT license. Issues and PRs welcome at [github.com/North-Metro-Tech/vaulls](https://github.com/North-Metro-Tech/vaulls).

Built by [North Metro Tech](https://northmetrotech.com.au).
