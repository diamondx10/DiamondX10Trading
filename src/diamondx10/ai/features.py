"""Feature vectors cho mo hinh TA offline cua dx10 (MODEL-AGNOSTIC).

Mo hinh nao (MLP, LSTM, gradient boosting, ...) cung an duoc: dau ra
chi la list[float] thuan (stdlib, KHONG phu thuoc torch / numpy /
pandas — requirements.txt cua dx10 khong co numpy/pandas), thu tu cot
co dinh boi FEATURE_NAMES, phien ban boi FEATURE_VERSION. Mo hinh da
luu phai kiem tra FEATURE_VERSION + FEATURE_NAMES khop luc load
(xem assert_feature_version) truoc khi dung.

DANH SACH FEATURE (FEATURE_VERSION = 1, 35 cot, thu tu co dinh):
  Returns / bien dong (chi tu gia dong cua va OHLC):
    0  log_ret_1    log(close[t] / close[t-1])
    1  log_ret_3    log(close[t] / close[t-3])
    2  log_ret_5    log(close[t] / close[t-5])
    3  log_ret_10   log(close[t] / close[t-10])
    4  log_ret_20   log(close[t] / close[t-20])
    5  hl_range_t   (high[t] - low[t]) / close[t]
    6  co_move_t    (close[t] - open[t]) / close[t]
    7  vol_5        do lech chuan cua log return 1 bar, 5 bar gan nhat
    8  vol_10       nhu tren, 10 bar
    9  vol_20       nhu tren, 20 bar
    10 volume_rel   volume[t] / trung binh volume 20 bar gan nhat
                    (1.0 neu khong co thong tin volume)
  Chi bao dx10 da co (models/quant.py, tinh theo tham so da resolve
  cua symbol — build_features nhan `params`):
    11 sma_fast_rel  (SMA_fast - close[t]) / close[t]
    12 sma_slow_rel  (SMA_slow - close[t]) / close[t]
    13 sma_cross     +1 neu SMA_fast > SMA_slow, -1 neu <, 0 neu =
    14 rsi_scaled    RSI(period) / 100  (0..1)
    15 atr_pct       ATR(period) / close[t]
    16 adx_scaled    ADX(14) / 100  (0..1)
    17 regime_trending      1 neu classify_regime(ADX) == TRENDING
    18 regime_transitional  1 neu == TRANSITIONAL
    19 regime_ranging       1 neu == RANGING
                    (UNKNOWN -> ca 3 bang 0)
  Mau hinh (patterns.py, chi mau hinh KET THUC o bar t):
    20 pattern_score  diem rong (-1..1) cua cac mau hinh ket thuc o t
    21-33 pat_<ten>   0/1 cho tung loai: bullish_engulfing,
                    bearish_engulfing, hammer, shooting_star, doji,
                    morning_star, evening_star, support, resistance,
                    double_top, double_bottom, breakout_up, breakout_down
  Huong lenh (do dataset.py gan, khong co trong bar):
    34 direction_long  +1.0 BUY / -1.0 SELL / 0.0 chua xac dinh.
                    Hai mau cung bar t khac nhau chi o cot nay co the
                    co nhan khac nhau — dung nhu thiet ke: mo hinh
                    hoc P(ket qua | feature, huong).

KHONG LOOKAHEAD (bao dam): build_features chi doc cac bar duoc truyen
vao — tuc la cua so ket thuc o bar t, khong bao gio doc bar > t.
Cac chi bao (SMA/RSI/ATR/ADX), mau hinh va regime deu tinh tren cua
so do. Nhap them bar tuong lai vao sau cua so khong doi ket qua
(xem tests/test_ai_features.py::test_no_lookahead_*). Ham la pure
function, deterministic, khong doc file / khong goi MT5 / khong
random.

Cua so: FEATURE_WINDOW = 50 bar. 50 bar du cho moi tham so per-symbol
da ship (sma_slow lon nhat 30 — XAUUSD/BNBUSD/INTC; RSI/ATR/ADX 14;
pivot can 5 bar moi ben; breakout can 10 bar). Neu config resolve ra
sma_slow > 50 (vuot khoang thuc te, du PARAM_RANGES cho toi 200) thi
build_features raise ValueError ro ten chi bao thay vi dien 0 lang le.
"""
import math

from ..models.quant import adx, atr, classify_regime, rsi, sma
from ..patterns import detect_patterns, pattern_summary

