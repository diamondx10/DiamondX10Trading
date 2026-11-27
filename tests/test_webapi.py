"""Test FastAPI backend (webapi.py) + core dat lenh cho (listener.py).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx). Khong goi MT5 that, khong gui
Telegram that, khong mo trinh duyet that. Kill switch that chi bat
tam trong test roi tat lai o finally; kho verdict chi dung file tam.
"""
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from diamondx10 import decisions, killswitch, webapi
from diamondx10 import synthesis as synthesis_mod
from diamondx10.listener import place_pending_order
from diamondx10.webapi import app, create_app


# --- HTTP helper (stdlib) ---
# Moi /api/* (tru /api/auth/*) doi cookie phien: fixture `base` dang
# nhap 1 lan bang OTP doc trong process (xem _signin) roi _get/_post
# tu kem cookie do. _req_full tra them headers de doc Set-Cookie.

_AUTH_HEADERS = {}


def _req_full(base, method, path, payload=None, headers=None):
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data,
                                     headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type") or ""
            if "application/json" in ctype:
                return resp.status, json.loads(body), resp.headers
            return resp.status, body, resp.headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body), exc.headers
        except ValueError:
            return exc.code, body, exc.headers


def _req(base, method, path, payload=None, headers=None):
    status, body, _ = _req_full(base, method, path, payload, headers)
    return status, body


def _get(base, path, headers=None):
    return _req(base, "GET", path,
                headers=_AUTH_HEADERS if headers is None else headers)


def _post(base, path, payload=None, headers=None):
    return _req(base, "POST", path, payload if payload is not None else {},
                headers=_AUTH_HEADERS if headers is None else headers)


def _signin(base, application):
    """Dang nhap bang OTP: gia Telegram gui duoc, doc ma OTP trong
    process qua app.state.otp_manager.peek_otp(), verify, tra header
    Cookie de goi cac route duoc bao ve."""
    from diamondx10 import telegram as telegram_mod
    orig_send = telegram_mod.send_message
    orig_status = telegram_mod.setup_status
    telegram_mod.send_message = lambda *a, **k: True
    telegram_mod.setup_status = lambda cfg: {
        "ready": True, "enabled": True, "has_token": True,
        "has_chat_id": True, "missing": []}
    try:
        # File test khac co the da yeu cau OTP tren cung app module
        # trong vong 15 giay truoc: gap 429 thi cho het cooldown roi
        # thu lai (chi xay ra khi chay nhieu file trong 1 process).
        for _attempt in range(3):
            status, body, _ = _req_full(
                base, "POST", "/api/auth/request-otp", {}, headers={})
            if status == 200:
                break
            if status == 429:
                time.sleep(int(body.get("retry_after") or 15) + 0.2)
                continue
            break
        assert status == 200, body
        assert body == {"sent": True}
        code = application.state.otp_manager.peek_otp()
        assert code is not None
        status, body, headers = _req_full(
            base, "POST", "/api/auth/verify-otp", {"code": code},
            headers={})
        assert status == 200, body
    finally:
        telegram_mod.send_message = orig_send
        telegram_mod.setup_status = orig_status
    cookie = (headers.get("Set-Cookie") or "").split(";")[0].strip()
    assert cookie.startswith("dx10_session=")
    return {"Cookie": cookie}


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _run_server(application):
    """Chay uvicorn trong thread, tra (base_url, stop_fn)."""
    port = _free_port()
    config = uvicorn.Config(application, host="127.0.0.1", port=port,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            # /api/auth/status khong doi dang nhap (dung de doi server).
            status, _ = _get(base, "/api/auth/status", headers={})
            if status == 200:
                break
        except Exception:  # noqa: BLE001 — cho server len
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("server webapi khong len trong 15 giay")

    def _stop():
        server.should_exit = True
        thread.join(timeout=10)

    return base, _stop


@pytest.fixture(scope="module")
def base():
    url, stop = _run_server(app)
    _AUTH_HEADERS.update(_signin(url, app))
    yield url
    stop()


# --- Fake cho core dat lenh / store ---

class FakePendingStore:
    """Store gia theo dung hop dong cua pending.py."""

    def __init__(self, orders=None):
        self.orders = dict(orders or {})

    def get(self, order_id):
        return self.orders.get(order_id)

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

    def mark_cancelled(self, order_id):
        self.orders[order_id]["status"] = "cancelled"
        return True


def _order(**overrides):
    order = {"desk": "forex", "manager": "Yuling Pan", "symbol": "EURUSD",
             "action": "BUY", "entry": 1.10, "sl": 1.05, "tp": 1.20,
             "volume": 0.01, "risk_usd": 75.0, "status": "pending",
             "ticket": None}
    order.update(overrides)
    return order


class FakeMT5:
    """MT5 gia: tai khoan demo, gia + order_check tuy chinh duoc."""

    TRADE_RETCODE_DONE = 10009
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, bid=1.10, trade_mode=0,
                 server="Exness-MT5Trial7", order_check_retcode=0,
                 order_send_retcode=10009):
        self._bid = bid
        self._trade_mode = trade_mode
        self._server = server
        self._order_check_retcode = order_check_retcode
        self._order_send_retcode = order_send_retcode
        self.sent_orders = []

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self._bid, ask=self._bid + 0.001)

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode,
                               server=self._server, demo=True)

    def order_check(self, request):
        return SimpleNamespace(retcode=self._order_check_retcode)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=self._order_send_retcode,
                               order=777001, comment="Done")

    def last_error(self):
        return (0, "ok")


