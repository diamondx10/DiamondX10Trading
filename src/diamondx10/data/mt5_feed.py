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
from pathlib import Path

from .feeds import DataFeed

# Khung thoi gian mac dinh cho bar: M15 (15 phut / nen).
DEFAULT_TIMEFRAME = "M15"

# Duong dan terminal MT5 da biet, theo thu tu uu tien (duong dan TUONG
# DOI so voi 1 thu muc goc Program Files). Duong dan cua user dung dau:
# C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe
KNOWN_TERMINAL_PATHS = (
    "MetaTrader 5 EXNESS/terminal64.exe",
    "MetaTrader 5/terminal64.exe",
)

# Bien moi truong Windows chua cac thu muc goc de tim terminal,
# theo thu tu uu tien.
_TERMINAL_ROOT_ENVS = (
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "LOCALAPPDATA",
)

# Thu tu uu tien khi quet 1 cap: ten thu muc cha chua "Exness" truoc,
# roi "MetaTrader", roi "MT5".
_SCAN_KEYWORD_RANKS = (("exness", 0), ("metatrader", 1), ("mt5", 2))

# Bien moi truong ghi de duong dan terminal (uu tien cao nhat,
# xem resolve_mt5_terminal_path).
TERMINAL_PATH_ENV = "MT5_TERMINAL_PATH"


def _is_windows():
    """True tren Windows. Doc os.name LUC GOI (khong doc luc import)
    de test co the gia lap Windows bang monkeypatch ham nay.

    (Khong the gia lap bang monkeypatch os.name="nt": pathlib khoa
    WindowsPath.__new__ theo os.name LUC IMPORT pathlib, nen tren
    Linux ma os.name bi doi thanh "nt" thi moi phep Path / "con"
    deu raise NotImplementedError.)
    """
    return os.name == "nt"


def _terminal_roots(search_roots=None):
    """Cac thu muc goc de tim terminal64.exe (da loai trung, giu thu tu).

    search_roots: truyen vao de test (list duong dan); None thi doc tu
    bien moi truong Windows (ProgramFiles, ProgramFiles(x86),
    ProgramW6432, LOCALAPPDATA).
    """
    if search_roots is not None:
        roots = [Path(r) for r in search_roots]
    else:
        roots = []
        for env in _TERMINAL_ROOT_ENVS:
            base = os.environ.get(env)
            if base:
                roots.append(Path(base))
    uniq, seen = [], set()
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(root)
    return uniq


def find_mt5_terminal(search_roots=None):
    """Tim file terminal64.exe cua MT5 tren Windows.

    Thu tu uu tien: (1) cac duong dan da biet trong
    KNOWN_TERMINAL_PATHS — truoc het "MetaTrader 5 EXNESS" (duong dan
    cua user: C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe),
    roi "MetaTrader 5" — o moi thu muc goc theo thu tu ProgramFiles,
    ProgramFiles(x86), ProgramW6432, LOCALAPPDATA; (2) quet 1 cap
    duoi moi thu muc goc tim */terminal64.exe, uu tien thu muc cha
    co ten chua "Exness", roi "MetaTrader", roi "MT5".

    Tra Path neu tim thay, khong thi None. Tren he dieu hanh khac
    Windows luon tra None. Khong bao gio raise:
    loi doc 1 thu muc goc (OSError) thi bo qua thu muc do.
    Ham nay CHI quet — khong doc bien moi truong MT5_TERMINAL_PATH
    hay config (xem resolve_mt5_terminal_path).
    """
    if not _is_windows():
        return None
    roots = _terminal_roots(search_roots)
    for base in roots:
        for rel in KNOWN_TERMINAL_PATHS:
            cand = base / rel
            try:
                if cand.is_file():
                    return cand
            except OSError:
                continue
    best, best_rank = None, None
    for base in roots:
        try:
            children = list(base.glob("*/terminal64.exe"))
        except OSError:
            continue
        for path in children:
            name = path.parent.name.lower()
            rank = next((r for kw, r in _SCAN_KEYWORD_RANKS if kw in name),
                        None)
            if rank is None:
                continue
            if best_rank is None or rank < best_rank:
                best, best_rank = path, rank
                if rank == 0:
                    return best
    return best


