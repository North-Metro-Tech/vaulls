"""Mint Coinbase CDP facilitator JWTs for x402 Authorization headers.

The Coinbase CDP x402 facilitator authenticates every /verify, /settle,
and /supported request with an ES256- or EdDSA-signed JWT passed as
``Authorization: Bearer <jwt>``. The canonical wire format is defined by
the Go SDK at ``coinbase/cdp-sdk/go/auth/jwt.go``.

This module mirrors the Go SDK exactly:

Header
    alg    "ES256" | "EdDSA"          auto-detected from secret
    kid    <key_id>                   same value as the ``sub`` claim
    nonce  <16-byte random hex>       32 lowercase hex chars
    (no ``typ`` — the Go SDK omits it. Both ``jwt.encode`` *and*
    ``jwt.api_jws.PyJWS().encode`` auto-inject ``typ: JWT``; we bypass both
    and assemble the compact JWS ourselves using PyJWT's algorithm classes
    for the signing primitive only.)

Claims
    sub   <key_id>
    iss   "cdp"                         literal string, not the key id
    iat   <now>
    nbf   <now>
    exp   <now + 120>                   matches Go default ExpiresIn
    uris  [f"{METHOD} {host}{path}"]    array, exactly one element, no
                                        scheme, no query, no port, no creds

Algorithm auto-detect (mirrors Go behaviour):
    1. Secret containing ``-----BEGIN`` → PEM EC P-256 → ES256.
    2. Otherwise base64-decode the secret; if the result is exactly 64 bytes,
       the first 32 bytes are the Ed25519 seed → EdDSA. (Go's
       ``ed25519.PrivateKey`` is 64 bytes ``seed||public``; ``cryptography``
       takes just the 32-byte seed.)
    3. Neither → ValueError.

Replay protection comes from ``exp=120s`` + the 16-byte ``nonce`` header.
No request body hash — the Go facilitator JWT does not hash the body.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from urllib.parse import urlparse

_CDP_EXTRAS_HINT = (
    "CDP facilitator authentication requires PyJWT + cryptography. "
    "Install with: pip install 'vaulls[cdp]'"
)


def _load_key_and_algo(secret: str) -> tuple[Any, str]:
    """Detect key type and return ``(signing_key, algorithm_name)``.

    Raises ``ImportError`` if the ``cdp`` extras aren't installed, and
    ``ValueError`` if the secret doesn't match either supported format.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ec import (
            EllipticCurvePrivateKey,
            SECP256R1,
        )
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key,
        )
    except ImportError as e:
        raise ImportError(_CDP_EXTRAS_HINT) from e

    if "-----BEGIN" in secret:
        key = load_pem_private_key(secret.encode("utf-8"), password=None)
        if not isinstance(key, EllipticCurvePrivateKey) or not isinstance(
            key.curve, SECP256R1
        ):
            raise ValueError(
                "VAULLS_CDP_API_KEY_SECRET: PEM key must be EC P-256 (secp256r1)"
            )
        return key, "ES256"

    try:
        decoded = base64.b64decode(secret, validate=True)
    except Exception:
        decoded = b""

    if len(decoded) == 64:
        seed = decoded[:32]
        return Ed25519PrivateKey.from_private_bytes(seed), "EdDSA"

    raise ValueError(
        "VAULLS_CDP_API_KEY_SECRET: unrecognized key format — "
        "expected PEM EC P-256 or base64 Ed25519 (64 bytes)"
    )


def build_cdp_jwt(key_id: str, key_secret: str, method: str, url: str) -> str:
    """Build a CDP facilitator JWT for a single METHOD + URL.

    Args:
        key_id: CDP API key id — used as ``kid`` header and ``sub`` claim.
        key_secret: CDP API key secret; PEM EC P-256 or base64 Ed25519.
        method: HTTP method, e.g. ``"POST"`` or ``"GET"``.
        url: Fully-qualified target URL, e.g.
            ``"https://api.cdp.coinbase.com/platform/v2/x402/verify"``.

    Returns:
        Compact JWT string ready for ``Authorization: Bearer <jwt>``.
    """
    try:
        from jwt.algorithms import get_default_algorithms
    except ImportError as e:
        raise ImportError(_CDP_EXTRAS_HINT) from e

    key, algorithm = _load_key_and_algo(key_secret)

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path
    uri = f"{method.upper()} {host}{path}"

    now = int(time.time())
    claims = {
        "sub": key_id,
        "iss": "cdp",
        "iat": now,
        "nbf": now,
        "exp": now + 120,
        "uris": [uri],
    }
    header = {
        "alg": algorithm,
        "kid": key_id,
        "nonce": os.urandom(16).hex(),
    }

    # PyJWT >=2.12 auto-injects ``typ: JWT`` in both ``jwt.encode()`` and
    # ``PyJWS().encode()``; the Go SDK omits ``typ`` entirely. Manual JWS
    # assembly is the only way to get full header control.
    alg = get_default_algorithms()[algorithm]
    signing_key = alg.prepare_key(key)
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    claims_b64 = _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    signature_b64 = _b64url(alg.sign(signing_input, signing_key))
    return f"{header_b64}.{claims_b64}.{signature_b64}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