class FakeProc:
    """Tien trinh gia cho live / listener (poll/terminate/wait)."""

    def __init__(self):
        self._rc = None
        self.terminated = False

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._rc = 0


def _cfg():
    return {"telegram": {"enabled": True, "chat_id": "1234567890",
                         "max_entry_deviation_pct": 1.0},
            "mt5": {"demo_only": True}}


# --- Core dat lenh cho (listener.place_pending_order) ---

def test_place_core_kill_switch_blocks(monkeypatch, tmp_path):
    """Kill switch ON -> core tu choi, khong goi order_send."""
    ks_path = tmp_path / "kill-switch.json"
    killswitch.engage("test", by="webapi-test", path=ks_path,
                      audit_path=tmp_path / "audit-log.jsonl")
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5()
    try:
        result = place_pending_order(_cfg(), mt5, store, "ord-1",
                                     kill_switch_path=str(ks_path))
    finally:
        killswitch.disengage(by="webapi-test", path=ks_path,
                             audit_path=tmp_path / "audit-log.jsonl")
    assert result["ok"] is False
    assert result["ticket"] is None
    assert "Kill switch" in result["reason"]
    assert mt5.sent_orders == []
    assert store.orders["ord-1"]["status"] == "pending"


def test_place_core_happy_path(monkeypatch, tmp_path):
    """Kill switch OFF + demo + gia khop -> dat xong, ticket + placed."""
    monkeypatch.setattr(decisions, "LOG",
                        tmp_path / "decisions-log.csv")
    ks_path = tmp_path / "kill-switch.json"
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5()
    result = place_pending_order(_cfg(), mt5, store, "ord-1",
                                 kill_switch_path=str(ks_path))
    assert result["ok"] is True
    assert result["ticket"] == 777001
    assert len(mt5.sent_orders) == 1
    assert store.orders["ord-1"]["status"] == "placed"
    assert store.orders["ord-1"]["ticket"] == 777001


def test_place_core_unknown_order():
    store = FakePendingStore({})
    result = place_pending_order(_cfg(), FakeMT5(), store, "khong-co")
    assert result["ok"] is False
    assert result["ticket"] is None


# --- API: trang thai / vi the / tin hieu ---

def test_status_shape(base):
    status, body = _get(base, "/api/status")
    assert status == 200
    for key in ("equity", "capital", "drawdown_pct", "kill_switch_on",
                "mt5_ok", "telegram_ready", "live_running",
                "listener_running", "desks"):
        assert key in body, f"thieu key {key}"
    assert body["mt5_ok"] is False  # Linux: khong co MT5
    assert isinstance(body["kill_switch_on"], bool)
    assert isinstance(body["telegram_ready"], bool)
    assert isinstance(body["desks"], list)
    for desk in body["desks"]:
        assert {"desk", "equity", "open_positions"} <= set(desk)


def test_positions_json(base):
    status, body = _get(base, "/api/positions")
    assert status == 200
    assert isinstance(body["positions"], list)


def test_signals_without_mt5(base):
    status, body = _get(base, "/api/signals?desk=forex")
    assert status == 200
    assert body["desk"] == "forex"
    assert body["signals"], "phai co tin hieu mo phong khi khong co MT5"
    for sig in body["signals"]:
        assert {"symbol", "action", "rsi", "atr", "patterns",
                "regime"} <= set(sig)
        assert sig["action"] in ("BUY", "SELL", "HOLD")
        assert isinstance(sig["patterns"], list)


def test_synthesis_missing_verdict(base, monkeypatch):
    """Chua co verdict -> fa_direction null, rationale noi ro PTCB."""
    monkeypatch.setattr(webapi, "load_verdict",
                        lambda store_path, desk: None)
    status, body = _get(base, "/api/synthesis?desk=forex")
    assert status == 200
    assert body["desk"] == "forex"
    assert body["items"]
    for item in body["items"]:
        assert {"symbol", "ta_action", "fa_direction", "fa_confidence",
                "recommendation", "size_factor", "verdict_age_hours",
                "rationale"} <= set(item)
        assert item["fa_direction"] is None
        assert "PTCB" in item["rationale"]


