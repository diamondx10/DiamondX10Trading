"""XAUUSD (vang) — Yumi phu trach."""
from .base import Strategy


class XauusdTrend(Strategy):
    name = "XauusdTrend (Yumi — XAUUSD)"
    desk = "xauusd"
    # Dung quy tac chung Phase 0 (SMA + RSI, SL 1,5 x ATR, TP 2:1);
    # nguong RSI rieng cho vang chi tach sau neu backtest cho thay can.
