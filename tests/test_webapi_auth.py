"""Test xac thuc OTP qua HTTP (webapi.py: /api/auth/* + middleware).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), theo mau tests/test_webapi.py.
Cookie doc tay tu header Set-Cookie. Telegram duoc gia bang ham
fake (outbox list); khong goi MT5 that, khong gui Telegram that.
Moi test dung 1 app moi (create_app) de phien / OTP khong lan nhau.
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

from diamondx10 import webapi
from diamondx10.webapi import create_app


# --- HTTP helper (stdlib, tra ca headers de doc Set-Cookie) ---

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


def _get(base, path, headers=None):
    return _req_full(base, "GET", path, headers=headers)


def _post(base, path, payload=None, headers=None):
    return _req_full(base, "POST", path,
                     payload if payload is not None else {},
                     headers=headers)


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
            status, _, _ = _get(base, "/api/auth/status")
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


def _cookie_header(headers):
    """'dx10_session=<token>' rut tu Set-Cookie (phan truoc ';')."""
    raw = headers.get("Set-Cookie") or ""
    return raw.split(";")[0].strip()


class FakeTelegram:
    """Gui gia: ghi text vao outbox, tra True (khong goi mang)."""

    def __init__(self):
        self.outbox = []

    def send_message(self, text, cfg=None, **kwargs):
        self.outbox.append(text)
        return True


@pytest.fixture
def server(monkeypatch):
    """App moi + server that + Telegram gia (ready, gui duoc)."""
    app = create_app()
    fake = FakeTelegram()
    monkeypatch.setattr(webapi.telegram, "send_message",
                        fake.send_message)
    monkeypatch.setattr(webapi.telegram, "setup_status",
                        lambda cfg: {"ready": True, "enabled": True,
                                     "has_token": True, "has_chat_id": True,
                                     "missing": []})
    url, stop = _run_server(app)
    yield url, app, fake
    stop()


def _request_otp(base):
    status, body, _ = _post(base, "/api/auth/request-otp", {})
    assert status == 200, body
    return body


def _signin(base, app):
    """Yeu cau OTP (Telegram gia) roi verify bang ma doc trong process.

    Tra header {"Cookie": "dx10_session=..."} de goi cac route
    duoc bao ve.
    """
    _request_otp(base)
    code = app.state.otp_manager.peek_otp()
    assert code is not None
    status, body, headers = _post(base, "/api/auth/verify-otp",
                                  {"code": code})
    assert status == 200, body
    cookie = _cookie_header(headers)
    assert cookie.startswith("dx10_session=")
    return {"Cookie": cookie}


# --- POST /api/auth/request-otp ---

def test_request_otp_sends_exactly_one_telegram_message(server):
    base, app, fake = server
    body = _request_otp(base)
    assert body == {"sent": True}
    assert len(fake.outbox) == 1
    code = app.state.otp_manager.peek_otp()
    assert code is not None and len(code) == 6
    assert code in fake.outbox[0]
    # Ma OTP KHONG bao gio nam trong response API.
    assert code not in json.dumps(body)
    assert "60" in fake.outbox[0]  # thoi han hieu luc trong tin nhan


def test_request_otp_cooldown_429(server):
    base, app, fake = server
    assert _request_otp(base) == {"sent": True}
    status, body, _ = _post(base, "/api/auth/request-otp", {})
    assert status == 429
    assert isinstance(body.get("retry_after"), int)
    assert 0 < body["retry_after"] <= 15
    assert len(fake.outbox) == 1  # lan bi chan khong gui them tin


# --- POST /api/auth/verify-otp ---

def test_verify_wrong_code_401(server):
    base, app, fake = server
    _request_otp(base)
    code = app.state.otp_manager.peek_otp()
    wrong = "000000" if code != "000000" else "000001"
    status, body, headers = _post(base, "/api/auth/verify-otp",
                                  {"code": wrong})
    assert status == 401
    assert body == {"reason": "invalid"}
    assert not headers.get("Set-Cookie")
    # Ma dung van con hieu luc sau 1 lan nhap sai.
    status, _, _ = _post(base, "/api/auth/verify-otp", {"code": code})
    assert status == 200


def test_verify_without_otp_401_no_otp(server):
    base, app, fake = server
    status, body, _ = _post(base, "/api/auth/verify-otp",
                            {"code": "123456"})
    assert status == 401
    assert body == {"reason": "no_otp"}


def test_verify_right_code_sets_cookie(server):
    base, app, fake = server
    _request_otp(base)
    code = app.state.otp_manager.peek_otp()
    status, body, headers = _post(base, "/api/auth/verify-otp",
                                  {"code": code})
    assert status == 200
    assert body == {"ok": True, "authenticated": True}
    raw = headers.get("Set-Cookie") or ""
    assert raw.startswith("dx10_session=")
    assert "HttpOnly" in raw
    assert "Max-Age=2592000" in raw  # 30 ngay
    assert "SameSite=lax" in raw
    assert "Path=/" in raw


def test_auth_status_with_and_without_cookie(server):
    base, app, fake = server
    status, body, _ = _get(base, "/api/auth/status")
    assert status == 200
    assert body == {"authenticated": False}
    headers = _signin(base, app)
    status, body, _ = _get(base, "/api/auth/status", headers=headers)
    assert status == 200
    assert body == {"authenticated": True}


# --- Route duoc bao ve: /api/status ---

def test_protected_status_needs_cookie(server):
    base, app, fake = server
    status, body, _ = _get(base, "/api/status")
    assert status == 401
    assert "detail" in body
    headers = _signin(base, app)
    status, body, _ = _get(base, "/api/status", headers=headers)
    assert status == 200
    assert "kill_switch_on" in body


def test_protected_routes_401_without_auth(server):
    base, app, fake = server
    for method, path in (("GET", "/api/positions"),
                         ("GET", "/api/posts"),
                         ("GET", "/api/language"),
                         ("POST", "/api/kill-switch")):
        if method == "GET":
            status, body, _ = _get(base, path)
        else:
            status, body, _ = _post(base, path, {"on": False})
        assert status == 401, (method, path, body)
    # Trang chu (SPA) van mo khong can dang nhap.
    status, _, _ = _get(base, "/")
    assert status == 200


# --- POST /api/auth/sign-out ---

def test_sign_out_invalidates_session(server):
    base, app, fake = server
    headers = _signin(base, app)
    status, body, resp_headers = _post(base, "/api/auth/sign-out",
                                       {}, headers=headers)
    assert status == 200
    assert body == {"ok": True}
    cleared = resp_headers.get("Set-Cookie") or ""
    assert "dx10_session=" in cleared and "Max-Age=0" in cleared
    # Cookie cu khong con dung duoc nua.
    status, _, _ = _get(base, "/api/status", headers=headers)
    assert status == 401
    status, body, _ = _get(base, "/api/auth/status", headers=headers)
    assert body == {"authenticated": False}


def test_sign_out_without_auth_401(server):
    base, app, fake = server
    status, body, _ = _post(base, "/api/auth/sign-out", {})
    assert status == 401


# --- Fallback: Telegram gui loi / chua cau hinh ---

def test_fallback_on_telegram_send_failure(server, monkeypatch, capsys):
    base, app, fake = server
    monkeypatch.setattr(webapi.telegram, "send_message",
                        lambda *a, **k: False)
    status, body, _ = _post(base, "/api/auth/request-otp", {})
    assert status == 200
    assert body.get("sent") is False
    assert body.get("fallback") == "terminal"
    assert body.get("reason")
    code = app.state.otp_manager.peek_otp()
    assert code is not None
    # Ma OTP KHONG nam trong bat ky response API nao.
    assert code not in json.dumps(body)
    # Ma duoc in ra console cua server (de doc tu terminal).
    assert code in capsys.readouterr().out
    # Ma fallback van dung duoc de dang nhap.
    status, _, _ = _post(base, "/api/auth/verify-otp", {"code": code})
    assert status == 200


def test_fallback_when_telegram_not_configured(server, monkeypatch):
    base, app, fake = server
    monkeypatch.setattr(webapi.telegram, "setup_status",
                        lambda cfg: {"ready": False, "enabled": False,
                                     "has_token": False,
                                     "has_chat_id": False,
                                     "missing": ["telegram.enabled"]})
    status, body, _ = _post(base, "/api/auth/request-otp", {})
    assert status == 200
    assert body.get("sent") is False
    assert body.get("fallback") == "terminal"
    assert fake.outbox == []  # khong co gang gui Telegram
    code = app.state.otp_manager.peek_otp()
    assert code not in json.dumps(body)


# --- App moi khong co phien cu ---

def test_fresh_app_has_no_sessions(server):
    base, app, fake = server
    headers = _signin(base, app)
    status, _, _ = _get(base, "/api/status", headers=headers)
    assert status == 200
    assert app.state.session_store.count() == 1
    app2 = create_app()
    assert app2.state.session_store.count() == 0
    assert app2.state.otp_manager.peek_otp() is None
    url2, stop2 = _run_server(app2)
    try:
        # Cookie cua app cu khong co gia tri tren app moi.
        status, _, _ = _get(url2, "/api/status", headers=headers)
        assert status == 401
        status, body, _ = _get(url2, "/api/auth/status", headers=headers)
        assert body == {"authenticated": False}
    finally:
        stop2()
