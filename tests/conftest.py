"""Shared test fixtures for VAULLS."""

import pytest
from vaulls.config import reset_config


@pytest.fixture(autouse=True)
def _clean_config():
    """Reset global config between tests."""
    reset_config()
    yield
    reset_config()
