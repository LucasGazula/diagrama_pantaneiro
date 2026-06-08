from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_active_user
from app.api.deps import get_active_portfolio
from app.core.db import get_async_session
from app.models.aporte_allocation import AporteAllocation
from app.models.aporte_event import AporteEvent
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.aporte import (
    AporteAllocationOut,
    AporteCreate,
    AporteEventOut,
    ApplyRequest,
    ExcludeRequest,
)
from app.services.aporte_service import apply_allocation, create_aporte_event, exclude_allocation
from app.services.refresh_prices import refresh_portfolio_prices

router = APIRouter(prefix="/api/aportes", tags=["aportes"])


async def _get_portfolio_event(
    session: AsyncSession, event_id: uuid.UUID, portfolio_id: uuid.UUID
) -> AporteEvent:
    event = (
        await session.execute(
            select(AporteEvent).where(
                AporteEvent.id == event_id,
                AporteEvent.portfolio_id == portfolio_id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="aporte not found"
        )
    return event


@router.post("", response_model=AporteEventOut, status_code=status.HTTP_201_CREATED)
async def create_aporte(
    body: AporteCreate,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> AporteEventOut:
    await refresh_portfolio_prices(session, portfolio.id)
    event = await create_aporte_event(session, user.id, portfolio.id, body.value)
    await session.commit()
    fresh = await _get_portfolio_event(session, event.id, portfolio.id)
    return AporteEventOut.model_validate(fresh)


@router.get("", response_model=list[AporteEventOut])
async def list_aportes(
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> list[AporteEventOut]:
    events = (
        await session.execute(
            select(AporteEvent)
            .where(AporteEvent.portfolio_id == portfolio.id)
            .order_by(AporteEvent.created_at.desc())
        )
    ).scalars().all()
    return [AporteEventOut.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=AporteEventOut)
async def get_aporte(
    event_id: uuid.UUID,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> AporteEventOut:
    event = await _get_portfolio_event(session, event_id, portfolio.id)
    return AporteEventOut.model_validate(event)


@router.post(
    "/{event_id}/allocations/{allocation_id}/apply",
    response_model=AporteAllocationOut,
)
async def apply(
    event_id: uuid.UUID,
    allocation_id: uuid.UUID,
    body: ApplyRequest,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> AporteAllocationOut:
    event = await _get_portfolio_event(session, event_id, portfolio.id)
    alloc = (
        await session.execute(
            select(AporteAllocation).where(
                AporteAllocation.id == allocation_id,
                AporteAllocation.aporte_event_id == event.id,
            )
        )
    ).scalar_one_or_none()
    if alloc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="allocation not found"
        )
    updated = await apply_allocation(
        session, alloc.id, body.applied_value_brl, body.applied_quantity
    )
    await session.commit()
    await session.refresh(updated)
    return AporteAllocationOut.model_validate(updated)


@router.post("/{event_id}/exclude", response_model=AporteEventOut)
async def exclude(
    event_id: uuid.UUID,
    body: ExcludeRequest,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> AporteEventOut:
    event = await _get_portfolio_event(session, event_id, portfolio.id)
    try:
        updated = await exclude_allocation(session, event.id, body.allocation_id)
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_400_BAD_REQUEST
            if "already applied" in detail
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=code, detail=detail)
    await session.commit()
    fresh = await _get_portfolio_event(session, event.id, portfolio.id)
    return AporteEventOut.model_validate(fresh)
