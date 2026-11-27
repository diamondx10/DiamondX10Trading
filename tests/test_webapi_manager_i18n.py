"""Test ly do Manager dich theo ngon ngu (webapi.py + procman.py + i18n.py).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), theo dung kieu tests/test_webapi.py.
Ngon ngu doi bang cach monkeypatch webapi._load_cfg (tra config tam
co khoa `language:`); khong dung MT5 that, khong gui Telegram that.
Chi dung so gia (chat_id 1234567890).
"""
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

from diamondx10 import telegram as telegram_mod
from diamondx10 import webapi
from diamondx10.webapi import create_app

_AUTH_HEADERS = {}

# Cac manh tieng Viet khong dau cu — khong duoc xuat hien trong bat ky
# ly do nao tra ve cho Manager nua.
OLD_FRAGMENTS = ("da khoi dong", "da chay", "khong khoi dong",
                 "thoat ngay")


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
    orig_send = telegram_mod.send_message
    orig_status = telegram_mod.setup_status
    telegram_mod.send_message = lambda *a, **k: True
    telegram_mod.setup_status = lambda cfg: {
        "ready": True, "enabled": True, "has_token": True,
        "has_chat_id": True, "missing": []}
    try:
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
    application = create_app()
    url, stop = _run_server(application)
    _AUTH_HEADERS.update(_signin(url, application))
    yield url
    stop()


class FakeProc:
    """Tien trinh gia (poll/terminate/wait/kill); rc=None = con chay."""

    def __init__(self, rc=None):
        self._rc = rc
        self.returncode = rc
        self.terminated = False

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = 0
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._rc = 0
        self.returncode = 0


def _set_cfg(monkeypatch, lang, telegram=None):
    """Config tam cho _load_cfg: chi khoa language + telegram gia."""
    cfg = {"language": lang,
           "telegram": telegram if telegram is not None else {
               "enabled": True, "chat_id": "1234567890"},
           "mt5": {"demo_only": True}}
    monkeypatch.setattr(webapi, "_load_cfg", lambda: cfg)
    return cfg


def _stop_all(base):
    _post(base, "/api/live/stop")
    _post(base, "/api/listener/stop")
    webapi._stop_proc("diagnostics")


def _assert_no_old_fragments(reason):
    for fragment in OLD_FRAGMENTS:
        assert fragment not in reason, f"{fragment!r} trong {reason!r}"


# --- Khoi dong thanh cong: EN + VI ---

def test_listener_start_reason_english(base, monkeypatch):
    _set_cfg(monkeypatch, "en")
    monkeypatch.setattr(webapi, "_spawn_proc",
                        lambda argv: FakeProc())
    _stop_all(base)
    try:
        status, body = _post(base, "/api/listener/start")
        assert status == 200
        assert body["ok"] is True
        assert body["reason"] == "Telegram listener started"
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)


def test_listener_start_reason_vietnamese(base, monkeypatch):
    _set_cfg(monkeypatch, "vi")
    monkeypatch.setattr(webapi, "_spawn_proc",
                        lambda argv: FakeProc())
    _stop_all(base)
    try:
        status, body = _post(base, "/api/listener/start")
        assert status == 200
        assert body["ok"] is True
        assert body["reason"] == "Đã khởi động Telegram listener"
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)


def test_live_start_reason_english(base, monkeypatch):
    _set_cfg(monkeypatch, "en")
    monkeypatch.setattr(webapi, "_spawn_proc",
                        lambda argv: FakeProc())
    _stop_all(base)
    try:
        status, body = _post(base, "/api/live/start",
                             {"mode": "recommend", "desk": "forex"})
        assert status == 200
        assert body["ok"] is True
        assert body["reason"] == "Live started"
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)


# --- Da chay: tu choi, dich ca 2 ngon ngu ---

def test_already_running_reason_both_languages(base, monkeypatch):
    monkeypatch.setattr(webapi, "_spawn_proc",
                        lambda argv: FakeProc())
    _stop_all(base)
    try:
        _set_cfg(monkeypatch, "en")
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is True
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is False
        assert body["reason"] == "Telegram listener is already running"
        _assert_no_old_fragments(body["reason"])
        _set_cfg(monkeypatch, "vi")
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is False
        assert body["reason"] == "Telegram listener đang chạy"
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)


# --- Spawn loi + thoat ngay: dich, chi tiet ky thuat giu nguyen ---

def test_spawn_failure_reason_both_languages(base, monkeypatch):
    def _boom(argv):
        raise RuntimeError("boom-test")

    monkeypatch.setattr(webapi, "_spawn_proc", _boom)
    _stop_all(base)
    try:
        _set_cfg(monkeypatch, "en")
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is False
        assert body["reason"] == (
            "Could not start Telegram listener: boom-test")
        _assert_no_old_fragments(body["reason"])
        _set_cfg(monkeypatch, "vi")
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is False
        assert body["reason"] == (
            "Không khởi động được Telegram listener: boom-test")
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)


def test_exited_immediately_reason_both_languages(base, monkeypatch):
    monkeypatch.setattr(webapi, "_spawn_proc",
                        lambda argv: FakeProc(rc=1))
    _stop_all(base)
    try:
        _set_cfg(monkeypatch, "en")
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is False
        assert body["reason"] == (
            "Telegram listener exited immediately (code 1) — "
            "check config / MT5 / log")
        _assert_no_old_fragments(body["reason"])
        _set_cfg(monkeypatch, "vi")
        status, body = _post(base, "/api/listener/start")
        assert status == 200 and body["ok"] is False
        assert body["reason"] == (
            "Telegram listener thoát ngay (mã 1) — "
            "kiểm tra config / MT5 / log")
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)


