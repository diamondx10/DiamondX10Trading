"""Test endpoint ngon ngu + tin doi (webapi.py, quy tac 51-52).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), theo dung kieu tests/test_webapi.py.
Config that chi dung file tam (monkeypatch DEFAULT_CONFIG_PATH) —
KHONG bao gio ghi vao config.yaml that cua repo. Kho tin / verdict /
briefing cung dung file tam.
"""
import json
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from diamondx10 import synthesis as synthesis_mod
from diamondx10 import webapi
from diamondx10.webapi import create_app

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
    application = create_app()
    url, stop = _run_server(application)
    _AUTH_HEADERS.update(_signin(url, application))
    yield url
    stop()


@pytest.fixture()
def cfg_file(tmp_path, monkeypatch):
    """config.yaml tam co san khoa khac + comment; tra Path."""
    path = tmp_path / "config.yaml"
    path.write_text(
        "# config tam cho test\n"
        "fund:\n"
        "  name: DiamondX10\n"
        "  total_capital_usd: 10000\n"
        "telegram:\n"
        "  enabled: false\n",
        encoding="utf-8")
    monkeypatch.setattr(webapi, "DEFAULT_CONFIG_PATH", path)
    return path


def _seed_news_store(path):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE seen_articles ("
        "  article_hash TEXT PRIMARY KEY,"
        "  article_title TEXT, article_url TEXT,"
        "  desks TEXT, trust_tier INTEGER, source TEXT,"
        "  pub_date TEXT, seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.execute(
        "INSERT INTO seen_articles (article_hash, article_title, "
        "article_url, desks, trust_tier, source, pub_date, seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("h1", "Fed giu nguyen lai suat", "https://x.test/1",
         "forex", 2, "Reuters", "2026-11-27T10:00:00Z",
         "2026-11-27 10:00:00"))
    conn.execute(
        "INSERT INTO seen_articles (article_hash, article_title, "
        "article_url, desks, trust_tier, source, pub_date, seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("h2", "Gia vang lap dinh moi", "https://x.test/2",
         "xauusd", 2, "Bloomberg", "2026-11-27T11:00:00Z",
         "2026-11-27 11:00:00"))
    conn.execute(
        "INSERT INTO seen_articles (article_hash, article_title, "
        "article_url, desks, trust_tier, source, pub_date, seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("h3", "Fed cu — tin cu hon cung desk forex",
         "https://x.test/3", "forex", 3, "x.com",
         "2026-11-26T09:00:00Z", "2026-11-26 09:00:00"))
    conn.commit()
    conn.close()


# --- GET / POST /api/language ---

def test_language_default_vi_when_key_missing(base, cfg_file):
    status, body = _get(base, "/api/language")
    assert status == 200
    assert body == {"language": "vi"}


def test_language_round_trip_vi_en_vi(base, cfg_file):
    status, body = _post(base, "/api/language", {"language": "en"})
    assert status == 200
    assert body == {"language": "en"}
    assert cfg_file.read_text(encoding="utf-8").count("language: en") == 1
    status, body = _get(base, "/api/language")
    assert status == 200
    assert body == {"language": "en"}
    status, body = _post(base, "/api/language", {"language": "vi"})
    assert status == 200
    assert body == {"language": "vi"}
    status, body = _get(base, "/api/language")
    assert body == {"language": "vi"}


def test_language_post_preserves_other_keys_and_comments(base, cfg_file):
    _post(base, "/api/language", {"language": "en"})
    text = cfg_file.read_text(encoding="utf-8")
    assert "# config tam cho test" in text
    assert "total_capital_usd: 10000" in text
    assert "telegram:" in text and "enabled: false" in text
    assert "language: en" in text
    # Doi lan 2: thay dong cu, khong them dong moi.
    _post(base, "/api/language", {"language": "vi"})
    text = cfg_file.read_text(encoding="utf-8")
    assert text.count("language:") == 1
    assert "language: vi" in text


def test_language_post_invalid_400(base, cfg_file):
    for bad in ("fr", "EN", "vi-VN", "", None, 123):
        status, body = _post(base, "/api/language", {"language": bad})
        assert status == 400, f"gia tri {bad!r} phai bi 400"
        assert "detail" in body
    status, body = _post(base, "/api/language", {})
    assert status == 400
    # Config khong bi doi boi cac request loi.
    assert "language:" not in cfg_file.read_text(encoding="utf-8")


def test_language_post_missing_config_no_create(base, tmp_path, monkeypatch):
    missing = tmp_path / "config.yaml"
    assert not missing.exists()
    monkeypatch.setattr(webapi, "DEFAULT_CONFIG_PATH", missing)
    status, body = _post(base, "/api/language", {"language": "en"})
    assert status in (400, 404)
    assert "detail" in body
    assert "config.yaml" in body["detail"]
    assert not missing.exists(), "khong duoc tu tao config nua voi"


