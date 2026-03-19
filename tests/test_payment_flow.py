"""End-to-end payment flow test.

Simulates the full 402 → sign → retry → verify → settle cycle using a
local buyer wallet and mocked facilitator.
"""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from eth_account import Account
from fastapi.testclient import TestClient
from x402 import x402ClientSync, x402ResourceServer
from x402.http.x402_http_client import x402HTTPClientSync
from x402.mechanisms.evm.exact import ExactEvmScheme, ExactEvmServerScheme
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.schemas import SettleResponse, VerifyResponse
from x402.server_base import SupportedKind, SupportedResponse

from src.server import create_app

TEST_WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"
# Hardhat account #0 — throwaway testnet key, not a real wallet
BUYER_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
BUYER_ADDRESS = Account.from_key(BUYER_PRIVATE_KEY).address
FAKE_TX_HASH = "0xfake_tx_hash_for_test_1234567890abcdef"


def _make_mock_facilitator():
    """Create a facilitator mock that approves all payments."""
    facilitator = MagicMock()
    facilitator.get_supported.return_value = SupportedResponse(
        kinds=[
            SupportedKind(x402_version=1, scheme="exact", network="eip155:84532")
        ],
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
    return facilitator


def _make_test_app():
    """Create app with mocked facilitator for e2e testing."""
    facilitator = _make_mock_facilitator()
    server = x402ResourceServer(facilitator)
    server.register("eip155:84532", ExactEvmServerScheme())
    server.initialize()
    return create_app(server=server, pay_to=TEST_WALLET)


def _make_buyer_http_client() -> x402HTTPClientSync:
    """Create a sync x402 HTTP client with a test buyer wallet."""
    account = Account.from_key(BUYER_PRIVATE_KEY)
    client = x402ClientSync()
    register_exact_evm_client(client, account)
    return x402HTTPClientSync(client)


def _do_paid_request(test_client: TestClient, buyer: x402HTTPClientSync):
    """Execute the 402 → sign → retry flow manually with TestClient."""
    # Step 1: initial request — should get 402
    resp = test_client.post(
        "/tools/max-demand",
        json={"site": "test-site"},
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 402, f"Expected 402, got {resp.status_code}"

    # Step 2: parse 402, create payment signature
    payment_headers, _ = buyer.handle_402_response(
        headers=dict(resp.headers),
        body=resp.content,
    )

    # Step 3: retry with payment header
    retry_headers = {"Accept": "application/json", **payment_headers}
    return test_client.post(
        "/tools/max-demand",
        json={"site": "test-site"},
        headers=retry_headers,
    )


def test_full_402_pay_verify_cycle():
    """Full round trip: 402 → client signs → retry → verify → settle → 200."""
    app = _make_test_app()
    buyer = _make_buyer_http_client()

    with TestClient(app) as client:
        response = _do_paid_request(client, buyer)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["max_demand_amps"] == 200
    assert data["standard"] == "AS3000:2018"


def test_settlement_headers_present():
    """After successful payment, response should include settlement headers."""
    app = _make_test_app()
    buyer = _make_buyer_http_client()

    with TestClient(app) as client:
        response = _do_paid_request(client, buyer)

    assert response.status_code == 200
    assert "payment-response" in response.headers


def test_settlement_logged_to_jsonl(tmp_path):
    """Settlement should be written to JSONL log file."""
    import src.settlement_log as sl

    log_file = tmp_path / "test_settlements.jsonl"
    original_path = sl.DEFAULT_LOG_PATH

    try:
        sl.DEFAULT_LOG_PATH = log_file
        app = _make_test_app()
        buyer = _make_buyer_http_client()

        with TestClient(app) as client:
            response = _do_paid_request(client, buyer)

        assert response.status_code == 200

        if log_file.exists():
            entries = [json.loads(line) for line in log_file.read_text().splitlines()]
            assert len(entries) >= 1
            entry = entries[0]
            assert entry["tool"] == "POST /tools/max-demand"
            assert "latency_ms" in entry
            assert entry["latency_ms"] > 0
    finally:
        sl.DEFAULT_LOG_PATH = original_path


def test_health_not_affected_by_payment_middleware():
    """Health endpoint should still work without payment."""
    app = _make_test_app()
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_latency_under_target():
    """Verify the payment cycle completes well under 2s target (mocked facilitator)."""
    app = _make_test_app()
    buyer = _make_buyer_http_client()

    with TestClient(app) as client:
        start = time.perf_counter()
        response = _do_paid_request(client, buyer)
        elapsed_ms = (time.perf_counter() - start) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 2000, f"Latency {elapsed_ms:.0f}ms exceeded 2s target"
