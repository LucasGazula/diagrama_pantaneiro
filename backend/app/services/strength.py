"""Strength computation and position value.

Ported from src/algorithm.ts. See REVERSE_ENGINEERING.md §4 for the formula
derivation and §5 for how strength feeds into the algorithm.
"""

from __future__ import annotations

from app.services.types import Asset, ClassType, DiagramType, Question

DIAGRAM_FOR_CLASS: dict[ClassType, DiagramType] = {
    "acoes_nacionais": "diagrama-do-cerrado",
    "acoes_internacionais": "diagrama-do-cerrado",
    "fundos_imobiliarios": "investimentos-imobiliarios",
    "reits": "investimentos-imobiliarios",
}


def position_value(asset: Asset) -> float:
    """Current BRL value of a position.

    Catalog-backed positions: amount × currentPrice.
    Manual RF positions: amount (which already holds the BRL value).
    """
    if tracking_mode(asset) == "units" and asset.current_price is not None:
        return asset.amount * asset.current_price
    return asset.amount


def tracking_mode(asset) -> str:
    """Explicit mode; fallback only for legacy fixtures/rows before migration."""
    return asset.tracking_mode or (
        "balance"
        if asset.type in ("rendafixa", "rendafixa_internacional") and asset.current_price is None
        else "units"
    )


def compute_strength(asset: Asset, questions: list[Question]) -> int:
    """Derive strength from diagram responses, or return stored strength if
    the asset has no associated diagram (crypto, RF).

    Formula: strength = 2 × (yes answers) − N, where N is the count of
    questions whose `diagram` matches the asset's class.
    """
    diagram = DIAGRAM_FOR_CLASS.get(asset.type)
    if diagram is None:
        return asset.strength
    bank_size = sum(1 for q in questions if q.diagram == diagram)
    yes = len(asset.diagram_responses) if asset.diagram_responses is not None else 0
    return 2 * yes - bank_size
