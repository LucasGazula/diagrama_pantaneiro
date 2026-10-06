from __future__ import annotations

import uuid

import pytest

from app.models.investment_target import InvestmentTarget
from app.models.portfolio import Portfolio as PortfolioModel
from app.models.position import Position
from app.services.algorithm import compute_suggestions
from app.services.aporte_service import apply_allocation, create_aporte_event, exclude_allocation
from app.services.types import Asset, Portfolio


def test_tesouro_never_exceeds_deposit_or_fabricates_units():
    td = Asset(
        id="td",
        type="rendafixa",
        name="Tesouro Selic 2029",
        amount=0,
        current_price=16000,
        strength=0,
        tracking_mode="units",
    )
    portfolio = Portfolio(assets=[td], targets={"rendafixa": 100}, questions=[])
    assert compute_suggestions(portfolio, 100) == []
    result = compute_suggestions(portfolio, 170)
    assert result[0].suggestion_quantity == 0.01
    assert result[0].suggestion_value == 160


def test_balance_with_quote_remains_brl():
    balance = Asset(
        id="cdb",
        type="rendafixa",
        name="CDB",
        amount=1000,
        current_price=500,
        strength=0,
        tracking_mode="balance",
    )
    result = compute_suggestions(
        Portfolio(assets=[balance], targets={"rendafixa": 100}, questions=[]), 100
    )
    assert result[0].current_value == 1000
    assert result[0].suggestion_value == 100
    assert result[0].suggestion_quantity == 0
    assert result[0].tracking_mode == "balance"


def test_excluding_bitcoin_keeps_stocks_balanced_and_class_limit():
    stocks = [
        Asset(id=name, name=name, type="acoes_nacionais", amount=10, current_price=10, strength=7)
        for name in ("BBAS3", "BBDC4", "VALE3")
    ]
    btc = Asset(id="btc", name="BTC", type="criptomoedas", amount=1, current_price=100, strength=0)
    portfolio = Portfolio(
        assets=[*stocks, btc], targets={"acoes_nacionais": 80, "criptomoedas": 20}, questions=[]
    )
    result = compute_suggestions(portfolio, 1000, {"btc"})
    assert {s.asset_id for s in result} == {a.id for a in stocks}
    values = [s.suggestion_value for s in result]
    assert max(values) - min(values) <= 10
    assert sum(values) <= (400 + 1000) * 0.8 - 300
    assert sum(values) == 820


def test_zero_target_cannot_absorb_rounding():
    assets = [
        Asset(
            id="stock", name="BBAS3", type="acoes_nacionais", amount=0, current_price=90, strength=5
        ),
        Asset(id="cdb", name="CDB", type="rendafixa", amount=0, strength=0),
    ]
    result = compute_suggestions(
        Portfolio(assets=assets, targets={"acoes_nacionais": 100, "rendafixa": 0}, questions=[]),
        100,
    )
    assert [(s.asset_id, s.suggestion_value) for s in result] == [("stock", 90)]


async def _portfolio(session):
    user_id = uuid.uuid4()
    p = PortfolioModel(id=uuid.uuid4(), user_id=user_id, name="Regressão", is_default=True)
    session.add(p)
    await session.flush()
    return user_id, p.id


async def test_pending_balance_allocation_after_explicit_conversion(session_maker):
    async with session_maker() as session:
        user, pid = await _portfolio(session)
        position = Position(
            user_id=user,
            portfolio_id=pid,
            name="Tesouro",
            asset_type="rendafixa",
            amount=1000,
            current_price=None,
            tracking_mode="balance",
            strength=0,
        )
        session.add(position)
        session.add(
            InvestmentTarget(
                user_id=user, portfolio_id=pid, asset_type="rendafixa", target_percentage=100
            )
        )
        await session.flush()
        event = await create_aporte_event(session, user, pid, 100)
        alloc = event.allocations[0]
        position.amount = 2
        position.current_price = 500
        position.tracking_mode = "units"
        await session.flush()
        await apply_allocation(session, alloc.id)
        await session.flush()
        await session.refresh(position)
        assert position.amount == pytest.approx(2.2)
        await apply_allocation(session, alloc.id)
        await session.refresh(position)
        assert position.amount == pytest.approx(2.2)


async def test_exclusion_preserves_applied_and_discovers_new_eligible_position(session_maker):
    async with session_maker() as session:
        user, pid = await _portfolio(session)
        btc = Position(
            user_id=user,
            portfolio_id=pid,
            name="BTC",
            asset_type="criptomoedas",
            amount=0,
            current_price=100,
            strength=1,
            tracking_mode="units",
        )
        stock = Position(
            user_id=user,
            portfolio_id=pid,
            name="BBAS3",
            asset_type="acoes_nacionais",
            amount=0,
            current_price=10,
            strength=5,
            tracking_mode="units",
        )
        other = Position(
            user_id=user,
            portfolio_id=pid,
            name="VALE3",
            asset_type="acoes_nacionais",
            amount=0,
            current_price=10,
            strength=5,
            tracking_mode="units",
        )
        session.add_all([btc, stock, other])
        session.add_all(
            [
                InvestmentTarget(
                    user_id=user, portfolio_id=pid, asset_type=cls, target_percentage=pct
                )
                for cls, pct in [("criptomoedas", 20), ("acoes_nacionais", 80)]
            ]
        )
        await session.flush()
        event = await create_aporte_event(session, user, pid, 100)
        applied = next(a for a in event.allocations if a.position_id == stock.id)
        excluded = next(a for a in event.allocations if a.position_id == btc.id)
        await apply_allocation(session, applied.id)
        saved = (applied.suggested_value_brl, applied.suggested_quantity, applied.applied_value_brl)
        await exclude_allocation(session, event.id, excluded.id)
        assert (
            applied.suggested_value_brl,
            applied.suggested_quantity,
            applied.applied_value_brl,
        ) == saved
        assert (
            sum(
                (a.applied_value_brl if a.applied else a.suggested_value_brl) or 0
                for a in event.allocations
                if not a.excluded
            )
            <= 100
        )
        with pytest.raises(ValueError, match="excluded"):
            await apply_allocation(session, excluded.id)
        # New asset missing from original event is eligible for subsequent recalculation.
        new = Position(
            user_id=user,
            portfolio_id=pid,
            name="BBDC4",
            asset_type="acoes_nacionais",
            amount=0,
            current_price=10,
            strength=5,
            tracking_mode="units",
        )
        session.add(new)
        await session.flush()
        vale = next(a for a in event.allocations if a.position_id == other.id)
        await exclude_allocation(session, event.id, vale.id)
        assert any(a.position_id == new.id and a.suggested_value_brl > 0 for a in event.allocations)


def test_stale_tesouro_price_is_not_used_for_new_purchase():
    td = Asset(
        id="td",
        type="rendafixa",
        name="Tesouro",
        amount=1,
        current_price=500,
        strength=0,
        tracking_mode="units",
        quote_stale=True,
    )
    assert (
        compute_suggestions(Portfolio(assets=[td], targets={"rendafixa": 100}, questions=[]), 100)
        == []
    )
