"""Test context chi bao (RSI/SMA/ADX) chay tu Strategy.signal() sang
generate_signals() roi vao outcomes.build_record.

Ly do: _soft_context() tinh RSI/SMA/ADX trong Strategy nhung
generate_signals() truoc day khong mang cac gia tri do ra ngoai, nen
ban ghi outcome tu duong live co rsi/adx = None va ta-review khong
chia duoc theo bien RSI / regime ADX. Fix: Strategy luu last_context
(chi tinh 1 lan, reset khi HOLD dung som) va generate_signals gan
vao khoa "context".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diamondx10.outcomes import build_record
from diamondx10.signals import generate_signals
from diamondx10.strategies.base import Strategy
from test_soft_rules import bars_from_closes, buy_bars


def test_generate_signals_carries_indicator_context():
    sig = generate_signals("forex", buy_bars())
    assert sig["action"] == "BUY"
    ctx = sig["context"]
    assert ctx["rsi"] is not None
    assert 0 <= ctx["rsi"] <= 100
    assert ctx["sma_fast"] is not None and ctx["sma_slow"] is not None
    assert ctx["sma_fast"] > ctx["sma_slow"]
    assert ctx["adx"] is not None
    assert ctx["atr"] is not None


def test_build_record_reads_context_from_live_signal():
    sig = generate_signals("forex", buy_bars())
    result = {"status": "TRADED", "action": "BUY", "price": 103.0,
              "sl": 101.0, "tp": 107.0, "volume": 0.01,
              "risk_usd": 10.0, "manager": "Yuling",
              "time": "2026-11-27T00:00:00Z"}
    rec = build_record(result, sig, None, "forex", "EURUSD")
    assert rec["context"]["rsi"] is not None
    assert rec["context"]["adx"] is not None
    assert rec["context"]["sma_relation"] == "fast>slow"
    assert rec["context"]["atr"] is not None


def test_hold_carries_no_stale_context():
    strat = Strategy()
    assert strat.signal(buy_bars())[0] == "BUY"
    assert strat.last_context is not None
    # HOLD dung som (chua du du lieu) — khong duoc mang context cu.
    assert strat.signal(bars_from_closes([100.0] * 5))[0] == "HOLD"
    assert strat.last_context is None
    sig = generate_signals("forex", bars_from_closes([100.0] * 5))
    assert sig["action"] == "HOLD"
    assert sig["context"] == {}
