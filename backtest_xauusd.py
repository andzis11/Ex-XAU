"""
backtest_xauusd.py — Standalone Backtest untuk Ex-XAU
======================================================
Strategi: EMA crossover + RSI filter + ATR-based SL/TP
Pair    : XAU/USD (H1)
Modal   : $500 (simulasi)

Cara pakai:
  python backtest_xauusd.py                        # pakai data sample bawaan
  python backtest_xauusd.py --csv data/XAUUSD.csv  # pakai CSV dari MT5 export
"""

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    USE_PANDAS_TA = True
except ImportError:
    USE_PANDAS_TA = False


# ─────────────────────────────────────────────
# 1. CONFIG
# ─────────────────────────────────────────────

@dataclass
class BacktestConfig:
    initial_balance: float = 500.0       # Modal awal ($)
    risk_percent: float = 1.0            # Risk per trade (% dari balance)
    atr_sl_mult: float = 2.0             # SL = ATR × multiplier (OPTIMIZED: 2.0)
    atr_tp_mult: float = 4.0             # TP = ATR × multiplier (OPTIMIZED: 4.0)
    atr_period: int = 14
    ema_fast: int = 20                   # OPTIMIZED: 20 (was 9-20)
    ema_slow: int = 50                   # OPTIMIZED: 50
    rsi_period: int = 14
    rsi_ob: float = 65.0                 # OPTIMIZED: 65 (was 70)
    rsi_os: float = 35.0                 # OPTIMIZED: 35 (was 30)
    min_confidence: float = 0.55         # OPTIMIZED: 55% (was 60%)
    max_spread_pips: float = 30.0
    pip_value_per_lot: float = 10.0      # XAU: $10 per pip per lot
    commission_per_lot: float = 7.0      # Round-trip commission
    lot_size: float = 0.01               # Fixed micro lot
    use_ema200_filter: bool = True       # OPTIMIZED: ON
    trend_bias: float = 0.30             # OPTIMIZED: 0.30


# ─────────────────────────────────────────────
# 2. INDICATORS
# ─────────────────────────────────────────────

