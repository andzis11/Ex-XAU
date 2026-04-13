"""
Layer 5 — Order Execution: Telegram notification & monitoring.
Sends trade alerts, status updates, and error notifications.
"""

import logging
from typing import Optional

import requests

from config import AppConfig, Symbol
from execution.signal_generator import TradeSignalResult
from risk.manager import RiskAssessment

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends notifications via Telegram Bot API.
    Provides trade alerts, performance updates, and error notifications.
    """

    API_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, config: AppConfig):
        self.config = config
        self.enabled = config.telegram.enabled and config.telegram.bot_token
        self.bot_token = config.telegram.bot_token
        self.chat_id = config.telegram.chat_id

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to the configured chat."""
        if not self.enabled:
            return False

        try:
            url = self.API_URL.format(token=self.bot_token, method="sendMessage")
            response = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            response.raise_for_status()
            return True

        except requests.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def notify_new_signal(self, signal: TradeSignalResult):
        """Send notification when a new trade signal is generated."""
        if not self.enabled or signal.signal.value == "NO_TRADE":
            return

        emoji = "🟢" if signal.signal.value == "BUY" else "🔴"

        text = (
            f"{emoji} *NEW SIGNAL: {signal.symbol.value}*\n\n"
            f"*Direction:* {signal.signal.value}\n"
            f"*Entry:* {signal.entry_price:.2f}\n"
            f"*Stop Loss:* {signal.recommended_stop_loss:.2f}\n"
            f"*Take Profit:* {signal.recommended_take_profit:.2f}\n"
            f"*Confluence:* {signal.confluence_score:.0%}\n\n"
            f"*Reasoning:*\n{signal.reasoning}\n\n"
            f"*Key Factors:*\n" + "\n".join(f"• {f}" for f in signal.key_factors[:5])
        )

        self.send_message(text)

    def notify_trade_executed(
        self,
        symbol: Symbol,
        direction: str,
        volume: float,
        entry: float,
        sl: float,
        tp: float,
        ticket: int,
    ):
        """Send notification when a trade is executed."""
        if not self.enabled:
            return

        emoji = "✅"

        text = (
            f"{emoji} *TRADE EXECUTED*\n\n"
            f"*Symbol:* {symbol.value}\n"
            f"*Direction:* {direction}\n"
            f"*Volume:* {volume} lot\n"
            f"*Entry:* {entry:.2f}\n"
            f"*SL:* {sl:.2f}\n"
            f"*TP:* {tp:.2f}\n"
            f"*Ticket:* `{ticket}`"
        )

        self.send_message(text)

    def notify_trade_closed(
        self,
        symbol: Symbol,
        direction: str,
        volume: float,
        entry: float,
        exit_price: float,
        pnl: float,
        ticket: int,
    ):
        """Send notification when a trade is closed."""
        if not self.enabled:
            return

        emoji = "💰" if pnl >= 0 else "📉"
        pnl_sign = "+" if pnl >= 0 else ""

        text = (
            f"{emoji} *TRADE CLOSED*\n\n"
            f"*Symbol:* {symbol.value}\n"
            f"*Direction:* {direction}\n"
            f"*Entry:* {entry:.2f}\n"
            f"*Exit:* {exit_price:.2f}\n"
            f"*P&L:* `{pnl_sign}${pnl:.2f}`\n"
            f"*Ticket:* `{ticket}`"
        )

        self.send_message(text)

    def notify_daily_summary(
        self,
        trades: int,
        wins: int,
        losses: int,
        total_pnl: float,
        equity: float,
    ):
        """Send daily performance summary."""
        if not self.enabled:
            return

        win_rate = (wins / trades * 100) if trades > 0 else 0
        pnl_sign = "+" if total_pnl >= 0 else ""

        text = (
            f"📊 *DAILY SUMMARY*\n\n"
            f"*Trades:* {trades}\n"
            f"*Wins:* {wins} | *Losses:* {losses}\n"
            f"*Win Rate:* {win_rate:.1f}%\n"
            f"*P&L:* `{pnl_sign}${total_pnl:.2f}`\n"
            f"*Equity:* `${equity:.2f}`"
        )

        self.send_message(text)

    def notify_error(self, error: str):
        """Send error notification."""
        if not self.enabled:
            return

        text = (
            f"🚨 *BOT ERROR*\n\n"
            f"```\n{error}\n```"
        )
        self.send_message(text)

    def notify_status(self, account_info: dict):
        """Send account status update."""
        if not self.enabled:
            return

        equity = account_info.get("equity", 0)
        balance = account_info.get("balance", 0)
        margin = account_info.get("margin", 0)
        free = account_info.get("margin_free", 0)

        text = (
            f"📈 *ACCOUNT STATUS*\n\n"
            f"*Balance:* ${balance:.2f}\n"
            f"*Equity:* ${equity:.2f}\n"
            f"*Margin Used:* ${margin:.2f}\n"
            f"*Free Margin:* ${free:.2f}"
        )

        self.send_message(text)

    def notify_risk_alert(self, risk: RiskAssessment, symbol: Symbol):
        """Send risk-related alert."""
        if not self.enabled:
            return

        text = (
            f"⚠️ *RISK ALERT: {symbol.value}*\n\n"
            f"*Approved:* {'Yes' if risk.approved else 'No'}\n"
            f"*Lot Size:* {risk.lot_size}\n"
            f"*Risk:* ${risk.risk_amount:.2f} ({risk.risk_pct:.1f}%)\n"
            f"*R:R Ratio:* {risk.risk_reward_ratio:.2f}\n\n"
            f"*Reason:* {risk.reason}"
        )

        self.send_message(text)

    def test_connection(self) -> bool:
        """Test Telegram connection."""
        return self.send_message("🤖 Trading bot connected and ready!")
