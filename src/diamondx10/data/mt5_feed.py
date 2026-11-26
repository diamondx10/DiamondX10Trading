"""MT5Feed — lay du lieu thoi gian thuc tu MetaTrader 5 (Exness demo).

Chi dung cho tai khoan DEMO. MT5 terminal phai dang chay tren CUNG may
voi tool Python (thuong la may Windows / VPS Windows), vi goi
MetaTrader5 cua Python chi noi duoc voi terminal dang chay local.

Quy tac an toan:
- Khong bao gio ghi mat khau that vao repo, log hay research.
  Mat khau chi lay tu bien moi truong MT5_PASSWORD (mac dinh) hoac tu
  config.yaml local (file nay da gitignore, khong commit).
- Goí MetaTrader5 duoc import LAZY (chi khi can): neu chua cai,
  tool van chay binh thuong voi SimulatedFeed; chi lenh mt5-* moi bao
  loi ro rang "chua cai MetaTrader5".
- Khong tu dong tao lenh o day — file nay chi lay du lieu.
  Khop lenh demo nam o src/diamondx10/execution.py, co chan DEMO-ONLY.
"""
import os

from .feeds import DataFeed

# Khung thoi gian mac dinh cho bar: M15 (15 phut / nen).
DEFAULT_TIMEFRAME = "M15"


def load_mt5(mt5_module=None):
    """Tra ve module MetaTrader5. Cho phep truyen module gia vao de test.

    Neu khong truyen module va goi MetaTrader5 chua cai -> ImportError
    voi huong dan cu the, thay vi loi import kho hieu.
    """
    if mt5_module is not None:
        return mt5_module
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise ImportError(
            "Chua cai goi MetaTrader5. Cai tren may chay MT5 terminal "
            "(Windows): pip install MetaTrader5 — roi dang nhap tai "
            "khoan DEMO Exness tren MT5 terminal truoc khi chay tool."
        ) from exc
    return mt5


def _timeframe_const(mt5, name):
    """Lay hang TIMEFRAME_* cua MT5 theo ten, vd 'M15' -> TIMEFRAME_M15."""
    const = getattr(mt5, f"TIMEFRAME_{name}", None)
    if const is None:
        raise ValueError(f"Khung thoi gian MT5 khong hop le: {name!r} (vd: M1, M5, M15, H1, D1)")
    return const


def _rate_to_bar(rate):
    """Chuyen 1 nen MT5 ve dinh dang chung cua tool: {'time': int, 'close': float}.

    copy_rates_from_pos tra ve mang numpy co field 'time'/'close'
    (truy cap kieu dict), hoac object co thuoc tinh .time/.close
    (trong test dung dict don gian).
    """
    try:
        return {"time": int(rate["time"]), "close": float(rate["close"])}
    except (TypeError, KeyError, IndexError):
        pass
    try:
        return {"time": int(rate.time), "close": float(rate.close)}
    except AttributeError:
        pass
    # Tuple theo thu tu MT5: (time, open, high, low, close, tick_volume, spread, real_volume)
    return {"time": int(rate[0]), "close": float(rate[4])}


def check_symbols(mt5, symbols):
    """Kiem tra symbol nao co tren server MT5 demo dang noi.

    Tra ve dict {symbol: True/False}. Symbol khong co (vd CDNS co the
    khong co tren Exness MT5 demo) thi bao False — nguoi dung biet de
    doi symbol hoac doi nguon du lieu cho desk do, thay vi lenh loi
    am tham khi chay.
    """
    result = {}
    for symbol in symbols:
        info = mt5.symbol_info(symbol)
        result[symbol] = info is not None
    return result


class MT5Feed(DataFeed):
    """Feed du lieu thoi gian thuc qua MT5 terminal (demo).

    Parameters
    ----------
    symbol : str — vd 'EURUSD', 'XAUUSD', 'BTCUSD'.
    login : int | None — so tai khoan demo Exness (lay tu config.yaml local).
    password : str | None — mat khau demo; neu None thi doc bien moi
        truong MT5_PASSWORD (khuyen dung), khong ghi mat khau vao repo.
    server : str | None — ten server demo, vd 'Exness-MT5Trial7'
        (dien ten that vao config.yaml local).
    timeframe : str — khung nen, mac dinh 'M15'.
    mt5_module : module | None — chi dung de test (truyen module gia);
        neu None thi import MetaTrader5 that (lazy).
    """

    def __init__(self, symbol, login=None, password=None, server=None,
                 timeframe=DEFAULT_TIMEFRAME, mt5_module=None):
        if not symbol:
            raise ValueError("MT5Feed can 1 symbol, vd 'EURUSD'")
        self.symbol = symbol
        self.login = login
        self.server = server
        self.timeframe = timeframe
        self.mt5 = load_mt5(mt5_module)
        password = password or os.environ.get("MT5_PASSWORD")
        if not self.mt5.initialize():
            raise ConnectionError(
                "Khong ket noi duoc MT5 terminal. Mo MT5 terminal len, "
                f"dang nhap tai khoan DEMO truoc, roi chay lai. Loi MT5: "
                f"{self.mt5.last_error()}"
            )
        if login is not None:
            ok = self.mt5.login(int(login), password=password, server=server)
            if not ok:
                raise ConnectionError(
                    "Dang nhap MT5 demo that bai (sai login / mat khau / "
                    f"server {server!r}). Loi MT5: {self.mt5.last_error()}"
                )
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(
                f"Symbol {symbol!r} khong co tren server MT5 demo dang noi "
                f"(server={server!r}). Kiem tra lai ten symbol tren MT5 "
                "terminal, hoac doi symbol cho desk nay."
            )
        if not self.mt5.symbol_select(symbol, True):
            raise ConnectionError(f"Khong chon duoc symbol {symbol!r} tren MT5.")

    def bars(self, n: int = 60):
        """n bar gan nhat, dinh dang [{'time': int, 'close': float}]."""
        tf = _timeframe_const(self.mt5, self.timeframe)
        rates = self.mt5.copy_rates_from_pos(self.symbol, tf, 0, n)
        if rates is None or len(rates) == 0:
            raise ConnectionError(
                f"MT5 khong tra ve bar nao cho {self.symbol!r} "
                f"(server={self.server!r}). Loi MT5: {self.mt5.last_error()}"
            )
        return [_rate_to_bar(r) for r in rates]

    def latest_price(self, symbol=None):
        """Gia moi nhat (bid) cua symbol; mac dinh la symbol cua feed."""
        symbol = symbol or self.symbol
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ConnectionError(
                f"MT5 khong tra ve tick cho {symbol!r}. "
                f"Loi MT5: {self.mt5.last_error()}"
            )
        try:
            return float(tick["bid"])
        except (TypeError, KeyError, IndexError):
            return float(tick.bid)

    def account_info(self):
        """Thong tin tai khoan dang dang nhap (de execution.py kiem tra demo)."""
        return self.mt5.account_info()

    def close(self):
        """Ngat ket noi MT5 terminal."""
        self.mt5.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
