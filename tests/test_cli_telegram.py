"""Test lenh `telegram-test` (diamondx10.__main__.cmd_telegram_test).

Khong goi Telegram that: token gia qua bien moi truong, send_message
duoc thay bang ban gia.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import cmd_telegram_test


def test_telegram_test_not_ready(monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    assert cmd_telegram_test({}) == 1


def test_telegram_test_sends(monkeypatch):
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "token-gia")
    cfg = {"telegram": {"enabled": True, "chat_id": "1234567890"}}
    sent = {}

    def fake_send(text, cfg=None, **kw):
        sent["text"] = text
        return True

    monkeypatch.setattr("diamondx10.telegram.send_message", fake_send)
    assert cmd_telegram_test(cfg) == 0
    assert "test message" in sent["text"]


def test_telegram_test_send_fails(monkeypatch):
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "token-gia")
    cfg = {"telegram": {"enabled": True, "chat_id": "1234567890"}}
    monkeypatch.setattr("diamondx10.telegram.send_message",
                        lambda text, cfg=None, **kw: False)
    assert cmd_telegram_test(cfg) == 1
