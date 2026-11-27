"""Test Phase D — canh bao Telegram (telegram.py, stdlib urllib).

Dung urlopen gia, khong goi Telegram that, khong co token that.
"""
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.telegram import (
    _risk_reward,
    format_blocked_alert,
    format_signal_alert,
    format_test_message,
    send_message,
    setup_status,
    telegram_enabled,
)


class FakeResponse:
    """Gia cua urlopen: context manager tra ve HTTP 200 + {"ok": true}."""

    def __init__(self, status=200, body=None):
        self.status = status
        self._body = body if body is not None else {"ok": True, "result": {}}

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_urlopen(monkeypatch, response=None):
    """Thay urlopen bang ban gia, tra dict ghi lai cac request da gui."""
    seen = {"requests": []}

    def fake_urlopen(request, timeout=None):
        seen["requests"].append(request)
        if isinstance(response, Exception):
            raise response
        return response if response is not None else FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return seen


def test_send_success(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert send_message("hello", token="tok123", chat_id="456") is True
    assert len(seen["requests"]) == 1
    req = seen["requests"][0]
    assert req.full_url == ("https://api.telegram.org/bottok123/sendMessage")
    payload = json.loads(req.data.decode("utf-8"))
    assert payload == {"chat_id": "456", "text": "hello"}


def test_token_from_env(monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "env-token-abc")
    seen = _capture_urlopen(monkeypatch)
    cfg = {"telegram": {"chat_id": "99"}}
    assert send_message("hi", cfg=cfg) is True
    assert "botenv-token-abc/sendMessage" in seen["requests"][0].full_url


def test_token_env_name_from_cfg(monkeypatch):
    monkeypatch.delenv("MY_BOT_TOKEN", raising=False)
    monkeypatch.setenv("MY_BOT_TOKEN", "cfg-env-token")
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    seen = _capture_urlopen(monkeypatch)
    cfg = {"telegram": {"chat_id": "99", "bot_token_env": "MY_BOT_TOKEN"}}
    assert send_message("hi", cfg=cfg) is True
    assert "botcfg-env-token/sendMessage" in seen["requests"][0].full_url


def test_param_token_beats_env(monkeypatch):
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "env-token")
    seen = _capture_urlopen(monkeypatch)
    assert send_message("hi", token="param-token", chat_id="1") is True
    assert "botparam-token/sendMessage" in seen["requests"][0].full_url


