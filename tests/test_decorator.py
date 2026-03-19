"""Tests for the @paywall decorator."""

import asyncio

from vaulls.decorator import paywall, is_paywalled, get_paywall_config


def test_paywall_attaches_config():
    @paywall(price="0.10", asset="USDC", network="base")
    def my_tool():
        return "result"

    assert is_paywalled(my_tool)
    pw = get_paywall_config(my_tool)
    assert pw is not None
    assert pw.price == "0.10"
    assert pw.asset == "USDC"
    assert pw.network == "base"


def test_paywall_preserves_function_name():
    @paywall(price="0.05")
    def calculate_something():
        return 42

    assert calculate_something.__name__ == "calculate_something"


def test_paywall_sync_function_still_callable():
    @paywall(price="0.05")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_paywall_async_function_still_callable():
    @paywall(price="0.05")
    async def async_add(a: int, b: int) -> int:
        return a + b

    result = asyncio.get_event_loop().run_until_complete(async_add(2, 3))
    assert result == 5


def test_paywall_async_preserves_vaulls_attr():
    @paywall(price="0.25", network="base")
    async def async_tool():
        return "async result"

    assert is_paywalled(async_tool)
    pw = get_paywall_config(async_tool)
    assert pw.price == "0.25"


def test_undecorated_function_not_paywalled():
    def plain_func():
        return "free"

    assert not is_paywalled(plain_func)
    assert get_paywall_config(plain_func) is None


def test_paywall_defaults():
    @paywall(price="1.00")
    def tool():
        return "result"

    pw = get_paywall_config(tool)
    assert pw.asset == "USDC"
    assert pw.network == ""  # falls back to global config
    assert pw.description == ""


def test_paywall_with_description():
    @paywall(price="0.05", description="Premium calculation")
    def tool():
        return "result"

    pw = get_paywall_config(tool)
    assert pw.description == "Premium calculation"
