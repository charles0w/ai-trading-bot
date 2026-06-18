"""Grade directional calls against the realized underlying move.

return_pct is the move *in the predicted direction* (positive = the call was
right). This grades the THESIS (direction). Option P&L net of premium/theta is a
separate, harsher measure tracked from actual paper fills — both matter, and the
go-live gate uses the costed one."""

from __future__ import annotations

from datetime import date
from typing import Callable

from .predictions import Prediction, PredictionLog

_UP = {"up", "long_call", "call"}
_DOWN = {"down", "long_put", "put"}


def directional_return_pct(direction: str, entry_ref: float, exit_ref: float) -> float:
    move = (exit_ref - entry_ref) / entry_ref * 100.0
    if direction in _UP:
        return move
    if direction in _DOWN:
        return -move
    raise ValueError(f"ungradeable direction: {direction!r}")


def grade(direction: str, entry_ref: float, exit_ref: float) -> tuple[bool, float]:
    r = directional_return_pct(direction, entry_ref, exit_ref)
    return (r > 0, r)


def grade_due(predlog: PredictionLog, get_price: Callable[[str], float | None],
              *, asof: date) -> list[str]:
    """Grade every open prediction whose horizon has elapsed by `asof`.
    `get_price(symbol)` supplies the exit reference. Returns graded ids."""
    graded: list[str] = []
    for p in predlog.load():
        if p.status != "open":
            continue
        made = date.fromisoformat(p.date)
        if (asof - made).days < p.horizon_days:
            continue
        exit_ref = get_price(p.symbol)
        if exit_ref is None:
            continue
        correct, ret = grade(p.direction, p.entry_ref, exit_ref)
        predlog.update(p.id, status="graded", graded_date=asof.isoformat(),
                       exit_ref=exit_ref, correct=correct, return_pct=ret)
        graded.append(p.id)
    return graded
