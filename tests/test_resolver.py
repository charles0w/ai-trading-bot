from __future__ import annotations

from datetime import date, timedelta

from trader_core.execution.intent import LONG_CALL, LONG_PUT, TradeIntent
from trader_core.execution.resolver import resolve_contract, target_strike

from conftest import FakeBroker

TODAY = date(2026, 6, 17)  # Wednesday


def _intent(direction=LONG_CALL, strike_rule="ATM", dte=35):
    return TradeIntent(underlying="NVDA", direction=direction, target_dte=dte,
                       strike_rule=strike_rule, signal_id="s1")


def test_target_strike_rules():
    assert target_strike("ATM", 200, "call") == 200
    assert target_strike("ABS:215", 200, "call") == 215
    assert target_strike("OTM:5pct", 200, "call") == 210      # call OTM = above
    assert target_strike("OTM:5%", 200, "put") == 190         # put OTM = below
    assert target_strike("ITM:5pct", 200, "call") == 190      # call ITM = below


def test_resolves_atm_nearest_strike():
    b = FakeBroker(spot=200.0, strike_step=5.0, mark=4.0)
    c = resolve_contract(b, _intent(strike_rule="ATM"), spot_price=200.0, today=TODAY)
    assert c is not None and c.strike == 200.0
    assert c.option_type == "call"
    assert c.mid is not None            # came back priced


def test_resolves_otm_call():
    b = FakeBroker(spot=200.0, strike_step=5.0)
    c = resolve_contract(b, _intent(strike_rule="OTM:5pct"), spot_price=200.0, today=TODAY)
    assert c.strike == 210.0


def test_resolves_otm_put():
    b = FakeBroker(spot=200.0, strike_step=5.0)
    c = resolve_contract(b, _intent(direction=LONG_PUT, strike_rule="OTM:5pct"),
                         spot_price=200.0, today=TODAY)
    assert c.strike == 190.0


def test_picks_expiry_near_target_dte():
    b = FakeBroker(spot=200.0, strike_step=5.0)
    c = resolve_contract(b, _intent(dte=35), spot_price=200.0, today=TODAY)
    target = TODAY + timedelta(days=35)
    assert c.expiry.weekday() == 4               # a Friday
    assert abs((c.expiry - target).days) <= 7    # within the window, nearest


def test_empty_chain_returns_none():
    b = FakeBroker(spot=202.0, strike_step=5.0)
    # off-strike spot (202) + tiny band -> window excludes every $5 strike
    c = resolve_contract(b, _intent(strike_rule="ATM"), spot_price=202.0,
                         today=TODAY, strike_band_pct=0.001)
    assert c is None
