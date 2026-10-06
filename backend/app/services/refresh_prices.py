"""Refresh all auto-refreshable positions for a given portfolio."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market_data.base import AdapterError, FETCH_CONCURRENCY, fetch_slots
from app.market_data.registry import adapter_for_asset_type
from app.models.portfolio import Portfolio  # noqa: F401
from app.models.position import Position
from app.models.user import User  # noqa: F401


@dataclass
class Failure:
    name: str
    reason: str


@dataclass
class RefreshResult:
    refreshed: int = 0
    skipped_manual: int = 0
    failed: list[Failure] = field(default_factory=list)
    stale: list[Failure] = field(default_factory=list)


async def refresh_portfolio_prices(
    session: AsyncSession,
    portfolio_id: uuid.UUID | None = None,
    *args,
    user_id: uuid.UUID | None = None,
    only_stale: bool = False,
    **kwargs,
) -> RefreshResult:
    if user_id is not None:
        positions = (
            (
                await session.execute(
                    select(Position).where(
                        or_(Position.user_id == user_id, Position.user_id == str(user_id))
                    )
                )
            )
            .scalars()
            .all()
        )
    elif portfolio_id is not None:
        positions = (
            (await session.execute(select(Position).where(Position.portfolio_id == portfolio_id)))
            .scalars()
            .all()
        )
    else:
        positions = (await session.execute(select(Position))).scalars().all()

    result = RefreshResult()
    if not positions:
        return result

    # Group positions by unique (asset_type, name) to query external APIs once per ticker
    grouped: dict[tuple[str, str], list[Position]] = {}
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    for p in positions:
        if (
            only_stale
            and p.current_price is not None
            and p.updated_at is not None
            and p.updated_at.replace(tzinfo=timezone.utc) >= cutoff
        ):
            continue
        if p.asset_type in ("rendafixa", "rendafixa_internacional"):
            p.tracking_mode = p.tracking_mode or ("balance" if p.current_price is None else "units")
            if p.tracking_mode == "balance":
                result.skipped_manual += 1
                continue
        key = (p.asset_type, p.external_id or p.name.strip())
        grouped.setdefault(key, []).append(p)

    async def refresh_group(key: tuple[str, str], group: list[Position]) -> None:
        asset_type, name = key
        routing = adapter_for_asset_type(asset_type, name)
        if routing is None:
            result.skipped_manual += len(group)
            return
        adapter, external_id = routing
        try:
            async with fetch_slots:
                quote = await adapter.fetch_price(external_id)
        except AdapterError as e:
            if asset_type == "rendafixa":
                for p in group:
                    p.quote_stale = True
            result.failed.append(Failure(name=name, reason=str(e)))
            return

        for p in group:
            p.current_price = quote.price_brl
            p.quote_as_of = quote.as_of or quote.fetched_at
            p.quote_stale = quote.stale
            if quote.stale:
                result.stale.append(
                    Failure(name=p.name, reason="Cotação antiga; confira data antes de aportar")
                )
            else:
                p.updated_at = quote.fetched_at
            result.refreshed += 1

    groups = list(grouped.items())
    for offset in range(0, len(groups), FETCH_CONCURRENCY):
        await asyncio.gather(
            *(refresh_group(k, grp) for k, grp in groups[offset : offset + FETCH_CONCURRENCY])
        )
    await session.commit()
    return result
