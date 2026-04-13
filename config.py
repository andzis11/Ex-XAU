"""
Configuration settings for the Exness AI Trading Bot.
Fill in your API keys and credentials before running.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Symbol(str, Enum):
    XAUUSD = "XAUUSD"
    BTCUSD = "BTCUSD"


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


@dataclass
class ExnessConfig:
    """Exness / MetaTrader connection settings."""
    # Option 1: Direct MT5 (Windows VPS)
    mt5_login: str = ""  # Your Exness account number
    mt5_password: str = ""
    mt5_server: str = ""  # e.g. "Exness-MT5Trial14"

    # Option 2: MetaAPI (cloud-based)
    metaapi_token: str = ""
    metaapi_account_id: str = ""

    # Fallback to MetaAPI if True
    use_metaapi: bool = True


@dataclass
class TradingConfig:
    """Trading parameters."""
    symbols: List[Symbol] = field(default_factory=lambda: [Symbol.XAUUSD, Symbol.BTCUSD])
    timeframe: Timeframe = Timeframe.H1

    # Risk
    risk_per_trade_pct: float = 1.0       # % of equity per trade
    max_daily_drawdown_pct: float = 5.0    # Stop trading if daily loss > 5%
    max_open_positions: int = 3

    # Execution
    slippage_tolerance: int = 10           # In points
    retry_attempts: int = 3
    retry_delay_seconds: float = 2.0

    # Signal threshold
    min_confluence_score: float = 0.70     # 70% minimum to enter trade


@dataclass
class RiskConfig:
    """Risk management parameters per symbol."""
    # XAU/USD
    xau_atr_sl_multiplier: float = 1.5     # SL = ATR × multiplier
    xau_atr_tp_multiplier: float = 2.0     # TP = ATR × multiplier

    # BTC/USD
    btc_atr_sl_multiplier: float = 2.0     # Wider SL for BTC
    btc_atr_tp_multiplier: float = 3.0

    # General
    kelly_fraction: float = 0.25           # Use 25% of Kelly for safety


@dataclass
class AIConfig:
    """AI / LLM settings."""
    # Anthropic Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-sonnet-20240229"

    # ML Model paths
    xau_model_path: str = "models/xau_model.pkl"
    btc_model_path: str = "models/btc_model.pkl"

    # Technical indicators
    ema_periods: tuple = (20, 50, 200)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0


@dataclass
class TelegramConfig:
    """Telegram notification settings."""
    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = False


@dataclass
class NewsConfig:
    """News / sentiment data settings."""
    forex_factory_url: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    high_impact_only: bool = True


@dataclass
class BacktestConfig:
    """Backtesting settings."""
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_balance: float = 10000.0
    commission_per_lot: float = 7.0       # $7 per round turn lot
    data_dir: str = "data/historical"
    results_dir: str = "results/backtest"


@dataclass
class DatabaseConfig:
    """Database settings for trade journal."""
    db_type: str = "sqlite"               # "sqlite" or "postgresql"
    sqlite_path: str = "data/trading_journal.db"
    postgresql_url: str = ""


@dataclass
class AppConfig:
    """Master configuration."""
    exness: ExnessConfig = field(default_factory=ExnessConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)

    # General
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"
    check_interval_seconds: int = 60       # Seconds between market checks


def load_config() -> AppConfig:
    """Load configuration, overriding with environment variables where set."""
    config = AppConfig()

    # Override from environment variables
    if os.getenv("EXNESS_LOGIN"):
        config.exness.mt5_login = os.getenv("EXNESS_LOGIN")
    if os.getenv("EXNESS_PASSWORD"):
        config.exness.mt5_password = os.getenv("EXNESS_PASSWORD")
    if os.getenv("EXNESS_SERVER"):
        config.exness.mt5_server = os.getenv("EXNESS_SERVER")
    if os.getenv("METAAPI_TOKEN"):
        config.exness.metaapi_token = os.getenv("METAAPI_TOKEN")
    if os.getenv("METAAPI_ACCOUNT_ID"):
        config.exness.metaapi_account_id = os.getenv("METAAPI_ACCOUNT_ID")
    if os.getenv("ANTHROPIC_API_KEY"):
        config.ai.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        config.telegram.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        config.telegram.enabled = True
    if os.getenv("TELEGRAM_CHAT_ID"):
        config.telegram.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    return config
