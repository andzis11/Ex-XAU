"""
Layer 2 — AI Analysis Engine: Unified analysis engine.
Combines technical analysis, ML prediction, and LLM reasoning.
"""

import logging
from typing import Optional

import pandas as pd

from config import AppConfig, Symbol
from analysis.technical import TechnicalAnalyzer, TechnicalSignals
from analysis.ml_model import MLSignalModel
from analysis.llm_reasoning import LLMReasoner

logger = logging.getLogger(__name__)


class AnalysisResult:
    """Combined analysis result from all Layer 2 components."""

    def __init__(self):
        self.symbol: Optional[Symbol] = None
        self.technical: Optional[TechnicalSignals] = None
        self.ml_prediction: dict = {}
        self.llm_analysis: dict = {}
        self.market_context: dict = {}

    @property
    def consensus_signal(self) -> str:
        """Determine consensus signal across all analyzers."""
        signals = []

        # Technical signal
        if self.technical:
            if self.technical.composite_score > 0.3:
                signals.append(("BUY", self.technical.composite_score))
            elif self.technical.composite_score < -0.3:
                signals.append(("SELL", abs(self.technical.composite_score)))
            else:
                signals.append(("HOLD", 0.5))

        # ML signal
        if self.ml_prediction:
            ml_sig = self.ml_prediction.get("signal", "HOLD")
            ml_conf = self.ml_prediction.get("confidence", 0.5)
            if ml_sig != "HOLD":
                signals.append((ml_sig, ml_conf))

        # LLM signal
        if self.llm_analysis:
            llm_sig = self.llm_analysis.get("signal", "NO_TRADE")
            llm_conf = self.llm_analysis.get("confidence", 0.5)
            if llm_sig != "NO_TRADE":
                signals.append((llm_sig, llm_conf))

        if not signals:
            return "HOLD"

        # Weighted vote
        buy_weight = sum(w for s, w in signals if s == "BUY")
        sell_weight = sum(w for s, w in signals if s == "SELL")

        if buy_weight > sell_weight and buy_weight > 0.5:
            return "BUY"
        elif sell_weight > buy_weight and sell_weight > 0.5:
            return "SELL"
        return "HOLD"

    @property
    def consensus_confidence(self) -> float:
        """Average confidence across all analyzers."""
        confidences = []

        if self.technical:
            confidences.append(abs(self.technical.composite_score))

        if self.ml_prediction:
            confidences.append(self.ml_prediction.get("confidence", 0))

        if self.llm_analysis:
            confidences.append(self.llm_analysis.get("confidence", 0))

        return sum(confidences) / len(confidences) if confidences else 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": str(self.symbol) if self.symbol else None,
            "consensus_signal": self.consensus_signal,
            "consensus_confidence": round(self.consensus_confidence, 4),
            "technical": self.technical.to_dict() if self.technical else None,
            "ml_prediction": self.ml_prediction,
            "llm_analysis": {
                "signal": self.llm_analysis.get("signal"),
                "confidence": self.llm_analysis.get("confidence"),
                "reasoning": self.llm_analysis.get("reasoning"),
            } if self.llm_analysis else None,
        }


class AnalysisEngine:
    """
    Layer 2 — AI Analysis Engine.
    Orchestrates technical analysis, ML prediction, and LLM reasoning.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.technical_analyzer = TechnicalAnalyzer(config)

        # Per-symbol ML models
        self.ml_models = {
            Symbol.XAUUSD: MLSignalModel(config, Symbol.XAUUSD),
            Symbol.BTCUSD: MLSignalModel(config, Symbol.BTCUSD),
        }

        self.llm_reasoner = LLMReasoner(config)

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: Symbol,
        market_context: Optional[dict] = None,
    ) -> AnalysisResult:
        """
        Run full analysis pipeline for a symbol.

        Args:
            df: OHLCV DataFrame
            symbol: Trading symbol
            market_context: Optional market context from data pipeline

        Returns:
            AnalysisResult with all analysis components
        """
        result = AnalysisResult()
        result.symbol = symbol
        result.market_context = market_context or {}

        logger.info(f"Running analysis for {symbol.value}...")

        # 1. Technical Analysis
        result.technical = self.technical_analyzer.analyze(df, symbol)
        if result.technical:
            logger.info(
                f"  Technical: {result.technical.ema_alignment} | "
                f"RSI={result.technical.rsi_value:.1f} | "
                f"Score={result.technical.composite_score:.2f}"
            )

        # 2. ML Prediction
        ml_model = self.ml_models.get(symbol)
        if ml_model:
            features = ml_model.extract_features(df)
            if features is not None:
                result.ml_prediction = ml_model.predict(features)
                logger.info(
                    f"  ML: {result.ml_prediction.get('signal')} "
                    f"(confidence: {result.ml_prediction.get('confidence', 0):.0%})"
                )

        # 3. LLM Reasoning
        result.llm_analysis = self.llm_reasoner.analyze(
            symbol=symbol,
            technical_signals=result.technical.to_dict() if result.technical else {},
            ml_prediction=result.ml_prediction,
            market_context=result.market_context,
        )
        logger.info(
            f"  LLM: {result.llm_analysis.get('signal')} "
            f"(confidence: {result.llm_analysis.get('confidence', 0):.0%})"
        )

        # Summary
        logger.info(
            f"  CONSENSUS: {result.consensus_signal} "
            f"(confidence: {result.consensus_confidence:.0%})"
        )

        return result
