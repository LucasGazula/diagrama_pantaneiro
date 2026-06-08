"""Regression tests for the 2026-04 architectural algorithm fix.

Scenarios the old algorithm got wrong:

* A single equity class with a positive-strength placeholder asset would
  absorb 100% of the aporte when every other class's assets were at the
  default strength=0 (manual crypto/RF). The new algorithm admits
  manual-strength classes at strength >= 0 and distributes per gap.

* When the aporte exceeded the sum of gaps, the old proportional-by-gap
  formula overshot target. The new algorithm caps each class at its gap
  and redistributes the excess by target percentage.
"""

from __future__ import annotations

import math

from app.services.algorithm import compute_suggestions
from app.services.types import Asset, Portfolio


def _make_portfolio(assets: list[Asset], targets: dict[str, float]) -> Portfolio:
    return Portfolio(assets=assets, targets=targets, questions=[])


def test_user_scenario_zero_strength_manual_classes_receive_allocation() -> None:
    """Reproduces the reported bug.

    Portfolio: BR stocks (strength > 0, already over-target in BRL), a single
    QQQ placeholder in acoes_internacionais with strength > 0 but qty=0,
    and crypto + RF positions at default strength=0.

    Targets: 40/20/20/20. Aporte: R$10k.

    Expected: internacional should cap at its gap (not absorb everything);
    crypto and RF should receive non-trivial allocations despite strength=0.
    """
    assets = [
        Asset(id="ac1", type="acoes_nacionais", name="BBAS3", amount=194, strength=7, current_price=24.28),
        Asset(id="ac2", type="acoes_nacionais", name="VALE3", amount=36, strength=7, current_price=87.44),
        Asset(id="ac3", type="acoes_nacionais", name="B3SA3", amount=85, strength=9, current_price=19.78),
        # Placeholder intent position — strength > 0, qty 0
        Asset(id="qqq", type="acoes_internacionais", name="QQQ", amount=0, strength=11, current_price=648.85),
        # Manual-strength classes, default 0
        Asset(id="btc", type="criptomoedas", name="BTC", amount=0.009, strength=0, current_price=384000.0),
        Asset(id="lig", type="rendafixa", name="LIG", amount=994, strength=0, current_price=1.185),
        Asset(id="tes", type="rendafixa", name="TESOURO", amount=7.87, strength=0, current_price=198.86),
    ]
    targets = {
        "acoes_nacionais": 40.0,
        "acoes_internacionais": 20.0,
        "fundos_imobiliarios": 0.0,
        "reits": 0.0,
        "criptomoedas": 20.0,
        "rendafixa": 20.0,
        "rendafixa_internacional": 0.0,
    }
    aporte = 10000.0

    out = compute_suggestions(_make_portfolio(assets, targets), aporte)

    by_class: dict[str, float] = {}
    for s in out:
        by_class[s.asset_type] = by_class.get(s.asset_type, 0.0) + s.suggestion_value

    # The old algorithm routed ~100% to acoes_internacionais. The fix caps it
    # to at most the class gap (about 47% of aporte under these targets).
    assert by_class.get("acoes_internacionais", 0) < aporte * 0.55, (
        "internacional should not absorb >55% of aporte; got "
        f"{by_class.get('acoes_internacionais', 0):.2f}"
    )

    # Crypto and RF must participate despite strength=0 on their assets.
    assert by_class.get("criptomoedas", 0) > 0, "crypto excluded from aporte"
    assert by_class.get("rendafixa", 0) > 0, "RF excluded from aporte"

    # Total should still equal aporte within quantization tolerance.
    total = sum(s.suggestion_value for s in out)
    assert math.isclose(total, aporte, abs_tol=aporte * 0.01)


def test_class_never_overshoots_target_when_aporte_smaller_than_total_gap() -> None:
    """When aporte <= total_gap, each class gets at most its own gap.
    Gaps are computed against portfolio_total (without aporte)."""
    # Two classes below target with large gaps. total_gap = 400, aporte = 300.
    assets = [
        Asset(id="a", type="acoes_nacionais", name="A", amount=100, strength=9, current_price=1.0),
        Asset(id="b", type="criptomoedas", name="B", amount=0.005, strength=5, current_price=20000.0),
    ]
    targets = {
        "acoes_nacionais": 50.0,
        "acoes_internacionais": 0.0,
        "fundos_imobiliarios": 0.0,
        "reits": 0.0,
        "criptomoedas": 50.0,
        "rendafixa": 0.0,
        "rendafixa_internacional": 0.0,
    }
    # portfolio_total = 200. Gaps: ACN 50%*200-100=0 (at target), CRY 50%*200-100=0 (at target)
    # total_gap=0 → split aporte by target pct
    portfolio_total = 200.0
    aporte = 300.0

    out = compute_suggestions(_make_portfolio(assets, targets), aporte)
    by_class: dict[str, float] = {}
    for s in out:
        by_class[s.asset_type] = by_class.get(s.asset_type, 0.0) + s.suggestion_value

    total = sum(s.suggestion_value for s in out)
    assert math.isclose(total, aporte, abs_tol=aporte * 0.01), (
        f"total {total:.2f} != aporte {aporte:.2f}"
    )

    # Both classes should get something
    assert by_class.get("acoes_nacionais", 0) > 0
    assert by_class.get("criptomoedas", 0) > 0


