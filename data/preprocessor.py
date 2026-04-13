"""
Layer 1 — Data Preprocessor.
Cleans, normalizes, and prepares OHLCV data for ML model input.
"""

import logging

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger(__name__)


class DataPreprocessor:
    """
    Preprocess OHLCV data for LSTM model input.
    Handles feature selection, scaling, and sequence generation.
    """

    FEATURE_COLUMNS = [
        "close", "rsi", "macd", "macd_signal",
        "atr", "ema_20", "ema_50", "tick_volume",
    ]

    def __init__(self, lookback: int = 60):
        """
        Args:
            lookback: Number of past candles to use as input sequence.
        """
        self.lookback = lookback
        self.scaler = MinMaxScaler()
        self._is_fitted = False

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Fit scaler and transform data into sequences.

        Args:
            df: DataFrame with indicator columns

        Returns:
            3D array of shape (n_sequences, lookback, n_features)
        """
        available_features = [c for c in self.FEATURE_COLUMNS if c in df.columns]

        if not available_features:
            logger.error("No feature columns found in DataFrame")
            return np.array([])

        X = self.scaler.fit_transform(df[available_features])
        self._is_fitted = True

        sequences = self._create_sequences(X)
        logger.info(
            f"Preprocessed {len(sequences)} sequences | "
            f"shape: {sequences.shape}"
        )
        return sequences

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform data using pre-fitted scaler (for inference).

        Args:
            df: DataFrame with indicator columns

        Returns:
            3D array of shape (n_sequences, lookback, n_features)
        """
        if not self._is_fitted:
            logger.warning("Scaler not fitted. Calling fit_transform instead.")
            return self.fit_transform(df)

        available_features = [c for c in self.FEATURE_COLUMNS if c in df.columns]
        X = self.scaler.transform(df[available_features])
        return self._create_sequences(X)

    def _create_sequences(self, data: np.ndarray) -> np.ndarray:
        """Create rolling window sequences from scaled data."""
        sequences = []
        for i in range(self.lookback, len(data)):
            sequences.append(data[i - self.lookback:i])
        return np.array(sequences)

    def inverse_transform_close(self, scaled_close: np.ndarray) -> np.ndarray:
        """
        Inverse transform only the 'close' column from scaled values.
        Useful for converting predicted prices back to real values.
        """
        # Create a dummy array with the right number of features
        n_features = len(self.FEATURE_COLUMNS)
        dummy = np.zeros((len(scaled_close), n_features))
        close_idx = self.FEATURE_COLUMNS.index("close")
        dummy[:, close_idx] = scaled_close.flatten()

        inverted = self.scaler.inverse_transform(dummy)
        return inverted[:, close_idx]

    def get_feature_shape(self) -> tuple:
        """Return (lookback, n_features) for model input shape."""
        return (self.lookback, len(self.FEATURE_COLUMNS))
