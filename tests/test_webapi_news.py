"""Test GET /api/news-cards (webapi.py + newsfeed.py) va fix log
streaming PYTHONUNBUFFERED (webapi._spawn_proc).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), giong test_webapi_logs.py. Kho the
tin duoc tro toi thu muc tam qua monkeypatch
diamondx10.newsfeed.NEWS_CARD_STORE — khong dung file that o
decisions/. Khong goi MT5 that, khong gui Telegram that.

Xac thuc giong test_webapi_logs.py: moi request qua _req; gap 401
thi _ensure_auth() lay session cookie bang dung flow OTP.
"""
import json
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from diamondx10 import telegram, webapi
from diamondx10.data.news import NewsArticle
from diamondx10.newsfeed import NewsCardStore
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
    application = create_app()
    _APP["app"] = application
    url, stop = _run_server(application)
    yield url
    stop()


# --- Kho the tin gia (so gia, khong dung so that) ---

def _seed_cards(path):
    """3 the gia: forex co impact, xauusd cho phan tich, crypto tier 3."""
    store = NewsCardStore(path=path)
    created, skipped = store.publish_cards([
        {"id": "news-1", "title": "Fed holds rates",
         "link": "https://example.invalid/fed",
         "source": "Example News", "summary": "Fed keeps rates steady.",
         "tier": 1, "desk": "forex", "analyst": "Yuling Pan",
         "published_utc": "2026-11-27T09:00:00+00:00",
         "created_utc": "2026-11-27T10:00:00+00:00",
         "impact": {"impact": "positive", "direction": "buy",
                    "confidence": 0.75,
                    "summary": "Steady rates support EURUSD.",
                    "affected_symbol": "EURUSD",
                    "verdict_created_utc": "2026-11-27T11:00:00+00:00"}},
        {"id": "news-2", "title": "Gold ETF inflows",
         "link": "https://example.invalid/gold",
         "source": "Example Press", "summary": "Inflows rise.",
         "tier": 2, "desk": "xauusd", "analyst": "Yumi",
         "published_utc": "2026-11-27T11:00:00+00:00",
         "created_utc": "2026-11-27T12:00:00+00:00",
         "impact": None},
        {"id": "news-3", "title": "BTC leak rumor",
         "link": "https://example.invalid/btc",
         "source": "Example Leak", "summary": "Unverified rumor.",
         "tier": 3, "desk": "crypto", "analyst": "Rich",
         "published_utc": "2026-11-27T08:00:00+00:00",
         "created_utc": "2026-11-27T09:00:00+00:00",
         "impact": {"impact": "negative", "direction": "sell",
                    "confidence": 0.8,
                    "summary": "Rumor pressures BTCUSD.",
                    "affected_symbol": "BTCUSD",
                    "verdict_created_utc": "2026-11-27T11:00:00+00:00"}},
    ])
    assert (created, skipped) == (3, 0)
    return store


@pytest.fixture()
def store_path(tmp_path, monkeypatch):
    """Kho the tin tro toi file tam; tra Path cua file kho."""
    from diamondx10 import newsfeed

    path = tmp_path / "news-cards.json"
    monkeypatch.setattr(newsfeed, "NEWS_CARD_STORE", path)
    return path


# --- GET /api/news-cards ---

def test_news_cards_requires_auth(base):
    """Khong co cookie session thi 401 (giong cac /api/* khac)."""
    status, _body, _hdrs = _raw_req(base, "GET", "/api/news-cards")
    assert status == 401


def test_news_cards_newest_first(base, store_path):
    _seed_cards(store_path)
    status, body = _get(base, "/api/news-cards")
    assert status == 200
    assert [c["id"] for c in body["cards"]] == [
        "news-2", "news-1", "news-3"]


def test_news_cards_desk_filter(base, store_path):
    _seed_cards(store_path)
    status, body = _get(base, "/api/news-cards?desk=crypto")
    assert status == 200
    assert [c["id"] for c in body["cards"]] == ["news-3"]
    status, body = _get(base, "/api/news-cards?desk=forex")
    assert [c["id"] for c in body["cards"]] == ["news-1"]
    status, body = _get(base, "/api/news-cards?desk=khong-co")
    assert status == 200
    assert body["cards"] == []


