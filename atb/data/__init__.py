"""Market-data layer: a provider interface + implementations.

The feature builder depends only on `MarketDataProvider`, so we can start free
(yfinance) and swap in Polygon/Tradier for proper options history later without
touching the features or the brain.
"""
