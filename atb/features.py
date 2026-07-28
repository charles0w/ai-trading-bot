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
from datetime import date, timedelta
from typing import Any

from trader_core.execution.intent import LONG_CALL, LONG_PUT, TradeIntent

from .chain_snapshots import ChainSnapshots
from .data.provider import MarketDataProvider, PriceBar
from .peers import PEERS


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
    # drift decomposition (2026-07-27): the single drift number can't tell
    # "gapped +8% then bleeding" (pop-and-fade, anti-signal B6) from "steady
    # accumulation" — split it so the model/analyst can.
    gap_day1: float | None = None            # first post-print session move
    drift_since_day1: float | None = None    # spot vs first post-print close
    # peer event (signals.md A4/A6): strongest peer EPS surprise, last 2 days
    peer_surprise_pct: float | None = None
    # macro regime
    vix: float | None = None
    vix_5d_change: float | None = None
    # earnings quality (paid; optional)
    sue: float | None = None
    # options (free snapshot via yfinance chain; iv_rank needs accumulated history)
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


# --------------------- enrichment (free-data signals) ----------------------
# Per-process caches keyed by asof: one VIX fetch and one earnings-calendar
# fetch per run, shared across every symbol in the loop.

_vix_cache: dict[date, tuple[float | None, float | None]] = {}
_peer_cal_cache: dict[date, dict[str, float]] = {}
TARGET_DTE = 35


def _vix_regime(provider, asof: date) -> tuple[float | None, float | None]:
    if asof not in _vix_cache:
        vix = chg = None
        try:
            closes = [b.close for b in provider.daily_bars("^VIX", lookback_days=40)]
            if closes:
                vix = closes[-1]
                if len(closes) >= 6 and closes[-6] > 0:
                    chg = closes[-1] / closes[-6] - 1
        except Exception:
            pass
        _vix_cache[asof] = (vix, chg)
    return _vix_cache[asof]


def _peer_surprises(provider, asof: date) -> dict[str, float]:
    """symbol -> EPS surprise pct for universe names that reported in the last
    2 days. One calendar call per run (no per-peer requests)."""
    if asof not in _peer_cal_cache:
        out: dict[str, float] = {}
        try:
            for it in provider.earnings_calendar(asof - timedelta(days=2), asof):
                sym, act, est = it.get("symbol"), it.get("epsActual"), it.get("epsEstimate")
                if sym and act is not None and est:
                    out[sym] = (act - est) / abs(est) * 100.0
        except Exception:
            pass
        _peer_cal_cache[asof] = out
    return _peer_cal_cache[asof]


def _enrich_chain(fv: FeatureVector, provider, asof: date) -> None:
    """Fill atm_iv / spread_pct / open_interest from the live chain and record
    the daily snapshot (data/chain_snapshots.jsonl — git-tracked; yfinance has
    no IV history, so rank baselines only exist if we've been recording).
    iv_rank stays None until >=10 recorded observations for the symbol."""
    if not hasattr(provider, "option_expiries") or not fv.spot:
        return
    try:
        expiries = [e for e in provider.option_expiries(fv.symbol)
                    if (e - asof).days >= 7]
        if not expiries:
            return
        expiry = min(expiries, key=lambda e: abs((e - asof).days - TARGET_DTE))
        chain = provider.option_chain(fv.symbol, expiry=expiry, option_type="call")
        if not chain:
            return
        atm = min(chain, key=lambda q: abs(q.strike - fv.spot))
        # Off-hours yfinance serves junk chains (iv ~0.004, zeroed bid/ask/OI).
        # Only accept — and only SNAPSHOT — plausible market-hours quotes;
        # recording junk would poison the iv_percentile baseline forever.
        plausible_iv = atm.iv is not None and 0.03 <= atm.iv <= 5.0
        has_market = (atm.bid or 0) > 0 or (atm.ask or 0) > 0
        if not (plausible_iv and has_market):
            return
        fv.atm_iv = atm.iv
        fv.spread_pct = atm.spread_pct
        fv.open_interest = atm.open_interest
        snaps = ChainSnapshots()
        if atm.iv is not None:
            fv.iv_rank = snaps.iv_percentile(fv.symbol, atm.iv)
        snaps.record({
            "date": asof.isoformat(), "symbol": fv.symbol,
            "expiry": expiry.isoformat(), "strike": atm.strike,
            "atm_iv": atm.iv, "spread_pct": atm.spread_pct,
            "oi": atm.open_interest, "volume": atm.volume, "spot": fv.spot,
        })
    except Exception:
        pass  # enrichment is best-effort; core features must never fail on it


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
        # post-earnings drift: spot vs the close on the first trading day on/after
        # the print. Only meaningful with an observation BEYOND that base close —
        # when a stale/NaN-truncated feed makes the base bar the newest bar and
        # spot is that same close, emit None, not a fabricated 0.0 (which reads
        # as "no drift, confirmed" to the signal and the LLM analyst).
        base_idx = next((i for i, b in enumerate(bars) if b.day >= earn.day), None)
        if base_idx is not None:
            base_bar = bars[base_idx]
            if base_bar.close and fv.spot:
                has_later_bar = bars[-1].day > base_bar.day
                if has_later_bar or fv.spot != base_bar.close:
                    fv.post_earnings_return = fv.spot / base_bar.close - 1
            # decomposition: base close (pre-reaction for AMC prints) -> first
            # post-print session close = gap_day1; that close -> spot = drift
            day1_bar = bars[base_idx + 1] if base_idx + 1 < len(bars) else None
            if day1_bar and base_bar.close and day1_bar.close:
                fv.gap_day1 = day1_bar.close / base_bar.close - 1
                if fv.spot and (bars[-1].day > day1_bar.day or fv.spot != day1_bar.close):
                    fv.drift_since_day1 = fv.spot / day1_bar.close - 1

    # peer-earnings surprise (A4/A6): strongest surprise among this symbol's
    # peers that reported within the last 2 days. Deliberately OUTSIDE the
    # own-earnings branch — the signal's whole point is the non-reporter
    # moving on the neighbor's print (AMD +12% on Intel's commentary).
    surprises = _peer_surprises(provider, asof) if hasattr(provider, "earnings_calendar") else {}
    peer_hits = {p: s for p, s in surprises.items()
                 if p in PEERS.get(symbol, frozenset())}
    if peer_hits:
        peer, s = max(peer_hits.items(), key=lambda kv: abs(kv[1]))
        fv.peer_surprise_pct = s
        fv.meta["peer_symbol"] = peer

    # macro regime + options chain (today-only: snapshots are "today's chain")
    fv.vix, fv.vix_5d_change = _vix_regime(provider, asof)
    if asof == date.today():
        _enrich_chain(fv, provider, asof)
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