def test_language_invalid_value_in_config_falls_back_vi(base, cfg_file):
    cfg_file.write_text("language: fr\nfund:\n  name: X\n",
                        encoding="utf-8")
    status, body = _get(base, "/api/language")
    assert status == 200
    assert body == {"language": "vi"}


# --- GET /api/team-news ---

def test_team_news_empty_data(base, tmp_path, monkeypatch):
    """Kho tin / verdict / briefing deu trong -> list rong, null."""
    news_path = tmp_path / "news-history.db"
    monkeypatch.setattr(webapi, "NEWS_STORE_PATH", news_path)
    monkeypatch.setattr(synthesis_mod, "VERDICT_STORE",
                        tmp_path / "fundamental-verdicts.json")
    briefings = tmp_path / "briefings"
    briefings.mkdir()
    monkeypatch.setattr(webapi, "BRIEFINGS_DIR", briefings)
    status, body = _get(base, "/api/team-news")
    assert status == 200
    assert body["items"] == []
    assert body["briefings"] == []
    assert set(body["verdicts"]) == {"forex", "xauusd", "crypto",
                                     "us_securities"}
    assert all(v is None for v in body["verdicts"].values())


def test_team_news_shape_with_data(base, tmp_path, monkeypatch):
    news_path = tmp_path / "news-history.db"
    _seed_news_store(news_path)
    monkeypatch.setattr(webapi, "NEWS_STORE_PATH", news_path)
    verdict_path = tmp_path / "fundamental-verdicts.json"
    monkeypatch.setattr(synthesis_mod, "VERDICT_STORE", verdict_path)
    verdict_path.write_text(json.dumps({
        "forex": {"desk": "forex", "analyst": "Yuling Pan",
                  "direction": "buy", "confidence": 0.8,
                  "drivers": ["USD yeu"], "risks": [],
                  "note": "", "created_utc": "2026-11-27T10:00:00Z"},
    }), encoding="utf-8")
    briefings = tmp_path / "briefings"
    briefings.mkdir()
    (briefings / "briefing-forex-20261127-1200.md").write_text(
        "# BRIEFING", encoding="utf-8")
    monkeypatch.setattr(webapi, "BRIEFINGS_DIR", briefings)

    status, body = _get(base, "/api/team-news")
    assert status == 200
    assert {"items", "verdicts", "briefings"} <= set(body)

    # Moi desk toi da 1 bai — bai cu hon cung desk forex bi loai.
    assert len(body["items"]) == 2
    by_desk = {i["desk"]: i for i in body["items"]}
    assert by_desk["forex"]["title"] == "Fed giu nguyen lai suat"
    assert by_desk["forex"]["source"] == "Reuters"
    assert by_desk["forex"]["tier"] == 2
    assert by_desk["forex"]["analyst"] == "Yuling Pan"
    assert by_desk["forex"]["time"] == "2026-11-27T10:00:00Z"
    assert by_desk["forex"]["briefing_url"] == (
        "briefings/briefing-forex-20261127-1200.md")
    assert by_desk["xauusd"]["analyst"] == "Yumi"
    assert by_desk["xauusd"]["briefing_url"] is None

    assert body["verdicts"]["forex"] == {"direction": "buy",
                                         "confidence": 0.8}
    assert body["verdicts"]["crypto"] is None
    assert body["verdicts"]["us_securities"] is None

    assert len(body["briefings"]) == 1
    assert body["briefings"][0]["desk"] == "forex"
    assert body["briefings"][0]["file"] == "briefing-forex-20261127-1200.md"
    assert body["briefings"][0]["time"]


def test_team_news_corrupt_verdict_store_degrades(base, tmp_path, monkeypatch):
    """Kho verdict hong -> verdicts null het, endpoint van 200."""
    news_path = tmp_path / "news-history.db"
    monkeypatch.setattr(webapi, "NEWS_STORE_PATH", news_path)
    verdict_path = tmp_path / "fundamental-verdicts.json"
    verdict_path.write_text("{khong phai json", encoding="utf-8")
    monkeypatch.setattr(synthesis_mod, "VERDICT_STORE", verdict_path)
    briefings = tmp_path / "briefings"
    briefings.mkdir()
    monkeypatch.setattr(webapi, "BRIEFINGS_DIR", briefings)
    status, body = _get(base, "/api/team-news")
    assert status == 200
    assert body["items"] == []
    assert all(v is None for v in body["verdicts"].values())