def test_news_cards_limit_clamps(base, store_path):
    _seed_cards(store_path)
    status, body = _get(base, "/api/news-cards?limit=2")
    assert status == 200
    assert len(body["cards"]) == 2
    # limit=0 kep ve 1 (khong tra rong vi limit hop le toi thieu la 1).
    status, body = _get(base, "/api/news-cards?limit=0")
    assert status == 200
    assert len(body["cards"]) == 1
    # limit vuot tran kep ve 200 — chi co 3 the nen tra ca 3.
    status, body = _get(base, "/api/news-cards?limit=500")
    assert status == 200
    assert len(body["cards"]) == 3
    # limit khong phai so thi FastAPI tra 422 truoc khi vao handler
    # (giong /api/posts) — khong phai loi cua endpoint.
    status, body = _get(base, "/api/news-cards?limit=abc")
    assert status == 422


def test_news_cards_impact_payload(base, store_path):
    """The co impact vs the cho phan tich (impact null) deu nam
    trong payload — feed hien impact nhu comment, the chua co thi
    hien trang thai dang cho."""
    _seed_cards(store_path)
    status, body = _get(base, "/api/news-cards")
    assert status == 200
    by_id = {c["id"]: c for c in body["cards"]}
    impact = by_id["news-1"]["impact"]
    assert impact["impact"] == "positive"
    assert impact["direction"] == "buy"
    assert impact["confidence"] == 0.75
    assert impact["affected_symbol"] == "EURUSD"
    assert impact["summary"] == "Steady rates support EURUSD."
    assert impact["verdict_created_utc"] == "2026-11-27T11:00:00+00:00"
    assert by_id["news-2"]["impact"] is None
    assert by_id["news-2"]["tier"] == 2
    assert by_id["news-3"]["tier"] == 3


def test_news_cards_missing_store_empty(base, store_path):
    """Kho chua co file thi tra list rong, 200 — khong bao gio 500."""
    assert not store_path.exists()
    status, body = _get(base, "/api/news-cards")
    assert status == 200
    assert body == {"cards": []}


def test_news_cards_corrupt_store_empty(base, store_path):
    """Kho hong (JSON sai) thi tra list rong, 200 — khong traceback."""
    store_path.write_text("{khong phai json", encoding="utf-8")
    status, body = _get(base, "/api/news-cards")
    assert status == 200
    assert body == {"cards": []}


# --- Fix log streaming: PYTHONUNBUFFERED=1 o _spawn_proc ---

def test_spawn_proc_sets_pythonunbuffered():
    """Tien trinh con spawn qua _spawn_proc thay
    PYTHONUNBUFFERED=1 trong env (co che cua fix log streaming)."""
    proc = webapi._spawn_proc(
        [sys.executable, "-c",
         "import os, sys; sys.stdout.write("
         "os.environ.get('PYTHONUNBUFFERED', ''))"])
    out, _err = proc.communicate(timeout=10)
    assert proc.returncode == 0
    assert out == "1"


def test_live_log_lines_visible_while_running(base, monkeypatch):
    """Hoi quy chinh cua fix log streaming: tien trinh con in KHONG
    flush — neu khong co PYTHONUNBUFFERED=1 thi stdout bi dem theo
    khoi (pipe) va /api/logs khong thay dong nao cho toi khi tien
    trinh thoat. Voi fix, cac dong da thay DUOC KHI tien trinh van
    dang chay (running=true)."""
    real_spawn = webapi._spawn_proc
    script = ("import time\n"
              "for i in range(5):\n"
              "    print(f'line{i}')\n"
              "    time.sleep(0.2)\n"
              "time.sleep(2)\n")
    monkeypatch.setattr(
        webapi, "_spawn_proc",
        lambda argv: real_spawn([sys.executable, "-c", script]))
    try:
        # Baseline: so dong log live da co tu cac test truoc.
        status, before = _get(base, "/api/logs?process=live")
        assert status == 200
        baseline = before["total"]
        status, body = _post(base, "/api/live/start",
                             {"mode": "recommend", "desk": "forex"})
        assert status == 200 and body["ok"] is True
        deadline = time.time() + 5
        seen_while_running = None
        while time.time() < deadline:
            status, body = _get(
                base, f"/api/logs?process=live&after={baseline}")
            assert status == 200
            if body["running"] is True and "line0" in body["lines"]:
                seen_while_running = body
                break
            time.sleep(0.05)
        assert seen_while_running is not None, (
            "khong thay dong log nao khi tien trinh van dang chay — "
            "log streaming bi dem (thieu PYTHONUNBUFFERED=1)")
        assert "line0" in seen_while_running["lines"]
    finally:
        _post(base, "/api/live/stop")


