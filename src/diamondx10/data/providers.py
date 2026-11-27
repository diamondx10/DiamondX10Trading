"""Noi provider du lieu thoi gian that vao day.

Provider hien co:
- 'simulated': SimulatedFeed trong feeds.py (mac dinh, dung cho demo/test).
- 'mt5': MT5Feed trong mt5_feed.py — lay du lieu thoi gian thuc tu
  MT5 terminal (Exness DEMO). Xem docs/mt5-demo.md.

Quy tac:
- Mat khau / API key chi doc tu bien moi truong / config.yaml local
  (khong commit). Khong bao gio ghi key that vao repo, log hay research.
- Moi provider moi la 1 class rieng ke thua DataFeed.
"""
import os

from .feeds import DataFeed, SimulatedFeed


def build_feed(cfg, desk, symbol=None, mt5_module=None):
    """Tao feed theo config: provider 'simulated' (mac dinh) hoac 'mt5'.

    symbol: neu None thi lay symbol dau tien cua desk trong
    cfg['data']['symbols'].
    """
    provider = str((cfg or {}).get("data", {}).get("provider", "simulated")).lower()
    if provider == "simulated":
        return SimulatedFeed(desk)
    if provider == "mt5":
        from .mt5_feed import MT5Feed

        mt5_cfg = (cfg or {}).get("mt5") or {}
        if symbol is None:
            symbols = (cfg or {}).get("data", {}).get("symbols", {}).get(desk) or []
            if not symbols:
                raise ValueError(
                    f"Chua cau hinh symbol cho desk {desk!r} trong "
                    "config.yaml (data.symbols)."
                )
            symbol = symbols[0]
        password_env = mt5_cfg.get("password_env", "MT5_PASSWORD")
        # Mat khau uu tien bien moi truong; chi doc tu config.yaml local
        # (file da gitignore) neu bien moi truong khong co — KHONG ghi
        # mat khau vao config.example.yaml hay bat ky file nao commit len repo.
        password = os.environ.get(password_env) if password_env else None
        password = password or mt5_cfg.get("password")
        return MT5Feed(
            symbol,
            login=mt5_cfg.get("login"),
            password=password,
            server=mt5_cfg.get("server"),
            timeframe=mt5_cfg.get("timeframe", "M15"),
            mt5_module=mt5_module,
            # Duong dan terminal trong config (mt5.terminal_path);
            # de trong (None) thi MT5Feed tu tim: bien moi truong
            # MT5_TERMINAL_PATH roi auto-scan (xem mt5_feed.py).
            path=mt5_cfg.get("terminal_path") or None,
            # Hau to symbol tren broker ("m" tren server Trial):
            # "auto" (mac dinh) thi suy ra tu ten server.
            symbol_suffix=mt5_cfg.get("symbol_suffix", "auto"),
        )
    raise ValueError(
        f"Provider du lieu khong biet: {provider!r} "
        "(chon 'simulated' hoac 'mt5' trong config.yaml)."
    )


class RealTimeFeed(DataFeed):
    """Feed thoi gian thuc — hien tai la MT5Feed khi provider='mt5'.

    Giunguyen ten class cu de code cu khong vo: RealTimeFeed(symbol, ...)
    se tao MT5Feed. Neu provider khong phai 'mt5' thi bao loi ro rang
    thay vi NotImplementedError chung chung.
    """

    def __init__(self, symbol=None, cfg=None, mt5_module=None, **kwargs):
        cfg = cfg or {"data": {"provider": "mt5"}, "mt5": {}}
        if str(cfg.get("data", {}).get("provider", "")).lower() != "mt5":
            raise NotImplementedError(
                "RealTimeFeed hien chi ho tro provider 'mt5' (Exness demo). "
                "Dat data.provider='mt5' trong config.yaml, xem docs/mt5-demo.md. "
                "Neu chua co MT5, dung SimulatedFeed (provider='simulated')."
            )
        self._feed = build_feed(cfg, kwargs.pop("desk", "forex"),
                                symbol=symbol, mt5_module=mt5_module)
        self.symbol = self._feed.symbol

    def bars(self, n: int = 60):
        return self._feed.bars(n)

    def latest_price(self, symbol: str):
        return self._feed.latest_price(symbol)

    def close(self):
        self._feed.close()
