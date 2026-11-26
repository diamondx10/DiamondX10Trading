"""Test MT5 demo connector — dung MT5 GIA, khong can terminal that,
khong can mang, khong co credential that."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.data.mt5_feed import MT5Feed, check_symbols, load_mt5
from diamondx10.data.providers import build_feed
from diamondx10.execution import (
    NotDemoAccountError,
    account_is_demo,
    check_demo_only,
    check_symbols_available,
    place_demo_order,
    position_size_lots,
)


class FakeMT5:
    """MT5 gia: gia co dinh, tai khoan demo, co NVDA/AMD nhung khong co CDNS."""

    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, trade_mode=0, server="Exness-MT5Trial7"):
        self._trade_mode = trade_mode
        self._server = server
        self.sent_orders = []
        self._rates = [{"time": 1700000000 + i * 900, "close": 100.0 + i}
                       for i in range(10)]

    def initialize(self):
        return True

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        if symbol in ("EURUSD", "XAUUSD", "NVDA", "AMD", "BTCUSD"):
            return SimpleNamespace(name=symbol)
        return None

    def symbol_select(self, symbol, enable):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return list(self._rates[-count:])

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=101.5, ask=101.6)

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode,
                               server=self._server, demo=True)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=123456, comment="Done")

    def shutdown(self):
        return True


DEMO_CFG = {"mt5": {"demo_only": True}, "data": {"provider": "mt5"}}
LIVE_CFG = {"mt5": {"demo_only": True}, "data": {"provider": "mt5"}}


def test_load_mt5_raises_clear_error_when_not_installed():
    # Tren VM Linux nay goi MetaTrader5 that khong co -> loi phai ro rang.
    with pytest.raises(ImportError, match="MetaTrader5"):
        load_mt5()


def test_feed_bar_conversion():
    feed = MT5Feed("EURUSD", login=123, password="demo-pass",
                   server="Exness-MT5Trial7", mt5_module=FakeMT5())
    bars = feed.bars(3)
    assert bars == [{"time": 1700006300, "close": 107.0},
                    {"time": 1700007200, "close": 108.0},
                    {"time": 1700008100, "close": 109.0}]
    assert feed.latest_price("EURUSD") == 101.5


def test_feed_symbol_not_found():
    with pytest.raises(ValueError, match="CDNS"):
        MT5Feed("CDNS", login=123, password="demo-pass",
                server="Exness-MT5Trial7", mt5_module=FakeMT5())


def test_symbol_check_flags_missing_cdns():
    mt5 = FakeMT5()
    result = check_symbols(mt5, ["NVDA", "AMD", "CDNS"])
    assert result == {"NVDA": True, "AMD": True, "CDNS": False}
    have, missing = check_symbols_available(mt5, ["NVDA", "AMD", "CDNS"])
    assert have == ["NVDA", "AMD"]
    assert missing == ["CDNS"]


def test_demo_guard_accepts_demo_account():
    mt5 = FakeMT5(trade_mode=0, server="Exness-MT5Trial7")
    assert account_is_demo(mt5, mt5.account_info(), "Exness-MT5Trial7") is True
    check_demo_only(DEMO_CFG, mt5, mt5.account_info(), "Exness-MT5Trial7")


def test_demo_guard_refuses_live_account():
    mt5 = FakeMT5(trade_mode=1, server="Exness-MT5Real1")
    assert account_is_demo(mt5, mt5.account_info(), "Exness-MT5Real1") is False
    with pytest.raises(NotDemoAccountError):
        check_demo_only(LIVE_CFG, mt5, mt5.account_info(), "Exness-MT5Real1")


def test_demo_guard_refuses_live_config():
    mt5 = FakeMT5()
    cfg = {"mt5": {"demo_only": False}, "data": {"provider": "mt5"}}
    with pytest.raises(NotDemoAccountError):
        check_demo_only(cfg, mt5, mt5.account_info(), "Exness-MT5Trial7")
    cfg2 = {"mt5": {"demo_only": True}, "data": {"provider": "live"}}
    with pytest.raises(NotDemoAccountError):
        check_demo_only(cfg2, mt5, mt5.account_info(), "Exness-MT5Trial7")


def test_demo_guard_refuses_unknown_account():
    mt5 = FakeMT5()
    with pytest.raises(NotDemoAccountError):
        check_demo_only(DEMO_CFG, mt5, None, "Exness-MT5Trial7")


def test_position_sizing_lots():
    # Von 500 USD, rui ro 1% = lo toi da 5 USD; entry 100, SL 90 -> 0.5 don vi
    # voi contract_size=1 thi 0.5 lot; tron xuong buoc 0.01.
    assert position_size_lots(500, 1.0, 100.0, 90.0, contract_size=1) == 0.5
    assert position_size_lots(500, 1.0, 100.0, 100.0, contract_size=1) == 0.0
    assert position_size_lots(500, 1.0, 100.0, 90.0, contract_size=100000) == 0.0


def test_place_demo_order_dry_run_sends_nothing(monkeypatch):
    mt5 = FakeMT5()
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    result = place_demo_order(
        mt5, symbol="EURUSD", action="BUY", volume=0.01, price=1.10,
        sl=1.078, desk="forex", manager="Yuling Pan",
        cfg=DEMO_CFG, account_info=mt5.account_info(),
        server="Exness-MT5Trial7", dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert mt5.sent_orders == []
    assert logged and logged[0][0][1].startswith("DRY-RUN-BUY")


def test_place_demo_order_sends_on_demo_and_logs(monkeypatch):
    mt5 = FakeMT5()
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    result = place_demo_order(
        mt5, symbol="EURUSD", action="BUY", volume=0.01, price=1.10,
        sl=1.078, desk="forex", manager="Yuling Pan",
        cfg=DEMO_CFG, account_info=mt5.account_info(),
        server="Exness-MT5Trial7")
    assert result["status"] == "SENT"
    assert result["order"] == 123456
    assert len(mt5.sent_orders) == 1
    assert mt5.sent_orders[0]["symbol"] == "EURUSD"
    assert logged and logged[0][0][1] == "BUY"


def test_place_demo_order_refuses_live_account(monkeypatch):
    mt5 = FakeMT5(trade_mode=1, server="Exness-MT5Real1")
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    with pytest.raises(NotDemoAccountError):
        place_demo_order(
            mt5, symbol="EURUSD", action="BUY", volume=0.01, price=1.10,
            sl=1.078, desk="forex", manager="Yuling Pan",
            cfg=LIVE_CFG, account_info=mt5.account_info(),
            server="Exness-MT5Real1")
    assert mt5.sent_orders == []
    assert logged == []


def test_build_feed_mt5_uses_fake_module():
    cfg = {"data": {"provider": "mt5", "symbols": {"forex": ["EURUSD"]}},
           "mt5": {"login": 123, "server": "Exness-MT5Trial7"}}
    feed = build_feed(cfg, "forex", mt5_module=FakeMT5())
    assert feed.symbol == "EURUSD"
    assert len(feed.bars(5)) == 5
