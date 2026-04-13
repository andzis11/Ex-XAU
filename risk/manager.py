"""
Layer 4 — Risk Manager.
Handles position sizing, stop loss / take profit validation,
daily loss limits, and overall portfolio risk.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from config import AppConfig, Symbol
from execution.signal_generator import TradeSignalResult

logger = logging.getLogger(__name__)


@dataclass
class RiskAssessment:
    """Result of risk assessment for a trade."""
    approved: bool
    reason: str
    lot_size: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0

    # Risk metrics
    risk_amount: float = 0.0        # $ amount at risk
    risk_pct: float = 0.0           # % of equity at risk
    potential_loss: float = 0.0     # Max potential loss in $
    potential_profit: float = 0.0   # Potential profit in $
    risk_reward_ratio: float = 0.0


class RiskManager:
    """
    Layer 4 — Risk Manager.
    Validates trades against risk rules and calculates position sizes.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._today = date.today()

    def reset_daily_tracking(self):
        """Reset daily P&L tracking (call at start of each trading day)."""
        today = date.today()
        if today != self._today:
            logger.info(f"New trading day: resetting daily P&L tracking")
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._today = today

    def update_daily_pnl(self, pnl: float):
        """Update daily P&L after a closed trade."""
        self._daily_pnl += pnl
        self._daily_trades += 1

    @property
    def daily_drawdown_pct(self) -> float:
        """Current daily drawdown percentage."""
        # This needs equity context — see check_trade method
        return 0.0

    def check_trade(
        self,
        signal: TradeSignalResult,
        account_equity: float,
        symbol_specs: Optional[dict] = None,
    ) -> RiskAssessment:
        """
        Perform full risk assessment for a trade signal.

        Args:
            signal: Trade signal from Layer 3
            account_equity: Current account equity
            symbol_specs: Symbol specifications (lot size limits, etc.)

        Returns:
            RiskAssessment with approval and position sizing
        """
        # Reset daily tracking if new day
        self.reset_daily_tracking()

        # Check 1: Daily drawdown limit
        if self._daily_pnl < 0:
            daily_dd_pct = abs(self._daily_pnl) / account_equity * 100
            if daily_dd_pct >= self.config.trading.max_daily_drawdown_pct:
                return RiskAssessment(
                    approved=False,
                    reason=(
                        f"Daily drawdown {daily_dd_pct:.1f}% exceeds "
                        f"limit {self.config.trading.max_daily_drawdown_pct}%. "
                        f"Trading halted for today."
                    ),
                )

        # Check 2: Signal must be approved
        if not signal.entry_price or signal.entry_price <= 0:
            return RiskAssessment(
                approved=False,
                reason="Invalid entry price",
            )

        # Check 3: SL must be set
        if not signal.recommended_stop_loss:
            return RiskAssessment(
                approved=False,
                reason="Stop loss not calculated",
            )

        # Check 4: SL distance must be reasonable
        sl_distance = abs(signal.entry_price - signal.recommended_stop_loss)
        if sl_distance <= 0:
            return RiskAssessment(
                approved=False,
                reason="Invalid stop loss distance",
            )

        # Check 5: Risk/Reward ratio
        tp_distance = abs(signal.entry_price - signal.recommended_take_profit)
        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

        if rr_ratio < 1.5:
            return RiskAssessment(
                approved=False,
                reason=(
                    f"Risk/Reward ratio {rr_ratio:.2f} below minimum 1.5"
                ),
            )

        # Calculate position size
        lot_size = self._calculate_position_size(
            signal=signal,
            account_equity=account_equity,
            sl_distance=sl_distance,
            symbol_specs=symbol_specs,
        )

        # Check 6: Lot size validation
        if lot_size <= 0:
            return RiskAssessment(
                approved=False,
                reason="Calculated lot size is zero or negative",
            )

        # Calculate risk metrics
        risk_amount = sl_distance * lot_size * self._get_tick_value(signal.symbol)
        risk_pct = risk_amount / account_equity * 100
        potential_profit = tp_distance * lot_size * self._get_tick_value(signal.symbol)

        return RiskAssessment(
            approved=True,
            reason="Trade approved by risk manager",
            lot_size=lot_size,
            stop_loss=signal.recommended_stop_loss,
            take_profit=signal.recommended_take_profit,
            risk_amount=risk_amount,
            risk_pct=risk_pct,
            potential_loss=risk_amount,
            potential_profit=potential_profit,
            risk_reward_ratio=rr_ratio,
        )

    def _calculate_position_size(
        self,
        signal: TradeSignalResult,
        account_equity: float,
        sl_distance: float,
        symbol_specs: Optional[dict] = None,
    ) -> float:
        """
        Calculate position size using Kelly Criterion with safety factor.

        Position size = (Account × Risk%) / (SL distance × Tick Value)
        """
        trading_cfg = self.config.trading
        risk_cfg = self.config.risk

        # Base risk: % of equity per trade
        risk_pct = trading_cfg.risk_per_trade_pct / 100

        # Kelly adjustment based on confluence score
        # Higher confluence = slightly larger position (up to 1.5x)
        kelly_adjustment = 1.0 + (signal.confluence_score - 0.5) * risk_cfg.kelly_fraction
        kelly_adjustment = max(0.5, min(kelly_adjustment, 1.5))  # Clamp 0.5x to 1.5x

        # Adjusted risk
        adjusted_risk = risk_pct * kelly_adjustment

        # Risk amount in dollars
        risk_amount = account_equity * adjusted_risk

        # Lot size calculation
        tick_value = self._get_tick_value(signal.symbol)
        raw_lot = risk_amount / (sl_distance * tick_value) if tick_value > 0 else 0

        # Round to valid lot size
        lot_size = self._normalize_lot_size(raw_lot, symbol_specs)

        logger.info(
            f"Position size: equity=${account_equity:.2f}, "
            f"risk={adjusted_risk:.1%}, kelly_adj={kelly_adjustment:.2f}x, "
            f"raw_lot={raw_lot:.4f}, final_lot={lot_size:.2f}"
        )

        return lot_size

    def _normalize_lot_size(
        self,
        raw_lot: float,
        symbol_specs: Optional[dict] = None,
    ) -> float:
        """Round lot size to valid increment and apply limits."""
        if symbol_specs:
            vol_min = symbol_specs.get("volume_min", 0.01)
            vol_max = symbol_specs.get("volume_max", 100.0)
            vol_step = symbol_specs.get("volume_step", 0.01)
        else:
            vol_min = 0.01
            vol_max = 100.0
            vol_step = 0.01

        # Clamp to min/max
        lot = max(vol_min, min(raw_lot, vol_max))

        # Round to step
        lot = round(lot / vol_step) * vol_step

        # Final clamp (after rounding)
        lot = max(vol_min, min(lot, vol_max))

        return round(lot, 2)

    def _get_tick_value(self, symbol: Symbol) -> float:
        """
        Get the tick value (profit per 1 point per 1 lot).
        These are approximate values — actual values come from broker.
        """
        # Approximate tick values (per standard lot)
        tick_values = {
            Symbol.XAUUSD: 100.0,   # $100 per $1 move per lot
            Symbol.BTCUSD: 1.0,     # $1 per $1 move per lot
        }
        return tick_values.get(symbol, 1.0)

    def validate_sl_tp(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        symbol: Symbol,
        symbol_specs: Optional[dict] = None,
    ) -> tuple:
        """
        Validate and adjust SL/TP levels.
        Returns (validated_sl, validated_tp, is_valid).
        """
        if not symbol_specs:
            return stop_loss, take_profit, True

        stops_level = symbol_specs.get("trade_stops_level", 0)
        point = symbol_specs.get("point", 1.0)
        min_distance = stops_level * point

        # Check SL distance from entry
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance < min_distance:
            logger.warning(
                f"SL distance {sl_distance} below minimum {min_distance}. Adjusting."
            )
            if entry_price > stop_loss:  # BUY
                stop_loss = entry_price - min_distance
            else:  # SELL
                stop_loss = entry_price + min_distance

        # Check TP distance from entry
        tp_distance = abs(entry_price - take_profit)
        if tp_distance < min_distance:
            logger.warning(
                f"TP distance {tp_distance} below minimum {min_distance}. Adjusting."
            )
            if entry_price < take_profit:  # BUY
                take_profit = entry_price + min_distance
            else:  # SELL
                take_profit = entry_price - min_distance

        return stop_loss, take_profit, True

    def get_portfolio_risk(self, open_positions: list, account_equity: float) -> dict:
        """
        Assess current portfolio risk from open positions.

        Returns dict with total_risk, max_drawdown_potential, etc.
        """
        if not open_positions:
            return {
                "total_risk_pct": 0.0,
                "total_exposure": 0.0,
                "position_count": 0,
            }

        total_risk = 0.0
        total_exposure = 0.0

        for pos in open_positions:
            entry = pos.get("price_open", 0)
            sl = pos.get("sl", 0)
            volume = pos.get("volume", 0)
            symbol_str = pos.get("symbol", "")

            # Determine symbol enum
            symbol = Symbol.XAUUSD if "XAU" in symbol_str.upper() else Symbol.BTCUSD
            tick_value = self._get_tick_value(symbol)

            if sl > 0 and entry > 0:
                risk = abs(entry - sl) * volume * tick_value
                total_risk += risk

            exposure = entry * volume * tick_value
            total_exposure += exposure

        total_risk_pct = (total_risk / account_equity * 100) if account_equity > 0 else 0

        return {
            "total_risk": total_risk,
            "total_risk_pct": total_risk_pct,
            "total_exposure": total_exposure,
            "position_count": len(open_positions),
        }
