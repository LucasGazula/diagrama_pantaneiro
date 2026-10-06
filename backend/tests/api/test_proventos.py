from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from httpx import AsyncClient
import pandas as pd
import pytest

from app.models.dividend import Dividend
from app.market_data.base import AdapterNetworkError
from app.services.dividend_service import _fetch_ticker_dividends_sync


async def _register_login_seed(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass!123"},
    )
    r = await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": "StrongPass!123"},
    )
    return r.json()["access_token"]


async def test_proventos_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/proventos")
    assert r.status_code == 401
    r2 = await client.post("/api/proventos/sync")
    assert r2.status_code == 401


def test_failed_history_is_reported_instead_of_replacing_cache_with_empty_data() -> None:
    ticker = Mock()
    type(ticker).dividends = PropertyMock(side_effect=RuntimeError("network down"))
    ticker.calendar = {}
    with (
        patch("app.services.dividend_service._fetch_fundamentus_sync", return_value={}),
        patch("yfinance.Ticker", return_value=ticker),
        pytest.raises(AdapterNetworkError),
    ):
        _fetch_ticker_dividends_sync("BBAS3", "acoes_nacionais")


def test_fetch_ticker_dividends_reads_yfinance_series() -> None:
    ticker = Mock()
    ticker.dividends = pd.Series(
        [0.25, 0.75],
        index=pd.to_datetime(["2026-08-01", "2026-09-01"]),
    )
    ticker.calendar = {}

    with (
        patch("app.services.dividend_service._fetch_fundamentus_sync", return_value={}),
        patch("yfinance.Ticker", return_value=ticker) as ticker_factory,
    ):
        items = _fetch_ticker_dividends_sync("bbas3", "acoes_nacionais")

    ticker_factory.assert_called_once_with("BBAS3.SA")
    assert [(item["payment_date"], item["amount_per_share"]) for item in items] == [
        (date(2026, 8, 1), 0.25),
        (date(2026, 9, 1), 0.75),
    ]


async def test_sync_only_fetches_active_portfolio_positions(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "proventos_scope@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    first_position = await client.post(
        "/api/positions",
        headers=headers,
        json={
            "name": "BBAS3",
            "assetType": "acoes_nacionais",
            "amount": 100.0,
            "currentPrice": 30.0,
            "strength": 8,
        },
    )
    assert first_position.status_code == 201

    second_portfolio = await client.post(
        "/api/portfolios", headers=headers, json={"name": "Carteira internacional"}
    )
    assert second_portfolio.status_code == 201
    second_headers = {
        **headers,
        "X-Portfolio-Id": second_portfolio.json()["id"],
    }
    second_position = await client.post(
        "/api/positions",
        headers=second_headers,
        json={
            "name": "AAPL",
            "assetType": "acoes_internacionais",
            "amount": 10.0,
            "currentPrice": 200.0,
            "strength": 8,
        },
    )
    assert second_position.status_code == 201

    fetched: list[str] = []

    def mock_fetch(ticker: str, asset_type: str):
        fetched.append(ticker)
        return []

    with patch(
        "app.services.dividend_service._fetch_ticker_dividends_sync", side_effect=mock_fetch
    ):
        sync_res = await client.post("/api/proventos/sync", headers=second_headers)

    assert sync_res.status_code == 200
    assert sync_res.json()["syncedTickers"] == 1
    assert fetched == ["AAPL"]


