# 🤖 Exness AI Trading Bot — XAU/USD & BTC/USD

AI-powered trading bot for **Exness** using **LSTM neural networks** and technical indicators. Supports Gold (XAU/USD) and Bitcoin (BTC/USD) with pair-specific risk parameters.

---

## 📁 Project Structure

```
ai_trading_bot/
│
├── config/
│   ├── settings.py          # API keys, bot parameters
│   └── pairs.py             # XAU/USD & BTC/USD pair-specific params
│
├── data/
│   ├── collector.py         # Fetch OHLCV from MT5
│   ├── preprocessor.py      # Feature scaling & sequence generation
│   ├── indicators.py        # RSI, MACD, BB, ATR, EMA
│   └── pipeline.py          # Unified data interface
│
├── models/
│   ├── trainer.py           # LSTM training (TensorFlow)
│   ├── predictor.py         # Live inference
│   └── saved_models/        # .h5 model files
│
├── strategy/
│   ├── signal_generator.py  # BUY/SELL/HOLD + indicator confirmation
│   ├── risk_manager.py      # SL, TP, lot sizing (pair-specific)
│   └── backtester.py        # Historical backtesting engine
│
├── execution/
│   ├── broker.py            # MT5 connection
│   ├── order_manager.py     # Open/close orders
│   └── portfolio.py         # Track open positions
│
├── monitoring/
│   ├── logger.py            # Structured logging
│   └── notifier.py          # Telegram alerts
│
├── backtest/                # Legacy: trade journal
│   └── trade_journal.py
│
├── main.py                  # Entry point + state machine
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚙️ Parameter Rekomendasi per Pair

| Parameter           | XAU/USD (Gold) | BTC/USD |
|---------------------|:--------------:|:-------:|
| Timeframe           | M15 / H1       | H1 / H4 |
| ATR SL Multiplier   | 1.5×           | 2.0×    |
| ATR TP Multiplier   | 3.0×           | 4.0×    |
| Max Lot             | 1.0            | 0.1     |
| Risk per Trade      | 1%             | 0.5%    |
| Min Confidence      | 70%            | 75%     |
| Max Spread          | 30 pips        | 50 pips |
| Pip Value / Lot     | $10            | $1      |

---

## 🔄 State Machine

```
INITIALIZING → CONNECTED → RUNNING ↔ PAUSED
                                ↓
                             STOPPING → STOPPED
                                ↓
                              ERROR
```

| State          | Description                                    |
|----------------|------------------------------------------------|
| `INITIALIZING` | Loading models, connecting to MT5              |
| `RUNNING`      | Normal trading cycle (every 15 min)            |
| `PAUSED`       | Auto-paused: wide spread / news / drawdown     |
| `STOPPING`     | Graceful shutdown in progress                  |
| `STOPPED`      | Bot fully stopped                              |
| `ERROR`        | Connection lost or fatal error                 |

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note**: `MetaTrader5` requires Windows with MT5 terminal installed. For Linux/Cloud, see MetaAPI client in `data/metaapi_client.py`.

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your Exness credentials, Telegram token, etc.
```

### 3. Train Models

```bash
python main.py train
```

Fetches 2000 bars of historical data, trains LSTM models per pair, saves `.h5` files to `models/saved_models/`.

### 4. Run Live

```bash
python main.py live --interval 15
```

Starts the bot with 15-minute check intervals.

### 5. Backtest

```bash
python main.py backtest --symbol XAUUSD
```

### 6. Check Status

```bash
python main.py status
```

---

## 🔄 Bot Flow (per 15-min cycle)

```
For each pair (XAUUSD, BTCUSD):

  1. 📊  Fetch OHLCV + indicators (M15/H1/H4)
  2. 🧠  LSTM prediction → BUY/SELL/HOLD + confidence
  3. ✅  Indicator confirmation (EMA, RSI, MACD, BB)
  4. ⚠️  Check spread (max 30/50 points)
  5. 📐  Check position limit (max 3 open per pair)
  6. 💰  Calculate lot size (risk-based, pair-specific)
  7. 🎯  Calculate SL/TP (ATR-based, pair-specific multipliers)
  8. 📤  Execute order via MT5
  9. 📝  Log to journal + send Telegram notification
```

---

## 📊 Performance Tracking

| Artifact                  | Location                     |
|---------------------------|------------------------------|
| Trade journal (SQLite)    | `data/trading_journal.db`    |
| Trade log (structured)    | `logs/trades.log`            |
| Bot log (rotating)        | `logs/bot.log`               |
| Backtest results (JSON)   | `results/backtest/*.json`    |

---

## 🛠️ Tech Stack

| Komponen    | Tools                              |
|-------------|------------------------------------|
| Language    | Python 3.10+                       |
| Broker API  | MetaTrader 5 (`MetaTrader5` lib)   |
| AI/ML       | TensorFlow (LSTM), scikit-learn    |
| Indicators  | `ta` library (pandas wrapper)      |
| Scheduler   | Built-in loop (configurable)       |
| Database    | SQLite                             |
| Monitoring  | Telegram Bot API                   |

---

## 📋 Configuration

### `.env` Variables

```bash
# Exness MT5
EXNESS_LOGIN=123456789
EXNESS_PASSWORD=your_password
EXNESS_SERVER=Exness-MT5Real8

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Pair-Specific Defaults (`config/pairs.py`)

```python
PAIR_CONFIG = {
    "XAUUSD": PairParams(
        atr_sl_multiplier=1.5,
        atr_tp_multiplier=3.0,
        max_lot=1.0,
        risk_percent=1.0,
        min_confidence=0.70,
        max_spread_points=30,
    ),
    "BTCUSD": PairParams(
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=4.0,
        max_lot=0.1,
        risk_percent=0.5,
        min_confidence=0.75,
        max_spread_points=50,
    ),
}
```

---

## ⚠️ Disclaimer

> **RISIKO TINGGI** — Trading forex & crypto mengandung risiko kehilangan modal.
>
> **Best Practices:**
> - ✅ Selalu **backtest** minimal 6 bulan data historis
> - ✅ Gunakan akun **demo** dulu sebelum live
> - ✅ Risk max **1-2%** per trade dari modal
> - ✅ Monitor bot setiap hari, jangan tinggalkan tanpa pengawasan
> - ✅ Gunakan **VPS** agar bot berjalan 24/7
> - ✅ Jangan over-optimasi model (hindari overfitting)

### VPS Rekomendasi

| Provider       | OS             | Harga      |
|----------------|----------------|------------|
| AWS EC2        | Windows Server | ~$10/bln   |
| DigitalOcean   | Windows        | ~$12/bln   |
| Vultr          | Windows        | ~$10/bln   |
| Contabo        | Windows Server | ~$7/bln    |

---

## 📜 License

MIT License — use at your own risk. This project is for educational purposes only.
