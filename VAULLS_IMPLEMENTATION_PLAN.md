# VAULLS Implementation Plan

**Project:** VAULLS — Value-Wall Monetisation Layer for MCP Tools
**Lead:** Aaron Clifft / North Metro Tech
**Stack:** Python (FastAPI) + x402 Protocol + Base Sepolia (USDC) + MCP
**Repo:** `vaulls` (GitHub, North Metro Tech org)
**Linear Project:** VAULLS (North Metro Tech workspace)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  AI Agent (Claude Code / Cursor / AutoGPT)          │
│  Has: x402-aware HTTP client + Base wallet          │
└──────────────────┬──────────────────────────────────┘
                   │ 1. MCP tool_call or HTTP request
                   ▼
┌─────────────────────────────────────────────────────┐
│  VAULLS Gateway (FastAPI + x402 middleware)          │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ @vaulls_gate(price=0.05, currency="USDC")     │  │
│  │                                               │  │
│  │  No payment? → 402 Payment Required           │  │
│  │  Valid payment? → Execute tool → Return result │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Routes:                                            │
│  POST /tools/max-demand-calc     → $0.05            │
│  POST /tools/as3000-check        → $0.10            │
│  POST /tools/lore-query          → $0.02            │
└──────────────────┬──────────────────────────────────┘
                   │ 2. Payment verification
                   ▼
