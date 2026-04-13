"""
Layer 1 — Indicators module.
Computes RSI, MACD, Bollinger Bands, ATR, EMA using the `ta` library.
"""

import logging

import pandas as pd

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False

logger = logging.getLogger(__name__)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all technical indicators to OHLCV DataFrame.

    Indicators added:
    - RSI (14-period)
    - MACD (12/26/9) → macd, macd_signal, macd_diff
    - Bollinger Bands (20, 2σ) → bb_upper, bb_lower, bb_mid
    - ATR (14-period)
    - EMA 20, EMA 50

    Returns DataFrame with all indicator columns.
    """
    if not TA_AVAILABLE:
        logger.error("ta library not installed. Install with: pip install ta")
        return df

    df = df.copy()

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # MACD
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["close"])
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()

    # ATR
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"]
    ).average_true_range()

    # EMA
    df["ema_20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema_50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    # Drop NaN rows created by indicator warmup
    df.dropna(inplace=True)

    logger.info(f"Indicators added. {len(df)} candles remaining after dropna")
    return df
