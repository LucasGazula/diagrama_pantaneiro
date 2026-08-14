from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient, Response

from app.market_data.brapi import _AVAILABLE_URL
from app.market_data.coingecko import _SEARCH_ENDPOINT
from app.market_data.yfinance_adapter import _SEARCH_URL


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass!123"},
    )
    r = await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": "StrongPass!123"},
    )
    return r.json()["access_token"]


async def test_search_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/catalog/search?type=acoes_nacionais&q=PETR")
    assert r.status_code == 401


async def test_empty_query_returns_empty_list(client: AsyncClient) -> None:
    token = await _register_and_login(client, "cat-empty@example.com")
    r = await client.get(
        "/api/catalog/search?type=acoes_nacionais&q=",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


@respx.mock
async def test_search_brapi_stocks(client: AsyncClient) -> None:
    respx.get(_AVAILABLE_URL).mock(
        return_value=Response(200, json={"stocks": ["PETR3", "PETR4", "PETRW"]})
    )
    token = await _register_and_login(client, "cat-brapi@example.com")
    r = await client.get(
        "/api/catalog/search?type=acoes_nacionais&q=PETR",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert names == ["PETR3", "PETR4", "PETRW"]


@respx.mock
async def test_search_coingecko_crypto(client: AsyncClient) -> None:
    respx.get(_SEARCH_ENDPOINT).mock(
        return_value=Response(
            200,
            json={
                "coins": [
                    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
                    {"id": "bitcoin-cash", "symbol": "bch", "name": "Bitcoin Cash"},
                ]
            },
        )
    )
    token = await _register_and_login(client, "cat-cg@example.com")
    r = await client.get(
        "/api/catalog/search?type=criptomoedas&q=btc",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "BTC"
    assert body[0]["label"] == "Bitcoin"


@respx.mock
async def test_search_yfinance_us_stocks_and_reits(client: AsyncClient) -> None:
    respx.get(_SEARCH_URL).mock(
        return_value=Response(
            200,
            json={
                "quotes": [
                    {"symbol": "AAPL", "shortname": "Apple Inc.", "exchDisp": "NASDAQ", "quoteType": "EQUITY"},
                    {"symbol": "AAPW", "shortname": "Roundhill ETF", "exchDisp": "BATS", "quoteType": "ETF"},
                ]
            },
        )
    )
    token = await _register_and_login(client, "cat-us@example.com")
    r = await client.get(
        "/api/catalog/search?type=acoes_internacionais&q=AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["name"] == "AAPL"
    assert body[0]["label"] == "Apple Inc. (NASDAQ)"

    # Also works for REITs
    r_reit = await client.get(
        "/api/catalog/search?type=reits&q=AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_reit.status_code == 200
    assert len(r_reit.json()) == 2


async def test_search_unsupported_type_returns_empty(client: AsyncClient) -> None:
    token = await _register_and_login(client, "cat-unknown@example.com")
    r = await client.get(
        "/api/catalog/search?type=unknown_type&q=test",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []

