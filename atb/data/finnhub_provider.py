"""Finnhub-backed earnings provider (free tier) with real SUE.

Finnhub's strength is earnings: per-quarter actual/estimate/surprise history
(for SUE) plus an earnings calendar (for the announcement date). Its free tier
does NOT give stock candles, so this provider DELEGATES price + option data to a
`price_provider` (e.g. YFinanceProvider) and implements `recent_earnings`
itself — together they satisfy MarketDataProvider.

SUE here = (actual - estimate) / stdev(historical actual-estimate). That's the
standard "standardized unexpected earnings" simplification; swap the
denominator for a richer estimate-dispersion measure later.

Get a free key at finnhub.io and put FINNHUB_API_KEY in .env.

    from atb.data.yfinance_provider import YFinanceProvider
    from atb.data.finnhub_provider import FinnhubProvider
    provider = FinnhubProvider(price_provider=YFinanceProvider())
"""

from __future__ import annotations

import os
import statistics
from datetime import date, timedelta

from .provider import EarningsEvent, OptionQuote, PriceBar


class FinnhubProvider:
    BASE = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None = None, *, price_provider=None, fetch_json=None):
        self.api_key = api_key or os.environ.get("FINNHUB_API_KEY")
        self.price_provider = price_provider
        self._fetch = fetch_json or self._http_fetch

    # --- HTTP -----------------------------------------------------------
    def _http_fetch(self, path: str, params: dict, *, retries: int = 3):
        import json
        import time
        import urllib.error
        import urllib.parse
        import urllib.request
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY not set")
        # Auth via header (per Finnhub docs) keeps the key out of URLs/logs.
        url = f"{self.BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"X-Finnhub-Token": self.api_key})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:  # rate limited; back off
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise

    # --- earnings (the part Finnhub is good at) -------------------------
    def _surprise_stdev(self, symbol: str) -> float | None:
        rows = self._fetch("/stock/earnings", {"symbol": symbol}) or []
        diffs = [
            r["actual"] - r["estimate"]
            for r in rows
            if r.get("actual") is not None and r.get("estimate") is not None
        ]
        return statistics.stdev(diffs) if len(diffs) >= 2 else None

    def earnings_calendar(self, frm: date, to: date, symbol: str | None = None) -> list[dict]:
        params = {"from": frm.isoformat(), "to": to.isoformat()}
        if symbol:
            params["symbol"] = symbol
        cal = self._fetch("/calendar/earnings", params) or {}
        return cal.get("earningsCalendar", []) if isinstance(cal, dict) else []

    def recent_earnings(self, symbol: str, *, asof: date) -> EarningsEvent | None:
        items = self.earnings_calendar(asof - timedelta(days=150), asof, symbol)

        best = None
        best_day = None
        for it in items:
            try:
                d = date.fromisoformat(it["date"])
            except (KeyError, ValueError):
                continue
            if d <= asof and it.get("epsActual") is not None:
                if best_day is None or d > best_day:
                    best, best_day = it, d
        if best is None:
            return None

        act, est = best.get("epsActual"), best.get("epsEstimate")
        std = self._surprise_stdev(symbol)
        sue = None
        # Floor the denominator (near-zero stdev makes SUE explode) and clip.
        if std and std > 1e-3 and act is not None and est is not None:
            sue = max(-10.0, min(10.0, (act - est) / std))
        return EarningsEvent(symbol=symbol, day=best_day, eps_actual=act,
                             eps_estimate=est, sue=sue)

    def earnings_history(self, symbol: str, *, years: int = 3):
        """Historical earnings (announce date + actual/estimate). Tries the price
        provider (yfinance) first; if that's empty (Yahoo's earnings endpoint is
        flaky), falls back to the Finnhub calendar queried in chunks (the long
        single-range call often returns little on the free tier)."""
        if self.price_provider and hasattr(self.price_provider, "earnings_history"):
            ev = self.price_provider.earnings_history(symbol, years=years)
            if ev:
                return ev
        return self._finnhub_earnings_history(symbol, years=years)

    def _finnhub_earnings_history(self, symbol: str, *, years: int = 3, chunk_days: int = 120):
        end = date.today()
        start = end - timedelta(days=int(years * 365))
        seen: dict[date, EarningsEvent] = {}
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(days=chunk_days), end)
            for it in self.earnings_calendar(cur, nxt, symbol):
                if it.get("epsActual") is None or not it.get("date"):
                    continue
                d = date.fromisoformat(it["date"])
                seen[d] = EarningsEvent(symbol=symbol, day=d,
                                        eps_actual=it.get("epsActual"),
                                        eps_estimate=it.get("epsEstimate"))
            cur = nxt
        return sorted(seen.values(), key=lambda e: e.day)

    # --- prices / options: delegate to the price provider ---------------
    def daily_bars(self, symbol: str, *, lookback_days: int = 500) -> list[PriceBar]:
        if not self.price_provider:
            raise NotImplementedError("FinnhubProvider needs a price_provider for daily_bars")
        return self.price_provider.daily_bars(symbol, lookback_days=lookback_days)

    def latest_price(self, symbol: str) -> float | None:
        if self.price_provider:
            return self.price_provider.latest_price(symbol)
        q = self._fetch("/quote", {"symbol": symbol}) or {}
        return float(q["c"]) if q.get("c") else None

    def option_chain(self, symbol: str, *, expiry: date, option_type: str) -> list[OptionQuote]:
        if self.price_provider:
            return self.price_provider.option_chain(symbol, expiry=expiry, option_type=option_type)
        return []
