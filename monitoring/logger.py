"""
Layer 6 — Logger module.
Structured logging for all bot activity with rotation support.
"""

import logging
import os
from datetime import datetime


def setup_logger(
    log_file: str = "logs/bot.log",
    level: str = "INFO",
) -> logging.Logger:
    """
    Set up application logger with console + file output.

    Args:
        log_file: Path to log file
        level: Log level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    logger = logging.getLogger("ai_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on re-init
    if logger.handlers:
        return logger

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%H:%M:%S",
    )
    console.setFormatter(console_fmt)

    # File handler (with rotation)
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
        )
    except ImportError:
        file_handler = logging.FileHandler(log_file)

    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)

    logger.info(f"Logger initialized | Level: {level} | File: {log_file}")
    return logger


class TradeLogger:
    """
    Specialized logger for trade-related events.
    Writes structured trade entries to a separate log file.
    """

    def __init__(self, log_file: str = "logs/trades.log"):
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

        self.logger = logging.getLogger("trades")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            self.logger.addHandler(handler)

    def log_signal(self, symbol: str, direction: str, confidence: float, entry: float):
        """Log a generated signal."""
        self.logger.info(
            f"SIGNAL | {symbol} | {direction} | "
            f"conf={confidence:.0%} | entry={entry:.2f}"
        )

    def log_order(self, symbol: str, ticket: int, direction: str,
                  lot: float, entry: float, sl: float, tp: float):
        """Log an executed order."""
        self.logger.info(
            f"ORDER  | {symbol} | #{ticket} | {direction} | "
            f"lot={lot} | entry={entry} | SL={sl} | TP={tp}"
        )

    def log_close(self, symbol: str, ticket: int, exit_price: float,
                  pnl: float, reason: str):
        """Log a closed trade."""
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        self.logger.info(
            f"CLOSE  | {symbol} | #{ticket} | "
            f"exit={exit_price} | PnL={pnl_str} | reason={reason}"
        )

    def log_error(self, message: str):
        """Log an error event."""
        self.logger.error(f"ERROR  | {message}")

    def log_status(self, message: str):
        """Log a status update."""
        self.logger.info(f"STATUS | {message}")
