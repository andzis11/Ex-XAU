"""
Pair-specific configuration for XAU/USD and BTC/USD.
SCALPING MODE — tight SL, quick TP, high frequency.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class PairParams:
    """Trading parameters for a single symbol."""
    timeframe: str                # M5 for scalping
    atr_sl_multiplier: float      # ATR multiplier for stop loss (tight)
    atr_tp_multiplier: float      # ATR multiplier for take profit (quick)
    max_lot: float                # Maximum lot size
    risk_percent: float           # Risk % per trade (higher for scalping)
    min_confidence: float         # Minimum signal score to enter
    max_spread_points: int        # Max acceptable spread
    pip_value_per_lot: float      # $ value per pip per standard lot


# SCALPING parameters — tight SL, quick TP, high frequency
PAIR_CONFIG: Dict[str, PairParams] = {
    "XAUUSD": PairParams(
        timeframe="M5",                       # Fast signals
        atr_sl_multiplier=1.0,                # Tight SL (was 2.0)
        atr_tp_multiplier=1.5,                # Quick TP (was 4.0)
        max_lot=1.0,
        risk_percent=1.0,                     # Higher risk (SL is tighter)
        min_confidence=0.50,                  # Higher quality entries
        max_spread_points=25,                 # Tighter spread limit
        pip_value_per_lot=10.0,
    ),
    "BTCUSD": PairParams(
        timeframe="M5",
        atr_sl_multiplier=1.2,                # Tight SL
        atr_tp_multiplier=1.8,                # Quick TP
        max_lot=0.1,
        risk_percent=1.0,
        min_confidence=0.50,
        max_spread_points=40,
        pip_value_per_lot=1.0,
    ),
}


def get_pair_params(symbol: str) -> PairParams:
    """Get parameters for a symbol."""
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["XAUUSD"])


def get_all_pairs() -> list:
    """Return list of all configured pair symbols."""
    return list(PAIR_CONFIG.keys())
