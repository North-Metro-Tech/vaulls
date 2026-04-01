# Changelog

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
