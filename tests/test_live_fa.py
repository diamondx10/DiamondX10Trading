"""Test FA gate trong vong live (live.py + synthesis.py).

Nhan dinh PTCB mau thuan manh voi PTKT -> BLOCKED-FA-CONFLICT, khong
dat lenh, ghi log + gui canh bao chan. Thieu/cu nhan dinh -> van chay
nhu cu, ket qua ghi ro "FA: chua co" / "FA: cu". Dung MT5 + feed gia,
khong can terminal that.
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.config import load_config
from diamondx10.live import process_symbol, run_live_cycle
from diamondx10.risk import DrawdownGuard

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500, "us_securities": 2500}


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG + equity state tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    return log_path, state_path


def make_guard():
    return DrawdownGuard(10000, DESKS, max_drawdown_pct=10.0,
                         desk_warning_pct=5.0)


def trend_bars(pattern=(0.2, 0.2, -0.25), n=60, start=100.0):
    """Nen theo mau tang lap lai — cho tin hieu BUY that (RSI ~59)."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class FakeMT5Live:
    """MT5 gia cho live: tai khoan demo, order_send ghi lai."""
    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, server="Exness-MT5Trial7"):
        self._server = server
        self.sent_orders = []

    def initialize(self, path=None):
        return True

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return SimpleNamespace(login=987654321, server=self._server,
                               balance=10000.0, currency="USD", trade_mode=0)

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol)

    def symbol_select(self, symbol, enable=True):
        return True

    def order_check(self, request):
        return SimpleNamespace(retcode=0)

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


def _write_verdict_store(tmp_path, desk="forex", direction="sell",
                         confidence=0.9, age_hours=0, analyst="Yumi"):
    created = (datetime.now(timezone.utc)
               - timedelta(hours=age_hours)).isoformat()
    verdict = {"desk": desk, "analyst": analyst, "direction": direction,
               "confidence": confidence, "drivers": ["test"], "risks": [],
               "note": "test", "created_utc": created}
    store = tmp_path / "fundamental-verdicts.json"
    store.write_text(json.dumps({desk: verdict}), encoding="utf-8")
    return store


def _call(cfg, mt5, feed, store=None, **kwargs):
    return process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager="Yuling Pan", guard=make_guard(), positions=[],
        volume=0.01, per_symbol_cap=2500.0, verdict_store=store, **kwargs)


def _log_rows(log_path):
    if not log_path.exists():
        return []
    with open(log_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_fa_conflict_blocks_buy(tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = _write_verdict_store(tmp_decisions[0].parent, direction="sell",
                                 confidence=0.9)
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "BLOCKED-FA-CONFLICT"
    assert result["action"] == "BLOCKED-FA-CONFLICT"
    assert result["fa_note"] == "FA: sell 0.9"
    assert mt5.sent_orders == []
    rows = _log_rows(log_path)
    assert rows and rows[-1]["action"] == "BLOCKED-FA-CONFLICT"


def test_fa_aligned_buy_trades(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = _write_verdict_store(tmp_decisions[0].parent, direction="buy",
                                 confidence=0.9)
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "TRADED"
    assert result["action"] == "BUY"
    assert result["fa_note"] == "FA: buy 0.9"
    assert len(mt5.sent_orders) == 1


def test_fa_missing_verdict_passes_through(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = tmp_decisions[0].parent / "khong-co-file.json"
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "TRADED"
    assert result["fa_note"] == "FA: chua co"
    assert len(mt5.sent_orders) == 1


def test_fa_stale_verdict_passes_through(tmp_decisions):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = _write_verdict_store(tmp_decisions[0].parent, direction="sell",
                                 confidence=0.9, age_hours=25)
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "TRADED"
    assert result["fa_note"] == "FA: cu"
    assert len(mt5.sent_orders) == 1


def test_fa_require_fa_blocks_when_missing(tmp_decisions):
    cfg = load_config()
    cfg["synthesis"] = {"verdict_max_age_hours": 24, "require_fa": True,
                        "fa_high_confidence": 0.6}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = tmp_decisions[0].parent / "khong-co-file.json"
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "BLOCKED-FA-CONFLICT"
    assert mt5.sent_orders == []


def test_fa_conflict_sends_blocked_alert(tmp_decisions):
    cfg = load_config()
    cfg["telegram"] = {"enabled": True, "chat_id": "123",
                       "bot_token_env": "DIAMONDX10_TELEGRAM_TOKEN"}
    cfg["language"] = "en"
    mt5 = FakeMT5Live()
    sent = []
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = _write_verdict_store(tmp_decisions[0].parent, direction="sell",
                                 confidence=0.9)
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"], volume=0.01,
        feed_factory=lambda s: feed, telegram=sent.append,
        verdict_store=store)
    assert summary["n_traded"] == 0
    assert summary["n_blocked"] == 1
    assert summary["results"][0]["status"] == "BLOCKED-FA-CONFLICT"
    assert len(sent) == 1
    assert "ORDER BLOCKED" in sent[0] and "BLOCKED-FA-CONFLICT" in sent[0]
