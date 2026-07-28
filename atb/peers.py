"""Static peer map for the liquid universe — powers the peer-earnings-surprise
feature (signals.md A4/A6, bidirectional). AMD ran +12% on Intel's commentary;
TXN/QCOM fell 7-8% on the ON warn. The map is deliberately coarse (thematic
groups, symmetric): the feature only asks "did a close peer print a big
surprise in the last two days", not for a supply-chain graph.

Keep entries within atb.universe.LIQUID so the calendar lookup stays one call.
"""

from __future__ import annotations

_GROUPS: list[set[str]] = [
    # semis + semi-adjacent hardware
    {"NVDA", "AMD", "AVGO", "INTC", "QCOM", "MU", "TXN", "MRVL", "SMCI"},
    # mega-cap internet / consumer tech
    {"AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NFLX"},
    # enterprise software / cloud / security
    {"MSFT", "CRM", "ORCL", "ADBE", "SNOW", "PANW", "IBM", "PLTR"},
    # banks / broker-dealers
    {"JPM", "BAC", "WFC", "GS", "MS", "C"},
    # payments / fintech
    {"V", "MA", "AXP", "PYPL", "COIN"},
    # healthcare / pharma
    {"UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO"},
    # big-box / home retail
    {"WMT", "COST", "HD", "LOW", "TGT"},
    # consumer brands / restaurants
    {"NKE", "MCD", "SBUX", "DIS", "PG", "KO", "PEP"},
    # energy
    {"XOM", "CVX", "COP"},
    # industrials / aero
    {"BA", "CAT", "GE", "HON", "UPS"},
    # telecom / cable
    {"T", "VZ", "CMCSA"},
    # autos / mobility
    {"TSLA", "F", "GM", "UBER"},
    # platform e-commerce / gig
    {"SHOP", "ABNB", "UBER", "PYPL"},
]

PEERS: dict[str, frozenset[str]] = {}
for _g in _GROUPS:
    for _s in _g:
        PEERS[_s] = frozenset(PEERS.get(_s, frozenset()) | (_g - {_s}))
