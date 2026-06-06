"""CoinGecko adapter for crypto. Returns BRL directly via vs_currencies=brl."""

from __future__ import annotations

import httpx

from app.market_data.base import (
    AdapterNetworkError,
    AdapterNotFoundError,
    Candidate,
    PriceQuote,
)

_ENDPOINT = "https://api.coingecko.com/api/v3/simple/price"
_SEARCH_ENDPOINT = "https://api.coingecko.com/api/v3/search"

# Symbol -> CoinGecko coin id. Expand as needed.
SYMBOL_TO_ID: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "XRP": "ripple",
    "DOT": "polkadot",
    "DOGE": "dogecoin",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "AVAX": "avalanche-2",
}


def resolve_coin_id(symbol_or_id: str) -> str:
    """Accept either a ticker symbol (BTC) or a CoinGecko id (bitcoin).
    Falls through to lowercased input if not in the known map."""
    s = symbol_or_id.strip()
    up = s.upper()
    return SYMBOL_TO_ID.get(up, s.lower())


class CoinGeckoAdapter:
    async def search(self, query: str) -> list[Candidate]:
        """CoinGecko /search returns matching coins by name/symbol."""
        q = query.strip()
        if not q:
            return []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(_SEARCH_ENDPOINT, params={"query": q})
                r.raise_for_status()
                data = r.json()
        except Exception:
            return []

        coins = (data.get("coins") or [])[:15]
        results: list[Candidate] = []
        for c in coins:
            symbol = (c.get("symbol") or "").upper()
            name = c.get("name") or symbol
            if not symbol:
                continue
            # Use symbol as the position name (matches how positions are stored)
            results.append(Candidate(name=symbol, label=name))
        return results

    async def fetch_price(self, external_id: str) -> PriceQuote:
        coin_id = resolve_coin_id(external_id)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    _ENDPOINT, params={"ids": coin_id, "vs_currencies": "brl"}
                )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            raise AdapterNetworkError(f"CoinGecko error for {coin_id}: {e}") from e

        entry = data.get(coin_id)
        if not entry or "brl" not in entry:
            raise AdapterNotFoundError(f"CoinGecko: no BRL price for {coin_id}")
        price = float(entry["brl"])
        if price <= 0:
            raise AdapterNotFoundError(f"CoinGecko: zero/negative price for {coin_id}")
        return PriceQuote.now(external_id=external_id, price_brl=price)
