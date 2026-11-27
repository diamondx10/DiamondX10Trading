"""Test SimulatedFeed OHLC bars — khong can du lieu that, khong can mang."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.data.feeds import SimulatedFeed


def _check_ohlc_invariants(bars):
    assert bars, "feed phai tra ve it nhat 1 bar"
    times = [b["time"] for b in bars]
    assert times == sorted(times) and len(set(times)) == len(times), \
        "time phai tang dan nghiem ngat"
    for b in bars:
        assert set(b) == {"time", "open", "high", "low", "close"}
        assert isinstance(b["time"], int)
        assert all(isinstance(b[k], float) for k in
                   ("open", "high", "low", "close"))
        assert b["high"] >= max(b["open"], b["close"])
        assert b["low"] <= min(b["open"], b["close"])


def test_simulated_bars_are_ohlc():
    bars = SimulatedFeed("forex").bars(60)
    assert len(bars) == 60
    _check_ohlc_invariants(bars)


def test_simulated_open_is_previous_close():
    bars = SimulatedFeed("forex").bars(60)
    for prev, cur in zip(bars, bars[1:]):
        assert cur["open"] == prev["close"]


def test_simulated_feed_deterministic_same_desk_seed():
    a = SimulatedFeed("forex", seed=42).bars(100)
    b = SimulatedFeed("forex", seed=42).bars(100)
    assert a == b
    # Desk khac / seed khac thi bar khac.
    assert SimulatedFeed("crypto", seed=42).bars(100) != a
    assert SimulatedFeed("forex", seed=7).bars(100) != a


def test_simulated_latest_price_is_last_close():
    feed = SimulatedFeed("xauusd")
    assert feed.latest_price("XAUUSD") == feed.bars(1)[-1]["close"]
    assert feed.latest_price("XAUUSD") == feed.bars(60)[-1]["close"]
