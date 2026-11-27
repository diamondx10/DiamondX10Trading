"""Nhan dien mau hinh gia (PTKT) tu nen OHLC.

Chi la BOI CANH — ket qua chi duoc ghi nhan va hien thi, KHONG dung
de chan hay doi tin hieu (giong regime trong signals.py).
Phat hien don gian, xac dinh (deterministic), khong can MT5 that.

Moi mau hinh tra ve: {name, direction, strength, bar_index, time,
detail} — direction "bullish" / "bearish" / "neutral", strength 0..1.
Chuoi hien thi dung tieng Viet KHONG dau.
"""

PIVOT_N = 5          # so bar moi ben de xac dinh dinh/day xoay chieu
DOUBLE_TOL = 0.01    # sai lech gia toi da giua 2 dinh/day (1%)
DOUBLE_MIN_GAP = 5   # khoang cach toi thieu giua 2 dinh/day (bar)
BREAKOUT_LOOKBACK = 10  # so bar truoc de lay dinh/day gan nhat


def _body(bar):
    return bar["close"] - bar["open"]


def _range(bar):
    return bar["high"] - bar["low"]


def _upper_shadow(bar):
    return bar["high"] - max(bar["open"], bar["close"])


def _lower_shadow(bar):
    return min(bar["open"], bar["close"]) - bar["low"]


def _time(bar):
    return bar.get("time")


def _make(name, direction, strength, index, bars, detail):
    return {"name": name, "direction": direction,
            "strength": round(max(0.0, min(1.0, float(strength))), 2),
            "bar_index": int(index),
            "time": _time(bars[index]) if 0 <= index < len(bars) else None,
            "detail": detail}


def _single_bar_patterns(bars, out):
    """Nen don: engulfing, hammer, shooting star, doji."""
    for i, bar in enumerate(bars):
        rng = _range(bar)
        if rng <= 0:
            continue
        body = _body(bar)
        abs_body = abs(body)
        # --- Doji: than nen rat nho so voi bien do ---
        if abs_body <= 0.10 * rng:
            out.append(_make("doji", "neutral", 0.5, i, bars,
                             "doji: gia mo va gia dong gan bang nhau"))
            continue
        # --- Engulfing (can nen truoc) ---
        if i > 0:
            prev = bars[i - 1]
            prev_body = _body(prev)
            prev_range = _range(prev)
            if (abs(prev_body) >= 0.15 * prev_range and prev_range > 0
                    and abs_body > abs(prev_body)):
                ratio = abs_body / abs(prev_body) if prev_body else 1.0
                strength = min(0.95, 0.6 + 0.1 * min(ratio, 3.0))
                if body > 0 and prev_body < 0 and bar["open"] <= prev["close"] \
                        and bar["close"] >= prev["open"]:
                    out.append(_make(
                        "bullish_engulfing", "bullish", strength, i, bars,
                        "nen tang bao phu nen giam truoc"))
                elif body < 0 and prev_body > 0 \
                        and bar["open"] >= prev["close"] \
                        and bar["close"] <= prev["open"]:
                    out.append(_make(
                        "bearish_engulfing", "bearish", strength, i, bars,
                        "nen giam bao phu nen tang truoc"))
        # --- Hammer / shooting star: than nho, 1 bong dai ---
        if abs_body <= 0.35 * rng:
            lower = _lower_shadow(bar)
            upper = _upper_shadow(bar)
            if lower >= 2 * abs_body and upper <= 0.5 * abs_body:
                out.append(_make("hammer", "bullish", 0.65, i, bars,
                                 "bua (hammer): bong duoi dai, than nho o tren"))
            elif upper >= 2 * abs_body and lower <= 0.5 * abs_body:
                out.append(_make("shooting_star", "bearish", 0.65, i, bars,
                                 "sao bang (shooting star): bong tren dai, "
                                 "than nho o duoi"))


def _three_bar_patterns(bars, out):
    """Morning star / evening star (3 nen)."""
    for i in range(2, len(bars)):
        b0, b1, b2 = bars[i - 2], bars[i - 1], bars[i]
        body0, body1, body2 = _body(b0), _body(b1), _body(b2)
        if abs(body1) > 0.5 * abs(body0):
            continue
        mid0 = (b0["open"] + b0["close"]) / 2
        if body0 < 0 and body2 > 0 and b2["close"] > mid0:
            out.append(_make("morning_star", "bullish", 0.8, i, bars,
                             "sao mai (morning star): dao chieu tang sau "
                             "3 nen"))
        elif body0 > 0 and body2 < 0 and b2["close"] < mid0:
            out.append(_make("evening_star", "bearish", 0.8, i, bars,
                             "sao hom (evening star): dao chieu giam sau "
                             "3 nen"))


