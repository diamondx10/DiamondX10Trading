"""Chung khoan My — Kathy phu trach: co phieu cong nghe AI, chip, EDA tool."""
from .base import Strategy


class USSecTrend(Strategy):
    name = "USSecTrend (Kathy — US AI/chip/EDA)"
    desk = "us_securities"
