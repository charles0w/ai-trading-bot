"""TradeIntent — the brain/hands seam.

Either front end produces a TradeIntent: lambos's parser ("an expert said
buy X") or ai-trading-bot's ML+LLM analyzer ("the model and the analyst
agree on a long call in NVDA"). The executor consumes it. This single type
is what replaces lambos's copy-trade-specific `ParsedAlert`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LONG_CALL = "long_call"
LONG_PUT = "long_put"
VALID_DIRECTIONS = (LONG_CALL, LONG_PUT)


@dataclass
class TradeIntent:
    underlying: str                       # "NVDA"
    direction: str                        # LONG_CALL | LONG_PUT
    target_dte: int                       # e.g. 35 (swing: 30-45)
    strike_rule: str                      # "ATM" | "DELTA:0.55" | "OTM:2pct" | "ABS:123.5"
    signal_id: str                        # FK to predictions.jsonl / signals table
    price_ref: float | None = None        # fallback for limit pricing / sizing
    conviction: float | None = None       # from the ML AND LLM intersection
    meta: dict[str, Any] = field(default_factory=dict)  # strategy tag, SUE, IV rank, model version...

    def __post_init__(self) -> None:
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of {VALID_DIRECTIONS}, got {self.direction!r}"
            )
        if not self.underlying:
            raise ValueError("underlying is required")
        if self.target_dte <= 0:
            raise ValueError(f"target_dte must be positive, got {self.target_dte}")
        if not self.signal_id:
            raise ValueError("signal_id is required (for grading/traceability)")

    @property
    def option_type(self) -> str:
        """'call' or 'put' — matches broker.base.OptionContract.option_type."""
        return "call" if self.direction == LONG_CALL else "put"
