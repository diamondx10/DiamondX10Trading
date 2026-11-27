"""Lop co so cho moi chien luoc (Phase 2 — quy tac da chot o
docs/phase0-desk-rules.md, dung chung cho ca 4 desk).

Tin hieu: giao cat SMA5/SMA20 + loc RSI(14), stop/take-profit theo ATR(14):
- BUY neu SMA5 > SMA20 va 50 < RSI(14) < 70.
- SELL neu SMA5 < SMA20 va 30 < RSI(14) < 50.
- RSI(14) > 80 hoac < 20 (cuc doan) -> khong mo lenh moi (HOLD).
- Chua du du lieu cho SMA20/RSI/ATR -> HOLD.

signal(bars) tra ve 3-tuple (action, reason, levels); levels la None khi
HOLD, con BUY/SELL thi la {"entry", "sl", "tp", "atr"} voi entry la
gia dong cua cua nen cuoi cung.
"""
from ..models.quant import atr, rsi, sma

# Gia tri mac dinh cung (fallback) khi khong co config nao truyen vao.
# Thu tu uu tien khi khoi tao (desk thang shared, shared thang cung):
#   SHARED_DEFAULTS < params (tham so chung) < DESK_OVERRIDES cua lop con
#   < desk_params (ghi de rieng desk trong config).
SHARED_DEFAULTS = {
    "sma_fast": 5,
    "sma_slow": 20,
    "rsi_period": 14,
    "rsi_buy_low": 50,
    "rsi_buy_high": 70,
    "rsi_sell_low": 30,
    "rsi_sell_high": 50,
    "rsi_extreme_high": 80,
    "rsi_extreme_low": 20,
    "atr_period": 14,
    "atr_sl_mult": 1.5,
    "tp_mult": 2.0,
    "trail_mult": 1.5,
}


