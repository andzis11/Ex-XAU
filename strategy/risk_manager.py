"""
Layer 4 — Risk Manager (SURVIVAL MODE).
Handles lot sizing, SL/TP validation, position limits.
Added: consecutive loss tracking, weekly drawdown limit.
"""

import logging
from datetime import date, datetime
from typing import Optional

import MetaTrader5 as mt5

from config.pairs import PairParams, get_pair_params

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk management with pair-specific parameters and survival safeguards.

    | Parameter           | XAU/USD    | BTC/USD  |
    |---------------------|------------|----------|
    | ATR SL mult         | 2.0x       | 2.5x     |
    | ATR TP mult         | 4.0x       | 5.0x     |
    | Max lot             | 1.0        | 0.1      |
    | Risk per trade      | 0.5%       | 0.5%     |
    | Min confidence      | 40%        | 40%      |
    | Max spread          | 30 points  | 50 pts   |
    """

    def __init__(
        self,
        account_balance: float,
        risk_percent: float = 0.5,
        max_consecutive_losses: int = 3,
        max_weekly_drawdown_pct: float = 8.0,
    ):
        self.balance = account_balance
        self.risk_percent = risk_percent
        self.max_consecutive_losses = max_consecutive_losses
        self.max_weekly_drawdown_pct = max_weekly_drawdown_pct

        # Tracking
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._last_reset_date = date.today()
        self._trade_history = []  # (datetime, pnl)
        self._consecutive_losses = 0

    def update_balance(self, new_balance: float):
        """Update account balance without resetting internal state."""
        self.balance = new_balance

    def record_trade(self, pnl: float):
        """Record a closed trade for tracking."""
        self._daily_pnl += pnl
        self._daily_trades += 1
        self._trade_history.append((datetime.now(), pnl))

        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0  # Reset on win

    @property
    def daily_drawdown(self) -> float:
        """Current daily drawdown (negative value if losing)."""
        return self._daily_pnl if self._daily_pnl < 0 else 0.0

    @property
    def daily_drawdown_pct(self) -> float:
        """Daily drawdown as percentage of balance."""
        if self.balance <= 0:
            return 0.0
        return abs(self.daily_drawdown) / self.balance * 100

    @property
    def weekly_drawdown_pct(self) -> float:
        """Weekly drawdown as percentage of balance (last 7 days)."""
        if self.balance <= 0 or not self._trade_history:
            return 0.0

        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Simple: track last 7 calendar days
        week_pnl = sum(
            pnl for dt, pnl in self._trade_history
            if (datetime.now() - dt).days <= 7
        )

        return abs(week_pnl) / self.balance * 100 if week_pnl < 0 else 0.0

    @property
    def consecutive_losses(self) -> int:
        """Number of consecutive losing trades."""
        return self._consecutive_losses

    @property
    def should_pause(self) -> tuple:
        """Check if bot should pause due to risk limits.
        Returns (should_pause, reason).
        """
        # Check consecutive losses
        if self._consecutive_losses >= self.max_consecutive_losses:
            return True, f"{self._consecutive_losses} consecutive losses"

        # Check daily drawdown
        if self.daily_drawdown_pct >= 3.0:
            return True, f"Daily DD {self.daily_drawdown_pct:.1f}%"

        # Check weekly drawdown
        if self.weekly_drawdown_pct >= self.max_weekly_drawdown_pct:
            return True, f"Weekly DD {self.weekly_drawdown_pct:.1f}%"

        return False, ""

    def reset_daily_tracking(self):
        """Reset daily P&L tracking (call at start of each trading day)."""
        today = date.today()
        if today != self._last_reset_date:
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset_date = today

    def calculate_lot_size(
        self,
        symbol: str,
        sl_distance: float,
    ) -> float:
        """
        Calculate lot size based on risk management.

        Lot = risk_amount / (sl_distance × pip_value_per_lot)

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            sl_distance: Stop loss distance in price (not pips)

        Returns:
            Lot size rounded to 2 decimal places
        """
        pair_params = get_pair_params(symbol)
        risk_amount = self.balance * (pair_params.risk_percent / 100)
        pip_value = pair_params.pip_value_per_lot

        if sl_distance <= 0:
            logger.warning(f"Invalid SL distance ({sl_distance}) for {symbol}")
            return 0.01

        # For XAU: sl_distance is in $, pip_value is $10 per lot per $0.01
        # Lot = risk_amount / (sl_distance / 0.01 * pip_value)
        # Simplified: Lot = risk_amount / (sl_distance * pip_value / 0.01)
        lot_size = risk_amount / (sl_distance * pip_value / 0.01)

        # Clamp between 0.01 and pair max
        lot_size = max(0.01, min(lot_size, pair_params.max_lot))

        logger.info(
            f"Lot size [{symbol}]: risk=${risk_amount:.2f}, "
            f"SL_dist={sl_distance:.2f}, pip_val=${pip_value}, lot={lot_size:.2f}"
        )
        return round(lot_size, 2)

    def is_trade_allowed(
        self,
        symbol: str,
        open_positions: list,
        max_positions: int = 2,
    ) -> bool:
        """Check if a new trade is allowed for this symbol."""
        if len(open_positions) >= max_positions:
            logger.warning(
                f"{symbol}: Max positions ({max_positions}) reached. Skipping."
            )
            return False
        return True

    def check_spread(
        self,
        symbol: str,
        tick: dict,
    ) -> bool:
        """Check if current spread is within acceptable range."""
        pair_params = get_pair_params(symbol)
        current_spread = tick.get("spread", 0)

        # Convert spread to points
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            spread_points = current_spread / symbol_info.point
        else:
            spread_points = current_spread * 10

        if spread_points > pair_params.max_spread_points:
            logger.warning(
                f"{symbol}: Spread {spread_points:.0f} points exceeds "
                f"max {pair_params.max_spread_points}. Skipping."
            )
            return False

        return True

    def get_account_risk_summary(self, open_positions: list, equity: float) -> dict:
        """Summarize current portfolio risk exposure."""
        total_risk = 0.0

        for pos in open_positions:
            entry = pos.price_open
            sl = pos.sl
            volume = pos.volume
            symbol_str = pos.symbol

            if sl > 0 and entry > 0:
                pair_params = get_pair_params(symbol_str)
                risk = abs(entry - sl) * volume * pair_params.pip_value_per_lot
                total_risk += risk

        risk_pct = (total_risk / equity * 100) if equity > 0 else 0

        return {
            "total_risk": round(total_risk, 2),
            "risk_pct": round(risk_pct, 2),
            "positions_count": len(open_positions),
            "equity": round(equity, 2),
            "consecutive_losses": self._consecutive_losses,
            "daily_dd_pct": round(self.daily_drawdown_pct, 2),
            "weekly_dd_pct": round(self.weekly_drawdown_pct, 2),
        }
