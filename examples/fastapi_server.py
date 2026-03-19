"""Example: FastAPI MCP server with VAULLS payment gating.

This shows how an MCP developer would add x402 payments to their
existing FastAPI-based tool server.

Run:
    pip install "vaulls[fastapi]"
    export VAULLS_PAY_TO=0xYourWalletAddress
    uvicorn examples.fastapi_server:app --reload
"""

from fastapi import FastAPI

import vaulls
from vaulls import paywall, enable_settlement_log
from vaulls.integrations.fastapi import vaulls_middleware

# 1. Configure VAULLS with your wallet
vaulls.configure(
    # pay_to is read from VAULLS_PAY_TO env var if not set here
    network="base-sepolia",  # use "base" for mainnet
)

# Optional: log settlements to a file
enable_settlement_log("settlements.jsonl")

# 2. Create your FastAPI app as normal
app = FastAPI(title="My Tool Server", version="1.0.0")


# 3. Your free tools — no change needed
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tools/free-lookup")
def free_lookup(data: dict):
    """This tool is free — no paywall."""
    return {"result": f"looked up {data.get('query', '?')}"}


# 4. Your paid tools — just add @paywall
@app.post("/tools/premium-analysis")
@paywall(price="0.10", description="Premium data analysis")
def premium_analysis(data: dict):
    """This tool costs $0.10 USDC per call."""
    return {
        "analysis": "detailed result here",
        "confidence": 0.95,
        "input": data,
    }


@app.post("/tools/expert-review")
@paywall(price="0.25", description="Expert-level review")
def expert_review(data: dict):
    """This tool costs $0.25 USDC per call."""
    return {
        "review": "expert assessment here",
        "grade": "A",
        "input": data,
    }


# 5. Wire up VAULLS middleware — this enables x402 payment gating
vaulls_middleware(app)
