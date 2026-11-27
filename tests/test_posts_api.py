"""Test API bai dang phan tich (webapi.py: /api/posts, /api/publish).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), theo mau tests/test_webapi.py.
Kho bai dang duoc gia bang PostStore tam (monkeypatch
webapi.PostStore); Telegram duoc gia bang ham fake (outbox list);
khong goi MT5 that, khong gui Telegram that.
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

from diamondx10 import posts as posts_mod
from diamondx10.posts import PostStore
from diamondx10.webapi import app, create_app
from diamondx10 import webapi


# --- HTTP helper (stdlib) ---

def _req(base, method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type") or ""
            if "application/json" in ctype:
                return resp.status, json.loads(body)
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, body


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
            status, _ = _get(base, "/api/status")
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
    yield url
    stop()


# --- Fake Telegram + kho tam ---

class FakeTelegram:
    """Gui gia: ghi text vao outbox, tra True (khong goi mang)."""

    def __init__(self):
        self.outbox = []

    def send_message(self, text, cfg=None, **kwargs):
        self.outbox.append(text)
        return True


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """PostStore tam + fake Telegram; tra (store, fake)."""
    store = PostStore(tmp_path / "posts.json")
    monkeypatch.setattr(webapi, "PostStore", lambda *a, **k: store)
    fake = FakeTelegram()
    monkeypatch.setattr(posts_mod.telegram_mod, "send_message",
                        fake.send_message)
    # Endpoint doc config that tu config.yaml local (telegram.enabled
    # = true) nen fake van duoc goi; monkeypatch o tren chan gui that.
    return store, fake


def _seed(store):
    rows = [
        {"id": "0000000a", "created_utc": "2026-11-27T08:00:00+00:00",
         "desk": "forex", "analyst": "Yuling Pan", "symbol": "EURUSD",
         "action": "BUY", "confidence": 0.8, "summary": "Bai cu.",
         "drivers": [], "risks": [], "entry": 1.10, "sl": 1.05,
         "tp": 1.20, "source": "manual", "verdict_created_utc": None},
        {"id": "0000000b", "created_utc": "2026-11-27T09:00:00+00:00",
         "desk": "crypto", "analyst": "Rich", "symbol": "BTCUSD",
         "action": "SELL", "confidence": 0.7, "summary": "Bai giua.",
         "drivers": [], "risks": [], "entry": 60000.0, "sl": 61000.0,
         "tp": 58000.0, "source": "manual", "verdict_created_utc": None},
        {"id": "0000000c", "created_utc": "2026-11-27T10:00:00+00:00",
         "desk": "forex", "analyst": "Yuling Pan", "symbol": "EURUSD",
         "action": "NEUTRAL", "confidence": 0.5, "summary": "Bai moi.",
         "drivers": [], "risks": [], "entry": None, "sl": None,
         "tp": None, "source": "synthesis",
         "verdict_created_utc": "2026-11-27T07:00:00+00:00"},
    ]
    store._save(rows)
    return rows


# --- GET /api/posts ---

def test_get_posts_empty(base, tmp_store):
    status, body = _get(base, "/api/posts")
    assert status == 200
    assert body == {"posts": []}


def test_get_posts_newest_first_limit_desk(base, tmp_store):
    store, _fake = tmp_store
    _seed(store)
    status, body = _get(base, "/api/posts")
    assert status == 200
    assert [row["id"] for row in body["posts"]] == [
        "0000000c", "0000000b", "0000000a"]
    # Du truong API theo hop dong.
    row = body["posts"][0]
    assert set(row) == {"id", "created_utc", "desk", "analyst", "symbol",
                        "action", "confidence", "summary", "drivers",
                        "risks", "entry", "sl", "tp", "source",
                        "verdict_created_utc"}
    status, body = _get(base, "/api/posts?limit=2")
    assert status == 200
    assert [row["id"] for row in body["posts"]] == ["0000000c", "0000000b"]
    status, body = _get(base, "/api/posts?desk=crypto")
    assert status == 200
    assert [row["id"] for row in body["posts"]] == ["0000000b"]
    status, body = _get(base, "/api/posts?desk=forex&limit=1")
    assert status == 200
    assert [row["id"] for row in body["posts"]] == ["0000000c"]


# --- POST /api/posts ---

def test_post_posts_buy_returns_201_and_sends_telegram(base, tmp_store):
    store, fake = tmp_store
    payload = {"desk": "forex", "symbol": "EURUSD", "action": "BUY",
               "summary": "PTKT BUY, PTCB mua.", "confidence": 0.8,
               "entry": 1.10, "sl": 1.05, "tp": 1.20,
               "drivers": ["ECB giu lai suat"], "risks": ["CPI cao"]}
    status, body = _post(base, "/api/posts", payload)
    assert status in (200, 201)
    post = body["post"]
    assert post["desk"] == "forex"
    assert post["symbol"] == "EURUSD"
    assert post["action"] == "BUY"
    assert post["analyst"] == "Yuling Pan"
    assert post["source"] == "manual"
    assert post["drivers"] == ["ECB giu lai suat"]
    assert len(store.list_posts()) == 1
    assert len(fake.outbox) == 1
    assert "EURUSD" in fake.outbox[0] and "BUY" in fake.outbox[0]


def test_post_posts_neutral_sends_nothing(base, tmp_store):
    store, fake = tmp_store
    payload = {"desk": "forex", "symbol": "EURUSD", "action": "NEUTRAL",
               "summary": "PTKT HOLD, cho them."}
    status, body = _post(base, "/api/posts", payload)
    assert status in (200, 201)
    assert body["post"]["action"] == "NEUTRAL"
    assert body["post"]["confidence"] == 0.0
    assert fake.outbox == []


def test_post_posts_validation_400s(base, tmp_store):
    store, fake = tmp_store
    good = {"desk": "forex", "symbol": "EURUSD", "action": "BUY",
            "summary": "PTKT BUY."}
    for bad in (
            {**good, "action": "HOLD"},
            {**good, "action": "MUA"},
            {k: v for k, v in good.items() if k != "summary"},
            {k: v for k, v in good.items() if k != "desk"},
            {k: v for k, v in good.items() if k != "symbol"},
            {k: v for k, v in good.items() if k != "action"},
            {**good, "summary": "   "},
            {**good, "confidence": 1.5},
            {**good, "drivers": "khong phai list"},
    ):
        status, body = _post(base, "/api/posts", bad)
        assert status == 400, bad
    assert store.list_posts() == []
    assert fake.outbox == []


# --- POST /api/publish ---

def test_post_publish_creates_posts_from_synthesis(base, tmp_store,
                                                   monkeypatch):
    store, fake = tmp_store

    def fake_synthesize(cfg, desk, symbol=None, publish=False,
                        post_store=None, **kwargs):
        assert publish is True
        target = post_store if post_store is not None else store
        post, _ = target.publish_post(
            desk=desk, symbol=symbol or "EURUSD", action="BUY",
            summary="PTKT BUY, PTCB mua.", confidence=0.8,
            entry=1.10, sl=1.05, tp=1.20, source="synthesis",
            verdict_created_utc="2026-11-27T07:00:00+00:00", cfg=cfg)
        return 0

    monkeypatch.setattr(webapi, "cmd_synthesize", fake_synthesize)
    status, body = _post(base, "/api/publish",
                         {"desk": "forex", "symbol": "EURUSD"})
    assert status == 200
    assert len(body["posts"]) == 1
    assert body["posts"][0]["action"] == "BUY"
    assert body["posts"][0]["source"] == "synthesis"
    assert len(fake.outbox) == 1
    # Chay lai: dedupe (cung verdict_created_utc) -> khong co bai moi.
    status, body = _post(base, "/api/publish",
                         {"desk": "forex", "symbol": "EURUSD"})
    assert status == 200
    assert body["posts"] == []
    assert len(fake.outbox) == 1


def test_post_publish_bad_desk_400(base, tmp_store):
    status, body = _post(base, "/api/publish", {"desk": "stocks"})
    assert status == 400


def test_post_publish_synthesize_error_500(base, tmp_store, monkeypatch):
    monkeypatch.setattr(webapi, "cmd_synthesize",
                        lambda *a, **k: 1)
    status, body = _post(base, "/api/publish", {"desk": "forex"})
    assert status == 500
