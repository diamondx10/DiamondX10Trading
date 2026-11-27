"""Xac thuc OTP cho WebUI DiamondX10 (dx10).

Chi dung trong bo nho (in-memory), KHONG luu file, KHONG ghi log:
  - OTPManager: ma OTP 6 chu so, TTL 60 giay, dung 1 lan, chi 1 OTP
    dang hoat dong tai 1 thoi diem (yeu cau moi vo hieu hoa OTP cu),
    cooldown ~15 giay giua 2 lan yeu cau, toi da 5 lan nhap sai thi
    OTP bi vo hieu hoa. So sanh bang hmac.compare_digest.
  - SessionStore: token phien (secrets.token_urlsafe(32)) -> thoi diem
    tao; server khoi dong lai thi toan bo phien mat (khong luu tru).

OTP va token phien KHONG BAO GIO duoc ghi log, ghi file hay tra ve
trong response API (chi tra boolean "sent" / ly do loi). Ngoai le duy
nhat theo thiet ke: khi Telegram khong gui duoc, webapi in ma OTP ra
stdout cua cua so terminal chay server de nguoi dung doc truc tiep.
"""
import hashlib
import hmac
import math
import secrets
import time
from datetime import datetime, timezone

OTP_TTL_SECONDS = 60
OTP_COOLDOWN_SECONDS = 15
OTP_MAX_ATTEMPTS = 5
SESSION_COOKIE_NAME = "dx10_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600

VERIFY_REASONS = ("invalid", "expired", "too_many_attempts", "no_otp")


class OTPManager:
    """Quan ly 1 OTP dang hoat dong (chi trong bo nho).

    clock: ham tra thoi gian hien tai (giay, dang monotonic) — mac
    dinh time.monotonic; test co the truyen dong ho gia de gia lap
    het han / het cooldown ma khong phai cho that.
    """

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._otp = None  # {"code", "created", "attempts"}
        self._last_request_at = None

    def _now(self):
        return float(self._clock())

    def request_otp(self):
        """Tao OTP moi. Tra dict {"ok", "code", "retry_after"}.

        Dang trong cooldown thi ok=False, code=None va retry_after la
        so giay con lai (lam tron len). OTP moi vo hieu hoa OTP cu.
        """
        now = self._now()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < OTP_COOLDOWN_SECONDS:
                return {"ok": False, "code": None,
                        "retry_after": int(math.ceil(
                            OTP_COOLDOWN_SECONDS - elapsed))}
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._otp = {"code": code, "created": now, "attempts": 0}
        self._last_request_at = now
        return {"ok": True, "code": code, "retry_after": None}

    def verify_otp(self, code):
        """Kiem tra ma OTP. Tra (ok, reason).

        ok=True thi reason=None va OTP bi xoa (dung 1 lan). ok=False
        thi reason la 1 trong "invalid" | "expired" |
        "too_many_attempts" | "no_otp". So sanh bang compare_digest.
        """
        if self._otp is None:
            return False, "no_otp"
        now = self._now()
        if now - self._otp["created"] >= OTP_TTL_SECONDS:
            self._otp = None
            return False, "expired"
        candidate = code if isinstance(code, str) else ""
        # compare_digest can 2 chuoi cung do dai; ma OTP luon 6 chu so
        # nen so sanh an toan — ma sai do dai cung tra False.
        if hmac.compare_digest(candidate.strip(), self._otp["code"]):
            self._otp = None
            return True, None
        self._otp["attempts"] += 1
        if self._otp["attempts"] >= OTP_MAX_ATTEMPTS:
            self._otp = None
            return False, "too_many_attempts"
        return False, "invalid"

    def has_active_otp(self):
        """True neu co OTP chua het han (khong lam moi trang thai)."""
        if self._otp is None:
            return False
        return self._now() - self._otp["created"] < OTP_TTL_SECONDS

    def peek_otp(self):
        """CHI DUNG CHO TEST (chay cung process voi server): doc ma OTP
        hien tai ma khong xoa no. KHONG dung o route/API nao."""
        if self._otp is None:
            return None
        return self._otp["code"]


class SessionStore:
    """Phien dang nhap (chi trong bo nho): token -> created_utc.

    Token het han sau 30 ngay; server khoi dong lai thi het phien.
    """

    def __init__(self):
        self._sessions = {}

    def create(self):
        """Tao phien moi, tra token (chuoi)."""
        token = secrets.token_urlsafe(32)
        self._sessions[token] = datetime.now(timezone.utc)
        return token

    def is_valid(self, token):
        """True neu token con trong store va chua qua 30 ngay."""
        if not isinstance(token, str) or not token:
            return False
        created = self._sessions.get(token)
        if created is None:
            return False
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age >= SESSION_MAX_AGE_SECONDS:
            del self._sessions[token]
            return False
        return True

    def revoke(self, token):
        """Xoa phien. Tra True neu phien co ton tai."""
        return self._sessions.pop(token, None) is not None

    def count(self):
        """So phien dang mo (chi dung cho test / chan doan)."""
        return len(self._sessions)


def hash_token(token):
    """Hash SHA-256 cua token (dung khi can ghi nhan ma khong lo
    token that — khong dung de so sanh phien)."""
    if not isinstance(token, str):
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
