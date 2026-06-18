from __future__ import annotations

import pytest

from trader_core.execution.intent import LONG_CALL, LONG_PUT, TradeIntent


def test_long_call_option_type():
    i = TradeIntent(underlying="NVDA", direction=LONG_CALL, target_dte=35,
                    strike_rule="ATM", signal_id="2026-06-16-NVDA")
    assert i.option_type == "call"


def test_long_put_option_type():
    i = TradeIntent(underlying="SPY", direction=LONG_PUT, target_dte=30,
                    strike_rule="DELTA:0.50", signal_id="s1")
    assert i.option_type == "put"


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        TradeIntent(underlying="NVDA", direction="short_call", target_dte=35,
                    strike_rule="ATM", signal_id="s1")


def test_nonpositive_dte_raises():
    with pytest.raises(ValueError):
        TradeIntent(underlying="NVDA", direction=LONG_CALL, target_dte=0,
                    strike_rule="ATM", signal_id="s1")


def test_missing_underlying_raises():
    with pytest.raises(ValueError):
        TradeIntent(underlying="", direction=LONG_CALL, target_dte=35,
                    strike_rule="ATM", signal_id="s1")


def test_missing_signal_id_raises():
    with pytest.raises(ValueError):
        TradeIntent(underlying="NVDA", direction=LONG_CALL, target_dte=35,
                    strike_rule="ATM", signal_id="")
