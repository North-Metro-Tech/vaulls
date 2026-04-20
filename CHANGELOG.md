# Changelog

## 0.3.0

Fixes the critical FastMCP paywall bypass (NOR-295): `@paywall` now enforces payment on FastMCP HTTP transport, not just on direct FastAPI routes.

### Bug Fixes

- **FastMCP `/mcp` paywall enforcement** — `vaulls_mcp_setup()` was pricing-discovery only; every `tools/call` returned 200 regardless of `@paywall` configuration. Fixed by adding `VaullsMCPMiddleware` and `vaulls_mcp_enforcement_app()`.

### New

- **`VaullsMCPMiddleware`** — raw ASGI middleware that intercepts `POST /mcp` JSON-RPC requests, identifies the target tool by `params.name`, and gates paywalled tools behind x402 payment verification before FastMCP dispatches the call.
- **`vaulls_mcp_enforcement_app(mcp)`** — wraps a FastMCP instance with the enforcement middleware and returns an ASGI app ready for `uvicorn.run()`. Supports free-tier metering, settlement logging, and multi-network configuration.
- `vaulls_mcp_setup()` remains unchanged — backwards-compatible for stdio transport (pricing discovery only).

### Usage

```python
from vaulls.integrations.mcp import vaulls_mcp_enforcement_app
import uvicorn

app = vaulls_mcp_enforcement_app(mcp)
uvicorn.run(app, host="0.0.0.0", port=8080)
```

## 0.2.0

Base mainnet verified. VAULLS now works end-to-end on production Base with real USDC settlement.

### Features

- **Coinbase CDP facilitator** — default facilitator migrated from x402.org to `https://api.cdp.coinbase.com/platform/v2/x402`
- **ES256 / EdDSA JWT authentication** — CDP Bearer tokens signed with per-request JWTs (PEM EC P-256 or base64 Ed25519 keys auto-detected)
- **Mainnet smoke test** — `examples/smoke_test.py` proves end-to-end payment flow on Base mainnet
- **`[cdp]` extra** — `pip install vaulls[cdp]` pulls in `PyJWT[crypto]` for facilitator auth

### Verified

Real $0.25 USDC payment settled on Base mainnet:
https://basescan.org/tx/0xbd4084737f7b54b5f96af23195010c1851c1b2bfff8cf0b77b169bd199068811

## 0.1.0

First public release of VAULLS — a pip-installable SDK that adds x402 payments to MCP servers.

### Features

- **`@paywall` decorator** — attach pricing metadata to any tool function with `@paywall(price="0.05")`
- **FastAPI integration** — middleware that gates routes behind x402 payment verification
- **MCP (FastMCP) integration** — enriches tool descriptions with pricing metadata
- **Free-tier metering** — `@paywall(free_calls=10)` gives callers N free calls before requiring payment
- **Settlement logging** — opt-in JSONL file logging and/or custom callback with configurable retry and exponential backoff
- **Circuit breaker** — opt-in protection against facilitator outages (fails fast with 503 + Retry-After)
- **Rate limiter** — opt-in per-caller token bucket rate limiting (returns 429 + Retry-After)
- **Redis-backed metering** — optional persistent metering via `pip install vaulls[redis]`
- **Multi-network support** — Base mainnet, Base Sepolia, and custom EVM chains
- **Pricing discovery** — `GET /vaulls/pricing` lists all paywalled tools and their prices
- **Health endpoint** — `GET /vaulls/health` with optional deep facilitator check
- **Agent-friendly 402 responses** — structured JSON body with step-by-step payment guidance
- **Structured logging** — `VaullsEvent` enum with optional metrics callback for Prometheus/StatsD/Datadog
- **Dataclass validation** — `__post_init__` checks on config (wallet format, URL scheme, price format)
- **Configurable facilitator timeout** — default 30s, configurable via code or env var
- **Coinbase CDP facilitator** — default facilitator is Coinbase CDP with API key authentication (replaces x402.org testnet facilitator)
