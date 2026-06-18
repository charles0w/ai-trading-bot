from __future__ import annotations

from datetime import datetime

from trader_core.config import MarketCfg, TradingAccountCfg
from trader_core.execution.risk import PT, RiskState, approve, in_trading_window

WEEKDAY_OPEN = datetime(2026, 6, 16, 9, 0, tzinfo=PT)   # Tue, within window, not a holiday


def _approve(**kw):
    base = dict(
        state=RiskState(), now_pt=WEEKDAY_OPEN, open_position_count=0,
        open_exposure_usd=0, config_trading_account=TradingAccountCfg(),
        config_market=MarketCfg(), signal_age_seconds=10,
    )
    base.update(kw)
    return approve(**base)


def test_happy_path():
    ok, why = _approve()
    assert ok and why == "ok"


def test_kill_switch():
    st = RiskState(kill_switch_engaged=True)
    ok, why = _approve(state=st)
    assert not ok and why == "kill_switch"


def test_daily_loss_breach_engages_kill_switch():
    st = RiskState(daily_realized_pnl_usd=-10_001)
    ok, why = _approve(state=st)
    assert not ok and why == "daily_loss_breach" and st.kill_switch_engaged


def test_max_open_positions():
    ok, why = _approve(open_position_count=50)
    assert not ok and why == "max_open_positions"


def test_max_capital():
    ok, why = _approve(open_exposure_usd=100_000)
    assert not ok and why == "max_capital"


def test_outside_trading_window():
    ok, why = _approve(now_pt=datetime(2026, 6, 16, 5, 0, tzinfo=PT))
    assert not ok and why == "outside_trading_window"


def test_stale_signal():
    ok, why = _approve(signal_age_seconds=90_000)
    assert not ok and why == "stale_signal"


def test_spread_too_wide():
    ok, why = _approve(spread_pct=20.0)
    assert not ok and why == "spread_too_wide"


def test_open_interest_too_low():
    ok, why = _approve(open_interest=50)
    assert not ok and why == "open_interest_too_low"


def test_weekend_not_in_window():
    assert not in_trading_window(datetime(2026, 6, 20, 9, 0, tzinfo=PT), "06:30", "12:55")