┌─────────────────────────────────────────────────────┐
│  Facilitator (Coinbase CDP / x402.org)              │
│  Verifies EIP-712 signature → Settles on Base       │
└─────────────────────────────────────────────────────┘
```

---

## Sprint 0 — Environment & Foundations (Day 1)

**Goal:** Repo scaffold, dependencies installed, testnet wallet created.
**Deliverable:** Empty FastAPI server that starts and responds on `/health`.

### Tasks

1. **Create repo structure:**
   ```
   vaulls/
   ├── src/
   │   ├── __init__.py
   │   ├── server.py          # FastAPI app + x402 middleware
   │   ├── gate.py            # @vaulls_gate decorator logic
   │   ├── tools/
   │   │   ├── __init__.py
   │   │   ├── electrical.py  # AS3000 / max demand calc
   │   │   └── lore.py        # Allogaia lore checker
   │   └── config.py          # Wallet address, pricing, facilitator URL
   ├── tests/
   │   ├── test_gate.py
   │   ├── test_402_response.py
   │   └── test_tools.py
   ├── mcp_manifest.json       # MCP server config with pricing metadata
   ├── pyproject.toml
   ├── .env.example
   └── README.md
   ```

2. **Install core dependencies:**
   ```bash
   pip install "x402[fastapi,httpx,evm]" fastapi uvicorn python-dotenv
   ```

3. **Create Base Sepolia testnet wallet:**
   - Use Coinbase Wallet or any EVM wallet
   - Fund with testnet USDC from Base Sepolia faucet
   - Store wallet address in `.env` as `VAULLS_PAY_TO`

4. **Skeleton FastAPI app:**
   ```python
   # src/server.py
   from fastapi import FastAPI

   app = FastAPI(title="VAULLS", version="0.1.0")

   @app.get("/health")
   def health():
       return {"status": "ok", "version": "0.1.0"}
   ```

5. **Verify it runs:** `uvicorn src.server:app --reload`

### Done When
- `GET /health` returns 200
- Repo initialised with `.gitignore`, `README.md`, `pyproject.toml`
- `.env` has `VAULLS_PAY_TO` set to your testnet wallet

---

## Sprint 1 — The 402 Gate (Days 2–3)

**Goal:** Any route wrapped with `@vaulls_gate` returns a proper x402 `402 Payment Required` response when called without payment headers.
**Deliverable:** A decorator that intercepts requests and returns spec-compliant 402 payloads.

### Tasks

1. **Integrate x402 FastAPI middleware:**
   ```python
   # src/server.py
   from fastapi import FastAPI
   from x402.integrations.fastapi import x402_middleware
   from x402.mechanisms.evm.exact import ExactEvmScheme
   from x402.facilitator import HTTPFacilitatorClient
   import os

   app = FastAPI(title="VAULLS")

   facilitator = HTTPFacilitatorClient(
       url="https://x402.org/facilitator"  # testnet facilitator
   )

   # x402 middleware handles 402 responses automatically
   x402_middleware(
       app,
       facilitator_client=facilitator,
       schemes=[ExactEvmScheme()],
       routes={
           "POST /tools/max-demand": {
               "price": "$0.05",
               "network": "eip155:84532",  # Base Sepolia
               "pay_to": os.getenv("VAULLS_PAY_TO"),
               "description": "AS3000 maximum demand calculation",
           }
       }
   )
   ```
   > **Note:** The x402 Python SDK on PyPI (`x402[fastapi]`) provides native FastAPI middleware. Read the SDK docs first — the API may differ from above pseudocode. The official quickstart is at `docs.cdp.coinbase.com/x402/quickstart-for-sellers`.

2. **Create a stub tool endpoint:**
   ```python
   @app.post("/tools/max-demand")
   def calculate_max_demand(site_data: dict):
       # Stub — real logic comes in Sprint 3
       return {"max_demand_amps": 200, "standard": "AS3000:2018", "status": "compliant"}
   ```

3. **Test the 402 flow manually:**
   ```bash
   # Should return 402 Payment Required with x402 payload
   curl -X POST http://localhost:8000/tools/max-demand \
     -H "Content-Type: application/json" \
     -d '{"site": "test"}'
   ```

4. **Write test:**
   ```python
   # tests/test_402_response.py
   def test_returns_402_without_payment(client):
       response = client.post("/tools/max-demand", json={"site": "test"})
       assert response.status_code == 402
       # Verify x402 payment requirements are in response
       assert "PAYMENT-REQUIRED" in response.headers or response.status_code == 402
   ```

### Done When
- Unauthenticated `POST /tools/max-demand` returns `402` with valid x402 payment requirements
- Payment requirements include correct price, network, and wallet address
- Test passes

---

## Sprint 2 — Payment Verification & Settlement (Days 4–5)

**Goal:** Accept a valid x402 payment header, verify it via facilitator, execute the tool, return the result.
**Deliverable:** End-to-end payment flow working on Base Sepolia testnet.

### Tasks

1. **Build an x402 test client:**
   ```python
   # tests/test_client.py
   from x402 import x402Client
   from x402.mechanisms.evm.exact import ExactEvmScheme

   # Load testnet signer (buyer wallet)
   client = x402Client()
   client.register("eip155:*", ExactEvmScheme(signer=buyer_signer))

   # This client auto-handles 402 → sign → retry flow
   response = client.post(
       "http://localhost:8000/tools/max-demand",
       json={"site": "test-site"}
   )
   ```

2. **Verify the full round trip:**
   - Client sends request → gets 402
   - Client signs payment via EIP-712 → retries with `X-PAYMENT` header
   - Server verifies via facilitator → executes tool → returns result
   - Settlement happens on Base Sepolia

3. **Add basic logging:**
   ```python
   # src/logging.py — minimal billing metadata
   import json, datetime

   def log_settlement(tool: str, price: str, payer: str, tx_hash: str):
       entry = {
           "timestamp": datetime.datetime.utcnow().isoformat(),
           "tool": tool,
           "price": price,
           "payer": payer,
           "tx_hash": tx_hash,
       }
       # Append to JSONL file — upgrade to DB later
       with open("settlements.jsonl", "a") as f:
           f.write(json.dumps(entry) + "\n")
   ```

4. **Measure settlement latency:**
   - Target: < 2 seconds from payment submission to tool response
   - Log timing at each step (receive → verify → execute → respond)

### Done When
- Full 402 → pay → verify → execute → respond cycle works on testnet
- Settlement logged to `settlements.jsonl`
- Latency < 2s measured and logged

---

## Sprint 3 — Real Domain Tools (Days 6–8)

**Goal:** Replace stubs with actual domain logic across two verticals.
**Deliverable:** Two working gated tools proving cross-domain portability.

### Tool 1: Electrical — AS3000 Maximum Demand Calculator

```python
# src/tools/electrical.py

def calculate_maximum_demand(site_data: dict) -> dict:
    """
    AS/NZS 3000:2018 Clause 2.2 maximum demand calculation.
    
    Input:  site_data with lighting_va, socket_va, fixed_appliances, 
            cooking_va, cooling_va, heating_va, motor_loads
    Output: total_demand_amps, diversity_applied, standard_reference,
            warnings (if approaching limits)
    """
    # Implement diversity factors per Table 2.2
    # Apply demand factors per clause 2.2.2
    # Return structured result with standard references
    pass
