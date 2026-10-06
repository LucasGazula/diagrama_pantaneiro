"""DB -> domain Portfolio converter.

Bridges the SQLAlchemy models (positions, investment_targets, diagram_questions)
to the in-memory `Portfolio` domain type that the rebalancing algorithm
expects.

Positions and targets are scoped to a single portfolio. Diagram questions
are user-scoped (shared library across all of a user's portfolios), so the
loader takes both user_id and portfolio_id.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagram_question import DiagramQuestion
from app.models.investment_target import InvestmentTarget
from app.models.position import Position
from app.services.types import Asset, Portfolio, Question


async def load_portfolio(
    session: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID
) -> Portfolio:
    pos_rows = (
        (await session.execute(select(Position).where(Position.portfolio_id == portfolio_id)))
        .scalars()
        .all()
    )
    tgt_rows = (
        (
            await session.execute(
                select(InvestmentTarget).where(InvestmentTarget.portfolio_id == portfolio_id)
            )
        )
        .scalars()
        .all()
    )
    q_rows = (
        (await session.execute(select(DiagramQuestion).where(DiagramQuestion.user_id == user_id)))
        .scalars()
        .all()
    )

    assets = [
        Asset(
            id=str(p.id),
            type=p.asset_type,  # type: ignore[arg-type]
            name=p.name,
            amount=p.amount,
            strength=p.strength,
            current_price=p.current_price,
            tracking_mode=p.tracking_mode,
            quote_stale=p.quote_stale,
            diagram_responses=p.diagram_responses,
        )
        for p in pos_rows
    ]
    targets = {t.asset_type: t.target_percentage for t in tgt_rows}
    questions = [
        Question(
            id=q.external_id or str(q.id),
            criteria=q.criterias,
            text=q.question_text,
            diagram=q.diagram_type,  # type: ignore[arg-type]
        )
        for q in q_rows
    ]
    return Portfolio(assets=assets, targets=targets, questions=questions)
