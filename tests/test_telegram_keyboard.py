"""Test ban phim inline + callback helpers Telegram (telegram.py).

Dung urlopen gia, khong goi Telegram that, khong co token that.
"""
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.telegram import (
    answer_callback_query,
    edit_message_reply_markup,
    edit_message_text,
    format_signal_alert,
    get_updates,
    order_keyboard,
    send_message,
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


def _payload(seen, index=0):
    return json.loads(seen["requests"][index].data.decode("utf-8"))


def _result():
    return {"symbol": "EURUSD", "action": "BUY", "price": 1.0974,
            "sl": 1.08, "tp": 1.13, "volume": 0.01, "risk_usd": 75.0,
            "time": "2026-11-27T09:00:00+00:00", "reason": "SMA5 > SMA20"}


# --- send_message + reply_markup --------------------------------------
def test_send_message_with_reply_markup(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    kb = order_keyboard("abcdef01", "BUY", "EURUSD", 0.01)
    assert send_message("hello", token="tok123", chat_id="456",
                        reply_markup=kb) is True
    payload = _payload(seen)
    assert payload["chat_id"] == "456"
    assert payload["text"] == "hello"
    assert payload["reply_markup"] == kb


def test_send_message_without_reply_markup_unchanged(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert send_message("hello", token="tok123", chat_id="456") is True
    assert _payload(seen) == {"chat_id": "456", "text": "hello"}


# --- order_keyboard ----------------------------------------------------
def test_order_keyboard_shape():
    kb = order_keyboard("abcdef01", "BUY", "EURUSD", 0.01)
    assert kb == {
        "inline_keyboard": [
            [{"text": "✅ Place BUY EURUSD 0.01 lot",
              "callback_data": "ord:abcdef01"}],
            [{"text": "❌ Ignore", "callback_data": "skip:abcdef01"}],
        ]}


def test_order_keyboard_sell_and_volume_format():
    kb = order_keyboard("1234abcd", "SELL", "XAUUSD", 0.1)
    button = kb["inline_keyboard"][0][0]
    assert button["text"] == "✅ Place SELL XAUUSD 0.1 lot"
    assert button["callback_data"] == "ord:1234abcd"
    # Volume 1.0 khong de so 0 thua, khong de dang float dai
    kb2 = order_keyboard("1234abcd", "BUY", "BTCUSD", 1.0)
    assert kb2["inline_keyboard"][0][0]["text"] == (
        "✅ Place BUY BTCUSD 1 lot")


def test_callback_data_length_within_telegram_limit():
    pending_id = "abcdef01"  # id 8 ky tu hex that
    assert len(f"ord:{pending_id}".encode("utf-8")) <= 64
    assert len(f"skip:{pending_id}".encode("utf-8")) <= 64


# --- format_signal_alert recommended -----------------------------------
def test_format_signal_alert_recommended():
    text = format_signal_alert(_result(), "forex", manager="Yuling",
                               recommended=True, pending_id="abcdef01")
    assert "Not placed yet — tap the button to place the order" in text
    assert "Pending order ID: abcdef01" in text
    assert "EURUSD" in text and "BUY" in text
    # Khuyen nghi thi khong duoc ghi la da dat lenh
    assert "Status: DEMO order placed" not in text


def test_format_signal_alert_not_recommended_unchanged():
    text = format_signal_alert(_result(), "forex", manager="Yuling")
    assert "Not placed yet" not in text
    assert "Pending order ID" not in text
    assert "EURUSD" in text


def test_format_signal_alert_recommended_without_pending_id():
    text = format_signal_alert(_result(), "forex", recommended=True)
    assert "Not placed yet" in text
    assert "Pending order ID" not in text


# --- answer_callback_query ---------------------------------------------
def test_answer_callback_query(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert answer_callback_query("cq-1", text="Da nhan",
                                 token="tok123") is True
    req = seen["requests"][0]
    assert req.full_url == (
        "https://api.telegram.org/bottok123/answerCallbackQuery")
    assert _payload(seen) == {"callback_query_id": "cq-1",
                              "text": "Da nhan"}


def test_answer_callback_query_without_text(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert answer_callback_query("cq-1", token="tok123") is True
    assert _payload(seen) == {"callback_query_id": "cq-1"}


def test_answer_callback_query_error_returns_false(monkeypatch):
    _capture_urlopen(monkeypatch,
                     response=urllib.error.URLError("mat mang"))
    assert answer_callback_query("cq-1", token="tok123") is False


# --- edit_message_text --------------------------------------------------
def test_edit_message_text(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    kb = order_keyboard("abcdef01", "BUY", "EURUSD", 0.01)
    assert edit_message_text("456", 789, "text moi", reply_markup=kb,
                             token="tok123") is True
    req = seen["requests"][0]
    assert req.full_url == (
        "https://api.telegram.org/bottok123/editMessageText")
    assert _payload(seen) == {"chat_id": "456", "message_id": 789,
                              "text": "text moi", "reply_markup": kb}


def test_edit_message_text_without_markup(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert edit_message_text("456", 789, "text moi",
                             token="tok123") is True
    assert _payload(seen) == {"chat_id": "456", "message_id": 789,
                              "text": "text moi"}


def test_edit_message_text_error_returns_false(monkeypatch):
    _capture_urlopen(monkeypatch,
                     response=FakeResponse(status=200,
                                           body={"ok": False,
                                                 "description": "nope"}))
    assert edit_message_text("456", 789, "x", token="tok123") is False


# --- edit_message_reply_markup ------------------------------------------
def test_edit_message_reply_markup_with_keyboard(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    kb = order_keyboard("abcdef01", "BUY", "EURUSD", 0.01)
    assert edit_message_reply_markup("456", 789, kb,
                                     token="tok123") is True
    req = seen["requests"][0]
    assert req.full_url == (
        "https://api.telegram.org/bottok123/editMessageReplyMarkup")
    assert _payload(seen) == {"chat_id": "456", "message_id": 789,
                              "reply_markup": kb}


def test_edit_message_reply_markup_none_removes_buttons(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert edit_message_reply_markup("456", 789, None,
                                     token="tok123") is True
    assert _payload(seen) == {"chat_id": "456", "message_id": 789,
                              "reply_markup": {}}


def test_edit_message_reply_markup_empty_removes_buttons(monkeypatch):
    seen = _capture_urlopen(monkeypatch)
    assert edit_message_reply_markup("456", 789, {},
                                     token="tok123") is True
    assert _payload(seen)["reply_markup"] == {}


# --- get_updates ---------------------------------------------------------
def test_get_updates_returns_result_list(monkeypatch):
    updates = [{"update_id": 10,
                "callback_query": {"id": "cq-1",
                                   "data": "ord:abcdef01"}}]
    _capture_urlopen(monkeypatch, response=FakeResponse(
        body={"ok": True, "result": updates}))
    assert get_updates(offset=10, timeout=5, token="tok123") == updates


def test_get_updates_passes_offset_and_timeout(monkeypatch):
    seen = _capture_urlopen(monkeypatch, response=FakeResponse(
        body={"ok": True, "result": []}))
    assert get_updates(offset=42, timeout=5, token="tok123") == []
    req = seen["requests"][0]
    assert req.full_url == "https://api.telegram.org/bottok123/getUpdates"
    assert _payload(seen) == {"timeout": 5, "offset": 42}


def test_get_updates_without_offset_omits_it(monkeypatch):
    seen = _capture_urlopen(monkeypatch, response=FakeResponse(
        body={"ok": True, "result": []}))
    assert get_updates(token="tok123") == []
    assert _payload(seen) == {"timeout": 30}


def test_get_updates_http_error_returns_empty_no_raise(monkeypatch):
    _capture_urlopen(monkeypatch,
                     response=urllib.error.URLError("mat mang"))
    assert get_updates(token="tok123") == []


def test_get_updates_not_ok_returns_empty(monkeypatch):
    _capture_urlopen(monkeypatch, response=FakeResponse(
        status=200, body={"ok": False, "result": []}))
    assert get_updates(token="tok123") == []
