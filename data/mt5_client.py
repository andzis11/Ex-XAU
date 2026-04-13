"""
Layer 1 — Data Sources: MetaTrader 5 direct connection.
Works on Windows VPS with MT5 terminal installed.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

from config import AppConfig, Symbol, Timeframe

logger = logging.getLogger(__name__)


class MT5DataClient:
    """Direct connection to Exness via MetaTrader 5 terminal."""

    # Map our timeframe enum to MT5 constants
    _TIMEFRAME_MAP = {
        Timeframe.M1: mt5.TIMEFRAME_M1 if MT5_AVAILABLE else None,
        Timeframe.M5: mt5.TIMEFRAME_M5 if MT5_AVAILABLE else None,
        Timeframe.M15: mt5.TIMEFRAME_M15 if MT5_AVAILABLE else None,
        Timeframe.M30: mt5.TIMEFRAME_M30 if MT5_AVAILABLE else None,
        Timeframe.H1: mt5.TIMEFRAME_H1 if MT5_AVAILABLE else None,
        Timeframe.H4: mt5.TIMEFRAME_H4 if MT5_AVAILABLE else None,
        Timeframe.D1: mt5.TIMEFRAME_D1 if MT5_AVAILABLE else None,
    }

    def __init__(self, config: AppConfig):
        self.config = config
        self._connected = False

    def connect(self) -> bool:
        """Initialize MT5 connection with Exness."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 library not installed. Use pip install MetaTrader5")
            return False

        exness = self.config.exness

        # Initialize MT5
        if not mt5.initialize():
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        # Login if credentials provided
        if exness.mt5_login and exness.mt5_password:
            result = mt5.login(
                login=int(exness.mt5_login),
                password=exness.mt5_password,
                server=exness.mt5_server if exness.mt5_server else None
            )
            if not result:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False

        self._connected = True
        account_info = mt5.account_info()
        if account_info:
            logger.info(
                f"MT5 Connected | Account: {account_info.login} | "
                f"Balance: ${account_info.balance:.2f} | "
                f"Server: {account_info.server}"
            )
        return True

    def disconnect(self):
        """Close MT5 connection."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    def get_rates(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        count: int = 1000
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV rates for a symbol.

        Returns DataFrame with columns: time, open, high, low, close, tick_volume
        """
        if not self._connected:
            logger.error("Not connected to MT5")
            return None

        tf = self._TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            logger.error(f"Unsupported timeframe: {timeframe}")
            return None

        rates = mt5.copy_rates_from_pos(str(symbol), tf, 0, count)
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        return df

    def get_tick(self, symbol: Symbol) -> Optional[dict]:
        """Get current tick (bid/ask) for a symbol."""
        if not self._connected:
            return None

        tick = mt5.symbol_info_tick(str(symbol))
        if tick is None:
            return None

        return {
            "symbol": str(symbol),
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "time": datetime.fromtimestamp(tick.time),
            "spread": tick.ask - tick.bid,
        }

    def get_symbol_info(self, symbol: Symbol) -> Optional[dict]:
        """Get symbol specifications (lot size, spread, etc.)."""
        if not self._connected:
            return None

        info = mt5.symbol_info(str(symbol))
        if info is None:
            return None

        return {
            "symbol": str(symbol),
            "point": info.point,
            "digits": info.digits,
            "spread": info.spread,
            "trade_stops_level": info.trade_stops_level,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "margin_initial": info.margin_initial,
        }

    def get_account_info(self) -> Optional[dict]:
        """Get current account information."""
        if not self._connected:
            return None

        info = mt5.account_info()
        if info is None:
            return None

        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
        }

    def get_positions(self, symbol: Optional[Symbol] = None) -> list:
        """Get open positions, optionally filtered by symbol."""
        if not self._connected:
            return []

        if symbol:
            positions = mt5.positions_get(symbol=str(symbol))
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "time": datetime.fromtimestamp(p.time),
            }
            for p in positions
        ]

    def get_orders(self) -> list:
        """Get pending orders."""
        if not self._connected:
            return []

        orders = mt5.orders_get()
        if orders is None:
            return []

        return [
            {
                "ticket": o.ticket,
                "symbol": o.symbol,
                "type": str(o.type),
                "volume": o.volume,
                "price_open": o.price_open,
                "sl": o.sl,
                "tp": o.tp,
            }
            for o in orders
        ]
