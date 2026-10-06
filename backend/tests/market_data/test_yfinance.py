from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import respx
from httpx import Response

from app.market_data import usd_brl
from app.market_data.base import AdapterNotFoundError
from app.market_data.yfinance_adapter import YFinanceAdapter


@pytest.fixture(autouse=True)
def reset():
    usd_brl._reset_cache_for_tests()


def _mock_fast_info(price: float | None, currency: str) -> MagicMock:
    """yfinance's fast_info is NOT a plain dict — it supports both [key]
    and .get(key, default). Use a MagicMock to emulate both."""
    data = {"last_price": price, "currency": currency}
    m = MagicMock()
    m.__getitem__.side_effect = data.__getitem__
    m.get.side_effect = lambda k, d=None: data.get(k, d)
    return m


@respx.mock
async def test_fetches_usd_and_converts_to_brl() -> None:
    respx.get(usd_brl._ENDPOINT).mock(return_value=Response(200, json={"USDBRL": {"bid": "5.0"}}))

    with patch("yfinance.Ticker") as MockTicker:
        ticker_obj = MagicMock()
        ticker_obj.fast_info = _mock_fast_info(400.0, "USD")
        MockTicker.return_value = ticker_obj

        quote = await YFinanceAdapter().fetch_price("QQQ")
        assert quote.external_id == "QQQ"
        assert quote.price_brl == pytest.approx(2000.0)  # 400 x 5


async def test_brl_ticker_passes_through_without_conversion() -> None:
    """B3 tickers (VALE3.SA) return BRL natively — no USD multiplication."""
    with patch("yfinance.Ticker") as MockTicker:
        ticker_obj = MagicMock()
        ticker_obj.fast_info = _mock_fast_info(88.79, "BRL")
        MockTicker.return_value = ticker_obj

        quote = await YFinanceAdapter().fetch_price("VALE3.SA")
        assert quote.price_brl == pytest.approx(88.79)


@respx.mock
async def test_missing_price_raises_not_found() -> None:
    respx.get(usd_brl._ENDPOINT).mock(return_value=Response(200, json={"USDBRL": {"bid": "5.0"}}))
    with patch("yfinance.Ticker") as MockTicker:
        ticker_obj = MagicMock()
        ticker_obj.fast_info = _mock_fast_info(None, "USD")
        MockTicker.return_value = ticker_obj
        with pytest.raises(AdapterNotFoundError):
            await YFinanceAdapter().fetch_price("NOPE")
