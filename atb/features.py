"""Feature builder for the PEAD-post-crush strategy (strategy-research-2026-06-16).

Computes what's possible from free price + earnings data (momentum, 52-week
high, realized vol, days-since-earnings, post-earnings drift) and leaves slots
for paid/options data (SUE, IV rank, spread, OI) to be filled when available.

`pead_baseline_intent` is a deliberately NAIVE placeholder that turns features
into a TradeIntent so the loop is end-to-end runnable. The ML signal + LLM
analyst intersection will replace it — it is not the strategy, it's a stub.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from trader_core.execution.intent import LONG_CALL, LONG_PUT, TradeIntent

from .data.provider import MarketDataProvider, PriceBar


@dataclass
class FeatureVector:
    symbol: str
    asof: date
    spot: float | None = None
    # trend / momentum (free, from prices)
    mom_12_1: float | None = None
    mom_6_1: float | None = None
    pct_from_52w_high: float | None = None
    realized_vol_20d: float | None = None
    # event (free-ish)
    last_earnings_date: date | None = None
    days_since_earnings: int | None = None
    post_earnings_return: float | None = None
    # earnings quality (paid; optional)
    sue: float | None = None
    # options (paid/limited; optional)
    atm_iv: float | None = None
    iv_rank: float | None = None
    spread_pct: float | None = None
    open_interest: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# ----------------------------- pure math ----------------------------------

def momentum(closes: list[float], *, lookback: int, skip: int) -> float | None:
    """Return from `lookback` trading days ago to `skip` days ago (skip the most
    recent month to avoid short-term reversal). e.g. 12-1 = lookback 252, skip 21."""
    if len(closes) < lookback + skip + 1:
        return None
    recent = closes[-(skip + 1)]
    past = closes[-(lookback + skip + 1)]
    return (recent / past - 1) if (past > 0 and recent > 0) else None


def realized_vol(closes: list[float], *, window: int = 20, ann: int = 252) -> float | None:
    if len(closes) < window + 1:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - window, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(ann)


def pct_from_high(spot: float, highs: list[float]) -> float | None:
    valid = [h for h in highs if h and h > 0]
    hi = max(valid) if valid else None
    return (spot / hi - 1) if (hi and spot) else None


# ----------------------------- builder ------------------------------------

def compute_features(provider: MarketDataProvider, symbol: str, *,
                     asof: date | None = None) -> FeatureVector:
    asof = asof or date.today()
    bars: list[PriceBar] = provider.daily_bars(symbol, lookback_days=500)
    fv = FeatureVector(symbol=symbol, asof=asof)
    if not bars:
        return fv

    closes = [b.close for b in bars]
    highs_52w = [b.high for b in bars[-252:]]
    fv.spot = provider.latest_price(symbol) or closes[-1]
    fv.mom_12_1 = momentum(closes, lookback=252, skip=21)
    fv.mom_6_1 = momentum(closes, lookback=126, skip=21)
    fv.pct_from_52w_high = pct_from_high(fv.spot, highs_52w)
    fv.realized_vol_20d = realized_vol(closes)

    earn = provider.recent_earnings(symbol, asof=asof)
    if earn is not None:
        fv.last_earnings_date = earn.day
        fv.days_since_earnings = (asof - earn.day).days
        fv.sue = earn.sue
        # post-earnings drift: spot vs the close on the first trading day on/after the print
        base = next((b.close for b in bars if b.day >= earn.day), None)
        if base and fv.spot:
            fv.post_earnings_return = fv.spot / base - 1
    return fv


# ------------------------- naive baseline (stub) --------------------------

def pead_baseline_intent(fv: FeatureVector, *, target_dte: int = 35,
                         entry_window=(1, 5)) -> TradeIntent | None:
    """NAIVE placeholder: in the post-earnings drift window (T+1..T+5), bet the
    drift continues — long call if the post-print move is up, long put if down.
    Replace with the ML+LLM intersection. Liquidity/IV-crush gates live in the
    risk layer + entry timing (this stub does not enforce T+1/T+2-only)."""
    lo, hi = entry_window
    if fv.days_since_earnings is None or not (lo <= fv.days_since_earnings <= hi):
        return None
    if fv.post_earnings_return is None or fv.spot is None or fv.post_earnings_return == 0:
        return None
    direction = LONG_CALL if fv.post_earnings_return > 0 else LONG_PUT
    return TradeIntent(
        underlying=fv.symbol,
        direction=direction,
        target_dte=target_dte,
        strike_rule="ATM",
        signal_id=f"{fv.asof.isoformat()}-{fv.symbol}-pead",
        price_ref=None,
        conviction=min(abs(fv.post_earnings_return) * 5, 1.0),  # crude
        meta={"strategy": "pead_baseline", "post_earnings_return": fv.post_earnings_return,
              "days_since_earnings": fv.days_since_earnings, "sue": fv.sue},
    )
