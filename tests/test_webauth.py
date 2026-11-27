"""Test OTPManager + SessionStore (webauth.py, chi trong bo nho).

Khong goi mang, khong ghi file, khong dung server that. Dong ho gia
de gia lap het han / het cooldown ma khong phai cho that.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import webauth
from diamondx10.webauth import OTPManager, SessionStore


class FakeClock:
    """Dong ho gia: tang tay de gia lap thoi gian troi qua."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _wrong_code(right):
    """Ma sai chac chan khac ma dung (ca 2 deu 6 chu so)."""
    return "000000" if right != "000000" else "000001"


# --- OTP: dinh dang 6 chu so, ke ca so 0 o dau ---

def test_otp_six_digits_with_leading_zeros(monkeypatch):
    """randbelow tra 42 -> ma phai la '000042' (du 6 chu so)."""
    monkeypatch.setattr(webauth.secrets, "randbelow", lambda n: 42)
    mgr = OTPManager()
    result = mgr.request_otp()
    assert result["ok"] is True
    assert result["code"] == "000042"
    assert re.fullmatch(r"\d{6}", result["code"])
    assert mgr.peek_otp() == "000042"


def test_otp_format_random(monkeypatch):
    mgr = OTPManager()
    result = mgr.request_otp()
    assert result["ok"] is True
    assert re.fullmatch(r"\d{6}", result["code"])


# --- OTP: TTL 60 giay ---

def test_otp_expires_after_60s():
    clock = FakeClock()
    mgr = OTPManager(clock=clock)
    mgr.request_otp()
    code = mgr.peek_otp()
    clock.advance(59)
    assert mgr.verify_otp(code) == (True, None)
    # OTP moi: het 60 giay thi het han.
    mgr.request_otp()
    code = mgr.peek_otp()
    clock.advance(60)
    assert mgr.verify_otp(code) == (False, "expired")
    # Het han roi thi khong con OTP nao.
    assert mgr.verify_otp(code) == (False, "no_otp")


# --- OTP: dung 1 lan ---

def test_otp_single_use():
    mgr = OTPManager()
    mgr.request_otp()
    code = mgr.peek_otp()
    assert mgr.verify_otp(code) == (True, None)
    assert mgr.verify_otp(code) == (False, "no_otp")


# --- OTP: ma sai bi tu choi ---

def test_otp_wrong_code_rejected():
    mgr = OTPManager()
    mgr.request_otp()
    code = mgr.peek_otp()
    assert mgr.verify_otp(_wrong_code(code)) == (False, "invalid")
    # Ma dung van con hieu luc sau 1 lan nhap sai.
    assert mgr.verify_otp(code) == (True, None)


def test_otp_verify_without_any_otp():
    mgr = OTPManager()
    assert mgr.verify_otp("123456") == (False, "no_otp")
    assert mgr.verify_otp("") == (False, "no_otp")
    assert mgr.verify_otp(None) == (False, "no_otp")


# --- OTP: toi da 5 lan nhap sai thi vo hieu hoa ---

def test_otp_five_attempts_cap_invalidates():
    mgr = OTPManager()
    mgr.request_otp()
    code = mgr.peek_otp()
    wrong = _wrong_code(code)
    for _ in range(4):
        assert mgr.verify_otp(wrong) == (False, "invalid")
    # Lan sai thu 5: het luot, OTP bi vo hieu hoa.
    assert mgr.verify_otp(wrong) == (False, "too_many_attempts")
    # Ma dung cung khong con dung duoc nua.
    assert mgr.verify_otp(code) == (False, "no_otp")


# --- OTP: gui lai vo hieu hoa ma cu ---

def test_otp_resend_invalidates_old_code():
    clock = FakeClock()
    mgr = OTPManager(clock=clock)
    mgr.request_otp()
    old = mgr.peek_otp()
    clock.advance(16)  # qua cooldown 15 giay
    result = mgr.request_otp()
    assert result["ok"] is True
    new = result["code"]
    assert mgr.verify_otp(old) == (False, "invalid")
    assert mgr.verify_otp(new) == (True, None)


# --- OTP: cooldown ~15 giay ---

def test_otp_request_cooldown():
    clock = FakeClock()
    mgr = OTPManager(clock=clock)
    assert mgr.request_otp()["ok"] is True
    second = mgr.request_otp()
    assert second["ok"] is False
    assert second["code"] is None
    assert 0 < second["retry_after"] <= 15
    # Chua het cooldown thi van bi chan, ma cu van con.
    assert mgr.request_otp()["retry_after"] > 0
    clock.advance(15)
    assert mgr.request_otp()["ok"] is True


# --- SessionStore ---

def test_session_create_valid_revoke():
    store = SessionStore()
    token = store.create()
    assert isinstance(token, str) and len(token) >= 32
    assert store.is_valid(token) is True
    assert store.is_valid("token-khong-co") is False
    assert store.is_valid("") is False
    assert store.is_valid(None) is False
    assert store.revoke(token) is True
    assert store.is_valid(token) is False
    assert store.revoke(token) is False


def test_session_tokens_independent():
    store = SessionStore()
    first = store.create()
    second = store.create()
    assert first != second
    assert store.count() == 2
    assert store.revoke(first) is True
    assert store.is_valid(first) is False
    assert store.is_valid(second) is True
