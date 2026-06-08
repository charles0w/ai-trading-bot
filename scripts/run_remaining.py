"""
Runs the 3 remaining pre-registered backtest combos in one go (no manual edits).
Save next to backtest.py and:  python run_remaining.py
"""
import backtest as bt


def run_combo(mode, strat, horizon, label):
    bt.UNIVERSE_MODE = mode
    bt.HORIZON = horizon
    print("\n" + "=" * 70 + f"\n=== {label}\n" + "=" * 70)
    close = bt.download_close(bt.universe_tickers(), bt.START, bt.END)
    members = bt.build_member_sets(close)
    bp = bt.base_up_rate(close, members, horizon)
    recs = bt.run(close, strat, members, horizon)
    dates = list(close.index)
    split_i = next((k for k, d in enumerate(dates) if d.date().isoformat() > bt.TRAIN_END), len(dates))
    print(f"Strategy: {strat.__name__} | universe={mode} | horizon={horizon}d | n={len(recs)}")
    bt.hit_stats([r for r in recs if r["i"] < split_i], bp, "IN-SAMPLE (tune; don't trust)")
    bt.portfolio_metrics(close, recs, 0, split_i - 1, "IN-SAMPLE")
    bt.hit_stats([r for r in recs if r["i"] >= split_i], bp, "OUT-OF-SAMPLE (counts)")
    bt.portfolio_metrics(close, recs, split_i, len(dates) - 1, "OUT-OF-SAMPLE")


if __name__ == "__main__":
    run_combo("snapshot2018", bt.strat_xsec_momentum, 21, "RUN 2 -- H-C momentum | snapshot2018 (the key test)")
    run_combo("etf", bt.strat_weekly_reversal, 5, "RUN 3 -- H-A reversal | sector-ETF control")
    run_combo("etf", bt.strat_xsec_momentum, 21, "RUN 4 -- H-C momentum | sector-ETF control")
