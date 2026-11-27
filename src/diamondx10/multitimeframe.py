"""Multi-timeframe TA (v1): xu huong khung lon + loc tin hieu khung vao.

Stack v1 (da chot): trend H1 + entry M15. Timing M5 NGOAI v1
(khong dung trong logic tin hieu); H4 NGOAI v1 (khong co trong
SUPPORTED_TIMEFRAMES).

- `resolve_timeframes(cfg)`: doc muc `timeframes:` trong config.
  Thieu muc -> M15-only, loc TAT (tuong thich cu).
- `compute_htf_trend(bars, ...)`: xu huong H1 tu SMA nhanh/cham +
  ADX(14). Do dai SMA lay tu resolve_strategy_params (ghi de rieng
  symbol duoc thua huong mien phi qua co che per_symbol san co —
  KHONG co he thong ghi de thu hai).
- `htf_filter(action, trend)`: loc tin hieu M15 theo trend H1 —
  chan lenh nguoc trend manh, cho qua khi trend yeu / thieu du lieu
  (degradation giong live: khong co du lieu thi khong loc).

Module nay chi tinh toan + loc, KHONG doc MT5 / kho / Telegram.
Live loop (coordinator tich hop sau) goi compute_htf_trend tren bar
H1 that roi truyen dict trend vao generate_signals(htf_trend=...);
backtest goi cung duong do tu kho lich su (xem backtest.py).
"""
from .models.quant import adx as _adx
from .models.quant import sma as _sma

# Khung nen hop le (giong __main__.SUPPORTED_TIMEFRAMES / live).
ALLOWED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "D1"}

# Mac dinh khi config THIEU muc `timeframes:`: M15-only, loc TAT.
_MISSING_DEFAULTS = {
    "entry": "M15",
    "trend": "H1",
    "timing": "M5",
    "trend_enabled": False,
    "timing_enabled": False,
    "htf_adx_min": 20,
    "trend_bars": 60,
}

# Mac dinh tung khoa khi muc `timeframes:` CO nhung thieu khoa:
# trend bat theo mac dinh (loc BAT khi nguoi dung khai muc nay).
_PRESENT_DEFAULTS = {
    "entry": "M15",
    "trend": "H1",
    "timing": "M5",
    "trend_enabled": True,
    "timing_enabled": False,
    "htf_adx_min": 20,
    "trend_bars": 60,
}

# Do dai SMA mac dinh khi khong resolve duoc tu config.
_DEFAULT_SMA_FAST = 5
_DEFAULT_SMA_SLOW = 20


def resolve_timeframes(cfg):
    """Doc muc `timeframes:` trong config ve dict day du 7 khoa.

    Thieu muc / cfg None / cfg khong phai dict -> M15-only, loc TAT
    (trend_enabled False — hanh vi cu giu nguyen). Co muc -> moi
    khoa thieu lay mac dinh rieng (trend_enabled mac dinh True).
    entry/trend/timing phai nam trong {M1, M5, M15, H1, D1} (ke ca
    H4) neu khong -> ValueError neu ro gia tri la. Khong bao gio
    raise khi thieu / None cfg.
    """
    if not isinstance(cfg, dict):
        return dict(_MISSING_DEFAULTS)
    section = cfg.get("timeframes")
    if not isinstance(section, dict):
        return dict(_MISSING_DEFAULTS)
    out = {}
    for key, default in _PRESENT_DEFAULTS.items():
        out[key] = section.get(key, default)
    for key in ("entry", "trend", "timing"):
        value = out[key]
        if value not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframes.{key} khong hop le: {value!r} "
                f"(chon trong {sorted(ALLOWED_TIMEFRAMES)})")
    for key in ("trend_enabled", "timing_enabled"):
        out[key] = bool(out[key])
    for key in ("htf_adx_min", "trend_bars"):
        try:
            out[key] = int(out[key])
        except (TypeError, ValueError):
            raise ValueError(
                f"timeframes.{key} phai la so nguyen, nhan "
                f"{out[key]!r}")
    return out


def _sma_lengths(cfg, desk, symbol):
    """Do dai SMA cho trend: resolve theo (desk, symbol) khi du
    ca 3 (cfg + desk + symbol), neu khong thi mac dinh 5/20.
    Resolve loi (vd symbol la) thi roi ve mac dinh — trend khong
    duoc crash vi config; khong bao gio raise."""
    if cfg is None or desk is None or symbol is None:
        return _DEFAULT_SMA_FAST, _DEFAULT_SMA_SLOW
    try:
        from .strategies.registry import resolve_strategy_params
        params = resolve_strategy_params(cfg, desk, symbol)
    except Exception:  # noqa: BLE001 — roi ve mac dinh, khong raise
        return _DEFAULT_SMA_FAST, _DEFAULT_SMA_SLOW
    try:
        return int(params["sma_fast"]), int(params["sma_slow"])
    except (KeyError, TypeError, ValueError):
        return _DEFAULT_SMA_FAST, _DEFAULT_SMA_SLOW


