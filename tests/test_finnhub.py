from __future__ import annotations

import statistics
from datetime import date

from atb.data.finnhub_provider import FinnhubProvider
from atb.data.provider import MarketDataProvider, PriceBar

EARNINGS_ROWS = [
    {"actual": 1.2, "estimate": 1.0},
    {"actual": 0.9, "estimate": 1.0},
    {"actual": 1.1, "estimate": 1.0},
    {"actual": 1.0, "estimate": 0.9},
]
CALENDAR = [
    {"date": "2026-03-10", "epsActual": 1.1, "epsEstimate": 1.0},
    {"date": "2026-06-10", "epsActual": 1.3, "epsEstimate": 1.0},   # latest <= asof
    {"date": "2026-09-10", "epsActual": None, "epsEstimate": 1.1},  # future / no actual
]


def _fetch(path, params):
    if path == "/stock/earnings":
        return EARNINGS_ROWS
    if path == "/calendar/earnings":
        return {"earningsCalendar": CALENDAR}
    if path == "/quote":
        return {"c": 123.4}
    return None


class FakePrice:
    def daily_bars(self, symbol, *, lookback_days=500):
        return [PriceBar(date(2026, 6, 16), 1, 1, 1, 100.0, 1_000)]

    def latest_price(self, symbol):
        return 100.0

    def option_chain(self, symbol, *, expiry, option_type):
        return []


def _provider(price=None):
    return FinnhubProvider(api_key="test", price_provider=price, fetch_json=_fetch)


def test_satisfies_provider_protocol():
    assert isinstance(_provider(FakePrice()), MarketDataProvider)


def test_recent_earnings_picks_latest_and_computes_sue():
    ev = _provider().recent_earnings("NVDA", asof=date(2026, 6, 16))
    assert ev is not None
    assert ev.day == date(2026, 6, 10)          # most recent <= asof with an actual
    assert ev.eps_actual == 1.3 and ev.eps_estimate == 1.0
    expected_sue = 0.3 / statistics.stdev([0.2, -0.1, 0.1, 0.1])
    assert abs(ev.sue - expected_sue) < 1e-9


def test_recent_earnings_none_when_no_calendar():
    p = FinnhubProvider(api_key="test", fetch_json=lambda path, params:
                        {"earningsCalendar": []} if path == "/calendar/earnings" else [])
    assert p.recent_earnings("NVDA", asof=date(2026, 6, 16)) is None


def test_delegates_prices_to_price_provider():
    p = _provider(FakePrice())
    assert p.latest_price("NVDA") == 100.0
    assert len(p.daily_bars("NVDA")) == 1