# --- i18n frontend: vi/en phai dong bo (khoa moi newsCard.*) ---

def test_frontend_i18n_parity():
    """webui/src/i18n.tsx: tap khoa VI phai bang tap khoa EN
    (I18nKey = keyof typeof VI nen TS cung bat, day la phong thu
    o tang test). Khoa the tin moi phai co o ca 2 ngon ngu."""
    path = (Path(__file__).resolve().parents[1] / "webui" / "src"
            / "i18n.tsx")
    text = path.read_text(encoding="utf-8")
    vi_text, rest = text.split("const EN", 1)
    en_text = rest.split("const STRINGS", 1)[0]

    def _keys(block):
        return set(re.findall(r"^  '([^']+)':", block, flags=re.M))

    vi_keys, en_keys = _keys(vi_text), _keys(en_text)
    assert vi_keys == en_keys, (
        f"chi co o vi: {sorted(vi_keys - en_keys)}; "
        f"chi co o en: {sorted(en_keys - vi_keys)}")
    for key in ("newsCard.label", "newsCard.impactTitle",
                "newsCard.awaitingAnalysis", "newsCard.affectedSymbol",
                "mgr.testMode", "mgr.testModeHint",
                "feed.testBadge", "feed.emptyNoNews",
                "newsFetch.loadNow", "newsFetch.loading",
                "newsFetch.done", "newsFetch.errors",
                "newsFetch.failed", "newsFetch.notConfigured",
                "newsFetch.empty",
                "newsAuto.label", "newsAuto.interval", "newsAuto.save",
                "newsAuto.lastFetch", "newsAuto.nextFetch",
                "newsAuto.never", "newsAuto.on", "newsAuto.off",
                "newsAuto.invalidInterval"):
        assert key in vi_keys and key in en_keys
    # Khoa TeamNews cu da bi xoa cung muc rieng (gop vao feed).
    assert not any(k.startswith("teamNews.") for k in vi_keys)


# --- Favicon (dau kim cuong + X, webui/public/favicon.svg) ---

def test_favicon_served(base):
    """GET /favicon.svg tra 200 + SVG that (khong doi auth, nhu GET /)."""
    request = urllib.request.Request(base + "/favicon.svg")
    with urllib.request.urlopen(request, timeout=10) as resp:
        assert resp.status == 200
        assert "image/svg+xml" in (resp.headers.get("Content-Type") or "")
        raw = resp.read()
    assert raw.lstrip().startswith(b"<svg")


def test_favicon_in_built_index():
    """Build React da dem favicon vao: index.html co link icon va
    file ton tai o src/diamondx10/static/."""
    static_dir = (Path(__file__).resolve().parents[1] / "src"
                  / "diamondx10" / "static")
    assert (static_dir / "favicon.svg").is_file()
    index = (static_dir / "index.html").read_text(encoding="utf-8")
    assert "favicon.svg" in index
    assert 'rel="icon"' in index


# --- Sua config theo dong (muc news:) ---

def test_apply_news_settings_no_news_section():
    text = "language: vi\nfund:\n  total_capital_usd: 10000\n"
    out = webapi._apply_news_settings_to_config_text(
        text, {"test_mode": "true"})
    assert "news:\n  test_mode: true\n" in out
    assert "language: vi" in out
    assert "total_capital_usd: 10000" in out


def test_apply_news_settings_existing_block_keeps_keys():
    text = ("news:\n  max_age_days: 2\n  filters:\n"
            "    blacklist_keywords: [\"spam\"]\nfund:\n  total_capital_usd: 1\n")
    out = webapi._apply_news_settings_to_config_text(
        text, {"test_mode": "true",
               "auto_fetch_enabled": "false",
               "auto_fetch_interval_min": "5"})
    assert "  test_mode: true" in out
    assert "  auto_fetch_enabled: false" in out
    assert "  auto_fetch_interval_min: 5" in out
    assert "blacklist_keywords" in out
    assert "total_capital_usd: 1" in out
    # Khoa moi chen trong khoi news:, truoc khoa cap cao nhat ke tiep.
    assert out.index("test_mode") < out.index("fund:")


