from __future__ import annotations

import json
import uuid
from datetime import timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_active_user
from app.api.deps import get_active_portfolio
from app.core.db import get_async_session
from app.models.diagram_question import DiagramQuestion
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.user import User
from app.schemas.position import PositionCreate, PositionOut, PositionUpdate
from app.services.import_auvp import import_auvp_user_doc
from app.services.strength import DIAGRAM_FOR_CLASS

router = APIRouter(prefix="/api/positions", tags=["positions"])

# Captured AUVP fixture that we auto-seed on first login.
# Path resolves to backend/tests/fixtures/auth_me.json in both dev (bind mount)
# and the prod image (tests/ is COPYed at build time).
_SEED_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "auth_me.json"
)


def _to_out(p: Position) -> PositionOut:
    mode = _mode(p)
    current_value = (
        p.amount * p.current_price if mode == "units" and p.current_price is not None else p.amount
    )
    updated_at = p.updated_at
    if updated_at is not None and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return PositionOut(
        id=p.id,
        name=p.name,
        asset_type=p.asset_type,
        amount=p.amount,
        current_price=p.current_price,
        current_value_brl=current_value,
        strength=p.strength,
        diagram_responses=p.diagram_responses,
        source=p.source,
        updated_at=updated_at,
        tracking_mode=mode,
        external_id=p.external_id,
        quote_as_of=p.quote_as_of,
        quote_stale=p.quote_stale,
    )


def _mode(p: Position) -> str:
    return p.tracking_mode or (
        "balance"
        if p.asset_type in ("rendafixa", "rendafixa_internacional") and p.current_price is None
        else "units"
    )


async def _bank_size(session: AsyncSession, user_id: uuid.UUID, diagram_type: str) -> int:
    """Count diagram_questions for this user matching the given diagram type."""
    from sqlalchemy import func as sa_func

    return (
        await session.execute(
            select(sa_func.count(DiagramQuestion.id)).where(
                DiagramQuestion.user_id == user_id,
                DiagramQuestion.diagram_type == diagram_type,
            )
        )
    ).scalar_one()


def _diagram_for(asset_type: str) -> str | None:
    return DIAGRAM_FOR_CLASS.get(asset_type)  # type: ignore[arg-type]


async def _compute_strength_if_diagram(
    session: AsyncSession,
    user_id: uuid.UUID,
    asset_type: str,
    diagram_responses: list[str] | None,
    fallback_strength: int,
) -> int:
    """If the asset type has an associated diagram AND responses were provided,
    compute strength = 2 x yes - N. Otherwise return the caller-supplied strength."""
    diagram = _diagram_for(asset_type)
    if diagram is None or diagram_responses is None:
        return fallback_strength
    n = await _bank_size(session, user_id, diagram)
    # Count only responses that map to a known question (drops stale external_ids
    # from imported AUVP data once the frontend has reconciled them). Cap to [-n, n]
    # as a safety net in case stale IDs still leak through.
    known_ids = {
        str(row[0])
        for row in (
            await session.execute(
                select(DiagramQuestion.id).where(
                    DiagramQuestion.user_id == user_id,
                    DiagramQuestion.diagram_type == diagram,
                )
            )
        ).all()
    }
    yes = sum(1 for r in diagram_responses if r in known_ids)
    return max(-n, min(n, 2 * yes - n))


async def _seed_if_empty(
    session: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID
) -> None:
    # Only auto-import the AUVP fixture for a brand-new user (no positions
    # anywhere yet). Creating a second portfolio must NOT re-seed — the user
    # expects it to start empty.
    existing = (
        await session.execute(select(Position).where(Position.user_id == user_id).limit(1))
    ).first()
    if existing is not None:
        return
    if not _SEED_FIXTURE.exists():
        return  # prod image without fixtures: silently skip
    with _SEED_FIXTURE.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    await import_auvp_user_doc(session, user_id, portfolio_id, doc)
    await session.commit()


