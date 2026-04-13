# 🤖 Exness AI Trading Bot — XAU/USD & BTC/USD

**SURVIVAL MODE** — Pure indicator-based trading. No LSTM. No over-complication.

AI-powered trading bot for **Exness** using proven technical indicators (EMA, RSI, MACD, Bollinger Bands) with strict risk management. Supports Gold (XAU/USD) and Bitcoin (BTC/USD).

---

## ✨ Features

- **📊 Pure Indicators** — EMA crossover + RSI + MACD + Bollinger Bands. No LSTM, no ML complexity
- **🔄 Trailing Stop** — Dynamic SL that follows profit (configurable via Telegram)
- **📱 Telegram Control Panel** — Interactive buttons, no typing needed
- **📰 News Filter** — Auto-pause during high-impact events (NFP, CPI, FOMC)
- **⏰ Session Filter** — Only trade during London/NY hours (7:00-22:00 UTC)
- **📉 Strict Risk Management** — 0.5% risk per trade, max 3 consecutive losses, daily/weekly DD limits
- **🔬 Backtest Engine** — Historical testing with performance metrics
- **🖥️ Linux & Windows Support** — Works on both platforms

---

## 📁 Project Structure

```
Ex-XAU/
├── config/
│   ├── settings.py              # Bot runtime parameters
│   └── pairs.py                 # XAU/USD & BTC/USD pair-specific params
├── data/
│   ├── collector.py             # Fetch OHLCV from MT5
│   ├── indicators.py            # RSI, MACD, BB, ATR, EMA
│   ├── news_filter.py           # News + session filter
│   └── pipeline.py              # Unified data interface
├── strategy/
│   ├── signal_generator.py      # Pure indicator-based signals (no LSTM)
│   ├── risk_manager.py          # SL, TP, lot sizing + survival safeguards
│   └── backtester.py            # Historical backtesting engine
├── execution/
│   ├── broker.py                # MT5 connection
│   ├── order_manager.py         # Open/close orders
│   └── portfolio.py             # Track open positions
├── monitoring/
│   ├── logger.py                # Structured logging
│   ├── notifier.py              # Telegram alerts
│   └── telegram_commands.py     # Interactive button control panel
├── main.py                      # Entry point + state machine + Telegram
├── backtest_xauusd.py           # Standalone backtest
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🎯 Strategy (SURVIVAL MODE)

### Entry Logic
```
For each pair (XAUUSD, BTCUSD):

  1. EMA(20/50) crossover → trend direction
  2. RSI filter → momentum confirmation
  3. MACD → momentum direction
  4. Bollinger Bands → overbought/oversold
  5. EMA200 trend filter → bias multiplier (1.3×)
  6. Combined score ≥ 0.40 → generate signal
```

### Exit Logic
- **Take Profit**: 4× ATR
- **Stop Loss**: 2× ATR (initial)
- **Trailing Stop**: Activates at 2× ATR profit, trails at 1× ATR

### Risk Rules (SURVIVAL MODE)
| Rule | Value |
|------|-------|
| Risk per trade | **0.5%** |
| Max positions per pair | **2** |
| Max daily drawdown | **3%** |
| Max weekly drawdown | **8%** |
| Max consecutive losses | **3** (auto-pause) |
| Trading hours | **07:00-22:00 UTC** only |

---

## 🐧 Setup — Linux (VPS / Cloud)

MetaTrader 5 **does not run natively on Linux**. Use one of these approaches:

### Option A: MetaAPI Cloud (Recommended)

[MetaAPI](https://metaapi.cloud/) provides a cloud-based MT5 API — no Windows needed.

```bash
pip install metaapi-cloud-sdk
# Set API token in .env: METAAPI_TOKEN=your_token
```

**Pros**: No Wine, works on any Linux, stable.
**Cons**: Paid service (~$30/mo).

### Option B: Wine (MT5 via compatibility layer)

```bash
sudo dpkg --add-architecture i386 && sudo apt update
sudo apt install wine64
wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
wine mt5setup.exe

# Then setup bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py train
python main.py live
```

### Option C: Windows VPS

| Provider  | OS             | RAM | Price    |
|-----------|----------------|-----|----------|
| Vultr     | Windows Server | 2GB | ~$10/mo  |
| Contabo   | Windows Server | 4GB | ~$7/mo   |
| AWS EC2   | Windows Server | 2GB | ~$30/mo  |

### Option D: Docker

```bash
docker pull carlosperate/mt5-wine:latest
docker run -d --name mt5-bot \
  -v $(pwd)/Ex-XAU:/app \
  -e EXNESS_LOGIN=123456 \
  -e EXNESS_PASSWORD=secret \
  carlosperate/mt5-wine python /app/main.py live
```

---

##  Setup — Windows

```powershell
# 1. Install Python 3.10+
winget install Python.Python.3.12

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
copy .env.example .env
# Edit with your credentials

# 4. Train & run
python main.py train
python main.py live
```

---

## 📱 Telegram Control Panel

Interactive buttons — **no typing needed**. Bot sends control panel on startup.

### Main Menu
```
🤖 Ex-XAU Bot (SURVIVAL MODE)
━━━━━━━━━━━━━━━━━━━━
Status: ▶️ RUNNING
Session: London-NY Overlap

📊 Trading:
• Risk: 0.5% per trade
• Confidence: 40%
• Max Pos: 2