def test_apply_news_settings_replaces_existing_key():
    text = "news:\n  test_mode: false\n  auto_fetch_interval_min: 5\n"
    out = webapi._apply_news_settings_to_config_text(
        text, {"test_mode": "true",
               "auto_fetch_interval_min": "30"})
    assert "  test_mode: true" in out
    assert "  auto_fetch_interval_min: 30" in out
    assert out.count("test_mode:") == 1
    assert out.count("auto_fetch_interval_min:") == 1


# --- Che do TEST tin tuc (GET/POST /api/news-test-mode) ---

@pytest.fixture()
def cfg_file(tmp_path, monkeypatch):
    """config.yaml tam (monkeypatch DEFAULT_CONFIG_PATH); tra Path."""
    path = tmp_path / "config.yaml"
    path.write_text("language: vi\n", encoding="utf-8")
    monkeypatch.setattr(webapi, "DEFAULT_CONFIG_PATH", path)
    return path


def test_news_test_mode_get_default_false(base, cfg_file):
    status, body = _get(base, "/api/news-test-mode")
    assert status == 200
    assert body == {"test_mode": False}


def test_news_test_mode_post_persists(base, cfg_file):
    status, body = _post(base, "/api/news-test-mode",
                         {"test_mode": True})
    assert status == 200
    assert body == {"test_mode": True}
    text = cfg_file.read_text(encoding="utf-8")
    assert "news:" in text
    assert "test_mode: true" in text
    assert "language: vi" in text  # khoa khac giu nguyen
    status, body = _get(base, "/api/news-test-mode")
    assert body == {"test_mode": True}
    # Tat lai: ghi false, khong tao khoa trung.
    status, body = _post(base, "/api/news-test-mode",
                         {"test_mode": False})
    assert body == {"test_mode": False}
    text = cfg_file.read_text(encoding="utf-8")
    assert text.count("test_mode:") == 1
    assert "test_mode: false" in text


def test_news_test_mode_post_existing_news_block(base, cfg_file):
    cfg_file.write_text(
        "language: vi\nnews:\n  max_age_days: 2\n  test_mode: false\n",
        encoding="utf-8")
    status, body = _post(base, "/api/news-test-mode",
                         {"test_mode": True})
    assert status == 200 and body == {"test_mode": True}
    text = cfg_file.read_text(encoding="utf-8")
    assert "max_age_days: 2" in text
    assert text.count("test_mode:") == 1


def test_news_test_mode_post_invalid_400(base, cfg_file):
    for bad in ({"test_mode": "yes"}, {"test_mode": 1}, {}):
        status, body = _post(base, "/api/news-test-mode", bad)
        assert status == 400, body
        assert "detail" in body


def test_news_test_mode_post_missing_config_404_no_create(
        base, tmp_path, monkeypatch):
    missing = tmp_path / "config.yaml"
    assert not missing.exists()
    monkeypatch.setattr(webapi, "DEFAULT_CONFIG_PATH", missing)
    status, body = _post(base, "/api/news-test-mode",
                         {"test_mode": True})
    assert status == 404
    assert not missing.exists()  # khong tu tao config


def test_news_test_mode_requires_auth(base):
    status, _body, _hdrs = _raw_req(base, "GET", "/api/news-test-mode")
    assert status == 401


# --- Lay tin ngay (POST /api/news-fetch) ---

def _fake_articles():
    """2 bai tin gia (NewsArticle that) cho fetcher gia."""
    return [
        NewsArticle(title="Fed holds rates",
                    link="https://example.invalid/fed",
                    source="Example News", summary="Fed keeps rates.",
                    desk_tags=["forex"], trust_tier=1),
        NewsArticle(title="Gold ETF inflows",
                    link="https://example.invalid/gold",
                    source="Example Press", summary="Inflows rise.",
                    desk_tags=["xauusd"], trust_tier=2),
    ]


