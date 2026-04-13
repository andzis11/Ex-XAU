"""
Layer 5 — Portfolio Tracker.
Tracks all open positions across XAU/USD and BTC/USD.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a single open trade."""
    ticket: int
    symbol: str
    direction: str       # "BUY" or "SELL"
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    open_time: datetime
    comment: str = ""
    pnl: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "direction": self.direction,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "open_time": self.open_time.isoformat(),
            "pnl": round(self.pnl, 2),
        }


class Portfolio:
    """
    Tracks all active positions per symbol.
    Provides filtering, summary, and position management.
    """

    def __init__(self):
        self.positions: Dict[int, Position] = {}  # ticket -> Position

    def refresh(self) -> List[Position]:
        """
        Refresh positions from MT5.
        Returns list of current open positions.
        """
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            self.positions.clear()
            return []

        self.positions.clear()
        for pos in mt5_positions:
            self.positions[pos.ticket] = Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                direction="BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                volume=pos.volume,
                entry_price=pos.price_open,
                stop_loss=pos.sl,
                take_profit=pos.tp,
                open_time=datetime.fromtimestamp(pos.time),
                comment=pos.comment,
                pnl=pos.profit,
            )

        logger.info(f"Portfolio refreshed: {len(self.positions)} open positions")
        return list(self.positions.values())

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get positions, optionally filtered by symbol."""
        if symbol:
            return [p for p in self.positions.values() if p.symbol == symbol]
        return list(self.positions.values())

    def get_positions_for_symbol(self, symbol: str) -> List[Position]:
        """Get all open positions for a specific symbol."""
        return [p for p in self.positions.values() if p.symbol == symbol]

    def count_positions(self, symbol: Optional[str] = None) -> int:
        """Count open positions, optionally per symbol."""
        return len(self.get_positions(symbol))

    def total_pnl(self) -> float:
        """Get total unrealized P&L across all positions."""
        return sum(p.pnl for p in self.positions.values())

    def total_pnl_symbol(self, symbol: str) -> float:
        """Get total P&L for a specific symbol."""
        return sum(p.pnl for p in self.positions.values() if p.symbol == symbol)

    def summary(self) -> dict:
        """Get portfolio summary."""
        by_symbol = {}
        for p in self.positions.values():
            if p.symbol not in by_symbol:
                by_symbol[p.symbol] = {"count": 0, "pnl": 0.0, "volume": 0.0}
            by_symbol[p.symbol]["count"] += 1
            by_symbol[p.symbol]["pnl"] += p.pnl
            by_symbol[p.symbol]["volume"] += p.volume

        return {
            "total_positions": len(self.positions),
            "total_pnl": round(self.total_pnl(), 2),
            "by_symbol": {
                sym: {k: round(v, 2) if isinstance(v, float) else v for k, v in info.items()}
                for sym, info in by_symbol.items()
            },
        }

    def find_by_ticket(self, ticket: int) -> Optional[Position]:
        """Find a position by ticket number."""
        return self.positions.get(ticket)
