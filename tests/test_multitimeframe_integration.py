"""Test tich hop da khung thoi gian (MTF): xu huong H1 + entry M15.

Hop dong chung (xem docs/multi-timeframe-ta.md, muc 64):
- Stack v1: trend H1 + entry M15. Timing M5 NGOAI v1, H4 NGOAI v1.
- `diamondx10.multitimeframe`: resolve_timeframes(cfg);
  compute_htf_trend(bars, cfg=None, *, timeframe="H1", desk=None,
  symbol=None) -> dict {timeframe, direction, adx, sma_fast, sma_slow,
  trusted, bars, reason, htf_adx_min}; direction trong
  {"up", "down", "neutral", "unknown"}; trusted = adx >= htf_adx_min
  (mac dinh 20); qua it nen -> "unknown", trusted False.
- htf_filter(action, trend) -> (allowed, note).
- generate_signals(..., htf_trend=None): tin hieu nguoc xu huong H1
  thanh HOLD, levels None, ghi chu HTF ghep vao reason; ket qua them
  khoa "htf_trend".
- outcomes.build_record: context them "htf" {timeframe, direction,
  adx, trusted, agreement} voi agreement trong {"agree", "against",
  "neutral", "not_applied"}.
- `diamondx10.data.multitimeframe.fetch_bars_for_timeframes(get_bars,
  symbol, cfg, *, store=None)` -> {"bars": {tf: [...]}, "missing":
  [tf...]}; TF loi hoac < 10 nen tinh la thieu, khong bao gio raise.
  Chu ky goi that: get_bars(timeframe, n) — hop dong goc khong ghi
  ro chu ky nay, test nay theo ban hien thuc da ha canh.

Chi dung nen GIA (khong MT5, khong mang). Fixture: so gia / chat_id
GIA (khong dung so that cua user).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_soft_rules import bars_from_closes, buy_bars, closes_from_changes

from diamondx10.data.multitimeframe import fetch_bars_for_timeframes
from diamondx10.multitimeframe import (
    compute_htf_trend,
    htf_filter,
    resolve_timeframes,
)
from diamondx10.outcomes import build_record
from diamondx10.signals import generate_signals


def h1_up_bars():
    # Xu huong len deu: SMA5 > SMA20, ADX(14) ~ 97.8 (>> 20).
    return bars_from_closes(closes_from_changes(100, [1] * 59))


def h1_down_bars():
    # Xu huong xuong deu: SMA5 < SMA20, ADX(14) ~ 97.8 (>> 20).
    return bars_from_closes(closes_from_changes(100, [-1] * 59))


def h1_flat_bars():
    # Di ngang: SMA5 == SMA20, ADX(14) = 0.0 -> khong dang tin.
    return bars_from_closes([100.0] * 60)


def sell_bars():
    # Anh doi xung cua buy_bars(): RSI ~ 40, SMA5 < SMA20 -> SELL.
    closes = closes_from_changes(
        100, [-1] * 6 + [-0.75, 2 / 3] * 6 + [-0.75, -0.75])
    return bars_from_closes(closes)


def _result(action="BUY"):
    return {"status": "TRADED", "action": action, "price": 103.0,
            "sl": 101.0, "tp": 107.0, "volume": 0.01, "risk_usd": 10.0,
            "manager": "Yuling", "time": "2026-11-27T00:00:00Z"}


# --- resolve_timeframes ---------------------------------------------------

def test_resolve_timeframes_missing_section_is_m15_only():
    resolved = resolve_timeframes({})
    assert resolved["entry"] == "M15"
    assert resolved["trend_enabled"] is False


def test_resolve_timeframes_full_section():
    cfg = {"timeframes": {"entry": "M15", "trend": "H1",
                          "timing": "M5", "trend_enabled": True,
                          "timing_enabled": False, "htf_adx_min": 20,
                          "trend_bars": 60}}
    resolved = resolve_timeframes(cfg)
    assert resolved["entry"] == "M15"
    assert resolved["trend"] == "H1"
    assert resolved["timing"] == "M5"
    assert resolved["trend_enabled"] is True
    assert resolved["timing_enabled"] is False
    assert resolved["htf_adx_min"] == 20
    assert resolved["trend_bars"] == 60


# --- compute_htf_trend ----------------------------------------------------

def test_htf_trend_up_strong_adx():
    trend = compute_htf_trend(h1_up_bars())
    assert trend["timeframe"] == "H1"
    assert trend["direction"] == "up"
    assert trend["adx"] >= 20
    assert trend["trusted"] is True
    assert trend["htf_adx_min"] == 20
    assert trend["bars"] == 60
    assert trend["sma_fast"] > trend["sma_slow"]


def test_htf_trend_down_strong_adx():
    trend = compute_htf_trend(h1_down_bars())
    assert trend["direction"] == "down"
    assert trend["adx"] >= 20
    assert trend["trusted"] is True
    assert trend["sma_fast"] < trend["sma_slow"]


def test_htf_trend_too_few_bars_is_unknown():
    trend = compute_htf_trend(bars_from_closes([100.0] * 5))
    assert trend["direction"] == "unknown"
    assert trend["trusted"] is False


def test_htf_trend_flat_is_untrusted():
    trend = compute_htf_trend(h1_flat_bars())
    assert trend["trusted"] is False
    assert trend["adx"] < 20


# --- htf_filter: bang cho phep / chan --------------------------------------

def test_htf_filter_no_trend_passes_through():
    assert htf_filter("BUY", None) == (True, "")
    assert htf_filter("SELL", None) == (True, "")


def test_htf_filter_unknown_passes_with_missing_note():
    trend = compute_htf_trend(bars_from_closes([100.0] * 5))
    allowed, note = htf_filter("BUY", trend)
    assert allowed is True
    assert note == "[HTF H1: thieu du lieu — khong ap dung loc]"


def test_htf_filter_untrusted_passes_with_low_adx_note():
    trend = {"timeframe": "H1", "direction": "up", "adx": 12.5,
             "sma_fast": 101.0, "sma_slow": 100.0, "trusted": False,
             "bars": 60, "reason": "", "htf_adx_min": 20}
    allowed, note = htf_filter("BUY", trend)
    assert allowed is True
    assert "[HTF H1: ADX thap (12.5 <" in note
    assert "khong ap dung loc]" in note


def test_htf_filter_up_allows_buy_blocks_sell():
    trend = compute_htf_trend(h1_up_bars())
    allowed, note = htf_filter("BUY", trend)
    assert allowed is True
    assert "[HTF H1: trend UP, ADX " in note
    assert "dong thuan]" in note
    allowed, note = htf_filter("SELL", trend)
    assert allowed is False
    assert note == "[HTF H1: trend UP — khong SELL]"


def test_htf_filter_down_allows_sell_blocks_buy():
    trend = compute_htf_trend(h1_down_bars())
    allowed, note = htf_filter("SELL", trend)
    assert allowed is True
    assert "[HTF H1: trend DOWN, ADX " in note
    assert "dong thuan]" in note
    allowed, note = htf_filter("BUY", trend)
    assert allowed is False
    assert note == "[HTF H1: trend DOWN — khong BUY]"


def test_htf_filter_neutral_allows_both():
    trend = {"timeframe": "H1", "direction": "neutral", "adx": 25.0,
             "sma_fast": 100.0, "sma_slow": 100.0, "trusted": True,
             "bars": 60, "reason": "", "htf_adx_min": 20}
    allowed, note = htf_filter("BUY", trend)
    assert allowed is True
    assert note == "[HTF H1: trend trung lap — cho phep]"
    assert htf_filter("SELL", trend)[0] is True


def test_htf_filter_hold_passes_through():
    trend = compute_htf_trend(h1_up_bars())
    assert htf_filter("HOLD", trend) == (True, "")


# --- End-to-end: (a) dong thuan --------------------------------------------

def test_e2e_htf_up_m15_buy_stays_buy():
    trend = compute_htf_trend(h1_up_bars())
    sig = generate_signals("forex", buy_bars(), htf_trend=trend)
    assert sig["action"] == "BUY"
    assert sig["levels"] is not None
    assert "[HTF H1: trend UP, ADX " in sig["reason"]
    assert "dong thuan]" in sig["reason"]
    assert sig["htf_trend"]["direction"] == "up"
    assert sig["htf_trend"]["trusted"] is True


# --- End-to-end: (b) nguoc xu huong ----------------------------------------

def test_e2e_htf_down_m15_buy_becomes_hold():
    trend = compute_htf_trend(h1_down_bars())
    sig = generate_signals("forex", buy_bars(), htf_trend=trend)
    assert sig["action"] == "HOLD"
    assert sig["levels"] is None
    assert "[HTF H1: trend DOWN — khong BUY]" in sig["reason"]
    assert sig["htf_trend"]["direction"] == "down"


# --- End-to-end: (c) thieu nen H1 ------------------------------------------

def test_e2e_missing_h1_degrades_to_m15_only():
    # Chu ky goi that cua module data: get_bars(timeframe, n).
    def fake_get_bars(timeframe, n, **kwargs):
        if timeframe == "H1":
            return []
        return buy_bars()

    cfg = {"timeframes": {"entry": "M15", "trend": "H1",
                          "timing": "M5", "trend_enabled": True,
                          "timing_enabled": False, "htf_adx_min": 20,
                          "trend_bars": 60}}
    fetched = fetch_bars_for_timeframes(fake_get_bars, "EURUSD", cfg)
    assert "H1" in fetched["missing"]
    assert fetched["bars"]["M15"]
    trend = compute_htf_trend(fetched["bars"].get("H1") or [])
    assert trend["direction"] == "unknown"
    assert trend["trusted"] is False
    # Khong crash, tin hieu M15 van chay, kem ghi chu thieu du lieu.
    sig = generate_signals("forex", fetched["bars"]["M15"],
                           htf_trend=trend)
    assert sig["action"] == "BUY"
    assert "[HTF H1: thieu du lieu — khong ap dung loc]" in sig["reason"]


def test_fetch_counts_raising_timeframe_as_missing():
    def fake_get_bars(timeframe, n, **kwargs):
        if timeframe == "H1":
            raise RuntimeError("MT5 chua mo")
        return buy_bars()

    cfg = {"timeframes": {"entry": "M15", "trend": "H1",
                          "timing": "M5", "trend_enabled": True,
                          "timing_enabled": False, "htf_adx_min": 20,
                          "trend_bars": 60}}
    fetched = fetch_bars_for_timeframes(fake_get_bars, "EURUSD", cfg)
    assert "H1" in fetched["missing"]
    assert fetched["bars"]["M15"]


# --- outcomes: boi canh htf trong ban ghi ---------------------------------

def test_build_record_carries_htf_agreement():
    trend = compute_htf_trend(h1_up_bars())
    sig = generate_signals("forex", buy_bars(), htf_trend=trend)
    rec = build_record(_result("BUY"), sig, None, "forex", "EURUSD")
    htf = rec["context"]["htf"]
    assert htf["timeframe"] == "H1"
    assert htf["direction"] == "up"
    assert htf["adx"] >= 20
    assert htf["trusted"] is True
    assert htf["agreement"] == "agree"


def test_build_record_htf_against_when_sell_into_uptrend():
    trend = compute_htf_trend(h1_up_bars())
    # SELL thuan M15 (khong qua loc) + trend H1 UP -> against.
    sig = generate_signals("forex", sell_bars())
    assert sig["action"] == "SELL"
    sig = dict(sig, htf_trend=trend)
    rec = build_record(_result("SELL"), sig, None, "forex", "EURUSD")
    assert rec["context"]["htf"]["agreement"] == "against"


def test_build_record_htf_not_applied_without_trend():
    sig = generate_signals("forex", buy_bars())
    rec = build_record(_result("BUY"), sig, None, "forex", "EURUSD")
    assert rec["context"]["htf"]["agreement"] == "not_applied"
