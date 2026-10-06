"""One-shot translator: AUVP backend user doc -> our DB rows.

Takes a parsed auth_me.json (dict) plus the target user_id and inserts
positions, targets, and diagram questions. Does not commit - the caller
manages the transaction boundary.

Schema translation:
  * Backend RF: { amount: 1, value: <brl>, no catalog link }
    -> Position { amount: <brl>, current_price: None }
  * Backend non-RF: { amount: <shares>, value: <brl>, catalog has price }
    -> Position { amount: <shares>, current_price: value / amount }
  * diagramResponses[] (list of question external_ids) is stored as-is in a
    JSON column - we keep the AUVP question _id to preserve referential
    integrity with diagram_questions.external_id.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagram_question import DiagramQuestion
from app.models.investment_target import InvestmentTarget
from app.models.position import Position

RF_TYPES = {"rendafixa", "rendafixa_internacional"}


async def import_auvp_user_doc(
    session: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    doc: dict[str, Any],
) -> None:
    # Positions
    for a in doc.get("assets", []):
        asset_type = a["type"]
        if asset_type in RF_TYPES:
            amount = float(a["value"])
            current_price = None
        else:
            amount = float(a["amount"])
            value = float(a["value"])
            current_price = value / amount if amount > 0 else None

        session.add(
            Position(
                user_id=user_id,
                portfolio_id=portfolio_id,
                name=a["name"],
                asset_type=asset_type,
                amount=amount,
                current_price=current_price,
                tracking_mode="balance" if asset_type in RF_TYPES else "units",
                strength=int(a["strength"]),
                diagram_responses=a.get("diagramResponses"),
                source="auvp_import",
            )
        )

    # Targets
    for g in doc.get("investimentGoals", []):
        session.add(
            InvestmentTarget(
                user_id=user_id,
                portfolio_id=portfolio_id,
                asset_type=g["type"],
                target_percentage=float(g["value"]),
            )
        )

    # Diagram questions
    for i, q in enumerate(doc.get("diagramQuestions", [])):
        session.add(
            DiagramQuestion(
                user_id=user_id,
                diagram_type=q["diagram"],
                criterias=q.get("criterias", ""),
                question_text=q["question"],
                display_order=i,
                external_id=q["_id"],
            )
        )
