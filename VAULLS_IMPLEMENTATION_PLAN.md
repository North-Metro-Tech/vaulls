# VAULLS Implementation Plan

**Project:** VAULLS — Value-Wall Monetisation Layer for MCP Tools
**Lead:** Aaron Clifft / North Metro Tech
**Stack:** Python + x402 Protocol + Base (USDC) + MCP
**Repo:** `vaulls` (GitHub, North Metro Tech org)
**Linear Project:** VAULLS (North Metro Tech workspace)

---

## What VAULLS Is

VAULLS is a **pip-installable Python package** that MCP server developers add to their own MCP servers to monetise their tools using the x402 payment protocol.

**It is NOT:**
- A standalone platform or gateway
- A repository of paywalled MCP tools
- Something that sits between agents and third-party MCPs

**It IS:**
- A library that MCP developers install into their own servers
- A set of decorators, middleware, and helpers that wrap existing MCP tool functions
- The x402 plumbing so developers don't have to build it themselves

**Analogy:** Stripe SDK for websites → VAULLS for MCP servers.
Just as a website owner adds Stripe to their own domain to accept payments, an MCP developer adds VAULLS to their own MCP server to accept x402 payments from AI agents.

**Relationship to Carbon-Contractors:** Carbon-Contractors is a Human-as-a-Service MCP with x402 baked in from the ground up. VAULLS packages that same payment capability so *any* MCP developer can add it to *their* server without writing the payment code themselves.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│  MCP Developer's Server (they own & operate this)        │
│                                                          │
│  from vaulls import paywall                              │
│                                                          │
│  @paywall(price="0.05", asset="USDC", network="base")   │
│  def my_tool(args):                                      │
│      return my_result    ← their logic, unchanged        │
│                                                          │
│  # VAULLS handles:                                       │
│  # - 402 response with x402 payment requirements         │
│  # - Payment verification via facilitator                │
│  # - Settlement logging                                  │
│  # - MCP pricing metadata exposure                       │
└──────────────────┬───────────────────────────────────────┘
                   │
    Agent calls tool, gets 402, pays, gets result
                   │
┌──────────────────┴───────────────────────────────────────┐
│  AI Agent (Claude Code / Cursor / etc.)                  │
│  Has: x402-aware HTTP client + Coinbase Smart Wallet     │
│                                                          │
│  Agent adds the MCP server as per normal.                │
│  If a tool requires payment → agent pays via x402.       │
│  If agent has no wallet → tool call fails with 402 info. │
└──────────────────────────────────────────────────────────┘
```

**Key principle:** The MCP developer owns the server, owns the wallet, sets the prices. VAULLS is just the library they import. End users (agents) still connect to MCP servers as per usual — they just need a smart wallet if the server has paywalled tools.

---

## Developer Experience (Target API)

### Minimal integration — decorator on a tool function

```python
# The developer's existing MCP server
from mcp.server.fastmcp import FastMCP
from vaulls import paywall

mcp = FastMCP("my-useful-tools")

# Without VAULLS — free tool, works as normal
@mcp.tool()
def free_tool(query: str) -> str:
    return "this is free"

# With VAULLS — same tool, now paywalled
@mcp.tool()
@paywall(price="0.05", asset="USDC", network="base")
def paid_tool(query: str) -> str:
    return "this cost $0.05"
```

### Configuration — developer sets their wallet

```python
import vaulls

vaulls.configure(
    pay_to="0x1234...",               # developer's wallet
    facilitator="https://x402.org/facilitator",
    network="base-sepolia",           # or "base" for mainnet
)
```

Or via environment variables:
```bash
VAULLS_PAY_TO=0x1234...
VAULLS_FACILITATOR_URL=https://x402.org/facilitator
VAULLS_NETWORK=base-sepolia
```

### Settlement logging — opt-in

```python
from vaulls import paywall, enable_settlement_log

# Log all settlements to a JSONL file (or callback)
enable_settlement_log("settlements.jsonl")

