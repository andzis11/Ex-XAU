"""
Layer 6 — Logging & Backtesting: Strategy backtesting engine.
Uses backtrader to test strategies on historical data.
"""

import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from config import AppConfig, Symbol

logger = logging.getLogger(__name__)


class BacktestResult:
    """Container for backtest results."""

    def __init__(self):
        self.initial_balance: float = 0
        self.final_balance: float = 0
        self.total_return_pct: float = 0
        self.max_drawdown_pct: float = 0
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.win_rate: float = 0
        self.profit_factor: float = 0
        self.sharpe_ratio: float = 0
        self.avg_trade_pnl: float = 0
        self.best_trade: float = 0
        self.worst_trade: float = 0
        self.total_commission: float = 0

    def to_dict(self) -> dict:
        return {
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(self.final_balance, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 1),
            "profit_factor": round(self.profit_factor, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "avg_trade_pnl": round(self.avg_trade_pnl, 2),
            "best_trade": round(self.best_trade, 2),
            "worst_trade": round(self.worst_trade, 2),
            "total_commission": round(self.total_commission, 2),
        }

    def summary(self) -> str:
        d = self.to_dict()
        return (
            f"\n{'='*50}\n"
            f"BACKTEST RESULTS\n"
            f"{'='*50}\n"
            f"Initial Balance:  ${d['initial_balance']:,.2f}\n"
            f"Final Balance:    ${d['final_balance']:,.2f}\n"
            f"Total Return:     {d['total_return_pct']:.2f}%\n"
            f"Max Drawdown:     {d['max_drawdown_pct']:.2f}%\n"
            f"{'-'*50}\n"
            f"Total Trades:     {d['total_trades']}\n"
            f"Win Rate:         {d['win_rate']:.1f}%\n"
            f"Profit Factor:    {d['profit_factor']:.2f}\n"
            f"Sharpe Ratio:     {d['sharpe_ratio']:.2f}\n"
            f"{'-'*50}\n"
            f"Avg Trade P&L:    ${d['avg_trade_pnl']:.2f}\n"
            f"Best Trade:       ${d['best_trade']:.2f}\n"
            f"Worst Trade:      ${d['worst_trade']:.2f}\n"
            f"Total Commission: ${d['total_commission']:.2f}\n"
            f"{'='*50}\n"
        )


class StrategyBacktester:
    """
    Layer 6 — Backtesting Engine.
    Runs historical backtests using the bot's strategy logic.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.data_dir = config.backtest.data_dir
        self.results_dir = config.backtest.results_dir

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)

    def load_historical_data(
        self,
        symbol: Symbol,
        start_date: str,
        end_date: str,
        timeframe: str = "1h",
    ) -> Optional[pd.DataFrame]:
        """
        Load historical OHLCV data from disk or download if needed.

        Args:
            symbol: Trading symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timeframe: Pandas frequency string (1h, 4h, 1d)

        Returns:
            OHLCV DataFrame
        """
        filepath = os.path.join(self.data_dir, f"{symbol.value}_{timeframe}.csv")

        if os.path.exists(filepath):
            logger.info(f"Loading historical data from {filepath}")
            df = pd.read_csv(filepath, index_col="time", parse_dates=True)
        else:
            logger.warning(f"No historical data found at {filepath}")
            return None

        # Filter by date range
        df = df.loc[start_date:end_date]

        if df.empty:
            logger.warning(f"No data in range {start_date} to {end_date}")
            return None

        logger.info(f"Loaded {len(df)} candles for {symbol.value}")
        return df

    def save_historical_data(
        self,
        symbol: Symbol,
        df: pd.DataFrame,
        timeframe: str = "1h",
    ):
        """Save OHLCV data to CSV for future backtests."""
        filepath = os.path.join(self.data_dir, f"{symbol.value}_{timeframe}.csv")
        df.to_csv(filepath)
        logger.info(f"Saved {len(df)} candles to {filepath}")

    def run_backtest(
        self,
        df: pd.DataFrame,
        symbol: Symbol,
        initial_balance: float = 10000,
    ) -> BacktestResult:
        """
        Run backtest on historical data using the bot's strategy.

        This is a simplified backtest that simulates the signal generation
        and trade execution logic without the full bot infrastructure.

        Args:
            df: Historical OHLCV DataFrame
            symbol: Trading symbol
            initial_balance: Starting capital

        Returns:
            BacktestResult with performance metrics
        """
        from analysis.technical import TechnicalAnalyzer

        logger.info(f"Running backtest on {len(df)} candles for {symbol.value}...")

        analyzer = TechnicalAnalyzer(self.config)
        result = BacktestResult()
        result.initial_balance = initial_balance

        balance = initial_balance
        equity_curve = [balance]
        trades = []
        commission_per_trade = self.config.backtest.commission_per_lot

        # Walk through data
        min_lookback = 200
        for i in range(min_lookback, len(df)):
            lookback_df = df.iloc[:i]

            # Run technical analysis
            signals = analyzer.analyze(lookback_df, symbol)
            if not signals:
                continue

            current_price = float(df["close"].iloc[i])
            atr = signals.atr_value

            # Simple strategy: follow composite score
            if signals.composite_score > 0.4:
                direction = "BUY"
                entry = current_price
                sl = entry - atr * self.config.risk.xau_atr_sl_multiplier
                tp = entry + atr * self.config.risk.xau_atr_tp_multiplier
            elif signals.composite_score < -0.4:
                direction = "SELL"
                entry = current_price
                sl = entry + atr * self.config.risk.xau_atr_sl_multiplier
                tp = entry - atr * self.config.risk.xau_atr_tp_multiplier
            else:
                continue

            # Simulate position sizing (1% risk)
            risk_amount = balance * 0.01
            sl_distance = abs(entry - sl)
            if sl_distance == 0:
                continue

            tick_value = 100.0 if symbol == Symbol.XAUUSD else 1.0
            volume = risk_amount / (sl_distance * tick_value)
            volume = max(0.01, min(volume, 10.0))  # Clamp

            commission = volume * commission_per_trade

            # Look ahead to find exit (simplified: check next 20 candles)
            exit_price = None
            exit_reason = "timeout"

            for j in range(i + 1, min(i + 20, len(df))):
                high = float(df["high"].iloc[j])
                low = float(df["low"].iloc[j])

                if direction == "BUY":
                    if low <= sl:
                        exit_price = sl
                        exit_reason = "stop_loss"
                        break
                    elif high >= tp:
                        exit_price = tp
                        exit_reason = "take_profit"
                        break
                else:  # SELL
                    if high >= sl:
                        exit_price = sl
                        exit_reason = "stop_loss"
                        break
                    elif low <= tp:
                        exit_price = tp
                        exit_reason = "take_profit"
                        break

            if exit_price is None:
                # Close at end of lookback
                exit_price = float(df["close"].iloc[min(i + 19, len(df) - 1)])

            # Calculate P&L
            if direction == "BUY":
                pnl = (exit_price - entry) * volume * tick_value
            else:
                pnl = (entry - exit_price) * volume * tick_value

            net_pnl = pnl - commission
            balance += net_pnl
            equity_curve.append(balance)

            trades.append({
                "entry": entry,
                "exit": exit_price,
                "direction": direction,
                "pnl": net_pnl,
                "reason": exit_reason,
                "volume": volume,
            })

        # Calculate metrics
        result.final_balance = balance
        result.total_return_pct = (balance - initial_balance) / initial_balance * 100
        result.total_trades = len(trades)

        if trades:
            pnls = [t["pnl"] for t in trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            result.winning_trades = len(wins)
            result.losing_trades = len(losses)
            result.win_rate = len(wins) / len(trades) * 100 if trades else 0
            result.profit_factor = (
                sum(wins) / abs(sum(losses)) if losses else float('inf')
            )
            result.avg_trade_pnl = sum(pnls) / len(pnls)
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

            # Simple Sharpe (annualized)
            if len(equity_curve) > 1:
                returns = [
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                    for i in range(1, len(equity_curve))
                ]
                if returns:
                    import numpy as np
                    avg_return = np.mean(returns)
                    std_return = np.std(returns)
                    result.sharpe_ratio = (
                        (avg_return / std_return) * (252 ** 0.5)
                        if std_return > 0 else 0
                    )

        # Save results
        self._save_results(result, symbol, trades)

        return result

    def _save_results(
        self,
        result: BacktestResult,
        symbol: Symbol,
        trades: list,
    ):
        """Save backtest results to file."""
        import json

        results_file = os.path.join(
            self.results_dir,
            f"backtest_{symbol.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )

        output = {
            "summary": result.to_dict(),
            "trades": trades,
        }

        with open(results_file, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Backtest results saved to {results_file}")
