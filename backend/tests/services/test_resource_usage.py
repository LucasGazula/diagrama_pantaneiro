"""Regression checks for bounded work and preservation of portfolio data."""

import asyncio
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, func, select

from app.market_data.base import AdapterNetworkError, PriceQuote
from app.models.dividend import Dividend
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.services import dividend_service as dividends
from app.services import refresh_prices as prices


@pytest.fixture(autouse=True)
def clear_sync_state(monkeypatch):
    dividends._last_sync.clear()
    slots = asyncio.Semaphore(2)
    monkeypatch.setattr(prices, "fetch_slots", slots)
    monkeypatch.setattr(dividends, "fetch_slots", slots)
    yield
    dividends._last_sync.clear()


async def seed_positions(session_maker, count=1):
    async with session_maker() as session:
        portfolio = Portfolio(user_id=uuid.uuid4(), name="Resources", is_default=True)
        session.add(portfolio)
        await session.flush()
        positions = [
            Position(
                user_id=portfolio.user_id,
                portfolio_id=portfolio.id,
                name=f"ASSET{i}",
                asset_type="acoes_internacionais",
                amount=10,
                current_price=100,
                strength=5,
            )
            for i in range(count)
        ]
        session.add_all(positions)
        await session.commit()
        return portfolio.id, [p.id for p in positions]


async def test_background_refresh_skips_fresh_prices_but_manual_refresh_does_not(
    session_maker,
    monkeypatch,
):
    portfolio_id, ids = await seed_positions(session_maker, 2)
    async with session_maker() as session:
        stale = await session.get(Position, ids[0])
        stale.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()
    adapter = AsyncMock()
    adapter.fetch_price.return_value = PriceQuote.now("test", 123)
    monkeypatch.setattr(prices, "adapter_for_asset_type", lambda at, name: (adapter, name))
    async with session_maker() as session:
        result = await prices.refresh_portfolio_prices(session, portfolio_id, only_stale=True)
        assert result.refreshed == 1
    assert adapter.fetch_price.await_count == 1
    async with session_maker() as session:
        result = await prices.refresh_portfolio_prices(session, portfolio_id)
        assert result.refreshed == 2
    assert adapter.fetch_price.await_count == 3


async def test_overlapping_price_and_dividend_jobs_share_concurrency_limit(
    session_maker,
    monkeypatch,
):
    portfolio_id, _ = await seed_positions(session_maker, 8)
    active = peak = 0
    lock = threading.Lock()

    def enter():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)

    def leave():
        nonlocal active
        with lock:
            active -= 1

    async def quote(name):
        enter()
        await asyncio.sleep(0.01)
        leave()
        return PriceQuote.now(name, 123)

    def history(name, asset_type):
        enter()
        time.sleep(0.01)
        leave()
        return []

    adapter = AsyncMock()
    adapter.fetch_price.side_effect = quote
    monkeypatch.setattr(prices, "adapter_for_asset_type", lambda at, name: (adapter, name))
    monkeypatch.setattr(dividends, "_fetch_ticker_dividends_sync", history)
    async with session_maker() as price_session, session_maker() as dividend_session:
        price_result, dividend_result = await asyncio.gather(
            prices.refresh_portfolio_prices(price_session, portfolio_id),
            dividends.sync_portfolio_dividends(dividend_session, portfolio_id),
        )
    assert peak == 2
    assert price_result.refreshed == dividend_result.synced_tickers == 8


async def test_dividend_history_is_written_in_batches(session_maker, engine, monkeypatch):
    portfolio_id, _ = await seed_positions(session_maker)
    items = [
        dict(
            ticker="ASSET0",
            payment_date=date(2020, 1, 1) + timedelta(days=i),
            ex_date=None,
            amount_per_share=1.0,
            currency="USD",
            dividend_type="Dividendo",
        )
        for i in range(250)
    ]
    monkeypatch.setattr(dividends, "_fetch_ticker_dividends_sync", lambda *args: items)
    inserts = []

    def count_inserts(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO dividends"):
            inserts.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count_inserts)
    async with session_maker() as session:
        result = await dividends.sync_portfolio_dividends(session, portfolio_id)
        assert result.total_dividends_stored == 250
        assert await session.scalar(select(func.count(Dividend.id))) == 250
    assert len(inserts) == 3


async def test_failed_sync_preserves_cached_history(session_maker, monkeypatch):
    portfolio_id, _ = await seed_positions(session_maker)
    async with session_maker() as session:
        session.add(Dividend(ticker="ASSET0", payment_date=date.today(), amount_per_share=1))
        await session.commit()

    def fail(*args):
        raise AdapterNetworkError("offline")

    monkeypatch.setattr(dividends, "_fetch_ticker_dividends_sync", fail)
    async with session_maker() as session:
        result = await dividends.sync_portfolio_dividends(session, portfolio_id)
        assert result.failed_tickers == ["ASSET0"]
        assert await session.scalar(select(func.count(Dividend.id))) == 1


async def test_empty_dividend_history_does_not_sync_on_every_calendar_view(
    session_maker,
    monkeypatch,
):
    portfolio_id, _ = await seed_positions(session_maker)
    fetched = []

    def history(ticker, asset_type):
        fetched.append(ticker)
        return []

    monkeypatch.setattr(dividends, "_fetch_ticker_dividends_sync", history)
    monkeypatch.setattr(dividends, "get_usd_brl_rate", AsyncMock(return_value=5))
    async with session_maker() as session:
        for month in (1, 2, 3):
            result = await dividends.get_portfolio_proventos(session, portfolio_id, 2026, month)
            assert result.items == []
    assert fetched == ["ASSET0"]
