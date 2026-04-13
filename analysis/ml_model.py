"""
Layer 2 — AI Analysis Engine: ML Model for pattern recognition.
Uses XGBoost for classification or LSTM for time series prediction.
"""

import logging
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from config import AppConfig, Symbol

logger = logging.getLogger(__name__)


class MLSignalModel:
    """
    ML-based signal predictor.
    Trains on historical OHLCV data to classify BUY/SELL/HOLD signals.
    """

    def __init__(self, config: AppConfig, symbol: Symbol):
        self.config = config
        self.symbol = symbol
        self.model = None
        self.scaler = StandardScaler()
        self._is_trained = False

        # Model path
        model_path = (
            config.ai.xau_model_path if symbol == Symbol.XAUUSD
            else config.ai.btc_model_path
        )
        self.model_path = model_path

    @property
    def feature_names(self) -> list:
        """Names of features used by the model."""
        return [
            "price_change_1", "price_change_3", "price_change_5",
            "volume_ratio",
            "rsi", "rsi_change",
            "macd_hist", "macd_hist_change",
            "bb_width", "bb_position",
            "atr_pct",
            "high_low_ratio",
        ]

    def extract_features(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        """
        Extract features from OHLCV data for ML model input.

        Args:
            df: OHLCV DataFrame with at least 200 rows

        Returns:
            Feature array ready for model prediction
        """
        if df is None or len(df) < 50:
            return None

        try:
            features = {}

            # Price changes (momentum)
            features["price_change_1"] = df["close"].pct_change(1).iloc[-1]
            features["price_change_3"] = df["close"].pct_change(3).iloc[-1]
            features["price_change_5"] = df["close"].pct_change(5).iloc[-1]

            # Volume analysis
            avg_volume = df["tick_volume"].rolling(20).mean().iloc[-2]
            current_volume = df["tick_volume"].iloc[-1]
            features["volume_ratio"] = current_volume / avg_volume if avg_volume > 0 else 1.0

            # RSI
            rsi = self._compute_rsi(df["close"])
            features["rsi"] = rsi.iloc[-1] / 100.0  # Normalize to 0-1
            features["rsi_change"] = rsi.iloc[-1] - rsi.iloc[-3] if len(rsi) > 3 else 0.0

            # MACD histogram
            macd_hist = self._compute_macd_hist(df["close"])
            features["macd_hist"] = float(macd_hist.iloc[-1])
            features["macd_hist_change"] = float(
                macd_hist.iloc[-1] - macd_hist.iloc[-2]
            ) if len(macd_hist) > 1 else 0.0

            # Bollinger Bands
            bb_width = self._compute_bb_width(df["close"])
            features["bb_width"] = float(bb_width.iloc[-1])
            features["bb_position"] = self._bb_position_score(df["close"])

            # ATR as % of price
            atr = self._compute_atr(df)
            features["atr_pct"] = float(atr.iloc[-1]) / float(df["close"].iloc[-1])

            # High/Low ratio (volatility indicator)
            features["high_low_ratio"] = float(
                (df["high"].iloc[-1] - df["low"].iloc[-1]) / df["close"].iloc[-1]
            )

            feature_array = np.array([features[name] for name in self.feature_names])
            return feature_array

        except Exception as e:
            logger.error(f"Error extracting features for {self.symbol}: {e}")
            return None

    def predict(self, features: np.ndarray) -> dict:
        """
        Predict signal from features.

        Returns:
            Dict with 'signal' (BUY/SELL/HOLD), 'confidence', and 'probabilities'
        """
        if not self._is_trained:
            # Try to load pre-trained model
            self.load()

        if not self._is_trained:
            logger.warning(f"No trained model for {self.symbol}, using rule-based fallback")
            return self._rule_based_prediction(features)

        # Scale features
        features_scaled = self.scaler.transform(features.reshape(1, -1))

        # Predict
        probabilities = self.model.predict_proba(features_scaled)[0]
        prediction = self.model.predict(features_scaled)[0]

        signal_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        signal = signal_map.get(prediction, "HOLD")

        confidence = float(np.max(probabilities))

        return {
            "signal": signal,
            "confidence": confidence,
            "probabilities": {
                "SELL": float(probabilities[0]),
                "HOLD": float(probabilities[1]),
                "BUY": float(probabilities[2]),
            },
        }

    def _rule_based_prediction(self, features: np.ndarray) -> dict:
        """Fallback rule-based prediction when no ML model is available."""
        feature_dict = dict(zip(self.feature_names, features))

        score = 0.0

        # RSI-based
        rsi = feature_dict.get("rsi", 0.5) * 100
        if rsi < 30:
            score += 0.3
        elif rsi > 70:
            score -= 0.3

        # MACD
        macd_hist = feature_dict.get("macd_hist", 0)
        if macd_hist > 0:
            score += 0.2
        else:
            score -= 0.2

        # Price momentum
        price_change = feature_dict.get("price_change_1", 0)
        if price_change > 0.001:
            score += 0.1
        elif price_change < -0.001:
            score -= 0.1

        # BB position (mean reversion)
        bb_pos = feature_dict.get("bb_position", 0)
        if bb_pos < -0.5:
            score += 0.2
        elif bb_pos > 0.5:
            score -= 0.2

        # Determine signal
        if score > 0.2:
            signal = "BUY"
        elif score < -0.2:
            signal = "SELL"
        else:
            signal = "HOLD"

        confidence = min(abs(score), 0.85) + 0.15  # Min 15% confidence

        return {
            "signal": signal,
            "confidence": confidence,
            "probabilities": {
                "BUY": max(score, 0) * 0.5 + 0.25,
                "HOLD": (1 - abs(score)) * 0.5,
                "SELL": max(-score, 0) * 0.5 + 0.25,
            },
        }

    def train(
        self,
        df: pd.DataFrame,
        labels: Optional[pd.Series] = None,
        epochs: int = 100
    ) -> bool:
        """
        Train the ML model on historical data.

        Args:
            df: Historical OHLCV data
            labels: Pre-computed labels (0=SELL, 1=HOLD, 2=BUY).
                    If None, generates labels from future returns.
            epochs: Number of boosting rounds

        Returns:
            True if training successful
        """
        if not XGBOOST_AVAILABLE:
            logger.error("XGBoost not installed. Install with: pip install xgboost")
            return False

        logger.info(f"Training ML model for {self.symbol}...")

        # Extract features for all rows
        feature_rows = []
        for i in range(50, len(df)):
            features = self.extract_features(df.iloc[:i])
            if features is not None:
                feature_rows.append(features)

        if not feature_rows:
            logger.error("No features extracted for training")
            return False

        X = np.array(feature_rows)

        # Generate or use labels
        if labels is None:
            # Generate labels from future 5-candle returns
            future_returns = df["close"].shift(-5).pct_change(5).iloc[50:]
            labels = pd.Series(
                np.where(future_returns > 0.003, 2,  # BUY
                         np.where(future_returns < -0.003, 0, 1))  # SELL / HOLD
            )
        else:
            labels = labels.iloc[50:]

        y = labels.values

        # Align X and y
        min_len = min(len(X), len(y))
        X, y = X[:min_len], y[:min_len]

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train XGBoost
        self.model = XGBClassifier(
            n_estimators=epochs,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="mlogloss",
        )

        self.model.fit(X_scaled, y)
        self._is_trained = True

        # Evaluate
        train_score = self.model.score(X_scaled, y)
        logger.info(f"Model trained | Train accuracy: {train_score:.2%}")

        # Save model
        self.save()

        return True

    def save(self):
        """Save trained model to disk."""
        if not self._is_trained:
            return

        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)

        with open(self.model_path, "wb") as f:
            pickle.dump({
                "model": self.model,
                "scaler": self.scaler,
                "symbol": str(self.symbol),
                "feature_names": self.feature_names,
            }, f)

        logger.info(f"Model saved to {self.model_path}")

    def load(self) -> bool:
        """Load pre-trained model from disk."""
        if not os.path.exists(self.model_path):
            logger.warning(f"No saved model at {self.model_path}")
            return False

        try:
            with open(self.model_path, "rb") as f:
                data = pickle.load(f)

            self.model = data["model"]
            self.scaler = data["scaler"]
            self._is_trained = True
            logger.info(f"Model loaded from {self.model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    # ---- Helper methods ----

    @staticmethod
    def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _compute_macd_hist(series: pd.Series) -> pd.Series:
        ema_fast = series.ewm(span=12, adjust=False).mean()
        ema_slow = series.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        return macd_line - signal_line

    @staticmethod
    def _compute_bb_width(series: pd.Series, period: int = 20, std: float = 2.0) -> pd.Series:
        sma = series.rolling(window=period).mean()
        std_dev = series.rolling(window=period).std()
        upper = sma + std * std_dev
        lower = sma - std * std_dev
        return (upper - lower) / sma

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=period).mean()

    @staticmethod
    def _bb_position_score(series: pd.Series, period: int = 20, std: float = 2.0) -> float:
        """Returns -1 (at lower band) to +1 (at upper band)."""
        sma = series.rolling(window=period).mean()
        std_dev = series.rolling(window=period).std()
        upper = sma + std * std_dev
        lower = sma - std * std_dev
        bb_range = upper - lower

        last_close = series.iloc[-1]
        last_lower = lower.iloc[-1]
        last_upper = upper.iloc[-1]

        if bb_range.iloc[-1] == 0:
            return 0.0

        return (last_close - last_lower) / bb_range.iloc[-1] * 2 - 1
