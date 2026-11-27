"""Test che do khuyen nghi (recommend mode) — live.py + report.py.

Che do khuyen nghi bat khi config trading.require_confirmation = true
hoac khi chay voi recommend_only=True (co `live --recommend-only` /
`mt5-trade --recommend-only`): tin hieu BUY/SELL vuot het gate thi
KHONG dat lenh ma tao lenh cho xac nhan trong PendingOrderStore, ghi
log RECOMMENDED, gui khuyen nghi kem ban phim inline Dat lenh / Bo qua.

Dung MT5 gia + feed gia + PendingOrderStore gia (theo dung hop dong
PendingOrderStore(path=None).create(order, ttl_min=15) -> id hex 8 ky
tu, .get/.mark_placed/.mark_cancelled/.resolve); khong can terminal
that, khong co lenh that, khong co mang that.
"""
import csv
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.config import load_config
from diamondx10.live import (
    _maybe_send_alert,
    process_symbol,
    run_live_cycle,
)
from diamondx10.report import build_report, format_report
from diamondx10.risk import DrawdownGuard

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500, "us_securities": 2500}


class FakePendingStore:
    """PendingOrderStore gia, dung hop dong that (create/get/
    mark_placed/mark_cancelled/resolve), ghi lai ttl de test."""

    def __init__(self, path=None):
        self.path = path
        self.orders = {}
        self.created_ttl = []
        self._n = 0

    def create(self, order, ttl_min=15):
        self._n += 1
        pid = f"{self._n:08x}"
        rec = dict(order)
        rec["id"] = pid
        rec["ttl_min"] = float(ttl_min)
        rec["expires_at"] = (
            datetime.now(timezone.utc)
            + timedelta(minutes=float(ttl_min))).isoformat()
        rec["status"] = "PENDING"
        self.orders[pid] = rec
        self.created_ttl.append(float(ttl_min))
        return pid

    def get(self, pid):
        return self.orders.get(pid)

    def mark_placed(self, pid, ticket):
        if pid in self.orders:
            self.orders[pid]["status"] = "PLACED"
            self.orders[pid]["ticket"] = ticket

    def mark_cancelled(self, pid):
        if pid in self.orders:
            self.orders[pid]["status"] = "CANCELLED"

    def resolve(self, pid):
        return self.orders.get(pid), None


