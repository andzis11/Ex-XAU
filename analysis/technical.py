"""
Layer 2 — AI Analysis Engine: Technical Analysis module.
Computes classic indicators: EMA, RSI, MACD, Bollinger Bands, ATR.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False

from config import AppConfig, Symbol

logger = logging.getLogger(__name__)


@dataclass
class TechnicalSignals:
    """Container for all technical indicator signals."""
    # Trend
    ema_20_trend: str = "neutral"   # bullish / bearish / neutral
    ema_50_trend: str = "neutral"
    ema_200_trend: str = "neutral"
    ema_alignment: str = "neutral"  # bullish (20>50>200) / bearish (20<50<200) / mixed

    # Momentum
    rsi_value: float = 50.0
    rsi_signal: str = "neutral"     # overbought / oversold / neutral

    # MACD
    macd_histogram: float = 0.0
    macd_signal: str = "neutral"    # bullish / bearish / neutral

    # Bollinger Bands
    bb_position: str = "middle"     # upper_band / lower_band / middle / outside_upper / outside_lower
    bb_width_pct: float = 0.0

    # Volatility
    atr_value: float = 0.0

    # Price action
    current_price: float = 0.0

    # Composite score (-1 to +1): -1 = strong sell, +1 = strong buy
    composite_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ema_20_trend": self.ema_20_trend,
            "ema_50_trend": self.ema_50_trend,
            "ema_200_trend": self.ema_200_trend,
            "ema_alignment": self.ema_alignment,
            "rsi_value": round(self.rsi_value, 2),
            "rsi_signal": self.rsi_signal,
            "macd_histogram": round(self.macd_histogram, 4),
            "macd_signal": self.macd_signal,
            "bb_position": self.bb_position,
            "bb_width_pct": round(self.bb_width_pct, 2),
            "atr_value": round(self.atr_value, 4),
            "current_price": round(self.current_price, 4),
            "composite_score": round(self.composite_score, 4),
        }


class TechnicalAnalyzer:
    """
    Compute technical indicators from OHLCV data.
    Uses pandas-ta if available, falls back to manual calculation.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        ai = config.ai
        self.ema_periods = ai.ema_periods
        self.rsi_period = ai.rsi_period
        self.macd_fast = ai.macd_fast
        self.macd_slow = ai.macd_slow
        self.macd_signal_period = ai.macd_signal
        self.bb_period = ai.bb_period
        self.bb_std = ai.bb_std

    def analyze(self, df: pd.DataFrame, symbol: Symbol) -> Optional[TechnicalSignals]:
        """
        Run full technical analysis on OHLCV data.

        Args:
            df: DataFrame with columns [open, high, low, close, tick_volume]
            symbol: Trading symbol

        Returns:
            TechnicalSignals object with all indicator values
        """
        if df is None or df.empty or len(df) < 200:
            logger.warning(f"Insufficient data for {symbol} analysis (need >= 200 candles)")
            return None

        signals = TechnicalSignals()

        # Calculate all indicators
        self._calculate_ema(df, signals)
        self._calculate_rsi(df, signals)
        self._calculate_macd(df, signals)
        self._calculate_bollinger_bands(df, signals)
        self._calculate_atr(df, signals)

        # Current price
        signals.current_price = float(df["close"].iloc[-1])

        # Composite score
        signals.composite_score = self._compute_composite_score(signals)

        return signals

    def _calculate_ema(self, df: pd.DataFrame, signals: TechnicalSignals):
        """Calculate EMA trends and alignment."""
        if PANDAS_TA_AVAILABLE:
            ema20 = ta.ema(df["close"], length=self.ema_periods[0])
            ema50 = ta.ema(df["close"], length=self.ema_periods[1])
            ema200 = ta.ema(df["close"], length=self.ema_periods[2])
        else:
            ema20 = df["close"].ewm(span=self.ema_periods[0], adjust=False).mean()
            ema50 = df["close"].ewm(span=self.ema_periods[1], adjust=False).mean()
            ema200 = df["close"].ewm(span=self.ema_periods[2], adjust=False).mean()

        last_close = float(df["close"].iloc[-1])

        # Individual EMA trends
        signals.ema_20_trend = self._ema_trend(last_close, float(ema20.iloc[-1]))
        signals.ema_50_trend = self._ema_trend(last_close, float(ema50.iloc[-1]))
        signals.ema_200_trend = self._ema_trend(last_close, float(ema200.iloc[-1]))

        # EMA alignment (triple EMA crossover)
        e20, e50, e200 = float(ema20.iloc[-1]), float(ema50.iloc[-1]), float(ema200.iloc[-1])
        if e20 > e50 > e200:
            signals.ema_alignment = "bullish"
        elif e20 < e50 < e200:
            signals.ema_alignment = "bearish"
        else:
            signals.ema_alignment = "mixed"

    def _ema_trend(self, price: float, ema: float) -> str:
        if price > ema * 1.001:
            return "bullish"
        elif price < ema * 0.999:
            return "bearish"
        return "neutral"

    def _calculate_rsi(self, df: pd.DataFrame, signals: TechnicalSignals):
        """Calculate RSI and determine signal."""
        if PANDAS_TA_AVAILABLE:
            rsi = ta.rsi(df["close"], length=self.rsi_period)
        else:
            rsi = self._manual_rsi(df["close"], self.rsi_period)

        signals.rsi_value = float(rsi.iloc[-1])

        if signals.rsi_value > 70:
            signals.rsi_signal = "overbought"
        elif signals.rsi_value < 30:
            signals.rsi_signal = "oversold"
        else:
            signals.rsi_signal = "neutral"

    def _manual_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Manual RSI calculation as fallback."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_macd(self, df: pd.DataFrame, signals: TechnicalSignals):
        """Calculate MACD and determine signal."""
        if PANDAS_TA_AVAILABLE:
            macd_result = ta.macd(
                df["close"],
                fast=self.macd_fast,
                slow=self.macd_slow,
                signal=self.macd_signal_period,
            )
            macd_line = macd_result[f"MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal_period}"]
            macd_hist = macd_result[f"MACDh_{self.macd_fast}_{self.macd_slow}_{self.macd_signal_period}"]
        else:
            macd_line, macd_hist = self._manual_macd(df["close"])

        signals.macd_histogram = float(macd_hist.iloc[-1])

        if signals.macd_histogram > 0:
            signals.macd_signal = "bullish"
        elif signals.macd_histogram < 0:
            signals.macd_signal = "bearish"
        else:
            signals.macd_signal = "neutral"

    def _manual_macd(self, series: pd.Series):
        """Manual MACD calculation."""
        ema_fast = series.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = series.ewm(span=self.macd_slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.macd_signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, histogram

    def _calculate_bollinger_bands(self, df: pd.DataFrame, signals: TechnicalSignals):
        """Calculate Bollinger Bands position."""
        if PANDAS_TA_AVAILABLE:
            bb = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
            lower = bb[f"BBL_{self.bb_period}_{self.bb_std}"]
            middle = bb[f"BBM_{self.bb_period}_{self.bb_std}"]
            upper = bb[f"BBU_{self.bb_period}_{self.bb_std}"]
        else:
            sma = df["close"].rolling(window=self.bb_period).mean()
            std = df["close"].rolling(window=self.bb_period).std()
            lower = sma - self.bb_std * std
            middle = sma
            upper = sma + self.bb_std * std

        last_close = float(df["close"].iloc[-1])
        last_lower = float(lower.iloc[-1])
        last_upper = float(upper.iloc[-1])

        # Determine position
        if last_close > last_upper:
            signals.bb_position = "outside_upper"
        elif last_close < last_lower:
            signals.bb_position = "outside_lower"
        elif last_close > (last_upper + last_lower) / 2:
            signals.bb_position = "upper_band"
        elif last_close < (last_upper + last_lower) / 2:
            signals.bb_position = "lower_band"
        else:
            signals.bb_position = "middle"

        # BB width as % of price (squeeze indicator)
        bb_range = last_upper - last_lower
        signals.bb_width_pct = (bb_range / last_close) * 100

    def _calculate_atr(self, df: pd.DataFrame, signals: TechnicalSignals):
        """Calculate Average True Range."""
        if PANDAS_TA_AVAILABLE:
            atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        else:
            atr = self._manual_atr(df)

        signals.atr_value = float(atr.iloc[-1])

    def _manual_atr(self, df: pd.DataFrame) -> pd.Series:
        """Manual ATR calculation."""
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=14).mean()

    def _compute_composite_score(self, signals: TechnicalSignals) -> float:
        """
        Compute a composite score from -1 (strong sell) to +1 (strong buy).
        Weighted combination of all indicators.
        """
        score = 0.0
        weights = {
            "ema_alignment": 0.25,
            "rsi": 0.15,
            "macd": 0.20,
            "bb": 0.15,
            "trend": 0.15,
            "momentum": 0.10,
        }

        # EMA alignment (strong signal)
        if signals.ema_alignment == "bullish":
            score += weights["ema_alignment"]
        elif signals.ema_alignment == "bearish":
            score -= weights["ema_alignment"]

        # RSI (mean reversion signal)
        if signals.rsi_signal == "oversold":
            score += weights["rsi"]
        elif signals.rsi_signal == "overbought":
            score -= weights["rsi"]
        elif signals.rsi_value > 50:
            score += weights["rsi"] * 0.3
        else:
            score -= weights["rsi"] * 0.3

        # MACD
        if signals.macd_signal == "bullish":
            score += weights["macd"]
        elif signals.macd_signal == "bearish":
            score -= weights["macd"]

        # Bollinger Bands (mean reversion)
        if signals.bb_position == "outside_lower":
            score += weights["bb"]
        elif signals.bb_position == "outside_upper":
            score -= weights["bb"]
        elif signals.bb_position == "lower_band":
            score += weights["bb"] * 0.3
        elif signals.bb_position == "upper_band":
            score -= weights["bb"] * 0.3

        # Individual EMA trends
        bullish_count = sum(1 for t in [signals.ema_20_trend, signals.ema_50_trend] if t == "bullish")
        bearish_count = sum(1 for t in [signals.ema_20_trend, signals.ema_50_trend] if t == "bearish")
        score += (bullish_count - bearish_count) * weights["trend"] / 2

        return max(-1.0, min(1.0, score))