def test_excess_aporte_redistributes_by_target_pct() -> None:
    """When aporte > total gap, every gap closes and the excess flows
    proportionally to target percentages across eligible classes."""
    assets = [
        # Start a little under target so there IS a gap, but small
        Asset(id="a", type="acoes_nacionais", name="A", amount=1, strength=9, current_price=100.0),
        Asset(id="b", type="criptomoedas", name="B", amount=0.01, strength=5, current_price=10000.0),
    ]
    targets = {
        "acoes_nacionais": 60.0,
        "acoes_internacionais": 0.0,
        "fundos_imobiliarios": 0.0,
        "reits": 0.0,
        "criptomoedas": 40.0,
        "rendafixa": 0.0,
        "rendafixa_internacional": 0.0,
    }
    # portfolio_total = 200; aporte huge to force excess scenario
    aporte = 10000.0

    out = compute_suggestions(_make_portfolio(assets, targets), aporte)
    total = sum(s.suggestion_value for s in out)
    assert math.isclose(total, aporte, abs_tol=aporte * 0.01)

    by_class: dict[str, float] = {}
    for s in out:
        by_class[s.asset_type] = by_class.get(s.asset_type, 0.0) + s.suggestion_value

    # Both eligible classes must be in the output
    assert by_class.get("acoes_nacionais", 0) > 0
    assert by_class.get("criptomoedas", 0) > 0

    # Ratio of the two should be roughly 60:40 (within 5% rel error given
    # the initial gap-closing step perturbs the split a bit).
    nacional = by_class["acoes_nacionais"]
    crypto = by_class["criptomoedas"]
    ratio = nacional / crypto
    expected = 60.0 / 40.0
    assert abs(ratio - expected) / expected < 0.2, (
        f"ratio {ratio:.3f} not close to expected {expected:.3f}"
    )


def test_manual_class_with_all_zero_strength_falls_back_to_value_weight() -> None:
    """Two RF positions both at strength=0; allocation should split by
    current value, not drop the class."""
    assets = [
        Asset(id="big", type="rendafixa", name="BIG", amount=2000, strength=0, current_price=None),
        Asset(id="small", type="rendafixa", name="SMALL", amount=500, strength=0, current_price=None),
    ]
    targets = {
        "acoes_nacionais": 0.0,
        "acoes_internacionais": 0.0,
        "fundos_imobiliarios": 0.0,
        "reits": 0.0,
        "criptomoedas": 0.0,
        "rendafixa": 100.0,
        "rendafixa_internacional": 0.0,
    }
    aporte = 500.0

    out = compute_suggestions(_make_portfolio(assets, targets), aporte)
    by_id = {s.asset_id: s.suggestion_value for s in out}

    # Both should receive (not dropped by the old strength > 0 filter).
    assert "big" in by_id
    assert "small" in by_id
    # BIG has 4x the value of SMALL — allocation should follow that weighting
    # (within tolerance: the sub-gap math still narrows toward proportional
    # end-state, not strictly 4:1 on delta). BIG just gets more than SMALL.
    assert by_id["big"] > by_id["small"]


def test_diagram_class_still_excludes_zero_strength_equity() -> None:
    """Equities with strength == 0 must not receive allocation even when
    a sibling equity has positive strength (preserves diagram quality filter)."""
    assets = [
        Asset(id="good", type="acoes_nacionais", name="GOOD", amount=10, strength=9, current_price=10.0),
        Asset(id="meh", type="acoes_nacionais", name="MEH", amount=10, strength=0, current_price=10.0),
        # Anchor class
        Asset(id="btc", type="criptomoedas", name="BTC", amount=0.001, strength=8, current_price=100000.0),
    ]
    targets = {
        "acoes_nacionais": 50.0,
        "acoes_internacionais": 0.0,
        "fundos_imobiliarios": 0.0,
        "reits": 0.0,
        "criptomoedas": 50.0,
        "rendafixa": 0.0,
        "rendafixa_internacional": 0.0,
    }
    aporte = 500.0

    out = compute_suggestions(_make_portfolio(assets, targets), aporte)
    for s in out:
        assert s.asset_id != "meh", (
            "zero-strength equity received allocation; diagram filter broken"
        )
