"""Tests for the FastAPI integration.

Uses a mocked x402 facilitator to test the full payment flow
through VAULLS as a library integrated into a developer's FastAPI app.
"""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

from eth_account import Account
from fastapi import FastAPI
from fastapi.testclient import TestClient
from x402 import x402ClientSync, x402ResourceServer
from x402.http.x402_http_client import x402HTTPClientSync
from x402.mechanisms.evm.exact import ExactEvmServerScheme, register_exact_evm_client
from x402.schemas import SettleResponse, VerifyResponse
from x402.server_base import SupportedKind, SupportedResponse

from vaulls import configure, paywall
from vaulls.config import reset_config
from vaulls.integrations.fastapi import vaulls_middleware

TEST_WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"
BUYER_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
BUYER_ADDRESS = Account.from_key(BUYER_PRIVATE_KEY).address
FAKE_TX_HASH = "0xfake_tx_hash_for_test_1234567890abcdef"


def _mock_server() -> x402ResourceServer:
    """Create an x402 resource server with mocked facilitator."""
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


def _create_test_app(server: x402ResourceServer) -> FastAPI:
    """Create a minimal FastAPI app with VAULLS — like a developer would."""
    reset_config()
    configure(pay_to=TEST_WALLET, network="base-sepolia")

    app = FastAPI()

    # Developer's free tool
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Developer's paid tool — decorated with @paywall
    @app.post("/tools/my-calc")
    @paywall(price="0.05", description="My calculation tool")
    def my_calc(data: dict):
        return {"result": 42, "input": data}

    # Wire up VAULLS
    vaulls_middleware(app, server=server)
    return app


def _do_paid_request(test_client: TestClient, buyer: x402HTTPClientSync, path: str = "/tools/my-calc"):
    """Execute the 402 → sign → retry flow."""
    resp = test_client.post(path, json={"query": "test"}, headers={"Accept": "application/json"})
    assert resp.status_code == 402

    payment_headers, _ = buyer.handle_402_response(headers=dict(resp.headers), body=resp.content)
    return test_client.post(path, json={"query": "test"}, headers={"Accept": "application/json", **payment_headers})


class TestFastAPIIntegration:
    def test_free_route_not_gated(self):
        app = _create_test_app(_mock_server())
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_paywalled_route_returns_402(self):
        app = _create_test_app(_mock_server())
        with TestClient(app) as client:
            resp = client.post("/tools/my-calc", json={"query": "test"}, headers={"Accept": "application/json"})
        assert resp.status_code == 402

    def test_402_contains_payment_requirements(self):
        app = _create_test_app(_mock_server())
        with TestClient(app) as client:
            resp = client.post("/tools/my-calc", json={"query": "test"}, headers={"Accept": "application/json"})

        payment_header = resp.headers.get("payment-required")
        assert payment_header is not None
        payload = json.loads(base64.b64decode(payment_header))
        reqs = payload.get("paymentRequirements", payload.get("accepts", []))
        assert len(reqs) > 0
        assert reqs[0]["payTo"] == TEST_WALLET

    def test_full_payment_flow(self):
        app = _create_test_app(_mock_server())
        buyer = _make_buyer()
        with TestClient(app) as client:
            resp = _do_paid_request(client, buyer)
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == 42

    def test_settlement_headers_present(self):
        app = _create_test_app(_mock_server())
        buyer = _make_buyer()
        with TestClient(app) as client:
            resp = _do_paid_request(client, buyer)
        assert resp.status_code == 200
        assert "payment-response" in resp.headers

    def test_latency_under_target(self):
        app = _create_test_app(_mock_server())
        buyer = _make_buyer()
        with TestClient(app) as client:
            start = time.perf_counter()
            resp = _do_paid_request(client, buyer)
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 2000

    def test_missing_wallet_raises(self):
        reset_config()
        configure(pay_to="")
        app = FastAPI()

        @app.post("/tools/test")
        @paywall(price="0.05")
        def tool(data: dict):
            return {"ok": True}

        try:
            vaulls_middleware(app)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "pay_to" in str(e)
        finally:
            reset_config()
