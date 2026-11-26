"""Backtest placeholder: chay chien luoc tren du lieu MO PHONG.
Ket qua khong phai ket qua giao dich that."""
from .data.feeds import SimulatedFeed
from .strategies import STRATEGIES


def run_backtest(desk, days=30):
    feed = SimulatedFeed(desk)
    bars = feed.bars(days + 20)
    strat = STRATEGIES[desk]
    action, reason = strat.signal(bars)
    return (f"Backtest (MO PHONG) desk={desk}, days={days}, "
            f"strategy={strat.name}, tin hieu cuoi: {action} — {reason}. "
            f"Chua co P&L that; chi kiem tra chien luoc chay duoc.")
