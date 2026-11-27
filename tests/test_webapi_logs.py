"""Test manager console: GET /api/logs, POST /api/diagnostics,
POST /api/telegram-test (webapi.py + procman.py).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), giong test_webapi.py. Khong goi MT5
that, khong gui Telegram that. Tien trinh con deu la gia (in dong log
roi cho dung).

Xac thuc (worker OTP song song da bat bao ve /api/*): moi request qua
_req; gap 401 thi _ensure_auth() lay session cookie bang dung flow
OTP — POST /api/auth/request-otp, doc ma qua
app.state.otp_manager.peek_otp() (chi trong process, KHONG qua API),
POST /api/auth/verify-otp. Khi chua co auth thi khong can cookie,
buoc nay khong chay (request-otp 404 -> None).
"""
import io
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from diamondx10 import telegram, webapi
from diamondx10.webapi import create_app


# --- HTTP helper (stdlib) + cookie xu ly auth neu co ---

_AUTH = {"cookie": None, "tried": False}
_APP = {"app": None}  # app FastAPI cua fixture (de doc OTP qua peek_otp)


def _raw_req(base, method, path, payload=None, headers=None):
    """1 request tho, tra (status, body_json_or_str, headers)."""
    data = None
    hdrs = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data,
                                     headers=hdrs, method=method)
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


def _peek_code():
    """Ma OTP hien tai cua app trong fixture (None neu chua co)."""
    application = _APP.get("app")
    if application is None:
        return None
    manager = getattr(application.state, "otp_manager", None)
    if manager is None:
        return None
    try:
        return manager.peek_otp()
    except Exception:  # noqa: BLE001 — khong doc duoc ma thi thoi
        return None


def _obtain_session_cookie(base):
    """Lay cookie session khi /api/* doi auth; None neu khong co auth.

    Dung dung flow cua worker OTP: POST /api/auth/request-otp, doc
    ma qua app.state.otp_manager.peek_otp() (chi trong process),
    POST /api/auth/verify-otp, lay Set-Cookie. Neu khong co route
    auth (404) thi khong co auth, tra None. Neu gap 429 (cooldown
    15 giay) thi doi retry_after roi thu lai.
    """
    code = None
    for _ in range(4):
        code = _peek_code()
        if code:
            break
        status, body, _hdrs = _raw_req(
            base, "POST", "/api/auth/request-otp", {})
        if status == 404:
            return None
        if status == 429:
            wait = 1
            if isinstance(body, dict):
                try:
                    wait = float(body.get("retry_after") or 1)
                except (TypeError, ValueError):
                    wait = 1
            time.sleep(min(wait, 20) + 0.5)
            continue
        if status != 200:
            return None
        code = _peek_code()
        break
    if not code:
        return None
    status, _body, hdrs = _raw_req(
        base, "POST", "/api/auth/verify-otp", {"code": code})
    if status == 200 and hdrs.get("Set-Cookie"):
        return hdrs["Set-Cookie"].split(";", 1)[0]
    return None


def _ensure_auth(base):
    if _AUTH["tried"]:
        return _AUTH["cookie"]
    _AUTH["tried"] = True
    _AUTH["cookie"] = _obtain_session_cookie(base)
    return _AUTH["cookie"]


def _req(base, method, path, payload=None):
    headers = {}
    if _AUTH["cookie"]:
        headers["Cookie"] = _AUTH["cookie"]
    status, body, _hdrs = _raw_req(base, method, path, payload, headers)
    if status == 401:
        cookie = _ensure_auth(base)
        if cookie:
            headers["Cookie"] = cookie
            status, body, _hdrs = _raw_req(base, method, path, payload,
                                           headers)
    return status, body


def _get(base, path):
    return _req(base, "GET", path)


def _post(base, path, payload=None):
    return _req(base, "POST", path, payload if payload is not None else {})


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
            # /api/auth/status khong doi dang nhap (dung de doi server);
            # /api/status doi cookie nen khong dung lam probe nua.
            status, _ = _get(base, "/api/auth/status")
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
    # App moi (create_app) de OTPManager / SessionStore khong lan voi
    # app module-level ma cac file test khac dung (tranh cooldown OTP).
    application = create_app()
    _APP["app"] = application
    url, stop = _run_server(application)
    yield url
    stop()


# --- Fake tien trinh in dong log ---