@pytest.fixture()
def news_cfg_file(tmp_path, monkeypatch):
    """config.yaml tam CO muc news: (nguon gia) + kho the tam."""
    from diamondx10 import newsfeed

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "language: vi\nnews:\n  max_age_days: 2\n"
        "  sources:\n    - {name: fake, enabled: true}\n",
        encoding="utf-8")
    monkeypatch.setattr(webapi, "DEFAULT_CONFIG_PATH", cfg)
    store_path = tmp_path / "news-cards.json"
    monkeypatch.setattr(newsfeed, "NEWS_CARD_STORE", store_path)
    return cfg, store_path


def _fake_run_news_factory(articles, calls):
    def _fake_run_news(news_cfg, desk=None, max_age_days=2, **kwargs):
        calls.append((desk, max_age_days))
        return {"fetched": len(articles), "matched": len(articles),
                "new": len(articles), "errors": [],
                "articles": list(articles)}

    return _fake_run_news


def test_news_fetch_ok_and_cards(base, news_cfg_file, monkeypatch):
    _cfg, store_path = news_cfg_file
    calls = []
    monkeypatch.setattr(
        webapi, "run_news",
        _fake_run_news_factory(_fake_articles(), calls))
    status, body = _post(base, "/api/news-fetch", {})
    assert status == 200, body
    assert body["fetched"] == 2
    assert body["matched"] == 2
    assert body["new"] == 2
    assert body["cards_created"] == 2
    assert body["errors"] == []
    # Luot lay dung tat ca desk (desk=None) nhu `news --all`.
    assert calls == [(None, 2)]
    # The tin da len feed, impact=None (dang cho phan tich).
    status, body = _get(base, "/api/news-cards")
    assert status == 200
    assert len(body["cards"]) == 2
    assert all(c["impact"] is None for c in body["cards"])
    assert {c["desk"] for c in body["cards"]} == {"forex", "xauusd"}


def test_news_fetch_dedupe_no_duplicates(
        base, news_cfg_file, monkeypatch):
    """Lay lai cung tin: khong tao the trung (publish_cards dedupe
    theo id + NewsStore MD5)."""
    _cfg, store_path = news_cfg_file
    monkeypatch.setattr(
        webapi, "run_news",
        _fake_run_news_factory(_fake_articles(), []))
    status, first = _post(base, "/api/news-fetch", {})
    assert status == 200 and first["cards_created"] == 2
    status, second = _post(base, "/api/news-fetch", {})
    assert status == 200
    assert second["cards_created"] == 0
    status, body = _get(base, "/api/news-cards")
    assert len(body["cards"]) == 2


def test_news_fetch_sends_no_telegram(
        base, news_cfg_file, monkeypatch):
    """Vong lay tin KHONG gui Telegram: outbox gia van rong sau khi
    lay tin (Telegram chi di qua duong dang bai / verdict)."""
    _cfg, store_path = news_cfg_file
    sent = []
    monkeypatch.setattr(
        telegram, "send_message",
        lambda text, **kw: sent.append(text) or True)
    monkeypatch.setattr(
        webapi, "run_news",
        _fake_run_news_factory(_fake_articles(), []))
    status, body = _post(base, "/api/news-fetch", {})
    assert status == 200
    assert sent == []


def test_news_fetch_unconfigured_400(base, cfg_file, monkeypatch):
    """Chua cau hinh nguon tin thi 400 ro rang — khong success rong,
    khong traceback."""
    calls = []
    monkeypatch.setattr(
        webapi, "run_news",
        _fake_run_news_factory(_fake_articles(), calls))
    status, body = _post(base, "/api/news-fetch", {})
    assert status == 400, body
    assert "Chua cau hinh nguon tin" in body["detail"]
    assert calls == []  # khong goi run_news khi chua cau hinh


def test_news_fetch_requires_auth(base):
    status, _body, _hdrs = _raw_req(base, "POST", "/api/news-fetch", {})
    assert status == 401


# --- Tu dong lay tin (GET/POST /api/news-auto-fetch) ---

