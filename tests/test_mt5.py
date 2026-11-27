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
    assert bars == [{"time": 1700006300, "open": 106.5, "high": 107.5,
                     "low": 106.0, "close": 107.0},
                    {"time": 1700007200, "open": 107.5, "high": 108.5,
                     "low": 107.0, "close": 108.0},
                    {"time": 1700008100, "open": 108.5, "high": 109.5,
                     "low": 108.0, "close": 109.0}]
    assert feed.latest_price("EURUSD") == 101.5


def test_rate_to_bar_tuple_style():
    # Tuple theo thu tu MT5: (time, open, high, low, close, tick_volume,
    # spread, real_volume) — dang ma copy_rates_from_pos tra ve khi
    # dung kieu numpy record / tuple.
    from diamondx10.data.mt5_feed import _rate_to_bar
    bar = _rate_to_bar((1700000000, 100.0, 101.0, 99.0, 100.5, 10, 2, 0))
    assert bar == {"time": 1700000000, "open": 100.0, "high": 101.0,
                   "low": 99.0, "close": 100.5}


def test_rate_to_bar_attribute_style():
    from diamondx10.data.mt5_feed import _rate_to_bar
    rate = SimpleNamespace(time=1700000000, open=100.0, high=101.0,
                           low=99.0, close=100.5)
    assert _rate_to_bar(rate) == {"time": 1700000000, "open": 100.0,
                                  "high": 101.0, "low": 99.0,
                                  "close": 100.5}


def test_mt5_bars_ohlc_invariants_and_time_order():
    feed = MT5Feed("EURUSD", login=123, password="demo-pass",
                   server="Exness-MT5Trial7", mt5_module=FakeMT5())
    bars = feed.bars(10)
    assert len(bars) == 10
    times = [b["time"] for b in bars]
    assert times == sorted(times) and len(set(times)) == len(times)
    for b in bars:
        assert set(b) == {"time", "open", "high", "low", "close"}
        assert b["high"] >= max(b["open"], b["close"])
        assert b["low"] <= min(b["open"], b["close"])


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


def test_desk_symbols_returns_all_symbols():
    from diamondx10.__main__ import _desk_symbols, split_desk_capital
    cfg = {"data": {"symbols": {
        "crypto": ["BTCUSD", "BNBUSD", "ETHUSD"],
        "us_securities": ["AMD", "CDNS", "SNPS", "INTC", "NVDA"],
    }}}
    assert _desk_symbols(cfg, "crypto", None) == ["BTCUSD", "BNBUSD", "ETHUSD"]
    assert _desk_symbols(cfg, "us_securities", None) == ["AMD", "CDNS", "SNPS", "INTC", "NVDA"]
    # --symbol van chi lay 1 symbol do.
    assert _desk_symbols(cfg, "crypto", "ETHUSD") == ["ETHUSD"]
    with pytest.raises(ValueError):
        _desk_symbols(cfg, "forex", None)


def test_split_desk_capital():
    from diamondx10.__main__ import split_desk_capital
    assert split_desk_capital(2500, 1) == 2500
    assert split_desk_capital(2500, 5) == 500
    assert split_desk_capital(2500, 3) == pytest.approx(2500 / 3)
    assert split_desk_capital(2500, 0) == 0.0
    # Von chia deu: BTC voi 833 USD/symbol, stop 2% o gia 90.000
    # thi van duoi 0.01 lot — test ghi lai gioi han that nay.
    assert position_size_lots(2500 / 3, 1.0, 90000, 90000 * 0.98,
                              contract_size=1) == 0.0
    # Nhung ETH thi dat duoc voi cung muc von chia.
    assert position_size_lots(2500 / 3, 1.0, 3000, 3000 * 0.98,
                              contract_size=1) == 0.13


def test_stop_and_target_buy_sell():
    from diamondx10.__main__ import stop_and_target
    sl, tp = stop_and_target(100.0, "BUY", 0.05, 0.05)
    assert (sl, tp) == (95.0, 105.0)
    sl, tp = stop_and_target(100.0, "SELL", 0.05, 0.05)
    assert (sl, tp) == (105.0, 95.0)


def test_place_demo_order_passes_tp(monkeypatch):
    mt5 = FakeMT5()
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    result = place_demo_order(
        mt5, symbol="EURUSD", action="BUY", volume=0.01, price=1.16,
        sl=1.102, tp=1.218, desk="forex", manager="Yuling Pan",
        cfg=LIVE_CFG, account_info=mt5.account_info(),
        server="Exness-MT5Trial7")
    assert result["status"] == "SENT"
    assert mt5.sent_orders[0]["tp"] == pytest.approx(1.218)
    assert "TP 1.218" in logged[0][0][2]


