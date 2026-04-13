"""
Layer 1 — Data Sources: Unified data pipeline.
Combines MT5/MetaAPI, news, and on-chain data into a single interface.
"""

import logging
from typing import Optional

import pandas as pd

from config import AppConfig, Symbol, Timeframe
from data.mt5_client import MT5DataClient
from data.metaapi_client import MetaAPIClient
from data.news_feed import NewsFeed

logger = logging.getLogger(__name__)


class DataPipeline:
    """
    Unified data pipeline for the trading bot.
    Abstracts away whether we use MT5 or MetaAPI.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.news_feed = NewsFeed(config)

        # Choose connection method
        if config.exness.use_metaapi:
            self.client = MetaAPIClient(config)
            self._connection_type = "MetaAPI"
        else:
            self.client = MT5DataClient(config)
            self._connection_type = "MT5"

    def connect(self) -> bool:
        """Establish connection to data source."""
        logger.info(f"Connecting via {self._connection_type}...")
        return self.client.connect()

    def disconnect(self):
        """Close connection."""
        self.client.disconnect()

    @property
    def connected(self) -> bool:
        return self.client.connected

    def get_ohlcv(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        count: int = 1000
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data.
        Returns DataFrame indexed by time with columns: open, high, low, close, tick_volume
        """
        return self.client.get_rates(symbol, timeframe, count)

    def get_current_price(self, symbol: Symbol) -> Optional[dict]:
        """Get current bid/ask price."""
        return self.client.get_tick(symbol)

    def get_symbol_specs(self, symbol: Symbol) -> Optional[dict]:
        """Get symbol specifications."""
        return self.client.get_symbol_info(symbol)

    def get_account_info(self) -> Optional[dict]:
        """Get account information."""
        return self.client.get_account_info()

    def get_market_context(self, symbol: Symbol) -> dict:
        """
        Get comprehensive market context for a symbol.
        Combines price data, news, and sentiment.
        """
        context = {
            "symbol": str(symbol),
            "price": self.get_current_price(symbol),
            "specs": self.get_symbol_specs(symbol),
            "account": self.get_account_info(),
            "news": self.news_feed.get_market_sentiment_summary(),
            "news_blackout": self.news_feed.is_news_blackout(),
        }

        # Fetch recent OHLCV for context
        df = self.get_ohlcv(symbol, self.config.trading.timeframe, count=100)
        if df is not None and not df.empty:
            context["recent_close"] = df["close"].iloc[-1]
            context["recent_change_pct"] = (
                (df["close"].iloc[-1] - df["close"].iloc[-5]) / df["close"].iloc[-5] * 100
            )

        return context