def trend_bars(pattern=(0.2, 0.2, -0.25), n=60, start=100.0):
    """Nen theo mau tang lap lai — cho tin hieu BUY that."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


def downtrend_bars(n=60, start=100.0):
    """Nen theo mau giam lap lai — cho tin hieu SELL that."""
    return trend_bars(pattern=(-0.2, -0.2, 0.25), n=n, start=start)


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
        return []

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


def _make_guard():
    return DrawdownGuard(10000, DESKS, max_drawdown_pct=10.0,
                         desk_warning_pct=5.0)


def _call(cfg, mt5, feed, positions=None, store=None, **kwargs):
    return process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager="Yuling Pan", guard=_make_guard(),
        positions=[] if positions is None else positions,
        volume=0.01, per_symbol_cap=2500.0,
        pending_store=store, **kwargs)


def _capture(sent):
    def _send(text, reply_markup=None):
        sent.append({"text": text, "reply_markup": reply_markup})
        return True
    return _send


def _write_verdict_store(tmp_path, desk="forex", direction="sell",
                         confidence=0.9, age_hours=0):
    created = (datetime.now(timezone.utc)
               - timedelta(hours=age_hours)).isoformat()
    verdict = {"desk": desk, "analyst": "Yumi", "direction": direction,
               "confidence": confidence, "drivers": ["test"], "risks": [],
               "note": "test", "created_utc": created}
    store = tmp_path / "fundamental-verdicts.json"
    store.write_text(json.dumps({desk: verdict}), encoding="utf-8")
    return store


# ---------------- recommend mode: BUY / SELL ----------------

def test_recommend_buy_via_config(tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    positions = []
    result = _call(cfg, mt5, feed, positions=positions, store=store)
    assert result["status"] == "RECOMMENDED"
    assert result["action"] == "BUY"
    assert result["price"] == pytest.approx(103.0)
    assert result["sl"] == pytest.approx(101.5)
    assert result["tp"] == pytest.approx(106.0)
    assert result["volume"] == 0.01
    assert result["risk_usd"] == pytest.approx(75.0)
    assert result["manager"] == "Yuling Pan"
    assert result["time"]
    pid = result["pending_id"]
    assert isinstance(pid, str) and len(pid) == 8
    # Lenh cho co du entry/SL/TP/volume nhu duong dat lenh.
    pending = store.get(pid)
    assert pending is not None
    assert pending["symbol"] == "EURUSD"
    assert pending["action"] == "BUY"
    assert pending["entry"] == pytest.approx(103.0)
    assert pending["sl"] == pytest.approx(101.5)
    assert pending["tp"] == pytest.approx(106.0)
    assert pending["volume"] == 0.01
    assert pending["desk"] == "forex"
    assert pending["manager"] == "Yuling Pan"
    # KHONG dat lenh that, KHONG mo vi the, KHONG dem vao gioi han ngay.
    assert mt5.sent_orders == []
    assert positions == []
    from diamondx10.decisions import count_trades_today
    assert count_trades_today("EURUSD") == 0
    rows = _log_rows(log_path)
    recs = [r for r in rows if r["action"] == "RECOMMENDED"]
    assert len(recs) == 1
    assert pid in recs[0]["reason"]
    assert "103" in recs[0]["reason"]


def test_recommend_buy_via_flag_overrides_config_off(tmp_decisions):
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": False}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    result = _call(cfg, mt5, feed, store=store, recommend_only=True)
    assert result["status"] == "RECOMMENDED"
    assert result["action"] == "BUY"
    assert store.get(result["pending_id"]) is not None
    assert mt5.sent_orders == []


def test_recommend_sell(tmp_decisions):
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(downtrend_bars(), latest=97.0, mt5=mt5)
    store = FakePendingStore()
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "RECOMMENDED"
    assert result["action"] == "SELL"
    pending = store.get(result["pending_id"])
    assert pending is not None and pending["action"] == "SELL"
    assert pending["entry"] == pytest.approx(97.0)
    assert mt5.sent_orders == []


def test_recommend_default_ttl_15(tmp_decisions):
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    cfg["telegram"] = {"enabled": True, "chat_id": "123"}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    _call(cfg, mt5, feed, store=store)
    assert store.created_ttl == [15.0]


def test_recommend_ttl_from_config(tmp_decisions):
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    cfg["telegram"] = {"enabled": True, "chat_id": "123",
                       "pending_order_ttl_min": 30}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    result = _call(cfg, mt5, feed, store=store)
    assert store.created_ttl == [30.0]
    pending = store.get(result["pending_id"])
    assert pending["ttl_min"] == 30.0


def test_recommend_uses_default_store_via_lazy_import(monkeypatch,
                                                      tmp_decisions):
    """Khong truyen pending_store: live.py import luoi .pending."""
    module = types.ModuleType("diamondx10.pending")
    created = {}

    class RecordingStore(FakePendingStore):
        def __init__(self, path=None):
            super().__init__(path)
            created["store"] = self

    module.PendingOrderStore = RecordingStore
    monkeypatch.setitem(sys.modules, "diamondx10.pending", module)
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager="Yuling Pan", guard=_make_guard(), positions=[],
        volume=0.01, per_symbol_cap=2500.0, recommend_only=True)
    assert result["status"] == "RECOMMENDED"
    assert created["store"].get(result["pending_id"]) is not None
    assert mt5.sent_orders == []


# ---------------- recommend mode: gate chan ----------------

def test_recommend_blocked_kill_switch(monkeypatch, tmp_decisions):
    monkeypatch.setattr("diamondx10.live.is_engaged", lambda: True)
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "BLOCKED-KILL-SWITCH"
    assert store.orders == {}
    assert mt5.sent_orders == []


def test_recommend_blocked_fa_conflict(tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    verdict = _write_verdict_store(tmp_decisions[0].parent,
                                   direction="sell", confidence=0.9)
    result = _call(cfg, mt5, feed, store=store, verdict_store=verdict)
    assert result["status"] == "BLOCKED-FA-CONFLICT"
    assert store.orders == {}
    assert mt5.sent_orders == []


def test_recommend_blocked_margin(tmp_decisions):
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    mt5 = FakeMT5Live(order_check_retcode=10006)  # khong du ky quy
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "BLOCKED-MARGIN"
    assert store.orders == {}
    assert mt5.sent_orders == []


# ---------------- alert kem ban phim / auto mode ----------------

def test_recommend_cycle_alert_has_keyboard(tmp_decisions):
    cfg = load_config()
    cfg["telegram"] = {"enabled": True, "chat_id": "123",
                       "bot_token_env": "DIAMONDX10_TELEGRAM_TOKEN"}
    mt5 = FakeMT5Live()
    sent = []
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"], volume=0.01,
        feed_factory=lambda s: feed, telegram=_capture(sent),
        recommend_only=True, pending_store=store)
    assert summary["n_recommended"] == 1
    assert summary["n_traded"] == 0
    assert len(mt5.sent_orders) == 0
    assert len(sent) == 1
    pid = summary["results"][0]["pending_id"]
    kb = sent[0]["reply_markup"]
    assert kb is not None
    callbacks = [b["callback_data"]
                 for row in kb["inline_keyboard"] for b in row]
    assert f"ord:{pid}" in callbacks
    assert f"skip:{pid}" in callbacks
    assert "EURUSD" in sent[0]["text"] and "BUY" in sent[0]["text"]


def test_maybe_send_alert_recommended_old_style_callable(tmp_decisions):
    cfg = load_config()
    cfg["telegram"] = {"enabled": True, "chat_id": "123"}
    sent = []
    result = {"symbol": "EURUSD", "action": "BUY", "status": "RECOMMENDED",
              "reason": "test", "volume": 0.01, "price": 103.0,
              "sl": 101.5, "tp": 106.0, "risk_usd": 75.0,
              "manager": "Yuling Pan", "time": "2026-11-27T10:00:00+00:00",
              "pending_id": "abcd1234"}
    # Ham gui cu chi nhan 1 doi so (nhu list.append, tra None): van gui
    # duoc, khong crash vi reply_markup (chi khong tra True).
    _maybe_send_alert(cfg, "forex", result, sent.append)
    assert len(sent) == 1
    assert "EURUSD" in sent[0]
    assert "Not placed yet" in sent[0]
    assert "abcd1234" in sent[0]


def test_auto_mode_buy_trades_no_keyboard_no_pending(tmp_decisions):
    cfg = load_config()
    cfg["telegram"] = {"enabled": True, "chat_id": "123",
                       "bot_token_env": "DIAMONDX10_TELEGRAM_TOKEN"}
    mt5 = FakeMT5Live()
    sent = []
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"], volume=0.01,
        feed_factory=lambda s: feed, telegram=_capture(sent),
        pending_store=store)
    assert summary["n_traded"] == 1
    assert summary["n_recommended"] == 0
    assert len(mt5.sent_orders) == 1
    assert store.orders == {}
    assert len(sent) == 1
    assert sent[0]["reply_markup"] is None  # TRADED: thong bao thuong
    assert "EURUSD" in sent[0]["text"]


def test_config_require_confirmation_enables_recommend_in_cycle(
        tmp_decisions):
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    cfg["telegram"] = {"enabled": True, "chat_id": "123"}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store = FakePendingStore()
    summary = run_live_cycle(
        cfg, "forex", symbols=["EURUSD"], volume=0.01,
        feed_factory=lambda s: feed, telegram=_capture([]),
        pending_store=store)
    assert summary["n_recommended"] == 1
    assert summary["n_traded"] == 0
    assert mt5.sent_orders == []


# ---------------- tich hop voi store + Telegram that ----------------

def test_recommend_with_real_pending_store(tmp_decisions, tmp_path):
    """Store that (decisions/pending-orders.json): lenh cho ghi file,
    het han theo ttl trong config, resolve() lay duoc lenh."""
    from diamondx10.pending import PendingOrderStore

    log_path, _ = tmp_decisions
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    cfg["telegram"] = {"enabled": True, "chat_id": "123",
                       "pending_order_ttl_min": 30}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    store_path = tmp_path / "pending-orders.json"
    store = PendingOrderStore(path=store_path)
    result = _call(cfg, mt5, feed, store=store)
    assert result["status"] == "RECOMMENDED"
    assert store_path.exists()
    stored = PendingOrderStore(path=store_path).get(result["pending_id"])
    assert stored is not None
    assert stored["symbol"] == "EURUSD"
    assert stored["action"] == "BUY"
    assert stored["status"] == "pending"
    created = datetime.fromisoformat(stored["created_utc"])
    expires = datetime.fromisoformat(stored["expires_utc"])
    assert (expires - created) == timedelta(minutes=30)
    order, reason = PendingOrderStore(path=store_path).resolve(
        result["pending_id"])
    assert reason is None
    assert order["entry"] == pytest.approx(103.0)
    assert order["volume"] == 0.01
    assert mt5.sent_orders == []


class _FakeHTTPResponse:
    def __init__(self, status=200, body=None):
        self.status = status
        self._body = body if body is not None else {"ok": True}

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_recommend_alert_real_http_carries_keyboard(monkeypatch,
                                                   tmp_decisions):
    """Duong gui that (telegram=None): payload sendMessage co
    reply_markup voi callback_data ord:<id>/skip:<id>."""
    import urllib.request

    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(request)
        return _FakeHTTPResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "fake-token-xyz")
    cfg = load_config()
    cfg["telegram"] = {"enabled": True, "chat_id": "123",
                       "bot_token_env": "DIAMONDX10_TELEGRAM_TOKEN"}
    result = {"symbol": "EURUSD", "action": "BUY", "status": "RECOMMENDED",
              "reason": "test", "volume": 0.01, "price": 103.0,
              "sl": 101.5, "tp": 106.0, "risk_usd": 75.0,
              "manager": "Yuling Pan", "time": "2026-11-27T10:00:00+00:00",
              "pending_id": "abcd1234"}
    assert _maybe_send_alert(cfg, "forex", result, None) is True
    assert len(seen) == 1
    payload = json.loads(seen[0].data.decode("utf-8"))
    assert payload["chat_id"] == "123"
    assert "Not placed yet" in payload["text"]
    kb = payload["reply_markup"]
    callbacks = [b["callback_data"]
                 for row in kb["inline_keyboard"] for b in row]
    assert "ord:abcd1234" in callbacks
    assert "skip:abcd1234" in callbacks


# ---------------- dry-run: khong tao lenh cho ----------------

def test_dry_run_creates_no_pending(monkeypatch, tmp_decisions):
    log_path, _ = tmp_decisions
    cfg = load_config()
    cfg["trading"] = {"require_confirmation": True}
    cfg["telegram"] = {"enabled": True, "chat_id": "123"}
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    account = SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7",
                              demo=True)
    store = FakePendingStore()
    module = types.ModuleType("diamondx10.pending")

    class RecordingStore(FakePendingStore):
        def __init__(self, path=None):
            super().__init__(path)
            store.orders = self.orders
            store.created_ttl = self.created_ttl

    module.PendingOrderStore = RecordingStore
    monkeypatch.setitem(sys.modules, "diamondx10.pending", module)
    monkeypatch.setattr("diamondx10.__main__.load_config",
                        lambda *a, **k: cfg)
    monkeypatch.setattr(
        "diamondx10.__main__._mt5_context",
        lambda cfg_, desk, symbol=None, mt5_module=None:
        (feed, mt5, account, "Exness-MT5Trial7"))
    from diamondx10.__main__ import main
    rc = main(["mt5-dry-run", "--desk", "forex", "--symbol", "EURUSD"])
    assert rc in (None, 0)
    assert mt5.sent_orders == []
    assert store.orders == {}
    rows = _log_rows(log_path)
    assert not [r for r in rows if r["action"] == "RECOMMENDED"]
    assert [r for r in rows if r["action"] == "DRY-RUN-BUY"]


# ---------------- report.py: RECOMMENDED ----------------

CFG_REPORT = {
    "fund": {"total_capital_usd": 10000, "desks": {
        "forex": {"manager": "Yuling Pan", "capital_usd": 2500},
        "xauusd": {"manager": "Yumi", "capital_usd": 2500},
        "crypto": {"manager": "Rich", "capital_usd": 2500},
        "us_securities": {"manager": "Kathy", "capital_usd": 2500}}},
    "risk": {"max_drawdown_pct": 10.0, "desk_warning_pct": 5.0},
}


def _write_log_with_recommended(tmp_path):
    path = tmp_path / "decisions-log.csv"
    rows = [
        {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
         "action": "BUY", "reason": "lenh 1", "manager": "Yuling Pan"},
        {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
         "action": "RECOMMENDED",
         "reason": ("RECOMMENDED BUY EURUSD 0.01 lot @ 103.0 "
                    "(SL 101.5, TP 106.0) [cho xac nhan, pending abc12345]"),
         "manager": "Yuling Pan"},
        {"date": "2026-11-27", "desk": "crypto", "symbol": "BTCUSD",
         "action": "BLOCKED-DAILY-LIMIT", "reason": "da dat 1 lenh hom nay",
         "manager": "Rich"},
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=decisions.HEADER)
        w.writeheader()
        w.writerows(rows)
    return path


def test_report_handles_recommended(tmp_path):
    log = _write_log_with_recommended(tmp_path)
    rep = build_report(CFG_REPORT, log_path=log,
                       state_path=tmp_path / "khong-co.json",
                       today="2026-11-27")
    # Khuyen nghi KHONG dem vao lenh da dat / P&L / vi the mo.
    assert rep["totals"]["trades"] == 1
    assert rep["trades_today"] == {"EURUSD": 1}
    assert rep["totals"]["blocked"] == 1
    assert rep["open_positions"] == []
    # Nhung van hien ro la dang cho xac nhan.
    assert rep["recommended_total"] == 1
    assert len(rep["recommended"]) == 1
    assert rep["recommended"][0]["symbol"] == "EURUSD"
    assert "abc12345" in rep["recommended"][0]["reason"]
    text = format_report(rep)
    assert "cho xac nhan" in text
    assert "abc12345" in text
    assert "chua dat lenh" in text
