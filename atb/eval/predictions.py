"""Append-only prediction log (JSONL) — every directional call the brain makes,
later graded against the realized move. This is the dataset the go-live gate is
computed from."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
                out.append(Prediction(**json.loads(line)))
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
