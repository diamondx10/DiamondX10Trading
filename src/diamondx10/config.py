"""Doc config.yaml; neu chua co thi dung config.example.yaml / mac dinh."""
from pathlib import Path
import yaml

DEFAULT = {
    # Ngon ngu giao dien (vi | en; mac dinh vi): web UI, canh bao
    # Telegram, briefing PTCB. CLI / console / log van tieng Viet
    # khong dau.
    "language": "vi",
    "fund": {"name": "DiamondX10", "total_capital_usd": 10000,
             "desks": {"forex": {"manager": "Yuling Pan", "capital_usd": 2500},
                       "us_securities": {"manager": "Kathy", "capital_usd": 2500},
                       "xauusd": {"manager": "Yumi", "capital_usd": 2500},
                       "crypto": {"manager": "Rich", "capital_usd": 2500}}},
    "risk": {"max_risk_per_trade_pct": 1.0, "max_drawdown_pct": 10.0,
             "desk_warning_pct": 5.0,
             "default_stop_loss_pct": 5.0, "default_take_profit_pct": 5.0,
             "per_symbol_pct": {"EURUSD": 3.0, "XAUUSD": 10.0, "BTCUSD": 8.0}},
    # Chien luoc chung Phase 2 (docs/phase0-desk-rules.md): SMA5/SMA20 +
    # RSI(14), SL theo ATR, TP = 2 x khoang cach SL. Crypto ghi de rieng
    # he so ATR (stop va trailing rong hon). Bang risk giu nguyen.
    "strategy": {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14,
                 "rsi_buy_low": 50, "rsi_buy_high": 70,
                 "rsi_sell_low": 30, "rsi_sell_high": 50,
                 "rsi_extreme_high": 80, "rsi_extreme_low": 20,
                 "atr_period": 14, "atr_sl_mult": 1.5,
                 "tp_mult": 2.0, "trail_mult": 1.5,
                 "desks": {"crypto": {"atr_sl_mult": 2.0,
                                      "trail_mult": 2.0}}},
    "data": {"provider": "simulated"},
    # Kho nen OHLC local (Phase A — xem docs/history-store.md):
    # backfill keo nen MT5 demo vao SQLite data/history.db (file
    # runtime, gitignore); default_timeframe / backfill_days la gia
    # tri mac dinh cho lenh backfill / export-bars khi khong truyen
    # --timeframe / --days.
    "history": {"db_path": "data/history.db",
                "default_timeframe": "M15", "backfill_days": 90},
    # Backtest Phase 3: phi + truot gia gia dinh (xem docs/backtest.md).
    # fee_pct: % notional moi lenh tron; slippage_pct: % gia vao, ca 2 chan.
    "backtest": {"fee_pct": 0.02, "slippage_pct": 0.01},
    # Su kien cam mo lenh moi (Phase 4, Q4): danh sach mac dinh RONG —
    # Phu/Kathy bo sung CPI/FOMC/NFP/lich earnings khi co lich cu the.
    # Moi su kien: {name, start (ISO datetime — GIO BAT DAU cua so cam,
    # vd 30 phut truoc gio tin), window_minutes, symbols (tuy chon:
    # chi ap cho cac symbol do, mac dinh ap cho moi symbol)}.
    "no_trade_events": [],
}


def load_config(path=None):
    path = Path(path or "config.yaml")
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "config.example.yaml"
    if not path.exists():
        return DEFAULT
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULT)
    merged.update(data)
    return merged
