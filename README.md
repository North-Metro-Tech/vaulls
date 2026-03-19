# VAULLS

**Add x402 payments to your MCP server in one line.**

VAULLS is a Python package that lets MCP server developers monetise their tools using the [x402 payment protocol](https://x402.org) and USDC on Base. Like adding Stripe to a website — but for AI agent tools.

## Quickstart

```bash
pip install "vaulls[fastapi]"
```

```python
from fastapi import FastAPI
from vaulls import configure, paywall
from vaulls.integrations.fastapi import vaulls_middleware

app = FastAPI()
configure(pay_to="0xYourWallet")

@app.post("/tools/my-tool")
@paywall(price="0.05")
def my_tool(data: dict):
    return {"result": "paid"}

vaulls_middleware(app)
```

That's it. Agents calling `/tools/my-tool` without payment get a `402 Payment Required` response with x402 payment instructions. Agents with a smart wallet pay automatically and get the result.

## How It Works

1. You own an MCP server with tools you've built
2. You `pip install vaulls` and add `@paywall(price="0.05")` to the tools you want to monetise
3. Agents connect to your MCP server as normal
4. When an agent calls a paywalled tool, it gets a `402` response with payment requirements
5. The agent's x402 client signs a USDC payment and retries — your tool executes and returns the result
6. Settlement happens on Base via the x402 facilitator

## Configuration

```python
import vaulls

vaulls.configure(
    pay_to="0xYourWallet",           # your Base wallet address
    network="base-sepolia",           # "base" for mainnet
    facilitator="https://x402.org/facilitator",
)
```

Or use environment variables:

```bash
export VAULLS_PAY_TO=0xYourWallet
export VAULLS_NETWORK=base-sepolia
export VAULLS_FACILITATOR_URL=https://x402.org/facilitator
```

## Settlement Logging

```python
from vaulls import enable_settlement_log

# Log to file
enable_settlement_log("settlements.jsonl")

# Or use a callback
enable_settlement_log(callback=lambda entry: print(entry))
```

## Stack

- **Payment:** x402 protocol (EIP-712 signatures)
- **Settlement:** USDC on Base
- **Integrations:** FastAPI, MCP Python SDK (FastMCP)