# --- Diagnostics + live mode sai ---

def test_diagnostics_reason_translated(base, monkeypatch):
    monkeypatch.setattr(webapi, "_spawn_proc",
                        lambda argv: FakeProc())
    _stop_all(base)
    try:
        _set_cfg(monkeypatch, "en")
        status, body = _post(base, "/api/diagnostics")
        assert status == 200 and body["ok"] is True
        assert body["reason"] == "System check started"
        _assert_no_old_fragments(body["reason"])
        webapi._stop_proc("diagnostics")
        _set_cfg(monkeypatch, "vi")
        status, body = _post(base, "/api/diagnostics")
        assert status == 200 and body["ok"] is True
        assert body["reason"] == "Đã khởi động Kiểm tra hệ thống"
        _assert_no_old_fragments(body["reason"])
    finally:
        _stop_all(base)
        # Do don registry dung chung cua webapi (module-global): neu
        # khong go, file test chay sau (vd test_webapi_logs) se thay
        # "diagnostics" nhu da tung chay.
        webapi._MANAGER._procs.pop("diagnostics", None)
        webapi._PROCS.pop("diagnostics", None)


def test_live_bad_mode_reason_both_languages(base, monkeypatch):
    _set_cfg(monkeypatch, "en")
    status, body = _post(base, "/api/live/start",
                         {"mode": "bogus", "desk": "forex"})
    assert status == 200 and body["ok"] is False
    assert body["reason"] == "Invalid mode (choose recommend | auto)"
    _assert_no_old_fragments(body["reason"])
    _set_cfg(monkeypatch, "vi")
    status, body = _post(base, "/api/live/start",
                         {"mode": "bogus", "desk": "forex"})
    assert status == 200 and body["ok"] is False
    assert body["reason"] == "Chế độ không hợp lệ (chọn recommend | auto)"
    _assert_no_old_fragments(body["reason"])


# --- Telegram test: chua san sang + gui duoc ---

def test_telegram_test_not_ready_both_languages(base, monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    sent = []
    monkeypatch.setattr(telegram_mod, "send_message",
                        lambda text, **kw: sent.append(text) or True)
    _set_cfg(monkeypatch, "en",
             telegram={"enabled": False, "chat_id": "1234567890"})
    status, body = _post(base, "/api/telegram-test")
    assert status == 200 and body["ok"] is False
    assert body["reason"] == (
        "Telegram is not ready — missing: "
        "telegram.enabled is not turned on (config.yaml); "
        "bot token (environment variable DIAMONDX10_TELEGRAM_TOKEN)")
    _assert_no_old_fragments(body["reason"])
    _set_cfg(monkeypatch, "vi",
             telegram={"enabled": False, "chat_id": "1234567890"})
    status, body = _post(base, "/api/telegram-test")
    assert status == 200 and body["ok"] is False
    assert body["reason"] == (
        "Telegram chưa sẵn sàng — thiếu: "
        "telegram.enabled chưa bật (config.yaml); "
        "token bot (biến môi trường DIAMONDX10_TELEGRAM_TOKEN)")
    _assert_no_old_fragments(body["reason"])
    assert sent == []


def test_telegram_test_sent_both_languages(base, monkeypatch):
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "fake-token-for-test")
    sent = []

    def _fake_send(text, **kwargs):
        sent.append(text)
        return True

    monkeypatch.setattr(telegram_mod, "send_message", _fake_send)
    _set_cfg(monkeypatch, "en",
             telegram={"enabled": True, "chat_id": "1234567890"})
    status, body = _post(base, "/api/telegram-test")
    assert status == 200 and body["ok"] is True
    assert body["reason"] == "Test message sent to Telegram"
    _assert_no_old_fragments(body["reason"])
    _set_cfg(monkeypatch, "vi",
             telegram={"enabled": True, "chat_id": "1234567890"})
    status, body = _post(base, "/api/telegram-test")
    assert status == 200 and body["ok"] is True
    assert body["reason"] == "Đã gửi tin nhắn thử lên Telegram"
    _assert_no_old_fragments(body["reason"])
    assert len(sent) == 2


# --- Kill switch + logs: chi tiet loi HTTP 400 dich theo ngon ngu ---

def test_kill_switch_bad_field_both_languages(base, monkeypatch):
    _set_cfg(monkeypatch, "en")
    status, body = _post(base, "/api/kill-switch", {"on": "yes"})
    assert status == 400
    assert body["detail"] == "Field 'on' must be true/false"
    _set_cfg(monkeypatch, "vi")
    status, body = _post(base, "/api/kill-switch", {"on": "yes"})
    assert status == 400
    assert body["detail"] == "Trường 'on' phải là true/false"


def test_logs_bad_process_both_languages(base, monkeypatch):
    _set_cfg(monkeypatch, "en")
    status, body = _get(base, "/api/logs?process=nope")
    assert status == 400
    assert body["detail"] == (
        "Invalid process name: nope "
        "(choose live | listener | diagnostics)")
    _set_cfg(monkeypatch, "vi")
    status, body = _get(base, "/api/logs?process=nope")
    assert status == 400
    assert body["detail"] == (
        "Tên tiến trình không hợp lệ: nope "
        "(chọn live | listener | diagnostics)")