def test_sl_5pct_sizing_regression():
    # Stop loss 5% + rui ro 1%: khoi luong cang nho. Ghi lai he qua that:
    # EURUSD voi 2.500 USD/desk cung khong du 0.01 lot.
    assert position_size_lots(2500, 1.0, 1.16, 1.16 * 0.95,
                              contract_size=100000) == 0.0
    # Vang van 0; ETH/BNB/chung khoan thi dat duoc.
    assert position_size_lots(2500, 1.0, 4000, 4000 * 0.95,
                              contract_size=100) == 0.0
    assert position_size_lots(2500 / 3, 1.0, 3000, 3000 * 0.95,
                              contract_size=1) == 0.05
    assert position_size_lots(500, 1.0, 180, 180 * 0.95,
                              contract_size=1) == 0.55


def test_risk_10pct_all_symbols_min_lot():
    # Quyet dinh 2026-11-26: tang rui ro len 10%/lenh de moi symbol
    # dat duoc it nhat 0.01 lot o stop 5%. Gia minh hoa; vang 8% chi
    # vua du o gia 4.000 (len 5.000 thi lai ve 0) nen chon 10%.
    cases = [
        ("EURUSD", 1.16, 100000, 2500),
        ("XAUUSD", 4000, 100, 2500),
        ("XAUUSD@5000", 5000, 100, 2500),
        ("BTCUSD", 90000, 1, 2500 / 3),
        ("BTCUSD@120k", 120000, 1, 2500 / 3),
        ("ETHUSD", 3000, 1, 2500 / 3),
        ("BNBUSD", 900, 1, 2500 / 3),
        ("NVDA", 180, 1, 500),
        ("AMD", 200, 1, 500),
        ("SNPS", 450, 1, 500),
        ("INTC", 40, 1, 500),
        ("CDNS", 350, 1, 500),
    ]
    for _name, entry, contract, cap in cases:
        lots = position_size_lots(cap, 10.0, entry, entry * 0.95,
                                  contract_size=contract)
        assert lots >= 0.01, _name
    # 8% thi vang len 5.000 lai ve 0 — ghi lai de sau nay khoi quay ve 8%.
    assert position_size_lots(2500, 8.0, 5000, 5000 * 0.95,
                              contract_size=100) == 0.0


def test_risk_pct_for_symbol():
    from diamondx10.__main__ import risk_pct_for_symbol
    cfg = {"risk": {"max_risk_per_trade_pct": 1.0,
                    "per_symbol_pct": {"EURUSD": 3.0, "XAUUSD": 10.0, "BTCUSD": 8.0}}}
    assert risk_pct_for_symbol(cfg, "EURUSD") == 3.0
    assert risk_pct_for_symbol(cfg, "XAUUSD") == 10.0
    assert risk_pct_for_symbol(cfg, "BTCUSD") == 8.0
    # Symbol khong co trong bang dung muc chung 1%.
    assert risk_pct_for_symbol(cfg, "ETHUSD") == 1.0
    assert risk_pct_for_symbol(cfg, "NVDA") == 1.0
    assert risk_pct_for_symbol({}, "EURUSD") == 1.0


def test_per_symbol_risk_all_symbols_min_lot():
    # Rui ro theo symbol (muc chung 1%, chi EURUSD 3%, XAUUSD 10%,
    # BTCUSD 8%): moi symbol dat duoc it nhat 0.01 lot o stop 5%.
    # Gia tham chieu co bien (vang 5.000, BTC 120.000).
    from diamondx10.__main__ import risk_pct_for_symbol
    cfg = {"risk": {"max_risk_per_trade_pct": 1.0,
                    "per_symbol_pct": {"EURUSD": 3.0, "XAUUSD": 10.0, "BTCUSD": 8.0}}}
    cases = [
        ("EURUSD", 1.16, 100000, 2500),
        ("XAUUSD", 5000, 100, 2500),
        ("BTCUSD", 120000, 1, 2500 / 3),
        ("ETHUSD", 3000, 1, 2500 / 3),
        ("BNBUSD", 900, 1, 2500 / 3),
        ("NVDA", 180, 1, 500),
        ("AMD", 200, 1, 500),
        ("SNPS", 450, 1, 500),
        ("INTC", 40, 1, 500),
        ("CDNS", 350, 1, 500),
    ]
    for name, entry, contract, cap in cases:
        rpct = risk_pct_for_symbol(cfg, name)
        lots = position_size_lots(cap, rpct, entry, entry * 0.95,
                                  contract_size=contract)
        assert lots >= 0.01, name
