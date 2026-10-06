"""Price adapter contracts.

Each external market data source implements PriceProvider.fetch_price(external_id)
returning a PriceQuote in BRL. The caller (refresh service) treats all adapters
interchangeably; currency conversion and per-source quirks live here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

# Shared by price and dividend syncs, including overlapping HTTP/background jobs.
FETCH_CONCURRENCY = 2
fetch_slots = asyncio.Semaphore(FETCH_CONCURRENCY)


@dataclass(frozen=True)
class PriceQuote:
    external_id: str
    price_brl: float
    fetched_at: datetime
    as_of: datetime | None = None
    stale: bool = False

    @staticmethod
    def now(external_id: str, price_brl: float) -> "PriceQuote":
        return PriceQuote(
            external_id=external_id,
            price_brl=price_brl,
            fetched_at=datetime.now(timezone.utc),
        )


class AdapterError(Exception):
    """Base class for adapter failures. Carries a human-readable reason."""


class AdapterNotFoundError(AdapterError):
    """External ID didn't resolve to a price (unknown ticker etc.)."""


class AdapterNetworkError(AdapterError):
    """HTTP failure, timeout, or malformed response."""


@dataclass(frozen=True)
class Candidate:
    """A suggestion returned by an adapter's search() method.

    `name` is what the user types as a position name (e.g. "PETR4" or
    "Tesouro Renda+ 2064"). `label` is a human-friendlier description
    for display. `current_price_brl` is optional — adapters that can
    cheaply include it do, others leave it None."""

    name: str
    label: str | None = None
    current_price_brl: float | None = None
    external_id: str | None = None
    quote_as_of: datetime | None = None


class PriceProvider(Protocol):
    """Every adapter exposes fetch_price(external_id) -> PriceQuote in BRL."""

    async def fetch_price(self, external_id: str) -> PriceQuote: ...


class Searchable(Protocol):
    """Adapters that support catalog search implement this additionally.
    yfinance does not (no clean search API)."""

    async def search(self, query: str) -> list[Candidate]: ...