@router.get("", response_model=list[PositionOut])
async def list_positions(
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> list[PositionOut]:
    await _seed_if_empty(session, user.id, portfolio.id)
    rows = (
        (await session.execute(select(Position).where(Position.portfolio_id == portfolio.id)))
        .scalars()
        .all()
    )
    return [_to_out(p) for p in rows]


@router.post("", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
async def create_position(
    body: PositionCreate,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> PositionOut:
    mode = body.tracking_mode or (
        "balance"
        if body.asset_type in ("rendafixa", "rendafixa_internacional")
        and body.current_price is None
        else "units"
    )
    if mode == "balance" and body.asset_type not in ("rendafixa", "rendafixa_internacional"):
        raise HTTPException(422, "Saldo manual disponível apenas para renda fixa")
    if mode == "units" and body.current_price is None:
        raise HTTPException(422, "Informe preço positivo para acompanhar quantidade")
    strength = await _compute_strength_if_diagram(
        session, user.id, body.asset_type, body.diagram_responses, body.strength
    )
    pos = Position(
        user_id=user.id,
        portfolio_id=portfolio.id,
        name=body.name,
        asset_type=body.asset_type,
        amount=body.amount,
        current_price=body.current_price,
        tracking_mode=mode,
        external_id=body.external_id,
        strength=strength,
        diagram_responses=body.diagram_responses,
        source="user",
    )
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    return _to_out(pos)


@router.patch("/{position_id}", response_model=PositionOut)
async def update_position(
    position_id: uuid.UUID,
    body: PositionUpdate,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> PositionOut:
    pos = (
        await session.execute(
            select(Position).where(
                Position.id == position_id, Position.portfolio_id == portfolio.id
            )
        )
    ).scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")

    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is None:
        raise HTTPException(422, "Nome não pode ser nulo")
    old_mode = _mode(pos)
    new_mode = updates.get("tracking_mode") or old_mode
    price = updates.get("current_price", pos.current_price)
    if new_mode == "balance" and pos.asset_type not in ("rendafixa", "rendafixa_internacional"):
        raise HTTPException(422, "Saldo manual disponível apenas para renda fixa")
    if new_mode == "units" and (price is None or price <= 0):
        raise HTTPException(422, "Informe preço positivo para acompanhar quantidade")
    if "amount" in updates and updates["amount"] is None:
        raise HTTPException(422, "Quantidade/saldo não pode ser nulo")
    if new_mode != old_mode:
        # Mode changes convert existing holdings. Amount must be edited separately.
        if "amount" in updates:
            raise HTTPException(
                422, "Ao mudar acompanhamento, salve conversão antes de editar saldo"
            )
        if new_mode == "units":
            updates["amount"] = pos.amount / price
        else:
            if pos.current_price is None:
                raise HTTPException(422, "Preço anterior necessário para converter saldo")
            updates["amount"] = pos.amount * pos.current_price
    updates["tracking_mode"] = new_mode
    if "current_price" in updates:
        updates["quote_stale"] = False
        updates["quote_as_of"] = None
    for k, v in updates.items():
        setattr(pos, k, v)

    # If diagram_responses changed AND this asset has a diagram, re-derive strength.
    # Explicit strength in the same PATCH body still wins (we check exclude_unset).
    if (
        "diagram_responses" in updates
        and "strength" not in updates
        and _diagram_for(pos.asset_type) is not None
    ):
        pos.strength = await _compute_strength_if_diagram(
            session, user.id, pos.asset_type, pos.diagram_responses, pos.strength
        )

    await session.commit()
    await session.refresh(pos)
    return _to_out(pos)


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: uuid.UUID,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    pos = (
        await session.execute(
            select(Position).where(
                Position.id == position_id, Position.portfolio_id == portfolio.id
            )
        )
    ).scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")
    await session.delete(pos)
    await session.commit()
