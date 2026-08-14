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


class TestExcludeRedistribution:
    """Verify excluded value redistributes fully to remaining assets."""

    def test_exclude_two_of_three_absorbs_full_aporte(self):
        """User scenario: 5000 aporte, exclude 2 positions, remaining gets all."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
            _make_asset("a3", "rendafixa", 1000, strength=0, price=None),
        ]
        targets = {"criptomoedas": 30, "acoes_nacionais": 50, "rendafixa": 20}
        portfolio = _make_portfolio(assets, targets)

        suggestions = compute_suggestions(portfolio, 5000, exclude_ids={"a1", "a2"})
        total = sum(s.suggestion_value for s in suggestions)
        assert total > 4970, f"Total {total} too low, {5000 - total:.2f} leaked"

    def test_exclude_preserves_full_aporte_multiple_exclusions(self):
        """Exclude 3 of 5 positions: remaining 2 absorb full aporte."""
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

        suggestions = compute_suggestions(portfolio, 5000, exclude_ids={"a1", "a3", "a5"})
        total = sum(s.suggestion_value for s in suggestions)
        ids = {s.asset_id for s in suggestions}
        assert "a1" not in ids and "a3" not in ids and "a5" not in ids
        assert total > 4970, f"Total {total} too low, {5000 - total:.2f} leaked"


class TestAbsorbResidualFallback:
    """Verify absorb_residual picks external assets when no absorber in suggestions."""

    def test_residual_goes_to_external_crypto_during_exclusion(self):
        """When exclusion removes the last BRL absorber from suggestions (but a
        crypto asset still exists in the portfolio outside suggestions), residual
        must find that external crypto and absorb into it.

        Portfolio setup: cry at target=50% with 0.05 BTC = 25000 BRL (above target),
        so it gets no initial suggestion. Exclusion flow triggers external fallback.
        """
        assets = [
            _make_asset("a1", "acoes_nacionais", 1, strength=3, price=55.0, name="CHEAP"),
            _make_asset("a2", "acoes_nacionais", 2, strength=3, price=95.0, name="EXPENSIVE"),
            _make_asset("btc", "criptomoedas", 0.05, strength=0, price=500000.0),
            # extra asset to exclude that triggers the external search
            _make_asset("rf", "rendafixa", 12000, strength=0, price=None),
        ]
        targets = {
            "acoes_nacionais": 40.0,
            "criptomoedas": 40.0,
            "rendafixa": 20.0,
            "acoes_internacionais": 0.0,
            "fundos_imobiliarios": 0.0,
            "reits": 0.0,
            "rendafixa_internacional": 0.0,
        }
        portfolio = _make_portfolio(assets, targets)
        # Exclude rf — its class may have gotten a suggestion and was the absorber.
        # After exclusion, residual must find BTC from all_assets as the fallback.

        suggestions = compute_suggestions(portfolio, 150, exclude_ids={"rf"})
        total = sum(s.suggestion_value for s in suggestions)
        assert total > 149, f"Total {total} too low, {150 - total:.2f} leaked"
        ids = {s.asset_id for s in suggestions}
        assert "rf" not in ids
        assert "btc" in ids

    def test_residual_goes_to_legacy_rf_during_exclusion(self):
        """Same scenario but with RF (unpriced) as the fallback absorber after exclusion."""
        assets = [
            _make_asset("a1", "acoes_nacionais", 1, strength=3, price=55.0, name="CHEAP"),
            _make_asset("a2", "acoes_nacionais", 2, strength=3, price=95.0, name="EXPENSIVE"),
            _make_asset("rf", "rendafixa", 12000, strength=0, price=None),
            _make_asset("cry", "criptomoedas", 5, strength=0, price=500.0),
        ]
        targets = {
            "acoes_nacionais": 40.0,
            "rendafixa": 40.0,
            "criptomoedas": 20.0,
            "acoes_internacionais": 0.0,
            "fundos_imobiliarios": 0.0,
            "reits": 0.0,
            "rendafixa_internacional": 0.0,
        }
        portfolio = _make_portfolio(assets, targets)
        # Exclude cry → RF becomes the fallback absorber

        suggestions = compute_suggestions(portfolio, 150, exclude_ids={"cry"})
        total = sum(s.suggestion_value for s in suggestions)
        assert total > 149, f"Total {total} too low, {150 - total:.2f} leaked"
        ids = {s.asset_id for s in suggestions}
        assert "cry" not in ids
        assert "rf" in ids

    def test_residual_not_absorbed_when_no_eligible_asset_exists(self):
        """If no crypto/RF asset exists (neither in suggestions nor in portfolio),
        residual leaks — it's unavoidable. The function must not crash."""
        assets = [
            _make_asset("a1", "acoes_nacionais", 1, strength=3, price=55.0, name="CHEAP"),
            _make_asset("a2", "acoes_nacionais", 1, strength=3, price=95.0, name="EXPENSIVE"),
        ]
        targets = {
            "acoes_nacionais": 100.0,
            "acoes_internacionais": 0.0,
            "fundos_imobiliarios": 0.0,
            "reits": 0.0,
            "criptomoedas": 0.0,
            "rendafixa": 0.0,
            "rendafixa_internacional": 0.0,
        }
        portfolio = _make_portfolio(assets, targets)

        suggestions = compute_suggestions(portfolio, 150)
        # Leak is inevitable — no absorbable asset. Just check no crash.
        assert len(suggestions) > 0

    def test_exclude_with_no_absorber_in_remaining_suggestions(self):
        """Exclude the only crypto asset; RF was at target. Residual must find
        the RF from all_assets as external absorber."""
        assets = [
            _make_asset("a1", "acoes_nacionais", 5, strength=3, price=100.0, name="CHEAP"),
            _make_asset("a2", "acoes_nacionais", 5, strength=3, price=90.0, name="EXPENSIVE"),
            _make_asset("cry", "criptomoedas", 2, strength=0, price=500.0),
            # RF has target 0 → never in suggestions, but is the only BRL absorber left
            _make_asset("rf", "rendafixa", 0, strength=0, price=None),
        ]
        targets = {
            "acoes_nacionais": 70.0,
            "criptomoedas": 30.0,
            "rendafixa": 0.0,
            "acoes_internacionais": 0.0,
            "fundos_imobiliarios": 0.0,
            "reits": 0.0,
            "rendafixa_internacional": 0.0,
        }
        portfolio = _make_portfolio(assets, targets)
        # portfolio_total = 500+450+1000+0 = 1950
        # Exclude cry → crypto class gets removed from eligible
        # ACN gets all, floor quantization creates residual → must be absorbed by RF

        suggestions = compute_suggestions(portfolio, 500, exclude_ids={"cry"})
        total = sum(s.suggestion_value for s in suggestions)
        assert total > 498, f"Total {total} too low, {500 - total:.2f} leaked"
        ids = {s.asset_id for s in suggestions}
        assert "cry" not in ids
        # RF should have been pulled in as external absorber
        assert "rf" in ids, "external RF absorber not found"

    def test_whole_share_residual_absorption(self):
        """When no crypto/RF absorbers exist, whole-share assets absorb residual
        iteratively as long as residual >= asset.current_price."""
        assets = [
            _make_asset("a1", "acoes_nacionais", 10, strength=3, price=100.0, name="STOCK_A"),
            _make_asset("a2", "fundos_imobiliarios", 10, strength=3, price=150.0, name="FII_B"),
        ]
        targets = {
            "acoes_nacionais": 50.0,
            "fundos_imobiliarios": 50.0,
            "criptomoedas": 0.0,
            "rendafixa": 0.0,
            "acoes_internacionais": 0.0,
            "reits": 0.0,
            "rendafixa_internacional": 0.0,
        }
        portfolio = _make_portfolio(assets, targets)

        # 5000 aporte:
        # Initial val = 1000 + 1500 = 2500. new_total = 7500.
        # Targets: ACN 3750 (gap 2750), FII 3750 (gap 2250).
        # ACN: floor(2750 / 100) = 27 shares = 2700.
        # FII: floor(2250 / 150) = 15 shares = 2250.
        # Total before absorption = 4950, residual = 50.
        # Neither stock (100) nor FII (150) <= 50, so leftover = 50.
        sug1 = compute_suggestions(portfolio, 5000)
        assert sum(s.suggestion_value for s in sug1) == 4950.0

        # With 5100 aporte:
        # new_total = 7600. Targets: ACN 3800 (gap 2800), FII 3800 (gap 2300).
        # ACN: floor(2800 / 100) = 28 shares = 2800.
        # FII: floor(2300 / 150) = 15 shares = 2250.
        # Total before absorption = 5050, residual = 50.
        # Now suppose aporte was 5150:
        # new_total = 7650. Targets: ACN 3825 (gap 2825), FII 3825 (gap 2325).
        # ACN: floor(2825 / 100) = 28 shares = 2800.
        # FII: floor(2325 / 150) = 15 shares = 2250.
        # Total before absorption = 5050, residual = 100.
        # Whole share absorber gives STOCK_A 29th share (+100).
        # Total after absorption = 2900 + 2250 = 5150.0 (0 leftover).
        sug2 = compute_suggestions(portfolio, 5150)
        assert sum(s.suggestion_value for s in sug2) == 5150.0

    def test_exclude_whole_share_assets_redistributes_with_minimal_leftover(self):
        """User scenario: 5000 aporte across whole-share assets, delete one,
        it rebalances and maximizes utilization without large leftover."""
        assets = [
            _make_asset("a1", "acoes_nacionais", 5, strength=3, price=500.0),
            _make_asset("a2", "acoes_nacionais", 10, strength=3, price=100.0),
            _make_asset("a3", "fundos_imobiliarios", 10, strength=3, price=150.0),
        ]
        targets = {
            "acoes_nacionais": 60.0,
            "fundos_imobiliarios": 40.0,
            "criptomoedas": 0.0,
            "rendafixa": 0.0,
            "acoes_internacionais": 0.0,
            "reits": 0.0,
            "rendafixa_internacional": 0.0,
        }
        portfolio = _make_portfolio(assets, targets)

        # Exclude a1 (the 500.0 stock)
        suggestions = compute_suggestions(portfolio, 5000, exclude_ids={"a1"})
        total = sum(s.suggestion_value for s in suggestions)
        # Leftover should be minimized (at most < min(price), which is 100)
        assert 5000 - total < 100.0
        ids = {s.asset_id for s in suggestions}
        assert "a1" not in ids
        assert "a2" in ids and "a3" in ids

