from __future__ import annotations

import asyncio
import pytest
import respx
from httpx import Response

from app.market_data import usd_brl
from app.market_data.base import AdapterNetworkError


@pytest.fixture(autouse=True)
def clear_cache():
    usd_brl._reset_cache_for_tests()


@respx.mock
async def test_fetches_rate_from_awesome_api() -> None:
    respx.get(usd_brl._ENDPOINT).mock(
        return_value=Response(200, json={"USDBRL": {"bid": "4.9922"}})
    )
    rate = await usd_brl.get_usd_brl_rate()
    assert rate == pytest.approx(4.9922)


@respx.mock
async def test_second_call_hits_cache() -> None:
    route = respx.get(usd_brl._ENDPOINT).mock(
        return_value=Response(200, json={"USDBRL": {"bid": "4.9922"}})
    )
    await usd_brl.get_usd_brl_rate()
    await usd_brl.get_usd_brl_rate()
    assert route.call_count == 1


@respx.mock
async def test_fallback_to_cache_on_network_error() -> None:
    # Prime the cache
    respx.get(usd_brl._ENDPOINT).mock(
        return_value=Response(200, json={"USDBRL": {"bid": "4.9922"}})
    )
    await usd_brl.get_usd_brl_rate()
    usd_brl._cache["rate"] = (4.9922, 0)  # force stale

    # Next call fails; should fall back to the stale cached rate
    respx.get(usd_brl._ENDPOINT).mock(side_effect=Exception("network down"))
    rate = await usd_brl.get_usd_brl_rate()
    assert rate == pytest.approx(4.9922)


@respx.mock
async def test_raises_when_no_cache_and_network_fails() -> None:
    respx.get(usd_brl._ENDPOINT).mock(side_effect=Exception("network down"))
    with pytest.raises(AdapterNetworkError):
        await usd_brl.get_usd_brl_rate()


@respx.mock
async def test_concurrent_rates_share_one_request() -> None:
    route = respx.get(usd_brl._ENDPOINT).respond(200, json={"USDBRL": {"bid": "5.0"}})
    assert await asyncio.gather(*(usd_brl.get_usd_brl_rate() for _ in range(12))) == [5.0] * 12
    assert route.call_count == 1
