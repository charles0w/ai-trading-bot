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

import collections
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

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
    """Raises on any delivery failure. The caller turns that into a non-zero
    exit so a broken dashboard feed fails the workflow loudly — this used to
    swallow errors (and a missing secret) and exit 0, which is how the feed went
    stale unnoticed."""
    if DRY:
        print(f"--- DRY {path} ---")
        print(json.dumps(payload, indent=2)[:1500])
        return
    if not SECRET:
        raise RuntimeError(
            "CEOS_REPORT_SECRET is not set — the dashboard feed cannot be "
            "delivered. Set it in .env locally, or as a repo secret for Actions.")
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "x-report-secret": SECRET})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(path, "->", r.status)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} HTTP {e.code}: {e.read()[:160]!r}") from e
    except Exception as e:
        raise RuntimeError(f"{path} {type(e).__name__}: {str(e)[:120]}") from e


def run_record_from_predictions(rows: list[dict], *, graded_today: int,
                                today: str) -> dict:
    """Activity record for this fire, derived from the prediction log.

    This used to parse logs/daily.log, but the Actions workflow calls the python
    scripts directly rather than run_daily.sh, so that file never exists on the
    runner and the detail was always empty. The prediction log is the artifact
    both paths actually write.

    A trading day that logged no new predictions is reported NOT ok: that is the
    silent-miss signature (the 2026-08-06 dropped run), and it should surface on
    the dashboard rather than read as a healthy zero-trade day.
    """
    todays = [r for r in rows if r.get("date") == today]
    by_component = collections.Counter(
        (r.get("meta") or {}).get("component") for r in todays)
    placed = sum(1 for r in todays
                 if (r.get("meta") or {}).get("stage") in ("placed", "dry_run"))
    summary = (f"{len(todays)} new ({by_component['ml']} ml · "
               f"{by_component['llm']} llm · {by_component['combined']} combined) · "
               f"{placed} placed · {graded_today} graded today")
    def _line(r: dict) -> str:
        # Every field is coerced: legacy rows predate the current schema (null
        # conviction, no component) and this runs in a step that now fails the
        # workflow, so a malformed row must not take the run down with it.
        conv = r.get("conviction")
        conv = f"{conv:.2f}" if isinstance(conv, (int, float)) else "—"
        meta = r.get("meta") or {}
        return (f"{str(r.get('symbol') or '?'):<6} "
                f"{str(meta.get('component') or '?'):<9} "
                f"{str(r.get('direction') or '?'):<5} conv={conv}  "
                f"stage={meta.get('stage', '-')}")

    detail = "\n".join(_line(r) for r in todays) or "no predictions logged today"
    return {"ok": bool(todays), "summary": summary, "detail": detail[:7000]}


def _upcoming(days: int = 7) -> list[dict]:
    """Liquid names reporting earnings in the next `days` days (forward-looking)."""
    try:
        from datetime import date, timedelta
        from atb.data.finnhub_provider import FinnhubProvider
        from atb.data.yfinance_provider import YFinanceProvider
        from atb.universe import LIQUID
        p = FinnhubProvider(price_provider=YFinanceProvider())
        cal = p.earnings_calendar(date.today(), date.today() + timedelta(days=days))
        up = [{"symbol": it["symbol"], "date": it.get("date"), "hour": it.get("hour"),
               "eps_estimate": it.get("epsEstimate")}
              for it in cal if it.get("symbol") in LIQUID and it.get("date")]
        return sorted(up, key=lambda x: x["date"])[:40]
    except Exception as e:
        print("upcoming fetch failed:", type(e).__name__, str(e)[:80])
        return []


def _broker():
    """Live Alpaca paper broker, or None if credentials/SDK are unavailable."""
    key, secret = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        print("broker unavailable: ALPACA_API_KEY/ALPACA_SECRET_KEY not set")
        return None
    try:
        from trader_core.broker.alpaca_client import AlpacaBroker
        return AlpacaBroker(key, secret, paper=True)
    except Exception as e:
        print("broker unavailable:", type(e).__name__, str(e)[:100])
        return None


def positions_from_broker(broker) -> list[dict] | None:
    """Open positions as dashboard rows, or None when the broker is unreachable.

    None and [] mean different things: [] is an account with nothing open, None
    is "don't know" and tells the caller to fall back rather than publish a
    confident zero.
    """
    if broker is None:
        return None
    try:
        return [{"occ_symbol": p.occ_symbol, "quantity": p.quantity,
                 "entry_price": p.entry_price, "mark": p.mark_price,
                 "entry_at_utc": None} for p in broker.list_positions()]
    except Exception as e:
        print("list_positions failed:", type(e).__name__, str(e)[:100])
        return None


def _positions_from_sqlite() -> list[dict]:
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


def collect_positions() -> list[dict]:
    """Alpaca first (it is the position-keeper of record), local SQLite as a
    fallback. data/atb.db is gitignored, so on the Actions runner only the
    broker has this — reading SQLite alone reported zero open positions
    forever."""
    rows = positions_from_broker(_broker())
    return rows if rows is not None else _positions_from_sqlite()


def main() -> None:
    preds = PredictionLog(PREDS).load()
    sc = summary(preds)
    positions = collect_positions()
    today = date.today().isoformat()
    run = run_record_from_predictions(
        [{"date": p.date, "symbol": p.symbol, "direction": p.direction,
          "conviction": p.conviction, "meta": p.meta} for p in preds],
        graded_today=sum(1 for p in preds if p.graded_date == today),
        today=today,
    )

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
        "state": "ok" if run["ok"] else "warn",
        "lastRun": datetime.now(timezone.utc).isoformat(),
        "summary": f"PEAD options swing (paper) — {note}",
        "ok": run["ok"],
        "metrics": metrics[:3],
    }
    if sc["n_graded"] > 0 and sc["hit_rate"] is not None:
        status["evalReliability"] = round(sc["hit_rate"], 3)
    if model.get("held_out_acc") is not None:
        status["evalScore"] = round(model["held_out_acc"], 3)

    _post("/api/report", {"agentId": "finance", "status": status})
    _post("/api/finance", {
        "model": model, "scorecard": sc, "predictions": preds_payload,
        "positions": positions, "candidates": [], "upcoming": _upcoming(),
        "note": note, "run": run,
    })


if __name__ == "__main__":
    main()
