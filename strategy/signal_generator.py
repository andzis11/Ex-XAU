"""
Layer 3 — Signal Generator.
Combines LSTM prediction with indicator-based confirmation to produce final signal.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.pairs import PairParams, get_pair_params
from models.predictor import LSTMPredictor

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
    Generates final BUY/SELL/HOLD signals by combining:
    1. LSTM model prediction (primary)
    2. Indicator confirmation (secondary filter)
    """

    def __init__(self, predictor: LSTMPredictor):
        self.predictor = predictor

    def generate(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> TradeSignal:
        """
        Generate trade signal for a symbol.

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            df: OHLCV DataFrame with indicators added

        Returns:
            TradeSignal with direction, confidence, SL, TP
        """
        pair_params = get_pair_params(symbol)
        entry_price = float(df["close"].iloc[-1])
        atr = float(df["atr"].iloc[-1])

        # 1. LSTM prediction
        lstm_signal, lstm_confidence = self.predictor.predict(symbol, df)

        # 2. Indicator confirmation
        indicator_agreement = self._check_indicator_agreement(df, lstm_signal)

        # 3. Adjust confidence based on indicator agreement
        adjusted_confidence = lstm_confidence
        if indicator_agreement > 0.5:
            adjusted_confidence = min(lstm_confidence * 1.15, 0.95)
        elif indicator_agreement < 0.3:
            adjusted_confidence *= 0.7

        # 4. Check against minimum confidence threshold
        if adjusted_confidence < pair_params.min_confidence:
            logger.info(
                f"{symbol}: Confidence {adjusted_confidence:.2%} "
                f"below threshold {pair_params.min_confidence:.0%}. Skipping."
            )
            return TradeSignal(
                symbol=symbol,
                direction="HOLD",
                confidence=adjusted_confidence,
                entry_price=entry_price,
                stop_loss=0,
                take_profit=0,
                atr=atr,
                reasons=[
                    f"LSTM: {lstm_signal} ({lstm_confidence:.0%})",
                    f"Adjusted: {adjusted_confidence:.0%}",
                    f"Indicator agreement: {indicator_agreement:.0%}",
                ],
            )

        # 5. If LSTM says HOLD, skip
        if lstm_signal == "HOLD":
            return TradeSignal(
                symbol=symbol,
                direction="HOLD",
                confidence=adjusted_confidence,
                entry_price=entry_price,
                stop_loss=0,
                take_profit=0,
                atr=atr,
                reasons=["LSTM predicts HOLD"],
            )

        # 6. Calculate SL/TP
        sl, tp = self._calculate_sl_tp(lstm_signal, entry_price, atr, pair_params)

        # 7. Build reasons
        reasons = [
            f"LSTM: {lstm_signal} ({lstm_confidence:.0%})",
            f"Adjusted confidence: {adjusted_confidence:.0%}",
            f"Indicator agreement: {indicator_agreement:.0%}",
            f"ATR: {atr:.4f}",
            f"SL: {sl:.2f} | TP: {tp:.2f}",
        ]

        return TradeSignal(
            symbol=symbol,
            direction=lstm_signal,
            confidence=adjusted_confidence,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            atr=atr,
            reasons=reasons,
        )

    def _check_indicator_agreement(self, df: pd.DataFrame, signal: str) -> float:
        """
        Check how many traditional indicators agree with the LSTM signal.
        Returns agreement ratio (0.0 to 1.0).

        Checks:
        - EMA trend alignment
        - RSI direction
        - MACD direction
        - Bollinger Bands position
        """
        if len(df) < 2:
            return 0.5  # Neutral, not enough data

        last = df.iloc[-1]
        prev = df.iloc[-2]
        agreements = 0
        total_checks = 0

        # Check 1: EMA alignment
        total_checks += 1
        if signal == "BUY" and last["ema_20"] > last["ema_50"]:
            agreements += 1
        elif signal == "SELL" and last["ema_20"] < last["ema_50"]:
            agreements += 1

        # Check 2: RSI
        total_checks += 1
        if signal == "BUY" and last["rsi"] < 70:  # Not overbought
            agreements += 1
        elif signal == "SELL" and last["rsi"] > 30:  # Not oversold
            agreements += 1

        # Check 3: MACD
        total_checks += 1
        if signal == "BUY" and last["macd"] > last["macd_signal"]:
            agreements += 1
        elif signal == "SELL" and last["macd"] < last["macd_signal"]:
            agreements += 1

        # Check 4: Price vs BB mid
        total_checks += 1
        if signal == "BUY" and last["close"] > last["bb_mid"]:
            agreements += 1
        elif signal == "SELL" and last["close"] < last["bb_mid"]:
            agreements += 1

        # Check 5: MACD momentum (diff increasing for BUY)
        total_checks += 1
        if len(df) >= 3:
            prev_prev = df.iloc[-3]
            macd_momentum_up = last["macd_diff"] > prev["macd_diff"]
            if signal == "BUY" and macd_momentum_up:
                agreements += 1
            elif signal == "SELL" and not macd_momentum_up:
                agreements += 1
        else:
            agreements += 0.5  # Partial credit if not enough data

        return agreements / total_checks

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
