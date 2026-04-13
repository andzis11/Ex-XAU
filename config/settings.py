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
    """Runtime bot parameters."""
    pairs: list = field(default_factory=lambda: ["XAUUSD", "BTCUSD"])
    timeframe: str = os.getenv("TIMEFRAME", "M15")         # M15 / H1 / H4
    check_interval_minutes: int = int(os.getenv("CHECK_INTERVAL", "15"))
    min_confidence: float = 0.70                            # Min 70% for entry
    risk_percent: float = 1.0                               # Risk per trade
    max_positions: int = 3                                  # Max open positions per pair
    magic_number: int = 20240101
    deviation: int = 20                                     # Slippage tolerance in points
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