def _unknown(timeframe, bars_n, reason, htf_adx_min, fast=None, slow=None):
    """Dict trend 'unknown' chuan (thieu du lieu / khong tinh duoc)."""
    return {"timeframe": timeframe, "direction": "unknown",
            "adx": None, "sma_fast": fast, "sma_slow": slow,
            "trusted": False, "bars": bars_n, "reason": reason,
            "htf_adx_min": htf_adx_min}


def compute_htf_trend(bars, cfg=None, *, timeframe="H1", desk=None,
                      symbol=None):
    """Xu huong khung lon (mac dinh H1) tu list bar OHLC.

    Tra dict {timeframe, direction, adx, sma_fast, sma_slow,
    trusted, bars, reason, htf_adx_min}:
    - direction: "up" (SMA nhanh > SMA cham), "down" (<), "neutral"
      (=), "unknown" (thieu du lieu / khong tinh duoc).
    - trusted: ADX(14) tinh duoc va >= htf_adx_min (mac dinh 20).
    - bars: so bar da nhan. Can toi thieu max(sma_slow, 15) + 1 bar;
      it hon -> direction "unknown", adx None, trusted False.
    Khong bao gio raise tren bar ngan / rong — tra dict "unknown".
    """
    tf_cfg = resolve_timeframes(cfg)
    htf_adx_min = tf_cfg["htf_adx_min"]
    bars = list(bars or [])
    fast_p, slow_p = _sma_lengths(cfg, desk, symbol)
    need = max(slow_p, 15) + 1
    if len(bars) < need:
        return _unknown(
            timeframe, len(bars),
            f"{timeframe}: thieu du lieu ({len(bars)}/{need} bar) — "
            "khong xac dinh duoc trend",
            htf_adx_min)
    try:
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        fast = _sma(closes, fast_p)
        slow = _sma(closes, slow_p)
        adx_val = _adx(highs, lows, closes, 14)
    except (KeyError, TypeError, ValueError):
        return _unknown(
            timeframe, len(bars),
            f"{timeframe}: khong tinh duoc SMA/ADX — "
            "khong xac dinh duoc trend",
            htf_adx_min)
    if fast is None or slow is None:
        return _unknown(
            timeframe, len(bars),
            f"{timeframe}: khong tinh duoc SMA/ADX — "
            "khong xac dinh duoc trend",
            htf_adx_min, fast, slow)
    if fast > slow:
        direction, relation, label = "up", ">", "trend UP"
    elif fast < slow:
        direction, relation, label = "down", "<", "trend DOWN"
    else:
        direction, relation, label = "neutral", "==", "trend trung lap"
    trusted = adx_val is not None and adx_val >= htf_adx_min
    adx_txt = f"{adx_val:.1f}" if adx_val is not None else "?"
    reason = (f"{timeframe}: SMA{fast_p} ({fast:.3f}) {relation} "
              f"SMA{slow_p} ({slow:.3f}), ADX {adx_txt} — {label}")
    if not trusted:
        reason += " (ADX thap — chua du tin cay)"
    return {"timeframe": timeframe, "direction": direction,
            "adx": adx_val, "sma_fast": fast, "sma_slow": slow,
            "trusted": trusted, "bars": len(bars), "reason": reason,
            "htf_adx_min": htf_adx_min}


def htf_filter(action, trend):
    """Loc tin hieu M15 theo trend H1. Tra (allowed, note).

    - trend None (tinh nang tat) -> (True, "").
    - HOLD -> (True, "") (loc chi ap cho BUY/SELL).
    - direction "unknown" (thieu du lieu) -> cho qua, ghi chu.
    - trusted False (ADX duoi nguong) -> cho qua, ghi chu.
    - "up": BUY dong thuan -> cho; SELL -> chan.
    - "down": nguoc lai. "neutral" -> cho, ghi chu trung lap.
    note la chuoi rong khi khong co gi can ghi them (tat / HOLD).
    """
    if action == "HOLD":
        return True, ""
    if trend is None:
        return True, ""
    if not isinstance(trend, dict):
        return True, ""
    tf = trend.get("timeframe") or "H1"
    direction = trend.get("direction")
    adx_val = trend.get("adx")
    htf_adx_min = trend.get("htf_adx_min", 20)
    adx_txt = f"{adx_val:.1f}" if adx_val is not None else "?"
    if direction not in ("up", "down", "neutral"):
        return True, (f"[HTF {tf}: thieu du lieu — khong ap dung loc]")
    if not trend.get("trusted"):
        return True, (f"[HTF {tf}: ADX thap ({adx_txt} < {htf_adx_min}) "
                      "— khong ap dung loc]")
    if direction == "up":
        if action == "BUY":
            return True, (f"[HTF {tf}: trend UP, ADX {adx_txt} "
                          "— dong thuan]")
        if action == "SELL":
            return False, f"[HTF {tf}: trend UP — khong SELL]"
    if direction == "down":
        if action == "SELL":
            return True, (f"[HTF {tf}: trend DOWN, ADX {adx_txt} "
                          "— dong thuan]")
        if action == "BUY":
            return False, f"[HTF {tf}: trend DOWN — khong BUY]"
    # direction == "neutral"
    return True, f"[HTF {tf}: trend trung lap — cho phep]"


__all__ = ["ALLOWED_TIMEFRAMES", "resolve_timeframes",
           "compute_htf_trend", "htf_filter"]
