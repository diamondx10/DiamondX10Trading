"""Test GET /api/portfolio-risk (webapi.py).

Chay server that trong thread tren cong tam (uvicorn) roi goi bang
urllib stdlib (khong them httpx), theo mau tests/test_webapi_auth.py.
Moi test dung 1 app moi (create_app) de phien / OTP khong lan nhau.

Endpoint goi engine that diamondx10.portfolio_risk
(build_portfolio_risk_report) — test so that chay qua engine that
voi lich su + vi the gia da seed vao file tam (patch
portfolio_risk.DEFAULT_DB_PATH + data.history.DEFAULT_DB_PATH +
decisions.EQUITY_STATE de khong dong vao file runtime cua repo).
"""
import json
import random
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

from diamondx10 import decisions as decisions_mod
from diamondx10 import portfolio_risk as portfolio_risk_mod
from diamondx10 import webapi
from diamondx10.data import history as history_mod
from diamondx10.data.history import HistoryStore
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


def _signin(base, app):
    """Yeu cau OTP (Telegram gia) roi verify bang ma doc trong process.

    Tra header {"Cookie": "dx10_session=..."} de goi cac route
    duoc bao ve.
    """
    status, body, _ = _post(base, "/api/auth/request-otp", {})
    assert status == 200, body
    code = app.state.otp_manager.peek_otp()
    assert code is not None
    status, body, headers = _post(base, "/api/auth/verify-otp",
                                  {"code": code})
    assert status == 200, body
    cookie = _cookie_header(headers)
    assert cookie.startswith("dx10_session=")
    return {"Cookie": cookie}


def _cfg(tmp_path, history_path=None, mc_paths=1000):
    """Config toi thieu cho endpoint: von 10000, gioi han VaR mac dinh
    2% (engine), kho lich su o file tam, MC 1000 path cho test nhanh."""
    return {
        "fund": {"total_capital_usd": 10000},
        "risk": {"max_drawdown_pct": 10.0, "mc_paths": mc_paths},
        "trading": {"demo_only": True},
        "history": {"db_path": str(history_path or (tmp_path / "h.db")),
                    "default_timeframe": "M15"},
    }


def _seed_bars(path, symbol, start_price, seed=7, n=60):
    """Seed n bar M15 (random walk co dinh seed) vao HistoryStore."""
    rng = random.Random(seed)
    price = start_price
    bars = []
    t0 = 1764000000  # epoch co dinh, cach nhau 900s (M15)
    for i in range(n):
        price *= 1 + rng.gauss(0, 0.001)
        bars.append({"time": t0 + i * 900,
                     "open": price, "high": price * 1.0005,
                     "low": price * 0.9995, "close": price,
                     "volume": 10})
    with HistoryStore(str(path)) as store:
        store.upsert_bars(symbol, "M15", bars)
    return bars


# --- 401 khi chua dang nhap ---

def test_portfolio_risk_401_without_signin(server):
    base, app, fake = server
    status, body, _ = _get(base, "/api/portfolio-risk")
    assert status == 401
    assert "detail" in body


# --- 200 + payload rong khi khong co vi the / lich su ---

def test_portfolio_risk_empty_state(server, monkeypatch, tmp_path):
    base, app, fake = server
    monkeypatch.setattr(webapi, "_load_cfg",
                        lambda: _cfg(tmp_path))
    monkeypatch.setattr(decisions_mod, "EQUITY_STATE",
                        tmp_path / "no-state.json")
    # Kho lich su tam trong (khong co bar nao).
    HistoryStore(str(tmp_path / "h.db")).close()
    monkeypatch.setattr(portfolio_risk_mod, "DEFAULT_DB_PATH",
                        tmp_path / "h.db")
    monkeypatch.setattr(history_mod, "DEFAULT_DB_PATH",
                        tmp_path / "h.db")
    headers = _signin(base, app)
    status, body, _ = _get(base, "/api/portfolio-risk", headers=headers)
    assert status == 200, body
    assert body["has_positions"] is False
    assert body["demo"] is False  # endpoint khong truyen demo=True
    assert body["equity_usd"] == 10000
    assert body["symbols"] == []
    assert body["exposures"] == []
    var = body["var"]
    assert var["parametric_95"] == 0.0
    assert var["mc_95"] == 0.0
    assert var["historical_95"] == 0.0
    # Gioi han VaR mac dinh cua engine: 2% von (khong phai DD 10%).
    assert var["limit_usd"] == 200.0
    assert var["limit_pct"] == 2.0
    assert var["breached"] is False
    assert body["mc"]["paths"] == 1000  # tu cfg test (mac dinh 10000)
    assert body["mc"]["seed"] == 42
    assert body["component_var"] == []
    assert body["concentration"] == {"largest_symbol": None,
                                     "largest_share_pct": None}
    assert body["stress"] == []
    assert body["warnings"]  # co canh bao "khong co vi the mo"
    assert set(body) >= {"has_positions", "demo", "equity_usd", "symbols",
                         "exposures", "var", "mc", "component_var",
                         "concentration", "stress", "warnings", "notes"}