class FakeProcLines:
    """Popen gia co stdout in san cac dong log (stderr rong)."""

    def __init__(self, lines):
        self.stdout = io.StringIO("".join(lines))
        self.stderr = io.StringIO("")
        self._rc = None
        self.terminated = False

    def poll(self):
        return self._rc

    @property
    def returncode(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._rc = 0


def _fake_spawn_factory(lines, spawned):
    def _fake_spawn(argv):
        spawned.append(list(argv))
        return FakeProcLines(lines)

    return _fake_spawn


def _wait_logs(base, process, total, timeout=5.0):
    """Doi den khi /api/logs co du `total` dong."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        status, last = _get(base, f"/api/logs?process={process}")
        assert status == 200, last
        if last["total"] >= total:
            return last
        time.sleep(0.05)
    return last


def _fake_cfg(monkeypatch):
    """Config gia cho telegram-test (khong dung so that)."""
    monkeypatch.setattr(
        webapi, "_load_cfg",
        lambda: {"telegram": {"enabled": True, "chat_id": "1234567890",
                             "max_entry_deviation_pct": 1.0},
                 "mt5": {"demo_only": True}})


# --- GET /api/logs ---

def test_logs_never_started_empty(base):
    """Tien trinh chua tung chay: buffer rong, running false."""
    status, body = _get(base, "/api/logs?process=diagnostics")
    assert status == 200
    assert body["process"] == "diagnostics"
    assert body["running"] is False
    assert body["started_utc"] is None
    assert body["exit_code"] is None
    assert body["lines"] == []
    assert body["total"] == 0


def test_logs_unknown_process_400(base):
    status, body = _get(base, "/api/logs?process=khong-co")
    assert status == 400
    assert "detail" in body


def test_live_start_logs_lines_and_cursor(base, monkeypatch):
    spawned = []
    monkeypatch.setattr(
        webapi, "_spawn_proc",
        _fake_spawn_factory(["live dong 1\n", "live dong 2\n",
                             "live dong 3\n"], spawned))
    try:
        status, body = _post(base, "/api/live/start",
                             {"mode": "recommend", "desk": "forex"})
        assert status == 200 and body["ok"] is True
        assert "--recommend-only" in spawned[0]
        body = _wait_logs(base, "live", 3)
        assert body["running"] is True
        assert body["started_utc"]
        assert body["exit_code"] is None
        assert body["lines"] == ["live dong 1", "live dong 2",
                                 "live dong 3"]
        assert body["total"] == 3
        # Cursor after=2 chi tra dong moi hon.
        status, body = _get(base, "/api/logs?process=live&after=2")
        assert status == 200
        assert body["total"] == 3
        assert body["lines"] == ["live dong 3"]
        status, body = _get(base, "/api/logs?process=live&after=3")
        assert body["lines"] == [] and body["total"] == 3
    finally:
        _post(base, "/api/live/stop")


def test_live_stop_keeps_buffered_lines(base, monkeypatch):
    spawned = []
    procs = []

    def _fake_spawn(argv):
        spawned.append(list(argv))
        proc = FakeProcLines(["giam sat\n"])
        procs.append(proc)
        return proc

    monkeypatch.setattr(webapi, "_spawn_proc", _fake_spawn)
    status, body = _post(base, "/api/live/start",
                         {"mode": "recommend", "desk": "forex"})
    assert status == 200 and body["ok"] is True
    _wait_logs(base, "live", 1)
    status, body = _post(base, "/api/live/stop")
    assert status == 200 and body["ok"] is True
    assert procs[0].terminated is True
    status, body = _get(base, "/api/live")
    assert body["running"] is False
    # Log van con sau khi dung, running false.
    status, body = _get(base, "/api/logs?process=live")
    assert status == 200
    assert body["running"] is False
    assert body["lines"] == ["giam sat"]
    assert body["total"] == 1


def test_listener_logs(base, monkeypatch):
    spawned = []
    monkeypatch.setattr(
        webapi, "_spawn_proc",
        _fake_spawn_factory(["listener san sang\n"], spawned))
    try:
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is True
        assert "telegram-listen" in spawned[0]
        body = _wait_logs(base, "listener", 1)
        assert body["running"] is True
        assert body["lines"] == ["listener san sang"]
    finally:
        _post(base, "/api/listener/stop")


# --- POST /api/diagnostics ---

def test_diagnostics_start_safe_mode_and_logs(base, monkeypatch):
    spawned = []
    monkeypatch.setattr(
        webapi, "_spawn_proc",
        _fake_spawn_factory(["[CHECK] moi truong ... OK\n",
                             "[CHECK] cau hinh ... OK\n"], spawned))
    try:
        status, body = _post(base, "/api/diagnostics")
        assert status == 200
        assert body["ok"] is True
        assert spawned[0][1] == "test_run.py"
        assert "--live-once" not in spawned[0]  # che do an toan: khong lenh
        body = _wait_logs(base, "diagnostics", 2)
        assert body["running"] is True
        assert body["lines"] == ["[CHECK] moi truong ... OK",
                                 "[CHECK] cau hinh ... OK"]
        # Da chay thi tu choi khoi dong lan 2.
        status, body = _post(base, "/api/diagnostics")
        assert status == 200
        assert body["ok"] is False
        assert "da chay" in body["reason"]
    finally:
        _stop_diag = webapi._stop_proc("diagnostics")
        assert _stop_diag is True
        status, body = _get(base, "/api/logs?process=diagnostics")
        assert body["running"] is False


# --- POST /api/telegram-test ---

def test_telegram_test_ok_with_fake_telegram(base, monkeypatch):
    _fake_cfg(monkeypatch)
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "fake-token-for-test")
    sent = []

    def _fake_send(text, **kwargs):
        sent.append(text)
        return True

    monkeypatch.setattr(telegram, "send_message", _fake_send)
    status, body = _post(base, "/api/telegram-test")
    assert status == 200
    assert body["ok"] is True
    assert body["reason"]
    assert len(sent) == 1


def test_telegram_test_not_ready(base, monkeypatch):
    monkeypatch.setattr(webapi, "_load_cfg",
                        lambda: {"telegram": {"enabled": False,
                                             "chat_id": "1234567890"}})
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    sent = []
    monkeypatch.setattr(telegram, "send_message",
                        lambda text, **kw: sent.append(text) or True)
    status, body = _post(base, "/api/telegram-test")
    assert status == 200
    assert body["ok"] is False
    assert "thieu" in body["reason"]
    assert sent == []  # chua san sang thi khong gui


# --- GET / van 200 ---

def test_root_still_200(base):
    status, body = _get(base, "/")
    assert status == 200
