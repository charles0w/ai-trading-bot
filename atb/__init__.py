"""ai-trading-bot application package (the 'brain' + app-specific glue).

trader_core is the reusable execution engine; atb holds app-specific pieces:
persistence (SQLiteStore), and later the data/feature layer, ML signal,
LLM analyst, and the pipeline that emits TradeIntents.
"""
