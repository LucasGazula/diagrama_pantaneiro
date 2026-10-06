from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_active_user
from app.api.deps import get_active_portfolio
from app.core.db import get_async_session
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.prices import PriceFailureOut, RefreshSummaryOut
from app.services.refresh_prices import refresh_portfolio_prices

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.post("/refresh", response_model=RefreshSummaryOut)
async def refresh_prices(
    scope: str = "active",
    force: bool = True,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> RefreshSummaryOut:
    refresh_options = {} if force else {"only_stale": True}
    if scope == "all":
        result = await refresh_portfolio_prices(
            session, portfolio.id, user_id=user.id, **refresh_options
        )
    else:
        result = await refresh_portfolio_prices(session, portfolio.id, **refresh_options)
    return RefreshSummaryOut(
        refreshed=result.refreshed,
        skipped_manual=result.skipped_manual,
        failed=[PriceFailureOut(name=f.name, reason=f.reason) for f in result.failed],
        stale=[PriceFailureOut(name=f.name, reason=f.reason) for f in result.stale],
    )