def _wait_auto_state(base, predicate, timeout=10.0):
    """Poll GET /api/news-auto-fetch den khi predicate(state) dung."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        status, last = _get(base, "/api/news-auto-fetch")
        assert status == 200, last
        if predicate(last):
            return last
        time.sleep(0.1)
    return last


def test_news_auto_fetch_get_default(base, cfg_file):
    status, body = _get(base, "/api/news-auto-fetch")
    assert status == 200
    assert body["enabled"] is False
    assert body["interval_min"] == 5
    assert body["last_fetch_utc"] is None
    assert body["next_fetch_utc"] is None


def test_news_auto_fetch_post_persists_and_clamps(
        base, cfg_file):
    # 0 kep ve 1.
    status, body = _post(base, "/api/news-auto-fetch",
                         {"enabled": True, "interval_min": 0})
    assert status == 200, body
    assert body["enabled"] is True
    assert body["interval_min"] == 1
    text = cfg_file.read_text(encoding="utf-8")
    assert "auto_fetch_enabled: true" in text
    assert "auto_fetch_interval_min: 1" in text
    # 999 kep ve 60.
    status, body = _post(base, "/api/news-auto-fetch",
                         {"enabled": True, "interval_min": 999})
    assert status == 200 and body["interval_min"] == 60
    assert "auto_fetch_interval_min: 60" in cfg_file.read_text(
        encoding="utf-8")
    # Tat lai de vong lap idle.
    status, body = _post(base, "/api/news-auto-fetch",
                         {"enabled": False, "interval_min": 5})
    assert status == 200 and body["enabled"] is False
    assert body["interval_min"] == 5


def test_news_auto_fetch_post_invalid(base, cfg_file):
    for bad in ({"enabled": "yes", "interval_min": 5},
                {"enabled": True, "interval_min": "5"},
                {"enabled": True, "interval_min": True},
                {"enabled": True, "interval_min": 2.5}):
        status, body = _post(base, "/api/news-auto-fetch", bad)
        assert status == 400, body
    # Tat lai (phong khi 1 case nao do lot luoi bat vong lap).
    _post(base, "/api/news-auto-fetch",
          {"enabled": False, "interval_min": 5})


def test_news_auto_fetch_post_missing_config_404_no_create(
        base, tmp_path, monkeypatch):
    missing = tmp_path / "config.yaml"
    assert not missing.exists()
    monkeypatch.setattr(webapi, "DEFAULT_CONFIG_PATH", missing)
    status, body = _post(base, "/api/news-auto-fetch",
                         {"enabled": True, "interval_min": 5})
    assert status == 404
    assert not missing.exists()


def test_news_auto_fetch_scheduled_sets_last_next(
        base, news_cfg_file, monkeypatch):
    """Bat auto-fetch: vong nen lay tin ngay 1 luot (khong doi het
    khoang), last_fetch_utc duoc set, next_fetch_utc ~ interval sau.
    Khong gui Telegram."""
    _cfg, store_path = news_cfg_file
    sent = []
    monkeypatch.setattr(
        telegram, "send_message",
        lambda text, **kw: sent.append(text) or True)
    monkeypatch.setattr(
        webapi, "run_news",
        _fake_run_news_factory(_fake_articles(), []))
    try:
        status, body = _post(base, "/api/news-auto-fetch",
                             {"enabled": True, "interval_min": 1})
        assert status == 200 and body["enabled"] is True
        state = _wait_auto_state(
            base, lambda s: s["last_fetch_utc"] is not None,
            timeout=10.0)
        assert state["last_fetch_utc"] is not None, state
        last = datetime.fromisoformat(
            state["last_fetch_utc"].replace("Z", "+00:00"))
        nxt = datetime.fromisoformat(
            state["next_fetch_utc"].replace("Z", "+00:00"))
        assert 50 <= (nxt - last).total_seconds() <= 70
        assert sent == []  # vong tu dong khong gui Telegram
        # The tin da duoc dang (dedupe: chi 2 the).
        status, body = _get(base, "/api/news-cards")
        assert len(body["cards"]) == 2
    finally:
        _post(base, "/api/news-auto-fetch",
              {"enabled": False, "interval_min": 5})
        # Vong lap thay tat trong ~5 giay: next_fetch_utc ve None.
        _wait_auto_state(
            base, lambda s: s["next_fetch_utc"] is None, timeout=10.0)


def test_news_auto_fetch_requires_auth(base):
    status, _body, _hdrs = _raw_req(
        base, "GET", "/api/news-auto-fetch")
    assert status == 401
