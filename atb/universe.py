"""Shared liquid, tight-spread optionable universe — the only names where the
academic PEAD edge survives option costs (strategy-research-2026-06-16). Used by
the scanner and the dashboard reporter so both agree on what's tradeable."""

from __future__ import annotations

LIQUID: set[str] = {
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "AMD",
    "NFLX", "CRM", "ORCL", "ADBE", "INTC", "QCOM", "MU", "TXN", "CSCO", "IBM",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP", "C",
    "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO",
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "MCD", "SBUX", "DIS",
    "XOM", "CVX", "COP", "BA", "CAT", "GE", "HON", "UPS",
    "PG", "KO", "PEP", "T", "VZ", "CMCSA", "PYPL", "UBER", "SHOP", "PLTR",
    "SMCI", "MRVL", "PANW", "SNOW", "COIN", "ABNB", "F", "GM",
}
