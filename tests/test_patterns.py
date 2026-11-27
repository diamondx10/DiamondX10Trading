"""Test mau hinh gia (PTKT): patterns.py + noi vao signals.py.
Dung nen tong hop (khong can MT5 that, khong co network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.patterns import detect_patterns, pattern_summary
from diamondx10.signals import generate_signals
from diamondx10.strategies import STRATEGIES


def bar(o, h, l, c, i):
    return {"time": i, "open": o, "high": h, "low": l, "close": c}


def neutral_bullish(i, base=100.0):
    """Nen trung lap: than 0.4, bong ngan, khong tao mau hinh."""
    return bar(base, base + 0.6, base - 0.2, base + 0.4, i)


def neutral_bearish(i, base=100.0):
    return bar(base + 0.4, base + 0.6, base - 0.2, base, i)


def names(patterns):
    return [p["name"] for p in patterns]


def pat(name, direction, strength=0.8):
    return {"name": name, "direction": direction, "strength": strength,
            "bar_index": 0, "time": 0, "detail": "test"}


def test_bullish_engulfing_detected():
    bars = [neutral_bearish(i) for i in range(4)]
    bars.append(bar(100.5, 100.7, 99.3, 99.5, 4))   # nen giam
    bars.append(bar(99.4, 100.8, 99.2, 100.6, 5))   # nen tang bao phu
    found = [p for p in detect_patterns(bars)
             if p["name"] == "bullish_engulfing"]
    assert len(found) == 1
    assert found[0]["direction"] == "bullish"
    assert found[0]["bar_index"] == 5
    assert found[0]["time"] == 5
    assert 0.0 <= found[0]["strength"] <= 1.0


def test_bearish_engulfing_detected():
    bars = [neutral_bullish(i) for i in range(4)]
    bars.append(bar(99.5, 100.7, 99.3, 100.5, 4))   # nen tang
    bars.append(bar(100.6, 100.8, 99.2, 99.4, 5))   # nen giam bao phu
    found = [p for p in detect_patterns(bars)
             if p["name"] == "bearish_engulfing"]
    assert len(found) == 1
    assert found[0]["direction"] == "bearish"
    assert found[0]["bar_index"] == 5


def test_hammer_detected():
    bars = [neutral_bullish(i) for i in range(5)]
    bars.append(bar(100.0, 101.0, 94.0, 100.9, 5))  # bong duoi dai
    found = [p for p in detect_patterns(bars) if p["name"] == "hammer"]
    assert len(found) == 1
    assert found[0]["direction"] == "bullish"


def test_shooting_star_detected():
    bars = [neutral_bullish(i) for i in range(5)]
    bars.append(bar(100.0, 107.0, 99.9, 100.9, 5))  # bong tren dai
    found = [p for p in detect_patterns(bars)
             if p["name"] == "shooting_star"]
    assert len(found) == 1
    assert found[0]["direction"] == "bearish"


def test_doji_detected():
    bars = [neutral_bullish(i) for i in range(5)]
    bars.append(bar(100.0, 101.0, 99.0, 100.02, 5))  # mo ~ dong
    found = [p for p in detect_patterns(bars) if p["name"] == "doji"]
    assert len(found) == 1
    assert found[0]["direction"] == "neutral"


def test_morning_star_detected():
    bars = [neutral_bearish(i) for i in range(4)]
    bars.append(bar(102.0, 102.2, 98.8, 99.0, 4))   # nen giam lon
    bars.append(bar(98.5, 99.0, 98.0, 98.7, 5))     # nen nho
    bars.append(bar(99.0, 101.7, 98.8, 101.5, 6))   # nen tang lon
    found = [p for p in detect_patterns(bars)
             if p["name"] == "morning_star"]
    assert len(found) == 1
    assert found[0]["direction"] == "bullish"
    assert found[0]["bar_index"] == 6


def test_evening_star_detected():
    bars = [neutral_bullish(i) for i in range(4)]
    bars.append(bar(99.0, 102.2, 98.8, 102.0, 4))   # nen tang lon
    bars.append(bar(102.5, 103.0, 102.0, 102.3, 5))  # nen nho
    bars.append(bar(102.0, 102.2, 99.3, 99.5, 6))   # nen giam lon
    found = [p for p in detect_patterns(bars)
             if p["name"] == "evening_star"]
    assert len(found) == 1
    assert found[0]["direction"] == "bearish"


def test_double_bottom_detected():
    # 2 day xoay chieu: 90.0 (bar 5) va 90.5 (bar 11), lech 0.56%.
    lows = [100, 99, 98, 97, 96, 90, 96, 97, 98, 97, 96, 90.5,
            96, 97, 98, 99, 100]
    bars = [bar(l + 0.6, l + 2.0, l, l + 1.0, i)
            for i, l in enumerate(lows)]
    pats = detect_patterns(bars)
    assert "double_bottom" in names(pats)
    assert "support" in names(pats)
    dbl = [p for p in pats if p["name"] == "double_bottom"][0]
    assert dbl["direction"] == "bullish"
    assert dbl["bar_index"] == 11
    assert "90.50" in dbl["detail"]


def test_breakout_up_detected():
    bars = [neutral_bullish(i) for i in range(11)]
    bars.append(bar(100.4, 102.2, 100.2, 102.0, 11))  # dong tren dinh cu
    found = [p for p in detect_patterns(bars)
             if p["name"] == "breakout_up"]
    assert len(found) == 1
    assert found[0]["direction"] == "bullish"
    assert found[0]["bar_index"] == 11


def test_breakout_down_detected():
    bars = [neutral_bearish(i) for i in range(11)]
    bars.append(bar(100.0, 100.2, 97.8, 98.0, 11))  # dong duoi day cu
    found = [p for p in detect_patterns(bars)
             if p["name"] == "breakout_down"]
    assert len(found) == 1
    assert found[0]["direction"] == "bearish"


def test_no_pattern_returns_empty():
    bars = [neutral_bullish(i) for i in range(12)]
    assert detect_patterns(bars) == []


def test_short_input_returns_empty():
    assert detect_patterns([]) == []
    assert detect_patterns([neutral_bullish(0)]) == []
    assert detect_patterns([neutral_bullish(i) for i in range(5)]) == []


def test_pattern_shape():
    bars = [neutral_bearish(i) for i in range(4)]
    bars.append(bar(100.5, 100.7, 99.3, 99.5, 4))
    bars.append(bar(99.4, 100.8, 99.2, 100.6, 5))
    for p in detect_patterns(bars):
        assert set(p) == {"name", "direction", "strength",
                          "bar_index", "time", "detail"}
        assert p["direction"] in ("bullish", "bearish", "neutral")
        assert 0.0 <= p["strength"] <= 1.0
        assert p["detail"].isascii()  # tieng Viet khong dau


def test_summary_bullish_positive():
    text, score = pattern_summary(
        [pat("bullish_engulfing", "bullish"),
         pat("hammer", "bullish"),
         pat("bearish_engulfing", "bearish", 0.8)])
    assert score > 0
    assert score <= 1.0
    assert "mau hinh tang" in text
    assert text.isascii()


def test_summary_bearish_negative():
    text, score = pattern_summary(
        [pat("bearish_engulfing", "bearish"),
         pat("shooting_star", "bearish"),
         pat("hammer", "bullish", 0.8)])
    assert score < 0
    assert score >= -1.0
    assert "mau hinh giam" in text


def test_summary_empty_zero():
    text, score = pattern_summary([])
    assert score == 0.0
    assert text == "khong co mau hinh"


def test_summary_neutral_only_zero():
    text, score = pattern_summary([pat("support", "neutral", 0.6),
                                   pat("resistance", "neutral", 0.6)])
    assert score == 0.0
    assert "ho tro" in text and "khang cu" in text


def test_generate_signals_includes_patterns_action_unchanged():
    closes = [100.0 + i for i in range(30)]
    bars = [{"time": i, "open": c, "high": c + 0.5,
             "low": c - 0.5, "close": c} for i, c in enumerate(closes)]
    expected_action = STRATEGIES["forex"].signal(bars)[0]
    sig = generate_signals("forex", bars)
    assert sig["action"] == expected_action
    assert "patterns" in sig
    assert "pattern_score" in sig
    assert isinstance(sig["patterns"], list)
    assert -1.0 <= sig["pattern_score"] <= 1.0
    _, score = pattern_summary(sig["patterns"])
    assert sig["pattern_score"] == score
