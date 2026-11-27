"""Chi bao dinh luong co ban: SMA, RSI, ATR, volatility.
Ly thuyet do Yuling nghien cuu, cai dat do LJ/Kel thuc hien."""


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    return sum(trs[-period:]) / period


def volatility(values, period=20):
    if len(values) < period:
        return None
    mean = sum(values[-period:]) / period
    var = sum((v - mean) ** 2 for v in values[-period:]) / period
    return var ** 0.5


def _true_ranges(highs, lows, closes):
    """True Range theo tung bar (bar 0 khong co gia dong cua truoc nen
    bo qua): TR[i] = max(high-low, |high - close truoc|,
    |low - close truoc|), i >= 1. Tra list dai len(closes) - 1."""
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    return trs


def atr_series(highs, lows, closes, period=14):
    """Chuoi ATR theo tung bar: ATR[i] = trung binh `period` True Range
    ket thuc o bar i (i >= period); None cho i < period. Gia tri cuoi
    bang atr(highs, lows, closes, period)."""
    trs = _true_ranges(highs, lows, closes)
    out = []
    for i in range(len(closes)):
        if i < period:
            out.append(None)
        else:
            # TR cua bar i nam o trs[i - 1]; cua so period TR ket thuc o i
            # la trs[i - period .. i - 1].
            window = trs[i - period:i]
            out.append(sum(window) / period)
    return out


def _ewm(values, period):
    """Trung binh luy thua kieu pandas ewm(alpha=1/period, adjust=True):
    y[t] = (x[t] + (1-a)*num[t-1]) / (1 + (1-a)*den[t-1]).
    Dung de lam min +DM/-DM va DX theo dung cach repo DiamondX10 (cu)
    tinh ADX (regime_detector.py). Tra list cung do dai, None cho
    gia tri dau vao None."""
    alpha = 1.0 / period
    decay = 1.0 - alpha
    out = []
    num = den = None
    for v in values:
        if v is None:
            out.append(None)
            continue
        if num is None:
            num, den = float(v), 1.0
        else:
            num = float(v) + decay * num
            den = 1.0 + decay * den
        out.append(num / den)
    return out


def adx(highs, lows, closes, period=14):
    """Average Directional Index (ADX) theo Wilder, nhu repo DiamondX10
    (cu) dung trong regime_detector.py: +DM/-DM lam min EWMA, DI =
    100 * DM lam min / ATR, DX = 100 * |+DI - -DI| / (+DI + -DI),
    ADX = EWMA cua DX. Tra None neu chua du du lieu (can it nhat
    period + 1 bar)."""
    n = len(closes)
    if n < period + 1:
        return None
    atrs = atr_series(highs, lows, closes, period)
    plus_dm = [None] * n
    minus_dm = [None] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
    plus_sm = _ewm(plus_dm, period)
    minus_sm = _ewm(minus_dm, period)
    dx = [None] * n
    for i in range(n):
        if atrs[i] is None or atrs[i] <= 0:
            dx[i] = 0.0
            continue
        pdi = 100 * (plus_sm[i] or 0.0) / atrs[i]
        mdi = 100 * (minus_sm[i] or 0.0) / atrs[i]
        denom = pdi + mdi
        dx[i] = 100 * abs(pdi - mdi) / denom if denom > 0 else 0.0
    adx_series = _ewm(dx, period)
    value = adx_series[-1]
    return None if value is None else float(value)


def atr_percentile(highs, lows, closes, period=14, lookback=100):
    """Phan vi cua ATR hien tai trong `lookback` gia tri ATR gan nhat
    (0-100). Tra 50.0 neu chua du lich su hoac ATR hien tai = 0 — giong
    repo DiamondX10 (cu)."""
    series = [v for v in atr_series(highs, lows, closes, period)
              if v is not None]
    if len(series) < lookback or not series or series[-1] <= 0:
        return 50.0
    window = series[-lookback:]
    current = series[-1]
    return sum(1 for v in window if v <= current) / len(window) * 100


# Nguong regime theo repo DiamondX10 (cu), regime_detector.py:
# ADX >= 40: xu huong manh; >= 25: xu huong; >= 15 (0,6 x 25):
# chuyen tiep; con lai: dao dong (ranging).
ADX_STRONG = 40.0
ADX_TREND = 25.0
ADX_TRANSITIONAL = 15.0
ATR_PCT_HIGH = 80.0
ATR_PCT_LOW = 20.0


def classify_regime(adx_value):
    """Phan loai regime chi tu ADX: 'TRENDING' / 'TRANSITIONAL' /
    'RANGING'. Nguong theo repo DiamondX10 (cu)."""
    if adx_value is None:
        return "UNKNOWN"
    if adx_value >= ADX_TREND:
        return "TRENDING"
    if adx_value >= ADX_TRANSITIONAL:
        return "TRANSITIONAL"
    return "RANGING"


def detect_regime(bars, adx_period=14, atr_period=14, atr_lookback=100):
    """Nhan dien regime thi truong tu bars OHLC (dict, giong
    RegimeDetector.detect() cua repo DiamondX10 cu).

    Tra dict {regime, direction, adx, atr_percentile, volatility,
    confidence}:
    - regime: TRENDING / TRANSITIONAL / RANGING / UNKNOWN (chua du du lieu).
    - direction: BULLISH / BEARISH / NEUTRAL theo SMA20 so voi SMA50.
    - volatility: HIGH / NORMAL / LOW theo phan vi ATR (80/20).
    - confidence: 0,1-0,95 theo cong thuc goc.
    Chi la THONG TIN BOI CANH — khong dung de chan tin hieu (xem
    docs/trading-principles.md, quy tac 21)."""
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    need = max(adx_period, atr_period) + 1
    if len(closes) < need:
        return {"regime": "UNKNOWN", "direction": "NEUTRAL", "adx": 0.0,
                "atr_percentile": 50.0, "volatility": "NORMAL",
                "confidence": 0.0}
    adx_val = adx(highs, lows, closes, adx_period) or 0.0
    atr_pct = atr_percentile(highs, lows, closes, atr_period, atr_lookback)
    sma_short = sma(closes, 20)
    sma_long = sma(closes, 50)
    direction = "NEUTRAL"
    if sma_short is not None and sma_long is not None:
        if sma_short > sma_long:
            direction = "BULLISH"
        elif sma_short < sma_long:
            direction = "BEARISH"
    if atr_pct >= ATR_PCT_HIGH:
        vol = "HIGH"
    elif atr_pct <= ATR_PCT_LOW:
        vol = "LOW"
    else:
        vol = "NORMAL"
    if adx_val >= ADX_STRONG:
        regime = "TRENDING"
        confidence = min(0.9, 0.5 + (adx_val - ADX_STRONG) / 40)
    elif adx_val >= ADX_TREND:
        regime = "TRENDING"
        confidence = 0.5 + (adx_val - ADX_TREND) / (ADX_STRONG - ADX_TREND) * 0.4
    elif adx_val >= ADX_TRANSITIONAL:
        regime = "TRANSITIONAL"
        confidence = 0.3 + (adx_val / ADX_TREND) * 0.2
    else:
        regime = "RANGING"
        confidence = 0.5 - (adx_val / ADX_TREND) * 0.3
    return {"regime": regime, "direction": direction,
            "adx": round(adx_val, 2), "atr_percentile": round(atr_pct, 1),
            "volatility": vol,
            "confidence": round(max(0.1, min(0.95, confidence)), 2)}
