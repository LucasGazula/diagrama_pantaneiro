"""Brapi.dev adapter for Brazilian-listed securities (B3).

Used for ações nacionais (VALE3, BBAS3, etc.) and fundos imobiliários
(HGLG11, etc.). Prices are already in BRL so no conversion needed.
"""

from __future__ import annotations

import os

import httpx

from app.market_data.base import (
    AdapterNetworkError,
    AdapterNotFoundError,
    Candidate,
    PriceQuote,
)
from app.market_data.http_client import market_client

_BASE_URL = "https://brapi.dev/api/quote"
_AVAILABLE_URL = "https://brapi.dev/api/available"


class BrapiAdapter:
    async def search(self, query: str) -> list[Candidate]:
        """Brapi's /api/available endpoint returns matching tickers WITHOUT
        requiring BRAPI_TOKEN (unlike /api/quote). Free to use for search."""
        q = query.strip()
        if not q:
            return []
        try:
            async with market_client() as client:
                r = await client.get(_AVAILABLE_URL, params={"search": q}, timeout=5.0)
                r.raise_for_status()
                data = r.json()
        except Exception:
            return []

        stocks = data.get("stocks") or []
        # Limit to 20 to keep the dropdown manageable
        return [Candidate(name=s) for s in stocks[:20]]

    async def fetch_price(self, external_id: str) -> PriceQuote:
        ticker = external_id.upper().strip()
        token = os.getenv("BRAPI_TOKEN")
        params = {"token": token} if token else {}
        try:
            async with market_client() as client:
                r = await client.get(f"{_BASE_URL}/{ticker}", params=params)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise AdapterNotFoundError(f"Brapi: {ticker} not found") from e
            raise AdapterNetworkError(f"Brapi HTTP {e.response.status_code} for {ticker}") from e
        except Exception as e:
            raise AdapterNetworkError(f"Brapi network error for {ticker}: {e}") from e

        results = data.get("results") or []
        if not results:
            raise AdapterNotFoundError(f"Brapi: empty results for {ticker}")
        price = results[0].get("regularMarketPrice")
        if price is None:
            raise AdapterNotFoundError(f"Brapi: no regularMarketPrice for {ticker}")
        return PriceQuote.now(external_id=ticker, price_brl=float(price))
