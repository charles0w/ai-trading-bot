from __future__ import annotations

from datetime import date, datetime, timedelta

from atb.data.provider import EarningsEvent, PriceBar
from atb.eval.predictions import PredictionLog
from atb.pipeline import run_symbol
from atb.signal.llm_analyst import LLMAnalyst
from atb.signal.pead_model import PeadHeuristicModel
from atb.store_sqlite import SQLiteStore
from trader_core.execution.risk import PT

from conftest import FakeBroker

ASOF = date(2026, 6, 17)
NOW_PT = datetime(2026, 6, 17, 9, 0, tzinfo=PT)   # weekday, in trading window


class _Provider:
    """Strong-uptrend prices + a recent positive-surprise earnings event."""

    def __init__(self):
        self._bars = []
        d = ASOF - timedelta(days=299)
        for i in range(300):
            c = 100 * (1.002 ** i)
            self._bars.append(PriceBar(d, c, c * 1.01, c * 0.99, c, 1e6))
            d += timedelta(days=1)

    def daily_bars(self, symbol, *, lookback_days=500):
        return self._bars

    def latest_price(self, symbol):
        return self._bars[-1].close

    def recent_earnings(self, symbol, *, asof):
        return EarningsEvent(symbol=symbol, day=asof - timedelta(days=2),
                             eps_actual=1.3, eps_estimate=1.0, sue=2.5)

    def option_chain(self, symbol, *, expiry, option_type):
        return []


def _agree_analyst():
    return LLMAnalyst(lambda prompt: '{"direction":"up","conviction":0.8,"rationale":"strong SUE+drift"}')


def _disagree_analyst():
    return LLMAnalyst(lambda prompt: '{"direction":"down","conviction":0.9,"rationale":"fade"}')


def test_pipeline_dry_run_logs_prediction_no_position(tmp_path):
    store = SQLiteStore(":memory:")
    predlog = PredictionLog(tmp_path / "p.jsonl")
    d = run_symbol("NVDA", provider=_Provider(), signal=PeadHeuristicModel(),
                   analyst=_agree_analyst(), broker=FakeBroker(), store=store,
                   predlog=predlog, asof=ASOF, now_pt=NOW_PT, execute=False)
    assert d.decision == "dry_run"
    assert d.intent is not None and d.intent.direction == "long_call"
    assert len(predlog.load()) == 1
    assert store.open_positions() == []      # nothing placed in dry run


def test_pipeline_execute_opens_position(tmp_path):
    store = SQLiteStore(":memory:")
    predlog = PredictionLog(tmp_path / "p.jsonl")
    d = run_symbol("NVDA", provider=_Provider(), signal=PeadHeuristicModel(),
                   analyst=_agree_analyst(), broker=FakeBroker(fill_sequence=("filled",)),
                   store=store, predlog=predlog, asof=ASOF, now_pt=NOW_PT, execute=True)
    assert d.decision == "placed" and d.position_id is not None
    assert len(store.open_positions()) == 1
    assert len(predlog.load()) == 1


def test_pipeline_no_trade_on_disagreement(tmp_path):
    store = SQLiteStore(":memory:")
    predlog = PredictionLog(tmp_path / "p.jsonl")
    d = run_symbol("NVDA", provider=_Provider(), signal=PeadHeuristicModel(),
                   analyst=_disagree_analyst(), broker=FakeBroker(), store=store,
                   predlog=predlog, asof=ASOF, now_pt=NOW_PT, execute=False)
    assert d.decision == "no_trade" and d.reason == "signal_no_trade"
    assert predlog.load() == []
