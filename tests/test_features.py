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
