"""
backtest.py -- honest walk-forward backtester that reuses the live grading rule.

v3 adds a POINT-IN-TIME universe to attack survivorship bias (v2's universe was
today's mega-cap winners, so its "wins" were circular -- see backtest.md).

UNIVERSE_MODE (set below):
  "snapshot2018" -- DEFAULT, runnable now. A large-cap universe fixed as of the
        backtest START (2018), deliberately including names that LAGGED (GE, IBM,
        INTC, T, WBA, KHC, F...). No 2026 hindsight in the selection -> the main
        survivorship driver is removed. Residual bias: a 2018 name acquired/delisted
        mid-window has price gaps (handled by NaN-skip).
  "etf"         -- sector ETFs only. Fully survivorship-free (ETFs don't delist for
        bad performance). The cleanest free control, but no single-name granularity.
  "pit_csv"     -- GOLD STANDARD. True point-in-time index membership from a free
        constituents CSV (download once; see PIT_CSV + backtest.md). Only trades
        names that were index members AS OF each date. Still can't fully fix delisted
        *prices* on free data, but removes the membership look-ahead.
  "winners2026" -- the old biased universe, kept only to reproduce/illustrate the trap.

HONEST LIMIT: a truly survivorship-free single-name backtest needs paid data with
delisted prices (CRSP / Norgate / Sharadar). Free tools can only approximate.

Requires: pip install yfinance pandas numpy
Run:      python backtest.py     (set UNIVERSE_MODE / STRATEGY / HORIZON below)
"""
from __future__ import annotations
import math
import statistics

# ── universe config ─────────────────────────────────────────────────────
UNIVERSE_MODE = "snapshot2018"     # snapshot2018 | etf | pit_csv | winners2026
PIT_CSV = "sp500_constituents.csv" # used only in pit_csv mode (see loader below)

ETF_UNIVERSE = ["SPY", "QQQ", "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU"]

WINNERS_2026 = [  # the biased v2 universe -- for contrast only
    "SPY", "QQQ", "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX",
    "JPM", "BAC", "XOM", "CVX", "UNH", "JNJ", "PG", "KO", "WMT", "HD",
]

# Large caps fixed as of START (2018), winners AND laggards (de-biased, all still trade):
SNAPSHOT_2018 = [
    "SPY",  # keep SPY for the benchmark comparison
    # tech / comm
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "INTC", "CSCO", "ORCL", "IBM", "QCOM",
    "TXN", "NVDA", "ADBE", "CRM", "AVGO", "T", "VZ", "CMCSA", "NFLX", "DIS",
    # financials
    "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "USB", "PNC", "BLK", "SCHW", "BRK-B", "AIG",
    # health
    "JNJ", "PFE", "UNH", "MRK", "ABBV", "AMGN", "GILD", "BMY", "CVS", "MDT", "LLY", "ABT", "BIIB",
    # consumer
    "PG", "KO", "PEP", "WMT", "HD", "MCD", "NKE", "COST", "SBUX", "LOW", "TGT", "MDLZ", "CL",
    "KHC", "MO", "PM",
    # industrials / energy / materials
    "XOM", "CVX", "COP", "SLB", "BA", "GE", "MMM", "CAT", "HON", "UNP", "UPS", "LMT", "EMR", "F", "GM",
    # payments / other
    "V", "MA", "PYPL", "BKNG", "AMT", "NEE", "DUK", "SO", "WBA",
]

START, END = "2018-01-01", "2026-06-01"
HORIZON = 5            # 5 for reversal/trend; momentum wants ~21 (see backtest.md)
NOISE = 0.01
COST_BPS = 5
TRAIN_END = "2023-06-01"


def universe_tickers():
    if UNIVERSE_MODE == "etf":
        return ETF_UNIVERSE
    if UNIVERSE_MODE == "winners2026":
        return WINNERS_2026
    if UNIVERSE_MODE == "pit_csv":
        return _pit_all_tickers()
    return SNAPSHOT_2018   # snapshot2018 (default)


# ── point-in-time membership (pit_csv mode) ──────────────────────────────
# Expects a CSV of historical index membership. Two accepted shapes:
#   (a) rows of (date, tickers) where tickers is space/comma-separated constituents
#       on that date  (e.g. fja05680/sp500 "S&P 500 Historical Components.csv")
#   (b) rows of (date, ticker, action in {add,remove})  -- change log
# Free source example: github.com/fja05680/sp500  (download once to PIT_CSV).
_PIT = None  # sorted list of (date_str, frozenset(tickers))

