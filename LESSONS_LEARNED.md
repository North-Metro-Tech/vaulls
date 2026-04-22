# Lessons Learned — VAULLS

Captured on 2026-04-19 after the v0.2.0 mainnet-verified release. This was a
practice run before the main project, so these lessons are written for future
me (or anyone doing something similar).

## 1. Nail the distribution model before writing a single line of code

VAULLS was almost built as the wrong thing. The first draft was a standalone
payment gateway that MCP servers would call out to. The intent was always
"a pip-installable library that drops into an existing MCP server" — like a
WordPress plugin, not a separate service.

**Lesson:** before building, write down the install command and the
first-use snippet. If they look like `pip install x` + `@x.decorator` the
architecture is a library. If they look like `docker run x` it's a service.
Two completely different codebases.

## 2. The testnet facilitator was a dead end — verify the production path early

Days were spent making the x402.org testnet facilitator work before
discovering the community consensus: it doesn't support Base mainnet and
never will. Coinbase CDP is the real production facilitator.

**Lesson:** for payment / auth / external-service integrations, the first
smoke test should hit the *production* service (with a throwaway
resource), not the sandbox. Sandboxes lie, production doesn't.

## 3. Auth headers are harder than the docs admit

The CDP facilitator requires `Authorization: Bearer <ES256/EdDSA JWT>` with
a very specific claim structure. Three traps:

- **`typ` header:** PyJWT auto-injects `typ: JWT` in every code path.
  CDP (following the Go SDK) rejects JWTs that include it. Had to bypass
  PyJWS entirely and assemble the compact JWS manually using PyJWT's
  algorithm classes only for the signing primitive.
- **`uris` claim:** plural, array of one element, format
  `"METHOD host/path"` — no scheme, no query, no port, no creds. Easy to
  get wrong because most JWT examples use a single string.
- **Key format auto-detect:** CDP offers both PEM EC P-256 (ES256) and
  base64 Ed25519 (EdDSA). The secret string looks different enough that
  you can auto-detect — but only if you know to check.

**Lesson:** when integrating with a service that has a Go/TS SDK but no
Python SDK, read the reference SDK source directly. Don't trust generic
JWT tutorials.

## 4. Wire-format quirks you only discover by reading the server source

The x402 v2 protocol uses the `PAYMENT-SIGNATURE` HTTP header for signed
payment payloads — not `X-PAYMENT` as much of the informal documentation
suggests. The payload itself must be Pydantic-serialized
(`model_dump_json()`), not built manually from a dict — field ordering
and nested type coercion matter for signature verification.

**Lesson:** when a request comes back with a generic 402 / 400, grep the
server source for the exact header name and parsing function. "The docs
say X" is not a good enough debug strategy.

## 5. End-to-end smoke tests catch what unit tests can't

97 unit tests passed green the whole way through. They all mocked the
facilitator. The real bugs — wrong header name, wrong payload
serialization, missing `typ` stripping — only surfaced when a real wallet
signed a real EIP-712 payment against a real CDP facilitator.

**Lesson:** mocks verify that your code does what you told it to do. They
don't verify that what you told it to do is what the other side expects.
Budget time for at least one real end-to-end test per integration boundary.

## 6. Version numbers are a product signal, not a file counter

Moving from sepolia-only to mainnet-ready felt like a 1.0 milestone. It
isn't. 1.0 means "I commit to this public API, breaking changes are a big
deal, write integration code against this with confidence." 0.x means "I
might rename things next week." VAULLS has zero production users — it
stays 0.x until that changes.

**Lesson:** 1.0 is a commitment to stability, not a reward for progress.
Don't burn it on a milestone nobody is depending on yet.

## 7. Windows vs POSIX shell differences cost real time

A non-trivial amount of time went into:

- `export X=y` (bash) vs `$env:X = "y"` (PowerShell)
- `uvicorn ...` (installed in PATH via pip) vs `python -m uvicorn ...`
  (always works)
- PowerShell here-strings (`@" ... "@`) for multi-line PEM secrets

**Lesson:** when writing examples for a library, write both shell flavours.
Prefer `python -m <module>` over bare commands — it always works. For env
vars, document both forms in the README.

## 8. CDP API key secrets are one-shot — save them immediately

The CDP portal shows the private key exactly once, at creation time. If
you miss it, you delete the key and start over. The Key ID looks like
`organizations/abc/apiKeys/xyz` (a path-style string). The secret is a
separate PEM block or a base64 string. Easy to conflate.

**Lesson:** whenever a service says "copy this now, we won't show it
again" — that's a hard instruction, not a suggestion. Paste into a
password manager before closing the tab.

## 9. Scope discipline: build the one thing, not the adjacent things

At one point I was about to build a demo MCP server inside the VAULLS repo
to "test against." That's wrong — VAULLS is a library that plugs into
*existing* MCP servers. The test is: does it work on an existing server?
Not: can I build a server that proves itself.

**Lesson:** when the library is "glue that goes into someone else's
codebase," the integration test environment should be a minimal example
of someone else's codebase, not a second codebase inside yours.

## 10. Trusted publishing beats API tokens

PyPI trusted publishing via GitHub Actions (OIDC) means no API token lives
anywhere. The `publish.yml` workflow triggers on GitHub Release
`published`, claims a short-lived OIDC token, and PyPI verifies the claim
against the configured trusted publisher. No secrets to rotate, no tokens
to leak.

**Lesson:** default to OIDC for anything that publishes artifacts. The
setup is a five-minute UI click on PyPI + a workflow file. Long-lived API
tokens should be the exception, not the default.

## Applied to the real project

Concrete things to carry over:

- Read the Go/TS reference SDK source before writing the Python client
- Write the production smoke test on day one, not the day before launch
- Plan the `pip install x` + first-use snippet before coding
- Set up PyPI trusted publishing on day one, not release day
- Test on Windows and Linux from the start, not at the end
- Keep the repo at `0.x.x` until real users are depending on it
