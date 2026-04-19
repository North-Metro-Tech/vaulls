# Changelog

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
