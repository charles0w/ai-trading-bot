from __future__ import annotations

import random
from datetime import date, timedelta

from atb.data.provider import PriceBar
from atb.signal.logistic import LogisticSignal
from atb.train.dataset import make_rows_for_symbol
from atb.train.trainer import accuracy, train_logistic


def _bars(n, start, fn):
    out, d = [], start
    for i in range(n):
        c = fn(i)
        out.append(PriceBar(d, c, c * 1.01, c * 0.99, c, 1e6))
        d += timedelta(days=1)
    return out


# --- dataset labeling ---

def test_make_rows_labels_uptrend_as_one():
    bars = _bars(300, date(2025, 8, 1), lambda i: 100 * (1.002 ** i))
    ed = bars[-12].day                      # earnings ~12 days before end
    rows = make_rows_for_symbol(bars, [ed], horizon_days=5, entry_offset_days=2,
                                sue_by_day={ed: 2.0})
    assert len(rows) == 1
    feat, label = rows[0]
    assert label == 1                        # uptrend -> up
    assert feat["sue"] == 2.0 and "mom_12_1" in feat


def test_make_rows_skips_when_no_future_bars():
    bars = _bars(300, date(2025, 8, 1), lambda i: 100 + i)
    ed = bars[-1].day                        # no bars after entry+horizon
    assert make_rows_for_symbol(bars, [ed], horizon_days=5) == []


# --- trainer learns a separable signal ---

def test_trainer_learns_sue_sign():
    random.seed(0)
    rows = []
    for _ in range(400):
        s = random.uniform(-3, 3)
        feat = {"sue": s, "post_earnings_return": 0.0, "mom_12_1": 0.0,
                "mom_6_1": 0.0, "realized_vol_20d": 0.0}
        rows.append((feat, 1 if s > 0 else 0))   # label determined by sign of sue
    model = train_logistic(rows, epochs=400, lr=0.5)
    assert model.weights["sue"] > 0
    assert accuracy(model, rows) > 0.9


def test_trained_model_scores_direction_in_window():
    rows = [({"sue": s, "post_earnings_return": 0.0, "mom_12_1": 0.0, "mom_6_1": 0.0,
              "realized_vol_20d": 0.0}, 1 if s > 0 else 0)
            for s in [3, 2, 1, -1, -2, -3] * 30]
    model = train_logistic(rows, epochs=300, lr=0.5)
    from atb.features import FeatureVector
    fv_up = FeatureVector(symbol="X", asof=date(2026, 6, 17), spot=100.0,
                          days_since_earnings=2, sue=2.5)
    fv_out = FeatureVector(symbol="X", asof=date(2026, 6, 17), spot=100.0,
                           days_since_earnings=30, sue=2.5)
    assert model.score(fv_up).direction == "up"
    assert model.score(fv_out).direction == "flat"


def test_build_dataset_uses_earnings_history():
    from atb.data.provider import EarningsEvent
    from atb.train.dataset import build_dataset

    bars = _bars(500, date(2024, 6, 1), lambda i: 100 * (1.001 ** i))

    class FakeProv:
        def daily_bars(self, sym, *, lookback_days=500):
            return bars
        def earnings_history(self, sym, *, years=3):
            # three past events spaced ~120 days, all with room for a forward window
            return [EarningsEvent(sym, bars[i].day, 1.2, 1.0) for i in (150, 270, 390)]

    rows = build_dataset(FakeProv(), ["NVDA"], years=3)
    assert len(rows) == 3
    assert all(r[1] in (0, 1) for r in rows)
    assert all("mom_12_1" in r[0] for r in rows)


def test_logistic_save_load_roundtrip(tmp_path):
    m = LogisticSignal(weights={"sue": 1.5, "post_earnings_return": 2.0, "mom_12_1": 0.3,
                                "mom_6_1": 0.1, "realized_vol_20d": -0.2}, bias=0.1)
    p = tmp_path / "model.json"
    m.save(p)
    loaded = LogisticSignal.load(p)
    assert loaded.weights["sue"] == 1.5 and loaded.bias == 0.1
