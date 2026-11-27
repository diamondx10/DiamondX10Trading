"""Forex — Yuling Pan phu trach (ly thuyet: xu huong + dong luong)."""
from .base import Strategy


class ForexTrend(Strategy):
    name = "ForexTrend (Yuling — Forex)"
    desk = "forex"
    # Dung quy tac chung Phase 0 (SMA + RSI, SL 1,5 x ATR, TP 2:1).
