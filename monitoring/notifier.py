"""
Layer 5 — Telegram Notifier.
Sends trade alerts, performance summaries, and error notifications via Telegram.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends messages to a Telegram chat via Bot API.
    """

    API_BASE = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        """
        Args:
            bot_token: Telegram BotFather token
            chat_id: Target chat ID
            enabled: Whether notifications are active
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)

        if self.enabled:
            logger.info(f"Telegram notifier enabled (chat: {chat_id})")
        else:
            logger.warning("Telegram notifier disabled (no token/chat_id)")

    def _send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to the Telegram chat."""
        if not self.enabled:
            return False

        try:
            url = self.API_BASE.format(token=self.bot_token, method="sendMessage")
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send(self, message: str) -> bool:
        """Send a plain text message."""
        return self._send(message, parse_mode="Markdown")

    def notify_bot_started(self, pairs: list):
        """Send startup notification."""
        text = (
            f"🤖 *AI Trading Bot AKTIF!*\n\n"
            f"Pairs: {', '.join(pairs)}\n"
            f"Mode: Live Trading\n"
            f"Monitoring every 15 minutes."
        )
        self._send(text)

    def notify_bot_stopped(self):
        """Send shutdown notification."""
        self._send("🛑 *Trading Bot berhenti.*")

    def notify_signal(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        entry: float,
        sl: float,
        tp: float,
        lot: float,
    ):
        """Send trade signal notification."""
        emoji = "🟢" if signal == "BUY" else "🔴"

        text = (
            f"{emoji} *ORDER MASUK*\n\n"
            f"Pair: `{symbol}`\n"
            f"Signal: *{signal}*\n"
            f"Entry: `{entry}`\n"
            f"SL: `{sl}` | TP: `{tp}`\n"
            f"Lot: `{lot}`\n"
            f"Confidence: `{confidence:.2%}`"
        )
        self._send(text)

    def notify_order_filled(
        self,
        symbol: str,
        ticket: int,
        direction: str,
        lot: float,
        entry: float,
    ):
        """Send order confirmation."""
        text = (
            f"✅ *Order Filled*\n\n"
            f"Pair: `{symbol}` | #{ticket}\n"
            f"Direction: {direction}\n"
            f"Lot: {lot} | Entry: {entry}"
        )
        self._send(text)

    def notify_trade_closed(
        self,
        symbol: str,
        ticket: int,
        pnl: float,
        reason: str,
    ):
        """Send trade close notification with P&L."""
        emoji = "💰" if pnl >= 0 else "📉"
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

        text = (
            f"{emoji} *Trade Closed*\n\n"
            f"Pair: `{symbol}` | #{ticket}\n"
            f"P&L: `{pnl_str}`\n"
            f"Reason: {reason}"
        )
        self._send(text)

    def notify_daily_summary(
        self,
        trades: int,
        wins: int,
        losses: int,
        total_pnl: float,
        equity: float,
    ):
        """Send end-of-day summary."""
        win_rate = (wins / trades * 100) if trades > 0 else 0
        pnl_sign = "+" if total_pnl >= 0 else ""

        text = (
            f"📊 *Daily Summary*\n\n"
            f"Trades: {trades} | W/L: {wins}/{losses}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"P&L: `{pnl_sign}${total_pnl:.2f}`\n"
            f"Equity: `${equity:.2f}`"
        )
        self._send(text)

    def notify_error(self, error: str):
        """Send error alert."""
        text = f"🚨 *ERROR*\n\n```\n{error[:500]}\n```"
        self._send(text)

    def notify_spread_warning(self, symbol: str, spread: float):
        """Warn about wide spread."""
        text = (
            f"⚠️ *Wide Spread*\n\n"
            f"Pair: `{symbol}`\n"
            f"Spread: `{spread:.1f}` points\n"
            f"Trade skipped."
        )
        self._send(text)

    def notify_daily_drawdown(self, drawdown_pct: float):
        """Alert when daily drawdown exceeds limit."""
        text = (
            f"🛑 *DAILY DRAWDOWN LIMIT*\n\n"
            f"Drawdown: `{drawdown_pct:.1f}%`\n"
            f"Trading paused until tomorrow."
        )
        self._send(text)

    def test(self) -> bool:
        """Send a test message to verify connection."""
        return self._send("✅ Bot connection test successful!")
