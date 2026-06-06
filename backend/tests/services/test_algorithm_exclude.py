"""Tests for compute_suggestions with exclude_ids parameter."""
from __future__ import annotations

from app.services.algorithm import compute_suggestions
from app.services.types import Asset, Portfolio


def _make_asset(
    id: str,
    asset_type: str,
    amount: float,
    strength: int = 1,
    price: float = 100.0,
    name: str = "",
) -> Asset:
    return Asset(
        id=id,
        type=asset_type,
        name=name or id,
        amount=amount,
        strength=strength,
        current_price=price,
    )


def _make_portfolio(assets: list[Asset], targets: dict[str, float]) -> Portfolio:
    return Portfolio(assets=assets, targets=targets, questions=[])


class TestExcludeBasic:
    def test_exclude_one_asset(self):
        """Excluding an asset gives it $0 suggestion and redistributes to others."""
        # Amounts chosen so total_gap (950) < aporte (2000): all classes get allocations.
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),   # value=250
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100), # value=1000
            _make_asset("a3", "rendafixa", 100, strength=0, price=None),     # value=100 (BRL)
        ]
        targets = {"criptomoedas": 30, "acoes_nacionais": 50, "rendafixa": 20}
        portfolio = _make_portfolio(assets, targets)

        all_suggestions = compute_suggestions(portfolio, 2000)
        assert len(all_suggestions) == 3

        excluded = compute_suggestions(portfolio, 2000, exclude_ids={"a1"})
        # a1 should not appear in results
        ids = {s.asset_id for s in excluded}
        assert "a1" not in ids
        # Total of remaining suggestions should be close to 2000
        total = sum(s.suggestion_value for s in excluded)
        assert total > 1990  # allow rounding

    def test_exclude_preserves_total(self):
        """Total of non-excluded suggestions equals aporte (within rounding)."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
            _make_asset("a3", "rendafixa", 1000, strength=0, price=None),
            _make_asset("a4", "acoes_internacionais", 5, strength=1, price=200),
            _make_asset("a5", "reits", 3, strength=1, price=150),
        ]
        targets = {
            "criptomoedas": 20,
            "acoes_nacionais": 30,
            "rendafixa": 10,
            "acoes_internacionais": 25,
            "reits": 15,
        }
        portfolio = _make_portfolio(assets, targets)

        for exclude_id in ["a1", "a2", "a3", "a4", "a5"]:
            suggestions = compute_suggestions(portfolio, 1000, exclude_ids={exclude_id})
            total = sum(s.suggestion_value for s in suggestions)
            assert total > 990, f"exclude {exclude_id}: total {total} too low"

    def test_exclude_already_excluded(self):
        """Excluding an asset not in the portfolio is a no-op."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
        ]
        targets = {"criptomoedas": 40, "acoes_nacionais": 60}
        portfolio = _make_portfolio(assets, targets)

        base = compute_suggestions(portfolio, 500)
        with_exclusion = compute_suggestions(portfolio, 500, exclude_ids={"nonexistent"})
        assert len(base) == len(with_exclusion)

    def test_exclude_all_but_one(self):
        """Remaining asset gets essentially the full aporte."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
            _make_asset("a3", "rendafixa", 1000, strength=0, price=None),
        ]
        targets = {"criptomoedas": 30, "acoes_nacionais": 50, "rendafixa": 20}
        portfolio = _make_portfolio(assets, targets)

        suggestions = compute_suggestions(portfolio, 500, exclude_ids={"a1", "a2"})
        assert len(suggestions) == 1
        assert suggestions[0].asset_id == "a3"
        assert suggestions[0].suggestion_value > 490
