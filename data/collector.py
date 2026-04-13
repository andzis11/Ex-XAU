"""
Layer 1 — Data Collector.
Fetches OHLCV data from MT5 and adds technical indicators.
"""

import logging
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from data.indicators import add_indicators

logger = logging.getLogger(__name__)


class DataCollector:
    """
    Fetches market data from MT5 and prepares it for analysis.
    """

    PAIRS = ["XAUUSD", "BTCUSD"]

    # Map timeframe strings to MT5 constants
    _TF_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "M15",
        bars: int = 500,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV rates from MT5.

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            timeframe: MT5 timeframe string (M15, H1, H4, etc.)
            bars: Number of bars to fetch

        Returns:
            DataFrame with columns: time, open, high, low, close, tick_volume
        """
        tf = self._TF_MAP.get(timeframe, mt5.TIMEFRAME_M15)

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)

        # Rename volume column for consistency
        if "tick_volume" not in df.columns and "volume" in df.columns:
            df.rename(columns={"volume": "tick_volume"}, inplace=True)

        logger.info(f"Fetched {len(df)} bars for {symbol} [{timeframe}]")
        return df

    def get_tick(self, symbol: str) -> Optional[dict]:
        """Get current tick (bid/ask/spread) for a symbol."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "spread": tick.ask - tick.bid,
            "time": tick.time,
        }

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Get symbol specifications."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        return {
            "point": info.point,
            "digits": info.digits,
            "spread": info.spread,
            "trade_stops_level": info.trade_stops_level,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
        }

    def get_indicators(self, symbol: str, timeframe: str = "M15", bars: int = 500) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV and add all technical indicators in one call.

        Returns:
            DataFrame with OHLCV + RSI, MACD, BB, ATR, EMA columns
        """
        df = self.get_ohlcv(symbol, timeframe, bars)
        if df is None:
            return None

        df = add_indicators(df)
        return df

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to an existing OHLCV DataFrame."""
        return add_indicators(df)
