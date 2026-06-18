"""Assemble labeled training rows from historical earnings + prices.

For each past earnings event: compute the SAME features the live brain uses,
point-in-time as of the entry day (earnings + entry_offset), and label it 1 if
the underlying rose over the next `horizon_days`, else 0. This is the labeled
dataset the logistic model trains on.

`make_rows_for_symbol` is pure (operates on already-fetched data) so it's
unit-tested offline; `build_dataset` does the live fetching (Mac).
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta

from ..features import momentum, realized_vol
from ..signal.logistic import FEATURES


def _first_idx_on_or_after(days: list[date], target: date) -> int | None:
    for i, d in enumerate(days):
        if d >= target:
            return i
    return None


def make_rows_for_symbol(bars, earnings_days, *, horizon_days: int = 5,
                         entry_offset_days: int = 2, sue_by_day=None):
    """bars: ascending PriceBar list. earnings_days: list[date]. sue_by_day: optional
    {date: sue}. Returns list of (feature_dict, label)."""
    sue_by_day = sue_by_day or {}
    days = [b.day for b in bars]
    closes = [b.close for b in bars]
    rows = []
    for ed in earnings_days:
        ei = _first_idx_on_or_after(days, ed + timedelta(days=entry_offset_days))
        xi = _first_idx_on_or_after(days, ed + timedelta(days=entry_offset_days + horizon_days))
        bi = _first_idx_on_or_after(days, ed)
        if ei is None or xi is None or xi <= ei or bi is None:
            continue
        c_upto = closes[: ei + 1]
        spot = closes[ei]
        drift = (spot / closes[bi] - 1) if closes[bi] else None
        feat = {
            "sue": sue_by_day.get(ed),
            "post_earnings_return": drift,
            "mom_12_1": momentum(c_upto, lookback=252, skip=21),
            "mom_6_1": momentum(c_upto, lookback=126, skip=21),
            "realized_vol_20d": realized_vol(c_upto),
        }
        feat = {k: (float(v) if v is not None else 0.0) for k, v in feat.items()}
        rows.append((feat, 1 if closes[xi] > closes[ei] else 0))
    return rows


def build_dataset(provider, symbols, *, years: int = 3, horizon_days: int = 5,
                  entry_offset_days: int = 2, verbose: bool = False, pause: float = 0.0):
    """Live dataset build (needs network). For each symbol: pull ~`years` of bars
    + earnings history (announce date + actual/estimate), compute per-event SUE
    from the expanding surprise series, and emit labeled rows. `provider` must
    expose daily_bars + earnings_history (FinnhubProvider delegates the latter to
    yfinance, which has reliable announce dates and no per-symbol rate limit)."""
    import time
    rows = []
    for sym in symbols:
        if pause:
            time.sleep(pause)
        try:
            bars = provider.daily_bars(sym, lookback_days=int(years * 365) + 90)
            events = provider.earnings_history(sym, years=years)   # sorted ascending
        except Exception as e:
            if verbose:
                print(f"  {sym:6} skipped ({type(e).__name__}: {str(e)[:50]})")
            continue
        surprises, sue_by_day = [], {}
        for ev in events:
            if ev.eps_actual is not None and ev.eps_estimate is not None:
                if len(surprises) >= 2:
                    sd = statistics.stdev(surprises)
                    if sd and sd > 1e-3:   # floor: near-zero stdev makes SUE explode
                        raw = (ev.eps_actual - ev.eps_estimate) / sd
                        sue_by_day[ev.day] = max(-10.0, min(10.0, raw))   # clip to a sane range
                surprises.append(ev.eps_actual - ev.eps_estimate)
        sym_rows = make_rows_for_symbol(
            bars, [ev.day for ev in events], horizon_days=horizon_days,
            entry_offset_days=entry_offset_days, sue_by_day=sue_by_day)
        if verbose:
            print(f"  {sym:6} {len(events):2} events -> {len(sym_rows):2} rows")
        rows.extend(sym_rows)
    return rows
