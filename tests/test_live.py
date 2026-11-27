"""Test Phase D — vong lap live (live.py) + CLI `live`.

Dung MT5 gia + feed gia, khong can terminal that, khong co lenh that.
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.config import load_config
from diamondx10.decisions import load_equity_state, save_equity_state
from diamondx10.live import (
    _seconds_until_next_boundary,
    process_symbol,
    run_live_cycle,
    run_live_loop,
)
from diamondx10.risk import DrawdownGuard

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500, "us_securities": 2500}


def make_guard():
    return DrawdownGuard(10000, DESKS, max_drawdown_pct=10.0,
                         desk_warning_pct=5.0)


def trend_bars(pattern=(0.2, 0.2, -0.25), n=60, start=100.0):
    """Nen theo mau tang lap lai — pattern nay cho tin hieu BUY that
    (RSI ~59, SMA5 > SMA20), giong test_risk_enforcement."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


def flat_bars(n=60, close=103.2):
    """Nen di ngang — SMA5 == SMA20 nen tin hieu HOLD."""
    return [{"time": 1700000000 + i * 900, "open": close, "high": close + 0.5,
             "low": close - 0.5, "close": close} for i in range(n)]


class FakeMT5Live:
    """MT5 gia cho live: tai khoan demo, order_check tuy chinh duoc."""

    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, trade_mode=0, server="Exness-MT5Trial7",
                 order_check_retcode=0):
        self._trade_mode = trade_mode
        self._server = server
        self._order_check_retcode = order_check_retcode
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
        return [{"time": 1700000000 + i * 900, "open": 100.0, "high": 100.5,
                 "low": 99.5, "close": 100.0} for i in range(count)]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=103.0, ask=103.1)

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode,
                               server=self._server, demo=True)

    def history_deals_get(self, *args, **kwargs):
        return []  # khong co deal dong — doi chieu theo nen

    def order_check(self, request):
        return SimpleNamespace(retcode=self._order_check_retcode)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=777001, comment="Done")

    def shutdown(self):
        return True


class FakeLiveFeed:
    """Feed gia: bars/latest thay doi duoc, co mt5 + account_info demo."""

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


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG + equity state tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    return log_path, state_path


def _log_rows(log_path):
    if not log_path.exists():
        return []
    with open(log_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _call_process_symbol(cfg, mt5, feed, guard=None, positions=None,
                         volume=0.01, per_symbol_cap=2500.0, **kwargs):
    """Goi process_symbol voi tai khoan demo mac dinh."""
    guard = guard if guard is not None else make_guard()
    positions = positions if positions is not None else []
    account = mt5.account_info()
    return process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5, account=account,
        server="Exness-MT5Trial7", manager="Yuling Pan", guard=guard,
        positions=positions, volume=volume,
        per_symbol_cap=per_symbol_cap, **kwargs)


# ---------------- process_symbol ----------------

