import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from x402 import x402ResourceServer
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server_base import SupportedKind, SupportedResponse

from src.server import create_app

TEST_WALLET = "0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b"


def _make_test_server() -> x402ResourceServer:
    """Create an x402 server with a mocked facilitator for testing."""
    facilitator = MagicMock()
    facilitator.get_supported.return_value = SupportedResponse(
        kinds=[
            SupportedKind(
                x402_version=1,
                scheme="exact",
                network="eip155:84532",
            )
        ],
    )

    server = x402ResourceServer(facilitator)
    server.register("eip155:84532", ExactEvmServerScheme())
    server.initialize()
    return server


@pytest.fixture
def client():
    """Test client with mocked facilitator."""
    server = _make_test_server()
    app = create_app(server=server, pay_to=TEST_WALLET)
    return TestClient(app)