def test_missing_token_returns_false_no_raise(monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    seen = _capture_urlopen(monkeypatch)
    assert send_message("hi", cfg={"telegram": {"chat_id": "1"}}) is False
    assert seen["requests"] == []


def test_missing_chat_id_returns_false_no_raise(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    cfg = {"telegram": {"chat_id": ""}}
    assert send_message("hi", token="tok", cfg=cfg) is False
    assert seen["requests"] == []


def test_http_error_returns_false_no_raise(monkeypatch):
    err = urllib.error.HTTPError(
        "https://api.telegram.org/botx/sendMessage", 403, "Forbidden",
        hdrs=None, fp=None)
    _capture_urlopen(monkeypatch, response=err)
    assert send_message("hi", token="tok", chat_id="1") is False


def test_network_error_returns_false_no_raise(monkeypatch):
    _capture_urlopen(monkeypatch,
                     response=urllib.error.URLError("mat mang"))
    assert send_message("hi", token="tok", chat_id="1") is False


def test_api_not_ok_returns_false(monkeypatch):
    _capture_urlopen(monkeypatch,
                     response=FakeResponse(
                         status=200, body={"ok": False,
                                           "description": "chat not found"}))
    assert send_message("hi", token="tok", chat_id="1") is False


def test_telegram_enabled_default_false():
    assert telegram_enabled({}) is False
    assert telegram_enabled({"telegram": {}}) is False
    assert telegram_enabled({"telegram": {"enabled": False}}) is False
    assert telegram_enabled({"telegram": {"enabled": True}}) is True


def test_format_signal_alert_has_all_fields():
    result = {"symbol": "EURUSD", "action": "BUY", "status": "TRADED",
              "reason": "SMA5 > SMA20, RSI 59", "volume": 0.01,
              "price": 103.0, "sl": 101.5, "tp": 106.0}
    text = format_signal_alert(result, "forex", lang="en")
    assert "EURUSD" in text and "BUY" in text
    assert "103" in text and "0.01" in text
    assert "101.5" in text and "106" in text
    assert "SMA5 > SMA20" in text


def test_format_blocked_alert_has_all_fields():
    result = {"symbol": "XAUUSD", "action": "BLOCKED-DRAWDOWN-FUND",
              "status": "BLOCKED-DRAWDOWN-FUND",
              "reason": "BLOCKED-DRAWDOWN-FUND: drawdown 11.0% vuot gioi han 10.0%"}
    text = format_blocked_alert(result, "xauusd", lang="en")
    assert "XAUUSD" in text
    assert "BLOCKED-DRAWDOWN-FUND" in text
    assert "11.0%" in text

# --- Dinh dang khuyen nghi mua/ban (tich hop Telegram) ------------------
def test_format_signal_alert_recommendation():
    result = {"symbol": "BTCUSD", "action": "BUY", "status": "TRADED",
              "reason": "SMA5 > SMA20, RSI 59", "volume": 0.02,
              "price": 61594.0, "sl": 60000.0, "tp": 64782.0,
              "risk_usd": 67.0, "manager": "Rich",
              "time": "2026-11-27T09:00:00+00:00", "order": 123456}
    text = format_signal_alert(result, "crypto", manager="Rich", lang="en")
    assert "BUY RECOMMENDATION" in text
    assert "(DEMO)" in text
    assert "BTCUSD" in text and "BUY" in text
    assert "61594" in text and "60000" in text and "64782" in text
    assert "0.02" in text
    assert "67" in text
    assert "R:R" in text and "1:2" in text
    assert "Rich" in text
    assert "123456" in text
    assert "SMA5 > SMA20" in text


def test_format_signal_alert_sell():
    result = {"symbol": "EURUSD", "action": "SELL", "status": "TRADED",
              "price": 1.10, "sl": 1.12, "tp": 1.06, "volume": 0.01}
    text = format_signal_alert(result, "forex", lang="en")
    assert "SELL RECOMMENDATION" in text
    assert "SELL" in text
    assert "1:2" in text


def test_format_signal_alert_minimal_no_crash():
    text = format_signal_alert(
        {"symbol": "XAUUSD", "action": "BUY", "status": "TRADED"}, "xauusd", lang="en")
    assert "BUY RECOMMENDATION" in text
    assert "XAUUSD" in text


def test_format_blocked_alert_with_levels():
    result = {"symbol": "XAUUSD", "action": "BUY",
              "status": "BLOCKED-VOLUME-ZERO",
              "reason": "volume tinh duoc = 0 (kiem tra risk/entry/SL)",
              "price": 3650.98, "sl": 3600.0, "tp": 3752.94, "volume": 0}
    text = format_blocked_alert(result, "xauusd", manager="Yumi", lang="en")
    assert "BLOCKED-VOLUME-ZERO" in text
    assert "BUY" in text
    assert "3650.98" in text
    assert "Yumi" in text


def test_setup_status(monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    status = setup_status({})
    assert status["ready"] is False
    assert len(status["missing"]) == 3
    cfg = {"telegram": {"enabled": True, "chat_id": "1234567890"}}
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "token-gia")
    status = setup_status(cfg)
    assert status["ready"] is True
    assert status["missing"] == []


def test_format_test_message():
    text = format_test_message(lang="en")
    assert "DiamondX10" in text
    assert "test message" in text
    assert "recommendation" in text


def test_format_signal_alert_english_only():
    """Giao dien Telegram bang tieng Anh (rule 44): tieu de khuyen nghi
    + cac truong trong tin nhan deu tieng Anh, khong con tu tieng Viet
    cua ban cu (KHUYEN NGHI / Khoi luong / Rui ro / Ly do / ...)."""
    from diamondx10.telegram import order_keyboard

    for action in ("BUY", "SELL"):
        result = {"symbol": "BTCUSD", "action": action,
                  "status": "RECOMMENDED",
                  "reason": "SMA5 > SMA20, RSI 59", "volume": 0.02,
                  "price": 61594.0, "sl": 60000.0, "tp": 64782.0,
                  "risk_usd": 67.0,
                  "time": "2026-11-27T09:00:00+00:00"}
        text = format_signal_alert(result, "crypto", manager="Rich",
                                   recommended=True, pending_id="abcdef01", lang="en")
        assert f"{action} RECOMMENDATION" in text
        assert "(DEMO)" in text
        for vietnamese in ("KHUYẾN NGHỊ", "MUA", "BÁN", "Khối lượng",
                           "Rủi ro", "Tỉ lệ", "Lý do", "Thời gian",
                           "Trạng thái", "Chua dat lenh", "Ma lenh cho",
                           "Lệnh"):
            assert vietnamese not in text
        for english in ("Volume:", "Max risk:", "R:R", "Reason:",
                        "Time (UTC):", "Not placed yet",
                        "Pending order ID: abcdef01"):
            assert english in text
    kb = order_keyboard("abcdef01", "BUY", "BTCUSD", 0.02, lang="en")
    labels = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert labels == ["✅ Place BUY BTCUSD 0.02 lot", "❌ Ignore"]


def test_risk_reward():
    assert _risk_reward(103.0, 101.5, 106.0) == "1:2"
    assert _risk_reward(103.0, 101.5, 104.5) == "1:1"
    assert _risk_reward(103.0, None, 106.0) is None
    assert _risk_reward(103.0, 103.0, 106.0) is None
    assert _risk_reward(103.0, 101.5, 133.0) == "1:20"
