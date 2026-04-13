"""
Telegram Inline Keyboard — Interactive button menu for bot control.
No typing needed — just tap buttons.
"""

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TelegramKeyboard:
    """
    Sends interactive inline keyboards via Telegram.
    Users tap buttons instead of typing commands.
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self._menu_message_id = None

    def send_message(self, text: str, reply_markup: dict = None, parse_mode: str = "Markdown") -> Optional[int]:
        """Send a message with optional inline keyboard. Returns message_id."""
        try:
            url = f"{self.api_base}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)

            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json().get("result", {}).get("message_id")
        except requests.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            return None

    def edit_message(self, text: str, reply_markup: dict = None) -> bool:
        """Edit existing menu message with updated content."""
        if not self._menu_message_id:
            return False
        try:
            url = f"{self.api_base}/editMessageText"
            payload = {
                "chat_id": self.chat_id,
                "message_id": self._menu_message_id,
                "text": text,
                "parse_mode": "Markdown",
            }
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def answer_callback(self, callback_query_id: str, text: str = "", show_alert: bool = False):
        """Acknowledge a button press."""
        try:
            url = f"{self.api_base}/answerCallbackQuery"
            requests.post(url, json={
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
            }, timeout=5)
        except Exception:
            pass

    # ──────────────────────────────────────────
    # MAIN MENU
    # ──────────────────────────────────────────

    def show_main_menu(self, bot_ref: dict) -> int:
        """Show the main control panel with all buttons."""
        paused = bot_ref.get("paused", False)
        tsl_on = bot_ref.get("use_trailing_stop", False)

        status_emoji = "⏸️ PAUSED" if paused else "▶️ RUNNING"
        tsl_status = "✅ ON" if tsl_on else "❌ OFF"

        text = (
            f"🤖 *Ex-XAU Bot Control Panel*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status: {status_emoji}\n\n"
            f"📊 *Trading:*\n"
            f"• Risk: `{bot_ref.get('risk_percent', 1.0)}%` per trade\n"
            f"• Confidence: `{bot_ref.get('min_confidence', 0.55)*100:.0f}%`\n"
            f"• Max Pos: `{bot_ref.get('max_positions', 3)}`\n\n"
            f"📐 *SL/TP:*\n"
            f"• ATR SL: `{bot_ref.get('atr_sl_mult', 2.0)}×`\n"
            f"• ATR TP: `{bot_ref.get('atr_tp_mult', 4.0)}×`\n\n"
            f"🔄 *Trailing Stop:*\n"
            f"• Status: {tsl_status}\n"
            f"• Activation: `{bot_ref.get('tsl_activation', 2.5)}× ATR`\n"
            f"• Trail: `{bot_ref.get('tsl_atr_mult', 1.5)}× ATR`\n\n"
            f"📈 *Session:*\n"
            f"• Cycles: `{bot_ref.get('cycle_count', 0)}`\n"
        )

        if "balance" in bot_ref:
            text += f"• Balance: `${bot_ref['balance']:.2f}`\n"

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "⏸️ PAUSE" if not paused else "▶️ RESUME",
                        "callback_data": "toggle_pause"
                    },
                    {
                        "text": "🔄 TSL: " + ("ON" if tsl_on else "OFF"),
                        "callback_data": "toggle_tsl"
                    }
                ],
                [
                    {"text": "📊 Risk", "callback_data": "menu_risk"},
                    {"text": "📐 SL/TP", "callback_data": "menu_sltp"},
                ],
                [
                    {"text": "🔄 TSL Params", "callback_data": "menu_tsl"},
                    {"text": "📈 Status", "callback_data": "cmd_status"},
                ],
            ]
        }

        msg_id = self.send_message(text, reply_markup=keyboard)
        if msg_id:
            self._menu_message_id = msg_id
        return msg_id

    # ──────────────────────────────────────────
    # RISK MENU
    # ──────────────────────────────────────────

    def show_risk_menu(self, bot_ref: dict) -> int:
        text = (
            f"📊 *Risk Settings*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Risk: `{bot_ref.get('risk_percent', 1.0)}%`\n"
            f"Confidence: `{bot_ref.get('min_confidence', 0.55)*100:.0f}%`\n"
            f"Max Positions: `{bot_ref.get('max_positions', 3)}`\n\n"
            f"_Tap a value to change it_"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Risk: 0.25%", "callback_data": "risk_0.25"},
                    {"text": "Risk: 0.5%", "callback_data": "risk_0.5"},
                    {"text": "Risk: 1.0%", "callback_data": "risk_1.0"},
                ],
                [
                    {"text": "Risk: 1.5%", "callback_data": "risk_1.5"},
                    {"text": "Risk: 2.0%", "callback_data": "risk_2.0"},
                    {"text": "Risk: 3.0%", "callback_data": "risk_3.0"},
                ],
                [
                    {"text": "Conf: 50%", "callback_data": "conf_50"},
                    {"text": "Conf: 55%", "callback_data": "conf_55"},
                    {"text": "Conf: 60%", "callback_data": "conf_60"},
                ],
                [
                    {"text": "Conf: 65%", "callback_data": "conf_65"},
                    {"text": "Conf: 70%", "callback_data": "conf_70"},
                ],
                [
                    {"text": "MaxPos: 1", "callback_data": "maxpos_1"},
                    {"text": "MaxPos: 2", "callback_data": "maxpos_2"},
                    {"text": "MaxPos: 3", "callback_data": "maxpos_3"},
                ],
                [
                    {"text": "🔙 Back", "callback_data": "back_main"},
                ],
            ]
        }

        return self.send_message(text, reply_markup=keyboard)

    # ──────────────────────────────────────────
    # SL/TP MENU
    # ──────────────────────────────────────────

    def show_sltp_menu(self, bot_ref: dict) -> int:
        text = (
            f"📐 *SL/TP Settings*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"ATR SL: `{bot_ref.get('atr_sl_mult', 2.0)}×`\n"
            f"ATR TP: `{bot_ref.get('atr_tp_mult', 4.0)}×`\n"
            f"R:R = 1:{bot_ref.get('atr_tp_mult', 4.0)/max(bot_ref.get('atr_sl_mult', 2.0),0.1):.1f}\n\n"
            f"_Tap to change_"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "SL: 1.0×", "callback_data": "sl_1.0"},
                    {"text": "SL: 1.5×", "callback_data": "sl_1.5"},
                    {"text": "SL: 2.0×", "callback_data": "sl_2.0"},
                ],
                [
                    {"text": "SL: 2.5×", "callback_data": "sl_2.5"},
                    {"text": "SL: 3.0×", "callback_data": "sl_3.0"},
                ],
                [
                    {"text": "TP: 2.0×", "callback_data": "tp_2.0"},
                    {"text": "TP: 3.0×", "callback_data": "tp_3.0"},
                    {"text": "TP: 4.0×", "callback_data": "tp_4.0"},
                ],
                [
                    {"text": "TP: 5.0×", "callback_data": "tp_5.0"},
                    {"text": "TP: 6.0×", "callback_data": "tp_6.0"},
                ],
                [
                    {"text": "🔙 Back", "callback_data": "back_main"},
                ],
            ]
        }

        return self.send_message(text, reply_markup=keyboard)

    # ──────────────────────────────────────────
    # TSL MENU
    # ──────────────────────────────────────────

    def show_tsl_menu(self, bot_ref: dict) -> int:
        tsl_on = bot_ref.get("use_trailing_stop", False)
        text = (
            f"🔄 *Trailing Stop Settings*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status: {'✅ ON' if tsl_on else '❌ OFF'}\n"
            f"Activation: `{bot_ref.get('tsl_activation', 2.5)}× ATR`\n"
            f"Trail Distance: `{bot_ref.get('tsl_atr_mult', 1.5)}× ATR`\n\n"
            f"_Tap to change_"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🔄 TSL: " + ("ON" if tsl_on else "OFF"),
                        "callback_data": "toggle_tsl"
                    },
                ],
                [
                    {"text": "Act: 1.0×", "callback_data": "tsl_act_1.0"},
                    {"text": "Act: 1.5×", "callback_data": "tsl_act_1.5"},
                    {"text": "Act: 2.0×", "callback_data": "tsl_act_2.0"},
                ],
                [
                    {"text": "Act: 2.5×", "callback_data": "tsl_act_2.5"},
                    {"text": "Act: 3.0×", "callback_data": "tsl_act_3.0"},
                ],
                [
                    {"text": "Trail: 0.5×", "callback_data": "tsl_trail_0.5"},
                    {"text": "Trail: 1.0×", "callback_data": "tsl_trail_1.0"},
                    {"text": "Trail: 1.5×", "callback_data": "tsl_trail_1.5"},
                ],
                [
                    {"text": "Trail: 2.0×", "callback_data": "tsl_trail_2.0"},
                ],
                [
                    {"text": "🔙 Back", "callback_data": "back_main"},
                ],
            ]
        }

        return self.send_message(text, reply_markup=keyboard)

    # ──────────────────────────────────────────
    # STATUS
    # ──────────────────────────────────────────

    def show_status(self, bot_ref: dict) -> int:
        paused = bot_ref.get("paused", False)
        status_emoji = "⏸️ PAUSED" if paused else "▶️ RUNNING"
        tsl_on = bot_ref.get("use_trailing_stop", False)

        text = (
            f"📈 *Full Bot Status*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"State: {status_emoji}\n\n"
            f"💰 *Account:*\n"
            f"• Balance: `${bot_ref.get('balance', 0):.2f}`\n"
            f"• Daily DD: `{bot_ref.get('daily_dd', 0):.1f}%`\n\n"
            f"⚙️ *Current Settings:*\n"
            f"• Risk: `{bot_ref.get('risk_percent', 1.0)}%`\n"
            f"• Confidence: `{bot_ref.get('min_confidence', 0.55)*100:.0f}%`\n"
            f"• Max Pos: `{bot_ref.get('max_positions', 3)}`\n"
            f"• ATR SL: `{bot_ref.get('atr_sl_mult', 2.0)}×`\n"
            f"• ATR TP: `{bot_ref.get('atr_tp_mult', 4.0)}×`\n"
            f"• TSL: {'ON' if tsl_on else 'OFF'}\n"
            f"  Act: `{bot_ref.get('tsl_activation', 2.5)}×` | "
            f"Trail: `{bot_ref.get('tsl_atr_mult', 1.5)}×`\n\n"
            f"📊 *Session:*\n"
            f"• Cycles: `{bot_ref.get('cycle_count', 0)}`"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔙 Back to Menu", "callback_data": "back_main"},
                ],
            ]
        }

        return self.send_message(text, reply_markup=keyboard)

    # ──────────────────────────────────────────
    # NOTIFICATIONS
    # ──────────────────────────────────────────

    def notify_setting_changed(self, setting: str, value: str):
        """Send a quick notification when a setting is changed."""
        self.send_message(f"✅ {setting} set to `{value}`")

    def notify_error(self, error: str):
        self.send_message(f"❌ Error: {error}")