```

**Why this tool:** It's genuinely useful, demonstrates real domain expertise, and the output is *verifiable* — an agent can cross-check the calculation against the standard. This is the "expertise has value" proof case.

### Tool 2: Creative — Allogaia Lore Consistency Checker

```python
# src/tools/lore.py

# Load from a simplified lore reference (JSON or markdown)
# Start with character names, faction affiliations, timeline events

def check_lore_consistency(query: dict) -> dict:
    """
    Query the Allogaia canonical lore database.
    
    Input:  query with entity_name, claim (e.g. "Arkannon is STA loyal")
    Output: canonical_answer, confidence, source_reference, contradictions
    """
    pass
```

**Why this tool:** Proves cross-domain portability. Same payment infra, completely different domain. Also seeds the Allogaia web3 game payment pattern.

### Pricing Config

```python
# src/config.py
TOOL_PRICING = {
    "POST /tools/max-demand": {
        "price": "$0.05",
        "description": "AS3000 maximum demand calculation",
    },
    "POST /tools/as3000-check": {
        "price": "$0.10",
        "description": "AS3000 compliance verification",
    },
    "POST /tools/lore-query": {
        "price": "$0.02",
        "description": "Allogaia canonical lore query",
    },
}
```

### Done When
- Both tools return real structured data (not stubs)
- Both tools gated behind x402 payment
- Same VAULLS middleware handles both with zero tool-specific payment code

---

## Sprint 4 — MCP Server Integration (Days 9–11)

**Goal:** Expose VAULLS-gated tools as an MCP server that Claude/Cursor can connect to.
**Deliverable:** A working MCP config that an agent can discover and use.

### Tasks

1. **Create MCP manifest with pricing metadata:**
   ```json
   {
     "name": "vaulls-tools",
     "description": "VAULLS-gated professional tools",
     "url": "http://localhost:8000/mcp",
     "tools": [
       {
         "name": "calculate_max_demand",
         "description": "AS3000:2018 maximum demand calculation for electrical installations",
         "inputSchema": {
           "type": "object",
           "properties": {
             "lighting_va": {"type": "number"},
             "socket_va": {"type": "number"},
             "fixed_appliances": {"type": "number"},
             "cooking_va": {"type": "number"}
           }
         },
         "x-vaulls-price": "$0.05",
         "x-vaulls-currency": "USDC",
         "x-vaulls-network": "base"
       },
       {
         "name": "query_allogaia_lore",
         "description": "Query canonical Allogaia Chronicles lore database",
         "inputSchema": {
           "type": "object",
           "properties": {
             "entity_name": {"type": "string"},
             "claim": {"type": "string"}
           }
         },
         "x-vaulls-price": "$0.02",
         "x-vaulls-currency": "USDC",
         "x-vaulls-network": "base"
       }
     ]
   }
   ```

2. **Implement MCP SSE transport on FastAPI:**
   - MCP uses Server-Sent Events (SSE) for streaming
   - The x402 gate sits *in front of* the tool execution, not the SSE connection
   - Agent connects to MCP → discovers tools → calls tool → hits 402 → pays → gets result

3. **Test with Claude Desktop or Cursor:**
   - Add the MCP server URL to client config
   - Verify tool discovery (agent sees available tools + pricing)
   - Verify gated execution flow

### Done When
- MCP server discoverable and connectable
- Tools listed with pricing metadata
- Full MCP → 402 → payment → result flow working

---

## Sprint 5 — Hardening & Demo Polish (Days 12–14)

**Goal:** Production-ready enough for a portfolio demo and LinkedIn post.
**Deliverable:** README with architecture diagram, demo video/GIF, deployed to a public endpoint.

### Tasks

1. **Error handling:**
   - Graceful handling of payment timeout
   - Clear error messages for insufficient funds
   - Retry logic guidance for agents
   - Rate limiting per wallet address

2. **Deploy to public endpoint:**
   - Option A: Railway / Render (fastest)
   - Option B: Your frankenfarm behind Cloudflare tunnel (free, on-brand)
   - Point `vaulls.northmetrotech.com.au` or similar at it

3. **README.md — the portfolio piece:**
   - Architecture diagram (the one above, cleaned up)
   - "5-minute quickstart" showing the decorator pattern
   - Demo GIF showing agent → 402 → payment → result flow
   - Cross-domain examples (electrical + lore)
   - Link to live testnet demo

4. **LinkedIn / portfolio writeup:**
   - Frame: "I built the monetisation layer for the agentic economy"
   - Emphasise: x402 protocol, MCP integration, cross-domain portability
   - Show: real electrical domain expertise encoded as a paid tool

5. **Tag for Allogaia web3 reuse:**
   - Document which components transfer directly to game payment infra
   - Create `ALLOGAIA_WEB3_NOTES.md` mapping VAULLS patterns → game use cases

### Done When
- Public URL serving gated tools on testnet
- README is portfolio-quality
- Demo reproducible by anyone with a testnet wallet

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python (FastAPI) | Matches your stack, official x402 SDK on PyPI |
| Settlement chain | Base Sepolia → Base mainnet | Lowest fees, strongest x402 ecosystem support, Coinbase-backed |
| Facilitator | Coinbase CDP (testnet: x402.org) | Official, free, handles verification + settlement |
| MCP transport | SSE over HTTP | Standard MCP pattern, works with Claude/Cursor |
| Storage | JSONL → SQLite → Postgres | Start simple, upgrade when needed |
| Deployment | Cloudflare Tunnel on frankenfarm | Free, uses your existing infra, good demo of self-hosting |

---

## Key Resources

- **x402 Official SDK (Python):** `pip install x402[fastapi,evm]` — [pypi.org/project/x402](https://pypi.org/project/x402/)
- **x402 Seller Quickstart:** [docs.cdp.coinbase.com/x402/quickstart-for-sellers](https://docs.cdp.coinbase.com/x402/quickstart-for-sellers)
- **Coinbase x402 Repo:** [github.com/coinbase/x402](https://github.com/coinbase/x402)
- **x402 Whitepaper:** [x402.org/x402-whitepaper.pdf](https://www.x402.org/x402-whitepaper.pdf)
- **Awesome x402 (ecosystem list):** [github.com/xpaysh/awesome-x402](https://github.com/xpaysh/awesome-x402)
- **Google A2A x402 Extension:** [github.com/google-agentic-commerce/a2a-x402](https://github.com/google-agentic-commerce/a2a-x402)
- **Base Sepolia Faucet:** Search "Base Sepolia faucet" for testnet ETH + USDC
- **MCP Spec:** [modelcontextprotocol.io](https://modelcontextprotocol.io)

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| x402 Python SDK API changes | Medium — breaks integration | Pin version in pyproject.toml, read SDK source before each sprint |
| Agent x402 adoption still early | Low for portfolio, high for revenue | Position as "infrastructure for the wave" not "product for today" |
| ADHD context-switch between sprints | Medium | Each sprint is standalone with its own "Done When" gate |
| Facilitator downtime on testnet | Low | x402.org testnet facilitator is Coinbase-backed; fallback to local mock |
| Scope creep into wallet/dashboard/UI | High | Hard scope boundary: NO frontend. Agent-first. CLI testing only. |

---

## Allogaia Web3 Game Reuse Map

| VAULLS Component | Game Equivalent |
|---|---|
| `@vaulls_gate` decorator | Asset verification gate (pay to verify item authenticity) |
| x402 402→pay→verify flow | In-game marketplace transaction pattern |
| Lore query tool | Canonical lore oracle for game events/quests |
| Settlement logging | Player transaction history / audit trail |
| MCP manifest with pricing | Game service catalogue (NPC services, crafting, etc.) |
| Base USDC settlement | Game token settlement (swap USDC for game token later) |

---

## Claude Code Session Kickoff Prompt

When you open this in Claude Code, use this as your first message:

```
I'm building VAULLS — a monetisation layer for MCP tools using the x402 payment protocol. 

Read VAULLS_IMPLEMENTATION_PLAN.md for full context.

I'm starting Sprint [N]. Here's the "Done When" criteria for this sprint:
[paste the Done When from the relevant sprint]

Let's build it. Start with [first task in the sprint].
```
