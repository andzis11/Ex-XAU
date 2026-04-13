"""
Exness AI Trading Bot — Main Entry Point.
Orchestrates all layers with a state machine and 15-minute schedule.
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5
import numpy as np

# Project imports
from config.settings import load_config, BotConfig
from config.pairs import get_pair_params, get_all_pairs
from execution.broker import ExnessBroker
from execution.order_manager import OrderManager
from execution.portfolio import Portfolio
from data.collector import DataCollector
from data.news_filter import NewsFilter
from models.trainer import LSTMTrainer
from models.predictor import LSTMPredictor
from strategy.signal_generator import SignalGenerator, TradeSignal
from strategy.risk_manager import RiskManager
from strategy.backtester import StrategyBacktester
from monitoring.logger import setup_logger, TradeLogger
from monitoring.notifier import TelegramNotifier

# ============================================================================
# State Machine
# ============================================================================

class BotState(Enum):
    """Bot lifecycle states."""
    INITIALIZING = "initializing"
    CONNECTED = "connected"
    RUNNING = "running"
    PAUSED = "paused"         # Paused due to news/error
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class BotStateMachine:
    """
    Manages bot state transitions.

    State diagram:
        INITIALIZING → CONNECTED → RUNNING ↔ PAUSED
                                      ↓
                                   STOPPING → STOPPED
                                      ↓
                                    ERROR → STOPPED
    """

    VALID_TRANSITIONS = {
        BotState.INITIALIZING: {BotState.CONNECTED, BotState.ERROR},
        BotState.CONNECTED: {BotState.RUNNING, BotState.STOPPING, BotState.ERROR},
        BotState.RUNNING: {BotState.PAUSED, BotState.STOPPING, BotState.ERROR},
        BotState.PAUSED: {BotState.RUNNING, BotState.STOPPING, BotState.ERROR},
        BotState.STOPPING: {BotState.STOPPED},
        BotState.ERROR: {BotState.STOPPED},
        BotState.STOPPED: set(),
    }

    def __init__(self):
        self._state = BotState.INITIALIZING

    @property
    def state(self) -> BotState:
        return self._state

    def transition(self, new_state: BotState) -> bool:
        """
        Attempt state transition.

        Returns:
            True if transition was valid and executed
        """
        allowed = self.VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            logging.getLogger("ai_bot").warning(
                f"Invalid transition: {self._state.value} → {new_state.value}"
            )
            return False

        old = self._state
        self._state = new_state
        logging.getLogger("ai_bot").info(f"State: {old.value} → {new_state.value}")
        return True

    def is_running(self) -> bool:
        return self._state in (BotState.RUNNING, BotState.PAUSED)

    def is_active(self) -> bool:
        return self._state not in (BotState.STOPPED, BotState.ERROR)


# ============================================================================
# Main Bot
# ============================================================================

class TradingBot:
    """
    Exness AI Trading Bot.

    Flow per cycle (every 15 minutes):
        1. Refresh portfolio & account
        2. For each pair (XAUUSD, BTCUSD):
            a. Fetch OHLCV + indicators
            b. LSTM prediction
            c. Signal generation with indicator confirmation
            d. Risk check (spread, positions, lot sizing)
            e. Execute order
        3. Log & notify
    """

    def __init__(self):
        # Config
        self.config = load_config()
        self.logger = setup_logger(self.config.bot.log_file, "INFO")
        self.trade_log = TradeLogger()
        self.logger = logging.getLogger("ai_bot")

        # State machine
        self.sm = BotStateMachine()

        # Components
        self.broker: Optional[ExnessBroker] = None
        self.collector: Optional[DataCollector] = None
        self.predictor: Optional[LSTMPredictor] = None
        self.signal_gen: Optional[SignalGenerator] = None
        self.risk: Optional[RiskManager] = None
        self.order_mgr: Optional[OrderManager] = None
        self.portfolio: Optional[Portfolio] = None
        self.notifier: Optional[TelegramNotifier] = None

        # Runtime
        self._running = False
        self._cycle_count = 0
        self._news_filter = NewsFilter()

    # ---- Lifecycle ----

    def initialize(self) -> bool:
        """Initialize all components and connect to MT5."""
        self.logger.info("=" * 60)
        self.logger.info("  EXNESS AI TRADING BOT v2.0")
        self.logger.info("=" * 60)

        # 1. Connect to broker
        self.broker = ExnessBroker(self.config.broker)
        if not self.broker.connect():
            self.logger.error("Failed to connect to Exness. Exiting.")
            self.sm.transition(BotState.ERROR)
            return False

        self.sm.transition(BotState.CONNECTED)

        # 2. Initialize data collector
        self.collector = DataCollector()

        # 3. Load LSTM models
        trainer = LSTMTrainer(model_dir=self.config.bot.model_dir)
        loaded = trainer.load_all_models()
        self.logger.info(f"Loaded {loaded} LSTM model(s)")

        # Hard stop if no models loaded — bot cannot trade without predictions
        if loaded == 0:
            self.logger.error(
                "CRITICAL: No LSTM models loaded! "
                "Run `python main.py train` first to train models. Exiting."
            )
            self.sm.transition(BotState.ERROR)
            return False

        self.predictor = LSTMPredictor()
        for symbol in get_all_pairs():
            model = trainer.get_model(symbol)
            if model:
                self.predictor.load_model(symbol, model)

        # 4. Initialize signal generator
        self.signal_gen = SignalGenerator(self.predictor)

        # 5. Initialize risk manager
        balance = self.broker.get_account_balance()
        self.risk = RiskManager(balance, self.config.bot.risk_percent)

        # 6. Initialize order manager & portfolio
        self.order_mgr = OrderManager(self.config.bot)
        self.portfolio = Portfolio()
        self.portfolio.refresh()

        # 7. Initialize notifier
        self.notifier = TelegramNotifier(
            bot_token=self.config.telegram.bot_token,
            chat_id=self.config.telegram.chat_id,
            enabled=self.config.telegram.enabled,
        )

        self.sm.transition(BotState.RUNNING)
        self._running = True

        self.logger.info(f"Bot initialized. Pairs: {get_all_pairs()}")
        self.trade_log.log_status("Bot started successfully")

        # Send notification
        self.notifier.notify_bot_started(get_all_pairs())

        return True

    def shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Shutting down...")
        self.sm.transition(BotState.STOPPING)
        self._running = False

        if self.broker:
            self.broker.disconnect()

        self.notifier.notify_bot_stopped()
        self.sm.transition(BotState.STOPPED)
        self.logger.info("Bot stopped.")

    def pause(self, reason: str = ""):
        """Pause trading (e.g., during news)."""
        self.sm.transition(BotState.PAUSED)
        self.logger.warning(f"Bot PAUSED: {reason}")

    def resume(self):
        """Resume trading after pause."""
        self.sm.transition(BotState.RUNNING)
        self.logger.info("Bot RESUMED")

    # ---- Main Loop ----

    def run(self, interval_minutes: int = 15):
        """
        Main event loop. Runs every N minutes.

        Args:
            interval_minutes: Seconds between cycles
        """
        # Register signal handlers
        signal.signal(signal.SIGINT, lambda s, f: self._handle_signal(s))
        signal.signal(signal.SIGTERM, lambda s, f: self._handle_signal(s))

        self.logger.info(f"Starting main loop (interval: {interval_minutes} min)")

        try:
            while self._running and self.sm.is_active():
                if self.sm.state == BotState.PAUSED:
                    time.sleep(60)  # Check every minute if we should resume
                    continue

                self._cycle()
                self._cycle_count += 1

                # Sleep in small increments for responsive shutdown
                for _ in range(interval_minutes * 60):
                    if not self._running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def _cycle(self):
        """Single cycle: process all pairs."""
        self.logger.info(f"\n{'='*50}")
        self.logger.info(f"  Cycle #{self._cycle_count} | {datetime.now().isoformat()}")
        self.logger.info(f"{'='*50}")

        # Check news blackout before trading
        is_blackout, reason = self._news_filter.check_blackout("XAUUSD")
        if is_blackout:
            self.logger.warning(f"NEWS BLACKOUT: {reason}")
            if self.sm.state != BotState.PAUSED:
                self.pause(reason=reason)
            return

        # Auto-resume if was paused for news and blackout ended
        if self.sm.state == BotState.PAUSED and not is_blackout:
            self.logger.info("News blackout ended. Resuming trading.")
            self.resume()

        # Refresh portfolio
        self.portfolio.refresh()

        # Update balance without resetting RiskManager state
        balance = self.broker.get_account_balance()
        self.risk.update_balance(balance)
        self.risk.reset_daily_tracking()

        # Check daily drawdown limit
        if self.risk.daily_drawdown_pct >= self.config.bot.max_daily_drawdown_pct:
            self.logger.warning(
                f"Daily drawdown {self.risk.daily_drawdown_pct:.1f}% "
                f"exceeds limit {self.config.bot.max_daily_drawdown_pct}%. Pausing."
            )
            self.notifier.notify_daily_drawdown(self.risk.daily_drawdown_pct)
            self.pause(reason=f"Daily DD {self.risk.daily_drawdown_pct:.1f}%")
            return

        for symbol in get_all_pairs():
            self._process_pair(symbol)

        # Log portfolio summary
        summary = self.portfolio.summary()
        self.logger.info(f"Portfolio: {summary['total_positions']} positions | "
                        f"PnL: ${summary['total_pnl']:.2f}")

    def _process_pair(self, symbol: str):
        """Process a single trading pair through the full pipeline."""
        self.logger.info(f"\n--- {symbol} ---")

        pair_params = get_pair_params(symbol)

        # 1. Fetch data + indicators
        df = self.collector.get_indicators(symbol, pair_params.timeframe, bars=500)
        if df is None or len(df) < 60:
            self.logger.warning(f"{symbol}: Insufficient data. Skipping.")
            return

        # 2. Get current tick
        tick = self.collector.get_tick(symbol)
        if tick is None:
            self.logger.warning(f"{symbol}: Cannot get tick. Skipping.")
            return

        # 3. Check spread
        if not self.risk.check_spread(symbol, tick):
            self.notifier.notify_spread_warning(symbol, tick["spread"])
            return

        # 4. Check position limits
        open_pos = self.portfolio.get_positions_for_symbol(symbol)
        if not self.risk.is_trade_allowed(symbol, open_pos, self.config.bot.max_positions):
            return

        # 5. Generate signal
        signal: TradeSignal = self.signal_gen.generate(symbol, df)

        self.trade_log.log_signal(
            symbol, signal.direction, signal.confidence, signal.entry_price
        )

        if not signal.is_valid:
            self.logger.info(
                f"{symbol}: No trade — {signal.direction} "
                f"(confidence: {signal.confidence:.0%})"
            )
            return

        # 6. Calculate lot size
        entry = signal.entry_price
        sl = signal.stop_loss

        # Calculate actual pip distance (price difference)
        sl_pips = abs(entry - sl)
        lot = self.risk.calculate_lot_size(symbol, sl_pips)

        self.logger.info(
            f"{symbol}: SIGNAL {signal.direction} | "
            f"conf={signal.confidence:.0%} | lot={lot} | "
            f"entry={entry} | SL={sl} | TP={signal.take_profit}"
        )
        self.logger.info(f"  Reasons: {'; '.join(signal.reasons)}")

        # 7. Execute order
        result = self.order_mgr.open_order(symbol, signal.direction, lot, sl, signal.take_profit)

        if result:
            self.trade_log.log_order(
                symbol, result["ticket"], signal.direction,
                lot, result["price"], sl, signal.take_profit,
            )
            self.notifier.notify_signal(
                symbol, signal.direction, signal.confidence,
                entry, sl, signal.take_profit, lot,
            )

            # Refresh portfolio
            self.portfolio.refresh()
        else:
            self.trade_log.log_error(f"{symbol}: Order execution failed")
            self.notifier.notify_error(f"Failed to execute {symbol} {signal.direction}")

    def _handle_signal(self, signum):
        """Handle OS signals for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received {sig_name}. Shutting down...")
        self._running = False

    # ---- Utilities ----

    def run_backtest(self, symbol: str, df):
        """Run a backtest for a symbol."""
        self.logger.info(f"Running backtest for {symbol}...")
        bt = StrategyBacktester(
            initial_balance=self.config.bot.risk_percent * 1000,  # Scale from config
            commission_per_lot=7.0,
        )
        result = bt.run(symbol, df)
        if result:
            print(result.summary())
        return result

    def status(self):
        """Print current bot status."""
        print(f"\n{'='*40}")
        print(f"BOT STATUS")
        print(f"{'='*40}")
        print(f"State: {self.sm.state.value}")
        print(f"Cycle count: {self._cycle_count}")

        if self.broker and self.broker.connected:
            info = self.broker.get_account_info()
            print(f"Balance: ${info.get('balance', 0):.2f}")
            print(f"Equity: ${info.get('equity', 0):.2f}")
            print(f"Margin: ${info.get('margin', 0):.2f}")

        if self.portfolio:
            summary = self.portfolio.summary()
            print(f"Open positions: {summary['total_positions']}")
            print(f"Total PnL: ${summary['total_pnl']:.2f}")


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Exness AI Trading Bot")
    parser.add_argument(
        "mode",
        choices=["live", "backtest", "status", "train"],
        default="live",
        nargs="?",
        help="Bot mode",
    )
    parser.add_argument(
        "--symbol",
        choices=["XAUUSD", "BTCUSD"],
        default="XAUUSD",
        help="Symbol for backtest/train",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Check interval in minutes (default: 15)",
    )

    args = parser.parse_args()
    bot = TradingBot()

    if args.mode == "live":
        if bot.initialize():
            bot.run(interval_minutes=args.interval)

    elif args.mode == "status":
        bot.initialize()
        bot.status()
        bot.shutdown()

    elif args.mode == "backtest":
        # Backtest mode — loads data from CSV or falls back to yfinance
        import pandas as pd
        data_file = f"data/historical/{args.symbol}_H1.csv"

        if os.path.exists(data_file):
            df = pd.read_csv(data_file, index_col="time", parse_dates=True)
            bot.run_backtest(args.symbol, df)
        else:
            print(f"No historical data found at {data_file}")
            print("Attempting to fetch data via yfinance fallback...")

            try:
                import yfinance as yf
                # Map symbols to yfinance tickers
                yf_map = {"XAUUSD": "GC=F", "BTCUSD": "BTC-USD"}
                yf_ticker = yf_map.get(args.symbol, args.symbol)

                ticker = yf.Ticker(yf_ticker)
                df = ticker.history(period="2y", interval="1h")
                df.index.name = "time"

                if not df.empty:
                    os.makedirs("data/historical", exist_ok=True)
                    df.to_csv(data_file)
                    print(f"Data saved to {data_file}. Run backtest again.")
                else:
                    print(f"Failed to fetch data for {yf_ticker}")
            except ImportError:
                print("yfinance not installed. Install with: pip install yfinance")
                print("Or run `python main.py train` first to download data.")
            except Exception as e:
                print(f"Error fetching data: {e}")
                print("Run `python main.py train` first to download data.")

    elif args.mode == "train":
        # Train mode — fetches data and trains LSTM models
        if not bot.initialize():
            sys.exit(1)

        from data.collector import DataCollector
        collector = DataCollector()
        trainer = LSTMTrainer(model_dir=bot.config.bot.model_dir)

        for symbol in get_all_pairs():
            pair_params = get_pair_params(symbol)
            df = collector.get_ohlcv(symbol, pair_params.timeframe, bars=2000)
            if df is not None:
                from data.indicators import add_indicators
                df = add_indicators(df)

                # Save for backtesting
                os.makedirs("data/historical", exist_ok=True)
                df.to_csv(f"data/historical/{symbol}_{pair_params.timeframe}.csv")

                trainer.train(symbol, df, epochs=50)

        bot.shutdown()


if __name__ == "__main__":
    main()