FEATURE_VERSION = 1
FEATURE_WINDOW = 50
RETURN_LOOKBACKS = (1, 3, 5, 10, 20)
VOL_LOOKBACKS = (5, 10, 20)
ADX_PERIOD = 14

PATTERN_NAMES = (
    "bullish_engulfing", "bearish_engulfing", "hammer", "shooting_star",
    "doji", "morning_star", "evening_star", "support", "resistance",
    "double_top", "double_bottom", "breakout_up", "breakout_down",
)

FEATURE_NAMES = (
    "log_ret_1", "log_ret_3", "log_ret_5", "log_ret_10", "log_ret_20",
    "hl_range_t", "co_move_t",
    "vol_5", "vol_10", "vol_20",
    "volume_rel",
    "sma_fast_rel", "sma_slow_rel", "sma_cross",
    "rsi_scaled", "atr_pct", "adx_scaled",
    "regime_trending", "regime_transitional", "regime_ranging",
    "pattern_score",
) + tuple("pat_%s" % name for name in PATTERN_NAMES) + (
    "direction_long",
)

# Tham so mac dinh khi caller khong truyen params (giong
# strategies/base.py SHARED_DEFAULTS cho cac khoa dung o day).
_DEFAULT_PARAMS = {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14,
                   "atr_period": 14}


