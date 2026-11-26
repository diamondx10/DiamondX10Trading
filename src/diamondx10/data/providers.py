"""Noi provider du lieu thoi gian that vao day.

Vi du (chua cai dat — dien provider cua ban):
    class RealTimeFeed(DataFeed):
        def __init__(self, api_key): ...
        def bars(self, n=60): goi API that, tra ve bar that
        def latest_price(self, symbol): goi API that

Quy tac:
- API key chi doc tu bien moi truong / config.yaml (khong commit).
- Khong bao gio ghi key that vao repo, log hay research.
- Moi provider moi la 1 class rieng ke thua DataFeed trong file nay.
"""
from .feeds import DataFeed


class RealTimeFeed(DataFeed):
    """Placeholder — chua noi provider that. Dung SimulatedFeed cho den
    khi ban cau hinh provider trong config.yaml."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Chua cau hinh provider du lieu thoi gian thuc. "
            "Xem config.example.yaml va src/diamondx10/data/providers.py."
        )

    def bars(self, n: int = 60):
        raise NotImplementedError

    def latest_price(self, symbol: str) -> float:
        raise NotImplementedError
