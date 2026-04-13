"""
compare_periods.py — Backtest comparison: 7, 14, 30 days
==========================================================
Fetches REAL XAU/USD data via yfinance and runs the survival mode strategy.
"""

import os
import sys
import json
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from backtest_xauusd import (
    BacktestConfig, Backtest, BacktestResult, Trade
)

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system("pip install yfinance")
    import yfinance as yf


def fetch_real_data(period: str, interval: str = "5m") -> pd.DataFrame:
    """Fetch real Gold futures data (proxy for XAU/USD)."""
    print(f"  Fetching real data ({period}, {interval})...")
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        print(f"  ❌ No data for period {period}")
        return None

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df.index.name = "time"
    return df[["open", "high", "low", "close", "volume"]]


def run_period_backtest(period_label: str, period_yf: str, balance=500):
    """Run backtest for a specific time period — SCALPING MODE."""
    print(f"\n{'='*60}")
    print(f"  PERIOD: {period_label} ({period_yf}) — SCALPING M5")
    print(f"{'='*60}")

    df = fetch_real_data(period_yf, interval="5m")
    if df is None or len(df) < 80:
        print(f"  ❌ Insufficient data ({len(df) if df is not None else 0} candles, need ≥80)")
        return None

    print(f"  Data: {len(df)} M5 candles | {df.index[0]} to {df.index[-1]}")
    print(f"  Price: ${df['close'].min():.2f} – ${df['close'].max():.2f}")

    cfg = BacktestConfig(
        initial_balance=balance,
        risk_percent=1.0,                    # SCALPING
        atr_sl_mult=1.0,                     # Tight SL
        atr_tp_mult=1.5,                     # Quick TP
        min_confidence=0.50,
        use_trailing_stop=True,
        trailing_atr_mult=0.5,               # Aggressive trail
        trailing_activation=0.8,             # Activate early
        ema200_trend_bias=0.40,
    )

    engine = Backtest(cfg)
    return engine.run(df)


def print_comparison_table(results: dict):
    print(f"\n{'='*80}")
    print(f"  COMPARISON SUMMARY")
    print(f"{'='*80}")
    hdr = f"  {'Period':<12} {'Candles':<9} {'Trades':<8} {'Win%':<7} {'PF':<7} " \
          f"{'Net $':<12} {'DD%':<7} {'Sharpe':<7}"
    print(hdr)
    print(f"  {'─'*12} {'─'*9} {'─'*8} {'─'*7} {'─'*7} {'─'*12} {'─'*7} {'─'*7}")

    for label, r in results.items():
        if r is None:
            print(f"  {label:<12} {'N/A':<9} {'N/A':<8} {'N/A':<7} {'N/A':<7} "
                  f"{'N/A':<12} {'N/A':<7} {'N/A':<7}")
            continue
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "∞"
        n_candles = len(r.equity_curve)
        print(f"  {label:<12} {n_candles:<9} {r.total_trades:<8} {r.win_rate:<7.1f} "
              f"{pf:<7} ${r.net_profit:>+10.2f} {r.max_dd:<7.1f} {r.sharpe:<7.2f}")

    print(f"{'='*80}\n")


def main():
    print("\n" + "=" * 60)
    print("  EX-XAU BACKTEST — REAL DATA COMPARISON (SCALPING)")
    print("  M5 timeframe | Tight SL 1× ATR | Quick TP 1.5× ATR")
    print("=" * 60)

    periods = {
        "7 Days":  "7d",
        "14 Days": "14d",
        "30 Days": "1mo",
    }

    results = {}
    for label, yf_period in periods.items():
        r = run_period_backtest(label, yf_period, balance=500)
        results[label] = r

        if r is None:
            continue

        # Detailed
        sep = "─" * 50
        print(f"\n  📊 {label} — Details")
        print(f"  {sep}")
        print(f"  Trades        : {r.total_trades}")
        print(f"  Win rate      : {r.win_rate:.1f}%")
        print(f"  Profit factor : {r.profit_factor:.2f}")
        print(f"  Net profit    : ${r.net_profit:>+10.2f} ({r.net_profit/500*100:+.1f}%)")
        print(f"  Max drawdown  : {r.max_dd:.1f}%")
        print(f"  Sharpe        : {r.sharpe:.2f}")
        print(f"  Exit: SL={r.exit_by_sl} | TP={r.exit_by_tp} | TSL={r.exit_by_tsl} | End={r.exit_by_end}")
        print(f"  Avg daily P&L : ${r.avg_daily_pnl:>+10.2f}")
        print(f"  Best / Worst  : ${r.best_day:>+8.2f} / ${r.worst_day:>+8.2f}")
        print(f"  {sep}")

        # Save JSON
        os.makedirs("results", exist_ok=True)
        with open(f"results/backtest_{label.replace(' ', '_').lower()}.json", "w") as f:
            json.dump({
                "period": label,
                "candles": len(r.equity_curve),
                "summary": {
                    "initial_balance": 500,
                    "final_balance": round(500 + r.net_profit, 2),
                    "net_profit": round(r.net_profit, 2),
                    "total_return_pct": round(r.net_profit / 500 * 100, 2),
                    "total_trades": r.total_trades,
                    "win_rate": round(r.win_rate, 2),
                    "profit_factor": round(r.profit_factor, 3) if r.profit_factor < 100 else 999.999,
                    "max_drawdown_pct": round(r.max_dd, 2),
                    "sharpe_ratio": round(r.sharpe, 3),
                    "avg_daily_pnl": round(r.avg_daily_pnl, 2),
                    "exit_breakdown": {"SL": r.exit_by_sl, "TP": r.exit_by_tp,
                                       "TSL": r.exit_by_tsl, "END": r.exit_by_end},
                },
            }, f, indent=2)
        print(f"  💾 Saved: results/backtest_{label.replace(' ', '_').lower()}.json")

    print_comparison_table(results)

    # Verdict
    print(f"\n  💡 VERDICT:")
    for label, r in results.items():
        if r is None:
            print(f"  {label:<12}: ❌ No data")
            continue
        pf_ok = r.profit_factor >= 1.2
        wr_ok = r.win_rate >= 45
        dd_ok = r.max_dd <= 30
        profitable = r.net_profit > 0

        if pf_ok and wr_ok and profitable:
            verdict = "✅ Profitable"
        elif profitable:
            verdict = "⚠️  Marginal"
        else:
            verdict = "❌ Unprofitable"

        print(f"  {label:<12}: {verdict}  PF={r.profit_factor:.2f}  WR={r.win_rate:.1f}%  DD={r.max_dd:.1f}%  ${r.net_profit:>+10.2f}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
