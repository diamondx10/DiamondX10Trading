"""Test hau to symbol 'm' tren server Exness TRIAL (dx10 suffix fix).

Tren server TRIAL moi symbol deu co hau to 'm' (EURUSD -> EURUSDm);
tren server REAL thi khong co hau to. Phan biet bang TEN SERVER.
Chi dung MT5 GIA, khong can terminal that, khong co credential that
(chat_id / login trong file nay deu la so gia theo quy uoc repo).
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions, killswitch
from diamondx10.config import load_config
from diamondx10.data.mt5_feed import (
    MT5Feed,
    build_symbol_map,
    check_symbols,
    resolve_mt5_symbol,
)
from diamondx10.data.providers import build_feed
from diamondx10.execution import (
    check_margin,
    check_symbols_available,
    place_demo_order,
)
from diamondx10.listener import _latest_price, place_pending_order
from diamondx10.live import process_symbol
from diamondx10.risk import DrawdownGuard

ALL_SYMBOLS = ["EURUSD", "XAUUSD", "BTCUSD", "ETHUSD", "BNBUSD",
               "AMD", "CDNS", "SNPS", "INTC", "NVDA"]
TRIAL_SERVER = "Exness-MT5Trial7"
REAL_SERVER = "Exness-MT5Real1"
DEMO_CFG = {"mt5": {"demo_only": True}, "data": {"provider": "mt5"}}
LOGIN = 987654321  # so gia theo quy uoc repo, khong phai login that


class FakeMT5Suffix:
    """MT5 gia: chi co cac symbol trong `existing`, ghi lai ten symbol
    duoc dung o moi cuoc goi (de kiem tra ten tren broker)."""

    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, existing, server=TRIAL_SERVER, trade_mode=0,
                 bid=101.5):
        self._existing = set(existing)
        self._server = server
        self._trade_mode = trade_mode
        self._bid = bid
        self.sent_orders = []
        self.checked = []
        self.selected = []
        self.tick_symbols = []
        self.rate_symbols = []
        self._rates = [{"time": 1700000000 + i * 900,
                        "open": 99.5 + i, "high": 100.5 + i,
                        "low": 99.0 + i, "close": 100.0 + i}
                       for i in range(10)]

    def initialize(self, path=None):
        return True

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        if symbol in self._existing:
            return SimpleNamespace(name=symbol)
        return None

    def symbol_select(self, symbol, enable):
        self.selected.append(symbol)
        return symbol in self._existing

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        self.rate_symbols.append(symbol)
        return list(self._rates[-count:])

    def copy_rates_range(self, symbol, timeframe, start, end):
        self.rate_symbols.append(symbol)
        return list(self._rates)

    def symbol_info_tick(self, symbol):
        self.tick_symbols.append(symbol)
        return SimpleNamespace(bid=self._bid, ask=self._bid + 0.001)

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode,
                               server=self._server, demo=True)

    def order_check(self, request):
        self.checked.append(request)
        return SimpleNamespace(retcode=0)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=123456, comment="Done")

    def shutdown(self):
        return True


def _trial_m_only():
    """Chi co ten *m (mo phong server Trial that)."""
    return FakeMT5Suffix([s + "m" for s in ALL_SYMBOLS])


def _real_canonical_only():
    return FakeMT5Suffix(list(ALL_SYMBOLS), server=REAL_SERVER)


# --- resolve_mt5_symbol -------------------------------------------------

@pytest.mark.parametrize("server,suffix,expected", [
    ("Exness-MT5Trial7", None, "EURUSDm"),
    ("Exness-MT5Trial7", "auto", "EURUSDm"),
    ("exness-mt5trial7", None, "EURUSDm"),   # khong phan biet hoa/thuong
    ("EXNESS-MT5TRIAL7", None, "EURUSDm"),
    ("Exness-MT5Real1", None, "EURUSD"),
    ("Exness-MT5Real1", "auto", "EURUSD"),
    ("Some-Other-Broker", None, "EURUSD"),   # server khong ro -> goc
    (None, None, "EURUSD"),
    ("Exness-MT5Real1", "m", "EURUSDm"),     # suffix ep buoc thang
    ("Exness-MT5Trial7", "", "EURUSD"),      # suffix rong ep khong hau to
    ("Exness-MT5Trial7", "x", "EURUSDx"),
])
def test_resolve_mt5_symbol(server, suffix, expected):
    assert resolve_mt5_symbol("EURUSD", server, suffix) == expected


# --- build_symbol_map ---------------------------------------------------

def test_build_symbol_map_trial_m_only():
    mt5 = _trial_m_only()
    result = build_symbol_map(mt5, ALL_SYMBOLS, TRIAL_SERVER)
    assert result == {s: s + "m" for s in ALL_SYMBOLS}


def test_build_symbol_map_real_canonical_only():
    mt5 = _real_canonical_only()
    result = build_symbol_map(mt5, ALL_SYMBOLS, REAL_SERVER)
    assert result == {s: s for s in ALL_SYMBOLS}


def test_build_symbol_map_falls_back_to_canonical():
    # Server Trial nhung broker chi co ten chuan (vd cau hinh sai):
    # roi xuong ten chuan thay vi bao mat.
    mt5 = FakeMT5Suffix(list(ALL_SYMBOLS), server=TRIAL_SERVER)
    result = build_symbol_map(mt5, ["EURUSD"], TRIAL_SERVER)
    assert result == {"EURUSD": "EURUSD"}


def test_build_symbol_map_returns_none_when_missing():
    mt5 = FakeMT5Suffix([], server=TRIAL_SERVER)
    assert build_symbol_map(mt5, ["EURUSD"], TRIAL_SERVER) == {"EURUSD": None}
    assert build_symbol_map(mt5, ["EURUSD"], REAL_SERVER) == {"EURUSD": None}


def test_build_symbol_map_explicit_suffix():
    mt5 = FakeMT5Suffix(["EURUSDm"], server=REAL_SERVER)
    assert build_symbol_map(mt5, ["EURUSD"], REAL_SERVER,
                            suffix="m") == {"EURUSD": "EURUSDm"}
    mt5 = FakeMT5Suffix(["EURUSD"], server=TRIAL_SERVER)
    assert build_symbol_map(mt5, ["EURUSD"], TRIAL_SERVER,
                            suffix="") == {"EURUSD": "EURUSD"}


# --- MT5Feed ------------------------------------------------------------

def test_feed_trial_resolves_all_10_symbols():
    mt5 = _trial_m_only()
    for symbol in ALL_SYMBOLS:
        feed = MT5Feed(symbol, login=LOGIN, password="demo-pass",
                       server=TRIAL_SERVER, mt5_module=mt5)
        assert feed.symbol == symbol  # ten chuan giu nguyen
        assert feed.broker_symbol(symbol) == symbol + "m"
        assert feed.symbol_map == {symbol: symbol + "m"}


def test_feed_trial_bars_and_ticks_use_m_name():
    mt5 = _trial_m_only()
    feed = MT5Feed("EURUSD", login=LOGIN, password="demo-pass",
                   server=TRIAL_SERVER, mt5_module=mt5)
    assert mt5.selected == ["EURUSDm"]  # __init__ select ten *m
    bars = feed.bars(3)
    assert len(bars) == 3
    assert mt5.rate_symbols == ["EURUSDm"]
    assert feed.latest_price() == 101.5
    assert mt5.tick_symbols == ["EURUSDm"]
    # latest_price(symbol khac) cung giai quyet + cache theo nhu cau.
    assert feed.latest_price("XAUUSD") == 101.5
    assert mt5.tick_symbols[-1] == "XAUUSDm"
    assert feed.symbol_map["XAUUSD"] == "XAUUSDm"


def test_feed_real_uses_no_suffix():
    mt5 = _real_canonical_only()
    feed = MT5Feed("EURUSD", login=LOGIN, password="demo-pass",
                   server=REAL_SERVER, mt5_module=mt5)
    assert feed.broker_symbol("EURUSD") == "EURUSD"
    assert mt5.selected == ["EURUSD"]
    feed.bars(2)
    assert mt5.rate_symbols == ["EURUSD"]
    feed.latest_price()
    assert mt5.tick_symbols == ["EURUSD"]


def test_feed_trial_falls_back_to_canonical_when_m_missing():
    mt5 = FakeMT5Suffix(list(ALL_SYMBOLS), server=TRIAL_SERVER)
    feed = MT5Feed("EURUSD", login=LOGIN, password="demo-pass",
                   server=TRIAL_SERVER, mt5_module=mt5)
    assert feed.broker_symbol("EURUSD") == "EURUSD"
    assert mt5.selected == ["EURUSD"]


def test_feed_neither_name_exists_errors_naming_both():
    mt5 = FakeMT5Suffix([], server=TRIAL_SERVER)
    with pytest.raises(ValueError) as excinfo:
        MT5Feed("EURUSD", login=LOGIN, password="demo-pass",
                server=TRIAL_SERVER, mt5_module=mt5)
    msg = str(excinfo.value)
    assert "EURUSDm" in msg and "EURUSD" in msg
    assert TRIAL_SERVER in msg


def test_feed_server_from_account_info_when_arg_missing():
    # Khong truyen server vao constructor: doc tu account_info().
    mt5 = _trial_m_only()
    feed = MT5Feed("EURUSD", login=LOGIN, password="demo-pass",
                   mt5_module=mt5)
    assert feed.server == TRIAL_SERVER
    assert feed.broker_symbol("EURUSD") == "EURUSDm"


def test_build_feed_passes_symbol_suffix_auto():
    cfg = {"data": {"provider": "mt5", "symbols": {"forex": ["EURUSD"]}},
           "mt5": {"login": LOGIN, "server": TRIAL_SERVER,
                   "symbol_suffix": "auto"}}
    feed = build_feed(cfg, "forex", mt5_module=_trial_m_only())
    assert feed.symbol == "EURUSD"
    assert feed.broker_symbol("EURUSD") == "EURUSDm"


# --- check_symbols / check_symbols_available ----------------------------

def test_check_symbols_trial_m_only_keyed_canonical():
    mt5 = _trial_m_only()
    result = check_symbols(mt5, ALL_SYMBOLS, server=TRIAL_SERVER)
    assert result == {s: True for s in ALL_SYMBOLS}
    # Khong truyen server/suffix: hanh vi cu — kiem tra ten chuan,
    # nen tren fake chi-co-*m thi bao False.
    assert check_symbols(mt5, ["EURUSD"]) == {"EURUSD": False}


def test_check_symbols_real_canonical():
    mt5 = _real_canonical_only()
    assert check_symbols(mt5, ["EURUSD", "GBPUSD"],
                         server=REAL_SERVER) == {"EURUSD": True,
                                                 "GBPUSD": False}


def test_check_symbols_available_trial_keyed_canonical():
    mt5 = _trial_m_only()
    have, missing = check_symbols_available(
        mt5, ["EURUSD", "XAUUSD", "GBPUSD"], server=TRIAL_SERVER)
    assert have == ["EURUSD", "XAUUSD"]
    assert missing == ["GBPUSD"]
    # Khong truyen server/suffix: hanh vi cu.
    have, missing = check_symbols_available(mt5, ["EURUSD"])
    assert have == [] and missing == ["EURUSD"]


# --- Duong dat lenh (execution) -----------------------------------------

def test_place_demo_order_uses_broker_symbol(monkeypatch):
    mt5 = _trial_m_only()
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    result = place_demo_order(
        mt5, symbol="EURUSD", action="BUY", volume=0.01, price=1.10,
        sl=1.078, desk="forex", manager="Yuling Pan",
        cfg=DEMO_CFG, account_info=mt5.account_info(),
        server=TRIAL_SERVER, broker_symbol="EURUSDm")
    assert result["status"] == "SENT"
    assert len(mt5.sent_orders) == 1
    assert mt5.sent_orders[0]["symbol"] == "EURUSDm"
    assert mt5.checked[0]["symbol"] == "EURUSDm"  # margin check cung *m
    # Log/ly do van dung ten chuan, khong phai ten *m.
    assert logged and logged[0][0][0] == "EURUSD"
    assert "EURUSDm" not in logged[0][0][2]


def test_check_margin_uses_broker_symbol():
    mt5 = _trial_m_only()
    ok, _msg = check_margin(mt5, "EURUSD", 0.01, 1.10,
                            mt5.account_info(), broker_symbol="EURUSDm")
    assert ok is True
    assert mt5.checked[0]["symbol"] == "EURUSDm"
    # Khong truyen broker_symbol: mac dinh ten chuan (hanh vi cu).
    mt5.checked.clear()
    ok, _msg = check_margin(mt5, "EURUSD", 0.01, 1.10,
                            mt5.account_info())
    assert mt5.checked[0]["symbol"] == "EURUSD"


# --- Listener -----------------------------------------------------------

class FakePendingStore:
    """Store gia theo dung hop dong cua pending.py."""

    def __init__(self, orders=None):
        self.orders = dict(orders or {})

    def resolve(self, order_id):
        order = self.orders.get(order_id)
        if order is None:
            return None, "khong tim thay lenh"
        if order.get("status") != "pending":
            return None, "lenh da duoc xu ly"
        return dict(order), None

    def mark_placed(self, order_id, ticket):
        self.orders[order_id]["status"] = "placed"
        self.orders[order_id]["ticket"] = ticket


def _listener_order(**overrides):
    order = {"desk": "forex", "manager": "Yuling Pan", "symbol": "EURUSD",
             "action": "BUY", "entry": 1.10, "sl": 1.05, "tp": 1.20,
             "volume": 0.01, "risk_usd": 75.0, "status": "pending",
             "ticket": None, "expires_at": time.time() + 3600}
    order.update(overrides)
    return order


def _listener_cfg(**mt5_overrides):
    mt5_cfg = {"demo_only": True, "server": TRIAL_SERVER}
    mt5_cfg.update(mt5_overrides)
    return {"telegram": {"enabled": True, "chat_id": "1234567890",
                         "max_entry_deviation_pct": 1.0},
            "mt5": mt5_cfg}


def test_latest_price_broker_symbol_uses_m_tick():
    mt5 = _trial_m_only()
    assert _latest_price(mt5, "EURUSD", broker_symbol="EURUSDm") == 101.5
    assert mt5.tick_symbols == ["EURUSDm"]
    # Khong truyen broker_symbol: tick dung ten chuan (hanh vi cu).
    mt5.tick_symbols.clear()
    assert _latest_price(mt5, "EURUSD") == 101.5
    assert mt5.tick_symbols == ["EURUSD"]


def test_listener_place_resolves_m_name(monkeypatch, tmp_path):
    monkeypatch.setattr(decisions, "LOG", tmp_path / "decisions-log.csv")
    monkeypatch.setattr(killswitch, "is_engaged", lambda path=None: False)
    mt5 = _trial_m_only()
    mt5._bid = 1.10  # gan entry 1.10 (do lech <= 1%)
    store = FakePendingStore({"ord-1": _listener_order()})
    result = place_pending_order(_listener_cfg(), mt5, store, "ord-1")
    assert result["ok"] is True
    assert result["ticket"] == 123456
    assert len(mt5.sent_orders) == 1
    assert mt5.sent_orders[0]["symbol"] == "EURUSDm"
    assert mt5.tick_symbols == ["EURUSDm"]
    assert mt5.checked[0]["symbol"] == "EURUSDm"
    assert store.orders["ord-1"]["status"] == "placed"


def test_listener_place_refuses_when_symbol_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(decisions, "LOG", tmp_path / "decisions-log.csv")
    monkeypatch.setattr(killswitch, "is_engaged", lambda path=None: False)
    mt5 = FakeMT5Suffix([], server=TRIAL_SERVER)
    store = FakePendingStore({"ord-1": _listener_order()})
    result = place_pending_order(_listener_cfg(), mt5, store, "ord-1")
    assert result["ok"] is False
    assert result["kind"] == "refused"
    assert "EURUSDm" in result["reason"] and "EURUSD" in result["reason"]
    assert TRIAL_SERVER in result["reason"]
    assert mt5.sent_orders == []
    assert store.orders["ord-1"]["status"] == "pending"


def test_listener_place_explicit_suffix_empty_uses_canonical(monkeypatch,
                                                             tmp_path):
    monkeypatch.setattr(decisions, "LOG", tmp_path / "decisions-log.csv")
    monkeypatch.setattr(killswitch, "is_engaged", lambda path=None: False)
    mt5 = FakeMT5Suffix(list(ALL_SYMBOLS), server=TRIAL_SERVER, bid=1.10)
    store = FakePendingStore({"ord-1": _listener_order()})
    cfg = _listener_cfg(symbol_suffix="")
    result = place_pending_order(cfg, mt5, store, "ord-1")
    assert result["ok"] is True
    assert mt5.sent_orders[0]["symbol"] == "EURUSD"


# --- Live process_symbol ------------------------------------------------

def _trend_bars(pattern=(0.2, 0.2, -0.25), n=60, start=100.0):
    """Nen tang lap lai — cho tin hieu BUY (giong test_live)."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class FakeLiveFeed:
    """Feed gia co broker_symbol() tra ten *m (nhu MT5Feed tren Trial)."""

    def __init__(self, bars_data, latest):
        self.bars_data = bars_data
        self._latest = latest

    def bars(self, n=60):
        return list(self.bars_data[-n:])

    def latest_price(self, symbol=None):
        return self._latest

    def broker_symbol(self, canonical):
        return canonical + "m"

    def close(self):
        return True


