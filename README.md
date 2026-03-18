# VAULLS

**Value-Wall Monetisation Layer for MCP Tools**

VAULLS is a payment gateway that lets you monetise MCP tools using the [x402 payment protocol](https://x402.org) and USDC on Base.

## Quickstart

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure your wallet
cp .env.example .env
# Edit .env and set VAULLS_PAY_TO to your Base Sepolia wallet address

# Run the server
uvicorn src.server:app --reload
```

## Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

## Stack

- **Runtime:** Python (FastAPI)
- **Payment:** x402 protocol (EIP-712 signatures)
- **Settlement:** Base Sepolia (USDC) → Base mainnet
- **Discovery:** MCP (Model Context Protocol)