# --- So that voi lich su + vi the gia da seed (engine that) ---

def test_portfolio_risk_real_numbers(server, monkeypatch, tmp_path):
    base, app, fake = server
    history_path = tmp_path / "history.db"
    _seed_bars(history_path, "EURUSD", 1.09, seed=7)
    _seed_bars(history_path, "XAUUSD", 3650.0, seed=8)
    state_path = tmp_path / "equity-state.json"
    state_path.write_text(json.dumps({
        "guard": {"fund_curve": [10000, 10050],
                  "desk_curves": {}},
        "positions": [
            {"desk": "forex", "symbol": "EURUSD", "direction": "BUY",
             "entry": 1.09, "volume": 0.1, "contract_size": 100000,
             "opened_date": "2026-11-28"},
            {"desk": "xauusd", "symbol": "XAUUSD", "direction": "BUY",
             "entry": 3650.0, "volume": 0.1, "contract_size": 100,
             "opened_date": "2026-11-28"},
        ]}), encoding="utf-8")
    monkeypatch.setattr(webapi, "_load_cfg",
                        lambda: _cfg(tmp_path, history_path))
    monkeypatch.setattr(decisions_mod, "EQUITY_STATE", state_path)
    monkeypatch.setattr(portfolio_risk_mod, "DEFAULT_DB_PATH",
                        history_path)
    monkeypatch.setattr(history_mod, "DEFAULT_DB_PATH", history_path)
    headers = _signin(base, app)
    status, body, _ = _get(base, "/api/portfolio-risk", headers=headers)
    assert status == 200, body
    assert body["has_positions"] is True
    assert body["symbols"] == ["EURUSD", "XAUUSD"]
    assert body["equity_usd"] == 10050
    assert len(body["exposures"]) == 2
    notionals = {e["symbol"]: e["notional_usd"]
                 for e in body["exposures"]}
    # EURUSD 0.1 lot x 100000 x ~gia dong (~1.09) ≈ 10900;
    # XAUUSD 0.1 x 100 x ~3650 ≈ 36500.
    assert 10000 < notionals["EURUSD"] < 12000
    assert 30000 < notionals["XAUUSD"] < 42000
    var = body["var"]
    assert var["parametric_95"] is not None and var["parametric_95"] > 0
    assert var["mc_95"] is not None and var["mc_95"] > 0
    assert var["historical_95"] is not None and var["historical_95"] > 0
    # Gioi han VaR 2% tren equity 10050.
    assert var["limit_usd"] == pytest.approx(201.0)
    assert var["limit_pct"] == 2.0
    assert var["breached"] == bool(
        max(v for v in (var["parametric_95"], var["historical_95"],
                        var["mc_95"]) if v is not None)
        > var["limit_usd"])
    assert body["mc"]["paths"] == 1000
    assert body["mc"]["seed"] == 42
    assert body["mc"]["p5"] is not None and body["mc"]["p95"] is not None
    comp = {c["symbol"]: c for c in body["component_var"]}
    assert set(comp) == {"EURUSD", "XAUUSD"}
    assert comp["XAUUSD"]["var_usd"] > comp["EURUSD"]["var_usd"]
    total_share = sum(c["share_pct"] for c in body["component_var"])
    assert abs(total_share - 100.0) < 0.5
    assert body["concentration"]["largest_symbol"] == "XAUUSD"
    assert body["concentration"]["largest_share_pct"] > 50
    assert body["stress"]  # cac kich ban mac dinh + ngay te nhat
    worst = min(body["stress"], key=lambda s: s["pnl_usd"])
    assert worst["name"] == "Tat ca rui ro giam"
    assert worst["pnl_usd"] < 0
    assert worst["breaches_drawdown"] is True  # -10% notional > DD 10% von
