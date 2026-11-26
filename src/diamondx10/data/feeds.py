"""Data feed interface. Provider that chi tra du lieu THOI GIAN THUC
duoc cai dat bang cach ke thua DataFeed (xem providers.py).
SimulatedFeed chi dung cho demo / test — gia duoc sinh ngau nhien,
KHONG phai gia thi truong that."""
import math
import random
from abc import ABC, abstractmethod


class DataFeed(ABC):
    """Interface ma moi provider du lieu thoi gian thuc phai cai dat."""

    @abstractmethod
    def bars(self, n: int = 60):
        """Tra ve n bar gan nhat: list[{'time': int, 'close': float}]."""

    @abstractmethod
    def latest_price(self, symbol: str) -> float:
        """Gia moi nhat cua 1 symbol."""


class SimulatedFeed(DataFeed):
    """Feed mo phong dung cho demo/backtest. Seed theo desk de lap lai duoc."""

    def __init__(self, desk: str = "forex", seed: int = 42):
        self.desk = desk
        self._rng = random.Random(f"{desk}-{seed}")
        self._bars = self._make_bars(500)

    def _make_bars(self, n):
        bars, price = [], 100.0
        for i in range(n):
            price *= 1 + self._rng.gauss(0, 0.005)
            bars.append({"time": i, "close": round(price, 4)})
        return bars

    def bars(self, n: int = 60):
        return list(self._bars[-n:])

    def latest_price(self, symbol: str) -> float:
        return self._bars[-1]["close"]


# providers.py — noi provider that vao day (placeholder, khong co key that).
