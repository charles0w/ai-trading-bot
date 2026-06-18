"""LLM analyst — Claude reads the feature vector and returns a structured thesis.

Depends on an injectable `complete(prompt) -> str` callable so it's testable
offline and provider-agnostic. On the Mac, pass a function that calls the
Anthropic SDK; in tests, pass a fake. The analyst NEVER decides sizing or
execution — it only emits a direction + conviction + rationale, which the
intersection rule combines with the ML signal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..features import FeatureVector

VERSION = "llm-analyst-v0"
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class Thesis:
    direction: str                 # "up" | "down" | "flat"
    conviction: float              # 0..1
    rationale: str
    raw: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def build_prompt(fv: FeatureVector) -> str:
    feats = {
        "symbol": fv.symbol, "asof": str(fv.asof), "spot": fv.spot,
        "sue": fv.sue, "days_since_earnings": fv.days_since_earnings,
        "post_earnings_return": fv.post_earnings_return,
        "mom_12_1": fv.mom_12_1, "mom_6_1": fv.mom_6_1,
        "pct_from_52w_high": fv.pct_from_52w_high,
        "realized_vol_20d": fv.realized_vol_20d, "iv_rank": fv.iv_rank,
    }
    return (
        "You are a disciplined equity-options swing analyst. Strategy: "
        "post-earnings-announcement drift, entered AFTER the IV crush, harvested "
        "with long calls/puts over ~3-6 weeks. Be skeptical: most setups are NOT "
        "tradeable. Given the features below, decide whether the drift is likely to "
        "continue and in which direction.\n\n"
        f"FEATURES:\n{json.dumps(feats, indent=2)}\n\n"
        'Respond with ONLY a JSON object: {"direction": "up"|"down"|"flat", '
        '"conviction": 0.0-1.0, "rationale": "one sentence"}. '
        "Use 'flat' (conviction 0) unless there is a clear, confirmed drift signal."
    )


def parse_thesis(raw: str) -> Thesis:
    """Extract the first JSON object from the model output; fall back to flat."""
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(match.group(0)) if match else {}
    except (json.JSONDecodeError, AttributeError):
        obj = {}
    direction = str(obj.get("direction", "flat")).lower()
    if direction not in ("up", "down", "flat"):
        direction = "flat"
    try:
        conviction = float(obj.get("conviction", 0.0))
    except (TypeError, ValueError):
        conviction = 0.0
    conviction = max(0.0, min(1.0, conviction))
    if direction == "flat":
        conviction = 0.0
    return Thesis(direction=direction, conviction=conviction,
                  rationale=str(obj.get("rationale", "")), raw=raw)


class LLMAnalyst:
    def __init__(self, complete: Callable[[str], str], *, model: str = DEFAULT_MODEL):
        self._complete = complete
        self.model = model

    def analyze(self, fv: FeatureVector) -> Thesis:
        raw = self._complete(build_prompt(fv))
        th = parse_thesis(raw)
        th.meta["model"] = self.model
        return th