def add_indicators(df: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # EMA
    df["ema_fast"] = close.ewm(span=cfg.ema_fast, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=cfg.ema_slow, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_g = gain.ewm(com=cfg.rsi_period - 1, adjust=False).mean()
    avg_l = loss.ewm(com=cfg.rsi_period - 1, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(com=cfg.atr_period - 1, adjust=False).mean()

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_mid"]   = sma20

    # EMA trend
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    return df.dropna()


# ─────────────────────────────────────────────
# 3. SIGNAL GENERATOR
# ─────────────────────────────────────────────

def generate_signal(row: pd.Series, prev: pd.Series, cfg: BacktestConfig) -> dict:
    """
    Skor berbasis confluence dari 4 indikator.
    Tiap konfirmasi menambah bobot.
    """
    buy_score  = 0.0
    sell_score = 0.0
    reasons    = []

    # ── EMA Crossover (bobot 0.35) ──
    ema_cross_up   = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
    ema_cross_down = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]
    ema_trend_bull = row["ema_fast"] > row["ema_slow"]
    ema_trend_bear = row["ema_fast"] < row["ema_slow"]

    if ema_cross_up:
        buy_score += 0.35
        reasons.append("EMA crossover UP")
    elif ema_trend_bull:
        buy_score += 0.15
        reasons.append("EMA trend bull")

    if ema_cross_down:
        sell_score += 0.35
        reasons.append("EMA crossover DOWN")
    elif ema_trend_bear:
        sell_score += 0.15
        reasons.append("EMA trend bear")

    # ── RSI Filter (bobot 0.25) ──
    if row["rsi"] < 50 and row["rsi"] > cfg.rsi_os:
        buy_score += 0.25
        reasons.append(f"RSI bullish ({row['rsi']:.0f})")
    elif row["rsi"] > 50 and row["rsi"] < cfg.rsi_ob:
        sell_score += 0.25
        reasons.append(f"RSI bearish ({row['rsi']:.0f})")

    # ── MACD (bobot 0.20) ──
    if row["macd"] > row["macd_signal"] and row["macd_hist"] > 0:
        buy_score += 0.20
        reasons.append("MACD bull")
    elif row["macd"] < row["macd_signal"] and row["macd_hist"] < 0:
        sell_score += 0.20
        reasons.append("MACD bear")

    # ── Bollinger Band (bobot 0.20) ──
    if row["close"] < row["bb_lower"]:
        buy_score += 0.20
        reasons.append("BB oversold")
    elif row["close"] > row["bb_upper"]:
        sell_score += 0.20
        reasons.append("BB overbought")
    elif row["close"] > row["bb_mid"]:
        buy_score += 0.10
    else:
        sell_score += 0.10

    # ── Trend filter (EMA200) — OPTIMIZED ──
    if cfg.use_ema200_filter:
        above_ema200 = row["close"] > row["ema200"]
        if above_ema200:
            # Strong bias toward BUY in uptrend
            buy_score  *= (1 + cfg.trend_bias)
            sell_score *= (1 - cfg.trend_bias * 0.5)
        else:
            # Strong bias toward SELL in downtrend
            buy_score  *= (1 - cfg.trend_bias * 0.5)
            sell_score *= (1 + cfg.trend_bias)

    # ── Tentukan arah ──
    if buy_score >= cfg.min_confidence and buy_score > sell_score:
        return {"direction": "BUY",  "confidence": buy_score,  "reasons": reasons}
    if sell_score >= cfg.min_confidence and sell_score > buy_score:
        return {"direction": "SELL", "confidence": sell_score, "reasons": reasons}
    return {"direction": "HOLD", "confidence": 0.0, "reasons": []}


# ─────────────────────────────────────────────
# 4. TRADE & POSITION
# ─────────────────────────────────────────────

@dataclass
class Trade:
    idx: int
    time: datetime
    symbol: str = "XAUUSD"
    direction: str = ""
    entry: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    lot: float = 0.01
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    exit_reason: str = ""
    pnl: float = 0.0
    commission: float = 0.0
    net_pnl: float = 0.0
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# 5. BACKTEST ENGINE
# ─────────────────────────────────────────────

class Backtest:
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg
        self.balance = cfg.initial_balance
        self.peak_balance = cfg.initial_balance
        self.trades: List[Trade] = []
        self.equity_curve: List[dict] = []
        self.open_trade: Optional[Trade] = None
        self.trade_idx = 0

    def run(self, df: pd.DataFrame) -> "BacktestResult":
        df = add_indicators(df, self.cfg)
        rows = df.reset_index()

        for i in range(1, len(rows)):
            row  = rows.iloc[i]
            prev = rows.iloc[i - 1]
            ts   = row.get("index", row.get("datetime", i))

            # ── Check open trade ──
            if self.open_trade:
                self._check_exit(row, ts)

            # ── Generate signal ──
            if not self.open_trade:
                sig = generate_signal(row, prev, self.cfg)
                if sig["direction"] in ("BUY", "SELL"):
                    self._open_trade(row, sig, ts)

            # ── Record equity ──
            mark = self._mark_to_market(row)
            self.equity_curve.append({
                "time": str(ts),
                "balance": round(self.balance, 2),
                "equity": round(mark, 2),
            })
            self.peak_balance = max(self.peak_balance, mark)

        # Close any remaining trade at end
        if self.open_trade:
            last = rows.iloc[-1]
            self._force_close(last, last.get("index", len(rows) - 1))

        return BacktestResult(self.cfg, self.trades, self.equity_curve, self.cfg.initial_balance)

    def _open_trade(self, row, sig, ts):
        cfg = self.cfg
        atr = row["atr"]
        entry = row["close"]
        d = sig["direction"]

        if d == "BUY":
            sl = entry - atr * cfg.atr_sl_mult
            tp = entry + atr * cfg.atr_tp_mult
        else:
            sl = entry + atr * cfg.atr_sl_mult
            tp = entry - atr * cfg.atr_tp_mult

        # Lot sizing: risk % of balance
        sl_dist = abs(entry - sl)
        risk_amt = self.balance * (cfg.risk_percent / 100)
        lot = round(risk_amt / (sl_dist * cfg.pip_value_per_lot / 0.01), 2)
        lot = max(0.01, min(lot, 1.0))  # clamp micro to 1.0 lot

        self.open_trade = Trade(
            idx=self.trade_idx,
            time=ts,
            direction=d,
            entry=entry,
            sl=sl,
            tp=tp,
            lot=lot,
            confidence=sig["confidence"],
            reasons=sig["reasons"],
        )
        self.trade_idx += 1

    def _check_exit(self, row, ts):
        t = self.open_trade
        hit_sl = hit_tp = False

        if t.direction == "BUY":
            if row["low"] <= t.sl:
                hit_sl = True
                exit_p = t.sl
            elif row["high"] >= t.tp:
                hit_tp = True
                exit_p = t.tp
            else:
                return
        else:
            if row["high"] >= t.sl:
                hit_sl = True
                exit_p = t.sl
            elif row["low"] <= t.tp:
                hit_tp = True
                exit_p = t.tp
            else:
                return

        t.exit_price = exit_p
        t.exit_time  = ts
        t.exit_reason = "SL" if hit_sl else "TP"

        pip_dist = (exit_p - t.entry) if t.direction == "BUY" else (t.entry - exit_p)
        gross_pnl = pip_dist * self.cfg.pip_value_per_lot * t.lot / 0.01
        commission = self.cfg.commission_per_lot * t.lot
        t.pnl       = round(gross_pnl, 2)
        t.commission = round(commission, 2)
        t.net_pnl   = round(gross_pnl - commission, 2)

        self.balance += t.net_pnl
        self.trades.append(t)
        self.open_trade = None

    def _force_close(self, row, ts):
        t = self.open_trade
        t.exit_price  = row["close"]
        t.exit_time   = ts
        t.exit_reason = "END"
        pip_dist = (t.exit_price - t.entry) if t.direction == "BUY" else (t.entry - t.exit_price)
        gross = pip_dist * self.cfg.pip_value_per_lot * t.lot / 0.01
        comm  = self.cfg.commission_per_lot * t.lot
        t.pnl = round(gross, 2)
        t.commission = round(comm, 2)
        t.net_pnl = round(gross - comm, 2)
        self.balance += t.net_pnl
        self.trades.append(t)
        self.open_trade = None

    def _mark_to_market(self, row) -> float:
        if not self.open_trade:
            return self.balance
        t = self.open_trade
        p = row["close"]
        pip_dist = (p - t.entry) if t.direction == "BUY" else (t.entry - p)
        unrealized = pip_dist * self.cfg.pip_value_per_lot * t.lot / 0.01
        return self.balance + unrealized


# ─────────────────────────────────────────────
# 6. RESULT & REPORT
# ─────────────────────────────────────────────

class BacktestResult:
    def __init__(self, cfg, trades, equity_curve, initial_balance):
        self.cfg = cfg
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_balance = initial_balance
        self._compute()

    def _compute(self):
        t = self.trades
        self.total_trades  = len(t)
        if not t:
            self.win_rate = self.avg_win = self.avg_loss = 0.0
            self.profit_factor = self.max_dd = self.net_profit = 0.0
            self.sharpe = 0.0
            return

        wins   = [x for x in t if x.net_pnl > 0]
        losses = [x for x in t if x.net_pnl <= 0]
        self.win_rate     = len(wins) / len(t) * 100
        self.avg_win      = np.mean([x.net_pnl for x in wins]) if wins else 0
        self.avg_loss     = np.mean([x.net_pnl for x in losses]) if losses else 0
        gross_profit      = sum(x.net_pnl for x in wins)
        gross_loss        = abs(sum(x.net_pnl for x in losses))
        self.profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
        self.net_profit   = sum(x.net_pnl for x in t)

        # Max drawdown
        eq = [e["equity"] for e in self.equity_curve]
        peak = eq[0]
        max_dd = 0.0
        for e in eq:
            peak = max(peak, e)
            dd = (peak - e) / peak * 100
            max_dd = max(max_dd, dd)
        self.max_dd = max_dd

        # Sharpe (simplified daily)
        pnls = [x.net_pnl for x in t]
        self.sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if np.std(pnls) > 0 else 0

        # Daily stats
        df_t = pd.DataFrame([{
            "date": str(x.time)[:10],
            "pnl": x.net_pnl
        } for x in t])
        daily = df_t.groupby("date")["pnl"].sum()
        self.avg_daily_pnl  = daily.mean() if len(daily) else 0
        self.best_day       = daily.max() if len(daily) else 0
        self.worst_day      = daily.min() if len(daily) else 0
        self.days_traded    = len(daily)

    def print_report(self):
        final_balance = self.initial_balance + self.net_profit
        total_return  = self.net_profit / self.initial_balance * 100

        sep = "=" * 52
        print(f"\n{sep}")
        print(f"  BACKTEST REPORT — XAUUSD H1")
        print(f"{sep}")
        print(f"  Modal awal     : ${self.initial_balance:>10.2f}")
        print(f"  Modal akhir    : ${final_balance:>10.2f}")
        print(f"  Net profit     : ${self.net_profit:>+10.2f}  ({total_return:+.1f}%)")
        print(f"{sep}")
        print(f"  Total trades   : {self.total_trades}")
        print(f"  Win rate       : {self.win_rate:.1f}%")
        print(f"  Profit factor  : {self.profit_factor:.2f}  (>1.5 = bagus)")
        print(f"  Avg win        : ${self.avg_win:>+.2f}")
        print(f"  Avg loss       : ${self.avg_loss:>+.2f}")
        print(f"  Reward/Risk    : {abs(self.avg_win/self.avg_loss):.2f}x" if self.avg_loss else "  Reward/Risk    : ∞")
        print(f"{sep}")
        print(f"  Max drawdown   : {self.max_dd:.1f}%")
        print(f"  Sharpe ratio   : {self.sharpe:.2f}  (>1.0 = layak)")
        print(f"{sep}")
        print(f"  Hari trading   : {self.days_traded}")
        print(f"  Avg profit/hari: ${self.avg_daily_pnl:>+.2f}")
        print(f"  Hari terbaik   : ${self.best_day:>+.2f}")
        print(f"  Hari terburuk  : ${self.worst_day:>+.2f}")
        print(f"{sep}")

        # Assessment
        print(f"\n  ASSESSMENT:")
        if self.profit_factor >= 1.5 and self.win_rate >= 50 and self.max_dd <= 20:
            verdict = "✅ LAYAK untuk demo trading"
        elif self.profit_factor >= 1.2 and self.win_rate >= 45:
            verdict = "⚠️  PERLU OPTIMASI sebelum demo"
        else:
            verdict = "❌ BELUM LAYAK — strategi perlu direvisi"
        print(f"  {verdict}")

        if self.avg_daily_pnl > 0:
            days_to_20 = 20 / self.avg_daily_pnl if self.avg_daily_pnl else float("inf")
            print(f"  Target $20/hari: perlu ~{days_to_20:.0f}x lipat avg profit harian")
        print(f"{sep}\n")

    def save_json(self, path: str):
        data = {
            "summary": {
                "initial_balance": self.initial_balance,
                "final_balance": round(self.initial_balance + self.net_profit, 2),
                "net_profit": round(self.net_profit, 2),
                "total_return_pct": round(self.net_profit / self.initial_balance * 100, 2),
                "total_trades": self.total_trades,
                "win_rate": round(self.win_rate, 2),
                "profit_factor": round(self.profit_factor, 3),
                "max_drawdown_pct": round(self.max_dd, 2),
                "sharpe_ratio": round(self.sharpe, 3),
                "avg_daily_pnl": round(self.avg_daily_pnl, 2),
            },
            "trades": [
                {
                    "id": t.idx,
                    "time": str(t.time),
                    "direction": t.direction,
                    "entry": round(t.entry, 2),
                    "sl": round(t.sl, 2),
                    "tp": round(t.tp, 2),
                    "lot": t.lot,
                    "exit": round(t.exit_price, 2),
                    "exit_reason": t.exit_reason,
                    "net_pnl": t.net_pnl,
                    "confidence": round(t.confidence, 3),
                }
                for t in self.trades
            ],
        }
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Hasil disimpan: {path}")


# ─────────────────────────────────────────────
# 7. DATA LOADER
# ─────────────────────────────────────────────

def load_data(csv_path: Optional[str] = None) -> pd.DataFrame:
    if csv_path and os.path.exists(csv_path):
        print(f"  Memuat data dari: {csv_path}")
        df = pd.read_csv(csv_path)
        # Normalize column names
        df.columns = [c.lower().strip() for c in df.columns]
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                raise ValueError(f"Kolom '{col}' tidak ditemukan. Pastikan CSV dari MT5 format standard.")
        return df
    else:
        print("  Menggunakan data simulasi XAU/USD (2000 candle H1)...")
        np.random.seed(42)
        n = 2000
        dates = pd.date_range("2024-01-01", periods=n, freq="1h")
        # Simulate realistic XAU/USD with trending behavior
        returns = np.random.normal(0.0001, 0.003, n)
        # Add trending periods
        for i in range(0, n, 200):
            trend = np.random.choice([-1, 1]) * 0.0005
            returns[i:i+200] += trend
        price = 2000.0 * np.cumprod(1 + returns)
        noise_h = abs(np.random.normal(0, 0.002, n))
        noise_l = abs(np.random.normal(0, 0.002, n))
        df = pd.DataFrame({
            "open":   price,
            "high":   price * (1 + noise_h),
            "low":    price * (1 - noise_l),
            "close":  price * (1 + np.random.normal(0, 0.001, n)),
            "volume": np.random.randint(500, 8000, n),
        }, index=dates)
        return df


# ─────────────────────────────────────────────
# 8. MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backtest Ex-XAU Strategy")
    parser.add_argument("--csv",       type=str,   default=None,  help="Path ke CSV OHLCV dari MT5")
    parser.add_argument("--balance",   type=float, default=500.0, help="Modal awal (default: 500)")
    parser.add_argument("--risk",      type=float, default=1.0,   help="Risk per trade % (default: 1)")
    parser.add_argument("--atr-sl",    type=float, default=2.0,   help="ATR SL multiplier (OPTIMIZED: 2.0)")
    parser.add_argument("--atr-tp",    type=float, default=4.0,   help="ATR TP multiplier (OPTIMIZED: 4.0)")
    parser.add_argument("--conf",      type=float, default=0.55,  help="Min confidence (OPTIMIZED: 0.55)")
    parser.add_argument("--rsi-os",    type=float, default=35.0,  help="RSI oversold (OPTIMIZED: 35)")
    parser.add_argument("--rsi-ob",    type=float, default=65.0,  help="RSI overbought (OPTIMIZED: 65)")
    parser.add_argument("--no-ema200", action="store_true",       help="Disable EMA200 trend filter")
    parser.add_argument("--bias",      type=float, default=0.30,  help="Trend bias (OPTIMIZED: 0.30)")
    parser.add_argument("--out",       type=str,   default="results/backtest_xauusd.json")
    args = parser.parse_args()

    print("\n" + "=" * 52)
    print("  EX-XAU BACKTEST ENGINE")
    print("=" * 52)
    print(f"  Modal    : ${args.balance}")
    print(f"  Risk/trd : {args.risk}%")
    print(f"  SL mult  : {args.atr_sl}× ATR")
    print(f"  TP mult  : {args.atr_tp}× ATR")
    print(f"  Min conf : {args.conf*100:.0f}%")

    cfg = BacktestConfig(
        initial_balance=args.balance,
        risk_percent=args.risk,
        atr_sl_mult=args.atr_sl,
        atr_tp_mult=args.atr_tp,
        min_confidence=args.conf,
        rsi_os=args.rsi_os,
        rsi_ob=args.rsi_ob,
        use_ema200_filter=not args.no_ema200,
        trend_bias=args.bias,
    )

    df     = load_data(args.csv)
    engine = Backtest(cfg)

    print(f"\n  Menjalankan backtest ({len(df)} candle)...")
    result = engine.run(df)
    result.print_report()
    result.save_json(args.out)


if __name__ == "__main__":
    main()
