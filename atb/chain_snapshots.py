"""Daily option-chain snapshot store (JSONL, one row per symbol per day).

yfinance option chains are snapshot-only — there is NO free historical IV/flow
feed, so the only way to have IV-rank or volume/OI baselines is to have been
recording them. The daily run appends a compact ATM summary per candidate; the
file is git-tracked (the Actions workflow commits it) so history accumulates
serverlessly and is shared across machines.

Row: {date, symbol, expiry, strike, atm_iv, spread_pct, oi, volume, spot}

Derived once enough history exists:
  iv_percentile(symbol, iv) -> 0-100 rank of `iv` vs this symbol's prior
  snapshots (None until `min_obs` observations — honest missing-data until then).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PATH = "data/chain_snapshots.jsonl"


class ChainSnapshots:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("ATB_CHAIN_SNAPSHOT_PATH", DEFAULT_PATH))
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def has(self, day: str, symbol: str) -> bool:
        return any(r.get("date") == day and r.get("symbol") == symbol
                   for r in self._rows())

    def record(self, row: dict[str, Any]) -> bool:
        """Append one snapshot; idempotent per (date, symbol). Returns True if written."""
        if self.has(row["date"], row["symbol"]):
            return False
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return True

    def iv_percentile(self, symbol: str, iv: float, *, min_obs: int = 10) -> float | None:
        """Percentile (0-100) of `iv` against this symbol's recorded ATM IVs.
        None until `min_obs` prior observations exist — a 3-day-old 'rank' is
        noise dressed as signal."""
        ivs = [r["atm_iv"] for r in self._rows()
               if r.get("symbol") == symbol and isinstance(r.get("atm_iv"), (int, float))]
        if len(ivs) < min_obs:
            return None
        return 100.0 * sum(1 for x in ivs if x <= iv) / len(ivs)
