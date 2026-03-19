import base64
import json

TEST_WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"


def test_health_not_gated(client):
    """Health endpoint should not be gated."""
    response = client.get("/health")
    assert response.status_code == 200


def test_returns_402_without_payment(client):
    """Unauthenticated POST to a gated tool should return 402."""
    response = client.post(
        "/tools/max-demand",
        json={"site": "test"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 402


def test_402_contains_payment_requirements(client):
    """The 402 response should include payment requirements with correct details."""
    response = client.post(
        "/tools/max-demand",
        json={"site": "test"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 402

    # x402 puts payment info in the PAYMENT-REQUIRED header (base64-encoded JSON)
    payment_header = response.headers.get("payment-required")
    assert payment_header is not None, "Missing PAYMENT-REQUIRED header"

    payload = json.loads(base64.b64decode(payment_header))

    # Verify payment requirements contain correct wallet and network
    reqs = payload.get("paymentRequirements", payload.get("accepts", []))
    assert len(reqs) > 0, "No payment requirements in response"

    req = reqs[0]
    assert req["payTo"] == TEST_WALLET
    assert req["network"] == "eip155:84532"
    assert req["scheme"] == "exact"
