"""
Layer 4 — Risk Manager.
Handles lot sizing, SL/TP validation, and position limits per pair.
Parameters differ for XAU/USD vs BTC/USD.
"""

import logging
from typing import Optional

import MetaTrader5 as mt5

from config.pairs import PairParams, get_pair_params

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk management with pair-specific parameters:

    | Parameter        | XAU/USD    | BTC/USD  |
    |------------------|------------|----------|
    | ATR SL mult      | 1.5x       | 2.0x     |
    | ATR TP mult      | 3.0x       | 4.0x     |
    | Max lot          | 1.0        | 0.1      |
    | Risk per trade   | 1.0%       | 0.5%     |
    | Min confidence   | 70%        | 75%      |
    | Max spread       | 30 points  | 50 pts   |
    """

    def __init__(self, account_balance: float, risk_percent: float = 1.0):
        """
        Args:
            account_balance: Current account balance
            risk_percent: Base risk % per trade (overridden per-pair)
        """
        self.balance = account_balance
        self.risk_percent = risk_percent
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._trade_history = []

    def update_balance(self, new_balance: float):
        """Update account balance without resetting internal state."""
        self.balance = new_balance

    def record_trade(self, pnl: float):
        """Record a closed trade for daily tracking."""
        self._daily_pnl += pnl
        self._daily_trades += 1
        self._trade_history.append(pnl)

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

    def reset_daily_tracking(self):
        """Reset daily P&L tracking (call at start of each trading day)."""
        from datetime import date
        if not hasattr(self, '_last_reset_date') or self._last_reset_date != date.today():
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset_date = date.today()

    def calculate_lot_size(
        self,
        symbol: str,
        sl_pips: float,
    ) -> float:
        """
        Calculate lot size based on risk management.

        Lot = risk_amount / (sl_pips × pip_value_per_lot)

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            sl_pips: Stop loss distance in pips

        Returns:
            Lot size rounded to 2 decimal places
        """
        pair_params = get_pair_params(symbol)
        risk_amount = self.balance * (pair_params.risk_percent / 100)
        pip_value = pair_params.pip_value_per_lot

        if sl_pips <= 0:
            logger.warning(f"Invalid SL pips ({sl_pips}) for {symbol}")
            return 0.01

        lot_size = risk_amount / (sl_pips * pip_value)

        # Clamp between 0.01 and pair max
        lot_size = max(0.01, min(lot_size, pair_params.max_lot))

        logger.info(
            f"Lot size [{symbol}]: risk=${risk_amount:.2f}, "
            f"SL={sl_pips:.1f} pips, pip_val=${pip_value}, lot={lot_size:.2f}"
        )
        return round(lot_size, 2)

    def calculate_sl_tp(
        self,
        signal: str,
        entry_price: float,
        atr: float,
        symbol: str,
    ) -> tuple:
        """
        Calculate SL & TP based on ATR and pair-specific multipliers.

        XAU/USD: SL = 1.5× ATR, TP = 3.0× ATR (R:R = 1:2)
        BTC/USD: SL = 2.0× ATR, TP = 4.0× ATR (R:R = 1:2)

        Returns:
            (sl, tp) tuple rounded to 2 decimals
        """
        pair_params = get_pair_params(symbol)

        if signal == "BUY":
            sl = entry_price - (atr * pair_params.atr_sl_multiplier)
            tp = entry_price + (atr * pair_params.atr_tp_multiplier)
        elif signal == "SELL":
            sl = entry_price + (atr * pair_params.atr_sl_multiplier)
            tp = entry_price - (atr * pair_params.atr_tp_multiplier)
        else:
            return None, None

        return round(sl, 2), round(tp, 2)

    def is_trade_allowed(
        self,
        symbol: str,
        open_positions: list,
        max_positions: int = 3,
    ) -> bool:
        """
        Check if a new trade is allowed for this symbol.

        Args:
            symbol: Trading symbol
            open_positions: List of current open positions for this symbol
            max_positions: Maximum concurrent positions allowed

        Returns:
            True if trade is allowed
        """
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
        """
        Check if current spread is within acceptable range.

        Args:
            symbol: Trading symbol
            tick: Current tick data with 'spread' key

        Returns:
            True if spread is acceptable
        """
        pair_params = get_pair_params(symbol)
        current_spread = tick.get("spread", 0)

        # Convert spread to points (approximate)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            spread_points = current_spread / symbol_info.point
        else:
            spread_points = current_spread * 10  # Rough estimate

        if spread_points > pair_params.max_spread_points:
            logger.warning(
                f"{symbol}: Spread {spread_points:.0f} points exceeds "
                f"max {pair_params.max_spread_points}. Skipping."
            )
            return False

        return True

    def get_account_risk_summary(
        self,
        open_positions: list,
        equity: float,
    ) -> dict:
        """
        Summarize current portfolio risk exposure.

        Returns:
            Dict with total_risk, positions_count, free_margin_pct, etc.
        """
        total_risk = 0.0

        for pos in open_positions:
            entry = pos.price_open
            sl = pos.sl
            volume = pos.volume
            symbol = pos.symbol

            if sl > 0 and entry > 0:
                pair_params = get_pair_params(symbol)
                risk = abs(entry - sl) * volume * pair_params.pip_value_per_lot
                total_risk += risk

        risk_pct = (total_risk / equity * 100) if equity > 0 else 0

        return {
            "total_risk": round(total_risk, 2),
            "risk_pct": round(risk_pct, 2),
            "positions_count": len(open_positions),
            "equity": round(equity, 2),
        }