def test_live_process_symbol_uses_broker_symbol(monkeypatch, tmp_path):
    monkeypatch.setattr(decisions, "LOG", tmp_path / "decisions-log.csv")
    monkeypatch.setattr(decisions, "EQUITY_STATE",
                        tmp_path / "equity-state.json")
    monkeypatch.setattr(killswitch, "is_engaged", lambda path=None: False)
    cfg = load_config()
    mt5 = _trial_m_only()
    feed = FakeLiveFeed(_trend_bars(), latest=103.2)
    guard = DrawdownGuard(10000, {"forex": 2500, "xauusd": 2500,
                                  "crypto": 2500, "us_securities": 2500},
                          max_drawdown_pct=10.0, desk_warning_pct=5.0)
    result = process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server=TRIAL_SERVER,
        manager="Yuling Pan", guard=guard, positions=[], volume=0.01,
        per_symbol_cap=2500.0,
        verdict_store=str(tmp_path / "no-verdicts.json"))
    assert result["status"] == "TRADED"
    assert result["symbol"] == "EURUSD"  # ket qua van ten chuan
    assert len(mt5.sent_orders) == 1
    assert mt5.sent_orders[0]["symbol"] == "EURUSDm"
    assert mt5.checked[0]["symbol"] == "EURUSDm"
