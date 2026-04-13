"""
Layer 5 — Exness MT5 Broker Connection.
Handles initialization, login, and connection lifecycle.
"""

import logging

import MetaTrader5 as mt5

from config.settings import BrokerConfig

logger = logging.getLogger(__name__)


class ExnessBroker:
    """
    Manages connection to Exness via MetaTrader 5.
    Supports both real and demo accounts.
    """

    def __init__(self, config: BrokerConfig):
        self.config = config
        self._connected = False

    def connect(self) -> bool:
        """
        Initialize MT5 and login to Exness.

        Returns:
            True if connection successful
        """
        if not mt5.initialize():
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        login_args = {
            "login": self.config.login,
            "password": self.config.password,
        }
        if self.config.server:
            login_args["server"] = self.config.server

        authorized = mt5.login(**login_args)

        if authorized:
            self._connected = True
            account = mt5.account_info()
            if account:
                logger.info(
                    f"✅ Connected to Exness | "
                    f"Account: {self.config.login} | "
                    f"Balance: ${account.balance:.2f} | "
                    f"Server: {account.server}"
                )
            return True
        else:
            error = mt5.last_error()
            logger.error(f"❌ Login failed: {error}")
            return False

    def disconnect(self):
        """Shutdown MT5 connection."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("Disconnected from MT5")

    @property
    def connected(self) -> bool:
        return self._connected

    def get_account_balance(self) -> float:
        """Get current account balance."""
        info = mt5.account_info()
        return info.balance if info else 0.0

    def get_account_equity(self) -> float:
        """Get current account equity."""
        info = mt5.account_info()
        return info.equity if info else 0.0

    def get_account_info(self) -> dict:
        """Get full account information."""
        info = mt5.account_info()
        if not info:
            return {}
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
            "server": info.server,
        }
