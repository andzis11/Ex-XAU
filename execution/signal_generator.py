"""
Layer 3 — Signal Generator.
Determines final trade signal based on confluence scoring across all analyzers.
Only generates signals when confluence score exceeds the threshold.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config import AppConfig, Symbol
from analysis.engine import AnalysisResult

logger = logging.getLogger(__name__)


class TradeSignal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


@dataclass
class TradeSignalResult:
    """Final trade signal with full context."""
    signal: TradeSignal
    symbol: Symbol
    confluence_score: float       # 0.0 to 1.0
    entry_price: float
    reasoning: str

    # Signal breakdown
    technical_agreement: float    # 0.0 to 1.0 — how many tech indicators agree
    ml_confidence: float          # 0.0 to 1.0
    llm_confidence: float         # 0.0 to 1.0

    # Risk info
    recommended_stop_loss: float = 0.0
    recommended_take_profit: float = 0.0
    recommended_lot_size: float = 0.0

    # Context
    key_factors: list = None
    risks: list = None
    analysis_details: dict = None

    def __post_init__(self):
        if self.key_factors is None:
            self.key_factors = []
        if self.risks is None:
            self.risks = []
        if self.analysis_details is None:
            self.analysis_details = {}


class SignalGenerator:
    """
    Layer 3 — Signal Generator.
    Combines all analysis outputs and generates final trade signal
    only when confluence score exceeds the configured threshold.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.min_confluence = config.trading.min_confluence_score

    def generate(
        self,
        analysis: AnalysisResult,
        current_price: float,
        atr: float = 0.0,
    ) -> TradeSignalResult:
        """
        Generate trade signal from analysis results.

        Args:
            analysis: Combined analysis result from Layer 2
            current_price: Current market price
            atr: Average True Range for SL/TP calculation

        Returns:
            TradeSignalResult with signal and all context
        """
        symbol = analysis.symbol

        # Calculate confluence components
        tech_agreement = self._calc_technical_agreement(analysis)
        ml_confidence = analysis.ml_prediction.get("confidence", 0)
        llm_confidence = analysis.llm_analysis.get("confidence", 0)

        # Overall confluence score (weighted average)
        confluence = (
            tech_agreement * 0.35 +
            ml_confidence * 0.35 +
            llm_confidence * 0.30
        )

        # Get consensus direction
        consensus = analysis.consensus_signal
        consensus_confidence = analysis.consensus_confidence

        # Build reasoning
        reasoning_parts = []
        key_factors = []
        risks = []

        # Technical reasoning
        if analysis.technical:
            tech = analysis.technical
            reasoning_parts.append(
                f"Tech: EMA {tech.ema_alignment}, "
                f"RSI {tech.rsi_signal} ({tech.rsi_value:.1f}), "
                f"MACD {tech.macd_signal}"
            )
            key_factors.append(f"EMA alignment: {tech.ema_alignment}")
            key_factors.append(f"RSI: {tech.rsi_value:.1f} ({tech.rsi_signal})")

        # ML reasoning
        if analysis.ml_prediction:
            ml = analysis.ml_prediction
            reasoning_parts.append(
                f"ML: {ml.get('signal')} ({ml.get('confidence', 0):.0%})"
            )
            key_factors.append(f"ML prediction: {ml.get('signal')}")

        # LLM reasoning
        if analysis.llm_analysis:
            llm = analysis.llm_analysis
            reasoning_parts.append(
                f"LLM: {llm.get('signal')} ({llm.get('confidence', 0):.0%})"
            )
            llm_reasoning = llm.get("reasoning", "")
            if llm_reasoning:
                key_factors.append(llm_reasoning[:100])
            risks.extend(llm.get("risks", []))

        reasoning = " | ".join(reasoning_parts)

        # Determine final signal
        if confluence < self.min_confluence:
            signal = TradeSignal.NO_TRADE
            reasoning = f"Confluence {confluence:.0%} below threshold {self.min_confluence:.0%}. {reasoning}"
        elif consensus == "BUY":
            signal = TradeSignal.BUY
        elif consensus == "SELL":
            signal = TradeSignal.SELL
        else:
            signal = TradeSignal.NO_TRADE
            reasoning = f"Consensus is HOLD. {reasoning}"

        # Build result
        result = TradeSignalResult(
            signal=signal,
            symbol=symbol,
            confluence_score=confluence,
            entry_price=current_price,
            reasoning=reasoning,
            technical_agreement=tech_agreement,
            ml_confidence=ml_confidence,
            llm_confidence=llm_confidence,
            key_factors=key_factors,
            risks=risks,
            analysis_details=analysis.to_dict(),
        )

        # Calculate SL/TP if signal is active
        if signal != TradeSignal.NO_TRADE and atr > 0:
            result = self._calculate_levels(result, atr)

        return result

    def _calc_technical_agreement(self, analysis: AnalysisResult) -> float:
        """
        Calculate how many technical indicators agree on direction.
        Returns 0.0 to 1.0.
        """
        if not analysis.technical:
            return 0.0

        tech = analysis.technical
        signals = []

        # EMA alignment
        if tech.ema_alignment == "bullish":
            signals.append(1)
        elif tech.ema_alignment == "bearish":
            signals.append(-1)
        else:
            signals.append(0)

        # RSI (mean reversion)
        if tech.rsi_signal == "oversold":
            signals.append(1)  # bullish reversal
        elif tech.rsi_signal == "overbought":
            signals.append(-1)  # bearish reversal
        else:
            signals.append(0)

        # MACD
        if tech.macd_signal == "bullish":
            signals.append(1)
        elif tech.macd_signal == "bearish":
            signals.append(-1)
        else:
            signals.append(0)

        # BB position (mean reversion)
        if tech.bb_position in ("outside_lower", "lower_band"):
            signals.append(1)
        elif tech.bb_position in ("outside_upper", "upper_band"):
            signals.append(-1)
        else:
            signals.append(0)

        # Composite score
        if tech.composite_score > 0.3:
            signals.append(1)
        elif tech.composite_score < -0.3:
            signals.append(-1)
        else:
            signals.append(0)

        # Calculate agreement
        non_zero = [s for s in signals if s != 0]
        if not non_zero:
            return 0.0

        agree = sum(1 for s in non_zero if s > 0)
        disagree = sum(1 for s in non_zero if s < 0)

        total = len(non_zero)
        agreement = abs(agree - disagree) / total

        return min(agreement, 1.0)

    def _calculate_levels(
        self,
        result: TradeSignalResult,
        atr: float,
    ) -> TradeSignalResult:
        """Calculate stop loss and take profit levels."""
        risk_cfg = self.config.risk

        if result.symbol == Symbol.XAUUSD:
            sl_mult = risk_cfg.xau_atr_sl_multiplier
            tp_mult = risk_cfg.xau_atr_tp_multiplier
        else:
            sl_mult = risk_cfg.btc_atr_sl_multiplier
            tp_mult = risk_cfg.btc_atr_tp_multiplier

        if result.signal == TradeSignal.BUY:
            result.recommended_stop_loss = result.entry_price - (atr * sl_mult)
            result.recommended_take_profit = result.entry_price + (atr * tp_mult)
        else:  # SELL
            result.recommended_stop_loss = result.entry_price + (atr * sl_mult)
            result.recommended_take_profit = result.entry_price - (atr * tp_mult)

        return result

    def should_trade(self, result: TradeSignalResult) -> bool:
        """Check if the signal meets all criteria for trading."""
        if result.signal == TradeSignal.NO_TRADE:
            return False

        if result.confluence_score < self.min_confluence:
            logger.warning(
                f"{result.symbol}: Confluence {result.confluence_score:.0%} "
                f"below threshold {self.min_confluence:.0%}"
            )
            return False

        if result.entry_price <= 0:
            logger.warning(f"{result.symbol}: Invalid entry price")
            return False

        return True