def test_process_symbol_hold_no_order(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(flat_bars(), latest=103.2, mt5=mt5)
    result = _call_process_symbol(cfg, mt5, feed)
    assert result["status"] == "HELD"
    assert result["action"] == "HOLD"
    assert mt5.sent_orders == []


def test_process_symbol_buy_trades_on_demo(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    positions = []
    result = _call_process_symbol(cfg, mt5, feed, positions=positions)
    assert result["status"] == "TRADED"
    assert result["action"] == "BUY"
    assert result["volume"] == 0.01
    assert result["price"] == pytest.approx(103.0)
    # ATR ~1.0, SL 1.5x ATR, TP 2x khoang cach SL (giong test cu).
    assert result["sl"] == pytest.approx(101.5)
    assert result["tp"] == pytest.approx(106.0)
    assert len(mt5.sent_orders) == 1
    assert mt5.sent_orders[0]["symbol"] == "EURUSD"
    assert len(positions) == 1
    assert positions[0]["direction"] == "BUY"
    assert positions[0]["entry"] == pytest.approx(103.0)


def test_process_symbol_buy_result_has_recommendation_fields(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = _call_process_symbol(cfg, mt5, feed)
    assert result["status"] == "TRADED"
    # Khuyen nghi Telegram can: rui ro toi da, nguoi phu trach, thoi gian.
    assert result["risk_usd"] == pytest.approx(75.0)  # 2500 USD x 3% EURUSD
    assert result["manager"] == "Yuling Pan"
    assert result["time"]


def test_process_symbol_blocked_drawdown(tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    guard = make_guard()
    guard.record_pnl("forex", -1100.0)  # vuot gioi han quy 10%
    result = _call_process_symbol(cfg, mt5, feed, guard=guard)
    assert result["status"] == "BLOCKED-DRAWDOWN-FUND"
    assert mt5.sent_orders == []
    rows = _log_rows(log_path)
    assert len([r for r in rows
                if r["action"] == "BLOCKED-DRAWDOWN-FUND"]) == 1


def test_process_symbol_blocked_no_trade_window(tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    now = datetime.now()
    start = (now.replace(microsecond=0)).isoformat()
    cfg["no_trade_events"] = [
        {"name": "CPI My", "start": start, "window_minutes": 60}]
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = _call_process_symbol(cfg, mt5, feed, now=now)
    assert result["status"] == "BLOCKED-NO-TRADE-WINDOW"
    assert mt5.sent_orders == []
    rows = _log_rows(log_path)
    assert len([r for r in rows
                if r["action"] == "BLOCKED-NO-TRADE-WINDOW"]) == 1


def test_process_symbol_volume_zero_blocked(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    # Von/symbol cuc nho + khong truyen volume -> size ve 0.
    result = _call_process_symbol(cfg, mt5, feed, volume=None,
                                  per_symbol_cap=1.0)
    assert result["status"] == "BLOCKED-VOLUME-ZERO"
    assert mt5.sent_orders == []


def test_process_symbol_blocked_margin(tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    mt5 = FakeMT5Live(order_check_retcode=10006)  # khong du ky quy
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = _call_process_symbol(cfg, mt5, feed)
    assert result["status"] == "BLOCKED-MARGIN"
    assert mt5.sent_orders == []
    rows = _log_rows(log_path)
    assert len([r for r in rows if r["action"] == "BLOCKED-MARGIN"]) == 1


def test_process_symbol_refuses_live_account(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live(trade_mode=1, server="Exness-MT5Real1")
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = _call_process_symbol(cfg, mt5, feed)
    assert result["status"] == "ERROR"
    assert "demo" in result["reason"].lower()
    assert mt5.sent_orders == []


# ---------------- run_live_cycle ----------------

def _cycle_cfg(telegram_enabled=False):
    cfg = load_config()
    cfg["telegram"] = {"enabled": telegram_enabled, "chat_id": "123",
                       "bot_token_env": "DIAMONDX10_TELEGRAM_TOKEN"}
    return cfg


def test_cycle_hold_no_order_no_alert(tmp_decisions):
    cfg = _cycle_cfg(telegram_enabled=True)
    sent = []
    feed = FakeLiveFeed(flat_bars(), latest=103.2, mt5=FakeMT5Live())
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"],
        feed_factory=lambda s: feed, telegram=sent.append)
    assert summary["desk"] == "forex"
    assert summary["timeframe"] == "M15"
    assert summary["n_traded"] == 0
    assert summary["n_blocked"] == 0
    assert summary["errors"] == []
    assert summary["results"][0]["status"] == "HELD"
    assert sent == []  # HOLD thi khong gui canh bao


def test_cycle_buy_trades_and_alerts(tmp_decisions):
    _, state_path = tmp_decisions
    cfg = _cycle_cfg(telegram_enabled=True)
    mt5 = FakeMT5Live()
    sent = []
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"], volume=0.01,
        feed_factory=lambda s: feed, telegram=sent.append)
    assert summary["n_traded"] == 1
    assert summary["errors"] == []
    assert len(mt5.sent_orders) == 1
    assert len(sent) == 1
    assert "EURUSD" in sent[0] and "BUY" in sent[0]
    assert "103" in sent[0]  # gia vao co trong canh bao
    state = load_equity_state(path=state_path)
    assert state is not None and len(state["positions"]) == 1


def test_cycle_blocked_drawdown_alerts(tmp_decisions):
    _, state_path = tmp_decisions
    cfg = _cycle_cfg(telegram_enabled=True)
    guard = make_guard()
    guard.record_pnl("forex", -1100.0)  # vuot gioi han quy 10%
    save_equity_state({"guard": guard.to_state(), "positions": []},
                      path=state_path)
    sent = []
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=FakeMT5Live())
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"], volume=0.01,
        feed_factory=lambda s: feed, telegram=sent.append)
    assert summary["n_traded"] == 0
    assert summary["n_blocked"] == 1
    assert summary["results"][0]["status"] == "BLOCKED-DRAWDOWN-FUND"
    assert len(sent) == 1
    assert "ORDER BLOCKED" in sent[0] and "BLOCKED-DRAWDOWN-FUND" in sent[0]


def test_cycle_one_symbol_error_does_not_crash(tmp_decisions):
    cfg = _cycle_cfg()
    mt5 = FakeMT5Live()
    buy_feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)

    def factory(symbol):
        if symbol == "XAUUSD":
            raise ConnectionError("mat ket noi MT5")
        return buy_feed

    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD", "XAUUSD"], volume=0.01,
        feed_factory=factory)
    assert summary["n_traded"] == 1
    assert len(summary["results"]) == 1
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["symbol"] == "XAUUSD"


def test_cycle_no_mt5_reports_error_cleanly(tmp_decisions):
    # Tren Linux khong co goi MetaTrader5: chu ky tra ve errors,
    # khong raise, khong traceback.
    cfg = _cycle_cfg()
    summary = run_live_cycle(cfg, "forex", symbols=["EURUSD"])
    assert summary["results"] == []
    assert summary["n_traded"] == 0
    assert len(summary["errors"]) == 1
    assert "MetaTrader5" in summary["errors"][0]["error"]


def test_cycle_invalid_timeframe_raises(tmp_decisions):
    cfg = _cycle_cfg()
    with pytest.raises(ValueError, match="Khung thoi gian"):
        run_live_cycle(cfg, "forex", symbols=["EURUSD"], timeframe="W1",
                       feed_factory=lambda s: FakeLiveFeed(
                           flat_bars(), 103.2, FakeMT5Live()))


# ---------------- run_live_loop ----------------

def test_live_loop_max_cycles(tmp_decisions):
    cfg = _cycle_cfg()
    feed = FakeLiveFeed(flat_bars(), latest=103.2, mt5=FakeMT5Live())
    sleeps = []
    summaries = run_live_loop(
        cfg, "forex", symbols=["EURUSD"], max_cycles=2,
        feed_factory=lambda s: feed, sleep_fn=sleeps.append)
    assert len(summaries) == 2
    assert all(s["n_traded"] == 0 for s in summaries)
    assert len(sleeps) == 1  # chi ngu giua 2 chu ky
    assert 0 < sleeps[0] <= 900


def test_seconds_until_next_boundary():
    # 10:07 UTC, bien M15 tiep theo 10:15 -> cho 8 phut.
    now = datetime(2026, 11, 27, 10, 7, tzinfo=timezone.utc)
    assert _seconds_until_next_boundary(15, now) == 480
    # Dung bien 10:15 -> cho tron 1 khoang 15 phut.
    now = datetime(2026, 11, 27, 10, 15, tzinfo=timezone.utc)
    assert _seconds_until_next_boundary(15, now) == 900


# ---------------- CLI `live` ----------------

def test_main_live_once_calls_cycle(monkeypatch, tmp_decisions):
    from diamondx10.__main__ import main

    called = {}

    def fake_cycle(cfg, desk, **kwargs):
        called["desk"] = desk
        called["kwargs"] = kwargs
        return {"desk": desk, "timeframe": "M15", "started_at": "x",
                "results": [{"symbol": "EURUSD", "action": "HOLD",
                             "status": "HELD", "reason": "test"}],
                "n_traded": 0, "n_blocked": 0, "errors": []}

    monkeypatch.setattr("diamondx10.__main__.run_live_cycle", fake_cycle)
    rc = main(["live", "--desk", "forex", "--symbol", "EURUSD", "--once"])
    assert rc in (None, 0)
    assert called["desk"] == "forex"
    assert called["kwargs"]["symbols"] == ["EURUSD"]


def test_main_live_once_all_errors_returns_1(monkeypatch, tmp_decisions):
    from diamondx10.__main__ import main

    def fake_cycle(cfg, desk, **kwargs):
        return {"desk": desk, "timeframe": "M15", "started_at": "x",
                "results": [], "n_traded": 0, "n_blocked": 0,
                "errors": [{"symbol": "EURUSD",
                            "error": "Chua cai goi MetaTrader5"}]}

    monkeypatch.setattr("diamondx10.__main__.run_live_cycle", fake_cycle)
    rc = main(["live", "--desk", "forex", "--once"])
    assert rc == 1
