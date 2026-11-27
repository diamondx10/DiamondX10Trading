"""Lenh cho (pending orders) — lenh khuyen nghi chua dat.

Khi co tin hieu dat chuan, live luu lenh vao store nay (status
"pending", het han sau ttl_min phut mac dinh 15) roi gui Telegram kem
ban phim inline. Nguoi dung bam nut "Dat lenh" -> listener goi
resolve(id) lay tham so lenh roi dat qua MT5; bam "Bo qua" hoac het
han thi lenh khong dat duoc nua.

File: decisions/pending-orders.json — JSON object {id: order_dict}.
Ghi kieu atomic-ish (ghi file tam cung thu muc roi os.replace).
File hong / thieu: coi nhu store rong, KHONG raise.
"""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_PATH = (Path(__file__).resolve().parents[2] / "decisions"
                / "pending-orders.json")

FIELDS = ("desk", "manager", "symbol", "action", "entry", "sl", "tp",
          "volume", "risk_usd")

ERR_NOT_FOUND = "khong tim thay lenh"
ERR_EXPIRED = "lenh da het han"
ERR_PROCESSED = "lenh da duoc xu ly"


def _parse_time(value):
    """Parse ISO timestamp -> datetime (aware UTC); loi thi None."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _as_utc(moment):
    """datetime (naive coi nhu UTC) hoac None -> now UTC."""
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


class PendingOrderStore:
    """Store lenh cho, luu file JSON {id: order_dict}."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self._orders = self._load()

    def _load(self):
        """Doc file; thieu file / JSON hong / khong phai dict -> {}."""
        try:
            if not self.path.exists():
                return {}
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self):
        """Ghi file: ghi tam cung thu muc roi os.replace (atomic-ish)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._orders, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)
        return self.path

    def create(self, order, ttl_min=15):
        """Tao lenh cho moi, tra id 8 ky tu hex.

        order: dict co desk/manager/symbol/action/entry/sl/tp/volume/
        risk_usd. Gan created_utc/expires_utc (UTC ISO), status
        "pending", ticket None. Id trung thi tao lai.
        """
        order_id = secrets.token_hex(4)
        while order_id in self._orders:
            order_id = secrets.token_hex(4)
        created = datetime.now(timezone.utc)
        record = {"id": order_id}
        for field in FIELDS:
            record[field] = order.get(field)
        record["created_utc"] = created.isoformat()
        record["expires_utc"] = (
            created + timedelta(minutes=ttl_min)).isoformat()
        record["status"] = "pending"
        record["ticket"] = None
        self._orders[order_id] = record
        self._save()
        return order_id

    def get(self, order_id):
        """Tra dict lenh (ban copy) hoac None neu khong co."""
        record = self._orders.get(order_id)
        return dict(record) if record is not None else None

    def mark_placed(self, order_id, ticket):
        """Danh dau lenh da dat (status "placed", luu ticket)."""
        record = self._orders.get(order_id)
        if record is None:
            return False
        record["status"] = "placed"
        record["ticket"] = ticket
        self._save()
        return True

    def mark_cancelled(self, order_id):
        """Danh dau lenh da huy (status "cancelled")."""
        record = self._orders.get(order_id)
        if record is None:
            return False
        record["status"] = "cancelled"
        self._save()
        return True

    def prune_expired(self, now=None):
        """Danh dau "expired" cho moi lenh pending da qua han.

        Chi ghi file khi co lenh thay doi. Tra so lenh bi danh dau.
        """
        moment = _as_utc(now)
        changed = 0
        for record in self._orders.values():
            if record.get("status") != "pending":
                continue
            expires = _parse_time(record.get("expires_utc"))
            if expires is None or moment > expires:
                record["status"] = "expired"
                changed += 1
        if changed:
            self._save()
        return changed

    def resolve(self, order_id, now=None):
        """Lay lenh de dat, chi khi con pending va chua het han.

        Tra (order, None) khi hop le; (None, "khong tim thay lenh")
        khi khong co; (None, "lenh da het han") khi pending nhung qua
        han (va danh dau expired); (None, "lenh da duoc xu ly") khi
        status la placed/cancelled/expired.
        """
        record = self._orders.get(order_id)
        if record is None:
            return None, ERR_NOT_FOUND
        if record.get("status") != "pending":
            return None, ERR_PROCESSED
        moment = _as_utc(now)
        expires = _parse_time(record.get("expires_utc"))
        if expires is None or moment > expires:
            record["status"] = "expired"
            self._save()
            return None, ERR_EXPIRED
        return dict(record), None
