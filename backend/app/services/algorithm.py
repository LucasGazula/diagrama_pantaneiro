"""Rebalancing algorithm — three-stage suggestion generator.

Originally ported from ``src/algorithm.ts`` to match the AUVP backend output
on a captured fixture (see REVERSE_ENGINEERING.md §5). Since then the semantic
diverged to fix two production issues discovered in real use:

  * **Zero-strength assets in manual-strength classes used to be invisible.**
    Crypto and renda-fixa positions default to strength=0 when created via
    the UI (no diagram to derive strength from). The old algorithm filtered
    ``strength > 0`` everywhere, so a portfolio whose only crypto/RF assets
    had default strength would have 100% of the aporte routed into whichever
    diagram-class (e.g., ações internacionais) still had a positive-strength
    asset, blowing past the target. Fix: manual-strength classes (crypto and
    RF) now accept ``strength >= 0``. Diagram classes (equities, FIIs, REITs)
    still require ``strength > 0`` — ``strength == 0`` there means the user
    gave zero yes-answers, which is an intentional neutral judgment.

  * **A class could overshoot its target.** When the aporte exceeded the sum
    of gaps across eligible classes, the previous ``aporte × (gap / total_gap)``
    distribution assigned each class more than its gap, overshooting. Fix:
    cap each class's share at its gap; redistribute the excess proportionally
    to each class's target percentage.

Stage 3 (quantization) and the residual absorber are unchanged.
"""

from __future__ import annotations

import math

from app.services.strength import DIAGRAM_FOR_CLASS, position_value
from app.services.types import Asset, ClassType, Portfolio, Suggestion

RF_TYPES: set[ClassType] = {"rendafixa", "rendafixa_internacional"}
FRACTIONAL_SHARE_TYPES: set[ClassType] = {"acoes_internacionais", "reits"}

# Classes whose strength is set manually by the user (no diagram). For these
# the default of 0 means "not yet evaluated" rather than "excluded", so they
# stay eligible for allocation. Diagram classes compute strength from the
# user's yes/no answers, so ``strength == 0`` there is a real judgment.
MANUAL_STRENGTH_TYPES: set[ClassType] = {
    cls for cls in ("criptomoedas", "rendafixa", "rendafixa_internacional")
    if cls not in DIAGRAM_FOR_CLASS
}


def _is_allocatable(a: Asset) -> bool:
    if a.strength < 0:
        return False
    if a.type in MANUAL_STRENGTH_TYPES:
        return True
    return a.strength > 0


def compute_suggestions(
    portfolio: Portfolio,
    aporte: float,
    exclude_ids: set[str] | None = None,
) -> list[Suggestion]:
    if aporte <= 0:
        return []

    exclude = exclude_ids or set()
    portfolio_total = sum(position_value(a) for a in portfolio.assets)
    new_total = portfolio_total + aporte

    class_share = _stage_one_inter_class(portfolio, new_total, aporte, exclude)
    if not class_share:
        return []

    raw_allocation = _stage_two_intra_class(class_share, portfolio.assets, exclude)
    suggestions = _stage_three_quantize(raw_allocation, portfolio.assets, aporte, new_total)
    return _absorb_residual(suggestions, portfolio.assets, aporte, new_total, exclude)


