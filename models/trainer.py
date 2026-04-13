"""
Layer 2 — LSTM Model Trainer.
Builds and trains an LSTM neural network for BUY/SELL/HOLD signal classification.
"""

import logging
import os

import numpy as np
import pandas as pd

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, load_model as keras_load
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

from data.preprocessor import DataPreprocessor
from config.pairs import PAIR_CONFIG

logger = logging.getLogger(__name__)


class LSTMTrainer:
    """
    Train LSTM models per pair (XAUUSD, BTCUSD).
    Each model predicts BUY/SELL/HOLD with confidence scores.
    """

    SIGNALS = ["BUY", "SELL", "HOLD"]

    def __init__(
        self,
        lookback: int = 60,
        model_dir: str = "models/saved_models",
    ):
        self.lookback = lookback
        self.model_dir = model_dir
        self.preprocessor = DataPreprocessor(lookback=lookback)
        self.models = {}  # symbol -> model

        os.makedirs(model_dir, exist_ok=True)

    def build_model(self, input_shape: tuple) -> Sequential:
        """
        Build LSTM model architecture.

        Args:
            input_shape: (lookback, n_features)

        Returns:
            Compiled Keras model
        """
        if not TF_AVAILABLE:
            logger.error("TensorFlow not installed. Install with: pip install tensorflow")
            return None

        model = Sequential([
            LSTM(128, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),
            LSTM(64, return_sequences=False),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(3, activation="softmax"),   # [BUY, SELL, HOLD]
        ])

        model.compile(
            optimizer="adam",
            loss="categorical_crossentropy",
            metrics=["accuracy"],
        )

        logger.info(f"Model built | Input shape: {input_shape}")
        model.summary(print_fn=logger.info)
        return model

    def prepare_labels(self, df: pd.DataFrame, future_bars: int = 5) -> np.ndarray:
        """
        Generate classification labels from future returns.

        Label logic:
        - BUY  (2): future return > +0.3%
        - SELL (0): future return < -0.3%
        - HOLD (1): otherwise

        Args:
            df: OHLCV DataFrame
            future_bars: How many bars ahead to look for labeling

        Returns:
            One-hot encoded labels array
        """
        future_returns = df["close"].shift(-future_bars).pct_change(future_bars)

        labels = np.where(
            future_returns > 0.003, 2,      # BUY
            np.where(future_returns < -0.003, 0, 1)  # SELL / HOLD
        )

        # One-hot encode
        one_hot = np.eye(3)[labels]
        return one_hot

    def train(
        self,
        symbol: str,
        df: pd.DataFrame,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.2,
    ) -> bool:
        """
        Train an LSTM model for a specific symbol.

        Args:
            symbol: "XAUUSD" or "BTCUSD"
            df: OHLCV DataFrame with indicators already added
            epochs: Max training epochs
            batch_size: Training batch size
            validation_split: Fraction of data for validation

        Returns:
            True if training successful
        """
        if not TF_AVAILABLE:
            logger.error("TensorFlow not available")
            return False

        logger.info(f"Training LSTM model for {symbol}...")

        # Prepare features
        sequences = self.preprocessor.fit_transform(df)
        if len(sequences) == 0:
            logger.error("No sequences generated")
            return False

        # Prepare labels (align with sequences)
        labels = self.prepare_labels(df)
        # Trim labels to match sequences (offset by lookback)
        labels = labels[self.lookback:]

        # Align lengths
        min_len = min(len(sequences), len(labels))
        X, y = sequences[:min_len], labels[:min_len]

        logger.info(f"Training data: X={X.shape}, y={y.shape}")

        # Build model
        input_shape = self.preprocessor.get_feature_shape()
        model = self.build_model(input_shape)
        if model is None:
            return False

        # Callbacks
        callbacks = [
            EarlyStopping(patience=10, restore_best_weights=True, monitor="val_loss"),
            ReduceLROnPlateau(factor=0.5, patience=5, min_lr=1e-6, monitor="val_loss"),
        ]

        # Train
        history = model.fit(
            X, y,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=callbacks,
            verbose=1,
        )

        # Evaluate
        train_acc = history.history["accuracy"][-1]
        val_acc = history.history.get("val_accuracy", [train_acc])[-1]
        logger.info(
            f"Training complete | Train acc: {train_acc:.2%} | Val acc: {val_acc:.2%}"
        )

        # Save
        self.models[symbol] = model
        self.save_model(symbol)

        return True

    def save_model(self, symbol: str):
        """Save trained model to disk."""
        model = self.models.get(symbol)
        if model is None:
            logger.warning(f"No model to save for {symbol}")
            return

        path = os.path.join(self.model_dir, f"{symbol.lower()}_lstm.h5")
        model.save(path)
        logger.info(f"Model saved to {path}")

    def load_model(self, symbol: str) -> bool:
        """Load pre-trained model from disk."""
        if not TF_AVAILABLE:
            return False

        path = os.path.join(self.model_dir, f"{symbol.lower()}_lstm.h5")
        if not os.path.exists(path):
            logger.warning(f"No saved model at {path}")
            return False

        try:
            self.models[symbol] = keras_load(path)
            logger.info(f"Model loaded for {symbol} from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model for {symbol}: {e}")
            return False

    def load_all_models(self) -> int:
        """Load all available saved models. Returns count of loaded models."""
        count = 0
        for symbol in PAIR_CONFIG:
            if self.load_model(symbol):
                count += 1
        logger.info(f"Loaded {count} model(s)")
        return count

    def get_model(self, symbol: str):
        """Get model for a symbol (must be trained or loaded first)."""
        return self.models.get(symbol)
