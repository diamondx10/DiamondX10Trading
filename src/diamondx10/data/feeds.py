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
        """Tra ve n bar gan nhat, dinh dang OHLC day du:

        list[{'time': int, 'open': float, 'high': float,
              'low': float, 'close': float}]

        'time' la timestamp (giay, epoch) cua bar; 'close' la gia dong
        cua — cac consumer cu chi dung 'close' van chay nhu truoc.
        Bat buoc: high >= max(open, close), low <= min(open, close),
        'time' tang dan theo thu tu bar.
        """

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
            open_price = price
            price *= 1 + self._rng.gauss(0, 0.005)
            close = round(price, 4)
            # High/low suy ra xac dinh tu open/close (dung RNG da seed
            # nen cung desk+seed cho ra cung bar): high >= max(open,
            # close), low <= min(open, close).
            half_range = (abs(close - open_price)
                          + abs(self._rng.gauss(0, 0.002)) * open_price) / 2
            high = round(max(open_price, close) + half_range, 4)
            low = round(min(open_price, close) - half_range, 4)
            bars.append({"time": i, "open": round(open_price, 4),
                         "high": high, "low": low, "close": close})
        return bars

    def bars(self, n: int = 60):
        return list(self._bars[-n:])

    def latest_price(self, symbol: str) -> float:
        return self._bars[-1]["close"]


# providers.py — noi provider that vao day (placeholder, khong co key that).