def _absorb_residual(
    suggestions: list[Suggestion],
    all_assets: list[Asset],
    aporte: float,
    new_total: float,
    exclude_ids: set[str] | None = None,
) -> list[Suggestion]:
    """Push leftover BRL (from stocks that couldn't buy a whole share) into
    assets that accept exact BRL: crypto and legacy RF. Picks the highest-
    strength absorber already in the suggestion list to keep rebalancing
    direction sensible."""
    total = sum(s.suggestion_value for s in suggestions)
    residual = aporte - total
    if residual <= 0.01:
        return suggestions

    # Tier 1 absorbers: criptomoedas, acoes_internacionais, reits, unpriced RF
    # These accept exact BRL (or extremely high precision, 4 decimal places)
    idx_absorber = -1
    best_strength = -1
    for i, s in enumerate(suggestions):
        if (
            s.asset_type == "criptomoedas" 
            or s.asset_type in FRACTIONAL_SHARE_TYPES 
            or (s.asset_type in RF_TYPES and s.current_price is None)
        ):
            if s.strength > best_strength:
                best_strength = s.strength
                idx_absorber = i

    # Fallback Tier 1: scan all non-excluded assets in portfolio
    if idx_absorber < 0:
        exclude = exclude_ids or set()
        suggested_ids = {s.asset_id for s in suggestions}
        best: Asset | None = None
        best_strength = -1
        for a in all_assets:
            if a.id in exclude or a.id in suggested_ids:
                continue
            if not _is_allocatable(a):
                continue
            if (
                a.type == "criptomoedas" 
                or a.type in FRACTIONAL_SHARE_TYPES 
                or (a.type in RF_TYPES and a.current_price is None)
            ):
                if a.strength > best_strength:
                    best_strength = a.strength
                    best = a
        if best is not None:
            suggestion_quantity: float
            if (best.type == "criptomoedas" or best.type in FRACTIONAL_SHARE_TYPES) and best.current_price:
                suggestion_quantity = round((residual / best.current_price) * 1e4) / 1e4
            else:
                suggestion_quantity = 1.0
            suggestions.append(
                Suggestion(
                    asset_id=best.id,
                    asset_type=best.type,
                    asset_name=best.name,
                    current_value=position_value(best),
                    current_quantity=best.amount,
                    current_price=best.current_price,
                    strength=best.strength,
                    suggestion_quantity=suggestion_quantity,
                    suggestion_value=residual,
                    suggestion_percentage=residual / aporte,
                    total_after_suggestion_percentage=((position_value(best) + residual) / new_total) * 100.0,
                )
            )
            return suggestions

    # Tier 2 absorbers: priced RF (where current_price > 0). Accepts increments of 0.01 units.
    if idx_absorber < 0:
        best_strength = -1
        for i, s in enumerate(suggestions):
            if s.asset_type in RF_TYPES and s.current_price is not None and s.current_price > 0:
                min_step_val = s.current_price * 0.01
                if residual >= min_step_val:
                    if s.strength > best_strength:
                        best_strength = s.strength
                        idx_absorber = i

    # Fallback Tier 2: scan all non-excluded assets in portfolio for priced RF
    if idx_absorber < 0:
        exclude = exclude_ids or set()
        suggested_ids = {s.asset_id for s in suggestions}
        best: Asset | None = None
        best_strength = -1
        for a in all_assets:
            if a.id in exclude or a.id in suggested_ids:
                continue
            if not _is_allocatable(a):
                continue
            if a.type in RF_TYPES and a.current_price is not None and a.current_price > 0:
                min_step_val = a.current_price * 0.01
                if residual >= min_step_val:
                    if a.strength > best_strength:
                        best_strength = a.strength
                        best = a
        if best is not None:
            additional_qty = math.floor(residual / best.current_price * 100) / 100
            absorb_val = additional_qty * best.current_price
            suggestions.append(
                Suggestion(
                    asset_id=best.id,
                    asset_type=best.type,
                    asset_name=best.name,
                    current_value=position_value(best),
                    current_quantity=best.amount,
                    current_price=best.current_price,
                    strength=best.strength,
                    suggestion_quantity=additional_qty,
                    suggestion_value=absorb_val,
                    suggestion_percentage=absorb_val / aporte,
                    total_after_suggestion_percentage=((position_value(best) + absorb_val) / new_total) * 100.0,
                )
            )
            return suggestions

    if idx_absorber >= 0:
        target = suggestions[idx_absorber]
        if target.asset_type in RF_TYPES and target.current_price is not None and target.current_price > 0:
            # Priced RF: absorb in increments of 0.01 units
            additional_qty = math.floor(residual / target.current_price * 100) / 100
            absorb_val = additional_qty * target.current_price
            new_value = target.suggestion_value + absorb_val
            new_quantity = target.suggestion_quantity + additional_qty
        else:
            # Crypto, fractional shares or unpriced RF: absorb entire residual
            new_value = target.suggestion_value + residual
            if (target.asset_type == "criptomoedas" or target.asset_type in FRACTIONAL_SHARE_TYPES) and target.current_price:
                new_quantity = round((new_value / target.current_price) * 1e4) / 1e4
            else:
                new_quantity = target.suggestion_quantity

        suggestions[idx_absorber] = target.model_copy(update={
            "suggestion_value": new_value,
            "suggestion_quantity": new_quantity,
            "suggestion_percentage": new_value / aporte,
            "total_after_suggestion_percentage": ((target.current_value + new_value) / new_total) * 100.0,
        })
        return suggestions

    # Tier 3 absorbers: whole-share assets (equities, FIIs, etc.)
    # Iteratively allocate additional whole units to the best eligible candidate
    # while residual >= candidate.current_price.
    while residual > 0.01:
        # Check candidates already in suggestions
        candidate_indices = [
            i for i, s in enumerate(suggestions)
            if s.current_price is not None and s.current_price > 0 and s.current_price <= (residual + 1e-4)
            and s.asset_type not in RF_TYPES
        ]
        if candidate_indices:
            best_idx = max(
                candidate_indices,
                key=lambda i: (
                    suggestions[i].strength,
                    -suggestions[i].total_after_suggestion_percentage,
                ),
            )
            target = suggestions[best_idx]
            assert target.current_price is not None
            price = target.current_price
            new_value = target.suggestion_value + price
            new_qty = target.suggestion_quantity + 1.0
            residual -= price
            suggestions[best_idx] = target.model_copy(update={
                "suggestion_value": new_value,
                "suggestion_quantity": new_qty,
                "suggestion_percentage": new_value / aporte,
                "total_after_suggestion_percentage": ((target.current_value + new_value) / new_total) * 100.0,
            })
            continue

        # Fallback candidates in all_assets (not in suggestions and not in exclude_ids)
        exclude = exclude_ids or set()
        suggested_ids = {s.asset_id for s in suggestions}
        fallback_candidates = [
            a for a in all_assets
            if a.id not in exclude and a.id not in suggested_ids
            and _is_allocatable(a)
            and a.current_price is not None and a.current_price > 0 and a.current_price <= (residual + 1e-4)
            and a.type not in RF_TYPES
        ]
        if not fallback_candidates:
            break

        best_asset = max(
            fallback_candidates,
            key=lambda a: (a.strength, -position_value(a)),
        )
        assert best_asset.current_price is not None
        price = best_asset.current_price
        residual -= price
        suggestions.append(
            Suggestion(
                asset_id=best_asset.id,
                asset_type=best_asset.type,
                asset_name=best_asset.name,
                current_value=position_value(best_asset),
                current_quantity=best_asset.amount,
                current_price=best_asset.current_price,
                strength=best_asset.strength,
                suggestion_quantity=1.0,
                suggestion_value=price,
                suggestion_percentage=price / aporte,
                total_after_suggestion_percentage=((position_value(best_asset) + price) / new_total) * 100.0,
            )
        )

    return suggestions


