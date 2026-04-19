"""Mainnet smoke test — makes a real x402 payment to /tools/expert-review.

Usage (PowerShell):
    $env:BUYER_PRIVATE_KEY = "0xYourPrivateKey"
    python examples/smoke_test.py

The BUYER_PRIVATE_KEY must belong to an account with USDC on Base mainnet.
"""

import base64
import json
import os
import sys

import httpx
from eth_account import Account
from x402 import x402ClientSync, parse_payment_required
from x402.mechanisms.evm.exact import ExactEvmClientScheme

SERVER_URL = os.getenv("SMOKE_TEST_SERVER", "http://localhost:8000")
ENDPOINT = f"{SERVER_URL}/tools/expert-review"
NETWORK = "eip155:8453"  # Base mainnet


def main():
    private_key = os.getenv("BUYER_PRIVATE_KEY")
    if not private_key:
        print("ERROR: Set BUYER_PRIVATE_KEY environment variable")
        sys.exit(1)

    account = Account.from_key(private_key)
    print(f"Buyer wallet: {account.address}")

    # Step 1 — call without payment, expect 402
    print(f"\nPOST {ENDPOINT} (no payment)...")
    r1 = httpx.post(ENDPOINT, json={}, follow_redirects=False)
    print(f"  Status: {r1.status_code}")
    assert r1.status_code == 402, f"Expected 402, got {r1.status_code}"

    payment_required_header = r1.headers.get("payment-required") or r1.headers.get("x-payment-required")
    if not payment_required_header:
        print("ERROR: No payment-required header in 402 response")
        print("Headers:", dict(r1.headers))
        sys.exit(1)

    decoded = json.loads(base64.b64decode(payment_required_header))
    payment_required = parse_payment_required(decoded)
    print(f"  Payment required: {payment_required}")

    # Step 2 — build signed payment payload
    print("\nSigning payment...")
    client = x402ClientSync()
    client.register(NETWORK, ExactEvmClientScheme(signer=account))

    payload = client.create_payment_payload(payment_required)
    x_payment = base64.b64encode(
        json.dumps(payload.model_dump() if hasattr(payload, "model_dump") else payload.__dict__).encode()
    ).decode()

    # Step 3 — retry with X-PAYMENT header
    print(f"\nPOST {ENDPOINT} (with payment)...")
    r2 = httpx.post(
        ENDPOINT,
        json={},
        headers={"X-PAYMENT": x_payment},
    )
    print(f"  Status: {r2.status_code}")
    print(f"  Body:   {r2.text[:500]}")

    if r2.status_code == 200:
        print("\n✓ SMOKE TEST PASSED — real USDC payment settled on Base mainnet")
        tx = r2.headers.get("payment-response", "")
        if tx:
            try:
                settlement = json.loads(base64.b64decode(tx))
                print(f"  tx_hash:  {settlement.get('transaction', 'n/a')}")
                print(f"  payer:    {settlement.get('payer', 'n/a')}")
                print(f"  amount:   {settlement.get('amount', 'n/a')}")
                print(f"  network:  {settlement.get('network', 'n/a')}")
                print(f"\n  BaseScan: https://basescan.org/tx/{settlement.get('transaction', '')}")
            except Exception as e:
                print(f"  Warning: could not decode payment-response header: {e}")
    else:
        print(f"\n✗ SMOKE TEST FAILED — status {r2.status_code}")
        sys.exit(1)


if __name__ == "__main__":
    main()
