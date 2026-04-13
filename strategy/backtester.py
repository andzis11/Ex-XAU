"""
Layer 6 — Backtester.
Tests strategy logic on historical data and produces performance metrics.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from config.pairs import get_pair_params
from data.indicators import add_indicators
from models.trainer import LSTMTrainer

logger = logging.getLogger(__name__)


class BacktestResult:
    """Container for backtest performance metrics."""

    def __init__(self):
        self.initial_balance: float = 0
        self.final_balance: float = 0
        self.total_return_pct: float = 0
        self.max_drawdown_pct: float = 0
        self.total_trades: int = 0
        self.wins: int = 0
        self.losses: int = 0
        self.win_rate: float = 0
        self.profit_factor: float = 0
        self.sharpe_ratio: float = 0
        self.avg_pnl: float = 0
        self.best_trade: float = 0
        self.worst_trade: float = 0
        self.total_commission: float = 0

    def to_dict(self) -> dict:
        return {k: round(v, 2) if isinstance(v, float) else v for k, v in vars(self).items()}

    def summary(self) -> str:
        d = self.to_dict()
        return (
            f"\n{'='*50}\n"
            f"BACKTEST RESULTS\n"
            f"{'='*50}\n"
            f"Initial Balance:  ${d['initial_balance']:>12,.2f}\n"
            f"Final Balance:    ${d['final_balance']:>12,.2f}\n"
            f"Total Return:     {d['total_return_pct']:>12.2f}%\n"
            f"Max Drawdown:     {d['max_drawdown_pct']:>12.2f}%\n"
            f"{'-'*50}\n"
            f"Total Trades:     {d['total_trades']:>12}\n"
            f"Wins / Losses:    {d['wins']:>6} / {d['losses']}\n"
            f"Win Rate:         {d['win_rate']:>12.1f}%\n"
            f"Profit Factor:    {d['profit_factor']:>12.2f}\n"
            f"Sharpe Ratio:     {d['sharpe_ratio']:>12.2f}\n"
            f"{'-'*50}\n"
            f"Avg P&L:          ${d['avg_pnl']:>12.2f}\n"
            f"Best Trade:       ${d['best_trade']:>12.2f}\n"
            f"Worst Trade:      ${d['worst_trade']:>12.2f}\n"
            f"Commission:       ${d['total_commission']:>12.2f}\n"
            f"{'='*50}\n"
        )


class StrategyBacktester:
    """
    Run historical backtests simulating the bot's full pipeline:
    Indicators → LSTM Prediction → Signal → Risk → Execution → P&L
    """

    def __init__(
        self,
        initial_balance: float = 10000,
        commission_per_lot: float = 7.0,
        results_dir: str = "results/backtest",
    ):
        self.initial_balance = initial_balance
        self.commission_per_lot = commission_per_lot
        self.results_dir = results_dir
        os.makedirs(results_dir, exist_ok=True)

    def run(
        self,
        symbol: str,
        df: pd.DataFrame,
        predictor=None,
    ) -> BacktestResult:
        """
        Run backtest on historical OHLCV data.

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            df: Raw OHLCV DataFrame (no indicators yet)
            predictor: LSTMPredictor instance (if None, uses rule-based fallback)

        Returns:
            BacktestResult with full performance metrics
        """
        logger.info(f"Starting backtest: {symbol} | {len(df)} candles")

        pair_params = get_pair_params(symbol)

        # Add indicators
        df = add_indicators(df)
        if df.empty:
            logger.error("No data after adding indicators")
            return None

        result = BacktestResult()
        result.initial_balance = self.initial_balance
        balance = self.initial_balance
        equity_curve = [balance]
        trades = []
        commission_total = 0.0

        # Walk-forward simulation
        # Start after indicator warmup (~50 bars) + LSTM lookback
        start_idx = 60
        for i in range(start_idx, len(df) - 1):
            lookback_df = df.iloc[:i]
            current = df.iloc[i]
            next_bar = df.iloc[i + 1]

            entry_price = float(current["close"])
            atr = float(current["atr"])

            # Get signal
            if predictor:
                signal, confidence = predictor.predict(symbol, lookback_df)
            else:
                # Fallback: rule-based signal
                signal, confidence = self._rule_based_signal(lookback_df)

            # Check confidence threshold
            if confidence < pair_params.min_confidence:
                equity_curve.append(balance)
                continue

            if signal == "HOLD":
                equity_curve.append(balance)
                continue

            # Check for existing open trade (simplified: max 1 position)
            open_trade = next(
                (t for t in trades if t["status"] == "OPEN"), None
            )

            # Close existing trade if conditions met
            if open_trade:
                # Check if SL or TP hit
                high = float(next_bar["high"])
                low = float(next_bar["low"])

                exited = False
                if open_trade["direction"] == "BUY":
                    if low <= open_trade["sl"]:
                        exit_price = open_trade["sl"]
                        exit_reason = "SL"
                        exited = True
                    elif high >= open_trade["tp"]:
                        exit_price = open_trade["tp"]
                        exit_reason = "TP"
                        exited = True
                else:  # SELL
                    if high >= open_trade["sl"]:
                        exit_price = open_trade["sl"]
                        exit_reason = "SL"
                        exited = True
                    elif low <= open_trade["tp"]:
                        exit_price = open_trade["tp"]
                        exit_reason = "TP"
                        exited = True

                if exited:
                    tick_value = pair_params.pip_value_per_lot
                    if open_trade["direction"] == "BUY":
                        pnl = (exit_price - open_trade["entry"]) * open_trade["lot"] * tick_value
                    else:
                        pnl = (open_trade["entry"] - exit_price) * open_trade["lot"] * tick_value

                    commission = open_trade["lot"] * self.commission_per_lot
                    net_pnl = pnl - commission
                    balance += net_pnl
                    commission_total += commission

                    open_trade["exit"] = exit_price
                    open_trade["pnl"] = net_pnl
                    open_trade["status"] = "CLOSED"
                    open_trade["exit_reason"] = exit_reason
                else:
                    equity_curve.append(balance)
                    continue
            else:
                equity_curve.append(balance)
                continue

            # Open new trade if no position
            if signal in ("BUY", "SELL"):
                sl, tp = self._calc_sl_tp(signal, entry_price, atr, pair_params)
                sl_pips = abs(entry_price - sl) / (atr / 14)  # Approximate pip calc
                lot = self._calc_lot(symbol, sl_pips, balance, pair_params)

                commission = lot * self.commission_per_lot

                trades.append({
                    "entry": entry_price,
                    "direction": signal,
                    "lot": lot,
                    "sl": sl,
                    "tp": tp,
                    "status": "OPEN",
                    "signal_confidence": confidence,
                    "atr": atr,
                })

        # Close any remaining open trades at last price
        last_price = float(df["close"].iloc[-1])
        for trade in trades:
            if trade["status"] == "OPEN":
                tick_value = pair_params.pip_value_per_lot
                if trade["direction"] == "BUY":
                    pnl = (last_price - trade["entry"]) * trade["lot"] * tick_value
                else:
                    pnl = (trade["entry"] - last_price) * trade["lot"] * tick_value

                commission = trade["lot"] * self.commission_per_lot
                net_pnl = pnl - commission
                balance += net_pnl
                commission_total += commission

                trade["exit"] = last_price
                trade["pnl"] = net_pnl
                trade["status"] = "CLOSED"
                trade["exit_reason"] = "end_of_backtest"

        # Calculate metrics
        result.final_balance = balance
        result.total_return_pct = (balance - self.initial_balance) / self.initial_balance * 100
        result.total_trades = len(trades)

        if trades:
            pnls = [t.get("pnl", 0) for t in trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            result.wins = len(wins)
            result.losses = len(losses)
            result.win_rate = len(wins) / len(trades) * 100 if trades else 0
            result.profit_factor = sum(wins) / abs(sum(losses)) if losses else float("inf")
            result.avg_pnl = sum(pnls) / len(pnls)
            result.best_trade = max(pnls)
            result.worst_trade = min(pnls)

            # Max drawdown
            peak = equity_curve[0]
            max_dd = 0.0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak * 100
                if dd > max_dd:
                    max_dd = dd
            result.max_drawdown_pct = max_dd

            # Sharpe ratio
            if len(equity_curve) > 1:
                returns = [
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                    for i in range(1, len(equity_curve))
                ]
                if returns:
                    avg_ret = np.mean(returns)
                    std_ret = np.std(returns)
                    result.sharpe_ratio = (avg_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0

        result.total_commission = commission_total

        # Save results
        self._save_results(symbol, result, trades)

        return result

    @staticmethod
    def _rule_based_signal(df: pd.DataFrame) -> tuple:
        """Fallback rule-based signal when no LSTM model is available."""
        last = df.iloc[-1]
        score = 0.0

        if last["ema_20"] > last["ema_50"]:
            score += 1
        else:
            score -= 1

        if last["rsi"] < 40:
            score += 1
        elif last["rsi"] > 60:
            score -= 1

        if last["macd"] > last["macd_signal"]:
            score += 1
        else:
            score -= 1

        if last["close"] > last["bb_mid"]:
            score += 0.5
        else:
            score -= 0.5

        if score >= 2:
            return "BUY", min(abs(score) / 3.5, 0.85)
        elif score <= -2:
            return "SELL", min(abs(score) / 3.5, 0.85)
        return "HOLD", 0.3

    @staticmethod
    def _calc_sl_tp(signal, entry, atr, pair_params) -> tuple:
        if signal == "BUY":
            sl = entry - atr * pair_params.atr_sl_multiplier
            tp = entry + atr * pair_params.atr_tp_multiplier
        else:
            sl = entry + atr * pair_params.atr_sl_multiplier
            tp = entry - atr * pair_params.atr_tp_multiplier
        return round(sl, 2), round(tp, 2)

    @staticmethod
    def _calc_lot(symbol, sl_pips, balance, pair_params) -> float:
        risk = balance * (pair_params.risk_percent / 100)
        lot = risk / (sl_pips * pair_params.pip_value_per_lot) if sl_pips > 0 else 0.01
        return max(0.01, min(lot, pair_params.max_lot))

    def _save_results(self, symbol, result, trades):
        """Save backtest results to JSON file."""
        filename = f"{symbol.lower()}_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        filepath = os.path.join(self.results_dir, filename)

        with open(filepath, "w") as f:
            json.dump({
                "summary": result.to_dict(),
                "trades": trades,
            }, f, indent=2)

        logger.info(f"Backtest results saved to {filepath}")
