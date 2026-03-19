from fastapi import FastAPI, Request
from x402 import x402ResourceServer
from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import ExactEvmServerScheme

from src.config import VAULLS_PAY_TO, FACILITATOR_URL, TOOL_PRICING


def build_routes(pay_to: str) -> dict:
    """Build x402 route config from TOOL_PRICING."""
    routes = {}
    for route_key, cfg in TOOL_PRICING.items():
        routes[route_key] = {
            "accepts": {
                "scheme": "exact",
                "payTo": pay_to,
                "price": cfg["price"],
                "network": "eip155:84532",
            },
            "description": cfg["description"],
        }
    return routes


def create_app(
    facilitator: HTTPFacilitatorClient | None = None,
    server: x402ResourceServer | None = None,
    pay_to: str | None = None,
) -> FastAPI:
    """Create the VAULLS FastAPI application.

    Args:
        facilitator: x402 facilitator client (defaults to production).
        server: x402 resource server (defaults to production).
        pay_to: Wallet address for payments (defaults to env var).
    """
    app = FastAPI(title="VAULLS", version="0.1.0")

    pay_to = pay_to or VAULLS_PAY_TO

    if server is None:
        facilitator = facilitator or HTTPFacilitatorClient({"url": FACILITATOR_URL})
        server = x402ResourceServer(facilitator)
        server.register("eip155:84532", ExactEvmServerScheme())

    routes = build_routes(pay_to)
    mw = payment_middleware(routes, server, sync_facilitator_on_start=False)

    @app.middleware("http")
    async def x402_mw(request: Request, call_next):
        return await mw(request, call_next)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/tools/max-demand")
    def calculate_max_demand(site_data: dict):
        # Stub — real logic comes in Sprint 3
        return {"max_demand_amps": 200, "standard": "AS3000:2018", "status": "compliant"}

    return app


# Default app instance for uvicorn
app = create_app()
