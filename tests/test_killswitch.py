"""Test Phase F — kill switch (killswitch.py + noi vao live.py).

Dung MT5 gia + feed gia, khong can terminal that, khong co lenh that.
"""
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import audit, decisions, killswitch
from diamondx10.decisions import save_equity_state
from diamondx10.live import process_symbol, run_live_cycle
from diamondx10.risk import DrawdownGuard

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500, "us_securities": 2500}


def trend_bars(pattern=(0.2, 0.2, -0.25), n=60, start=100.0):
    """Nen theo mau tang lap lai — cho tin hieu BUY that (RSI ~59)."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class FakeMT5:
    """MT5 gia: tai khoan demo, ghi lai lenh da gui."""
    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self):
        self.sent_orders = []

    def initialize(self, path=None):
        return True

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol)

    def symbol_select(self, symbol, enable):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return [{"time": 1700000000 + i * 900, "open": 100.0,
                 "high": 100.5, "low": 99.5, "close": 100.0}
                for i in range(count)]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=103.0, ask=103.1)

    def account_info(self):
        return SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7",
                              demo=True)

    def history_deals_get(self, *args, **kwargs):
        return []

    def order_check(self, request):
        return SimpleNamespace(retcode=0)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=777001, comment="Done")

    def shutdown(self):
        return True


class FakeFeed:
    def __init__(self, bars_data, latest, mt5=None):
        self.bars_data = bars_data
        self._latest = latest
        self.mt5 = mt5

    def bars(self, n=60):
        return list(self.bars_data[-n:])

    def latest_price(self, symbol=None):
        return self._latest

    def account_info(self):
        return self.mt5.account_info() if self.mt5 is not None else None

    def close(self):
        return True


def _cfg():
    return {
        "fund": {"total_capital_usd": 10000, "desks": {
            d: {"manager": m, "capital_usd": 2500}
            for d, m in [("forex", "Yuling Pan"), ("xauusd", "Yumi"),
                         ("crypto", "Rich"),
                         ("us_securities", "Kathy")]}},
        "risk": {"max_risk_per_trade_pct": 1.0, "max_drawdown_pct": 10.0,
                 "desk_warning_pct": 5.0,
                 "fund_daily_loss_pct": 3.0,
                 "max_open_positions_fund": 10,
                 "max_open_positions_desk": 2,
                 "per_symbol_pct": {"EURUSD": 3.0}},
        "data": {"symbols": {"forex": ["EURUSD"]}},
        "backtest": {"fee_pct": 0.02},
        "no_trade_events": [],
    }


def _patch_all(monkeypatch, tmp_path):
    """LOG + equity state + kill switch + audit tam (khong cham file that)."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    ks_path = tmp_path / "kill-switch.json"
    audit_path = tmp_path / "audit-log.jsonl"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    monkeypatch.setattr(killswitch, "KILL_SWITCH_FILE", ks_path)
    monkeypatch.setattr(audit, "AUDIT_LOG", audit_path)
    return log_path, state_path, ks_path, audit_path