def _std(values):
    """Do lech chuan quan the (population std); [] -> 0.0."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def _log_returns(closes):
    """Log return 1 bar: [log(c[i]/c[i-1])], i >= 1."""
    return [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes))]


def assert_feature_version(version, names=None):
    """Kiem tra mo hinh da luu khop feature hien tai.

    Raise ValueError neu version khac FEATURE_VERSION hoac danh sach
    ten cot (neu truyen) khac FEATURE_NAMES. Goi luc load model,
    truoc khi dung bat ky vector nao.
    """
    if version != FEATURE_VERSION:
        raise ValueError(
            "Feature version khong khop: model luu version %r, "
            "hien tai FEATURE_VERSION = %r — train lai model hoac "
            "dung dung phien ban features" % (version, FEATURE_VERSION))
    if names is not None and list(names) != list(FEATURE_NAMES):
        raise ValueError(
            "FEATURE_NAMES khong khop: model luu %d cot, hien tai %d "
            "cot (FEATURE_VERSION = %r) — train lai model"
            % (len(list(names)), len(FEATURE_NAMES), FEATURE_VERSION))


def feature_names():
    """Ban sao danh sach ten cot (thu tu co dinh, version 1)."""
    return list(FEATURE_NAMES)


def build_features(bars, params=None, direction=None):
    """Xay 1 vector feature (list[float], dai len(FEATURE_NAMES))
    tu cua so bar ket thuc o bar t.

    bars: list dict {open, high, low, close, volume?, time?} theo
        thu tu thoi gian tang dan — CHI cac bar <= t (khong bao gio
        truyen bar tuong lai vao day). Can it nhat FEATURE_WINDOW
        bar; neu truyen nhieu hon thi chi dung FEATURE_WINDOW bar
        cuoi (chinh la cua so ket thuc o t).
    params: dict tham so TA da resolve cua symbol (resolve_
        strategy_params) — chi doc sma_fast, sma_slow, rsi_period,
        atr_period; None thi dung mac dinh SMA5/20, RSI14, ATR14.
        ADX luon chu ky 14 (chuan dx10, strategies/base.py).
    direction: "BUY" -> +1.0, "SELL" -> -1.0, None -> 0.0 (cot
        direction_long). Gia tri khac thi raise ValueError.

    Raise ValueError (khong dien gia tri gia) khi: thieu bar, gia
    <= 0, hoac chi bao khong tinh duoc (vd sma_slow > cua so).
    """
    if bars is None:
        raise ValueError("build_features can it nhat %d bar, nhan None"
                         % FEATURE_WINDOW)
    window = list(bars)[-FEATURE_WINDOW:]
    if len(window) < FEATURE_WINDOW:
        raise ValueError(
            "build_features can it nhat %d bar cho cua so feature, "
            "chi co %d bar" % (FEATURE_WINDOW, len(window)))
    closes = [float(b["close"]) for b in window]
    highs = [float(b["high"]) for b in window]
    lows = [float(b["low"]) for b in window]
    opens = [float(b["open"]) for b in window]
    volumes = [float(b.get("volume") or 0.0) for b in window]
    if any(c <= 0 for c in closes):
        raise ValueError("build_features: gia dong cua phai > 0")
    if any(h < l for h, l in zip(highs, lows)):
        raise ValueError("build_features: high < low o 1 bar")

    merged = dict(_DEFAULT_PARAMS)
    merged.update(params or {})
    sma_fast_p = int(merged["sma_fast"])
    sma_slow_p = int(merged["sma_slow"])
    rsi_p = int(merged["rsi_period"])
    atr_p = int(merged["atr_period"])

    last = closes[-1]
    rets = _log_returns(closes)  # dai FEATURE_WINDOW - 1, 1-bar returns

    def _ret(k):
        # Return k bar = tong k log return 1 bar gan nhat
        # = log(close[t] / close[t-k]).
        return sum(rets[-k:])

    # --- Returns / bien dong ---
    hl_range = (highs[-1] - lows[-1]) / last
    co_move = (closes[-1] - opens[-1]) / last
    vols = [_std(rets[-n:]) if len(rets) >= n else _std(rets)
            for n in VOL_LOOKBACKS]
    mean_vol = sum(volumes[-20:]) / 20.0
    volume_rel = volumes[-1] / mean_vol if mean_vol > 0 else 1.0

    # --- Chi bao dx10 (chi tu cua so, khong lookahead) ---
    sma_fast = sma(closes, sma_fast_p)
    sma_slow = sma(closes, sma_slow_p)
    rsi_val = rsi(closes, rsi_p)
    atr_val = atr(highs, lows, closes, atr_p)
    adx_val = adx(highs, lows, closes, ADX_PERIOD)
    missing = []
    if sma_fast is None:
        missing.append("SMA(%d)" % sma_fast_p)
    if sma_slow is None:
        missing.append("SMA(%d)" % sma_slow_p)
    if rsi_val is None:
        missing.append("RSI(%d)" % rsi_p)
    if atr_val is None:
        missing.append("ATR(%d)" % atr_p)
    if adx_val is None:
        missing.append("ADX(%d)" % ADX_PERIOD)
    if missing:
        raise ValueError(
            "build_features: khong tinh duoc %s tren cua so %d bar — "
            "tham so vuot qua cua so (vd sma_slow lon), khong dien 0"
            % (", ".join(missing), FEATURE_WINDOW))
    if sma_fast > sma_slow:
        sma_cross = 1.0
    elif sma_fast < sma_slow:
        sma_cross = -1.0
    else:
        sma_cross = 0.0
    regime = classify_regime(adx_val)
    regime_feats = (1.0 if regime == "TRENDING" else 0.0,
                    1.0 if regime == "TRANSITIONAL" else 0.0,
                    1.0 if regime == "RANGING" else 0.0)

    # --- Mau hinh ket thuc o bar t (bar_index == chi so cuoi cua so) ---
    last_idx = len(window) - 1
    at_last = [p for p in detect_patterns(window)
               if p["bar_index"] == last_idx]
    _summary, pattern_score = pattern_summary(at_last)
    present = {p["name"] for p in at_last}
    pattern_flags = [1.0 if name in present else 0.0
                     for name in PATTERN_NAMES]

    # --- Huong lenh ---
    if direction is None:
        direction_long = 0.0
    elif direction == "BUY":
        direction_long = 1.0
    elif direction == "SELL":
        direction_long = -1.0
    else:
        raise ValueError("build_features: direction phai la 'BUY' / "
                         "'SELL' / None, nhan %r" % (direction,))

    row = ([_ret(k) for k in RETURN_LOOKBACKS]
           + [hl_range, co_move]
           + vols
           + [volume_rel,
              (sma_fast - last) / last,
              (sma_slow - last) / last,
              sma_cross,
              rsi_val / 100.0,
              atr_val / last,
              adx_val / 100.0]
           + list(regime_feats)
           + [float(pattern_score)]
           + pattern_flags
           + [direction_long])
    assert len(row) == len(FEATURE_NAMES), (len(row), len(FEATURE_NAMES))
    return [float(v) for v in row]


__all__ = ["FEATURE_VERSION", "FEATURE_WINDOW", "FEATURE_NAMES",
           "RETURN_LOOKBACKS", "VOL_LOOKBACKS", "PATTERN_NAMES",
           "ADX_PERIOD", "assert_feature_version", "feature_names",
           "build_features"]
