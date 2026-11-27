"""Chung khoan My — Kathy phu trach: co phieu cong nghe AI, chip, EDA tool."""
from .base import Strategy


class USSecTrend(Strategy):
    name = "USSecTrend (Kathy — US AI/chip/EDA)"
    desk = "us_securities"
    # Dung quy tac chung Phase 0 (SMA + RSI, SL 1,5 x ATR, TP 2:1);
    # NVDA tach nguong rieng sau chi khi backtest cho thay can.
