"""Lop co so cho moi chien luoc (Phase 2 — quy tac da chot o
docs/phase0-desk-rules.md, dung chung cho ca 4 desk).

Tin hieu: giao cat SMA5/SMA20 + loc RSI(14), stop/take-profit theo ATR(14):
- BUY neu SMA5 > SMA20 va 50 < RSI(14) < 70.
- SELL neu SMA5 < SMA20 va 30 < RSI(14) < 50.
- RSI(14) > 80 hoac < 20 (cuc doan) -> khong mo lenh moi (HOLD).
- Chua du du lieu cho SMA20/RSI/ATR -> HOLD.

signal(bars) tra ve 3-tuple (action, reason, levels); levels la None khi
HOLD, con BUY/SELL thi la {"entry", "sl", "tp", "atr"} voi entry la
gia dong cua cua nen cuoi cung — them "size_scale" (<= 1.0) khi co
soft rule scale tac dong (xem strategies/soft_rules.py).

Gate cung theo tham so (ap truoc khi tra BUY/SELL, cho ca 4 desk):
- adx_min > 0: ADX(14) < adx_min -> HOLD (khong du xu huong).
- min_atr_pct > 0: ATR(14)/gia < min_atr_pct -> HOLD (bien dong qua thap).
Mac dinh adx_min = 0 (tat) va khong co min_atr_pct (tat) nen hanh vi
cu giu nguyen; gia tri rieng theo symbol nam o strategy.per_symbol.
"""
from ..models.quant import adx, atr, rsi, sma
from .soft_rules import apply_soft_rules, evaluate_condition  # noqa: F401
from .soft_rules import validate_soft_rules

# Gia tri mac dinh cung (fallback) khi khong co config nao truyen vao.
# Thu tu uu tien khi khoi tao (desk thang shared, shared thang cung):
#   SHARED_DEFAULTS < params (tham so chung) < DESK_OVERRIDES cua lop con
#   < desk_params (ghi de rieng desk trong config).
# adx_min = 0 nghia la gate ADX TAT (hanh vi cu). min_atr_pct KHONG co
# trong SHARED_DEFAULTS mot cach co y: DonchianBreakout setdefault
# 0.003 cua no chi chay khi khoa nay vang mat; neu de 0.0 vao day thi
# setdefault do chet va Donchian mat loc bien dong thap.
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
    "adx_min": 0,
}


class Strategy:
    name = "base"
    desk = ""
    # Ghi de theo desk o lop con, vd crypto: atr_sl_mult 2.0, trail_mult 2.0.
    DESK_OVERRIDES = {}

    def __init__(self, params=None, desk_params=None, soft_rules=None):
        merged = dict(SHARED_DEFAULTS)
        merged.update(params or {})
        merged.update(self.DESK_OVERRIDES or {})
        merged.update(desk_params or {})
        self.params = merged
        # Quy tac mem da loc theo scope (build_strategy_for_symbol /
        # build_strategies truyen vao); khoi tao truc tiep thi validate
        # o day de rule go sai khong bao gio lang le khong lam gi.
        self.soft_rules = validate_soft_rules(soft_rules)
        # Context chi bao (RSI/SMA/ADX/ATR%) cua lan signal() gan nhat —
        # generate_signals/outcomes doc tu day, khong tinh lai. None
        # khi signal() chua chay hoac dung som truoc khi co context.
        self.last_context = None

    def _p(self, key):
        return self.params[key]

    def _soft_context(self, bars, atr_val=None, entry=None):
        """Context chi bao cho soft rule + gate ADX/ATR%: dict {rsi,
        sma_fast, sma_slow, adx, atr_pct, patterns}.

        patterns chi tinh khi co rule can condition pattern (lazy,
        tranh ton chi phi detect_patterns moi bar trong backtest).
        adx tinh theo chu ky 14 (chuan Wilder); gia tri None = chua
        du du lieu -> condition ve chi bao do = False.
        """
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        if atr_val is None:
            atr_val = atr(highs, lows, closes, self._p("atr_period"))
        if entry is None:
            entry = closes[-1] if closes else None
        ctx = {
            "rsi": rsi(closes, self._p("rsi_period")),
            "sma_fast": sma(closes, self._p("sma_fast")),
            "sma_slow": sma(closes, self._p("sma_slow")),
            "adx": adx(highs, lows, closes, 14),
            "atr_pct": (atr_val / entry
                        if atr_val is not None and entry else None),
            "patterns": None,
        }
        if any(r["condition"]["type"] == "pattern"
               for r in self.soft_rules):
            from ..patterns import detect_patterns
            ctx["patterns"] = detect_patterns(bars)
        # Luu lai cho generate_signals/outcomes: dung chinh cac gia tri
        # cua lan tinh nay (kem ATR tuyet doi), khong dung gia tri cu.
        self.last_context = dict(ctx)
        self.last_context["atr"] = atr_val
        return ctx

    def _param_gate_hold(self, ctx):
        """Gate cung theo tham so adx_min / min_atr_pct.

        Tra ly do HOLD (str) neu bi chan, None neu vuot qua. ADX
        khong tinh duoc (None, chua du du lieu) thi cho qua — gate
        khong duoc doan mo tren du lieu thieu.
        """
        adx_min = self.params.get("adx_min", 0) or 0
        if adx_min > 0 and ctx.get("adx") is not None \
                and ctx["adx"] < adx_min:
            return (f"ADX(14) ({ctx['adx']:.1f}) < adx_min {adx_min} — "
                    "khong du xu huong, khong mo lenh moi")
        min_atr_pct = self.params.get("min_atr_pct", 0) or 0
        if min_atr_pct > 0 and ctx.get("atr_pct") is not None \
                and ctx["atr_pct"] < min_atr_pct:
            return (f"ATR/gia ({ctx['atr_pct']:.4f}) < min_atr_pct "
                    f"{min_atr_pct} — bien dong qua thap, khong mo lenh moi")
        return None

    def _apply_soft_rules(self, action, reason, levels, ctx):
        """Diem danh gia soft rule DUY NHAT trong duong signal.

        Tra (action, reason, levels): block/require bien BUY/SELL
        thanh HOLD (ly do neu ten rule); scale thi gan
        levels["size_scale"] (<= 1.0) va ghi ten rule vao reason.
        HOLD truyen vao thi tra nguyen.
        """
        if action not in ("BUY", "SELL"):
            return action, reason, levels
        new_action, size_scale, applied, block_reason = apply_soft_rules(
            self.soft_rules, action, ctx)
        if block_reason is not None:
            return "HOLD", f"{reason} [{block_reason}]", None
        if size_scale < 1.0:
            levels = dict(levels or {})
            levels["size_scale"] = round(size_scale, 4)
            reason = (f"{reason} [soft rule {', '.join(applied)}: "
                      f"scale x{size_scale:.2f}]")
        return new_action, reason, levels

    def signal(self, bars):
        # Reset truoc: HOLD dung som (chua du du lieu / RSI cuc doan)
        # khong duoc mang context cua lan tinh truoc.
        self.last_context = None
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
        ctx = self._soft_context(bars, atr_val, entry)
        gate_reason = self._param_gate_hold(ctx)
        if gate_reason is not None:
            return "HOLD", gate_reason, None
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
            return self._apply_soft_rules(
                "BUY", reason,
                self.levels_for_entry("BUY", entry, atr_val), ctx)
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
            return self._apply_soft_rules(
                "SELL", reason,
                self.levels_for_entry("SELL", entry, atr_val), ctx)
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
