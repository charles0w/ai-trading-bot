from __future__ import annotations

from datetime import date, timedelta

from atb.chain_snapshots import ChainSnapshots
from atb.data.provider import EarningsEvent, OptionQuote
from atb.features import compute_features

from test_features import FakeProvider, _bars


# --- store semantics ---

def test_record_is_idempotent_per_day_symbol(tmp_path):
    s = ChainSnapshots(tmp_path / "c.jsonl")
    row = {"date": "2026-07-27", "symbol": "INTC", "atm_iv": 0.5}
    assert s.record(row) is True
    assert s.record(row) is False
    assert len(s._rows()) == 1
    assert s.record({**row, "date": "2026-07-28"}) is True   # next day appends


def test_iv_percentile_needs_min_obs(tmp_path):
    s = ChainSnapshots(tmp_path / "c.jsonl")
    for i in range(9):
        s.record({"date": f"2026-07-{10+i:02d}", "symbol": "INTC", "atm_iv": 0.30 + i * 0.01})
    assert s.iv_percentile("INTC", 0.35) is None              # 9 obs < 10 — honest None
    s.record({"date": "2026-07-19", "symbol": "INTC", "atm_iv": 0.39})
    p = s.iv_percentile("INTC", 0.39)
    assert p == 100.0                                          # at the top of its range
    assert s.iv_percentile("INTC", 0.30) == 10.0               # bottom decile
    assert s.iv_percentile("AAPL", 0.5) is None                # other symbols unaffected


# --- feature enrichment end-to-end (fake chain provider) ---

class ChainProvider(FakeProvider):
    """FakeProvider + the optional option_expiries capability."""

    def option_expiries(self, symbol):
        today = date.today()
        return [today + timedelta(days=3),     # too near — must be skipped
                today + timedelta(days=34),    # nearest to 35-DTE target
                today + timedelta(days=62)]

    def option_chain(self, symbol, *, expiry, option_type):
        return [
            OptionQuote("X1", strike=95.0, expiry=expiry, option_type="call",
                        bid=9.0, ask=9.4, iv=0.61, open_interest=500, volume=120.0),
            OptionQuote("X2", strike=100.0, expiry=expiry, option_type="call",
                        bid=5.0, ask=5.2, iv=0.55, open_interest=1500, volume=800.0),
            OptionQuote("X3", strike=110.0, expiry=expiry, option_type="call",
                        bid=1.8, ask=2.0, iv=0.52, open_interest=900, volume=50.0),
        ]


def test_chain_enrichment_fills_atm_and_records_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ATB_CHAIN_SNAPSHOT_PATH", str(tmp_path / "c.jsonl"))
    bars = _bars(300, date.today() - timedelta(days=299), lambda i: 100.0)
    earn = EarningsEvent(symbol="INTC", day=date.today() - timedelta(days=2),
                         eps_actual=1.3, eps_estimate=1.0)
    fv = compute_features(ChainProvider(bars, earnings=earn), "INTC", asof=date.today())
    assert fv.atm_iv == 0.55                      # 100-strike is ATM at spot 100
    assert fv.open_interest == 1500
    assert fv.spread_pct is not None and fv.spread_pct < 5
    assert fv.iv_rank is None                     # no history yet — honest None
    rows = ChainSnapshots(tmp_path / "c.jsonl")._rows()
    assert len(rows) == 1 and rows[0]["symbol"] == "INTC"
    assert rows[0]["atm_iv"] == 0.55 and rows[0]["volume"] == 800.0
    # re-run same day: no duplicate snapshot
    compute_features(ChainProvider(bars, earnings=earn), "INTC", asof=date.today())
    assert len(ChainSnapshots(tmp_path / "c.jsonl")._rows()) == 1


class JunkChainProvider(ChainProvider):
    """Simulates yfinance off-hours junk: absurd IV, zeroed bid/ask/OI."""

    def option_chain(self, symbol, *, expiry, option_type):
        return [OptionQuote("J", strike=100.0, expiry=expiry, option_type="call",
                            bid=0.0, ask=0.0, iv=0.0039, open_interest=0, volume=None)]


def test_junk_offhours_chain_is_rejected_and_not_snapshotted(tmp_path, monkeypatch):
    # 2026-07-27 regression: an off-hours chain served iv=0.0039 with zeroed
    # quotes — recording it would poison the iv_percentile baseline forever
    monkeypatch.setenv("ATB_CHAIN_SNAPSHOT_PATH", str(tmp_path / "c.jsonl"))
    bars = _bars(300, date.today() - timedelta(days=299), lambda i: 100.0)
    fv = compute_features(JunkChainProvider(bars), "INTC", asof=date.today())
    assert fv.atm_iv is None and fv.open_interest is None
    assert not (tmp_path / "c.jsonl").exists() or ChainSnapshots(tmp_path / "c.jsonl")._rows() == []


def test_no_chain_capability_no_enrichment(tmp_path, monkeypatch):
    monkeypatch.setenv("ATB_CHAIN_SNAPSHOT_PATH", str(tmp_path / "c.jsonl"))
    bars = _bars(300, date.today() - timedelta(days=299), lambda i: 100.0)
    fv = compute_features(FakeProvider(bars), "INTC", asof=date.today())
    assert fv.atm_iv is None and fv.spread_pct is None
    assert not (tmp_path / "c.jsonl").exists() or ChainSnapshots(tmp_path / "c.jsonl")._rows() == []
