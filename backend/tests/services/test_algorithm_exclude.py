"""Exclusions preserve exposure and targets; unused cash is explicit."""

from __future__ import annotations

import itertools
import random

import pytest

from app.services.algorithm import compute_suggestions
from app.services.strength import position_value
from app.services.types import Asset, Portfolio


def asset(id, type, amount, price, strength=1):
    return Asset(id=id, type=type, name=id, amount=amount, current_price=price, strength=strength)


def assert_limits(portfolio, aporte, excluded, suggestions):
    assert all(s.asset_id not in excluded for s in suggestions)
    assert sum(s.suggestion_value for s in suggestions) <= aporte + 1e-6
    new_total = sum(position_value(a) for a in portfolio.assets) + aporte
    for cls in portfolio.targets:
        bought = sum(s.suggestion_value for s in suggestions if s.asset_type == cls)
        current = sum(position_value(a) for a in portfolio.assets if a.type == cls)
        assert bought <= max(0, new_total * portfolio.targets[cls] / 100 - current) + 1e-6
    for s in suggestions:
        if s.tracking_mode == "units":
            assert s.suggestion_value == pytest.approx(s.suggestion_quantity * s.current_price)


@pytest.mark.parametrize("aporte", [50, 500, 1000, 5000])
def test_all_exclusion_combinations_respect_targets(aporte):
    portfolio = Portfolio(
        assets=[
            asset("btc", "criptomoedas", 0.5, 500, 0),
            asset("bbas", "acoes_nacionais", 10, 100),
            asset("cdb", "rendafixa", 1000, None, 0),
            asset("us", "acoes_internacionais", 5, 200),
            asset("reit", "reits", 3, 150),
        ],
        targets={
            "criptomoedas": 20,
            "acoes_nacionais": 30,
            "rendafixa": 10,
            "acoes_internacionais": 25,
            "reits": 15,
        },
        questions=[],
    )
    ids = [a.id for a in portfolio.assets]
    for count in range(6):
        for combination in itertools.combinations(ids, count):
            excluded = set(combination)
            suggestions = compute_suggestions(portfolio, aporte, excluded)
            assert_limits(portfolio, aporte, excluded, suggestions)
            assert suggestions == compute_suggestions(portfolio, aporte, excluded)


def test_excluding_overweight_stock_still_counts_its_exposure():
    portfolio = Portfolio(
        assets=[
            asset("excluded", "acoes_nacionais", 100, 100),
            asset("other", "acoes_nacionais", 0, 100),
            asset("rf", "rendafixa", 0, None, 0),
        ],
        targets={"acoes_nacionais": 50, "rendafixa": 50},
        questions=[],
    )
    result = compute_suggestions(portfolio, 1000, {"excluded"})
    assert {s.asset_id for s in result} == {"rf"}
    assert result[0].suggestion_value == 1000


def test_only_overweight_remaining_asset_does_not_receive_entire_deposit():
    portfolio = Portfolio(
        assets=[asset("cdb", "rendafixa", 1000, None, 0), asset("btc", "criptomoedas", 1, 100)],
        targets={"rendafixa": 20, "criptomoedas": 80},
        questions=[],
    )
    assert compute_suggestions(portfolio, 500, {"btc"}) == []


def test_residual_does_not_buy_overweight_or_zero_target_absorbers():
    portfolio = Portfolio(
        assets=[
            asset("stock", "acoes_nacionais", 5, 90, 3),
            asset("btc", "criptomoedas", 1, 1000, 0),
            asset("manual", "rendafixa", 0, None, 0),
        ],
        targets={"acoes_nacionais": 70, "criptomoedas": 30, "rendafixa": 0},
        questions=[],
    )
    result = compute_suggestions(portfolio, 500, {"btc"})
    assert {s.asset_id for s in result} == {"stock"}
    assert sum(s.suggestion_value for s in result) == 450
    assert_limits(portfolio, 500, {"btc"}, result)


def test_whole_share_residual_cannot_exceed_class_target():
    portfolio = Portfolio(
        assets=[
            asset("stock", "acoes_nacionais", 10, 100, 3),
            asset("fii", "fundos_imobiliarios", 10, 150, 3),
        ],
        targets={"acoes_nacionais": 50, "fundos_imobiliarios": 50},
        questions=[],
    )
    result = compute_suggestions(portfolio, 5150)
    assert sum(s.suggestion_value for s in result) == 5050
    assert_limits(portfolio, 5150, set(), result)


def test_random_portfolios_never_overspend_or_violate_targets():
    rng = random.Random(42)
    for _ in range(150):
        classes = ["acoes_nacionais", "rendafixa", "criptomoedas"]
        weights = [rng.uniform(1, 10) for _ in classes]
        targets = {cls: 100 * w / sum(weights) for cls, w in zip(classes, weights)}
        assets = [
            asset(str(i), cls, rng.uniform(0, 100), rng.uniform(1, 1000), rng.randint(0, 10))
            for i, cls in enumerate(classes * 3)
        ]
        portfolio = Portfolio(assets=assets, targets=targets, questions=[])
        excluded = {a.id for a in assets if rng.random() < 0.25}
        aporte = rng.uniform(1, 10000)
        assert_limits(portfolio, aporte, excluded, compute_suggestions(portfolio, aporte, excluded))
