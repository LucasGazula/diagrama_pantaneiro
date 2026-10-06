"""USD->BRL rate from AwesomeAPI (https://economia.awesomeapi.com.br)."""

from __future__ import annotations

import asyncio
import time

from app.market_data.base import AdapterNetworkError
from app.market_data.http_client import market_client

_ENDPOINT = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
_CACHE_TTL_SECONDS = 600  # 10 min

_cache: dict[str, tuple[float, float]] = {}  # key -> (rate, fetched_at_epoch)
_load_lock = asyncio.Lock()
_retry_after = 0.0


async def get_usd_brl_rate() -> float:
    """Current USD->BRL rate. Cached for 10 min to avoid hammering AwesomeAPI.
    On network failure, returns the last cached rate if available, else raises."""
    global _retry_after
    async with _load_lock:
        now = time.monotonic()
        cached = _cache.get("rate")
        if cached is not None and (now - cached[1] < _CACHE_TTL_SECONDS or now < _retry_after):
            return cached[0]

        try:
            async with market_client() as client:
                r = await client.get(_ENDPOINT, timeout=5.0)
                r.raise_for_status()
                data = r.json()
            rate = float(data["USDBRL"]["bid"])
        except Exception as e:
            if cached is not None:
                _retry_after = time.monotonic() + 60
                return cached[0]  # fall back to stale
            raise AdapterNetworkError(f"USD-BRL fetch failed: {e}") from e

        _cache["rate"] = (rate, time.monotonic())
        _retry_after = 0.0
        return rate


def _reset_cache_for_tests() -> None:
    global _load_lock, _retry_after
    _cache.clear()
    _load_lock = asyncio.Lock()
    _retry_after = 0.0
