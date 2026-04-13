"""
Exness AI Trading Bot — Main Entry Point (SURVIVAL MODE).
Pure indicator-based strategy. No LSTM dependency.
Orchestrates all layers with a state machine and session-aware scheduling.
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime
from enum import Enum
from typing import Optional

import requests
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
from strategy.signal_generator import SignalGenerator, TradeSignal
from strategy.risk_manager import RiskManager
from strategy.backtester import StrategyBacktester
from monitoring.logger import setup_logger, TradeLogger
from monitoring.notifier import TelegramNotifier
from monitoring.telegram_commands import TelegramKeyboard

# ============================================================================
# State Machine
# ============================================================================

class BotState(Enum):
    """Bot lifecycle states."""
    INITIALIZING = "initializing"
    CONNECTED = "connected"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class BotStateMachine:
    """Manages bot state transitions."""

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
        """Attempt state transition."""
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
# Main Bot (SURVIVAL MODE)
# ============================================================================

class TradingBot:
    """
    Exness AI Trading Bot — SURVIVAL MODE.
    Pure indicator-based strategy with strict risk management.

    Key principles:
    - Trend-following > prediction
    - Survival > greed (0.5% risk per trade)
    - Simple & proven > complex & fragile
    """

    def __init__(self):
        self.config = load_config()
        self.logger = setup_logger(self.config.bot.log_file, "INFO")
        self.trade_log = TradeLogger()
        self.logger = logging.getLogger("ai_bot")

        # State machine
        self.sm = BotStateMachine()

        # Components
        self.broker: Optional[ExnessBroker] = None
        self.collector: Optional[DataCollector] = None
        self.signal_gen: Optional[SignalGenerator] = None
        self.risk: Optional[RiskManager] = None
        self.order_mgr: Optional[OrderManager] = None
        self.portfolio: Optional[Portfolio] = None
        self.notifier: Optional[TelegramNotifier] = None
        self._keyboard: Optional[TelegramKeyboard] = None

        # Filters
        self._news_filter: Optional[NewsFilter] = None

        # Runtime
        self._running = False
        self._cycle_count = 0
        self._last_update_id = 0

        # Mutable params (shared with Telegram)
        self._params = {
            "use_trailing_stop": self.config.bot.use_trailing_stop,
            "tsl_activation": self.config.bot.trailing_activation,
            "tsl_atr_mult": self.config.bot.trailing_atr_mult,
            "risk_percent": self.config.bot.risk_percent,
            "min_confidence": self.config.bot.min_confidence,
            "max_positions": self.config.bot.max_positions,
            "atr_sl_mult": 2.0,
            "atr_tp_mult": 4.0,
            "paused": False,
            "cycle_count": 0,
            "balance": 0.0,
            "daily_dd": 0.0,
            "weekly_dd": 0.0,
            "consecutive_losses": 0,
            "session_name": "Off Hours",
        }

    # ---- Lifecycle ----

    def initialize(self) -> bool:
        """Initialize all components and connect to MT5."""
        self.logger.info("=" * 60)
        self.logger.info("  EXNESS AI TRADING BOT v3.0 — SURVIVAL MODE")
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

        # 3. Initialize signal generator (pure indicators, no LSTM)
        self.signal_gen = SignalGenerator(
            ema200_trend_bias=self.config.bot.ema200_trend_bias,
            min_confidence=self.config.bot.min_confidence,
        )

        # 4. Initialize risk manager
        balance = self.broker.get_account_balance()
        self.risk = RiskManager(
            account_balance=balance,
            risk_percent=self.config.bot.risk_percent,
            max_consecutive_losses=self.config.bot.max_consecutive_losses,
            max_weekly_drawdown_pct=self.config.bot.max_weekly_drawdown_pct,
        )

        # 5. Initialize order manager & portfolio
        self.order_mgr = OrderManager(self.config.bot)
        self.portfolio = Portfolio()
        self.portfolio.refresh()

        # 6. Initialize news + session filter
        self._news_filter = NewsFilter(
            session_filter_enabled=self.config.bot.session_filter_enabled,
            session_start_utc=self.config.bot.session_start_utc,
            session_end_utc=self.config.bot.session_end_utc,
        )

        # 7. Initialize notifier & Telegram keyboard
        self.notifier = TelegramNotifier(
            bot_token=self.config.telegram.bot_token,
            chat_id=self.config.telegram.chat_id,
            enabled=self.config.telegram.enabled,
        )

        if self.config.telegram.enabled and self.config.telegram.bot_token:
            self._keyboard = TelegramKeyboard(
                bot_token=self.config.telegram.bot_token,
                chat_id=self.config.telegram.chat_id,
            )
            self.logger.info("Telegram control panel initialized")

        self.sm.transition(BotState.RUNNING)
        self._running = True

        self.logger.info(f"Bot initialized. Pairs: {get_all_pairs()}")
        self.logger.info("Strategy: Pure indicators (no LSTM)")
        self.logger.info(f"Risk: {self.config.bot.risk_percent}% per trade")
        self.logger.info(
            f"Sessions: {self.config.bot.session_start_utc}:00-"
            f"{self.config.bot.session_end_utc}:00 UTC"
        )
        self.trade_log.log_status("Bot started (SURVIVAL MODE)")

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
        """Pause trading."""
        self.sm.transition(BotState.PAUSED)
        self._params["paused"] = True
        self.logger.warning(f"Bot PAUSED: {reason}")

    def resume(self):
        """Resume trading after pause."""
        self.sm.transition(BotState.RUNNING)
        self._params["paused"] = False
        self.logger.info("Bot RESUMED")

    # ---- Main Loop ----

    def run(self, interval_minutes: int = 15):
        """Main event loop."""
        signal.signal(signal.SIGINT, lambda s, f: self._handle_signal(s))
        signal.signal(signal.SIGTERM, lambda s, f: self._handle_signal(s))

        self.logger.info(f"Starting main loop (interval: {interval_minutes} min)")

        # Show initial Telegram menu
        if self._keyboard:
            self._params["cycle_count"] = 0
            self._params["balance"] = self.broker.get_account_balance() if self.broker else 0
            self._keyboard.show_main_menu(self._params)
            self.logger.info("Telegram control panel sent")

        try:
            while self._running and self.sm.is_active():
                # Poll Telegram buttons
                self._poll_telegram_commands()

                # Check if Telegram paused the bot
                if self._params.get("paused", False) and self.sm.state != BotState.PAUSED:
                    self.pause(reason="Paused via Telegram")
                    time.sleep(60)
                    continue

                if self._params.get("paused", False):
                    time.sleep(60)
                    continue

                if self.sm.state == BotState.PAUSED:
                    time.sleep(60)
                    continue

                self._cycle()
                self._cycle_count += 1

                # Sleep in small increments
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

        # Check session + news blackout
        is_blackout, reason = self._news_filter.check_blackout("XAUUSD")
        if is_blackout:
            self.logger.info(f"FILTER: {reason}")
            if self.sm.state != BotState.PAUSED:
                self.pause(reason=reason)
            return

        # Auto-resume if was paused for session/news and now clear
        if self.sm.state == BotState.PAUSED and not is_blackout:
            self.logger.info("Filter cleared. Resuming trading.")
            self.resume()

        # Refresh portfolio
        self.portfolio.refresh()

        # Update balance & risk tracking
        balance = self.broker.get_account_balance()
        self._params["balance"] = balance
        self.risk.update_balance(balance)
        self.risk.reset_daily_tracking()
        self._params["daily_dd"] = self.risk.daily_drawdown_pct
        self._params["weekly_dd"] = self.risk.weekly_drawdown_pct
        self._params["consecutive_losses"] = self.risk.consecutive_losses
        self._params["session_name"] = self._news_filter.get_session_name()

        # Check risk limits (consecutive losses, daily/weekly DD)
        should_pause, pause_reason = self.risk.should_pause
        if should_pause:
            self.logger.warning(f"RISK LIMIT: {pause_reason}. Pausing.")
            self.notifier.send(f"⚠️ Risk limit hit: {pause_reason}. Bot paused.")
            self.pause(reason=pause_reason)
            return

        for symbol in get_all_pairs():
            self._process_pair(symbol)

        # Portfolio summary
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
        max_pos = self._params.get("max_positions", self.config.bot.max_positions)
        open_pos = self.portfolio.get_positions_for_symbol(symbol)
        if not self.risk.is_trade_allowed(symbol, open_pos, max_pos):
            return

        # 5. Generate signal (pure indicators)
        signal: TradeSignal = self.signal_gen.generate(symbol, df)

        self.trade_log.log_signal(
            symbol, signal.direction, signal.confidence, signal.entry_price
        )

        # Apply dynamic confidence threshold
        effective_conf = self._params.get("min_confidence", pair_params.min_confidence)
        if not signal.is_valid or signal.confidence < effective_conf:
            self.logger.info(
                f"{symbol}: No trade — {signal.direction} "
                f"(score: {signal.confidence:.2f} < {effective_conf:.2f})"
            )
            return

        self.logger.info(
            f"  TSL: {'ON' if self._params.get('use_trailing_stop', True) else 'OFF'} "
            f"(act={self._params.get('tsl_activation', 2.0)}×, "
            f"trail={self._params.get('tsl_atr_mult', 1.0)}×)"
        )

        # 6. Calculate lot size
        entry = signal.entry_price
        sl = signal.stop_loss
        sl_distance = abs(entry - sl)
        lot = self.risk.calculate_lot_size(symbol, sl_distance)

        self.logger.info(
            f"{symbol}: SIGNAL {signal.direction} | "
            f"score={signal.confidence:.2f} | lot={lot} | "
            f"entry={entry} | SL={sl} | TP={signal.take_profit}"
        )
        self.logger.info(f"  Reasons: {'; '.join(signal.reasons)}")

        # 7. Execute order
        result = self.order_mgr.open_order(
            symbol, signal.direction, lot, sl, signal.take_profit
        )

        if result:
            self.trade_log.log_order(
                symbol, result["ticket"], signal.direction,
                lot, result["price"], sl, signal.take_profit,
            )
            self.notifier.notify_signal(
                symbol, signal.direction, signal.confidence,
                entry, sl, signal.take_profit, lot,
            )
            self.portfolio.refresh()
        else:
            self.trade_log.log_error(f"{symbol}: Order execution failed")
            self.notifier.notify_error(f"Failed to execute {symbol} {signal.direction}")

    # ---- Telegram ----

    def _poll_telegram_commands(self):
        """Check for Telegram button presses."""
        if not self._keyboard:
            return

        try:
            url = f"{self._keyboard.api_base}/getUpdates"
            params = {
                "offset": self._last_update_id + 1,
                "timeout": 1,
                "allowed_updates": ["callback_query"],
            }
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                return

            data = resp.json()
            if not data.get("ok") or "result" not in data:
                return

            for update in data["result"]:
                self._last_update_id = update["update_id"]
                callback = update.get("callback_query", {})
                if not callback:
                    continue

                cb_id = callback["id"]
                cb_data = callback.get("data", "")

                # Refresh params
                self._params["cycle_count"] = self._cycle_count
                self._params["balance"] = self.broker.get_account_balance() if self.broker else 0
                self._params["daily_dd"] = self.risk.daily_drawdown_pct if self.risk else 0
                self._params["weekly_dd"] = self.risk.weekly_drawdown_pct if self.risk else 0
                self._params["consecutive_losses"] = self.risk.consecutive_losses if self.risk else 0
                self._params["session_name"] = self._news_filter.get_session_name() if self._news_filter else "N/A"

                self._handle_button(cb_data)
                self._keyboard.answer_callback(cb_id)

        except Exception as e:
            self.logger.debug(f"Telegram button poll error: {e}")

    def _handle_button(self, data: str):
        """Process inline keyboard button press."""
        if not data:
            return

        if data == "toggle_pause":
            self._params["paused"] = not self._params.get("paused", False)
            action = "PAUSED" if self._params["paused"] else "RESUMED"
            self._keyboard.notify_setting_changed("Bot", action)
            if self._params["paused"]:
                self.pause(reason="Paused via Telegram")
            else:
                self.resume()
            self._keyboard.show_main_menu(self._params)
            return

        elif data == "toggle_tsl":
            current = self._params.get("use_trailing_stop", True)
            self._params["use_trailing_stop"] = not current
            status = "ON" if self._params["use_trailing_stop"] else "OFF"
            self._keyboard.notify_setting_changed("Trailing Stop", status)
            self._keyboard.show_main_menu(self._params)
            return

        elif data.startswith("risk_"):
            val = float(data.replace("risk_", ""))
            self._params["risk_percent"] = val
            self._keyboard.notify_setting_changed("Risk/trade", f"{val}%")
            self._keyboard.show_risk_menu(self._params)
            return

        elif data.startswith("conf_"):
            val = float(data.replace("conf_", "")) / 100.0
            self._params["min_confidence"] = val
            self._keyboard.notify_setting_changed("Min Confidence", f"{val*100:.0f}%")
            self._keyboard.show_risk_menu(self._params)
            return

        elif data.startswith("maxpos_"):
            val = int(data.replace("maxpos_", ""))
            self._params["max_positions"] = val
            self._keyboard.notify_setting_changed("Max Positions", str(val))
            self._keyboard.show_risk_menu(self._params)
            return

        elif data.startswith("sl_"):
            val = float(data.replace("sl_", ""))
            self._params["atr_sl_mult"] = val
            self._keyboard.notify_setting_changed("ATR SL", f"{val}×")
            self._keyboard.show_sltp_menu(self._params)
            return

        elif data.startswith("tp_"):
            val = float(data.replace("tp_", ""))
            self._params["atr_tp_mult"] = val
            self._keyboard.notify_setting_changed("ATR TP", f"{val}×")
            self._keyboard.show_sltp_menu(self._params)
            return

        elif data.startswith("tsl_act_"):
            val = float(data.replace("tsl_act_", ""))
            self._params["tsl_activation"] = val
            self._keyboard.notify_setting_changed("TSL Activation", f"{val}× ATR")
            self._keyboard.show_tsl_menu(self._params)
            return

        elif data.startswith("tsl_trail_"):
            val = float(data.replace("tsl_trail_", ""))
            self._params["tsl_atr_mult"] = val
            self._keyboard.notify_setting_changed("TSL Trail", f"{val}× ATR")
            self._keyboard.show_tsl_menu(self._params)
            return

        elif data == "back_main":
            self._keyboard.show_main_menu(self._params)
        elif data == "menu_risk":
            self._keyboard.show_risk_menu(self._params)
        elif data == "menu_sltp":
            self._keyboard.show_sltp_menu(self._params)
        elif data == "menu_tsl":
            self._keyboard.show_tsl_menu(self._params)
        elif data == "cmd_status":
            self._keyboard.show_status(self._params)

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
            initial_balance=self.config.bot.risk_percent * 1000,
            commission_per_lot=7.0,
        )
        result = bt.run(symbol, df)
        if result:
            print(result.summary())
        return result

    def status(self):
        """Print current bot status."""
        print(f"\n{'='*40}")
        print(f"BOT STATUS (SURVIVAL MODE)")
        print(f"{'='*40}")
        print(f"State: {self.sm.state.value}")
        print(f"Strategy: Pure indicators (no LSTM)")
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

        if self.risk:
            print(f"Consecutive losses: {self.risk.consecutive_losses}")
            print(f"Daily DD: {self.risk.daily_drawdown_pct:.1f}%")
            print(f"Weekly DD: {self.risk.weekly_drawdown_pct:.1f}%")


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Exness AI Trading Bot — SURVIVAL MODE"
    )
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
        import pandas as pd
        data_file = f"data/historical/{args.symbol}_H1.csv"
        if os.path.exists(data_file):
            df = pd.read_csv(data_file, index_col="time", parse_dates=True)
            bot.run_backtest(args.symbol, df)
        else:
            print(f"No historical data found at {data_file}")
            print("Attempting yfinance fallback...")
            try:
                import yfinance as yf
                yf_map = {"XAUUSD": "GC=F", "BTCUSD": "BTC-USD"}
                ticker = yf.Ticker(yf_map.get(args.symbol, args.symbol))
                df = ticker.history(period="2y", interval="1h")
                df.index.name = "time"
                if not df.empty:
                    os.makedirs("data/historical", exist_ok=True)
                    df.to_csv(data_file)
                    print(f"Data saved. Run again.")
                else:
                    print(f"Failed to fetch data.")
            except ImportError:
                print("Install yfinance: pip install yfinance")
            except Exception as e:
                print(f"Error: {e}")

    elif args.mode == "train":
        # Train mode — still fetches data and saves for backtest
        # (LSTM training removed — pure indicator strategy)
        if not bot.initialize():
            sys.exit(1)

        from data.collector import DataCollector
        collector = DataCollector()

        for symbol in get_all_pairs():
            pair_params = get_pair_params(symbol)
            df = collector.get_ohlcv(symbol, pair_params.timeframe, bars=2000)
            if df is not None:
                from data.indicators import add_indicators
                df = add_indicators(df)
                os.makedirs("data/historical", exist_ok=True)
                df.to_csv(f"data/historical/{symbol}_{pair_params.timeframe}.csv")
                print(f"Data saved: data/historical/{symbol}_{pair_params.timeframe}.csv")

        bot.shutdown()
        print("\nNote: LSTM training removed. Strategy uses pure indicators.")
        print("Run `python backtest_xauusd.py` to test the strategy.")


if __name__ == "__main__":
    main()
