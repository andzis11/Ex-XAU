"""
Parameter Optimizer — Grid Search untuk Ex-XAU Strategy
=========================================================
Mencari kombinasi parameter terbaik dari data historis.
"""

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
# 1. INDICATORS (same as backtest_xauusd.py)
# ─────────────────────────────────────────────

def add_indicators(df: pd.DataFrame, ema_fast: int, ema_slow: int,
                   rsi_period: int = 14, atr_period: int = 14) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    df["ema_fast"] = close.ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=ema_slow, adjust=False).mean()

    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_g = gain.ewm(com=rsi_period - 1, adjust=False).mean()
    avg_l = loss.ewm(com=rsi_period - 1, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(com=atr_period - 1, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_mid"]   = sma20

    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    return df.dropna()


# ─────────────────────────────────────────────
# 2. SIGNAL GENERATOR (optimized)
# ─────────────────────────────────────────────

def generate_signal(row, prev, ema_fast, ema_slow, rsi_os, rsi_ob,
                    min_confidence, use_ema200_filter, trend_bias):
    buy_score  = 0.0
    sell_score = 0.0
    reasons    = []

    # ── EMA Crossover (bobot 0.35) ──
    ema_cross_up   = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
    ema_cross_down = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]
    ema_trend_bull = row["ema_fast"] > row["ema_slow"]
    ema_trend_bear = row["ema_fast"] < row["ema_slow"]

    if ema_cross_up:
        buy_score += 0.35
        reasons.append("EMA cross UP")
    elif ema_trend_bull:
        buy_score += 0.15
        reasons.append("EMA bull")

    if ema_cross_down:
        sell_score += 0.35
        reasons.append("EMA cross DN")
    elif ema_trend_bear:
        sell_score += 0.15
        reasons.append("EMA bear")

    # ── RSI (bobot 0.25) ──
    rsi = row["rsi"]
    if rsi < 50 and rsi > rsi_os:
        buy_score += 0.25
        reasons.append(f"RSI bull {rsi:.0f}")
    elif rsi > 50 and rsi < rsi_ob:
        sell_score += 0.25
        reasons.append(f"RSI bear {rsi:.0f}")

    # ── MACD (bobot 0.20) ──
    if row["macd"] > row["macd_signal"] and row["macd_hist"] > 0:
        buy_score += 0.20
        reasons.append("MACD bull")
    elif row["macd"] < row["macd_signal"] and row["macd_hist"] < 0:
        sell_score += 0.20
        reasons.append("MACD bear")

    # ── Bollinger Band (bobot 0.20) ──
    if row["close"] < row["bb_lower"]:
        buy_score += 0.20
        reasons.append("BB oversold")
    elif row["close"] > row["bb_upper"]:
        sell_score += 0.20
        reasons.append("BB overbought")
    elif row["close"] > row["bb_mid"]:
        buy_score += 0.10
    else:
        sell_score += 0.10

    # ── EMA200 trend filter ──
    if use_ema200_filter:
        above_ema200 = row["close"] > row["ema200"]
        if above_ema200:
            # Bias: favor BUY when above EMA200
            buy_score  *= (1 + trend_bias)
            sell_score *= (1 - trend_bias * 0.5)
        else:
            buy_score  *= (1 - trend_bias * 0.5)
            sell_score *= (1 + trend_bias)

    # ── Tentukan arah ──
    if buy_score >= min_confidence and buy_score > sell_score:
        return {"direction": "BUY",  "confidence": buy_score,  "reasons": reasons}
    if sell_score >= min_confidence and sell_score > buy_score:
        return {"direction": "SELL", "confidence": sell_score, "reasons": reasons}
    return {"direction": "HOLD", "confidence": 0.0, "reasons": []}


# ─────────────────────────────────────────────
# 3. BACKTEST ENGINE (lightweight)
# ─────────────────────────────────────────────

def run_backtest(df, initial_balance, risk_pct, atr_sl, atr_tp,
                 ema_fast, ema_slow, rsi_os, rsi_ob, min_confidence,
                 use_ema200_filter, trend_bias, pip_value=10.0, commission_lot=7.0):
    """Lightweight backtest — returns dict of results."""
    balance = initial_balance
    peak = initial_balance
    equity_curve = []
    open_trade = None
    trade_idx = 0
    trades = []

    dfi = add_indicators(df, ema_fast, ema_slow, rsi_period=14, atr_period=14)
    rows = dfi.reset_index()

    for i in range(1, len(rows)):
        row  = rows.iloc[i]
        prev = rows.iloc[i - 1]

        # Check open trade exit
        if open_trade:
            t = open_trade
            hit_sl = hit_tp = False
            if t["direction"] == "BUY":
                if row["low"] <= t["sl"]:
                    hit_sl = True; exit_p = t["sl"]
                elif row["high"] >= t["tp"]:
                    hit_tp = True; exit_p = t["tp"]
                else:
                    # Record equity and continue
                    mark = balance + ((row["close"] - t["entry"]) if t["direction"]=="BUY" else (t["entry"] - row["close"])) * pip_value * t["lot"] / 0.01
                    equity_curve.append(mark)
                    peak = max(peak, mark)
                    continue
            else:
                if row["high"] >= t["sl"]:
                    hit_sl = True; exit_p = t["sl"]
                elif row["low"] <= t["tp"]:
                    hit_tp = True; exit_p = t["tp"]
                else:
                    mark = balance + ((row["close"] - t["entry"]) if t["direction"]=="BUY" else (t["entry"] - row["close"])) * pip_value * t["lot"] / 0.01
                    equity_curve.append(mark)
                    peak = max(peak, mark)
                    continue

            pip_dist = (exit_p - t["entry"]) if t["direction"] == "BUY" else (t["entry"] - exit_p)
            gross = pip_dist * pip_value * t["lot"] / 0.01
            comm = commission_lot * t["lot"]
            net = gross - comm
            balance += net

            trades.append({
                "direction": t["direction"],
                "net_pnl": net,
                "exit_reason": "SL" if hit_sl else "TP",
                "entry": t["entry"],
                "exit": exit_p,
            })
            open_trade = None

        # Generate new signal
        sig = generate_signal(row, prev, ema_fast, ema_slow, rsi_os, rsi_ob,
                              min_confidence, use_ema200_filter, trend_bias)
        if sig["direction"] in ("BUY", "SELL") and not open_trade:
            atr = row["atr"]
            entry = row["close"]
            d = sig["direction"]

            if d == "BUY":
                sl = entry - atr * atr_sl
                tp = entry + atr * atr_tp
            else:
                sl = entry + atr * atr_sl
                tp = entry - atr * atr_tp

            sl_dist = abs(entry - sl)
            risk_amt = balance * (risk_pct / 100)
            lot = max(0.01, min(round(risk_amt / (sl_dist * pip_value / 0.01), 2), 1.0))

            open_trade = {
                "direction": d, "entry": entry, "sl": sl, "tp": tp, "lot": lot,
            }

        # Equity tracking
        if open_trade:
            mark = balance + ((row["close"] - open_trade["entry"]) if open_trade["direction"]=="BUY" else (open_trade["entry"] - row["close"])) * pip_value * open_trade["lot"] / 0.01
        else:
            mark = balance
        equity_curve.append(mark)
        peak = max(peak, mark)

    # Force close
    if open_trade:
        t = open_trade
        last_price = rows.iloc[-1]["close"]
        pip_dist = (last_price - t["entry"]) if t["direction"] == "BUY" else (t["entry"] - last_price)
        net = pip_dist * pip_value * t["lot"] / 0.01 - commission_lot * t["lot"]
        balance += net
        trades.append({"direction": t["direction"], "net_pnl": net, "exit_reason": "END"})

    # Compute metrics
    if not trades:
        return {"net_pnl": 0, "win_rate": 0, "profit_factor": 0, "max_dd": 0,
                "total_trades": 0, "sharpe": 0, "final_balance": balance}

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100
    gp = sum(t["net_pnl"] for t in wins)
    gl = abs(sum(t["net_pnl"] for t in losses))
    pf = gp / gl if gl else float("inf")
    npnl = sum(t["net_pnl"] for t in trades)

    # Max drawdown
    max_dd = 0
    pk = equity_curve[0]
    for e in equity_curve:
        pk = max(pk, e)
        dd = (pk - e) / pk * 100
        max_dd = max(max_dd, dd)

    # Sharpe
    pnls = [t["net_pnl"] for t in trades]
    sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if np.std(pnls) > 0 else 0

    return {
        "net_pnl": npnl,
        "win_rate": win_rate,
        "profit_factor": pf,
        "max_dd": max_dd,
        "total_trades": len(trades),
        "sharpe": sharpe,
        "final_balance": balance,
    }


# ─────────────────────────────────────────────
# 4. DATA LOADER
# ─────────────────────────────────────────────

def load_data(csv_path=None):
    if csv_path and os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        df.columns = [c.lower().strip() for c in df.columns]
        return df
    else:
        np.random.seed(42)
        n = 2000
        dates = pd.date_range("2024-01-01", periods=n, freq="1h")
        returns = np.random.normal(0.0001, 0.003, n)
        for i in range(0, n, 200):
            trend = np.random.choice([-1, 1]) * 0.0005
            returns[i:i+200] += trend
        price = 2000.0 * np.cumprod(1 + returns)
        df = pd.DataFrame({
            "open":   price,
            "high":   price * (1 + abs(np.random.normal(0, 0.002, n))),
            "low":    price * (1 - abs(np.random.normal(0, 0.002, n))),
            "close":  price * (1 + np.random.normal(0, 0.001, n)),
            "volume": np.random.randint(500, 8000, n),
        }, index=dates)
        return df


# ─────────────────────────────────────────────
# 5. GRID SEARCH
# ─────────────────────────────────────────────

def optimize(df, initial_balance=500):
    """Grid search over key parameters."""
    best = None
    best_params = None
    total_combos = 0

    # Parameter grid — tuned for XAU/USD
    param_grid = {
        "ema_fast":     [9, 12, 20],
        "ema_slow":     [21, 34, 50],
        "rsi_os":       [25, 30, 35],
        "rsi_ob":       [65, 70, 75],
        "atr_sl":       [1.0, 1.5, 2.0],
        "atr_tp":       [2.0, 3.0, 4.0],
        "min_confidence": [0.55, 0.60, 0.65, 0.70],
        "use_ema200_filter": [True, False],
        "trend_bias":   [0.1, 0.2, 0.3],
    }

    print("\n  Parameter Grid Search")
    print(f"  {'='*50}")

    # Use subset for speed (limit combinations)
    ema_combos = [(9,21), (12,21), (9,34), (20,50)]
    rsi_combos = [(25,75), (30,70), (35,65)]
    atr_combos = [(1.0, 2.0), (1.5, 3.0), (2.0, 4.0)]
    conf_values = [0.55, 0.60, 0.65, 0.70]
    ema200_values = [True, False]
    bias_values = [0.1, 0.2, 0.3]

    for ema_fast, ema_slow in ema_combos:
        for rsi_os, rsi_ob in rsi_combos:
            for atr_sl, atr_tp in atr_combos:
                for mc in conf_values:
                    for e200 in ema200_values:
                        for tb in bias_values:
                            total_combos += 1
                            r = run_backtest(
                                df, initial_balance,
                                risk_pct=1.0,
                                atr_sl=atr_sl, atr_tp=atr_tp,
                                ema_fast=ema_fast, ema_slow=ema_slow,
                                rsi_os=rsi_os, rsi_ob=rsi_ob,
                                min_confidence=mc,
                                use_ema200_filter=e200,
                                trend_bias=tb,
                            )

                            # Scoring: prioritize profit factor + win rate + low drawdown
                            score = (
                                r["profit_factor"] * 0.35 +
                                r["win_rate"] / 100 * 0.25 +
                                max(0, (1 - r["max_dd"]/100)) * 0.20 +
                                (1 if r["net_pnl"] > 0 else -1) * 0.20
                            )

                            if best is None or score > best:
                                best = score
                                best_params = {
                                    "ema_fast": ema_fast,
                                    "ema_slow": ema_slow,
                                    "rsi_os": rsi_os,
                                    "rsi_ob": rsi_ob,
                                    "atr_sl": atr_sl,
                                    "atr_tp": atr_tp,
                                    "min_confidence": mc,
                                    "use_ema200_filter": e200,
                                    "trend_bias": tb,
                                }
                                best_results = r

                            if total_combos % 500 == 0:
                                print(f"  Tested {total_combos} combos... best PF={best_results['profit_factor']:.2f}")

    print(f"\n  {'='*50}")
    print(f"  Total combinations tested: {total_combos}")
    print(f"  Best score: {best:.3f}")

    # Run detailed backtest with best params
    print(f"\n  Running detailed backtest with best params...")
    detailed = run_backtest(
        df, initial_balance,
        risk_pct=1.0,
        atr_sl=best_params["atr_sl"], atr_tp=best_params["atr_tp"],
        ema_fast=best_params["ema_fast"], ema_slow=best_params["ema_slow"],
        rsi_os=best_params["rsi_os"], rsi_ob=best_params["rsi_ob"],
        min_confidence=best_params["min_confidence"],
        use_ema200_filter=best_params["use_ema200_filter"],
        trend_bias=best_params["trend_bias"],
    )

    return best_params, detailed


# ─────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parameter Optimizer for Ex-XAU")
    parser.add_argument("--csv",     type=str, default=None, help="Path to CSV")
    parser.add_argument("--balance", type=float, default=500.0)
    args = parser.parse_args()

    print("\n" + "=" * 52)
    print("  EX-XAU PARAMETER OPTIMIZER")
    print("=" * 52)

    df = load_data(args.csv)
    print(f"  Data: {len(df)} candles")

    best_params, results = optimize(df, args.balance)

    # Print results
    sep = "=" * 52
    print(f"\n{sep}")
    print(f"  OPTIMAL PARAMETERS FOUND")
    print(f"{sep}")
    print(f"  EMA fast/slow    : {best_params['ema_fast']} / {best_params['ema_slow']}")
    print(f"  RSI OS/OB        : {best_params['rsi_os']} / {best_params['rsi_ob']}")
    print(f"  ATR SL/TP mult   : {best_params['atr_sl']}× / {best_params['atr_tp']}×")
    print(f"  Min confidence   : {best_params['min_confidence']*100:.0f}%")
    print(f"  EMA200 filter    : {'ON' if best_params['use_ema200_filter'] else 'OFF'}")
    print(f"  Trend bias       : {best_params['trend_bias']}")
    print(f"{sep}")
    print(f"  Net profit       : ${results['net_pnl']:>+10.2f}")
    print(f"  Win rate         : {results['win_rate']:.1f}%")
    print(f"  Profit factor    : {results['profit_factor']:.2f}")
    print(f"  Max drawdown     : {results['max_dd']:.1f}%")
    print(f"  Sharpe ratio     : {results['sharpe']:.2f}")
    print(f"  Total trades     : {results['total_trades']}")
    print(f"  Final balance    : ${results['final_balance']:>10.2f}")
    print(f"{sep}")

    # Verdict
    pf_ok = results['profit_factor'] >= 1.5
    wr_ok = results['win_rate'] >= 50
    dd_ok = results['max_dd'] <= 20
    npnl_ok = results['net_pnl'] > 0

    if pf_ok and wr_ok and dd_ok and npnl_ok:
        verdict = "✅ LAYAK untuk demo trading"
    elif pf_ok or (wr_ok and npnl_ok):
        verdict = "⚠️  PERLU OPTIMASI sebelum demo"
    else:
        verdict = "❌ BELUM LAYAK — strategi perlu direvisi"

    print(f"\n  VERDICT: {verdict}")
    print(f"{sep}\n")

    # Save
    output = {
        "best_parameters": best_params,
        "results": results,
    }
    os.makedirs("results", exist_ok=True)
    with open("results/optimized_params.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Saved: results/optimized_params.json\n")


if __name__ == "__main__":
    main()
