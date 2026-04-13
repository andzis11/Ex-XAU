"""
Telegram Command Handler — Interactive bot control via Telegram.
Allows real-time parameter adjustments without restarting the bot.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TelegramCommands:
    """
    Handles incoming Telegram messages as bot commands.
    Available commands:
        /status      — Show bot status
        /tsl on|off  — Enable/disable trailing stop
        /tsl_params <act_mult> <trail_mult> — Set TSL parameters
        /risk <pct>  — Change risk per trade (e.g., /risk 0.5)
        /confidence <pct> — Change min confidence (e.g., /confidence 60)
        /pause       — Pause trading
        /resume      — Resume trading
        /atr_sl <mult> — Set ATR SL multiplier
        /atr_tp <mult> — Set ATR TP multiplier
        /maxpos <n>  — Set max positions per pair
        /help        — Show all commands
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message to Telegram chat."""
        try:
            url = f"{self.api_base}/sendMessage"
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

    def parse_command(self, message: str) -> tuple:
        """
        Parse incoming message into (command, args).
        Returns ("", "") if not a command.
        """
        text = message.strip()
        if not text.startswith("/"):
            return "", ""

        parts = text.split()
        command = parts[0].lower().lstrip("/")
        args = parts[1:] if len(parts) > 1 else []
        return command, args

    def handle_command(self, command: str, args: list, bot_ref: dict) -> str:
        """
        Process a command and return response text.
        bot_ref: dict containing mutable references to bot components.
        """
        cmd = command.lower()

        # ── /status ──
        if cmd == "status":
            return self._cmd_status(bot_ref)

        # ── /tsl ──
        elif cmd == "tsl":
            if not args:
                current = bot_ref.get("use_trailing_stop", False)
                return f"Usage: `/tsl on` or `/tsl off`\nCurrent: {'ON' if current else 'OFF'}"
            if args[0].lower() == "on":
                bot_ref["use_trailing_stop"] = True
                return "✅ Trailing Stop **ENABLED**"
            elif args[0].lower() == "off":
                bot_ref["use_trailing_stop"] = False
                return "⛔ Trailing Stop **DISABLED**"
            else:
                return "Usage: `/tsl on` or `/tsl off`"

        # ── /tsl_params ──
        elif cmd == "tsl_params":
            if len(args) < 2:
                act = bot_ref.get("tsl_activation", 1.5)
                trail = bot_ref.get("tsl_atr_mult", 1.0)
                return (
                    f"Usage: `/tsl_params <activation_mult> <trail_mult>`\n"
                    f"Current: act={act}×, trail={trail}× ATR"
                )
            try:
                bot_ref["tsl_activation"] = float(args[0])
                bot_ref["tsl_atr_mult"] = float(args[1])
                return f"✅ TSL params updated: act={args[0]}×, trail={args[1]}× ATR"
            except ValueError:
                return "❌ Invalid numbers. Example: `/tsl_params 2.5 1.5`"

        # ── /risk ──
        elif cmd == "risk":
            if not args:
                current = bot_ref.get("risk_percent", 1.0)
                return f"Usage: `/risk <percent>`\nCurrent: {current}%"
            try:
                val = float(args[0])
                if val < 0.1 or val > 5.0:
                    return "⚠️ Risk must be between 0.1% and 5.0%"
                bot_ref["risk_percent"] = val
                return f"✅ Risk per trade: **{val}%**"
            except ValueError:
                return "❌ Invalid number. Example: `/risk 0.5`"

        # ── /confidence ──
        elif cmd == "confidence":
            if not args:
                current = bot_ref.get("min_confidence", 0.55)
                return f"Usage: `/confidence <percent>`\nCurrent: {current*100:.0f}%"
            try:
                val = float(args[0]) / 100.0
                if val < 0.3 or val > 0.9:
                    return "⚠️ Confidence must be between 30% and 90%"
                bot_ref["min_confidence"] = val
                return f"✅ Min confidence: **{val*100:.0f}%**"
            except ValueError:
                return "❌ Invalid number. Example: `/confidence 60`"

        # ── /pause ──
        elif cmd == "pause":
            bot_ref["paused"] = True
            reason = args[0] if args else "Manual pause via Telegram"
            return f"⏸️ Bot **PAUSED**\nReason: {reason}"

        # ── /resume ──
        elif cmd == "resume":
            bot_ref["paused"] = False
            return "▶️ Bot **RESUMED**"

        # ── /atr_sl ──
        elif cmd == "atr_sl":
            if not args:
                current = bot_ref.get("atr_sl_mult", 2.0)
                return f"Usage: `/atr_sl <multiplier>`\nCurrent: {current}× ATR"
            try:
                val = float(args[0])
                if val < 0.5 or val > 5.0:
                    return "⚠️ ATR SL must be between 0.5× and 5.0×"
                bot_ref["atr_sl_mult"] = val
                return f"✅ ATR SL multiplier: **{val}×**"
            except ValueError:
                return "❌ Invalid number. Example: `/atr_sl 2.0`"

        # ── /atr_tp ──
        elif cmd == "atr_tp":
            if not args:
                current = bot_ref.get("atr_tp_mult", 4.0)
                return f"Usage: `/atr_tp <multiplier>`\nCurrent: {current}× ATR"
            try:
                val = float(args[0])
                if val < 1.0 or val > 10.0:
                    return "⚠️ ATR TP must be between 1.0× and 10.0×"
                bot_ref["atr_tp_mult"] = val
                return f"✅ ATR TP multiplier: **{val}×**"
            except ValueError:
                return "❌ Invalid number. Example: `/atr_tp 4.0`"

        # ── /maxpos ──
        elif cmd == "maxpos":
            if not args:
                current = bot_ref.get("max_positions", 3)
                return f"Usage: `/maxpos <count>`\nCurrent: {current}"
            try:
                val = int(args[0])
                if val < 1 or val > 10:
                    return "⚠️ Max positions must be between 1 and 10"
                bot_ref["max_positions"] = val
                return f"✅ Max positions per pair: **{val}**"
            except ValueError:
                return "❌ Invalid number. Example: `/maxpos 3`"

        # ── /help ──
        elif cmd == "help":
            return self._cmd_help()

        # ── Unknown ──
        else:
            return f"❓ Unknown command: `/{cmd}`\nType `/help` for available commands."

    def _cmd_status(self, bot_ref: dict) -> str:
        """Generate status report."""
        paused = bot_ref.get("paused", False)
        status_emoji = "⏸️ PAUSED" if paused else "▶️ RUNNING"

        lines = [
            f"🤖 *Bot Status: {status_emoji}*",
            "",
            f"📊 *Trading Parameters:*",
            f"• Risk/trade: `{bot_ref.get('risk_percent', 1.0)}%`",
            f"• Min confidence: `{bot_ref.get('min_confidence', 0.55)*100:.0f}%`",
            f"• Max positions: `{bot_ref.get('max_positions', 3)}`",
            "",
            f"📐 *SL/TP Settings:*",
            f"• ATR SL: `{bot_ref.get('atr_sl_mult', 2.0)}×`",
            f"• ATR TP: `{bot_ref.get('atr_tp_mult', 4.0)}×`",
            "",
            f"🔄 *Trailing Stop:*",
            f"• Status: `{'ON' if bot_ref.get('use_trailing_stop', False) else 'OFF'}`",
            f"• Activation: `{bot_ref.get('tsl_activation', 1.5)}× ATR`",
            f"• Trail distance: `{bot_ref.get('tsl_atr_mult', 1.0)}× ATR`",
            "",
            f"📈 *Session:*",
            f"• Cycle count: `{bot_ref.get('cycle_count', 0)}`",
        ]

        if "balance" in bot_ref:
            lines.append(f"• Balance: `${bot_ref['balance']:.2f}`")
        if "daily_dd" in bot_ref:
            lines.append(f"• Daily DD: `{bot_ref['daily_dd']:.1f}%`")

        return "\n".join(lines)

    def _cmd_help(self) -> str:
        return (
            "📖 *Available Commands*\n\n"
            "📊 *Monitoring:*\n"
            "• `/status` — Show current bot status\n\n"
            "🔄 *Trailing Stop:*\n"
            "• `/tsl on|off` — Enable/disable trailing stop\n"
            "• `/tsl_params <act> <trail>` — Set TSL parameters\n\n"
            "📐 *Risk Settings:*\n"
            "• `/risk <pct>` — Risk per trade (0.1-5.0%)\n"
            "• `/confidence <pct>` — Min confidence (30-90%)\n"
            "• `/maxpos <n>` — Max positions per pair (1-10)\n\n"
            "📏 *SL/TP Settings:*\n"
            "• `/atr_sl <mult>` — ATR SL multiplier (0.5-5.0×)\n"
            "• `/atr_tp <mult>` — ATR TP multiplier (1.0-10.0×)\n\n"
            "⏯️ *Control:*\n"
            "• `/pause [reason]` — Pause trading\n"
            "• `/resume` — Resume trading\n\n"
            "💡 *Examples:*\n"
            "• `/tsl on`\n"
            "• `/tsl_params 2.5 1.5`\n"
            "• `/risk 0.5`\n"
            "• `/pause NFP news incoming`"
        )
