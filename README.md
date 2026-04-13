# 🤖 Exness AI Trading Bot — XAU/USD & BTC/USD

AI-powered trading bot for **Exness** using **LSTM neural networks**, technical indicators, and interactive Telegram control. Supports Gold (XAU/USD) and Bitcoin (BTC/USD) with pair-specific risk parameters.

---

## ✨ Features

- **🧠 LSTM Neural Network** — Trained per pair for BUY/SELL/HOLD prediction
- **📊 Technical Confluence** — EMA, RSI, MACD, Bollinger Bands, ATR
- **🔄 Trailing Stop** — Dynamic SL that follows profit (configurable via Telegram)
- **📱 Telegram Control Panel** — Interactive buttons, no typing needed
- **📰 News Filter** — Auto-pause during high-impact events (NFP, CPI, FOMC)
- **📉 Daily Drawdown Limit** — Auto-pause when daily loss exceeds threshold
- **🔬 Backtest Engine** — Historical testing with performance metrics
- **⚙️ Parameter Optimizer** — Grid search for optimal strategy settings
- **🖥️ Linux & Windows Support** — Works on both platforms

---

## 📁 Project Structure

```
Ex-XAU/
│
├── config/
│   ├── settings.py              # Bot runtime parameters
│   └── pairs.py                 # XAU/USD & BTC/USD pair-specific params
│
├── data/
│   ├── collector.py             # Fetch OHLCV from MT5
│   ├── indicators.py            # RSI, MACD, BB, ATR, EMA
│   ├── preprocessor.py          # Feature scaling & sequence generation
│   ├── news_filter.py           # Auto-pause on high-impact news
│   └── pipeline.py              # Unified data interface
│
├── models/
│   ├── trainer.py               # LSTM training (TensorFlow)
│   ├── predictor.py             # Live inference
│   └── saved_models/            # .h5 model files
│
├── strategy/
│   ├── signal_generator.py      # BUY/SELL/HOLD + indicator confirmation
│   ├── risk_manager.py          # SL, TP, lot sizing (pair-specific)
│   └── backtester.py            # Historical backtesting engine
│
├── execution/
│   ├── broker.py                # MT5 connection
│   ├── order_manager.py         # Open/close orders
│   ├── order_executor.py        # Order execution logic
│   ├── portfolio.py             # Track open positions
│   └── signal_generator.py      # Legacy signal gen
│
├── monitoring/
│   ├── logger.py                # Structured logging
│   ├── notifier.py              # Telegram alerts
│   └── telegram_commands.py     # Interactive button control panel
│
├── risk/
│   └── manager.py               # Risk assessment (Layer 4)
│
├── backtest/                    # Trade journal
│   └── trade_journal.py
│
├── main.py                      # Entry point + state machine + Telegram
├── backtest_xauusd.py           # Standalone backtest (simulated/real data)
├── optimize_params.py           # Grid search parameter optimizer
├── requirements.txt
├── .env.example
└── README.md
```

---

## ️ Setup — Windows (Native MT5)

### Prerequisites

- Windows 10/11
- Python 3.10+
- MetaTrader 5 terminal installed

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 2. Configure

```powershell
copy .env.example .env
# Edit .env with your Exness credentials & Telegram token
```

### 3. Train Models

```powershell
python main.py train
```

Fetches 2000 bars of historical data, trains LSTM models per pair, saves `.h5` files.

### 4. Run Live

```powershell
python main.py live --interval 15
```

---

## 🐧 Setup — Linux (VPS / Cloud)

MetaTrader 5 **does not run natively on Linux**. Use one of these approaches:

### Option A: Wine (MT5 via compatibility layer)

```bash
# Install Wine
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install wine64

# Download MT5
wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
wine mt5setup.exe

# Install Python deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure & run
cp .env.example .env
python main.py train
python main.py live
```

> **Note**: Wine + MT5 works but may be unstable. Test thoroughly before live trading.

### Option B: MetaAPI Cloud (Recommended for Linux)

