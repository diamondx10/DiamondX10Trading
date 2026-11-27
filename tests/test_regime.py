"""Test ADX/regime (merge tu DiamondX10): classify_regime, detect_regime,
atr_percentile, adx. Dung du lieu tong hop (khong can MT5 that)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.models.quant import (
    adx,
    atr_percentile,
    classify_regime,
    detect_regime,
)


def bars_from_closes(closes, half_range=0.5):
    return [{"time": i, "open": c, "high": c + half_range,
             "low": c - half_range, "close": c}
            for i, c in enumerate(closes)]


def closes_from_changes(start, changes):
    out = [start]
    for d in changes:
        out.append(round(out[-1] + d, 6))
    return out


def series(bars):
    return ([b["high"] for b in bars], [b["low"] for b in bars],
            [b["close"] for b in bars])


def test_adx_strong_trend_high():
    # Tang deu 30 bar: ADX phai cao (> 25).
    bars = bars_from_closes(closes_from_changes(100, [1.0] * 30))
    value = adx(*series(bars))
    assert value is not None
    assert value > 25.0


def test_adx_flat_low():
    # Dao dong quanh 1 gia (len/xuong xen ke nho): ADX phai thap.
    bars = bars_from_closes(
        closes_from_changes(100, [0.2, -0.2] * 15))
    value = adx(*series(bars))
    assert value is not None
    assert value < 25.0


def test_adx_needs_enough_bars():
    bars = bars_from_closes([100.0] * 10)
    assert adx(*series(bars)) is None


def test_classify_regime_thresholds():
    # classify_regime chi co 3 muc (nguong ADX 25/15 cua repo goc);
    # ADX >= 40 chi lam tang confidence trong detect_regime.
    assert classify_regime(45.0) == "TRENDING"
    assert classify_regime(30.0) == "TRENDING"
    assert classify_regime(20.0) == "TRANSITIONAL"
    assert classify_regime(10.0) == "RANGING"
    assert classify_regime(None) == "UNKNOWN"


def test_detect_regime_trending_bullish():
    # Can >= 51 bar de SMA50 co gia tri (huong SMA20 vs SMA50).
    bars = bars_from_closes(closes_from_changes(100, [1.0] * 60))
    reg = detect_regime(bars)
    assert reg["regime"] == "TRENDING"
    assert reg["direction"] == "BULLISH"
    assert reg["adx"] > 25.0
    assert 0.0 <= reg["confidence"] <= 1.0


def test_detect_regime_bearish_direction():
    bars = bars_from_closes(closes_from_changes(100, [-1.0] * 60))
    reg = detect_regime(bars)
    assert reg["direction"] == "BEARISH"


def test_detect_regime_unknown_too_few_bars():
    bars = bars_from_closes([100.0] * 5)
    reg = detect_regime(bars)
    assert reg["regime"] == "UNKNOWN"
    assert reg["adx"] == 0.0
    assert reg["confidence"] == 0.0


def test_atr_percentile_default_when_short():
    # It hon 100 gia tri ATR: mac dinh 50.0 (trung binh), khong crash.
    bars = bars_from_closes(closes_from_changes(100, [0.5] * 30))
    assert atr_percentile(*series(bars)) == 50.0
    assert 0.0 <= atr_percentile(*series(bars), lookback=10) <= 100.0


def test_detect_regime_volatility_bands():
    # ATR percentile mac dinh 50 -> volatility NORMAL.
    bars = bars_from_closes(closes_from_changes(100, [1.0] * 30))
    reg = detect_regime(bars)
    assert reg["volatility"] in ("LOW", "NORMAL", "HIGH")
    assert reg["atr_percentile"] == 50.0


def test_adx_value_bounded():
    bars = bars_from_closes(closes_from_changes(100, [1.0, -0.5] * 15))
    value = adx(*series(bars))
    assert value is not None
    assert 0.0 <= value <= 100.0
    assert not math.isnan(value)
