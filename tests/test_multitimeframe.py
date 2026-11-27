"""Test multi-timeframe TA v1 (trend H1 + entry M15).

Chi dung bar gia (fake), khong can MT5, khong co network.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import (
    compare_strategies,
    run_backtest,
    run_backtest_from_history,
)
from diamondx10.config import DEFAULT
from diamondx10.data.history import HistoryStore
from diamondx10.multitimeframe import (
    compute_htf_trend,
    htf_filter,
    resolve_timeframes,
)
from diamondx10.outcomes import build_record
from diamondx10.signals import generate_signals


def _bars(closes, step=3600, t0=0, half=0.5):
    return [{"time": t0 + i * step, "open": c, "high": c + half,
             "low": c - half, "close": c}
            for i, c in enumerate(closes)]


def _up_closes(n=60, start=100.0, step=1.0):
    return [start + i * step for i in range(n)]


def _down_closes(n=60, start=160.0, step=1.0):
    return [start - i * step for i in range(n)]


def _osc_closes(n=60, start=100.0):
    # Tang/giam xen ke: SMA5 > SMA20 nhung ADX thap (~6) — trend yeu.
    out = [start]
    for i in range(n - 1):
        out.append(round(out[-1] + (0.75 if i % 2 == 0 else -2 / 3), 6))
    return out


def _cfg(mtf=False, per_symbol=None, tf_overrides=None):
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    if per_symbol is not None:
        cfg["strategy"] = dict(cfg["strategy"])
        cfg["strategy"]["per_symbol"] = per_symbol
    if mtf:
        section = {"entry": "M15", "trend": "H1", "timing": "M5",
                   "trend_enabled": True, "timing_enabled": False,
                   "htf_adx_min": 20, "trend_bars": 60}
        if tf_overrides:
            section.update(tf_overrides)
        cfg["timeframes"] = section
    return cfg


def _trend(direction, adx=28.5, trusted=True, timeframe="H1", minimum=20):
    return {"timeframe": timeframe, "direction": direction, "adx": adx,
            "sma_fast": 105.0, "sma_slow": 100.0, "trusted": trusted,
            "bars": 60, "reason": "fake", "htf_adx_min": minimum}


# ---------------- resolve_timeframes ----------------

def test_resolve_timeframes_missing_section_is_m15_only_off():
    assert resolve_timeframes(None) == {
        "entry": "M15", "trend": "H1", "timing": "M5",
        "trend_enabled": False, "timing_enabled": False,
        "htf_adx_min": 20, "trend_bars": 60}
    assert resolve_timeframes({})["trend_enabled"] is False
    assert resolve_timeframes({"timeframes": None})["trend_enabled"] \
        is False
    assert resolve_timeframes({"timeframes": "khong-phai-dict"})[
        "trend_enabled"] is False


def test_resolve_timeframes_present_section_defaults():
    out = resolve_timeframes({"timeframes": {"trend_enabled": False}})
    assert out == {"entry": "M15", "trend": "H1", "timing": "M5",
                   "trend_enabled": False, "timing_enabled": False,
                   "htf_adx_min": 20, "trend_bars": 60}
    # Muc co nhung thieu khoa trend_enabled -> mac dinh True.
    assert resolve_timeframes({"timeframes": {}})["trend_enabled"] is True
    assert resolve_timeframes({"timeframes": {"htf_adx_min": 25}})[
        "htf_adx_min"] == 25


def test_resolve_timeframes_exact_contract_section():
    cfg = {"timeframes": {"entry": "M15", "trend": "H1", "timing": "M5",
                          "trend_enabled": True, "timing_enabled": False,
                          "htf_adx_min": 20, "trend_bars": 60}}
    assert resolve_timeframes(cfg) == cfg["timeframes"]


@pytest.mark.parametrize("key,value", [
    ("entry", "H4"), ("entry", "W1"), ("trend", "H4"),
    ("trend", "M30"), ("timing", "H4"), ("timing", "D2")])
def test_resolve_timeframes_bad_timeframe_raises(key, value):
    with pytest.raises(ValueError, match=value):
        resolve_timeframes({"timeframes": {key: value}})


# ---------------- compute_htf_trend ----------------

def test_compute_htf_trend_up():
    trend = compute_htf_trend(_bars(_up_closes()))
    assert trend["direction"] == "up"
    assert trend["trusted"] is True
    assert trend["adx"] == pytest.approx(97.8, abs=0.5)
    assert trend["adx"] >= 20
    assert trend["bars"] == 60
    assert trend["timeframe"] == "H1"
    assert trend["htf_adx_min"] == 20
    assert trend["sma_fast"] > trend["sma_slow"]
    assert "trend UP" in trend["reason"]
    assert "SMA5" in trend["reason"] and "SMA20" in trend["reason"]


def test_compute_htf_trend_down():
    trend = compute_htf_trend(_bars(_down_closes()))
    assert trend["direction"] == "down"
    assert trend["trusted"] is True
    assert trend["sma_fast"] < trend["sma_slow"]
    assert "trend DOWN" in trend["reason"]


def test_compute_htf_trend_neutral_flat():
    trend = compute_htf_trend(_bars([100.0] * 60))
    assert trend["direction"] == "neutral"
    assert trend["sma_fast"] == pytest.approx(trend["sma_slow"])
    assert "trung lap" in trend["reason"]


def test_compute_htf_trend_unknown_short_and_empty():
    for bars in (_bars(_up_closes(10)), [], None):
        trend = compute_htf_trend(bars)
        assert trend["direction"] == "unknown"
        assert trend["adx"] is None
        assert trend["trusted"] is False
        assert trend["bars"] == len(bars or [])
        assert "thieu du lieu" in trend["reason"]


def test_compute_htf_trend_weak_adx_not_trusted():
    trend = compute_htf_trend(_bars(_osc_closes()))
    assert trend["direction"] == "up"
    assert trend["trusted"] is False
    assert trend["adx"] is not None and trend["adx"] < 20
    assert "ADX thap" in trend["reason"]


def test_compute_htf_trend_per_symbol_sma_lengths():
    cfg = _cfg(per_symbol={"EURUSD": {"sma_fast": 8, "sma_slow": 21}})
    trend = compute_htf_trend(_bars(_up_closes()), cfg,
                              desk="forex", symbol="EURUSD")
    assert trend["direction"] == "up"
    assert "SMA8" in trend["reason"] and "SMA21" in trend["reason"]
    # Khong truyen cfg/desk/symbol -> mac dinh 5/20.
    plain = compute_htf_trend(_bars(_up_closes()))
    assert "SMA5" in plain["reason"] and "SMA20" in plain["reason"]


def test_compute_htf_trend_htf_adx_min_from_cfg():
    cfg = _cfg(mtf=True, tf_overrides={"htf_adx_min": 99})
    trend = compute_htf_trend(_bars(_up_closes()), cfg)
    assert trend["htf_adx_min"] == 99
    assert trend["trusted"] is False  # ADX ~97.8 < 99
    cfg_low = _cfg(mtf=True, tf_overrides={"htf_adx_min": 10})
    assert compute_htf_trend(
        _bars(_up_closes()), cfg_low)["trusted"] is True


# ---------------- htf_filter ----------------

def test_htf_filter_none_and_hold():
    assert htf_filter("BUY", None) == (True, "")
    assert htf_filter("SELL", None) == (True, "")
    assert htf_filter("HOLD", _trend("up")) == (True, "")


def test_htf_filter_unknown_and_weak_adx_pass_with_note():
    assert htf_filter("BUY", _trend("unknown", adx=None,
                                     trusted=False)) == (
        True, "[HTF H1: thieu du lieu — khong ap dung loc]")
    assert htf_filter("SELL", _trend("up", adx=12.3,
                                     trusted=False)) == (
        True, "[HTF H1: ADX thap (12.3 < 20) — khong ap dung loc]")


def test_htf_filter_up_blocks_sell_allows_buy():
    assert htf_filter("BUY", _trend("up")) == (
        True, "[HTF H1: trend UP, ADX 28.5 — dong thuan]")
    assert htf_filter("SELL", _trend("up")) == (
        False, "[HTF H1: trend UP — khong SELL]")


def test_htf_filter_down_blocks_buy_allows_sell():
    assert htf_filter("SELL", _trend("down")) == (
        True, "[HTF H1: trend DOWN, ADX 28.5 — dong thuan]")
    assert htf_filter("BUY", _trend("down")) == (
        False, "[HTF H1: trend DOWN — khong BUY]")


def test_htf_filter_neutral_allows_with_note():
    assert htf_filter("BUY", _trend("neutral")) == (
        True, "[HTF H1: trend trung lap — cho phep]")
    assert htf_filter("SELL", _trend("neutral")) == (
        True, "[HTF H1: trend trung lap — cho phep]")


def test_htf_filter_adx_none_prints_question_mark():
    allowed, note = htf_filter("BUY", _trend("up", adx=None))
    assert allowed is True
    assert note == "[HTF H1: trend UP, ADX ? — dong thuan]"


# ---------------- generate_signals ----------------

def _m15_buy_bars():
    # RSI ~60, SMA5 > SMA20 -> BUY (mau tu test_soft_rules).
    closes = [100.0]
    for d in [1] * 6 + [0.75, -2 / 3] * 6 + [0.75, 0.75]:
        closes.append(round(closes[-1] + d, 6))
    return _bars(closes, step=900)


def test_generate_signals_blocks_counter_trend_buy():
    trend = compute_htf_trend(_bars(_down_closes()))
    assert trend["direction"] == "down" and trend["trusted"] is True
    sig = generate_signals("forex", _m15_buy_bars(), htf_trend=trend)
    assert sig["action"] == "HOLD"
    assert sig["levels"] is None
    assert "[HTF H1: trend DOWN — khong BUY]" in sig["reason"]
    assert sig["htf_trend"] == trend


def test_generate_signals_allows_aligned_buy():
    trend = compute_htf_trend(_bars(_up_closes()))
    assert trend["direction"] == "up" and trend["trusted"] is True
    sig = generate_signals("forex", _m15_buy_bars(), htf_trend=trend)
    assert sig["action"] == "BUY"
    assert sig["levels"] is not None
    assert "[HTF H1: trend UP, ADX" in sig["reason"]
    assert "dong thuan" in sig["reason"]
    assert sig["htf_trend"] == trend


def test_generate_signals_no_trend_is_unchanged():
    plain = generate_signals("forex", _m15_buy_bars())
    assert plain["action"] == "BUY"
    assert plain["levels"] is not None
    assert "[HTF" not in plain["reason"]
    assert plain["htf_trend"] is None
    # Trend unknown / yeu thi cho qua, chi them ghi chu.
    weak = compute_htf_trend(_bars(_osc_closes()))
    sig = generate_signals("forex", _m15_buy_bars(), htf_trend=weak)
    assert sig["action"] == "BUY"
    assert "khong ap dung loc" in sig["reason"]


def test_generate_signals_hold_unaffected_by_trend():
    flat = _bars([100.0] * 60, step=900)
    sig = generate_signals("forex", flat,
                           htf_trend=_trend("down"))
    assert sig["action"] == "HOLD"
    assert "[HTF" not in sig["reason"]


# ---------------- outcomes.build_record ----------------

def _fake_sig(action="BUY", trend=None):
    sig = {"desk": "forex", "strategy": "default", "action": action,
           "reason": "fake", "levels": {"entry": 103.0, "sl": 101.5,
                                        "tp": 106.0, "atr": 1.0},
           "size_scale": 1.0, "regime": {"regime": "TRENDING"},
           "patterns": [], "pattern_score": 0.0, "symbol": "EURUSD",
           "params": {"sma_fast": 5, "sma_slow": 20},
           "context": {"rsi": 59.0, "sma_fast": 103.5,
                       "sma_slow": 102.0, "adx": 28.5},
           "htf_trend": trend}
    return sig


def _fake_result(action="BUY"):
    return {"symbol": "EURUSD", "action": action, "status": "TRADED",
            "price": 103.0, "sl": 101.5, "tp": 106.0, "volume": 0.01,
            "risk_usd": 10.0, "manager": "Yuling Pan",
            "time": "2026-11-27T10:00:00+00:00"}


@pytest.mark.parametrize("action,direction,expected", [
    ("BUY", "up", "agree"),
    ("SELL", "down", "agree"),
    ("BUY", "down", "against"),
    ("SELL", "up", "against"),
    ("BUY", "neutral", "neutral"),
    ("SELL", "neutral", "neutral"),
])
def test_build_record_htf_agreement(action, direction, expected):
    rec = build_record(_fake_result(action),
                       _fake_sig(action, _trend(direction)),
                       None, "forex", "EURUSD")
    htf = rec["context"]["htf"]
    assert htf == {"timeframe": "H1", "direction": direction,
                   "adx": pytest.approx(28.5), "trusted": True,
                   "agreement": expected}


@pytest.mark.parametrize("trend", [
    None,
    {"timeframe": "H1", "direction": "unknown", "adx": None,
     "trusted": False, "htf_adx_min": 20},
    {"timeframe": "H1", "direction": "up", "adx": 12.3,
     "trusted": False, "htf_adx_min": 20},
])
def test_build_record_htf_not_applied(trend):
    rec = build_record(_fake_result("BUY"), _fake_sig("BUY", trend),
                       None, "forex", "EURUSD")
    assert rec["context"]["htf"]["agreement"] == "not_applied"
    if trend is None:
        assert rec["context"]["htf"] == {
            "timeframe": None, "direction": None, "adx": None,
            "trusted": None, "agreement": "not_applied"}
    else:
        assert rec["context"]["htf"]["direction"] == \
            trend["direction"]


def test_build_record_without_htf_key_never_raises():
    sig = _fake_sig("BUY", None)
    del sig["htf_trend"]
    rec = build_record(_fake_result("BUY"), sig, None, "forex",
                       "EURUSD")
    assert rec["context"]["htf"]["agreement"] == "not_applied"
    # Khoa cu van nguyen ven.
    assert rec["context"]["rsi"] == pytest.approx(59.0)


# ---------------- backtest MTF ----------------

def _m15_uptrend_bars(n=200):
    closes = [100.0]
    for i in range(n - 1):
        closes.append(round(closes[-1] + (0.75 if i % 2 == 0 else -2 / 3),
                            6))
    return _bars(closes, step=900, t0=0)


def _h1_trend_bars(direction, n=110):
    # Bar H1 bat dau TRUOC cua so M15 (60 bar truoc) de trend da
    # tin cay ngay tu bar M15 dau tien.
    if direction == "up":
        closes = _up_closes(n, start=100.0, step=1.0)
    else:
        closes = _down_closes(n, start=300.0, step=1.0)
    return _bars(closes, step=3600, t0=-216000)


def test_backtest_mtf_downtrend_blocks_entries():
    m15 = _m15_uptrend_bars()
    h1_down = _h1_trend_bars("down")
    base = run_backtest("forex", 30, cfg=_cfg(), symbols=["EURUSD"],
                        bars_by_symbol={"EURUSD": m15})
    assert len(base["trades"]) > 0
    assert base["multitimeframe"]["enabled"] is False
    blocked = run_backtest(
        "forex", 30, cfg=_cfg(mtf=True), symbols=["EURUSD"],
        bars_by_symbol={"EURUSD": m15},
        trend_bars_by_symbol={"EURUSD": h1_down})
    assert blocked["multitimeframe"]["enabled"] is True
    assert blocked["multitimeframe"]["missing_trend_bars"] == []
    assert len(blocked["trades"]) == 0


def test_backtest_mtf_uptrend_allows_same_entries():
    m15 = _m15_uptrend_bars()
    h1_up = _h1_trend_bars("up")
    base = run_backtest("forex", 30, cfg=_cfg(), symbols=["EURUSD"],
                        bars_by_symbol={"EURUSD": m15})
    aligned = run_backtest(
        "forex", 30, cfg=_cfg(mtf=True), symbols=["EURUSD"],
        bars_by_symbol={"EURUSD": m15},
        trend_bars_by_symbol={"EURUSD": h1_up})
    assert len(aligned["trades"]) == len(base["trades"])
    assert [(t["entry"], t["exit"]) for t in aligned["trades"]] == \
        [(t["entry"], t["exit"]) for t in base["trades"]]
    assert "[HTF H1: trend UP" in aligned["trades"][0]["entry_reason"]


def test_backtest_mtf_missing_trend_bars_runs_m15_only(capsys):
    m15 = _m15_uptrend_bars()
    base = run_backtest("forex", 30, cfg=_cfg(), symbols=["EURUSD"],
                        bars_by_symbol={"EURUSD": m15})
    result = run_backtest("forex", 30, cfg=_cfg(mtf=True),
                          symbols=["EURUSD"],
                          bars_by_symbol={"EURUSD": m15})
    assert result["multitimeframe"]["missing_trend_bars"] == ["EURUSD"]
    assert len(result["trades"]) == len(base["trades"])
    assert "Canh bao MTF" in capsys.readouterr().out


def test_backtest_from_history_mtf(tmp_path):
    m15 = _m15_uptrend_bars()
    h1_down = _h1_trend_bars("down")
    with HistoryStore(tmp_path / "history.db") as store:
        store.upsert_bars("EURUSD", "M15", m15)
        store.upsert_bars("EURUSD", "H1", h1_down)
        blocked = run_backtest_from_history(
            "forex", _cfg(mtf=True), symbols=["EURUSD"], store=store)
    assert blocked["simulated"] is False
    assert blocked["multitimeframe"]["enabled"] is True
    assert len(blocked["trades"]) == 0
    # Thieu bar H1 trong kho -> M15-only + canh bao, lenh nhu cu.
    with HistoryStore(tmp_path / "history2.db") as store:
        store.upsert_bars("EURUSD", "M15", m15)
        result = run_backtest_from_history(
            "forex", _cfg(mtf=True), symbols=["EURUSD"], store=store)
    assert result["multitimeframe"]["missing_trend_bars"] == ["EURUSD"]
    base = run_backtest("forex", 30, cfg=_cfg(), symbols=["EURUSD"],
                        bars_by_symbol={"EURUSD": m15})
    assert len(result["trades"]) == len(base["trades"])


def test_compare_inherits_mtf_filter_when_trend_bars_given():
    m15 = _m15_uptrend_bars()
    h1_down = _h1_trend_bars("down")
    base = compare_strategies(
        "forex", ["default"], cfg=_cfg(), symbols=["EURUSD"],
        train_bars=40, test_bars=40, step_bars=40,
        bars_by_symbol={"EURUSD": m15})
    assert base["rows"][0]["oos_n_trades"] > 0
    filtered = compare_strategies(
        "forex", ["default"], cfg=_cfg(mtf=True), symbols=["EURUSD"],
        train_bars=40, test_bars=40, step_bars=40,
        bars_by_symbol={"EURUSD": m15},
        trend_bars_by_symbol={"EURUSD": h1_down})
    assert filtered["rows"][0]["oos_n_trades"] == 0