[MetaAPI](https://metaapi.cloud/) provides a cloud-based MT5 API — no Windows needed.

```bash
# Install MetaAPI SDK
pip install metaapi-cloud-sdk

# Set API token in .env
echo "METAAPI_TOKEN=your_metaapi_token" >> .env

# Use MetaAPI client instead of native MT5
# See data/metaapi_client.py for integration
```

**Pros**: No Wine, works on any Linux, no VPS Windows license needed.
**Cons**: Paid service (~$30/mo for live account).

### Option C: Windows VPS

Run the bot on a Windows VPS where MT5 runs natively:

| Provider  | OS             | RAM  | Price      |
|-----------|----------------|------|------------|
| Vultr     | Windows Server | 2GB  | ~$10/mo    |
| Contabo   | Windows Server | 4GB  | ~$7/mo     |
| AWS EC2   | Windows Server | 2GB  | ~$30/mo    |
| DigitalOcean | Windows     | 2GB  | ~$12/mo    |

**Setup steps on VPS**:

```powershell
# 1. RDP into VPS

# 2. Install Python
winget install Python.Python.3.12

# 3. Install MT5
# Download from exness.com or metaquotes.net

# 4. Clone repo
git clone https://github.com/andzis11/Ex-XAU.git
cd Ex-XAU

# 5. Setup
pip install -r requirements.txt
copy .env.example .env
# Edit .env with credentials

# 6. Train & run
python main.py train
python main.py live
```

### Option D: Docker (Wine-based container)

```bash
docker pull carlosperate/mt5-wine:latest
docker run -d --name mt5-bot \
  -v $(pwd)/Ex-XAU:/app \
  -e EXNESS_LOGIN=123456 \
  -e EXNESS_PASSWORD=secret \
  -e TELEGRAM_BOT_TOKEN=token \
  carlosperate/mt5-wine python /app/main.py live
```

---

## 📱 Telegram Control Panel

Interactive buttons — **no typing needed**. Bot sends control panel on startup.

### Main Menu

```
🤖 Ex-XAU Bot Control Panel
━━━━━━━━━━━━━━━━━━━━
Status: ▶️ RUNNING

📊 Trading:
• Risk: 1.0% per trade
• Confidence: 55%
• Max Pos: 3

📐 SL/TP:
• ATR SL: 2.0×
• ATR TP: 4.0×

🔄 Trailing Stop:
• Status: ✅ ON
• Activation: 2.5× ATR
• Trail: 1.5× ATR

[ ⏸️ PAUSE ]  [ 🔄 TSL: ON ]
[ 📊 Risk   ]  [ 📐 SL/TP  ]
[ 🔄 TSL Params ] [ 📈 Status ]
```

### Sub-Menus

**Risk Settings** — Tap preset values:
```
[ Risk: 0.25% ] [ Risk: 0.5% ] [ Risk: 1.0% ]
[ Risk: 1.5%  ] [ Risk: 2.0% ] [ Risk: 3.0% ]
[ Conf: 50%   ] [ Conf: 55%  ] [ Conf: 60%  ]
[ Conf: 65%   ] [ Conf: 70%  ]
[ MaxPos: 1   ] [ MaxPos: 2  ] [ MaxPos: 3  ]
```

**SL/TP Settings**:
```
[ SL: 1.0× ] [ SL: 1.5× ] [ SL: 2.0× ]
[ SL: 2.5× ] [ SL: 3.0× ]
[ TP: 2.0× ] [ TP: 3.0× ] [ TP: 4.0× ]
[ TP: 5.0× ] [ TP: 6.0× ]
```

**Trailing Stop Settings**:
```
[ 🔄 TSL: ON ]
[ Act: 1.0× ] [ Act: 1.5× ] [ Act: 2.0× ]
[ Act: 2.5× ] [ Act: 3.0× ]
[ Trail: 0.5× ] [ Trail: 1.0× ] [ Trail: 1.5× ]
[ Trail: 2.0× ]
```

### Setting Up Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow prompts
3. Copy the **Bot Token**
4. Get your **Chat ID**:
   - Send a message to your new bot
   - Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Find `"chat":{"id":123456789}` → that's your chat ID
5. Add to `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

---

## ⚙️ Optimized Parameters (Grid Search Results)

Parameters optimized via **864 combination grid search**:

| Parameter        | Before | **Optimized** | Impact |
|------------------|--------|---------------|--------|
| ATR SL           | 1.5×   | **2.0×**      | Less whipsaw |
| ATR TP           | 3.0×   | **4.0×**      | Better R:R |
| RSI Oversold     | 30     | **35**        | Earlier BUY signals |
| RSI Overbought   | 70     | **65**        | Earlier SELL signals |
| Min Confidence   | 60-70% | **55%**       | More trade opportunities |
| EMA200 Bias      | 1.1×   | **1.3×**      | Stronger trend filter |
| Trailing Stop    | OFF    | **ON** (2.5×/1.5×) | Profit protection |

### Backtest Results (Simulated Data)

| Metric        | Before | **After** |
|---------------|--------|-----------|
| Net Profit    | -$353  | **+$12,408** |
| Win Rate      | 34.1%  | **53.3%** |
| Profit Factor | 0.93   | **2.36** |
| Max Drawdown  | 122%   | **58.7%** |
| Sharpe Ratio  | -0.55  | **6.47** |

> ⚠️ **Results on simulated data only**. Always backtest with real MT5 data and demo trade first.

---

## 🔄 State Machine

```
INITIALIZING → CONNECTED → RUNNING ↔ PAUSED
                                ↓
                             STOPPING → STOPPED
                                ↓
                              ERROR
```

| State          | Trigger                                    |
|----------------|--------------------------------------------|
| `INITIALIZING` | Bot starting up                            |
| `CONNECTED`    | MT5 login successful                       |
| `RUNNING`      | Normal trading (every 15 min)              |
| `PAUSED`       | News event / drawdown limit / manual pause |
| `STOPPING`     | Graceful shutdown (SIGINT/SIGTERM)         |
| `STOPPED`      | Bot fully stopped                          |
| `ERROR`        | Connection lost / no models loaded         |

---

## 🚀 Quick Start

### 1. Install

```bash
# Windows
pip install -r requirements.txt

# Linux (with Wine or MetaAPI)
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env:
#   EXNESS_LOGIN, EXNESS_PASSWORD, EXNESS_SERVER
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

### 3. Train Models (Required Before Live)

```bash
python main.py train
```

> Without trained models, bot will refuse to start (safety check).

### 4. Run Live

```bash
python main.py live --interval 15
```

### 5. Backtest

```bash
# With simulated data
python backtest_xauusd.py

# With real MT5 CSV
python backtest_xauusd.py --csv data/XAUUSD_H1.csv

# Without trailing stop (compare)
python backtest_xauusd.py --no-tsl
```

### 6. Optimize Parameters

```bash
python optimize_params.py
```

### 7. Check Status

```bash
python main.py status
```

---

## 🔄 Bot Flow (per 15-min cycle)

```
For each pair (XAUUSD, BTCUSD):

  1. 📰  Check news blackout → pause if high-impact event
  2. 📊  Fetch OHLCV + indicators (M15/H1/H4)
  3. 🧠  LSTM prediction → BUY/SELL/HOLD + confidence
  4. ✅  Indicator confirmation (EMA, RSI, MACD, BB)
  5. ⚠️  Check spread (max 30/50 points)
  6. 📐  Check position limit (max 3 open per pair)
  7. 🔄  Update trailing stop if active
  8. 💰  Calculate lot size (risk-based, pair-specific)
  9. 🎯  Calculate SL/TP (ATR-based, pair-specific)
  10. 📤 Execute order via MT5
  11. 📝 Log + Telegram notification
```

---

## 📊 Performance Tracking

| Artifact                | Location                  |
|-------------------------|---------------------------|
| Trade journal (SQLite)  | `data/trading_journal.db` |
| Bot log (rotating)      | `logs/bot.log`            |
| Backtest results (JSON) | `results/backtest/*.json` |
| Optimized params (JSON) | `results/optimized_params.json` |

---

## 🛠️ Tech Stack

| Component    | Tools                                   |
|--------------|-----------------------------------------|
| Language     | Python 3.10+                            |
| Broker API   | MetaTrader 5 / MetaAPI Cloud            |
| AI/ML        | TensorFlow (LSTM), scikit-learn         |
| Indicators   | `ta` library (pandas wrapper)           |
| Notifications| Telegram Bot API (inline keyboards)     |
| Data Fetch   | yfinance (fallback for backtest)        |
| Database     | SQLite                                  |

---

## 📋 Configuration

### `.env` Variables

```bash
# Exness MT5
EXNESS_LOGIN=123456789
EXNESS_PASSWORD=your_password
EXNESS_SERVER=Exness-MT5Real8

# Telegram (for control panel + alerts)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

### Pair-Specific Parameters (`config/pairs.py`)

```python
PAIR_CONFIG = {
    "XAUUSD": PairParams(
        atr_sl_multiplier=2.0,       # Optimized
        atr_tp_multiplier=4.0,       # Optimized
        max_lot=1.0,
        risk_percent=1.0,
        min_confidence=0.55,         # Optimized
        max_spread_points=30,
        pip_value_per_lot=10.0,
    ),
    "BTCUSD": PairParams(
        atr_sl_multiplier=2.5,       # Optimized
        atr_tp_multiplier=5.0,       # Optimized
        max_lot=0.1,
        risk_percent=0.5,
        min_confidence=0.60,         # Optimized
        max_spread_points=50,
        pip_value_per_lot=1.0,
    ),
}
```

---

## ⚠️ Disclaimer

> **HIGH RISK** — Forex & crypto trading carries significant risk of capital loss.
>
> **Best Practices:**
> - ✅ **Always backtest** on real historical data before live trading
> - ✅ Use **demo account** for 2-4 weeks minimum
> - ✅ Risk max **1-2%** per trade
> - ✅ Monitor bot daily — don't leave unattended
> - ✅ Use **VPS** for 24/7 uptime
> - ✅ Avoid over-optimization (overfitting risk)
> - ✅ **Never trade money you can't afford to lose**

### Realistic Expectations

| Modal    | Target Realistis/Hari | Target Realistis/Bulan |
|----------|-----------------------|------------------------|
| $500     | $5–$10                | $100–$200              |
| $1,000   | $10–$20               | $200–$400              |
| $5,000   | $50–$100              | $1,000–$2,000          |

> Target $20/hari dari modal $500 = 4%/hari = **tidak realistis** tanpa risiko blown.

---

## 📜 License

MIT License — use at your own risk. This project is for **educational purposes only**.

---

## 🤝 Contributing

Pull requests welcome. Please test changes on demo account before merging.