class Strategy:
    name = "base"
    desk = ""
    # Ghi de theo desk o lop con, vd crypto: atr_sl_mult 2.0, trail_mult 2.0.
    DESK_OVERRIDES = {}

    def __init__(self, params=None, desk_params=None):
        merged = dict(SHARED_DEFAULTS)
        merged.update(params or {})
        merged.update(self.DESK_OVERRIDES or {})
        merged.update(desk_params or {})
        self.params = merged

    def _p(self, key):
        return self.params[key]

    def signal(self, bars):
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        sma_fast_p = self._p("sma_fast")
        sma_slow_p = self._p("sma_slow")
        rsi_p = self._p("rsi_period")
        atr_p = self._p("atr_period")
        need = max(sma_slow_p, rsi_p + 1, atr_p + 1)
        if len(closes) < need:
            return ("HOLD",
                    f"chua du du lieu: can {need} nen, chi co {len(closes)}",
                    None)
        fast = sma(closes, sma_fast_p)
        slow = sma(closes, sma_slow_p)
        rsi_val = rsi(closes, rsi_p)
        atr_val = atr(highs, lows, closes, atr_p)
        if fast is None or slow is None or rsi_val is None or atr_val is None:
            return ("HOLD",
                    "chua du du lieu: chua tinh duoc SMA/RSI/ATR",
                    None)
        if rsi_val > self._p("rsi_extreme_high") or rsi_val < self._p("rsi_extreme_low"):
            return ("HOLD",
                    f"RSI cuc doan ({rsi_val:.1f}) — khong mo lenh moi",
                    None)
        entry = closes[-1]
        if fast > slow:
            if rsi_val <= self._p("rsi_buy_low"):
                return ("HOLD",
                        f"SMA{sma_fast_p} ({fast:.2f}) > SMA{sma_slow_p} ({slow:.2f}) "
                        f"nhung RSI ({rsi_val:.1f}) <= {self._p('rsi_buy_low')} "
                        f"— mat dong luong tang, khong BUY",
                        None)
            if rsi_val >= self._p("rsi_buy_high"):
                return ("HOLD",
                        f"SMA{sma_fast_p} ({fast:.2f}) > SMA{sma_slow_p} ({slow:.2f}) "
                        f"nhung RSI ({rsi_val:.1f}) >= {self._p('rsi_buy_high')} "
                        f"— qua mua, khong BUY",
                        None)
            reason = (f"SMA{sma_fast_p} ({fast:.2f}) > SMA{sma_slow_p} ({slow:.2f}), "
                      f"RSI ({rsi_val:.1f}) trong {self._p('rsi_buy_low')}-"
                      f"{self._p('rsi_buy_high')}")
            return "BUY", reason, self.levels_for_entry("BUY", entry, atr_val)
        if fast < slow:
            if rsi_val >= self._p("rsi_sell_high"):
                return ("HOLD",
                        f"SMA{sma_fast_p} ({fast:.2f}) < SMA{sma_slow_p} ({slow:.2f}) "
                        f"nhung RSI ({rsi_val:.1f}) >= {self._p('rsi_sell_high')} "
                        f"— mat dong luong giam, khong SELL",
                        None)
            if rsi_val <= self._p("rsi_sell_low"):
                return ("HOLD",
                        f"SMA{sma_fast_p} ({fast:.2f}) < SMA{sma_slow_p} ({slow:.2f}) "
                        f"nhung RSI ({rsi_val:.1f}) <= {self._p('rsi_sell_low')} "
                        f"— qua ban, khong SELL",
                        None)
            reason = (f"SMA{sma_fast_p} ({fast:.2f}) < SMA{sma_slow_p} ({slow:.2f}), "
                      f"RSI ({rsi_val:.1f}) trong {self._p('rsi_sell_low')}-"
                      f"{self._p('rsi_sell_high')}")
            return "SELL", reason, self.levels_for_entry("SELL", entry, atr_val)
        return "HOLD", f"SMA{sma_fast_p} == SMA{sma_slow_p}", None

    def levels_for_entry(self, action, entry, atr_value):
        """Tinh SL/TP theo ATR tu mot gia vao bat ky (vd gia live luc dat
        lenh). BUY: SL duoi gia, TP tren gia; SELL: nguoc lai.
        SL cach entry atr_sl_mult x ATR; TP cach entry tp_mult x
        khoang cach SL (ti le 2:1). Tra None neu khong tinh duoc."""
        if action not in ("BUY", "SELL"):
            return None
        if atr_value is None or atr_value <= 0:
            return None
        sl_dist = self._p("atr_sl_mult") * atr_value
        if action == "BUY":
            sl = entry - sl_dist
            tp = entry + self._p("tp_mult") * sl_dist
        else:
            sl = entry + sl_dist
            tp = entry - self._p("tp_mult") * sl_dist
        return {"entry": float(entry), "sl": float(sl),
                "tp": float(tp), "atr": float(atr_value)}

    def trailing_stop(self, entry, sl, direction, price, atr_value):
        """Dời SL theo gia (pure — khong giu trang thai).
        Khi gia chay co loi duoc 1 x khoang cach SL goc thi dời SL ve
        gia hoa von (entry); sau do trailing SL cach gia hien tai
        trail_mult x ATR. Khong bao gio dời SL nguoc lai chong lai
        vi the. Tra SL moi (bang SL cu neu chua du dieu kien doi)."""
        if direction not in ("BUY", "SELL"):
            return sl
        if atr_value is None or atr_value <= 0:
            return sl
        sl_dist = abs(entry - sl)
        if sl_dist <= 0:
            return sl
        if direction == "BUY":
            if price - entry < sl_dist:
                return sl
            candidate = max(entry, price - self._p("trail_mult") * atr_value)
            return max(sl, candidate)
        if entry - price < sl_dist:
            return sl
        candidate = min(entry, price + self._p("trail_mult") * atr_value)
        return min(sl, candidate)

    def reversal_exit(self, open_direction, bars):
        """True neu nen hien tai cho tin hieu day du nguoc huong vi the
        dang mo (SMA cat nguoc + RSI xac nhan) -> dong lenh o gia thi
        truong. Vi du: dang BUY ma signal() ra SELL thi dong BUY.
        HOLD hoac cung huong thi False."""
        if open_direction not in ("BUY", "SELL"):
            return False
        action, _reason, _levels = self.signal(bars)
        opposite = "SELL" if open_direction == "BUY" else "BUY"
        return action == opposite