def _stage_one_inter_class(
    portfolio: Portfolio,
    new_total: float,
    aporte: float,
    exclude_ids: set[str] | None = None,
) -> dict[ClassType, float]:
    """Inter-class split.

    Eligible = classes with target > 0 AND at least one allocatable asset.
    Three cases:
      * ``total_gap >= aporte`` — scale the aporte across gaps (no overshoot).
      * ``total_gap < aporte``  — close every gap, distribute the excess by
        target pct across eligible classes (preserves target ratios on the
        new money; minor overshoot is unavoidable).
      * ``total_gap == 0``       — every class at/above target; split the
        aporte by target pct.
    """
    exclude = exclude_ids or set()
    assets = portfolio.assets
    targets = portfolio.targets

    eligible_classes: set[ClassType] = {
        a.type for a in assets 
        if _is_allocatable(a) and a.id not in exclude
    }

    gaps: dict[ClassType, float] = {}
    eligible_targets: dict[ClassType, float] = {}
    for cls in eligible_classes:
        pct = targets.get(cls, 0) or 0
        if pct <= 0:
            continue
        eligible_targets[cls] = pct
        target_value = (pct / 100.0) * new_total
        current_value = sum(position_value(a) for a in assets if a.type == cls)
        gap = max(0.0, target_value - current_value)
        if gap > 0:
            gaps[cls] = gap

    total_gap = sum(gaps.values())
    total_pct = sum(eligible_targets.values())

    if total_pct <= 0:
        return {}

    if total_gap == 0:
        # All classes at/above target; split aporte by target pct.
        return {cls: aporte * (pct / total_pct) for cls, pct in eligible_targets.items()}

    if total_gap >= aporte:
        # Enough gap to absorb entire aporte proportionally.
        return {cls: aporte * (g / total_gap) for cls, g in gaps.items()}

    # Close every gap, distribute excess by target pct.
    shares: dict[ClassType, float] = dict(gaps)
    excess = aporte - total_gap
    for cls, pct in eligible_targets.items():
        shares[cls] = shares.get(cls, 0.0) + excess * (pct / total_pct)
    return shares