📐 SL/TP:
• ATR SL: 2.0×
• ATR TP: 4.0×

🔄 Trailing Stop:
• Status: ✅ ON
• Act: 2.0× | Trail: 1.0×

📈 Session:
• Cycles: 42
• Consec. Loss: 0
• Balance: $523.45
• Daily DD: 0.5%

[ ⏸️ PAUSE ]  [ 🔄 TSL: ON ]
[ 📊 Risk   ]  [ 📐 SL/TP  ]
[ 🔄 TSL Params ] [ 📈 Status ]
```

### Sub-Menus

**Risk Settings** — Tap preset values:
```
[ Risk: 0.25% ] [ Risk: 0.5% ] [ Risk: 1.0% ]
[ Risk: 1.5%  ] [ Risk: 2.0%  ]
[ Conf: 35%   ] [ Conf: 40%  ] [ Conf: 50%  ]
[ Conf: 55%   ] [ Conf: 60%  ]
[ MaxPos: 1   ] [ MaxPos: 2  ] [ MaxPos: 3  ]
```

**SL/TP Settings**:
```
[ SL: 1.0× ] [ SL: 1.5× ] [ SL: 2.0× ]
[ SL: 2.5× ] [ SL: 3.0× ]
[ TP: 2.0× ] [ TP: 3.0× ] [ TP: 4.0× ]
[ TP: 5.0× ] [ TP: 6.0× ]
```

**Trailing Stop**:
```
[ 🔄 TSL: ON ]
[ Act: 1.0× ] [ Act: 1.5× ] [ Act: 2.0× ]
[ Act: 2.5× ] [ Act: 3.0× ]
[ Trail: 0.5× ] [ Trail: 1.0× ] [ Trail: 1.5× ]
[ Trail: 2.0× ]
```

### Setting Up Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow prompts → copy **Bot Token**
3. Get your **Chat ID**: send a message to your bot, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → find `"chat":{"id":123456789}`
4. Add to `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

---

## 🚀 Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env:
#   EXNESS_LOGIN, EXNESS_PASSWORD, EXNESS_SERVER
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

### 3. Fetch Historical Data

```bash
python main.py train
# Downloads 2000 bars of OHLCV data + adds indicators
# Saves to data/historical/ for backtesting
```

> Note: `train` mode no longer trains LSTM. It just fetches and saves data.

### 4. Backtest

```bash
# With simulated data
python backtest_xauusd.py

# With real MT5 CSV
python backtest_xauusd.py --csv data/historical/XAUUSD_M15.csv

# Without trailing stop
python backtest_xauusd.py --no-tsl
```

### 5. Run Live

```bash
python main.py live --interval 15
```

### 6. Check Status

```bash
python main.py status
```

---

## 🔄 Bot Flow (per 15-min cycle)

```
For each pair (XAUUSD, BTCUSD):

  1. ⏰  Check session filter (07:00-22:00 UTC only)
  2. 📰  Check news blackout → pause if high-impact event
  3. 📊  Fetch OHLCV + indicators
  4. 🧠  Generate signal (EMA + RSI + MACD + BB + EMA200 bias)
  5. ⚠️  Check spread (max 30/50 points)
  6. 📐  Check position limit (max 2 per pair)
  7. 🔄  Update trailing stop if active
  8. 💰  Calculate lot size (0.5% risk)
  9. 🎯  Calculate SL/TP (ATR-based)
  10. 📤 Execute order via MT5
  11. 📝 Log + Telegram notification
  12. 🛑  Check risk limits (consecutive losses, daily/weekly DD)
```

---

## 📊 Backtest Results (Simulated Data)

| Metric          | Value     |
|-----------------|-----------|
| Net Profit      | +$3,741   |
| Total Return    | +748%     |
| Win Rate        | 51.6%     |
| Profit Factor   | 1.21      |
| Max Drawdown    | 81.2%     |
| Sharpe Ratio    | 1.43      |
| Total Trades    | 155       |

> ⚠️ **Results on simulated data only**. Always backtest with real MT5 data and demo trade first.
> Max drawdown is high on simulated data due to random walk nature. Real trending data typically produces lower drawdown.

---

## 📊 Performance Tracking

| Artifact                | Location                  |
|-------------------------|---------------------------|
| Trade journal (SQLite)  | `data/trading_journal.db` |
| Bot log (rotating)      | `logs/bot.log`            |
| Backtest results (JSON) | `results/backtest_xauusd.json` |

---

## 🛠️ Tech Stack

| Component    | Tools                                   |
|--------------|-----------------------------------------|
| Language     | Python 3.10+                            |
| Broker API   | MetaTrader 5 / MetaAPI Cloud            |
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

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

### Pair-Specific Parameters (`config/pairs.py`)

```python
PAIR_CONFIG = {
    "XAUUSD": PairParams(
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=4.0,
        max_lot=1.0,
        risk_percent=0.5,            # SURVIVAL MODE
        min_confidence=0.40,
        max_spread_points=30,
        pip_value_per_lot=10.0,
    ),
    "BTCUSD": PairParams(
        atr_sl_multiplier=2.5,
        atr_tp_multiplier=5.0,
        max_lot=0.1,
        risk_percent=0.5,
        min_confidence=0.40,
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
> - ✅ Risk max **0.5-1%** per trade
> - ✅ Monitor bot daily — don't leave unattended
> - ✅ Use **VPS** for 24/7 uptime
> - ✅ Avoid over-optimization
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
