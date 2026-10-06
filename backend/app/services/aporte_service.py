"""Aporte business logic: create events + apply allocations.

Does NOT handle HTTP or auth - that's the API layer's job. These functions
take an AsyncSession and caller-verified IDs, then do the domain work.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aporte_allocation import AporteAllocation
from app.models.aporte_event import AporteEvent
from app.models.position import Position
from app.services.algorithm import compute_suggestions
from app.services.portfolio_loader import load_portfolio

RF_TYPES = {"rendafixa", "rendafixa_internacional"}


async def create_aporte_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    aporte_value_brl: float,
) -> AporteEvent:
    """Compute suggestions for the given portfolio + persist them as a new
    AporteEvent with unapplied AporteAllocations."""
    portfolio = await load_portfolio(session, user_id, portfolio_id)
    suggestions = compute_suggestions(portfolio, aporte_value_brl)

    event = AporteEvent(
        user_id=user_id,
        portfolio_id=portfolio_id,
        aporte_value_brl=aporte_value_brl,
    )
    session.add(event)
    await session.flush()  # assigns event.id

    for s in suggestions:
        session.add(
            AporteAllocation(
                aporte_event_id=event.id,
                position_id=uuid.UUID(s.asset_id),
                position_name_snapshot=s.asset_name,
                asset_type_snapshot=s.asset_type,
                price_at_aporte_brl=s.current_price,
                tracking_mode_snapshot=s.tracking_mode,
                suggested_value_brl=s.suggestion_value,
                suggested_quantity=s.suggestion_quantity,
            )
        )
    await session.flush()
    await session.refresh(event, ["allocations"])
    return event


async def apply_allocation(
    session: AsyncSession,
    allocation_id: uuid.UUID,
    applied_value_brl: float | None = None,
    applied_quantity: float | None = None,
) -> AporteAllocation:
    """Mark an allocation applied and mutate the referenced Position's amount.

    If applied_value_brl/applied_quantity are omitted, the suggested values
    are used as-is. For RF positions (amount stores BRL), amount is
    incremented by applied_value_brl; for crypto and stocks (amount stores
    shares), amount is incremented by applied_quantity.
    """
    alloc = (
        await session.execute(select(AporteAllocation).where(AporteAllocation.id == allocation_id))
    ).scalar_one()

    if alloc.applied:
        return alloc
    if alloc.excluded:
        raise ValueError("allocation excluded")
    value = applied_value_brl if applied_value_brl is not None else alloc.suggested_value_brl
    quantity = applied_quantity if applied_quantity is not None else alloc.suggested_quantity
    original_mode = alloc.tracking_mode_snapshot or (
        "balance"
        if alloc.asset_type_snapshot in RF_TYPES and alloc.price_at_aporte_brl is None
        else "units"
    )
    position = await session.get(Position, alloc.position_id) if alloc.position_id else None
    if original_mode == "units":
        price = alloc.price_at_aporte_brl
        if price is None or price <= 0:
            raise ValueError("allocation has no valid price")
        if applied_value_brl is not None and applied_quantity is None:
            quantity = value / price
        elif applied_quantity is not None and applied_value_brl is None:
            value = quantity * price
        elif abs(value - quantity * price) > 0.01:
            raise ValueError("value and quantity do not match allocation price")
    if value <= 0 or quantity < 0:
        raise ValueError("allocation must be positive")
    event = await session.get(AporteEvent, alloc.aporte_event_id)
    others = (
        (
            await session.execute(
                select(AporteAllocation).where(
                    AporteAllocation.aporte_event_id == event.id,
                    AporteAllocation.applied.is_(True),
                    AporteAllocation.id != alloc.id,
                )
            )
        )
        .scalars()
        .all()
    )
    if value + sum(a.applied_value_brl or 0 for a in others) > event.aporte_value_brl + 0.001:
        raise ValueError("allocation exceeds remaining deposit")

    # Claim once before incrementing holdings; concurrent repeats cannot double apply.
    claimed = await session.execute(
        update(AporteAllocation)
        .where(
            AporteAllocation.id == alloc.id,
            AporteAllocation.applied.is_(False),
            AporteAllocation.excluded.is_(False),
        )
        .values(
            applied=True,
            applied_at=datetime.now(timezone.utc),
            applied_value_brl=value,
            applied_quantity=quantity,
        )
    )
    if claimed.rowcount and position is not None:
        mode = position.tracking_mode or (
            "balance"
            if position.asset_type in RF_TYPES and position.current_price is None
            else "units"
        )
        increment = value
        if mode == "units":
            if original_mode == "units":
                increment = quantity
            else:
                if position.current_price is None or position.current_price <= 0:
                    raise ValueError("position has no valid price for conversion")
                increment = value / position.current_price
        await session.execute(
            update(Position)
            .where(Position.id == position.id)
            .values(amount=Position.amount + increment)
        )
    await session.refresh(alloc)
    return alloc


async def exclude_allocation(
    session: AsyncSession,
    event_id: uuid.UUID,
    allocation_id: uuid.UUID,
) -> AporteEvent:
    """Mark an allocation excluded and rebalance remaining allocations.

    Loads the portfolio, runs compute_suggestions with the excluded asset
    IDs filtered out, then persists updated suggestions to DB.
    """
    # Load event
    event = (
        await session.execute(select(AporteEvent).where(AporteEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise ValueError("event not found")

    # Load the target allocation
    alloc = (
        await session.execute(
            select(AporteAllocation).where(
                AporteAllocation.id == allocation_id,
                AporteAllocation.aporte_event_id == event.id,
            )
        )
    ).scalar_one_or_none()
    if alloc is None:
        raise ValueError("allocation not found")
    if alloc.applied:
        raise ValueError("allocation already applied")
    if alloc.excluded:
        return event  # idempotent

    # Mark excluded
    alloc.excluded = True
    alloc.suggested_value_brl = 0
    alloc.suggested_quantity = 0

    # Collect all allocations for the event
    all_allocs = (
        (
            await session.execute(
                select(AporteAllocation).where(AporteAllocation.aporte_event_id == event.id)
            )
        )
        .scalars()
        .all()
    )

    # Applied purchases already count in holdings. Rebalance only unspent cash,
    # keeping all other portfolio assets eligible, including newly relevant ones.
    portfolio = await load_portfolio(session, event.user_id, event.portfolio_id)
    exclude_ids = {
        str(a.position_id)
        for a in all_allocs
        if (a.excluded or a.applied) and a.position_id is not None
    }
    remaining = max(
        0, event.aporte_value_brl - sum(a.applied_value_brl or 0 for a in all_allocs if a.applied)
    )
    suggestions = compute_suggestions(portfolio, remaining, exclude_ids)

    # Map suggestions by position_id for quick lookup
    suggestion_map = {s.asset_id: s for s in suggestions}
    existing_by_pos_id = {str(a.position_id): a for a in all_allocs if a.position_id is not None}

    # Update existing allocations
    for existing in all_allocs:
        if existing.excluded or existing.applied:
            continue
        if existing.position_id and str(existing.position_id) in suggestion_map:
            s = suggestion_map[str(existing.position_id)]
            existing.suggested_value_brl = s.suggestion_value
            existing.suggested_quantity = s.suggestion_quantity
            existing.price_at_aporte_brl = s.current_price
            existing.tracking_mode_snapshot = s.tracking_mode
        else:
            # Asset no longer in suggestions (shouldn't happen, but defensive)
            existing.suggested_value_brl = 0
            existing.suggested_quantity = 0

    # Add new allocations if any fallback asset was pulled in
    for s in suggestions:
        if s.asset_id not in existing_by_pos_id:
            session.add(
                AporteAllocation(
                    aporte_event_id=event.id,
                    position_id=uuid.UUID(s.asset_id),
                    position_name_snapshot=s.asset_name,
                    asset_type_snapshot=s.asset_type,
                    price_at_aporte_brl=s.current_price,
                    tracking_mode_snapshot=s.tracking_mode,
                    suggested_value_brl=s.suggestion_value,
                    suggested_quantity=s.suggestion_quantity,
                )
            )

    await session.flush()
    await session.refresh(event, ["allocations"])
    return event
