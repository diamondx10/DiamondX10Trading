"""Lop co so cho moi chien luoc. Moi chien luoc tra ve 1 trong
BUY / SELL / HOLD + ly do (de ghi vao decisions log)."""
from ..models.quant import sma


class Strategy:
    name = "base"
    desk = ""

    def signal(self, bars):
        closes = [b["close"] for b in bars]
        fast, slow = sma(closes, 5), sma(closes, 20)
        if fast is None or slow is None:
            return "HOLD", "chua du du lieu"
        if fast > slow:
            return "BUY", f"SMA5 ({fast:.2f}) > SMA20 ({slow:.2f})"
        if fast < slow:
            return "SELL", f"SMA5 ({fast:.2f}) < SMA20 ({slow:.2f})"
        return "HOLD", "SMA5 == SMA20"
