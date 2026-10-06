from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_active_portfolio
from app.core.db import get_async_session
from app.models.portfolio import Portfolio
from app.schemas.dividend import DividendCalendarOut, DividendSyncOut
from app.services.dividend_service import get_portfolio_proventos, sync_portfolio_dividends

router = APIRouter(prefix="/api/proventos", tags=["proventos"])


@router.get("", response_model=DividendCalendarOut)
async def get_proventos(
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    date_mode: str = Query(default="payment", pattern="^(payment|ex)$"),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> DividendCalendarOut:
    return await get_portfolio_proventos(
        session=session,
        portfolio_id=portfolio.id,
        year=year,
        month=month,
        date_mode=date_mode,
    )


@router.post("/sync", response_model=DividendSyncOut)
async def sync_proventos(
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> DividendSyncOut:
    return await sync_portfolio_dividends(session=session, portfolio_id=portfolio.id)
