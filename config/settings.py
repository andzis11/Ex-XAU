"""
Bot configuration — API keys, credentials, and runtime parameters.
Load from .env or set defaults here.
"""

import os
from dataclasses import dataclass, field


@dataclass
class BrokerConfig:
    """Exness MT5 connection settings."""
    login: int = int(os.getenv("EXNESS_LOGIN", "0"))
    password: str = os.getenv("EXNESS_PASSWORD", "")
    server: str = os.getenv("EXNESS_SERVER", "Exness-MT5Real8")
    use_demo: bool = os.getenv("USE_DEMO", "false").lower() == "true"


@dataclass
class TelegramConfig:
    """Telegram notification settings."""
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    enabled: bool = bool(os.getenv("TELEGRAM_BOT_TOKEN"))


@dataclass
class BotConfig:
    """Runtime bot parameters — SCALPING MODE defaults."""
    pairs: list = field(default_factory=lambda: ["XAUUSD", "BTCUSD"])
    timeframe: str = os.getenv("TIMEFRAME", "M5")          # M5 for scalping
    check_interval_minutes: int = int(os.getenv("CHECK_INTERVAL", "5"))

    # Risk management (SCALPING MODE)
    risk_percent: float = 1.0                              # 1% per trade (SL is tighter)
    max_positions: int = 3                                  # Max 3 open per pair
    max_daily_drawdown_pct: float = 5.0                     # Stop at 5% daily loss
    max_weekly_drawdown_pct: float = 15.0                   # Stop at 15% weekly loss
    max_consecutive_losses: int = 5                         # Pause after 5 losses

    # Session filter — SCALPING: London-NY overlap only (highest volatility)
    session_filter_enabled: bool = True
    session_start_utc: int = 12                             # 12:00 UTC (London-NY overlap)
    session_end_utc: int = 16                               # 16:00 UTC (NY morning)

    # Signal generation (pure indicators, scalping-optimized)
    min_confidence: float = 0.50                            # Higher quality entries
    ema200_trend_bias: float = 0.40                         # Stronger trend filter

    # Trailing stop (aggressive profit lock)
    use_trailing_stop: bool = True
    trailing_atr_mult: float = 0.5                          # Tight trail
    trailing_activation: float = 0.8                        # Activate early

    # Scalping: no overnight positions
    close_all_on_session_end: bool = True

    # Misc
    magic_number: int = 20240101
    deviation: int = 20
    db_path: str = "data/trading_journal.db"
    log_file: str = "logs/bot.log"
    model_dir: str = "models/saved_models"


@dataclass
class AppConfig:
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    bot: BotConfig = field(default_factory=BotConfig)


def load_config() -> AppConfig:
    return AppConfig()
