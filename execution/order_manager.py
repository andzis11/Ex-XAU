"""
Layer 5 — Order Manager.
Handles open/close order execution via MT5.
"""

import logging
from typing import Optional

import MetaTrader5 as mt5

from config.settings import BotConfig

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Executes market orders, modifies SL/TP, and closes positions via MT5.
    """

    def __init__(self, config: BotConfig):
        self.magic = config.magic_number
        self.deviation = config.deviation

    def open_order(
        self,
        symbol: str,
        signal: str,
        lot: float,
        sl: float,
        tp: float,
    ) -> Optional[dict]:
        """
        Open a market order (BUY or SELL).

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            signal: "BUY" or "SELL"
            lot: Position size
            sl: Stop loss price
            tp: Take profit price

        Returns:
            Order result dict or None on failure
        """
        order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick for {symbol}")
            return None

        price = tick.ask if signal == "BUY" else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": f"AI_BOT_{signal}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        logger.info(
            f"Sending order: {symbol} {signal} | "
            f"lot={lot} | price={price} | SL={sl} | TP={tp}"
        )

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"❌ Order failed [{symbol}]: {result.comment} (code: {result.retcode})")
            return None

        logger.info(
            f"✅ Order opened: {symbol} {signal} | "
            f"Ticket: {result.order} | Lot: {lot} | Price: {result.price}"
        )

        return {
            "ticket": result.order,
            "price": result.price,
            "volume": lot,
            "symbol": symbol,
            "direction": signal,
        }

    def close_position(self, ticket: int, symbol: str) -> bool:
        """
        Close a specific position by ticket.

        Args:
            ticket: Position ticket number
            symbol: Trading symbol

        Returns:
            True if closed successfully
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"Position {ticket} not found")
            return False

        pos = positions[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False

        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "AI_BOT_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Failed to close {ticket}: {result.comment}")
            return False

        logger.info(f"✅ Position {ticket} closed at {price}")
        return True

    def close_all_positions(self, symbol: str) -> int:
        """
        Close all open positions for a symbol.

        Returns:
            Number of positions closed
        """
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return 0

        count = 0
        for pos in positions:
            if self.close_position(pos.ticket, symbol):
                count += 1

        logger.info(f"Closed {count} position(s) for {symbol}")
        return count

    def modify_position(
        self,
        ticket: int,
        sl: float = 0.0,
        tp: float = 0.0,
    ) -> bool:
        """
        Modify SL/TP of an open position.

        Args:
            ticket: Position ticket
            sl: New stop loss (0 to keep unchanged)
            tp: New take profit (0 to keep unchanged)

        Returns:
            True if modified successfully
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False

        pos = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "sl": round(sl, 2) if sl > 0 else pos.sl,
            "tp": round(tp, 2) if tp > 0 else pos.tp,
            "position": ticket,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Failed to modify {ticket}: {result.comment}")
            return False

        logger.info(f"Position {ticket} modified: SL={sl}, TP={tp}")
        return True
