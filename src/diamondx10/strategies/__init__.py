"""Dang ky chien luoc theo desk. Yuling nghien cuu ly thuyet,
LJ/Kel cai dat thanh code o day."""
from .base import Strategy
from .crypto import CryptoMomentum
from .forex import ForexTrend
from .us_securities import USSecTrend
from .xauusd import XauusdTrend

STRATEGIES = {
    "forex": ForexTrend(),
    "us_securities": USSecTrend(),
    "xauusd": XauusdTrend(),
    "crypto": CryptoMomentum(),
}
__all__ = ["Strategy", "STRATEGIES"]
