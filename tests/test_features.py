from __future__ import annotations

from datetime import date, timedelta

from atb.data.provider import EarningsEvent, PriceBar
from atb.features import (
    compute_features, momentum, pct_from_high, pead_baseline_intent, realized_vol,
)
from atb.features import FeatureVector
from trader_core.execution.intent import LONG_CALL, LONG_PUT


class FakeProvider:
    def __init__(self, bars, earnings=None, spot=None):
        self._bars, self._earn, self._spot = bars, earnings, spot

    def daily_bars(self, symbol, *, lookback_days=500):
        return self._bars

    def latest_price(self, symbol):
        return self._spot if self._spot is not None else (self._bars[-1].close if self._bars else None)

    def recent_earnings(self, symbol, *, asof):
        return self._earn

    def option_chain(self, symbol, *, expiry, option_type):
        return []


def _bars(n, start, fn):
    out, d = [], start
    for i in range(n):
        c = fn(i)
        out.append(PriceBar(day=d, open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1e6))
        d += timedelta(days=1)
    return out


# --- pure math ---

def test_momentum():
    assert abs(momentum([10, 11, 12, 13], lookback=2, skip=1) - 0.2) < 1e-9  # 12/10 - 1
    assert momentum([1, 2, 3], lookback=252, skip=21) is None     # too short


def test_realized_vol_constant_is_zero():
    assert realized_vol([100] * 30) == 0.0


def test_pct_from_high():
    assert abs(pct_from_high(100, [90, 110, 100]) - (100 / 110 - 1)) < 1e-9


# --- regression: a poisoned 0.0 close (yfinance NaN coercion) must not crash ---

def test_realized_vol_skips_nonpositive_close():
    # a 0.0 close in the window used to raise ValueError: math domain error
    rv = realized_vol([100.0] * 29 + [0.0])
    assert rv is not None and rv >= 0.0


def test_momentum_none_on_nonpositive():
    assert momentum([1.0, 0.0, 1.0, 1.0, 1.0], lookback=3, skip=0) is None  # past (idx -4) == 0
    assert momentum([1.0, 1.0, 1.0, 1.0, 0.0], lookback=3, skip=0) is None  # recent (idx -1) == 0


def test_pct_from_high_ignores_zeros_and_zero_spot():
    assert abs(pct_from_high(100, [0.0, 110, 0.0]) - (100 / 110 - 1)) < 1e-9
    assert pct_from_high(0.0, [110]) is None


# --- builder ---

def test_compute_features_uptrend_with_earnings():
    bars = _bars(300, date(2025, 8, 1), lambda i: 100 * (1.001 ** i))
    asof = bars[-1].day
    earn = EarningsEvent(symbol="NVDA", day=bars[-4].day, eps_actual=1.2, eps_estimate=1.0)
    fv = compute_features(FakeProvider(bars, earnings=earn), "NVDA", asof=asof)
    assert fv.mom_12_1 is not None and fv.mom_12_1 > 0
    assert fv.realized_vol_20d is not None and fv.realized_vol_20d >= 0
    assert fv.pct_from_52w_high is not None and fv.pct_from_52w_high <= 0  # spot below high
    assert fv.days_since_earnings == (asof - bars[-4].day).days
    assert fv.post_earnings_return is not None and fv.post_earnings_return > 0


def test_compute_features_no_bars():
    fv = compute_features(FakeProvider([]), "XYZ", asof=date(2026, 6, 17))
    assert fv.spot is None and fv.mom_12_1 is None


# --- regression: drift must be None, not 0.0, when the feed is truncated ---
# (2026-07-26: yfinance served the newest session with a NaN close, so bars
# ended on the earnings day itself and spot == base close → fabricated 0.0
# drift fed to the signal and the LLM analyst.)

def test_drift_none_when_base_bar_is_newest_and_spot_equals_close():
    bars = _bars(300, date(2025, 8, 1), lambda i: 100 * (1.001 ** i))
    asof = bars[-1].day + timedelta(days=2)  # weekend after a truncated feed
    earn = EarningsEvent(symbol="INTC", day=bars[-1].day, eps_actual=1.2, eps_estimate=1.0)
    fv = compute_features(FakeProvider(bars, earnings=earn), "INTC", asof=asof)
    assert fv.post_earnings_return is None  # was exactly 0.0 before the fix


def test_drift_computed_from_fresh_quote_without_later_bar():
    bars = _bars(300, date(2025, 8, 1), lambda i: 100 * (1.001 ** i))
    asof = bars[-1].day + timedelta(days=1)
    earn = EarningsEvent(symbol="INTC", day=bars[-1].day, eps_actual=1.2, eps_estimate=1.0)
    spot = bars[-1].close * 1.03  # live quote fresher than the stale bars
    fv = compute_features(FakeProvider(bars, earnings=earn, spot=spot), "INTC", asof=asof)
    assert fv.post_earnings_return is not None
    assert abs(fv.post_earnings_return - 0.03) < 1e-9


