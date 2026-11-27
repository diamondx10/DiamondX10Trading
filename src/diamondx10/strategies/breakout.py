"""Chien luoc breakout kenh Donchian — CHI DUNG CHO BACKTEST SO SANH,
chua dung cho duong live.

Nguon: repo DiamondX10 (cu), src/analysis/strategies/breakout.py
(Donchian Channel 20 + loc ATR). Dieu chinh cho phu hop tool nay:
- Khong co xac nhan khoi luong (bar cua tool khong co volume) va
  khong co xac nhan retest (ban goc tat mac dinh, retest=False).
- Diem vao: gia dong cua pha tren dinh Donchian 20 nen truoc thi BUY,
  pha duoi day Donchian 20 nen truoc thi SELL. Dinh/day tinh tren
  `donchian_period` nen TRUOC nen hien tai (giong ban goc dung
  don_high.iloc[-2]).
- Loc bien dong cua ban goc (ATR/gia < 0,003 thi giam diem con 0,5)
  chuyen thanh HOLD o day: bien dong qua thap thi khong mo lenh moi
  (khop muc theo doi "khong giao dich khi bien dong qua thap" trong
  docs/trading-principles.md, quy tac 6).
- SL/TP theo ATR, trailing stop, thoat khi dao chieu: dung lai ham
  cua lop co so (strategies/base.py) nhu chien luoc chung da chot.

Su dung live can Phu duyet + bang chung backtest (walk-forward):
hien chi chay qua `backtest --strategy donchian` hoac
`run_backtest(..., strategy_name="donchian")`.
"""
from ..models.quant import atr
from .base import Strategy


class DonchianBreakout(Strategy):
    name = "DonchianBreakout (so sanh backtest — chua dung live)"
    desk = ""
    DESK_OVERRIDES = {}

    def __init__(self, params=None, desk_params=None):
        super().__init__(params=params, desk_params=desk_params)
        self.params.setdefault("donchian_period", 20)
        # ATR toi thieu so voi gia (0,3%): duoi muc nay thi HOLD.
        self.params.setdefault("min_atr_pct", 0.003)

    def signal(self, bars):
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        period = int(self._p("donchian_period"))
        atr_p = self._p("atr_period")
        need = max(period + 1, atr_p + 1)
        if len(closes) < need:
            return ("HOLD",
                    f"chua du du lieu: can {need} nen, chi co {len(closes)}",
                    None)
        don_high = max(highs[-(period + 1):-1])
        don_low = min(lows[-(period + 1):-1])
        atr_val = atr(highs, lows, closes, atr_p)
        if atr_val is None:
            return ("HOLD",
                    "chua du du lieu: chua tinh duoc ATR",
                    None)
        entry = closes[-1]
        if entry > 0 and atr_val / entry < self._p("min_atr_pct"):
            return ("HOLD",
                    f"ATR/gia ({atr_val / entry:.4f}) < "
                    f"{self._p('min_atr_pct')} — bien dong qua thap, "
                    "khong mo lenh breakout",
                    None)
        if entry >= don_high:
            reason = (f"gia dong cua ({entry:.4f}) pha tren dinh Donchian "
                      f"{period} ({don_high:.4f})")
            return "BUY", reason, self.levels_for_entry("BUY", entry, atr_val)
        if entry <= don_low:
            reason = (f"gia dong cua ({entry:.4f}) pha duoi day Donchian "
                      f"{period} ({don_low:.4f})")
            return "SELL", reason, self.levels_for_entry("SELL", entry, atr_val)
        return ("HOLD",
                f"gia ({entry:.4f}) trong kenh Donchian {period} "
                f"[{don_low:.4f}, {don_high:.4f}]",
                None)
