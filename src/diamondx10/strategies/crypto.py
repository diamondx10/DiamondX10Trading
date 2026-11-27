"""Crypto — Rich phu trach (dong luong)."""
from .base import Strategy


class CryptoMomentum(Strategy):
    name = "CryptoMomentum (Rich — Crypto)"
    desk = "crypto"
    # Crypto bien dong manh hon: stop va trailing rong hon (Phase 0, Q2).
    DESK_OVERRIDES = {"atr_sl_mult": 2.0, "trail_mult": 2.0}