def test_decisions_newest_first(base):
    status, body = _get(base, "/api/decisions?lines=5")
    assert status == 200
    rows = body["rows"]
    assert isinstance(rows, list) and len(rows) <= 5
    for row in rows:
        assert {"time", "symbol", "action", "reason", "desk",
                "manager"} <= set(row)


def test_briefings_empty_ok(base):
    status, body = _get(base, "/api/briefings")
    assert status == 200
    assert isinstance(body["briefings"], list)


def test_backtest_null_when_missing(base):
    status, body = _get(base, "/api/backtest")
    assert status == 200
    assert "backtest" in body


def test_bars_simulated_fallback(base):
    status, body = _get(base, "/api/bars?symbol=EURUSD&n=10")
    assert status == 200
    assert body["symbol"] == "EURUSD"
    assert len(body["bars"]) == 10
    for bar in body["bars"]:
        assert {"time", "open", "high", "low", "close"} <= set(bar)


def test_news_empty_store_ok(base):
    status, body = _get(base, "/api/news?desk=forex")
    assert status == 200
    assert body["desk"] == "forex"
    assert isinstance(body["articles"], list)
    assert "note" in body


def test_briefing_invalid_desk(base):
    status, body = _post(base, "/api/briefing",
                         {"desk": "khong-co", "days": 3})
    assert status == 200
    assert body["ok"] is False
    assert body["file"] is None


# --- API: lenh cho (dung chung validation voi listener) ---

def test_pending_place_kill_switch_blocks(base, monkeypatch):
    """Kill switch ON -> POST place tra ok:false, khong dat lenh."""
    store = FakePendingStore({"ord-1": _order()})
    monkeypatch.setattr(webapi, "PendingOrderStore", lambda: store)
    killswitch.engage("test webapi", by="webapi-test")
    try:
        status, body = _post(base, "/api/pending/ord-1/place")
    finally:
        killswitch.disengage(by="webapi-test")
    assert status == 200
    assert body["ok"] is False
    assert body["ticket"] is None
    assert "Kill switch" in body["reason"]
    assert store.orders["ord-1"]["status"] == "pending"


def test_pending_place_unknown_404(base):
    status, body = _post(base, "/api/pending/khong-co/place")
    assert status == 404
    assert "detail" in body


def test_pending_ignore(base, monkeypatch):
    store = FakePendingStore({"ord-9": _order()})
    monkeypatch.setattr(webapi, "PendingOrderStore", lambda: store)
    status, body = _post(base, "/api/pending/ord-9/ignore")
    assert status == 200
    assert body == {"ok": True}
    assert store.orders["ord-9"]["status"] == "cancelled"
    status, _ = _post(base, "/api/pending/khong-co/ignore")
    assert status == 404


def test_pending_list(base):
    status, body = _get(base, "/api/pending")
    assert status == 200
    assert isinstance(body["pending"], list)


# --- API: kill switch ---

def test_kill_switch_toggle(base):
    try:
        status, body = _post(base, "/api/kill-switch", {"on": True})
        assert status == 200
        assert body == {"kill_switch_on": True}
        assert killswitch.is_engaged() is True
        status, body = _post(base, "/api/kill-switch", {"on": False})
        assert status == 200
        assert body == {"kill_switch_on": False}
        assert killswitch.is_engaged() is False
    finally:
        killswitch.disengage(by="webapi-test")


# --- API: verdict ---

def test_verdicts_paste_and_invalid(base, monkeypatch, tmp_path):
    """Verdict hop le -> luu + doc lai duoc; verdict sai -> 400."""
    monkeypatch.setattr(synthesis_mod, "VERDICT_STORE",
                        tmp_path / "fundamental-verdicts.json")
    good = {"desk": "forex", "analyst": "Yuling Pan",
            "direction": "buy", "confidence": 0.8,
            "drivers": ["USD yeu"], "risks": ["CPI cao"], "note": "test"}
    status, body = _post(base, "/api/verdicts", {"verdict": good})
    assert status == 200
    assert body["ok"] is True
    status, body = _get(base, "/api/verdicts")
    assert status == 200
    assert len(body["verdicts"]) == 1
    item = body["verdicts"][0]
    assert item["desk"] == "forex"
    assert item["direction"] == "buy"
    assert item["confidence"] == 0.8
    assert item["age_hours"] is not None
    bad = dict(good, direction="moon")
    status, body = _post(base, "/api/verdicts", {"verdict": bad})
    assert status == 400
    assert "detail" in body


