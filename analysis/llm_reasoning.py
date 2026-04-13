"""
Layer 2 — AI Analysis Engine: LLM Reasoning module.
Uses Claude/GPT to analyze market context and provide fundamental analysis.
"""

import json
import logging
from typing import Optional

from config import AppConfig, Symbol

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logger = logging.getLogger(__name__)


class LLMReasoner:
    """
    Uses Claude API to analyze market conditions and provide
    fundamental reasoning for trade decisions.
    """

    SYSTEM_PROMPT = """You are an expert forex and crypto trading analyst.
Your job is to analyze market conditions and provide a clear BUY, SELL, or NO TRADE
recommendation with reasoning.

Respond ONLY in valid JSON format with this exact structure:
{
    "signal": "BUY" | "SELL" | "NO_TRADE",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation of your analysis",
    "key_factors": ["factor1", "factor2", "factor3"],
    "risks": ["risk1", "risk2"]
}

Consider:
- Technical setup (trend, momentum, support/resistance)
- Fundamental context (news, economic events, sentiment)
- Risk factors (volatility, spread, liquidity)
- Market timing (session overlap, news proximity)"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.client = None

        if ANTHROPIC_AVAILABLE and config.ai.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=config.ai.anthropic_api_key)
        else:
            logger.warning(
                "Anthropic SDK not available or API key not set. "
                "LLM reasoning will use fallback mode."
            )

    def analyze(
        self,
        symbol: Symbol,
        technical_signals: dict,
        ml_prediction: dict,
        market_context: dict,
    ) -> dict:
        """
        Get LLM analysis for a trading opportunity.

        Args:
            symbol: Trading pair (XAUUSD or BTCUSD)
            technical_signals: Output from TechnicalAnalyzer
            ml_prediction: Output from MLSignalModel
            market_context: Current market context (price, news, etc.)

        Returns:
            Dict with signal, confidence, reasoning, key_factors, risks
        """
        prompt = self._build_prompt(symbol, technical_signals, ml_prediction, market_context)

        if self.client:
            try:
                return self._call_claude(prompt)
            except Exception as e:
                logger.error(f"Claude API error: {e}")
                return self._fallback_analysis(technical_signals, ml_prediction)
        else:
            return self._fallback_analysis(technical_signals, ml_prediction)

    def _build_prompt(
        self,
        symbol: Symbol,
        technical: dict,
        ml: dict,
        context: dict,
    ) -> str:
        """Build the analysis prompt for the LLM."""
        symbol_name = str(symbol)

        # Symbol-specific context
        if symbol == Symbol.XAUUSD:
            symbol_context = (
                f"Analyzing {symbol_name} (Gold). "
                "Gold is highly correlated with USD weakness, real yields, and safe-haven flows. "
                "Key sessions: London (8-16 UTC), NY (13-21 UTC). "
                "Watch DXY, US 10Y yields, and geopolitical risk."
            )
        else:
            symbol_context = (
                f"Analyzing {symbol_name} (Bitcoin). "
                "BTC is influenced by crypto-specific factors: exchange flows, whale activity, "
                "regulatory news, and risk sentiment. "
                "Watch for weekend liquidity gaps and funding rates."
            )

        return f"""{symbol_context}

CURRENT MARKET DATA:
- Current Price: {context.get('recent_close', 'N/A')}
- 5-candle change: {context.get('recent_change_pct', 'N/A')}%
- Spread: {context.get('price', {}).get('spread', 'N/A')}

TECHNICAL INDICATORS:
- EMA Alignment: {technical.get('ema_alignment', 'N/A')}
- RSI: {technical.get('rsi_value', 'N/A')} ({technical.get('rsi_signal', 'N/A')})
- MACD: {technical.get('macd_signal', 'N/A')} (histogram: {technical.get('macd_histogram', 'N/A')})
- Bollinger Bands: {technical.get('bb_position', 'N/A')}
- ATR: {technical.get('atr_value', 'N/A')}
- Composite Score: {technical.get('composite_score', 'N/A')}

ML MODEL PREDICTION:
- Signal: {ml.get('signal', 'N/A')}
- Confidence: {ml.get('confidence', 'N/A')}

NEWS & SENTIMENT:
- News Risk Level: {context.get('news', {}).get('risk_level', 'N/A')}
- News Summary: {context.get('news', {}).get('summary', 'N/A')}
- In News Blackout: {context.get('news_blackout', (False, None))[0]}

Provide your analysis in JSON format."""

    def _call_claude(self, prompt: str) -> dict:
        """Call Claude API for analysis."""
        message = self.client.messages.create(
            model=self.config.ai.anthropic_model,
            max_tokens=500,
            temperature=0.3,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse JSON response
        try:
            # Extract JSON from response text
            content = message.content[0].text
            # Find JSON block
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                result = json.loads(json_str)

                # Validate required fields
                required = ["signal", "confidence", "reasoning"]
                for field in required:
                    if field not in result:
                        raise ValueError(f"Missing field: {field}")

                return result

        except (json.JSONDecodeError, IndexError, ValueError) as e:
            logger.error(f"Failed to parse Claude response: {e}")
            return self._parse_raw_response(content)

    def _parse_raw_response(self, text: str) -> dict:
        """Try to extract signal info from non-JSON response."""
        text_lower = text.lower()

        if "buy" in text_lower:
            signal = "BUY"
        elif "sell" in text_lower:
            signal = "SELL"
        else:
            signal = "NO_TRADE"

        return {
            "signal": signal,
            "confidence": 0.5,
            "reasoning": text[:300],
            "key_factors": [],
            "risks": [],
        }

    def _fallback_analysis(self, technical: dict, ml: dict) -> dict:
        """
        Fallback analysis when LLM is unavailable.
        Uses rule-based logic combining technical and ML signals.
        """
        tech_score = technical.get("composite_score", 0)
        ml_signal = ml.get("signal", "HOLD")
        ml_confidence = ml.get("confidence", 0.5)

        # Combine signals
        combined_score = 0.0

        # Technical contribution (40%)
        combined_score += tech_score * 0.4

        # ML contribution (40%)
        if ml_signal == "BUY":
            combined_score += ml_confidence * 0.4
        elif ml_signal == "SELL":
            combined_score -= ml_confidence * 0.4

        # Determine final signal
        if combined_score > 0.2:
            signal = "BUY"
        elif combined_score < -0.2:
            signal = "SELL"
        else:
            signal = "NO_TRADE"

        confidence = min(abs(combined_score) * 2, 0.85) + 0.15

        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": (
                f"Rule-based fallback. Tech score: {tech_score:.2f}, "
                f"ML signal: {ml_signal} ({ml_confidence:.0%})"
            ),
            "key_factors": [
                f"EMA alignment: {technical.get('ema_alignment', 'N/A')}",
                f"RSI: {technical.get('rsi_value', 0):.1f}",
            ],
            "risks": ["LLM analysis unavailable — using rule-based fallback"],
        }
