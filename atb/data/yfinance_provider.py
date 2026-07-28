"""Free market-data provider via yfinance (prices + earnings dates + basic
option chains). Runs on your Mac (needs network). Good enough to prototype the
PEAD features; swap to Polygon/Tradier for real options history + IV later.

Gaps vs. a paid feed: no clean SUE (needs an estimate-surprise history), no IV
rank history, snapshot-only chains. Those FeatureVector slots stay None until a
richer provider fills them.
"""

from __future__ import annotations

from datetime import date, timedelta

from .provider import EarningsEvent, OptionQuote, PriceBar


def _f(x):
    try:
        if x is None or x != x:  # None or NaN
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


class YFinanceProvider:
    def __init__(self) -> None:
        import yfinance  # noqa: F401  (fail early if missing)

    def _ticker(self, symbol: str):
        import yfinance as yf
        return yf.Ticker(symbol)

    def daily_bars(self, symbol: str, *, lookback_days: int = 500) -> list[PriceBar]:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        hist = self._ticker(symbol).history(start=start, auto_adjust=False)
        bars: list[PriceBar] = []
        for idx, row in hist.iterrows():
            day = idx.date() if hasattr(idx, "date") else idx
            close = _f(row.get("Close"))
            if close is None or close <= 0:
                # Skip partial/NaN rows (e.g. the in-progress current day before
                # close). Fabricating a 0.0 price poisons log-returns downstream
                # (math.log(0) -> ValueError) and zeroes out spot.
                continue
            bars.append(PriceBar(
                day=day, open=_f(row.get("Open")) or close, high=_f(row.get("High")) or close,
                low=_f(row.get("Low")) or close, close=close,
                volume=_f(row.get("Volume")) or 0.0,
            ))
        return bars

    def latest_price(self, symbol: str) -> float | None:
        bars = self.daily_bars(symbol, lookback_days=7)
        return bars[-1].close if bars else None

    def recent_earnings(self, symbol: str, *, asof: date) -> EarningsEvent | None:
        t = self._ticker(symbol)
        df = None
        try:
            df = t.get_earnings_dates(limit=16)
        except Exception:
            try:
                df = t.earnings_dates
            except Exception:
                df = None
        if df is None or len(df) == 0:
            return None
        best = None
        for idx, row in df.iterrows():
            day = idx.date() if hasattr(idx, "date") else idx
            if day <= asof and (best is None or day > best.day):
                best = EarningsEvent(
                    symbol=symbol, day=day,
                    eps_actual=_f(row.get("Reported EPS")),
                    eps_estimate=_f(row.get("EPS Estimate")),
                )
        return best

    def earnings_history(self, symbol: str, *, years: int = 3, limit: int = 24) -> list[EarningsEvent]:
        """Past earnings with announce date + actual/estimate (for the training
        dataset). Free, one call/symbol, and has the real announcement date."""
        t = self._ticker(symbol)
        df = None
        try:
            df = t.get_earnings_dates(limit=limit)
        except Exception:
            try:
                df = t.earnings_dates
            except Exception:
                df = None
        if df is None or len(df) == 0:
            return []
        today = date.today()
        cutoff = today - timedelta(days=int(years * 365))
        out: list[EarningsEvent] = []
        for idx, row in df.iterrows():
            day = idx.date() if hasattr(idx, "date") else idx
            if day > today or day < cutoff:
                continue
            act = _f(row.get("Reported EPS"))
            if act is None:           # not yet reported
                continue
            out.append(EarningsEvent(symbol=symbol, day=day, eps_actual=act,
                                     eps_estimate=_f(row.get("EPS Estimate"))))
        out.sort(key=lambda e: e.day)
        return out

    def option_expiries(self, symbol: str) -> list[date]:
        """Listed option expiries (optional capability — see provider.py)."""
        try:
            return [date.fromisoformat(e) for e in (self._ticker(symbol).options or ())]
        except Exception:
            return []

    def option_chain(self, symbol: str, *, expiry: date, option_type: str) -> list[OptionQuote]:
        try:
            chain = self._ticker(symbol).option_chain(expiry.isoformat())
            df = chain.calls if option_type == "call" else chain.puts
        except Exception:
            return []
        out: list[OptionQuote] = []
        for _, r in df.iterrows():
            oi = r.get("openInterest")
            out.append(OptionQuote(
                occ_symbol=str(r.get("contractSymbol", "")),
                strike=_f(r.get("strike")) or 0.0, expiry=expiry, option_type=option_type,
                bid=_f(r.get("bid")), ask=_f(r.get("ask")),
                iv=_f(r.get("impliedVolatility")),
                open_interest=int(oi) if oi is not None and oi == oi else None,
                volume=_f(r.get("volume")),
            ))
        return out