def resolve_mt5_terminal_path(cfg=None, search_roots=None):
    """Duong dan terminal MT5 se dung, theo thu tu uu tien.

    Day la LOP doc bien moi truong / config (find_mt5_terminal chi
    quet, khong doc 2 thu nay):
    (1) bien moi truong MT5_TERMINAL_PATH, neu dat va file ton tai;
    (2) mt5.terminal_path trong config (dict cfg), neu dat va file
    ton tai; (3) auto-scan find_mt5_terminal().
    Ghi de dat nhung file khong ton tai thi roi xuong muc sau (khong
    bao loi o day — neu duong dan da chon ma initialize(path=...) loi
    thi MT5Feed bao loi ro rang, khong tu doi sang terminal mac dinh).

    Tra Path neu tim thay, khong thi None.
    """
    override = (os.environ.get(TERMINAL_PATH_ENV) or "").strip()
    if not override:
        mt5_cfg = (cfg or {}).get("mt5") or {}
        if isinstance(mt5_cfg, dict):
            override = str(mt5_cfg.get("terminal_path") or "").strip()
    if override:
        cand = Path(override)
        try:
            if cand.is_file():
                return cand
        except OSError:
            pass
    return find_mt5_terminal(search_roots=search_roots)


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


def _rate_to_bar(rate, include_volume=False):
    """Chuyen 1 nen MT5 ve dinh dang OHLC chung cua tool:

    {'time': int, 'open': float, 'high': float, 'low': float,
     'close': float} (+ 'volume' neu include_volume=True).

    Ho tro 3 kieu truy cap ma copy_rates_from_pos co the tra ve:
    dict (rate["open"], ... — kieu numpy structured array), attribute
    (rate.open, ...), va tuple theo thu tu MT5
    (time, open, high, low, close, tick_volume, spread, real_volume).
    Mac dinh KHONG them 'volume' de cac consumer cu (chi dung OHLC)
    khong doi hanh vi; kho lich su (history.py) thi can volume nen
    truyen include_volume=True.
    """
    try:
        bar = {"time": int(rate["time"]),
               "open": float(rate["open"]),
               "high": float(rate["high"]),
               "low": float(rate["low"]),
               "close": float(rate["close"])}
        if include_volume:
            bar["volume"] = float(rate.get("tick_volume") or 0.0)
        return bar
    except (TypeError, KeyError, IndexError, AttributeError):
        pass
    try:
        bar = {"time": int(rate.time),
               "open": float(rate.open),
               "high": float(rate.high),
               "low": float(rate.low),
               "close": float(rate.close)}
        if include_volume:
            bar["volume"] = float(getattr(rate, "tick_volume", 0.0) or 0.0)
        return bar
    except AttributeError:
        pass
    # Tuple theo thu tu MT5: (time, open, high, low, close, tick_volume, spread, real_volume)
    bar = {"time": int(rate[0]),
           "open": float(rate[1]),
           "high": float(rate[2]),
           "low": float(rate[3]),
           "close": float(rate[4])}
    if include_volume:
        bar["volume"] = float(rate[5]) if len(rate) > 5 else 0.0
    return bar


def resolve_mt5_symbol(symbol, server, suffix=None):
    """Ten symbol tren broker tu ten chuan (canonical) + server.

    Tren server Exness TRIAL moi symbol deu co hau to 'm'
    (EURUSD -> EURUSDm); tren server REAL thi khong co hau to.
    Phan biet Trial/Real bang TEN SERVER (chua "Trial"/"Real",
    khong phan biet hoa/thuong).

    suffix: neu dat ro (khac None va khac "auto") thi dung luon
    (vd suffix="m" ep them 'm', suffix="" ep khong hau to);
    None hoac "auto" thi suy ra tu ten server. Server la/unknown
    (None hoac khong chua "Trial") thi tra ten goc.
    """
    if suffix is not None and suffix != "auto":
        return symbol + str(suffix)
    if server is not None and "trial" in str(server).lower():
        return symbol + "m"
    return symbol


def build_symbol_map(mt5, symbols, server, suffix=None):
    """Map ten chuan -> ten tren broker ({canonical: broker | None}).

    Voi moi symbol thu cac ung vien theo thu tu
    [resolve_mt5_symbol(s, server, suffix), s]; ung vien dau tien
    ma mt5.symbol_info() tra ve khong-None thi thang. Chi kiem tra
    su ton tai (khong goi symbol_select o day). Neu ca 2 ung vien
    deu khong co thi gia tri la None. Neu mt5 khong co symbol_info
    (module gia toi gian) thi khong kiem tra duoc — tra ten chuan
    de giu hanh vi cu.
    """
    symbol_info = getattr(mt5, "symbol_info", None)
    result = {}
    for symbol in symbols:
        mapped = resolve_mt5_symbol(symbol, server, suffix)
        if symbol_info is None:
            result[symbol] = symbol
            continue
        found = None
        candidates = [mapped] if mapped == symbol else [mapped, symbol]
        for candidate in candidates:
            try:
                info = symbol_info(candidate)
            except Exception:  # noqa: BLE001 — coi nhu khong co
                info = None
            if info is not None:
                found = candidate
                break
        result[symbol] = found
    return result