# --- API: muse-send (muse_browser chua san sang) ---

def test_muse_send_blocked_without_browser(base, monkeypatch, tmp_path):
    """sys.modules co muse_browser=None -> job bao loi, khong crash."""
    briefings = tmp_path / "briefings"
    briefings.mkdir()
    (briefings / "briefing-forex-20261127-1200.md").write_text(
        "# BRIEFING TEST", encoding="utf-8")
    monkeypatch.setattr(webapi, "BRIEFINGS_DIR", briefings)
    monkeypatch.setitem(sys.modules, "diamondx10.muse_browser", None)
    status, body = _post(base, "/api/muse-send",
                         {"file": "briefing-forex-20261127-1200.md"})
    assert status == 200
    assert body["status"] == "sending"
    job_id = body["job_id"]
    deadline = time.time() + 10
    final = None
    while time.time() < deadline:
        status, final = _get(base, f"/api/muse-send/{job_id}")
        assert status == 200
        if final["status"] != "sending":
            break
        time.sleep(0.1)
    assert final["status"] == "error"
    assert "Muse browser chua san sang" in final["reason"]
    assert final["verdict"] is None


def test_muse_send_path_traversal_400(base):
    status, body = _post(base, "/api/muse-send",
                         {"file": "../config.yaml"})
    assert status == 400
    status, body = _get(base, "/api/muse-send/khong-co-job")
    assert status == 404


# --- API: live / listener (tien trinh gia) ---

def test_live_start_stop_fake_proc(base, monkeypatch):
    spawned = []
    procs = []

    def _fake_spawn(argv):
        proc = FakeProc()
        spawned.append(argv)
        procs.append(proc)
        return proc

    monkeypatch.setattr(webapi, "_spawn_proc", _fake_spawn)
    status, body = _get(base, "/api/live")
    assert status == 200 and body["running"] is False
    status, body = _post(base, "/api/live/start",
                         {"mode": "recommend", "desk": "forex"})
    assert status == 200
    assert body["ok"] is True
    assert "--recommend-only" in spawned[0]
    assert "--desk" in spawned[0] and "forex" in spawned[0]
    status, body = _get(base, "/api/live")
    assert body["running"] is True
    assert body["mode"] == "recommend"
    status, body = _post(base, "/api/live/start",
                         {"mode": "auto", "desk": "forex"})
    assert body["ok"] is False  # da chay thi khong khoi dong lai
    status, body = _post(base, "/api/live/stop")
    assert status == 200 and body["ok"] is True
    assert procs[0].terminated is True
    status, body = _get(base, "/api/live")
    assert body["running"] is False


def test_listener_start_stop_fake_proc(base, monkeypatch):
    spawned = []

    def _fake_spawn(argv):
        spawned.append(argv)
        return FakeProc()

    monkeypatch.setattr(webapi, "_spawn_proc", _fake_spawn)
    status, body = _post(base, "/api/listener/start")
    assert status == 200
    assert body["ok"] is True
    assert "telegram-listen" in spawned[0]
    status, body = _get(base, "/api/listener")
    assert body["running"] is True
    status, body = _post(base, "/api/listener/stop")
    assert status == 200 and body["ok"] is True
    status, body = _get(base, "/api/listener")
    assert body["running"] is False


# --- Frontend tinh: GET / ---

def test_root_serves_built_index(base):
    status, body = _get(base, "/")
    assert status == 200
    assert isinstance(body, str) and "DiamondX10" in body


def test_root_no_frontend_json(tmp_path):
    """Static dir trong (chua build) -> JSON bao frontend chua build."""
    empty = tmp_path / "static"
    empty.mkdir()
    url, stop = _run_server(create_app(static_dir=empty))
    try:
        status, body = _get(url, "/")
        assert status == 200
        assert isinstance(body, dict)
        assert "frontend chua duoc build" in body["message"]
        # /api/status doi dang nhap; /api/auth/status mo de biet API
        # van chay.
        status, _ = _get(url, "/api/auth/status", headers={})
        assert status == 200  # API van chay
        status, _ = _get(url, "/api/status", headers={})
        assert status == 401  # chua dang nhap thi API bi chan
    finally:
        stop()


def test_root_fake_frontend_html(tmp_path):
    """Static dir co index.html -> tra HTML 200."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        "<html><body>DiamondX10 fake</body></html>", encoding="utf-8")
    url, stop = _run_server(create_app(static_dir=static))
    try:
        status, body = _get(url, "/")
        assert status == 200
        assert isinstance(body, str) and "DiamondX10 fake" in body
    finally:
        stop()
