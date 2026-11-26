"""Forex — Yuling Pan phu trach (ly thuyet: xu huong + dong luong)."""
from .base import Strategy


class ForexTrend(Strategy):
    name = "ForexTrend (Yuling — Forex)"
    desk = "forex"