def check_symbols(mt5, symbols, server=None, suffix=None):
    """Kiem tra symbol nao co tren server MT5 demo dang noi.

    Tra ve dict {symbol: True/False} khoa theo TEN CHUAN. Symbol khong co
    (vd CDNS co the khong co tren Exness MT5 demo) thi bao False — nguoi
    dung biet de doi symbol hoac doi nguon du lieu cho desk do, thay vi
    lenh loi am tham khi chay.

    Khi truyen server/suffix: kiem tra TEN TREN BROKER
    (resolve_mt5_symbol) thay vi ten chuan. Khi khong truyen ca 2 thi
    giu hanh vi cu (kiem tra ten chuan).
    """
    result = {}
    for symbol in symbols:
        if server is None and suffix is None:
            name = symbol
        else:
            name = resolve_mt5_symbol(symbol, server, suffix)
        info = mt5.symbol_info(name)
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
    path : str | Path | None — duong dan file terminal64.exe se noi
        toi. Neu None thi tu dong tim: bien moi truong
        MT5_TERMINAL_PATH, roi auto-scan (find_mt5_terminal). Neu
        duong dan da chon ma initialize(path=...) that bai thi BAO LOI
        chu KHONG tu doi sang initialize() khong duong dan (co the
        dinh nham terminal cua broker khac).
    symbol_suffix : str | None — hau to symbol ep buoc, vd "m" hoac "".
        None/"auto" (mac dinh) thi suy ra tu ten server: server Trial
        -> 'm', server Real/khac -> khong hau to. Ten chuan (self.symbol)
        luon giu nguyen; ten tren broker nam o self.symbol_map /
        broker_symbol().
    """

    def __init__(self, symbol, login=None, password=None, server=None,
                 timeframe=DEFAULT_TIMEFRAME, mt5_module=None, path=None,
                 symbol_suffix=None):
        if not symbol:
            raise ValueError("MT5Feed can 1 symbol, vd 'EURUSD'")
        self.symbol = symbol
        self.login = login
        self.server = server
        self.symbol_suffix = symbol_suffix
        self.timeframe = timeframe
        self.mt5 = load_mt5(mt5_module)
        password = password or os.environ.get("MT5_PASSWORD")
        if path is None:
            resolved = resolve_mt5_terminal_path()
            path = resolved
        self.terminal_path = Path(path) if path is not None else None
        if self.terminal_path is not None:
            try:
                ok = self.mt5.initialize(path=str(self.terminal_path))
            except Exception as exc:
                raise ConnectionError(
                    "Khong ket noi duoc MT5 terminal o duong dan da chon "
                    f"{self.terminal_path} (mt5.initialize(path=...) loi: "
                    f"{exc}). KHONG tu dong thu terminal mac dinh (co the "
                    "nham broker). Xoa dong terminal_path trong config.yaml "
                    "local hoac chay lai quickstart.py de quet lai terminal, "
                    "roi thu lai."
                ) from exc
            if not ok:
                raise ConnectionError(
                    "Khong ket noi duoc MT5 terminal o duong dan da chon "
                    f"{self.terminal_path} — terminal chua mo, hoac duong "
                    "dan sai (co the la terminal cua broker khac). KHONG tu "
                    "dong thu terminal mac dinh (co the nham broker). Xoa "
                    "dong terminal_path trong config.yaml local hoac chay "
                    "lai quickstart.py de quet lai terminal, roi thu lai. "
                    f"Loi MT5: {self.mt5.last_error()}"
                )
        elif not self.mt5.initialize():
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
        # Server thuc te dang dang nhap (de suy hau to symbol 'm' tren
        # Trial): doc tu account_info(), roi xuong server truyen vao
        # neu khong doc duoc.
        effective_server = server
        try:
            _acct = (self.mt5.account_info()
                     if hasattr(self.mt5, "account_info") else None)
        except Exception:  # noqa: BLE001 — roi xuong server truyen vao
            _acct = None
        if _acct is not None:
            _acct_server = getattr(_acct, "server", None)
            if _acct_server:
                effective_server = _acct_server
        self.server = effective_server
        # Ten tren broker (vd EURUSDm tren Trial): thu ten co hau to
        # truoc, roi xuong ten chuan neu broker khong co ten do.
        self.symbol_map = build_symbol_map(
            self.mt5, [symbol], effective_server, symbol_suffix)
        broker_symbol = self.symbol_map.get(symbol)
        if broker_symbol is None:
            tried = resolve_mt5_symbol(symbol, effective_server,
                                       symbol_suffix)
            tried_txt = (f"{tried!r} va {symbol!r}" if tried != symbol
                         else f"{tried!r}")
            raise ValueError(
                f"Symbol {symbol!r} khong co tren server MT5 demo dang noi "
                f"(da thu {tried_txt}, "
                f"server={effective_server!r}). Kiem tra lai ten symbol "
                "tren MT5 terminal, hoac doi symbol cho desk nay."
            )
        info = self.mt5.symbol_info(broker_symbol)
        if info is None:
            tried_txt = (f"{broker_symbol!r} va {symbol!r}"
                         if broker_symbol != symbol
                         else f"{broker_symbol!r}")
            raise ValueError(
                f"Symbol {symbol!r} khong co tren server MT5 demo dang noi "
                f"(da thu {tried_txt}, "
                f"server={effective_server!r}). Kiem tra lai ten symbol "
                "tren MT5 terminal, hoac doi symbol cho desk nay."
            )
        if not self.mt5.symbol_select(broker_symbol, True):
            raise ConnectionError(
                f"Khong chon duoc symbol {broker_symbol!r} tren MT5.")

    def broker_symbol(self, canonical):
        """Ten tren broker cua 1 symbol chuan (vd 'EURUSD' -> 'EURUSDm'
        tren server Trial). Giai quyet + cache theo nhu cau cho cac
        symbol khac symbol cua feed; tra None neu broker khong co
        ca ten co hau to lan ten chuan. self.symbol van giu ten chuan.
        """
        if canonical in self.symbol_map:
            return self.symbol_map[canonical]
        mapped = build_symbol_map(self.mt5, [canonical], self.server,
                                  self.symbol_suffix).get(canonical)
        self.symbol_map[canonical] = mapped
        return mapped

    def bars(self, n: int = 60):
        """n bar gan nhat, dinh dang OHLC: [{'time': int, 'open': float,
        'high': float, 'low': float, 'close': float}]."""
        tf = _timeframe_const(self.mt5, self.timeframe)
        broker = self.broker_symbol(self.symbol) or self.symbol
        rates = self.mt5.copy_rates_from_pos(broker, tf, 0, n)
        if rates is None or len(rates) == 0:
            raise ConnectionError(
                f"MT5 khong tra ve bar nao cho {self.symbol!r} "
                f"(server={self.server!r}). Loi MT5: {self.mt5.last_error()}"
            )
        return [_rate_to_bar(r) for r in rates]

    def bars_range(self, timeframe=None, start=None, end=None):
        """Bar trong 1 khoang thoi gian (dung cho backfill — Phase A).

        timeframe: ten khung nen (mac dinh khung cua feed); start/end:
        datetime (naive hieu la UTC). Tra list bar OHLC + volume,
        theo thu tu thoi gian tang dan. Dung copy_rates_range cua MT5.
        """
        from datetime import timezone as _tz

        tf_name = timeframe or self.timeframe
        tf = _timeframe_const(self.mt5, tf_name)
        if start is None or end is None:
            raise ValueError("bars_range can ca start va end (datetime)")
        if start.tzinfo is None:
            start = start.replace(tzinfo=_tz.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=_tz.utc)
        if end <= start:
            raise ValueError("bars_range: end phai sau start")
        broker = self.broker_symbol(self.symbol) or self.symbol
        rates = self.mt5.copy_rates_range(broker, tf, start, end)
        if rates is None:
            raise ConnectionError(
                f"MT5 khong tra ve bar nao cho {self.symbol!r} "
                f"({tf_name}, {start}..{end}). "
                f"Loi MT5: {self.mt5.last_error()}"
            )
        bars = [_rate_to_bar(r, include_volume=True) for r in rates]
        return sorted(bars, key=lambda b: b["time"])

    def bars_for_days(self, timeframe=None, days=30, end=None):
        """Bar trong N ngay gan nhat (tien ich cho backfill).

        end: datetime ket thuc (mac dinh: bay gio, UTC). Tra list bar
        OHLC + volume theo thu tu thoi gian.
        """
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz

        end = end or _dt.now(_tz.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=_tz.utc)
        start = end - _td(days=int(days))
        return self.bars_range(timeframe, start, end)

    def latest_price(self, symbol=None):
        """Gia moi nhat (bid) cua symbol; mac dinh la symbol cua feed."""
        symbol = symbol or self.symbol
        broker = self.broker_symbol(symbol) or symbol
        tick = self.mt5.symbol_info_tick(broker)
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