def _stage_two_intra_class(
    class_share: dict[ClassType, float],
    all_assets: list[Asset],
    exclude_ids: set[str] | None = None,
) -> dict[str, float]:
    """Intra-class split.

    Weighting cascade for each class:
      1. If any allocatable asset has ``strength > 0``: weight = ``max(0, strength)``
         (zero-strength assets in a mixed class receive nothing — preserves
         the diagram-quality filter for equities).
      2. Else weight = current value (manual classes where all strengths sit
         at the default 0).
      3. Else (all zero, all empty): equal weight.
    """
    exclude = exclude_ids or set()
    out: dict[str, float] = {}

    for cls, share in class_share.items():
        allocatable = [
            a for a in all_assets 
            if a.type == cls and _is_allocatable(a) and a.id not in exclude
        ]
        if not allocatable:
            continue

        if any(a.strength > 0 for a in allocatable):
            weights: list[tuple[Asset, float]] = [
                (a, float(max(0, a.strength))) for a in allocatable
            ]
        else:
            value_total = sum(position_value(a) for a in allocatable)
            if value_total > 0:
                weights = [(a, position_value(a)) for a in allocatable]
            else:
                weights = [(a, 1.0) for a in allocatable]

        total_weight = sum(w for _, w in weights)
        if total_weight <= 0:
            continue

        class_total_after = sum(position_value(a) for a in allocatable) + share

        sub_gaps: list[tuple[Asset, float]] = []
        for a, w in weights:
            sub_target = (w / total_weight) * class_total_after
            sub_gaps.append((a, max(0.0, sub_target - position_value(a))))

        sum_sub_gaps = sum(g for _, g in sub_gaps)
        if sum_sub_gaps == 0:
            # All sub-targets already met; spread share by weight to keep ratios.
            for a, w in weights:
                if w > 0:
                    raw = share * (w / total_weight)
                    if raw > 0:
                        out[a.id] = raw
            continue

        for a, gap in sub_gaps:
            if gap > 0:
                raw = share * (gap / sum_sub_gaps)
                if raw > 0:
                    out[a.id] = raw
    return out


def _stage_three_quantize(
    raw_allocation: dict[str, float],
    all_assets: list[Asset],
    aporte: float,
    new_total: float,
) -> list[Suggestion]:
    by_id = {a.id: a for a in all_assets}
    out: list[Suggestion] = []

    for asset_id, raw in raw_allocation.items():
        a = by_id.get(asset_id)
        if a is None:
            continue

        if a.type == "criptomoedas":
            assert a.current_price is not None
            suggestion_quantity = round((raw / a.current_price) * 1e4) / 1e4
            suggestion_value = raw
        elif a.type in FRACTIONAL_SHARE_TYPES:
            # Avenue/Nomad brokers allow fractional US shares and REITs.
            assert a.current_price is not None
            suggestion_quantity = round((raw / a.current_price) * 1e4) / 1e4
            suggestion_value = raw
        elif a.type in RF_TYPES:
            if a.current_price is not None and a.current_price > 0:
                # Priced RF (Tesouro): quantize to fractional units (2dp)
                suggestion_quantity = round(raw / a.current_price, 2)
                suggestion_value = suggestion_quantity * a.current_price
            else:
                # Legacy unpriced RF (private LCI/CDB/etc.)
                suggestion_quantity = 1.0
                suggestion_value = raw
        else:
            assert a.current_price is not None
            suggestion_quantity = float(math.floor(raw / a.current_price))
            suggestion_value = suggestion_quantity * a.current_price

        if suggestion_value <= 0:
            continue

        current_value = position_value(a)
        out.append(
            Suggestion(
                asset_id=a.id,
                asset_type=a.type,
                asset_name=a.name,
                current_value=current_value,
                current_quantity=a.amount,
                current_price=a.current_price,
                strength=a.strength,
                suggestion_quantity=suggestion_quantity,
                suggestion_value=suggestion_value,
                suggestion_percentage=suggestion_value / aporte,
                total_after_suggestion_percentage=((current_value + suggestion_value) / new_total) * 100.0,
            ),
        )
    return out
