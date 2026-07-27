"""Append-only prediction log (JSONL) — every directional call the brain makes,
later graded against the realized move. This is the dataset the go-live gate is
computed from."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class Prediction:
    id: str
    date: str                       # ISO date the call was made
    symbol: str
    direction: str                  # "up"|"down" (long_call/long_put also accepted)
    horizon_days: int
    entry_ref: float
    conviction: float | None = None
    rationale: str = ""
    status: str = "open"            # "open" | "graded"
    graded_date: str | None = None
    exit_ref: float | None = None
    correct: bool | None = None
    return_pct: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


_RENAMES = {"ticker": "symbol"}          # 2026-07 legacy schema (morning-watch era)
_FIELDS = {f.name for f in fields(Prediction)}


def _normalize(raw: dict) -> dict:
    """Adapt a raw JSONL row to the current Prediction schema.

    Legacy rows (seeded from the vault mirror) use `ticker` instead of
    `symbol`, carry extra keys (`signals`, `entry_ref_source`, ...), and hold
    categorical convictions ("low"/"medium"). Renames map across, unknown keys
    are preserved under `meta`, and string convictions become None (honest —
    fabricating a numeric conviction would pollute brier/calibration) with the
    label kept as meta["conviction_label"]."""
    d: dict[str, Any] = {}
    meta = dict(raw.get("meta") or {})
    for k, v in raw.items():
        if k == "meta":
            continue
        k = _RENAMES.get(k, k)
        if k in _FIELDS:
            d[k] = v
        else:
            meta.setdefault(k, v)
    if isinstance(d.get("conviction"), str):
        meta.setdefault("conviction_label", d["conviction"])
        d["conviction"] = None
    d["meta"] = meta
    return d


class PredictionLog:
    def __init__(self, path: str | Path = "data/predictions.jsonl"):
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, pred: Prediction) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(pred)) + "\n")

    def load(self) -> list[Prediction]:
        if not self.path.exists():
            return []
        out: list[Prediction] = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(Prediction(**_normalize(json.loads(line))))
        return out

    def update(self, pred_id: str, **fields: Any) -> bool:
        preds = self.load()
        found = False
        for p in preds:
            if p.id == pred_id:
                for k, v in fields.items():
                    setattr(p, k, v)
                found = True
        if found:
            with self.path.open("w") as f:
                for p in preds:
                    f.write(json.dumps(asdict(p)) + "\n")
        return found
