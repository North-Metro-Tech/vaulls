"""Tests for VaullsMCPMiddleware — FastMCP /mcp paywall enforcement.

Uses a minimal Starlette app to mimic FastMCP's POST /mcp JSON-RPC endpoint
so tests run without the ``mcp`` package installed.  The x402 facilitator is
mocked the same way as in test_fastapi_integration.py.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from eth_account import Account
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route
from x402 import x402ClientSync, x402ResourceServer
from x402.http.x402_http_client import x402HTTPClientSync
from x402.mechanisms.evm.exact import ExactEvmServerScheme, register_exact_evm_client
from x402.schemas import SettleResponse, VerifyResponse
from x402.server_base import SupportedKind, SupportedResponse

from vaulls import configure, paywall
from vaulls.config import reset_config
from vaulls.decorator import get_paywall_config
from vaulls.integrations.mcp import VaullsMCPMiddleware, _build_mcp_routes
from vaulls.metering import get_meter

TEST_WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"
BUYER_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
BUYER_ADDRESS = Account.from_key(BUYER_PRIVATE_KEY).address
FAKE_TX_HASH = "0xfake_mcp_tx_hash_1234567890abcdef"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_server() -> x402ResourceServer:
    """x402ResourceServer backed by a mock facilitator."""
    facilitator = MagicMock()
    facilitator.get_supported.return_value = SupportedResponse(
        kinds=[SupportedKind(x402_version=1, scheme="exact", network="eip155:84532")]
    )
    facilitator.verify = AsyncMock(
        return_value=VerifyResponse(is_valid=True, payer=BUYER_ADDRESS)
    )
    facilitator.settle = AsyncMock(
        return_value=SettleResponse(
            success=True,
            payer=BUYER_ADDRESS,
            transaction=FAKE_TX_HASH,
            network="eip155:84532",
        )
    )
    server = x402ResourceServer(facilitator)
    server.register("eip155:84532", ExactEvmServerScheme())
    server.initialize()
    return server


def _make_buyer() -> x402HTTPClientSync:
    account = Account.from_key(BUYER_PRIVATE_KEY)
    client = x402ClientSync()
    register_exact_evm_client(client, account)
    return x402HTTPClientSync(client)


async def _fake_mcp_handler(request: StarletteRequest) -> JSONResponse:
    """Minimal handler that mimics FastMCP's /mcp JSON-RPC endpoint."""
    body = await request.body()
    try:
        rpc = json.loads(body)
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": rpc.get("id"),
        "result": {
            "content": [{"type": "text", "text": "tool_result"}],
            "isError": False,
        },
    })


def _fake_fastmcp_asgi() -> Starlette:
    return Starlette(routes=[Route("/mcp", _fake_mcp_handler, methods=["POST"])])


def _tools_call_body(tool_name: str, params: dict | None = None) -> bytes:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": params or {}},
    }).encode()


def _other_rpc_body(method: str = "initialize") -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}).encode()


