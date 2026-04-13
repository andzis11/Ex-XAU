"""
Layer 6 — Logging & Backtesting: Trade Journal database.
Records every trade, signal, and performance metric for analysis.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

from config import AppConfig, Symbol
from execution.signal_generator import TradeSignalResult, TradeSignal
from risk.manager import RiskAssessment

logger = logging.getLogger(__name__)


class TradeJournal:
    """
    Layer 6 — Trade Journal.
    Persists all trading activity to SQLite (or PostgreSQL).
    Enables performance analysis and strategy optimization.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.db_path = config.database.sqlite_path

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        # Initialize database
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                confluence_score REAL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                technical_score REAL,
                ml_signal TEXT,
                ml_confidence REAL,
                llm_signal TEXT,
                llm_confidence REAL,
                reasoning TEXT,
                key_factors TEXT,
                risk_approved INTEGER,
                risk_reason TEXT
            )
        """)

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                volume REAL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                exit_price REAL,
                exit_time TEXT,
                pnl REAL,
                commission REAL,
                net_pnl REAL,
                status TEXT DEFAULT 'OPEN',
                slippage REAL,
                execution_time_ms REAL,
                signal_id INTEGER,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)

        # Daily summary table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_trades INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                breakeven INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                gross_profit REAL DEFAULT 0,
                gross_loss REAL DEFAULT 0,
                avg_win REAL DEFAULT 0,
                avg_loss REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                profit_factor REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                end_equity REAL DEFAULT 0
            )
        """)

        # Performance metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                details TEXT
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"Trade journal initialized: {self.db_path}")

    def record_signal(
        self,
        signal: TradeSignalResult,
        risk_assessment: Optional[RiskAssessment] = None,
    ) -> int:
        """
        Record a trade signal (whether executed or not).

        Returns:
            signal_id for linking to trades
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signals (
                timestamp, symbol, signal, confluence_score,
                entry_price, stop_loss, take_profit,
                technical_score, ml_signal, ml_confidence,
                llm_signal, llm_confidence, reasoning, key_factors,
                risk_approved, risk_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            signal.symbol.value,
            signal.signal.value,
            signal.confluence_score,
            signal.entry_price,
            signal.recommended_stop_loss,
            signal.recommended_take_profit,
            signal.technical_agreement,
            signal.analysis_details.get("ml_prediction", {}).get("signal"),
            signal.analysis_details.get("ml_prediction", {}).get("confidence"),
            signal.analysis_details.get("llm_analysis", {}).get("signal") if signal.analysis_details.get("llm_analysis") else None,
            signal.analysis_details.get("llm_analysis", {}).get("confidence") if signal.analysis_details.get("llm_analysis") else None,
            signal.reasoning,
            json.dumps(signal.key_factors),
            1 if risk_assessment and risk_assessment.approved else 0,
            risk_assessment.reason if risk_assessment else None,
        ))

        signal_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return signal_id

    def record_trade_open(
        self,
        signal_id: int,
        ticket: int,
        symbol: Symbol,
        direction: str,
        volume: float,
        entry_price: float,
        sl: float,
        tp: float,
        execution_time_ms: float = 0,
    ) -> int:
        """Record an opened trade."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trades (
                ticket, timestamp, symbol, direction, volume,
                entry_price, stop_loss, take_profit, status,
                execution_time_ms, signal_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket,
            datetime.utcnow().isoformat(),
            symbol.value,
            direction,
            volume,
            entry_price,
            sl,
            tp,
            "OPEN",
            execution_time_ms,
            signal_id,
        ))

        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return trade_id

    def record_trade_close(
        self,
        ticket: int,
        exit_price: float,
        pnl: float,
        commission: float = 0,
    ) -> bool:
        """Record a closed trade with P&L."""
        conn = self._get_connection()
        cursor = conn.cursor()

        net_pnl = pnl - commission

        cursor.execute("""
            UPDATE trades SET
                exit_price = ?,
                exit_time = ?,
                pnl = ?,
                commission = ?,
                net_pnl = ?,
                status = ?
            WHERE ticket = ? AND status = 'OPEN'
        """, (
            exit_price,
            datetime.utcnow().isoformat(),
            pnl,
            commission,
            net_pnl,
            "CLOSED",
            ticket,
        ))

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if updated:
            logger.info(f"Trade {ticket} closed: P&L=${net_pnl:.2f}")
        else:
            logger.warning(f"Trade {ticket} not found or already closed")

        return updated

    def get_open_trades(self) -> list:
        """Get all open trades."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY timestamp DESC")
        trades = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return trades

    def get_recent_trades(self, limit: int = 50) -> list:
        """Get recent closed trades."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT ?",
            (limit,),
        )
        trades = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return trades

    def get_performance_summary(self) -> dict:
        """Calculate overall performance metrics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Basic stats
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN net_pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                SUM(net_pnl) as total_pnl,
                AVG(CASE WHEN net_pnl > 0 THEN net_pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN net_pnl < 0 THEN net_pnl ELSE NULL END) as avg_loss,
                SUM(CASE WHEN net_pnl > 0 THEN net_pnl ELSE 0 END) as gross_profit,
                SUM(CASE WHEN net_pnl < 0 THEN ABS(net_pnl) ELSE 0 END) as gross_loss
            FROM trades WHERE status = 'CLOSED'
        """)

        row = cursor.fetchone()
        if not row or row["total_trades"] == 0:
            conn.close()
            return {
                "total_trades": 0,
                "message": "No closed trades yet",
            }

        total = row["total_trades"]
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        total_pnl = row["total_pnl"] or 0
        gross_profit = row["gross_profit"] or 0
        gross_loss = row["gross_loss"] or 0

        win_rate = (wins / total * 100) if total > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        # Max drawdown calculation
        cursor.execute("""
            SELECT timestamp, net_pnl FROM trades
            WHERE status = 'CLOSED' ORDER BY exit_time ASC
        """)
        closed_trades = cursor.fetchall()

        max_dd = 0.0
        peak = 0.0
        running_pnl = 0.0
        for trade in closed_trades:
            running_pnl += trade["net_pnl"]
            if running_pnl > peak:
                peak = running_pnl
            dd = peak - running_pnl
            if dd > max_dd:
                max_dd = dd

        conn.close()

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": row["breakeven"] or 0,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(row["avg_win"] or 0, 2),
            "avg_loss": round(row["avg_loss"] or 0, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_dd, 2),
            "avg_rr": round(abs(row["avg_win"] or 0) / abs(row["avg_loss"] or 1), 2),
        }

    def get_daily_performance(self, days: int = 30) -> list:
        """Get daily performance for the last N days."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM daily_summary
            ORDER BY date DESC LIMIT ?
        """, (days,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def record_daily_summary(
        self,
        trade_data: dict,
        end_equity: float,
    ):
        """Record daily performance summary."""
        conn = self._get_connection()
        cursor = conn.cursor()

        today = datetime.utcnow().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT OR REPLACE INTO daily_summary (
                date, total_trades, wins, losses, breakeven,
                total_pnl, gross_profit, gross_loss,
                avg_win, avg_loss, win_rate, profit_factor,
                max_drawdown, end_equity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today,
            trade_data.get("total_trades", 0),
            trade_data.get("wins", 0),
            trade_data.get("losses", 0),
            trade_data.get("breakeven", 0),
            trade_data.get("total_pnl", 0),
            trade_data.get("gross_profit", 0),
            trade_data.get("gross_loss", 0),
            trade_data.get("avg_win", 0),
            trade_data.get("avg_loss", 0),
            trade_data.get("win_rate", 0),
            trade_data.get("profit_factor", 0),
            trade_data.get("max_drawdown", 0),
            end_equity,
        ))

        conn.commit()
        conn.close()