def _swing_pivots(bars):
    """Dinh/day xoay chieu: high (low) cao (thap) nhat trong cua so
    PIVOT_N bar moi ben, va cao (thap) hon 2 bar ke ben (tranh nen
    bang nhau). Tra (high_pivots, low_pivots): list (index, price)."""
    highs, lows = [], []
    n = len(bars)
    for i in range(PIVOT_N, n - PIVOT_N):
        hi = bars[i]["high"]
        lo = bars[i]["low"]
        window_h = [b["high"] for b in bars[i - PIVOT_N:i + PIVOT_N + 1]]
        window_l = [b["low"] for b in bars[i - PIVOT_N:i + PIVOT_N + 1]]
        if hi == max(window_h) and hi > bars[i - 1]["high"] \
                and hi > bars[i + 1]["high"]:
            highs.append((i, hi))
        if lo == min(window_l) and lo < bars[i - 1]["low"] \
                and lo < bars[i + 1]["low"]:
            lows.append((i, lo))
    return highs, lows


def _pivot_patterns(bars, out, highs, lows):
    """Ho tro / khang cu tu dinh/day xoay chieu + double top/bottom."""
    for i, price in highs:
        out.append(_make("resistance", "neutral", 0.6, i, bars,
                         "khang cu %.2f" % price))
    for i, price in lows:
        out.append(_make("support", "neutral", 0.6, i, bars,
                         "ho tro %.2f" % price))
    for (i1, p1), (i2, p2) in zip(highs, highs[1:]):
        if i2 - i1 < DOUBLE_MIN_GAP:
            continue
        if abs(p1 - p2) / p1 <= DOUBLE_TOL:
            strength = 0.8 if abs(p1 - p2) / p1 <= 0.005 else 0.65
            out.append(_make("double_top", "bearish", strength, i2, bars,
                             "dinh doi tai %.2f" % p2))
    for (i1, p1), (i2, p2) in zip(lows, lows[1:]):
        if i2 - i1 < DOUBLE_MIN_GAP:
            continue
        if abs(p1 - p2) / p1 <= DOUBLE_TOL:
            strength = 0.8 if abs(p1 - p2) / p1 <= 0.005 else 0.65
            out.append(_make("double_bottom", "bullish", strength, i2, bars,
                             "day doi tai %.2f" % p2))


def _breakout_patterns(bars, out):
    """Pha vo dinh cao (day thap) cua BREAKOUT_LOOKBACK bar truoc.
    Chi ghi nhan bar dau tien cua moi dot pha vo."""
    for i in range(BREAKOUT_LOOKBACK, len(bars)):
        prev_high = max(b["high"] for b in bars[i - BREAKOUT_LOOKBACK:i])
        prev_low = min(b["low"] for b in bars[i - BREAKOUT_LOOKBACK:i])
        if bars[i]["close"] > prev_high:
            if i == BREAKOUT_LOOKBACK or bars[i - 1]["close"] <= max(
                    b["high"] for b in bars[i - BREAKOUT_LOOKBACK - 1:i - 1]):
                out.append(_make("breakout_up", "bullish", 0.85, i, bars,
                                 "pha vo dinh gan nhat %.2f" % prev_high))
        elif bars[i]["close"] < prev_low:
            if i == BREAKOUT_LOOKBACK or bars[i - 1]["close"] >= min(
                    b["low"] for b in bars[i - BREAKOUT_LOOKBACK - 1:i - 1]):
                out.append(_make("breakout_down", "bearish", 0.85, i, bars,
                                 "pha vo day gan nhat %.2f" % prev_low))


def detect_patterns(bars):
    """Nhan dien mau hinh gia tu list bar OHLC.

    Bar: dict co open/high/low/close, time tuy chon. It hon 6 bar
    thi tra [] (chua du du lieu). Ket qua sap xep theo bar_index.
    """
    if bars is None or len(bars) < 6:
        return []
    out = []
    _single_bar_patterns(bars, out)
    _three_bar_patterns(bars, out)
    highs, lows = _swing_pivots(bars)
    _pivot_patterns(bars, out, highs, lows)
    _breakout_patterns(bars, out)
    out.sort(key=lambda p: (p["bar_index"], p["name"]))
    return out


def pattern_summary(patterns):
    """Tom tat ngan (tieng Viet khong dau) + diem rong (-1..1).

    Diem = trung binh co trong so (theo strength) cua cac mau hinh
    co huong: tang duong, giam am; mau hinh trung lap (ho tro /
    khang cu, doji) khong tinh vao diem. Khong co mau hinh -> 0.0.
    """
    if not patterns:
        return "khong co mau hinh", 0.0
    bull = sum(p["strength"] for p in patterns
               if p["direction"] == "bullish")
    bear = sum(p["strength"] for p in patterns
               if p["direction"] == "bearish")
    n_bull = sum(1 for p in patterns if p["direction"] == "bullish")
    n_bear = sum(1 for p in patterns if p["direction"] == "bearish")
    n_sup = sum(1 for p in patterns if p["name"] == "support")
    n_res = sum(1 for p in patterns if p["name"] == "resistance")
    if bull + bear > 0:
        net = (bull - bear) / (bull + bear)
    else:
        net = 0.0
    net = round(max(-1.0, min(1.0, net)), 4)
    parts = []
    if n_bull:
        parts.append("%d mau hinh tang" % n_bull)
    if n_bear:
        parts.append("%d mau hinh giam" % n_bear)
    if n_sup:
        parts.append("%d muc ho tro" % n_sup)
    if n_res:
        parts.append("%d muc khang cu" % n_res)
    if not parts:
        parts.append("%d mau hinh trung lap" % len(patterns))
    return ", ".join(parts), net
