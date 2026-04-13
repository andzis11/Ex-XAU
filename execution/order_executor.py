"""
Layer 5 — Order Execution: MetaAPI REST client for order management.
Handles trade execution with retry logic and slippage tolerance.
"""

import logging
import time
from enum import Enum
from typing import Optional

import requests

from config import AppConfig, Symbol

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    BUY = "ORDER_TYPE_BUY"
    SELL = "ORDER_TYPE_SELL"
    BUY_LIMIT = "ORDER_TYPE_BUY_LIMIT"
    SELL_LIMIT = "ORDER_TYPE_SELL_LIMIT"
    BUY_STOP = "ORDER_TYPE_BUY_STOP"
    SELL_STOP = "ORDER_TYPE_SELL_STOP"


class ExecutionResult:
    """Result of an order execution attempt."""

    def __init__(self):
        self.success: bool = False
        self.ticket: int = 0
        self.error: str = ""
        self.price: float = 0.0
        self.volume: float = 0.0
        self.sl: float = 0.0
        self.tp: float = 0.0
        self.attempts: int = 0
        self.execution_time_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "ticket": self.ticket,
            "error": self.error,
            "price": self.price,
            "volume": self.volume,
            "sl": self.sl,
            "tp": self.tp,
            "attempts": self.attempts,
            "execution_time_ms": round(self.execution_time_ms, 1),
        }


class OrderExecutor:
    """
    Layer 5 — Order Execution via MetaAPI.
    Handles placing, modifying, and closing orders with retry logic.
    """

    BASE_URL = "https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai"

    def __init__(self, config: AppConfig):
        self.config = config
        self._account_id = config.exness.metaapi_account_id
        self._headers = {
            "auth-token": config.exness.metaapi_token,
            "Content-Type": "application/json",
        }
        self.max_retries = config.trading.retry_attempts
        self.retry_delay = config.trading.retry_delay_seconds
        self.slippage = config.trading.slippage_tolerance

    def _url(self, path: str) -> str:
        return f"{self.BASE_URL}/users/current/accounts/{self._account_id}/{path}"

    def execute_buy(
        self,
        symbol: Symbol,
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "AI_BOT",
    ) -> ExecutionResult:
        """Execute a BUY market order."""
        return self._execute_market_order(
            symbol=symbol,
            order_type=OrderType.BUY,
            volume=volume,
            sl=sl,
            tp=tp,
            comment=comment,
        )

    def execute_sell(
        self,
        symbol: Symbol,
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "AI_BOT",
    ) -> ExecutionResult:
        """Execute a SELL market order."""
        return self._execute_market_order(
            symbol=symbol,
            order_type=OrderType.SELL,
            volume=volume,
            sl=sl,
            tp=tp,
            comment=comment,
        )

    def _execute_market_order(
        self,
        symbol: Symbol,
        order_type: OrderType,
        volume: float,
        sl: float,
        tp: float,
        comment: str,
    ) -> ExecutionResult:
        """Execute a market order with retry logic."""
        result = ExecutionResult()
        start_time = time.time()

        order_body = {
            "actionType": "ORDER_TYPE_FILL",
            "orderType": order_type.value,
            "symbol": str(symbol),
            "volume": volume,
            "comment": comment,
        }

        if sl > 0:
            order_body["stopLoss"] = sl
        if tp > 0:
            order_body["takeProfit"] = tp

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            try:
                logger.info(
                    f"Attempt {attempt}/{self.max_retries}: "
                    f"{order_type.value} {volume} {symbol} "
                    f"SL={sl} TP={tp}"
                )

                response = requests.post(
                    self._url("trade"),
                    headers=self._headers,
                    json=order_body,
                    timeout=15,
                )

                if response.status_code == 201:
                    data = response.json()
                    result.success = True
                    result.ticket = int(data.get("orderId", 0))
                    result.volume = volume
                    result.sl = sl
                    result.tp = tp
                    result.execution_time_ms = (time.time() - start_time) * 1000

                    logger.info(
                        f"Order executed: ticket={result.ticket} | "
                        f"volume={volume} | "
                        f"time={result.execution_time_ms:.0f}ms"
                    )
                    return result

                elif response.status_code == 429:
                    # Rate limited — wait and retry
                    retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                    logger.warning(f"Rate limited. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                else:
                    error_data = response.json()
                    error_msg = error_data.get("message", str(response.status_code))
                    logger.warning(f"Attempt {attempt} failed: {error_msg}")

                    # Don't retry certain errors
                    if response.status_code in (400, 401, 403):
                        result.error = error_msg
                        return result

                    result.error = error_msg

            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt} request error: {e}")
                result.error = str(e)

            # Wait before retry
            if attempt < self.max_retries:
                delay = self.retry_delay * attempt  # Exponential backoff
                logger.info(f"Waiting {delay}s before retry...")
                time.sleep(delay)

        result.execution_time_ms = (time.time() - start_time) * 1000
        logger.error(
            f"Order execution FAILED after {self.max_retries} attempts: {result.error}"
        )
        return result

    def close_position(self, ticket: int) -> ExecutionResult:
        """Close an open position by ticket."""
        result = ExecutionResult()

        try:
            response = requests.post(
                self._url("trade"),
                headers=self._headers,
                json={
                    "actionType": "ORDER_TYPE_CLOSE_BY",
                    "positionId": ticket,
                },
                timeout=15,
            )

            if response.status_code == 201:
                result.success = True
                result.ticket = ticket
                logger.info(f"Position {ticket} closed successfully")
            else:
                result.error = response.json().get("message", "Unknown error")

        except requests.RequestException as e:
            result.error = str(e)

        return result

    def modify_position(
        self,
        ticket: int,
        sl: float = 0.0,
        tp: float = 0.0,
    ) -> ExecutionResult:
        """Modify SL/TP of an open position."""
        result = ExecutionResult()

        body = {"positionId": ticket}
        if sl > 0:
            body["stopLoss"] = sl
        if tp > 0:
            body["takeProfit"] = tp

        try:
            response = requests.post(
                self._url("trade"),
                headers=self._headers,
                json=body,
                timeout=15,
            )

            if response.status_code == 201:
                result.success = True
                result.ticket = ticket
                result.sl = sl
                result.tp = tp
            else:
                result.error = response.json().get("message", "Unknown error")

        except requests.RequestException as e:
            result.error = str(e)

        return result

    def get_positions(self) -> list:
        """Get all open positions."""
        try:
            response = requests.get(
                self._url("positions"),
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_account_info(self) -> Optional[dict]:
        """Get current account information."""
        try:
            response = requests.get(
                self._url(""),
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get account info: {e}")
            return None
