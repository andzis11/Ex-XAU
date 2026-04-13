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
    """Runtime bot parameters — SURVIVAL MODE defaults."""
    pairs: list = field(default_factory=lambda: ["XAUUSD", "BTCUSD"])
    timeframe: str = os.getenv("TIMEFRAME", "M15")         # M15 / H1 / H4
    check_interval_minutes: int = int(os.getenv("CHECK_INTERVAL", "15"))

    # Risk management (SURVIVAL MODE)
    risk_percent: float = 0.5                              # 0.5% per trade
    max_positions: int = 2                                  # Max 2 open per pair
    max_daily_drawdown_pct: float = 3.0                     # Stop at 3% daily loss
    max_weekly_drawdown_pct: float = 8.0                    # Stop at 8% weekly loss
    max_consecutive_losses: int = 3                         # Pause after 3 losses

    # Session filter (only trade volatile hours)
    session_filter_enabled: bool = True                     # Only London/NY overlap
    session_start_utc: int = 7                              # 07:00 UTC (London open)
    session_end_utc: int = 22                               # 22:00 UTC (NY close)

    # Signal generation (pure indicators, no LSTM)
    min_confidence: float = 0.40                            # Lower for pure indicators
    ema200_trend_bias: float = 0.30                         # Strong trend filter

    # Trailing stop
    use_trailing_stop: bool = True
    trailing_atr_mult: float = 1.0
    trailing_activation: float = 2.0

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