def _load_pit():
    global _PIT
    if _PIT is not None:
        return _PIT
    import csv
    rows = list(csv.reader(open(PIT_CSV, newline="")))
    header = [h.strip().lower() for h in rows[0]]
    snaps = {}
    if "tickers" in header or "constituents" in header:
        di = header.index("date")
        ti = header.index("tickers") if "tickers" in header else header.index("constituents")
        for r in rows[1:]:
            d = r[di].strip()
            toks = r[ti].replace(",", " ").split()
            snaps[d] = frozenset(t.strip().upper() for t in toks if t.strip())
    else:  # change-log form: rebuild running membership
        di, si, ai = header.index("date"), header.index("ticker"), header.index("action")
        cur = set()
        for r in sorted(rows[1:], key=lambda x: x[di]):
            t = r[si].strip().upper()
            if r[ai].strip().lower().startswith("add"):
                cur.add(t)
            else:
                cur.discard(t)
            snaps[r[di].strip()] = frozenset(cur)
    _PIT = sorted(snaps.items())
    return _PIT

def _pit_all_tickers():
    allt = set()
    for _, s in _load_pit():
        allt |= s
    return sorted(allt | {"SPY"})

def _pit_members_asof(date_str):
    pit = _load_pit()
    m = frozenset()
    for d, s in pit:
        if d <= date_str:
            m = s
        else:
            break
    return m | {"SPY"}


def build_member_sets(close):
    """Per-date set of tradeable tickers (members as-of date AND price present)."""
    cols = list(close.columns)
    present = close.notna().values   # rows x cols boolean
    cidx = {c: k for k, c in enumerate(cols)}
    out = []
    for i, d in enumerate(close.index):
        if UNIVERSE_MODE == "pit_csv":
            elig = _pit_members_asof(d.date().isoformat())
            out.append({c for c in cols if c in elig and present[i, cidx[c]]})
        else:
            out.append({c for c in cols if present[i, cidx[c]]})
    return out


# ── data ────────────────────────────────────────────────────────────────
def download_close(tickers, start, end):
    import yfinance as yf
    df = yf.download(sorted(set(tickers)), start=start, end=end, progress=False, auto_adjust=True)
    close = df["Close"] if "Close" in df else df
    return close.dropna(how="all")


# ── strategies: see hist = prices for ELIGIBLE members through date only ──
def strat_weekly_reversal(date, hist, n=2):
    if len(hist) < 7:
        return []
    r5 = (hist.iloc[-1] / hist.iloc[-6] - 1).dropna()
    if r5.empty:
        return []
    worst = r5.nsmallest(min(n, len(r5)))
    return [(t, "up", "high" if worst[t] <= -0.10 else "medium") for t in worst.index]

def strat_trend_200dma(date, hist):
    if len(hist) < 200:
        return []
    last = hist.iloc[-1]; ma = hist.iloc[-200:].mean()
    return [(t, "up", "medium") for t in hist.columns
            if not math.isnan(last[t]) and not math.isnan(ma[t]) and last[t] > ma[t]]

def strat_xsec_momentum(date, hist, n=3):
    if len(hist) < 252:
        return []
    mom = (hist.iloc[-21] / hist.iloc[-252] - 1).dropna()
    if mom.empty:
        return []
    top = mom.nlargest(min(n, len(mom)))
    return [(t, "up", "medium") for t in top.index]

STRATEGY = strat_weekly_reversal


def grade_call(direction, entry, exit_):   # mirrors sync_dashboard.py
    if entry is None or exit_ is None or entry == 0:
        return None
    ret = exit_ / entry - 1
    realized = (ret if direction == "up" else -ret) - COST_BPS / 10000.0
    return {"ret": ret, "realized": realized, "correct": bool(ret > NOISE if direction == "up" else ret < -NOISE)}


def run(close, strategy, members, horizon=HORIZON):
    dates = list(close.index); out = []
    for i in range(1, len(dates) - horizon):
        cols = [c for c in close.columns if c in members[i]]
        if not cols:
            continue
        hist = close.iloc[: i + 1][cols]            # eligible members, data through day i
        for ticker, direction, conv in strategy(dates[i], hist):
            entry = float(close[ticker].iloc[i]); exit_ = float(close[ticker].iloc[i + horizon])
            g = grade_call(direction, entry, exit_)
            if g is None or math.isnan(entry) or math.isnan(exit_):
                continue
            out.append({"i": i, "exit_i": i + horizon, "date": dates[i].date().isoformat(),
                        "ticker": ticker, "direction": direction, "conviction": conv, **g})
    return out


def base_up_rate(close, members, horizon=HORIZON):
    ups = tot = 0
    for i in range(1, len(close.index) - horizon):
        for t in members[i]:
            e, x = close[t].iloc[i], close[t].iloc[i + horizon]
            if math.isnan(e) or math.isnan(x) or e == 0:
                continue
            tot += 1
            if x / e - 1 > NOISE:
                ups += 1
    return ups / tot if tot else 0.0


