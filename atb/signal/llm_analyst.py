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
        "gap_day1": fv.gap_day1,
        "drift_since_day1": fv.drift_since_day1,
        "peer_surprise_pct": fv.peer_surprise_pct,
        "peer_symbol": fv.meta.get("peer_symbol"),
        "mom_12_1": fv.mom_12_1, "mom_6_1": fv.mom_6_1,
        "pct_from_52w_high": fv.pct_from_52w_high,
        "realized_vol_20d": fv.realized_vol_20d,
        "atm_iv": fv.atm_iv, "iv_rank": fv.iv_rank,
        "option_spread_pct": fv.spread_pct, "atm_open_interest": fv.open_interest,
        "vix": fv.vix, "vix_5d_change": fv.vix_5d_change,
    }
    return (
        "You are a disciplined equity-options swing analyst. Strategy: "
        "post-earnings-announcement drift, entered AFTER the IV crush, harvested "
        "with long calls/puts over ~3-6 weeks. Be skeptical: most setups are NOT "
        "tradeable. Given the features below, decide whether the drift is likely to "
        "continue and in which direction.\n\n"
        "Feature notes: gap_day1 is the initial post-print reaction and "
        "drift_since_day1 the move since — a big gap with fading drift is the "
        "pop-and-fade anti-pattern, not continuation. peer_surprise_pct is the "
        "strongest EPS surprise from a close peer in the last 2 days (peer "
        "catalysts move neighbors both directions). atm_iv/iv_rank/spread are "
        "the ~35-DTE ATM call snapshot — rich or wide options can make a "
        "correct thesis untradeable. vix/vix_5d_change give the macro regime; "
        "a spiking VIX argues for standing aside. Null means unavailable.\n\n"
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
