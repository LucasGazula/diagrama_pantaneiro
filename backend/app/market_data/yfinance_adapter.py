"""yfinance adapter — works for any market yfinance supports.

For BRL-denominated tickers (B3's .SA suffix), the price passes through.
For USD tickers (US stocks/REITs), price is multiplied by the current
USD-BRL rate. Other currencies raise AdapterError.

yfinance is synchronous; we wrap the blocking call in asyncio.to_thread
so the event loop isn't stalled during network I/O.
"""

from __future__ import annotations

import asyncio

from app.market_data.base import (
    AdapterError,
    AdapterNetworkError,
    AdapterNotFoundError,
    Candidate,
    PriceQuote,
)
from app.market_data.usd_brl import get_usd_brl_rate
from app.market_data.http_client import market_client

_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"


def _fetch_price_and_currency(ticker: str) -> tuple[float, str]:
    """Sync helper — yfinance's library is synchronous.

    Returns (price_in_native_currency, currency_code).
    """
    import yfinance as yf

    info = yf.Ticker(ticker)
    try:
        price = info.fast_info["last_price"]
        currency = (info.fast_info.get("currency") or "USD").upper()
    except Exception as e:
        raise AdapterNotFoundError(f"yfinance: {ticker} lookup failed: {e}") from e
    if price is None or price == 0:
        raise AdapterNotFoundError(f"yfinance: no price for {ticker}")
    return float(price), currency


class YFinanceAdapter:
    async def search(self, query: str) -> list[Candidate]:
        q = query.strip()
        if not q:
            return []
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with market_client() as client:
                r = await client.get(
                    _SEARCH_URL,
                    params={"q": q, "quotesCount": 20, "newsCount": 0},
                    headers=headers,
                    timeout=5.0,
                )
                r.raise_for_status()
                data = r.json()
        except Exception:
            return []

        quotes = data.get("quotes") or []
        candidates: list[Candidate] = []
        for quote in quotes:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            quote_type = (quote.get("quoteType") or "").upper()
            if quote_type not in ("EQUITY", "ETF", "MUTUALFUND", ""):
                continue
            short_name = (quote.get("shortname") or quote.get("longname") or "").strip()
            exch = (quote.get("exchDisp") or quote.get("exchange") or "").strip()
            if short_name and exch:
                label = f"{short_name} ({exch})"
            elif short_name:
                label = short_name
            elif exch:
                label = exch
            else:
                label = None
            candidates.append(Candidate(name=symbol, label=label))
        return candidates[:20]

    async def fetch_price(self, external_id: str) -> PriceQuote:
        ticker = external_id.upper().strip()
        try:
            price, currency = await asyncio.to_thread(_fetch_price_and_currency, ticker)
        except AdapterNotFoundError:
            raise
        except Exception as e:
            raise AdapterNetworkError(f"yfinance error for {ticker}: {e}") from e

        if currency == "BRL":
            price_brl = price
        elif currency == "USD":
            rate = await get_usd_brl_rate()
            price_brl = price * rate
        else:
            raise AdapterError(f"yfinance: unsupported currency {currency} for {ticker}")

        return PriceQuote.now(external_id=ticker, price_brl=price_brl)
