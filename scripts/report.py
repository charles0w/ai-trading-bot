"""Push the bot's status + trading snapshot to the ceos-enterprise dashboard.

Sends two payloads (auth: x-report-secret):
  POST /api/report   -> the Finance fleet card (state, summary, 3 metrics, evals)
  POST /api/finance  -> the /finance trading desk (scorecard, predictions, positions)

    python scripts/report.py          # push live
    python scripts/report.py --dry    # print payloads, send nothing

Env (.env): CEOS_REPORT_SECRET (= dashboard REPORT_SECRET); optional
CEOS_DASHBOARD_URL (default https://ceos-enterprise.vercel.app).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from atb.eval.predictions import PredictionLog
from atb.eval.reliability import summary

BASE = os.environ.get("CEOS_DASHBOARD_URL", "https://ceos-enterprise.vercel.app").rstrip("/")
SECRET = os.environ.get("CEOS_REPORT_SECRET") or os.environ.get("REPORT_SECRET") or ""
DB, PREDS, MODEL = "data/atb.db", "data/predictions.jsonl", "data/model.json"
DRY = "--dry" in sys.argv


def _post(path: str, payload: dict) -> None:
    if DRY:
        print(f"--- DRY {path} ---")
        print(json.dumps(payload, indent=2)[:1500])
        return
    if not SECRET:
        print(f"no CEOS_REPORT_SECRET — skipping {path}")
        return
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "x-report-secret": SECRET})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(path, "->", r.status)
    except urllib.error.HTTPError as e:
        print(path, "HTTP", e.code, e.read()[:160])
    except Exception as e:
        print(path, "ERR", type(e).__name__, str(e)[:120])


def _positions() -> list[dict]:
    if not os.path.exists(DB):
        return []
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT occ_symbol, quantity, entry_price, mark, entry_at_utc "
            "FROM positions WHERE closed = 0").fetchall()
    except Exception:
        rows = []
    con.close()
    return [dict(r) for r in rows]


def main() -> None:
    preds = PredictionLog(PREDS).load()
    sc = summary(preds)
    positions = _positions()

    model = {}
    if os.path.exists(MODEL):
        m = json.load(open(MODEL))
        model = {"version": m.get("version"), "weights": m.get("weights"),
                 "held_out_acc": m.get("held_out_acc"), "n_rows": m.get("n_rows")}

    preds_payload = [{
        "id": p.id, "date": p.date, "symbol": p.symbol, "direction": p.direction,
        "horizon_days": p.horizon_days, "entry_ref": p.entry_ref, "conviction": p.conviction,
        "status": p.status, "correct": p.correct, "return_pct": p.return_pct,
    } for p in preds][-200:]

    note = f"{sc['n_total']} preds · {sc['n_graded']} graded · {len(positions)} open"

    # card metrics (max 3)
    metrics = [{"label": "Predictions", "value": sc["n_total"]}]
    if sc["n_graded"] > 0 and sc["hit_rate"] is not None:
        metrics.append({"label": "Hit rate", "value": round(sc["hit_rate"] * 100, 1), "unit": "%"})
    if model.get("held_out_acc") is not None:
        metrics.append({"label": "Model OOS", "value": round(model["held_out_acc"] * 100, 1), "unit": "%"})
    else:
        metrics.append({"label": "Open pos", "value": len(positions)})

    status = {
        "state": "ok",
        "lastRun": datetime.now(timezone.utc).isoformat(),
        "summary": f"PEAD options swing (paper) — {note}",
        "ok": True,
        "metrics": metrics[:3],
    }
    if sc["n_graded"] > 0 and sc["hit_rate"] is not None:
        status["evalReliability"] = round(sc["hit_rate"], 3)
    if model.get("held_out_acc") is not None:
        status["evalScore"] = round(model["held_out_acc"], 3)

    _post("/api/report", {"agentId": "finance", "status": status})
    _post("/api/finance", {
        "model": model, "scorecard": sc, "predictions": preds_payload,
        "positions": positions, "candidates": [], "note": note,
    })


if __name__ == "__main__":
    main()
