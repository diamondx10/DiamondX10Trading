"""Smoke test: khong can du lieu that, khong can mang."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.data.feeds import SimulatedFeed
from diamondx10.models.quant import rsi, sma
from diamondx10.portfolio import Portfolio
from diamondx10.signals import generate_signals


def test_sma_and_signals():
    bars = SimulatedFeed("forex").bars(60)
    assert sma([b["close"] for b in bars], 5) is not None
    assert rsi([b["close"] for b in bars]) is not None
    s = generate_signals("forex", bars)
    assert s["action"] in ("BUY", "SELL", "HOLD")


def test_portfolio_total_is_2000():
    pf = Portfolio.from_config({"fund": {"desks": {
        "forex": {"manager": "Yuling Pan", "capital_usd": 500},
        "us_securities": {"manager": "Kathy", "capital_usd": 500},
        "xauusd": {"manager": "Yumi", "capital_usd": 500},
        "crypto": {"manager": "Rich", "capital_usd": 500}}}})
    assert pf.total_capital_usd == 2000