# Or provide a custom callback
enable_settlement_log(callback=my_logging_function)
```

---

## Sprint Plan

### Sprint 0 — Repo Scaffold ✅ COMPLETE

**Delivered:** FastAPI skeleton, health endpoint, pyproject.toml, test suite.

**Note:** Sprint 0-2 built a working x402 payment flow as a standalone server. This validated that the x402 middleware, facilitator verification, and settlement logging all work. That code is now reference material for the library rewrite.

---

### Sprint 1 — x402 Payment Gate ✅ COMPLETE

**Delivered:** Route-based x402 middleware returning 402 responses, payment verification via facilitator.

---

### Sprint 2 — Payment Verification & Settlement ✅ COMPLETE

**Delivered:** End-to-end 402 → sign → verify → settle flow, settlement logging to JSONL.

---

### Sprint 3 — Library Pivot ✅ COMPLETE

**Goal:** Restructure VAULLS from a standalone server into a pip-installable library with a clean developer API.
**Deliverable:** `pip install vaulls` gives MCP developers a `@paywall` decorator they can add to their own tools.

#### Tasks

1. **Restructure package layout:**
   ```
   vaulls/
   ├── vaulls/                      # the library (what gets pip installed)
   │   ├── __init__.py              # public API: paywall, configure
   │   ├── decorator.py             # @paywall decorator implementation
   │   ├── config.py                # configure(), env var loading
   │   ├── middleware.py             # x402 middleware wiring (framework-agnostic core)
   │   ├── integrations/
   │   │   ├── __init__.py
   │   │   ├── fastapi.py           # FastAPI-specific middleware adapter
   │   │   └── mcp.py               # MCP SDK (FastMCP) adapter
   │   ├── settlement.py            # settlement logging (JSONL, callbacks)
   │   └── types.py                 # shared types / dataclasses
   ├── examples/
   │   ├── fastapi_server.py        # example: FastAPI MCP server with VAULLS
   │   └── fastmcp_server.py        # example: FastMCP server with VAULLS
   ├── tests/
   │   ├── conftest.py
   │   ├── test_decorator.py        # @paywall unit tests
   │   ├── test_config.py           # configure() tests
   │   ├── test_middleware.py        # x402 middleware tests
   │   ├── test_settlement.py       # logging tests
   │   └── test_integration.py      # end-to-end: decorate → 402 → pay → result
   ├── pyproject.toml
   ├── README.md
   └── LICENSE
   ```

2. **Implement `vaulls.configure()`:**
   - Stores wallet address, facilitator URL, network
   - Falls back to env vars (`VAULLS_PAY_TO`, etc.)
   - Validates config on first paywall call
   - Thread-safe global config singleton

3. **Implement `@paywall` decorator:**
   - Wraps any callable (sync or async)
   - On call without valid payment: raises/returns 402 with x402 payment requirements
   - On call with valid payment: verifies via facilitator, executes function, returns result
   - Attaches pricing metadata to function (inspectable by MCP tooling)
   - Works with both FastAPI route handlers and MCP tool functions

4. **Implement FastAPI integration:**
   - Adapter that hooks `@paywall`-decorated route handlers into FastAPI middleware
   - Reuses proven x402 middleware pattern from Sprints 1-2
   - Auto-discovers paywalled routes and builds route config

5. **Implement MCP (FastMCP) integration:**
   - Adapter for the MCP Python SDK (`mcp` package / FastMCP)
   - Intercepts tool calls to paywalled functions
   - Exposes pricing metadata via MCP tool descriptions
   - Maintains standard MCP transport (stdio/SSE) — payment happens at the tool execution layer

6. **Port settlement logging:**
   - Extract from Sprint 2 code into `vaulls.settlement`
   - JSONL output (default) or custom callback
   - Opt-in, not required

7. **Update pyproject.toml for library distribution:**
   ```toml
   [project]
   name = "vaulls"
   version = "0.2.0"
   description = "Add x402 payments to your MCP server in one line"

   dependencies = [
       "x402[evm]>=2.4.0",
   ]

   [project.optional-dependencies]
   fastapi = ["fastapi>=0.115.0", "x402[fastapi]>=2.4.0"]
   mcp = ["mcp>=1.0.0"]
   dev = ["pytest>=8.0.0", "httpx>=0.27.0", "fastapi>=0.115.0"]
   ```

8. **Write unit tests for every public API surface.**

#### Done When
- `pip install vaulls` works
- Developer can `from vaulls import paywall` and decorate a function
- Decorated function returns 402 without payment, executes with payment
- Settlement logging works
- Tests pass
- At least one working example in `examples/`

---

### Sprint 4 — MCP-Native Integration & Pricing Discovery ✅ COMPLETE

**Goal:** Make pricing discoverable so agents know what tools cost before calling them.
**Deliverable:** Agents connecting to a VAULLS-enabled MCP server can see prices in tool metadata.

#### Tasks

1. **Pricing metadata in MCP tool descriptions:**
   - `@paywall` annotates the MCP tool's description with pricing info
   - Agent sees: "This tool costs $0.05 USDC on Base" in the tool listing
   - Uses `x-vaulls-*` metadata fields if MCP schema supports extensions

2. **Free-tier / metered support (optional):**
   - `@paywall(price="0.05", free_calls=10)` — first N calls free
   - Tracked per-wallet (or per-session if no wallet)
   - Simple in-memory counter, not a billing system

3. **Multi-network support:**
   - Base mainnet, Base Sepolia, other EVM chains
   - Developer configures which network(s) they accept
   - `@paywall(price="0.05", network=["base", "base-sepolia"])`

4. **Error handling & agent UX:**
   - Clear error messages when agent has no wallet
   - Retry guidance in 402 response body
   - Timeout handling for facilitator calls

#### Done When
- Agent connecting to example MCP server sees tool prices
- Multi-network config works
- Error messages are clear and actionable for agents

---

### Sprint 5 — Hardening, Docs & Release ✅ COMPLETE

**Goal:** Production-ready package on PyPI, portfolio-quality documentation.
**Deliverable:** Published package, README with examples, demo.

#### Tasks

1. **PyPI release:**
   - Clean up package metadata
   - Publish to PyPI as `vaulls`
   - Verify `pip install vaulls` works from a clean environment

2. **README — the developer onboarding doc:**
   - 3-step quickstart: install → configure → decorate
   - Architecture diagram showing where VAULLS sits
   - Example MCP server with 2-3 paywalled tools
   - "How agents pay" section explaining the x402 flow
   - Link to Carbon-Contractors as a real-world example

3. **Example servers:**
   - `examples/fastmcp_server.py` — minimal FastMCP with one free + one paid tool
   - `examples/fastapi_mcp.py` — FastAPI-based MCP with VAULLS
   - Each example runnable with `python examples/xxx.py`

4. **Security review:**
   - Payment verification is server-side only (no client trust)
   - Wallet address validation
   - Rate limiting guidance (not built-in, but documented)
   - No secret material in package

5. **Portfolio positioning:**
   - Frame: "I built the Stripe SDK for the agentic economy"
   - Emphasise: developer tool, not a platform
   - Show: Carbon-Contractors as production use case
   - Differentiate from x402 itself: "x402 is the protocol, VAULLS is the developer experience"

#### Done When
- Package on PyPI
- README is clear enough that a developer can integrate in < 10 minutes
- Examples run out of the box
- Tests pass in CI

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Package type | pip-installable library | Developers add to their own servers, not a standalone app |
| Primary integration | MCP Python SDK (FastMCP) | Most MCP servers use this — meet developers where they are |
| Secondary integration | FastAPI | Many MCP servers use FastAPI under the hood |
| Core decorator | `@paywall` | One-line integration, minimal API surface |
| Settlement chain | Base (Sepolia for test, mainnet for prod) | Lowest fees, strongest x402 support, Coinbase-backed |
| Facilitator | x402.org (default, configurable) | Official, handles verification + settlement |
| Config | `configure()` + env vars | Explicit API with sensible defaults |
| Settlement logging | Opt-in JSONL + callback hook | Developers choose their own logging strategy |

---

## What Stays From Sprints 0-2

The existing code validated the x402 payment flow end-to-end. These pieces port directly into the library:

| Existing Code | Becomes |
|---|---|
| `build_routes()` in server.py | `vaulls/middleware.py` route builder |
| x402 middleware wiring | `vaulls/integrations/fastapi.py` |
| `log_settlement()` | `vaulls/settlement.py` |
| Test fixtures (mocked facilitator) | `tests/conftest.py` |
| `.env` config pattern | `vaulls/config.py` with `configure()` |

What gets **removed:**
- `/tools/max-demand` stub endpoint (not our tool to build)
- `/health` endpoint (that's the developer's concern)
- `TOOL_PRICING` config (pricing lives on the decorator now)
- Any domain-specific tool logic

---

## Relationship to Carbon-Contractors

```
Carbon-Contractors                    Any MCP Developer
(Aaron's own MCP)                     (using VAULLS)
─────────────────                     ──────────────────
x402 baked in from scratch            pip install vaulls
Custom payment code                   @paywall(price="0.05")
Full control over payment flow        VAULLS handles the plumbing
Human-as-a-Service tools              Their own domain tools

Both use:
- x402 protocol
- Coinbase Smart Wallets
- Base / USDC settlement
- Same agent-facing 402 flow
```

VAULLS extracts the payment pattern from Carbon-Contractors and packages it so other developers don't have to build it themselves.

---

## Key Resources

- **x402 Official SDK (Python):** `pip install x402[fastapi,evm]` — [pypi.org/project/x402](https://pypi.org/project/x402/)
- **x402 Seller Quickstart:** [docs.cdp.coinbase.com/x402/quickstart-for-sellers](https://docs.cdp.coinbase.com/x402/quickstart-for-sellers)
- **MCP Python SDK:** [github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
- **FastMCP:** Part of MCP Python SDK — the standard way to build MCP servers in Python
- **Carbon-Contractors:** North Metro Tech's production x402 MCP (reference implementation)

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| MCP SDK internal API changes | High — decorator may break | Pin MCP SDK version, test against multiple versions |
| x402 Python SDK API changes | Medium | Pin version, read SDK source before integration |
| FastMCP doesn't expose tool-call hooks | High — may need alternative integration point | Research FastMCP internals in Sprint 3 before committing to approach |
| Decorator approach too magical | Medium — developers may not trust it | Provide explicit middleware option alongside decorator |
| Scope creep into building tools | High | Hard rule: VAULLS never contains domain tools. That's the developer's job. |
| Agent x402 wallet adoption still early | Low for launch | Position as infrastructure — "ready when the agents are" |
