"""Training harness for the PEAD logistic signal.

dataset.py assembles labeled rows from historical earnings + prices (the
'train itself' part); trainer.py fits a logistic model with plain gradient
descent (no sklearn). The output is data/model.json, loaded by LogisticSignal.
"""

from __future__ import annotations

from .dataset import build_dataset, make_rows_for_symbol
from .trainer import accuracy, train_logistic

__all__ = ["build_dataset", "make_rows_for_symbol", "train_logistic", "accuracy"]
