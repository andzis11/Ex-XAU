"""
Layer 1 — Data Sources: MetaAPI cloud connection.
Works on any platform (Linux/Windows) without MT5 terminal.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

from config import AppConfig, Symbol, Timeframe

logger = logging.getLogger(__name__)


class MetaAPIClient:
    """Cloud-based connection to Exness via MetaAPI."""

    BASE_URL = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
    TRADING_URL = "https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai"

    # Map timeframe to MetaAPI interval strings
    _TIMEFRAME_MAP = {
        Timeframe.M1: "1m",
        Timeframe.M5: "5m",
        Timeframe.M15: "15m",
        Timeframe.M30: "30m",
        Timeframe.H1: "1h",
        Timeframe.H4: "4h",
        Timeframe.D1: "1d",
    }

    def __init__(self, config: AppConfig):
        self.config = config
        self._connected = False

    @property
    def headers(self) -> dict:
        return {
            "auth-token": self.config.exness.metaapi_token,
            "Content-Type": "application/json",
        }

    def connect(self) -> bool:
        """Verify connection by fetching account info."""
        account_id = self.config.exness.metaapi_account_id
        if not account_id:
            logger.error("No MetaAPI account ID configured")
            return False

        try:
            url = f"{self.BASE_URL}/users/current/accounts/{account_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            logger.info(
                f"MetaAPI Connected | Account: {account_id} | "
                f"Platform: {data.get('platform', 'N/A')} | "
                f"Type: {data.get('type', 'N/A')}"
            )
            self._connected = True
            return True

        except requests.RequestException as e:
            logger.error(f"MetaAPI connection failed: {e}")
            return False

    def disconnect(self):
        self._connected = False
        logger.info("MetaAPI disconnected")

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
        Fetch OHLCV candles via MetaAPI.
        """
        if not self._connected:
            logger.error("Not connected to MetaAPI")
            return None

        account_id = self.config.exness.metaapi_account_id
        tf = self._TIMEFRAME_MAP.get(timeframe)

        try:
            url = (
                f"{self.TRADING_URL}/users/current/accounts/{account_id}"
                f"/history/candles"
            )
            params = {
                "symbol": str(symbol),
                "timeframe": tf,
                "limit": count,
            }

            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()

            candles = response.json()
            if not candles:
                logger.warning(f"No candle data for {symbol} {timeframe}")
                return None

            df = pd.DataFrame(candles)
            df["time"] = pd.to_datetime(df["time"])
            df.set_index("time", inplace=True)
            df = df[["open", "high", "low", "close", "tickVolume"]].rename(
                columns={"tickVolume": "tick_volume"}
            )
            return df

        except requests.RequestException as e:
            logger.error(f"Failed to get rates for {symbol}: {e}")
            return None

    def get_tick(self, symbol: Symbol) -> Optional[dict]:
        """Get current price for a symbol."""
        if not self._connected:
            return None

        account_id = self.config.exness.metaapi_account_id

        try:
            url = (
                f"{self.TRADING_URL}/users/current/accounts/{account_id}"
                f"/market-data/{symbol}"
            )
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return {
                "symbol": str(symbol),
                "bid": data.get("bid"),
                "ask": data.get("ask"),
                "last": data.get("last"),
                "spread": data.get("ask", 0) - data.get("bid", 0),
            }

        except requests.RequestException as e:
            logger.error(f"Failed to get tick for {symbol}: {e}")
            return None

    def get_symbol_info(self, symbol: Symbol) -> Optional[dict]:
        """Get symbol specifications."""
        if not self._connected:
            return None

        account_id = self.config.exness.metaapi_account_id

        try:
            url = (
                f"{self.TRADING_URL}/users/current/accounts/{account_id}"
                f"/symbols/{symbol}/specification"
            )
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return {
                "symbol": str(symbol),
                "point": data.get("point"),
                "digits": data.get("digits"),
                "spread": data.get("spread"),
                "volume_min": data.get("minVolume"),
                "volume_max": data.get("maxVolume"),
                "volume_step": data.get("volumeStep"),
            }

        except requests.RequestException as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
            return None

    def get_account_info(self) -> Optional[dict]:
        """Get account information via MetaAPI."""
        if not self._connected:
            return None

        account_id = self.config.exness.metaapi_account_id

        try:
            url = f"{self.TRADING_URL}/users/current/accounts/{account_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return {
                "balance": data.get("balance"),
                "equity": data.get("equity"),
                "margin": data.get("margin"),
                "margin_free": data.get("freeMargin"),
                "leverage": data.get("leverage"),
            }

        except requests.RequestException as e:
            logger.error(f"Failed to get account info: {e}")
            return None
