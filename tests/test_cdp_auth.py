"""Tests for CDP facilitator JWT authentication (Go SDK parity).

Pins the exact wire format of the ``Authorization`` header sent to the
Coinbase CDP x402 facilitator: an ES256 or EdDSA JWT whose claim set
and header shape match ``coinbase/cdp-sdk/go/auth/jwt.go``.
"""

from __future__ import annotations

import base64
import builtins
import json
import re

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from vaulls import configure
from vaulls.config import get_config, reset_config
from vaulls.integrations.fastapi import _build_cdp_auth

CDP_URL = "https://api.cdp.coinbase.com/platform/v2/x402"
EXPECTED_HOST = "api.cdp.coinbase.com"
EXPECTED_PATH = "/platform/v2/x402"
KEY_ID = "test-key-id-12345"
WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def es256_keys():
    """Generate an ephemeral P-256 keypair. Returns (pem_secret, public_key)."""
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pem, priv.public_key()


@pytest.fixture
def eddsa_keys():
    """Generate an ephemeral Ed25519 keypair. Returns (base64_secret, public_key).

    Secret is base64(seed || public) — matches Go's ``ed25519.PrivateKey``
    serialization (64 bytes total).
    """
    priv = Ed25519PrivateKey.generate()
    seed = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    secret_b64 = base64.b64encode(seed + pub_bytes).decode("ascii")
    return secret_b64, priv.public_key()


@pytest.fixture(autouse=True)
def _reset():
    reset_config()
    yield
    reset_config()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_token(auth_header: str) -> str:
    assert auth_header.startswith("Bearer "), auth_header
    return auth_header[len("Bearer "):]


def _raw_header(token: str) -> dict:
    """Base64-decode the JWS header segment verbatim — no PyJWT normalization."""
    header_b64 = token.split(".")[0]
    padded = header_b64 + "=" * ((4 - len(header_b64) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _assert_header(token: str, algorithm: str) -> None:
    header = _raw_header(token)
    assert header["alg"] == algorithm
    assert header["kid"] == KEY_ID
    assert re.fullmatch(r"[0-9a-f]{32}", header["nonce"]), header["nonce"]
    # Go SDK omits `typ` entirely. PyJWT's high-level `jwt.encode` auto-injects
    # `typ: JWT`, so the implementation uses PyJWS directly. This guards that.
    assert "typ" not in header, header


def _assert_claims(token: str, public_key, algorithm: str, expected_uri: str) -> None:
    claims = jwt.decode(
        token,
        public_key,
        algorithms=[algorithm],
        options={"verify_aud": False},
    )
    assert claims["sub"] == KEY_ID
    assert claims["iss"] == "cdp"
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == 120
    assert isinstance(claims["uris"], list)
    assert len(claims["uris"]) == 1
    assert claims["uris"][0] == expected_uri


ENDPOINTS = [
    ("verify", "POST", "/verify"),
    ("settle", "POST", "/settle"),
    ("supported", "GET", "/supported"),
]


def _configure(secret: str, url: str = CDP_URL) -> None:
    configure(
        pay_to=WALLET,
        facilitator_url=url,
        cdp_api_key_id=KEY_ID,
        cdp_api_key_secret=secret,
    )


# ---------------------------------------------------------------------------
# Happy paths — both algorithms
# ---------------------------------------------------------------------------


class TestES256:
    def test_all_endpoints_have_valid_jwt(self, es256_keys):
        secret, public_key = es256_keys
        _configure(secret)
        provider = _build_cdp_auth(get_config())
        assert provider is not None
        headers = provider.get_auth_headers()

        for endpoint, method, suffix in ENDPOINTS:
            auth_dict = getattr(headers, endpoint)
            token = _extract_token(auth_dict["Authorization"])
            _assert_header(token, "ES256")
            _assert_claims(
                token,
                public_key,
                "ES256",
                f"{method} {EXPECTED_HOST}{EXPECTED_PATH}{suffix}",
            )

    def test_fresh_jwt_per_call(self, es256_keys):
        """x402 invokes our callable on every request — tokens must differ
        per-call (fresh nonce + fresh timestamp window)."""
        secret, _ = es256_keys
        _configure(secret)
        provider = _build_cdp_auth(get_config())

        h1 = provider.get_auth_headers().verify["Authorization"]
        h2 = provider.get_auth_headers().verify["Authorization"]
        assert h1 != h2


class TestEdDSA:
    def test_all_endpoints_have_valid_jwt(self, eddsa_keys):
        secret, public_key = eddsa_keys
        _configure(secret)
        provider = _build_cdp_auth(get_config())
        assert provider is not None
        headers = provider.get_auth_headers()

        for endpoint, method, suffix in ENDPOINTS:
            auth_dict = getattr(headers, endpoint)
            token = _extract_token(auth_dict["Authorization"])
            _assert_header(token, "EdDSA")
            _assert_claims(
                token,
                public_key,
                "EdDSA",
                f"{method} {EXPECTED_HOST}{EXPECTED_PATH}{suffix}",
            )


# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------


class TestTestnetRegression:
    def test_no_keys_returns_none(self):
        configure(pay_to=WALLET, facilitator_url="https://x402.org/facilitator")
        assert _build_cdp_auth(get_config()) is None

    def test_only_key_id_returns_none(self):
        configure(
            pay_to=WALLET,
            facilitator_url=CDP_URL,
            cdp_api_key_id=KEY_ID,
            cdp_api_key_secret="",
        )
        assert _build_cdp_auth(get_config()) is None

    def test_only_secret_returns_none(self, es256_keys):
        secret, _ = es256_keys
        configure(
            pay_to=WALLET,
            facilitator_url=CDP_URL,
            cdp_api_key_id="",
            cdp_api_key_secret=secret,
        )
        assert _build_cdp_auth(get_config()) is None


class TestCanonicalization:
    def test_strips_port_and_userinfo(self, es256_keys):
        secret, public_key = es256_keys
        _configure(
            secret,
            url="https://user:pw@api.cdp.coinbase.com:443/platform/v2/x402",
        )
        provider = _build_cdp_auth(get_config())
        token = _extract_token(provider.get_auth_headers().verify["Authorization"])
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
        assert claims["uris"] == [f"POST {EXPECTED_HOST}{EXPECTED_PATH}/verify"]


class TestMissingDependency:
    def test_absent_jwt_raises_import_error_with_extras_hint(
        self, monkeypatch, es256_keys
    ):
        """Simulate PyJWT not being installed (as a user who did
        ``pip install vaulls`` without ``[cdp]`` would see). The error must
        name the ``vaulls[cdp]`` extra so they know how to fix it."""
        secret, _ = es256_keys
        _configure(secret)
        provider = _build_cdp_auth(get_config())
        assert provider is not None

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "jwt" or name.startswith("jwt."):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        # Lazy-import design: the ImportError surfaces when the callable
        # is invoked on an outgoing request, not at config time.
        with pytest.raises(ImportError, match=r"vaulls\[cdp\]"):
            provider.get_auth_headers()
