from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aporte_allocation import AporteAllocation
from app.models.portfolio import Portfolio as PortfolioModel
from app.models.position import Position
from app.services.aporte_service import (
    apply_allocation,
    create_aporte_event,
    exclude_allocation,
)
from app.services.import_auvp import import_auvp_user_doc

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "auth_me.json"


@pytest.fixture
async def session(session_maker) -> AsyncSession:
    async with session_maker() as s:
        yield s


async def _seeded_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    p = PortfolioModel(
        id=uuid.uuid4(), user_id=user_id, name="Principal", is_default=True
    )
    session.add(p)
    await session.flush()
    with FIXTURE.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    await import_auvp_user_doc(session, user_id, p.id, doc)
    await session.commit()
    return user_id, p.id


async def test_create_aporte_event_persists_event_and_allocations(
    session: AsyncSession,
) -> None:
    user_id, portfolio_id = await _seeded_user(session)

    event = await create_aporte_event(session, user_id, portfolio_id, 500)
    await session.commit()

    assert event.aporte_value_brl == 500
    assert len(event.allocations) == 3
    for a in event.allocations:
        assert a.applied is False
        assert a.suggested_value_brl > 0
        assert a.position_name_snapshot


async def test_apply_allocation_updates_position_and_marks_applied(
    session: AsyncSession,
) -> None:
    user_id, portfolio_id = await _seeded_user(session)
    event = await create_aporte_event(session, user_id, portfolio_id, 500)
    await session.commit()

    btc_alloc = next(
        a for a in event.allocations if a.asset_type_snapshot == "criptomoedas"
    )
    btc_position_before = (
        await session.execute(
            select(Position).where(Position.id == btc_alloc.position_id)
        )
    ).scalar_one()
    amount_before = btc_position_before.amount

    await apply_allocation(session, btc_alloc.id)
    await session.commit()

    refreshed = (
        await session.execute(
            select(AporteAllocation).where(AporteAllocation.id == btc_alloc.id)
        )
    ).scalar_one()
    assert refreshed.applied is True
    assert refreshed.applied_at is not None
    assert refreshed.applied_quantity == btc_alloc.suggested_quantity
    assert refreshed.applied_value_brl == btc_alloc.suggested_value_brl

    btc_position_after = (
        await session.execute(
            select(Position).where(Position.id == btc_alloc.position_id)
        )
    ).scalar_one()
    assert (
        abs(btc_position_after.amount - (amount_before + btc_alloc.suggested_quantity))
        < 1e-6
    )


async def test_apply_rf_allocation_adds_brl_value_to_amount(
    session: AsyncSession,
) -> None:
    """Unpriced RF (private LCI/CDB) stores BRL in amount. Applying adds BRL."""
    user_id, portfolio_id = await _seeded_user(session)
    event = await create_aporte_event(session, user_id, portfolio_id, 500)
    await session.commit()

    rf_alloc = next(
        a for a in event.allocations if a.asset_type_snapshot == "rendafixa"
    )
    pos_before = (
        await session.execute(
            select(Position).where(Position.id == rf_alloc.position_id)
        )
    ).scalar_one()
    assert pos_before.current_price is None  # confirm unpriced
    amount_before = pos_before.amount

    await apply_allocation(session, rf_alloc.id)
    await session.commit()

    pos_after = (
        await session.execute(
            select(Position).where(Position.id == rf_alloc.position_id)
        )
    ).scalar_one()
    assert (
        abs(pos_after.amount - (amount_before + rf_alloc.suggested_value_brl)) < 1e-6
    )


async def test_apply_priced_rf_adds_units_not_brl(session: AsyncSession) -> None:
    """Priced RF (Tesouro) stores units in amount. Applying adds units."""
    user_id, portfolio_id = await _seeded_user(session)

    # Promote one RF position to priced (simulate a Tesouro refresh having run)
    # Find an RF position, switch it to unit-priced.
    rf = (
        await session.execute(
            select(Position).where(
                Position.user_id == user_id,
                Position.asset_type == "rendafixa",
            )
        )
    ).scalars().first()
    assert rf is not None
    # Simulate: originally amount=1074 BRL, now Tesouro PU=500, so 2.148 units
    rf.amount = 2.148
    rf.current_price = 500.0
    await session.commit()

    # Create an aporte big enough that this position gets allocated
    event = await create_aporte_event(session, user_id, portfolio_id, 10000)
    await session.commit()

    # Find the allocation for our priced-RF position (if any)
    priced_alloc = next(
        (a for a in event.allocations if a.position_id == rf.id),
        None,
    )
    if priced_alloc is None:
        pytest.skip(
            "algorithm didn't allocate to the priced-RF position at this aporte level"
        )

    # With price set, quantity should be units (not 1.0)
    # and value should be quantity * price
    assert priced_alloc.suggested_quantity != 1.0
    expected_value = priced_alloc.suggested_quantity * 500.0
    assert abs(priced_alloc.suggested_value_brl - expected_value) < 1e-4

    amount_before = rf.amount

    await apply_allocation(session, priced_alloc.id)
    await session.commit()

    await session.refresh(rf)
    # amount (units) grew by suggested_quantity (units), NOT by value (BRL)
    assert abs(rf.amount - (amount_before + priced_alloc.suggested_quantity)) < 1e-4


async def test_exclude_allocation_rebalances_only_among_remaining_suggestions(
    session: AsyncSession,
) -> None:
    user_id, portfolio_id = await _seeded_user(session)

    # 1. Create an aporte event with 500 BRL
    event = await create_aporte_event(session, user_id, portfolio_id, 500)
    await session.commit()

    # Verify we have suggestions
    assert len(event.allocations) == 3
    original_ids = {str(a.position_id) for a in event.allocations}

    # 2. Exclude one allocation
    alloc_to_exclude = event.allocations[0]
    excluded_id = str(alloc_to_exclude.position_id)

    updated_event = await exclude_allocation(session, event.id, alloc_to_exclude.id)
    await session.commit()

    # 3. Verify that the excluded allocation is zeroed out and marked excluded
    for a in updated_event.allocations:
        if str(a.position_id) == excluded_id:
            assert a.excluded is True
            assert a.suggested_value_brl == 0
        else:
            # 4. Verify that remaining suggestions only include assets from the original set
            assert a.excluded is False
            assert str(a.position_id) in original_ids
            # They should have absorbed the value
            assert a.suggested_value_brl > 0