def _p_two_sided(z):
    return math.erfc(abs(z) / math.sqrt(2))

def hit_stats(records, baseline_p, label):
    n = len(records)
    if n == 0:
        print("\n[" + label + "] no trades."); return
    hit = sum(r["correct"] for r in records) / n
    se = math.sqrt(baseline_p * (1 - baseline_p) / n)
    z = (hit - baseline_p) / se if se else float("nan")
    p = _p_two_sided(z) if not math.isnan(z) else float("nan")
    sig = "*** sig (Bonferroni p<.017)" if p < 0.017 else ("~ p<.05" if p < 0.05 else "not significant")
    print("\n[" + label + "] trades=" + str(n))
    print(f"  hit {hit:.1%} vs baseline {baseline_p:.1%}  edge {hit-baseline_p:+.1%}  z={z:.2f} p={p:.3f}  {sig}")
    print(f"  avg realized/trade {statistics.mean(r['realized'] for r in records):+.2%} (after {COST_BPS}bps)")


def portfolio_metrics(close, records, lo, hi, label):
    import numpy as np
    dr = close.pct_change().values
    colidx = {t: k for k, t in enumerate(close.columns)}
    nday = len(close.index)
    pnl = np.zeros(nday); cnt = np.zeros(nday); cost = np.zeros(nday)
    for r in records:
        if r["i"] < lo or r["i"] > hi:
            continue
        sign = 1.0 if r["direction"] == "up" else -1.0
        c = colidx[r["ticker"]]
        for t in range(r["i"] + 1, min(r["exit_i"], hi) + 1):
            d = dr[t, c]
            if not np.isnan(d):
                pnl[t] += sign * d; cnt[t] += 1
        cost[r["i"] + 1] += COST_BPS / 10000.0
    port = np.where(cnt > 0, (pnl - cost) / np.where(cnt > 0, cnt, 1), 0.0)[lo:hi + 1]
    if len(port) == 0:
        print("\n[" + label + " portfolio] empty."); return
    eq = np.cumprod(1 + port); yrs = len(port) / 252
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 and eq[-1] > 0 else float("nan")
    peak = np.maximum.accumulate(eq); maxdd = float((eq / peak - 1).min())
    active = port[cnt[lo:hi + 1] > 0]
    sharpe = (active.mean() / active.std() * math.sqrt(252)) if len(active) > 1 and active.std() > 0 else float("nan")
    spy = dr[lo + 1:hi + 1, colidx["SPY"]]; spy = spy[~np.isnan(spy)]
    spy_eq = float(np.prod(1 + spy)); spy_cagr = spy_eq ** (1 / yrs) - 1 if yrs > 0 else float("nan")
    verdict = "BEATS" if cagr > spy_cagr else "LAGS"
    print("\n[" + label + " PORTFOLIO (capital-shared, real)]")
    print(f"  total {eq[-1]-1:+.1%}  CAGR {cagr:+.1%}  maxDD {maxdd:.1%}  Sharpe {sharpe:.2f}")
    print(f"  buy-hold SPY: total {spy_eq-1:+.1%}  CAGR {spy_cagr:+.1%}  -> strategy {verdict} SPY")


def main():
    tickers = universe_tickers()
    print(f"Universe: {UNIVERSE_MODE} ({len(tickers)} tickers).  Downloading {START}..{END} ...")
    close = download_close(tickers, START, END)
    members = build_member_sets(close)
    bp = base_up_rate(close, members)
    recs = run(close, STRATEGY, members)
    dates = list(close.index)
    split_i = next((k for k, d in enumerate(dates) if d.date().isoformat() > TRAIN_END), len(dates))
    in_s = [r for r in recs if r["i"] < split_i]
    oos = [r for r in recs if r["i"] >= split_i]
    print(f"\nStrategy: {STRATEGY.__name__} | horizon={HORIZON}d cost={COST_BPS}bps | split @ {TRAIN_END}")
    hit_stats(in_s, bp, "IN-SAMPLE (tune; don't trust)")
    portfolio_metrics(close, recs, 0, split_i - 1, "IN-SAMPLE")
    hit_stats(oos, bp, "OUT-OF-SAMPLE (counts)")
    portfolio_metrics(close, recs, split_i, len(dates) - 1, "OUT-OF-SAMPLE")
    print("\nVerdict bar: OOS beats baseline (p<.017), survives costs, AND portfolio beats")
    print("buy-hold SPY risk-adjusted. On a de-biased universe, expect most edges to shrink.")


if __name__ == "__main__":
    main()
