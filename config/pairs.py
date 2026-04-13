"""
Pair-specific configuration for XAU/USD and BTC/USD.
SIMPLIFIED — pure indicator-based strategy (no LSTM dependency).
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class PairParams:
    """Trading parameters for a single symbol."""
    timeframe: str                # M15 / H1 / H4
    atr_sl_multiplier: float      # ATR multiplier for stop loss
    atr_tp_multiplier: float      # ATR multiplier for take profit
    max_lot: float                # Maximum lot size
    risk_percent: float           # Risk % per trade (SURVIVAL MODE: 0.5%)
    min_confidence: float         # Minimum signal score to enter
    max_spread_points: int        # Max acceptable spread before skipping
    pip_value_per_lot: float      # $ value per pip per standard lot


# Parameter table — optimized for consistency, not greed
PAIR_CONFIG: Dict[str, PairParams] = {
    "XAUUSD": PairParams(
        timeframe="M15",
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=4.0,
        max_lot=1.0,
        risk_percent=0.5,            # SURVIVAL MODE: 0.5% (was 1.0%)
        min_confidence=0.40,         # Lower threshold (pure indicators)
        max_spread_points=30,
        pip_value_per_lot=10.0,
    ),
    "BTCUSD": PairParams(
        timeframe="H1",
        atr_sl_multiplier=2.5,
        atr_tp_multiplier=5.0,
        max_lot=0.1,
        risk_percent=0.5,            # SURVIVAL MODE: 0.5% (was 0.5%)
        min_confidence=0.40,         # Lower threshold (pure indicators)
        max_spread_points=50,
        pip_value_per_lot=1.0,
    ),
}


def get_pair_params(symbol: str) -> PairParams:
    """Get parameters for a symbol. Falls back to XAUUSD defaults."""
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["XAUUSD"])


def get_all_pairs() -> list:
    """Return list of all configured pair symbols."""
    return list(PAIR_CONFIG.keys())