def _build_test_middleware(
    paywalled_tools: dict,
    server: x402ResourceServer,
    free_tools: dict | None = None,
) -> VaullsMCPMiddleware:
    reset_config()
    configure(pay_to=TEST_WALLET, network="base-sepolia")
    from vaulls.config import get_config
    cfg = get_config()
    paywalled_routes = _build_mcp_routes(paywalled_tools, cfg)
    free_routes = {
        name: (name, pw.free_calls)
        for name, pw in paywalled_tools.items()
        if pw.free_calls > 0
    }
    if free_tools:
        free_routes.update(free_tools)
    return VaullsMCPMiddleware(
        app=_fake_fastmcp_asgi(),
        paywalled_tools=paywalled_tools,
        paywalled_routes=paywalled_routes,
        free_routes=free_routes,
        server=server,
        cfg=cfg,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset():
    reset_config()
    get_meter().reset()
    yield
    reset_config()
    get_meter().reset()


# ---------------------------------------------------------------------------
# Tests: basic enforcement
# ---------------------------------------------------------------------------

class TestMCPEnforcement:
    @pytest.fixture
    def paywalled_tools(self):
        @paywall(price="0.05", description="A paid tool")
        def paid_tool(q: str) -> str:
            return "result"

        @paywall(price="0.10")
        def another_paid_tool(q: str) -> str:
            return "result2"

        return {
            "paid_tool": get_paywall_config(paid_tool),
            "another_paid_tool": get_paywall_config(another_paid_tool),
        }

    @pytest.mark.asyncio
    async def test_non_paywalled_tool_passes_through(self, paywalled_tools):
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                content=_tools_call_body("free_tool"),
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["content"][0]["text"] == "tool_result"

    @pytest.mark.asyncio
    async def test_paywalled_tool_returns_402(self, paywalled_tools):
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                content=_tools_call_body("paid_tool"),
                headers={"content-type": "application/json", "accept": "application/json"},
            )
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_402_has_payment_required_header(self, paywalled_tools):
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                content=_tools_call_body("paid_tool"),
                headers={"content-type": "application/json", "accept": "application/json"},
            )
        assert resp.status_code == 402
        assert "payment-required" in resp.headers

    @pytest.mark.asyncio
    async def test_full_payment_flow(self, paywalled_tools):
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        buyer = _make_buyer()
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            # First call → 402
            resp = await client.post(
                "/mcp",
                content=_tools_call_body("paid_tool"),
                headers={"content-type": "application/json", "accept": "application/json, text/event-stream"},
            )
            assert resp.status_code == 402

            # Sign and retry
            payment_headers, _ = buyer.handle_402_response(
                headers=dict(resp.headers), body=resp.content
            )
            resp2 = await client.post(
                "/mcp",
                content=_tools_call_body("paid_tool"),
                headers={
                    "content-type": "application/json",
                    "accept": "application/json, text/event-stream",
                    **payment_headers,
                },
            )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["result"]["content"][0]["text"] == "tool_result"

    @pytest.mark.asyncio
    async def test_non_tools_call_passes_through(self, paywalled_tools):
        """initialize, tools/list, etc. must never be gated."""
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                content=_other_rpc_body("initialize"),
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_json_passes_through(self, paywalled_tools):
        """Malformed body must not crash — pass through to FastMCP."""
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                content=b"not json at all",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code != 500

    @pytest.mark.asyncio
    async def test_non_mcp_path_passes_through(self, paywalled_tools):
        """Requests to paths other than /mcp are never inspected."""
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.get("/health")
        # The fake FastMCP app has no /health route — 404 is fine; 500 is not
        assert resp.status_code != 500

    @pytest.mark.asyncio
    async def test_different_paywalled_tools_each_require_payment(self, paywalled_tools):
        """Each paywalled tool independently requires payment."""
        mw = _build_test_middleware(paywalled_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            r1 = await client.post(
                "/mcp",
                content=_tools_call_body("paid_tool"),
                headers={"content-type": "application/json", "accept": "application/json"},
            )
            r2 = await client.post(
                "/mcp",
                content=_tools_call_body("another_paid_tool"),
                headers={"content-type": "application/json", "accept": "application/json"},
            )
        assert r1.status_code == 402
        assert r2.status_code == 402


# ---------------------------------------------------------------------------
# Tests: free tier
# ---------------------------------------------------------------------------

class TestMCPFreeTier:
    @pytest.fixture
    def freemium_tools(self):
        @paywall(price="0.05", free_calls=3)
        def freemium_tool(q: str) -> str:
            return "result"

        return {"freemium_tool": get_paywall_config(freemium_tool)}

    @pytest.mark.asyncio
    async def test_free_calls_bypass_payment(self, freemium_tools):
        mw = _build_test_middleware(freemium_tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            # First 3 calls should be free
            for i in range(3):
                resp = await client.post(
                    "/mcp",
                    content=_tools_call_body("freemium_tool"),
                    headers={"content-type": "application/json", "accept": "application/json"},
                )
                assert resp.status_code == 200, f"Call {i+1} should be free, got {resp.status_code}"

            # 4th call requires payment
            resp = await client.post(
                "/mcp",
                content=_tools_call_body("freemium_tool"),
                headers={"content-type": "application/json", "accept": "application/json"},
            )
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_tool_without_free_calls_always_requires_payment(self):
        @paywall(price="0.10", free_calls=0)
        def paid_only(q: str) -> str:
            return "result"

        tools = {"paid_only": get_paywall_config(paid_only)}
        mw = _build_test_middleware(tools, _mock_server())
        async with AsyncClient(transport=ASGITransport(app=mw), base_url="http://test") as client:
            resp = await client.post(
                "/mcp",
                content=_tools_call_body("paid_only"),
                headers={"content-type": "application/json", "accept": "application/json"},
            )
        assert resp.status_code == 402
