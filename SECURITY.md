# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| 0.1.x   | No        |
| < 0.1   | No        |

We're a small project. Only the latest release receives security patches.

## Reporting a Vulnerability

**Do NOT open a public issue for security bugs.**

Email **aaron@northmetrotech.com.au** with:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment (if known)

### Response Timeline

- **Acknowledgement:** Within 48 hours
- **Critical patches:** Aim for 7 days
- **Non-critical:** Next release cycle

## Scope

This policy covers the **VAULLS library itself** — the `vaulls` Python package and its integration code.

**Out of scope:**

- Third-party dependencies (x402, FastAPI, MCP SDK, etc.) — report those upstream
- The x402 facilitator service
- Base network or USDC contract issues

## Trust Boundary

VAULLS is a **payment gating layer**. It orchestrates x402 payment flows but:

- Does **not** custody funds
- Does **not** hold or store private keys
- Does **not** store wallet credentials
- Does **not** perform on-chain settlement directly

All payment verification and settlement is handled by the [x402 facilitator](https://x402.org). VAULLS attaches pricing metadata to your endpoints and delegates payment verification to the facilitator via the x402 protocol.

Security researchers should understand this trust boundary when evaluating the library.

## Credit

We credit reporters in the [CHANGELOG](CHANGELOG.md) unless you prefer to remain anonymous. Let us know your preference when reporting.
