from __future__ import annotations

from trader_core.execution.sizing import size_position


def _size(**kw):
    base = dict(
        premium_per_share=1.00, sizing_mode="fixed_dollar",
        max_per_trade_usd=250, max_premium_per_contract=2.00,
        max_capital_usd=2000, current_open_exposure_usd=0,
        broker_buying_power_usd=100_000,
    )
    base.update(kw)
    return size_position(**base)


def test_premium_invalid():
    d = _size(premium_per_share=0)
    assert d.contracts == 0 and d.reason == "premium_invalid"


def test_premium_too_high():
    d = _size(premium_per_share=2.50, max_premium_per_contract=2.00)
    assert d.contracts == 0 and d.reason == "premium_too_high"


def test_fixed_dollar_count():
    d = _size(premium_per_share=1.00, sizing_mode="fixed_dollar", max_per_trade_usd=250)
    # $100/contract, $250 budget -> 2 contracts, $200
    assert d.contracts == 2 and d.cost_usd == 200 and d.reason == "ok"


def test_one_contract_mode():
    d = _size(premium_per_share=1.00, sizing_mode="one_contract", max_per_trade_usd=250)
    assert d.contracts == 1 and d.reason == "ok"


def test_no_buying_power():
    # $300/contract but per-trade cap is $250
    d = _size(premium_per_share=3.00, max_premium_per_contract=5.00, max_per_trade_usd=250)
    assert d.contracts == 0 and d.reason == "no_buying_power"


def test_cap_exceeded():
    d = _size(current_open_exposure_usd=2000, max_capital_usd=2000)
    assert d.contracts == 0 and d.reason == "cap_exceeded"
