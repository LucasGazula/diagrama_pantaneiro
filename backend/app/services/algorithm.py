"""Buy-only rebalancing with explicit units and bounded target allocations.

Excluded holdings still count toward portfolio value. Only new purchases are
excluded. Cash remains available when no eligible purchase respects the targets.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_FLOOR

from app.services.strength import position_value, tracking_mode
from app.services.types import Asset, ClassType, Portfolio, Suggestion

RF_TYPES: set[ClassType] = {"rendafixa", "rendafixa_internacional"}
FRACTIONAL_SHARE_TYPES: set[ClassType] = {"acoes_internacionais", "reits"}
MANUAL_STRENGTH_TYPES: set[ClassType] = {"criptomoedas", *RF_TYPES}


def _is_allocatable(a: Asset) -> bool:
    if a.type in RF_TYPES and tracking_mode(a) == "units" and a.quote_stale:
        return False
    if a.strength < 0 or (a.type not in MANUAL_STRENGTH_TYPES and a.strength == 0):
        return False
    return tracking_mode(a) == "balance" or (
        a.current_price is not None and math.isfinite(a.current_price) and a.current_price > 0
    )


def _stage_one_inter_class(
    portfolio: Portfolio, new_total: float, aporte: float, exclude_ids: set[str] | None = None
) -> dict[ClassType, float]:
    excluded = exclude_ids or set()
    eligible = {a.type for a in portfolio.assets if a.id not in excluded and _is_allocatable(a)}
    gaps = {}
    for cls in sorted(eligible):
        target = portfolio.targets.get(cls, 0)
        if target <= 0:
            continue
        current = sum(position_value(a) for a in portfolio.assets if a.type == cls)
        gap = max(0.0, new_total * target / 100 - current)
        if gap > 0:
            gaps[cls] = gap
    total_gap = sum(gaps.values())
    if total_gap <= 0:
        return {}
    scale = min(1.0, aporte / total_gap)
    return {cls: gap * scale for cls, gap in gaps.items()}


def _stage_two_intra_class(
    class_share: dict[ClassType, float],
    all_assets: list[Asset],
    exclude_ids: set[str] | None = None,
) -> dict[str, float]:
    excluded = exclude_ids or set()
    out = {}
    for cls, share in class_share.items():
        eligible = sorted(
            (
                a
                for a in all_assets
                if a.type == cls and a.id not in excluded and _is_allocatable(a)
            ),
            key=lambda a: a.id,
        )
        if not eligible:
            continue
        if any(a.strength > 0 for a in eligible):
            weights = [float(max(0, a.strength)) for a in eligible]
        else:
            weights = [position_value(a) for a in eligible]
            if sum(weights) <= 0:
                weights = [1.0] * len(eligible)
        weight_sum = sum(weights)
        # Held/excluded assets remain part of class exposure.
        total_after = sum(position_value(a) for a in all_assets if a.type == cls) + share
        gaps = [
            max(0.0, total_after * w / weight_sum - position_value(a))
            for a, w in zip(eligible, weights, strict=True)
        ]
        gap_sum = sum(gaps)
        if gap_sum > 0:
            for a, gap in zip(eligible, gaps, strict=True):
                if gap > 0:
                    out[a.id] = share * gap / gap_sum
    return out


def _step(a: Asset) -> Decimal | None:
    if tracking_mode(a) == "balance":
        return None
    if a.type in RF_TYPES:
        return Decimal("0.01")
    if a.type == "criptomoedas":
        return Decimal("0.00000001")
    if a.type in FRACTIONAL_SHARE_TYPES:
        return Decimal("0.0001")
    return Decimal(1)


def compute_suggestions(
    portfolio: Portfolio, aporte: float, exclude_ids: set[str] | None = None
) -> list[Suggestion]:
    if not math.isfinite(aporte) or aporte <= 0:
        return []
    new_total = sum(position_value(a) for a in portfolio.assets) + aporte
    shares = _stage_one_inter_class(portfolio, new_total, aporte, exclude_ids)
    raw = _stage_two_intra_class(shares, portfolio.assets, exclude_ids)
    by_id = {a.id: a for a in portfolio.assets}
    values: dict[str, Decimal] = {}
    quantities: dict[str, Decimal] = {}
    for asset_id, allocation in raw.items():
        a = by_id[asset_id]
        step = _step(a)
        if step is None:
            quantities[asset_id] = Decimal(0)  # balance has no fictitious "one unit"
            values[asset_id] = Decimal(str(allocation))
        else:
            price = Decimal(str(a.current_price))
            quantity = (Decimal(str(allocation)) / price / step).to_integral_value(
                rounding=ROUND_FLOOR
            ) * step
            quantities[asset_id] = quantity
            values[asset_id] = quantity * price

    # Rounding leftovers go to the purchase that most improves the intended
    # allocation, never to a fixed highest-strength absorber or a zero-target class.
    remaining = Decimal(str(aporte)) - sum(values.values(), Decimal(0))
    class_room = {
        cls: Decimal(
            str(
                max(
                    0,
                    new_total * portfolio.targets.get(cls, 0) / 100
                    - sum(position_value(a) for a in portfolio.assets if a.type == cls),
                )
            )
        )
        - sum((v for aid, v in values.items() if by_id[aid].type == cls), Decimal(0))
        for cls in shares
    }
    awarded: set[str] = set()
    while remaining > Decimal("0.00000001"):
        best = None
        for aid, ideal in raw.items():
            if aid in awarded:
                continue
            a = by_id[aid]
            step = _step(a)
            if step is None:
                continue
            cost = step * Decimal(str(a.current_price))
            if cost > remaining or cost > class_room[a.type] + Decimal("0.00000001"):
                continue
            gap = Decimal(str(ideal)) - values[aid]
            room = class_room[a.type]
            improvement = (
                room * room
                - (room - cost) * (room - cost)
                + gap * gap
                - (gap - cost) * (gap - cost)
            )
            if improvement > 0 and (best is None or improvement > best[0]):
                best = (improvement, aid, step, cost)
        if best is None:
            break
        _, aid, step, cost = best
        awarded.add(aid)
        quantities[aid] += step
        values[aid] += cost
        class_room[by_id[aid].type] -= cost
        remaining -= cost

    return [
        Suggestion(
            asset_id=aid,
            asset_type=by_id[aid].type,
            asset_name=by_id[aid].name,
            current_value=position_value(by_id[aid]),
            current_quantity=by_id[aid].amount,
            current_price=by_id[aid].current_price
            if tracking_mode(by_id[aid]) == "units"
            else None,
            tracking_mode=tracking_mode(by_id[aid]),
            strength=by_id[aid].strength,
            suggestion_quantity=float(quantities[aid]),
            suggestion_value=float(value),
            suggestion_percentage=float(value) / aporte,
            total_after_suggestion_percentage=(position_value(by_id[aid]) + float(value))
            / new_total
            * 100,
        )
        for aid, value in values.items()
        if value > 0
    ]
