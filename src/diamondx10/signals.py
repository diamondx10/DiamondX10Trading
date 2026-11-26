"""Sinh tin hieu cho 1 desk tu feed hien tai."""
from .strategies import STRATEGIES


def generate_signals(desk, bars):
    strat = STRATEGIES[desk]
    action, reason = strat.signal(bars)
    return {"desk": desk, "strategy": strat.name, "action": action, "reason": reason}
