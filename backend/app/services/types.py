"""Pure-Python domain types for the rebalancing algorithm.

Ported from src/types.ts. Kept deliberately separate from SQLAlchemy models
(app/models/) and API schemas (app/schemas/) so the algorithm remains a
pure function of in-memory data with no ORM or HTTP coupling.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


ClassType = Literal[
    "acoes_nacionais",
    "acoes_internacionais",
    "fundos_imobiliarios",
    "reits",
    "criptomoedas",
    "rendafixa",
    "rendafixa_internacional",
]

DiagramType = Literal["diagrama-do-cerrado", "investimentos-imobiliarios"]


class Question(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    criteria: str
    text: str
    diagram: DiagramType


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: ClassType
    name: str
    amount: float
    strength: int
    current_price: float | None = None
    tracking_mode: Literal["balance", "units"] | None = None
    quote_stale: bool = False
    diagram_responses: list[str] | None = None


class Portfolio(BaseModel):
    model_config = ConfigDict(frozen=True)

    assets: list[Asset]
    targets: dict[str, float]  # keyed by ClassType string; Partial in spirit
    questions: list[Question]


class Suggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: str
    asset_type: ClassType
    asset_name: str
    current_value: float
    current_quantity: float
    current_price: float | None = None
    tracking_mode: Literal["balance", "units"] = "units"
    strength: int
    suggestion_quantity: float
    suggestion_value: float
    suggestion_percentage: float
    total_after_suggestion_percentage: float
