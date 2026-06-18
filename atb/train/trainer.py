"""Plain gradient-descent logistic regression (no third-party ML deps).

rows = list of (feature_dict, label) where label is 1 if the underlying moved
UP over the horizon, else 0. The model learns P(up | features); inference maps
that to a direction + probability. L2-regularized; standardize-free (features
are already on comparable scales)."""

from __future__ import annotations

from .. signal.logistic import FEATURES, LogisticSignal, sigmoid


def train_logistic(rows, *, features=FEATURES, lr: float = 0.3, epochs: int = 500,
                   l2: float = 1e-3) -> LogisticSignal:
    w = {f: 0.0 for f in features}
    b = 0.0
    n = len(rows)
    if n == 0:
        return LogisticSignal(weights=w, bias=b, features=list(features))
    for _ in range(epochs):
        gw = {f: 0.0 for f in features}
        gb = 0.0
        for x, y in rows:
            z = b + sum(w[f] * x.get(f, 0.0) for f in features)
            err = sigmoid(z) - y
            for f in features:
                gw[f] += err * x.get(f, 0.0)
            gb += err
        for f in features:
            w[f] -= lr * (gw[f] / n + l2 * w[f])
        b -= lr * (gb / n)
    return LogisticSignal(weights=w, bias=b, features=list(features))


def accuracy(model: LogisticSignal, rows) -> float | None:
    if not rows:
        return None
    correct = 0
    for x, y in rows:
        z = model.bias + sum(model.weights.get(f, 0.0) * x.get(f, 0.0) for f in model.features)
        correct += int((1 if sigmoid(z) >= 0.5 else 0) == y)
    return correct / len(rows)
