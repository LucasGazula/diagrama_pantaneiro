"""Background periodic task scheduler for price updates (every 15 min) and dividend sync (daily)."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
import os
import time

import app.models  # noqa: F401
from app.core.db import get_async_session_maker
from app.services.dividend_service import sync_portfolio_dividends
from app.services.refresh_prices import refresh_portfolio_prices

logger = logging.getLogger("uvicorn.error")

_scheduler_task: asyncio.Task | None = None


async def _run_loop() -> None:
    logger.info("Background scheduler started (prices: 15m, dividends: daily)")
    session_maker = get_async_session_maker()
    last_price_refresh: float = 0.0
    last_dividend_sync_date: date | None = None

    # Brief delay on startup so web server stabilizes and passes initial healthcheck
    await asyncio.sleep(15)

    while True:
        now = time.time()
        today = date.today()

        # 1. Price refresh every 15 minutes (900 seconds)
        if now - last_price_refresh >= 15 * 60:
            try:
                async with session_maker() as session:
                    res = await refresh_portfolio_prices(session, only_stale=True)
                    logger.info(
                        "Periodic price refresh complete: %d refreshed, %d failed",
                        res.refreshed,
                        len(res.failed),
                    )
                last_price_refresh = now
            except Exception as e:
                logger.warning("Periodic price refresh failed: %s", e)

        # 2. Dividend sync once a day
        if last_dividend_sync_date != today:
            try:
                async with session_maker() as session:
                    div_res = await sync_portfolio_dividends(session)
                    logger.info(
                        "Daily dividend sync complete: %d synced, %d stored",
                        div_res.synced_tickers,
                        div_res.total_dividends_stored,
                    )
                last_dividend_sync_date = today
            except Exception as e:
                logger.warning("Daily dividend sync failed: %s", e)

        # Sleep 60 seconds before next check
        await asyncio.sleep(60)


def start_scheduler() -> None:
    global _scheduler_task
    # Do not run background tasks during pytest or test runners
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
        return
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_run_loop())


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
