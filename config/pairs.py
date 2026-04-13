"""
Pair-specific configuration for XAU/USD and BTC/USD.
Parameters differ per instrument based on volatility characteristics.
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
    risk_percent: float           # Risk % per trade
    min_confidence: float         # Minimum model confidence to enter
    max_spread_points: int        # Max acceptable spread before skipping
    pip_value_per_lot: float      # $ value per pip per standard lot


# Parameter table per the spec
PAIR_CONFIG: Dict[str, PairParams] = {
    "XAUUSD": PairParams(
        timeframe="M15",
        atr_sl_multiplier=1.5,
        atr_tp_multiplier=3.0,
        max_lot=1.0,
        risk_percent=1.0,
        min_confidence=0.70,
        max_spread_points=30,
        pip_value_per_lot=10.0,     # $10 per pip per lot
    ),
    "BTCUSD": PairParams(
        timeframe="H1",
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=4.0,
        max_lot=0.1,
        risk_percent=0.5,
        min_confidence=0.75,
        max_spread_points=50,
        pip_value_per_lot=1.0,      # $1 per pip per lot
    ),
}


def get_pair_params(symbol: str) -> PairParams:
    """Get parameters for a symbol. Falls back to XAUUSD defaults."""
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["XAUUSD"])


def get_all_pairs() -> list:
    """Return list of all configured pair symbols."""
    return list(PAIR_CONFIG.keys())
