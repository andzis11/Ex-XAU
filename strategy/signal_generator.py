"""
Layer 3 — Signal Generator (SIMPLIFIED).
Pure indicator-based signals. No LSTM dependency.
Combines EMA crossover, RSI, MACD, Bollinger Bands with EMA200 trend filter.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.pairs import PairParams, get_pair_params

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """Final trade signal output."""
    symbol: str
    direction: str           # "BUY" | "SELL" | "HOLD"
    confidence: float        # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    reasons: list            # Human-readable reasons

    @property
    def is_valid(self) -> bool:
        return self.direction in ("BUY", "SELL") and self.confidence > 0


class SignalGenerator:
    """
    Pure indicator-based signal generator.
    No ML/LSTM — just proven technical confluence.

    Scoring:
    - EMA crossover: 0.35 (trend change)
    - EMA trend: 0.15 (direction alignment)
    - RSI filter: 0.25 (momentum confirmation)
    - MACD: 0.20 (momentum direction)
    - Bollinger Bands: 0.20 (overbought/oversold)
    - EMA200 bias: multiplier (trend filter)
    """

    def __init__(
        self,
        ema200_trend_bias: float = 0.30,
        min_confidence: float = 0.40,
    ):
        self.ema200_trend_bias = ema200_trend_bias
        self.min_confidence = min_confidence

    def generate(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> TradeSignal:
        """
        Generate trade signal from pure indicators.

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            df: OHLCV DataFrame with indicators

        Returns:
            TradeSignal with direction, confidence, SL, TP
        """
        pair_params = get_pair_params(symbol)
        entry_price = float(df["close"].iloc[-1])
        atr = float(df["atr"].iloc[-1])

        if len(df) < 2:
            return TradeSignal(
                symbol=symbol, direction="HOLD", confidence=0.0,
                entry_price=entry_price, stop_loss=0, take_profit=0,
                atr=atr, reasons=["Insufficient data"],
            )

        row = df.iloc[-1]
        prev = df.iloc[-2]
        buy_score = 0.0
        sell_score = 0.0
        reasons = []

        # ── 1. EMA Crossover (bobot 0.35) ──
        ema_cross_up = (
            prev["ema_20"] <= prev["ema_50"]
            and row["ema_20"] > row["ema_50"]
        )
        ema_cross_down = (
            prev["ema_20"] >= prev["ema_50"]
            and row["ema_20"] < row["ema_50"]
        )
        ema_trend_bull = row["ema_20"] > row["ema_50"]
        ema_trend_bear = row["ema_20"] < row["ema_50"]

        if ema_cross_up:
            buy_score += 0.35
            reasons.append("EMA crossover UP")
        elif ema_trend_bull:
            buy_score += 0.15
            reasons.append("EMA trend bull")

        if ema_cross_down:
            sell_score += 0.35
            reasons.append("EMA crossover DOWN")
        elif ema_trend_bear:
            sell_score += 0.15
            reasons.append("EMA trend bear")

        # ── 2. RSI Filter (bobot 0.25) ──
        rsi = float(row["rsi"])
        if rsi < 50 and rsi > 35:
            buy_score += 0.25
            reasons.append(f"RSI bullish ({rsi:.0f})")
        elif rsi > 50 and rsi < 65:
            sell_score += 0.25
            reasons.append(f"RSI bearish ({rsi:.0f})")

        # ── 3. MACD (bobot 0.20) ──
        if float(row["macd"]) > float(row["macd_signal"]) and float(row["macd_diff"]) > 0:
            buy_score += 0.20
            reasons.append("MACD bull")
        elif float(row["macd"]) < float(row["macd_signal"]) and float(row["macd_diff"]) < 0:
            sell_score += 0.20
            reasons.append("MACD bear")

        # ── 4. Bollinger Band (bobot 0.20) ──
        close = float(row["close"])
        bb_upper = float(row["bb_upper"])
        bb_lower = float(row["bb_lower"])
        bb_mid = float(row["bb_mid"])

        if close < bb_lower:
            buy_score += 0.20
            reasons.append("BB oversold")
        elif close > bb_upper:
            sell_score += 0.20
            reasons.append("BB overbought")
        elif close > bb_mid:
            buy_score += 0.10
        else:
            sell_score += 0.10

        # ── 5. EMA200 Trend Filter (bias multiplier) ──
        ema200 = float(row.get("ema200", 0))
        if ema200 > 0:
            above_ema200 = close > ema200
            if above_ema200:
                buy_score *= (1 + self.ema200_trend_bias)
                sell_score *= (1 - self.ema200_trend_bias * 0.5)
                reasons.append(f"Above EMA200 (bias BUY)")
            else:
                buy_score *= (1 - self.ema200_trend_bias * 0.5)
                sell_score *= (1 + self.ema200_trend_bias)
                reasons.append(f"Below EMA200 (bias SELL)")

        # ── Determine direction ──
        confidence = max(buy_score, sell_score)

        if confidence < self.min_confidence:
            return TradeSignal(
                symbol=symbol,
                direction="HOLD",
                confidence=confidence,
                entry_price=entry_price,
                stop_loss=0,
                take_profit=0,
                atr=atr,
                reasons=reasons + [f"Score {confidence:.2f} below threshold"],
            )

        if buy_score > sell_score:
            direction = "BUY"
        elif sell_score > buy_score:
            direction = "SELL"
        else:
            return TradeSignal(
                symbol=symbol, direction="HOLD", confidence=0.0,
                entry_price=entry_price, stop_loss=0, take_profit=0,
                atr=atr, reasons=["No clear direction"],
            )

        # ── Calculate SL/TP ──
        sl, tp = self._calculate_sl_tp(direction, entry_price, atr, pair_params)

        reasons.append(f"Score: {confidence:.2f}")
        reasons.append(f"ATR: {atr:.4f}")
        reasons.append(f"SL: {sl:.2f} | TP: {tp:.2f}")

        return TradeSignal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            atr=atr,
            reasons=reasons,
        )

    @staticmethod
    def _calculate_sl_tp(
        signal: str,
        entry_price: float,
        atr: float,
        pair_params: PairParams,
    ) -> tuple:
        """Calculate stop loss and take profit based on ATR."""
        if signal == "BUY":
            sl = entry_price - (atr * pair_params.atr_sl_multiplier)
            tp = entry_price + (atr * pair_params.atr_tp_multiplier)
        elif signal == "SELL":
            sl = entry_price + (atr * pair_params.atr_sl_multiplier)
            tp = entry_price - (atr * pair_params.atr_tp_multiplier)
        else:
            return 0.0, 0.0

        return round(sl, 2), round(tp, 2)
