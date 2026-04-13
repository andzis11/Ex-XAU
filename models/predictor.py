"""
Layer 2 — LSTM Model Predictor.
Runs inference on live data using trained LSTM models.
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

from data.preprocessor import DataPreprocessor
from config.pairs import PAIR_CONFIG

logger = logging.getLogger(__name__)


class LSTMPredictor:
    """
    Predict BUY/SELL/HOLD signals using trained LSTM models.
    Returns signal class and confidence probability.
    """

    SIGNAL_CLASSES = ["BUY", "SELL", "HOLD"]

    def __init__(self, lookback: int = 60):
        self.lookback = lookback
        self.preprocessor = DataPreprocessor(lookback=lookback)
        self.models = {}  # symbol -> model
        self._scalers_fitted = {}

    def load_model(self, symbol: str, model) -> bool:
        """
        Load a trained Keras model for a symbol.

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            model: Loaded Keras model object

        Returns:
            True if loaded successfully
        """
        if not TF_AVAILABLE:
            logger.error("TensorFlow not available")
            return False

        self.models[symbol] = model
        logger.info(f"Predictor loaded model for {symbol}")
        return True

    def predict(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> Tuple[str, float]:
        """
        Predict signal for the latest candle.

        Args:
            symbol: Trading symbol
            df: OHLCV DataFrame with indicators (at least lookback + 1 rows)

        Returns:
            (signal, confidence) tuple
            signal: "BUY" | "SELL" | "HOLD"
            confidence: 0.0 to 1.0
        """
        if not TF_AVAILABLE:
            return "HOLD", 0.0

        model = self.models.get(symbol)
        if model is None:
            logger.warning(f"No model loaded for {symbol}")
            return "HOLD", 0.0

        if len(df) < self.lookback + 1:
            logger.warning(
                f"Insufficient data for {symbol}: "
                f"need {self.lookback + 1}, have {len(df)}"
            )
            return "HOLD", 0.0

        try:
            # Scale the full dataset for consistent scaling
            available_features = [
                c for c in DataPreprocessor.FEATURE_COLUMNS if c in df.columns
            ]

            from sklearn.preprocessing import MinMaxScaler
            scaler = MinMaxScaler()
            X_scaled = scaler.fit_transform(df[available_features])

            # Take the last lookback candles as input sequence
            sequence = X_scaled[-self.lookback:].reshape(1, self.lookback, len(available_features))

            # Predict
            prediction = model.predict(sequence, verbose=0)
            probabilities = prediction[0]

            signal_idx = int(np.argmax(probabilities))
            confidence = float(np.max(probabilities))

            signal = self.SIGNAL_CLASSES[signal_idx]

            logger.info(
                f"{symbol} prediction: {signal} "
                f"(BUY={probabilities[0]:.2%}, "
                f"SELL={probabilities[1]:.2%}, "
                f"HOLD={probabilities[2]:.2%})"
            )

            return signal, confidence

        except Exception as e:
            logger.error(f"Prediction error for {symbol}: {e}")
            return "HOLD", 0.0

    def predict_batch(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> list:
        """
        Predict signals for all possible sequences in the DataFrame.

        Returns:
            List of (timestamp, signal, confidence) tuples
        """
        if not TF_AVAILABLE:
            return []

        model = self.models.get(symbol)
        if model is None:
            return []

        available_features = [
            c for c in DataPreprocessor.FEATURE_COLUMNS if c in df.columns
        ]

        from sklearn.preprocessing import MinMaxScaler
        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(df[available_features])

        sequences = []
        timestamps = []
        for i in range(self.lookback, len(X_scaled)):
            sequences.append(X_scaled[i - self.lookback:i])
            timestamps.append(df.index[i])

        if not sequences:
            return []

        X = np.array(sequences)
        predictions = model.predict(X, verbose=0)

        results = []
        for i, (ts, pred) in enumerate(zip(timestamps, predictions)):
            signal_idx = int(np.argmax(pred))
            confidence = float(np.max(pred))
            results.append((ts, self.SIGNAL_CLASSES[signal_idx], confidence))

        return results