def _log_rows(log_path):
    if not log_path.exists():
        return []
    with open(log_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------- killswitch.py ----------------

def test_status_missing_file_is_not_engaged(tmp_path):
    ks_path = tmp_path / "kill-switch.json"
    assert killswitch.is_engaged(path=ks_path) is False
    assert killswitch.status(path=ks_path) == {
        "engaged": False, "engaged_at": None, "reason": "", "by": ""}


def test_engage_disengage_roundtrip(tmp_path, monkeypatch):
    ks_path = tmp_path / "kill-switch.json"
    audit_path = tmp_path / "audit-log.jsonl"
    monkeypatch.setattr(audit, "AUDIT_LOG", audit_path)
    st = killswitch.engage("su co thi truong", by="Phu", path=ks_path)
    assert st["engaged"] is True
    assert st["reason"] == "su co thi truong"
    assert st["by"] == "Phu"
    assert st["engaged_at"]
    assert killswitch.is_engaged(path=ks_path) is True
    # File trang thai ghi dung noi dung.
    saved = json.loads(ks_path.read_text(encoding="utf-8"))
    assert saved["engaged"] is True
    assert saved["reason"] == "su co thi truong"
    st = killswitch.disengage(by="Phu", path=ks_path)
    assert st["engaged"] is False
    assert killswitch.is_engaged(path=ks_path) is False


def test_status_corrupt_file_is_not_engaged(tmp_path):
    ks_path = tmp_path / "kill-switch.json"
    ks_path.write_text("{khong phai json", encoding="utf-8")
    assert killswitch.is_engaged(path=ks_path) is False


# ---------------- process_symbol ----------------

def test_process_symbol_blocked_when_kill_switch_engaged(monkeypatch,
                                                         tmp_path):
    log_path, _, ks_path, _ = _patch_all(monkeypatch, tmp_path)
    killswitch.engage("test", by="tester", path=ks_path)
    mt5 = FakeMT5()
    feed = FakeFeed(trend_bars(), 103.2, mt5=mt5)
    result = process_symbol(
        _cfg(), "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager="Yuling Pan", guard=DrawdownGuard(10000, DESKS),
        positions=[], volume=0.01, per_symbol_cap=2500.0)
    assert result["status"] == "BLOCKED-KILL-SWITCH"
    assert mt5.sent_orders == []  # khong co lenh nao duoc gui
    actions = [r["action"] for r in _log_rows(log_path)]
    assert "BLOCKED-KILL-SWITCH" in actions


def test_process_symbol_trades_when_kill_switch_off(monkeypatch, tmp_path):
    _patch_all(monkeypatch, tmp_path)
    mt5 = FakeMT5()
    feed = FakeFeed(trend_bars(), 103.2, mt5=mt5)
    result = process_symbol(
        _cfg(), "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager="Yuling Pan", guard=DrawdownGuard(10000, DESKS),
        positions=[], volume=0.01, per_symbol_cap=2500.0)
    assert result["status"] == "TRADED"
    assert len(mt5.sent_orders) == 1


# ---------------- run_live_cycle ----------------

def test_cycle_with_kill_switch_blocks_new_orders_but_reconciles(
        monkeypatch, tmp_path):
    log_path, state_path, ks_path, audit_path = _patch_all(monkeypatch,
                                                           tmp_path)
    # Vi the mo san: BUY EURUSD @ 100, SL 101 — nen dau tien low 99.7
    # <= SL nen dong ngay trong chu ky (doi chieu van chay).
    save_equity_state({
        "guard": DrawdownGuard(10000, DESKS).to_state(),
        "positions": [{"desk": "forex", "symbol": "EURUSD",
                       "direction": "BUY", "entry": 100.0, "sl": 101.0,
                       "tp": 200.0, "volume": 0.01,
                       "contract_size": 100000, "atr": 0.1,
                       "opened_date": "2026-11-27"}]},
        path=state_path)
    killswitch.engage("test chu ky", by="tester", path=ks_path)
    mt5 = FakeMT5()

    def factory(symbol):
        return FakeFeed(trend_bars(), 103.2, mt5=mt5)

    summary = run_live_cycle(_cfg(), "forex", symbols=["EURUSD"],
                             feed_factory=factory)
    assert summary["kill_switch_engaged"] is True
    assert summary["n_traded"] == 0
    assert summary["results"][0]["status"] == "BLOCKED-KILL-SWITCH"
    assert mt5.sent_orders == []
    actions = [r["action"] for r in _log_rows(log_path)]
    assert "CLOSE" in actions  # doi chieu van dong vi the cu
    assert "KILL-SWITCH-ENGAGED" in actions
    events = audit.read_events(path=audit_path)
    assert "LIVE_CYCLE_STARTED" in [e["event"] for e in events]
    assert "LIVE_CYCLE_STOPPED" in [e["event"] for e in events]