def test_drift_true_zero_survives_when_later_bar_exists():
    # a genuine flat close after the print is legitimate data, not an artifact
    bars = _bars(300, date(2025, 8, 1), lambda i: 100.0)
    asof = bars[-1].day
    earn = EarningsEvent(symbol="T", day=bars[-3].day, eps_actual=1.0, eps_estimate=1.0)
    fv = compute_features(FakeProvider(bars, earnings=earn), "T", asof=asof)
    assert fv.post_earnings_return == 0.0


# --- drift decomposition (gap vs subsequent drift — pop-and-fade detection) ---

def test_drift_decomposition_separates_gap_from_fade():
    # print-day close 100, next session gaps to 108, then bleeds to 103:
    # old single number said +3% "drift"; decomposition shows +8% gap, -4.6% fade
    closes = [100.0] * 296 + [100.0, 108.0, 105.0, 103.0]
    bars = _bars(300, date(2025, 8, 1), lambda i: closes[i])
    asof = bars[-1].day
    earn = EarningsEvent(symbol="INTC", day=bars[-4].day, eps_actual=1.3, eps_estimate=1.0)
    fv = compute_features(FakeProvider(bars, earnings=earn), "INTC", asof=asof)
    assert abs(fv.gap_day1 - 0.08) < 1e-9                      # 108/100 - 1
    assert abs(fv.drift_since_day1 - (103.0 / 108.0 - 1)) < 1e-9   # fading
    assert fv.post_earnings_return is not None and fv.post_earnings_return > 0


def test_drift_decomposition_none_without_post_print_bar():
    bars = _bars(300, date(2025, 8, 1), lambda i: 100 * (1.001 ** i))
    asof = bars[-1].day + timedelta(days=2)
    earn = EarningsEvent(symbol="INTC", day=bars[-1].day, eps_actual=1.2, eps_estimate=1.0)
    fv = compute_features(FakeProvider(bars, earnings=earn), "INTC", asof=asof)
    assert fv.gap_day1 is None and fv.drift_since_day1 is None


# --- peer-earnings surprise (A4/A6) ---

class CalendarProvider(FakeProvider):
    def __init__(self, bars, calendar, **kw):
        super().__init__(bars, **kw)
        self._cal = calendar

    def earnings_calendar(self, frm, to, symbol=None):
        return self._cal


def test_peer_surprise_fires_for_non_reporter(monkeypatch):
    import atb.features as F
    monkeypatch.setattr(F, "_peer_cal_cache", {})
    bars = _bars(300, date(2025, 8, 1), lambda i: 100.0)
    cal = [
        {"symbol": "INTC", "epsActual": 1.2, "epsEstimate": 1.0},   # +20% — AMD's peer
        {"symbol": "JPM", "epsActual": 0.9, "epsEstimate": 1.0},    # not AMD's peer
    ]
    fv = compute_features(CalendarProvider(bars, cal), "AMD", asof=bars[-1].day)
    assert abs(fv.peer_surprise_pct - 20.0) < 1e-9
    assert fv.meta["peer_symbol"] == "INTC"


def test_peer_surprise_none_without_peer_events(monkeypatch):
    import atb.features as F
    monkeypatch.setattr(F, "_peer_cal_cache", {})
    bars = _bars(300, date(2025, 8, 1), lambda i: 100.0)
    cal = [{"symbol": "XOM", "epsActual": 2.0, "epsEstimate": 1.0}]  # not a semi peer
    fv = compute_features(CalendarProvider(bars, cal), "AMD", asof=bars[-1].day)
    assert fv.peer_surprise_pct is None


# --- VIX regime ---

class VixProvider(FakeProvider):
    def daily_bars(self, symbol, *, lookback_days=500):
        if symbol == "^VIX":
            vals = [15.0] * 34 + [16.0, 18.0, 20.0, 22.0, 23.0, 24.0]
            return _bars(40, date(2026, 5, 1), lambda i: vals[i])
        return self._bars


def test_vix_regime_level_and_change(monkeypatch):
    import atb.features as F
    monkeypatch.setattr(F, "_vix_cache", {})
    bars = _bars(300, date(2025, 8, 1), lambda i: 100.0)
    fv = compute_features(VixProvider(bars), "AAPL", asof=bars[-1].day)
    assert fv.vix == 24.0
    assert abs(fv.vix_5d_change - (24.0 / 16.0 - 1)) < 1e-9   # spiking regime


# --- baseline intent stub ---

def test_baseline_long_call_in_window():
    fv = FeatureVector(symbol="NVDA", asof=date(2026, 6, 17), spot=200.0,
                       days_since_earnings=3, post_earnings_return=0.05)
    intent = pead_baseline_intent(fv)
    assert intent is not None and intent.direction == LONG_CALL


def test_baseline_long_put_on_negative_drift():
    fv = FeatureVector(symbol="NVDA", asof=date(2026, 6, 17), spot=200.0,
                       days_since_earnings=2, post_earnings_return=-0.04)
    assert pead_baseline_intent(fv).direction == LONG_PUT


def test_baseline_none_outside_window():
    fv = FeatureVector(symbol="NVDA", asof=date(2026, 6, 17), spot=200.0,
                       days_since_earnings=12, post_earnings_return=0.05)
    assert pead_baseline_intent(fv) is None