async def test_proventos_sync_and_get(client: AsyncClient, session_maker) -> None:
    token = await _register_login_seed(client, "proventos@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Add positions
    r_pos1 = await client.post(
        "/api/positions",
        headers=headers,
        json={
            "name": "BBAS3",
            "assetType": "acoes_nacionais",
            "amount": 100.0,
            "currentPrice": 30.0,
            "strength": 8,
        },
    )
    assert r_pos1.status_code == 201

    r_pos2 = await client.post(
        "/api/positions",
        headers=headers,
        json={
            "name": "AAPL",
            "assetType": "acoes_internacionais",
            "amount": 10.0,
            "currentPrice": 200.0,
            "strength": 8,
        },
    )
    assert r_pos2.status_code == 201

    fake_bbas3_divs = [
        {
            "ticker": "BBAS3",
            "payment_date": date(2026, 9, 15),
            "ex_date": date(2026, 9, 1),
            "amount_per_share": 0.50,
            "currency": "BRL",
            "dividend_type": "Dividendo",
        }
    ]
    fake_aapl_divs = [
        {
            "ticker": "AAPL",
            "payment_date": date(2026, 9, 20),
            "ex_date": date(2026, 9, 5),
            "amount_per_share": 1.0,
            "currency": "USD",
            "dividend_type": "Dividendo",
        }
    ]

    def mock_fetch(ticker, asset_type):
        if ticker == "BBAS3":
            return fake_bbas3_divs
        if ticker == "AAPL":
            return fake_aapl_divs
        return []

    with (
        patch("app.services.dividend_service._fetch_ticker_dividends_sync", side_effect=mock_fetch),
        patch("app.services.dividend_service.get_usd_brl_rate", new=AsyncMock(return_value=5.0)),
    ):
        sync_res = await client.post("/api/proventos/sync", headers=headers)
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["syncedTickers"] == 2
        assert sync_data["failedTickers"] == []
        assert sync_data["totalDividendsStored"] >= 2

        # Query proventos for September 2026
        get_res = await client.get("/api/proventos?year=2026&month=9", headers=headers)
        assert get_res.status_code == 200
        cal_data = get_res.json()
        assert cal_data["year"] == 2026
        assert cal_data["month"] == 9
        assert cal_data["usdRate"] == 5.0
        assert len(cal_data["items"]) == 2

        # BBAS3: 100 shares * 0.50 BRL = 50.0 BRL
        # AAPL: 10 shares * 1.0 USD * 5.0 rate = 50.0 BRL
        assert cal_data["totalMonthBrl"] == 100.0


async def test_proventos_date_mode_ex(client: AsyncClient, session_maker) -> None:
    token = await _register_login_seed(client, "proventos_ex@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/positions",
        headers=headers,
        json={
            "name": "HGLG11",
            "assetType": "fundos_imobiliarios",
            "amount": 50.0,
            "currentPrice": 160.0,
            "strength": 9,
        },
    )

    async with session_maker() as session:
        div = Dividend(
            ticker="HGLG11",
            payment_date=date(2026, 10, 15),
            ex_date=date(2026, 9, 30),
            amount_per_share=1.10,
            currency="BRL",
            dividend_type="Rendimento",
        )
        session.add(div)
        await session.commit()

    with patch("app.services.dividend_service.get_usd_brl_rate", new=AsyncMock(return_value=5.0)):
        # Under payment_date mode for September 2026 -> 0 items (payment is in Oct)
        r_pay = await client.get(
            "/api/proventos?year=2026&month=9&date_mode=payment", headers=headers
        )
        assert r_pay.status_code == 200
        assert len(r_pay.json()["items"]) == 0

        # Under ex_date mode for September 2026 -> 1 item (ex_date is 2026-09-30)
        r_ex = await client.get("/api/proventos?year=2026&month=9&date_mode=ex", headers=headers)
        assert r_ex.status_code == 200
        assert len(r_ex.json()["items"]) == 1
        item = r_ex.json()["items"][0]
        assert item["ticker"] == "HGLG11"
        assert item["totalBrl"] == 55.0  # 50 * 1.10


async def test_proventos_jcp_deducts_fifteen_percent_tax(
    client: AsyncClient, session_maker
) -> None:
    token = await _register_login_seed(client, "proventos_jcp@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 100 shares of BBAS3
    await client.post(
        "/api/positions",
        headers=headers,
        json={
            "name": "BBAS3",
            "assetType": "acoes_nacionais",
            "amount": 100.0,
            "currentPrice": 30.0,
            "strength": 8,
        },
    )

    # Add JCP dividend
    async with session_maker() as session:
        div = Dividend(
            ticker="BBAS3",
            payment_date=date(2026, 9, 15),
            ex_date=date(2026, 9, 1),
            amount_per_share=1.00,  # 1.00 gross per share
            currency="BRL",
            dividend_type="JRS CAP PROPRIO",
        )
        session.add(div)
        await session.commit()

    with patch("app.services.dividend_service.get_usd_brl_rate", new=AsyncMock(return_value=5.0)):
        res = await client.get("/api/proventos?year=2026&month=9", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["isJcp"] is True
        assert item["taxRate"] == 0.15
        assert item["rateBrl"] == 1.00
        assert item["rateNetBrl"] == 0.85
        assert item["totalBrl"] == 100.00
        assert item["totalNetBrl"] == 85.00
        assert item["taxBrl"] == 15.00
        assert data["totalMonthBrl"] == 100.00
        assert data["totalMonthNetBrl"] == 85.00
        assert data["totalTaxBrl"] == 15.00
