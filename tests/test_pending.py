"""Test PendingOrderStore — lenh cho chua dat (pending.py).

Khong goi Telegram that, khong can MT5. Moi test dung file tam rieng.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.pending import DEFAULT_PATH, PendingOrderStore


def _order(**overrides):
    order = {"desk": "forex", "manager": "Yuling", "symbol": "EURUSD",
             "action": "BUY", "entry": 1.0974, "sl": 1.08, "tp": 1.13,
             "volume": 0.01, "risk_usd": 75.0}
    order.update(overrides)
    return order


def test_default_path_is_repo_decisions():
    assert DEFAULT_PATH.name == "pending-orders.json"
    assert DEFAULT_PATH.parent.name == "decisions"
    assert DEFAULT_PATH.parent.parent.name == "DiamondX10Trading"


def test_create_returns_8_char_hex_id_and_stores_fields(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order())
    assert re.fullmatch(r"[0-9a-f]{8}", order_id)
    record = store.get(order_id)
    assert record is not None
    assert record["id"] == order_id
    assert record["desk"] == "forex"
    assert record["manager"] == "Yuling"
    assert record["symbol"] == "EURUSD"
    assert record["action"] == "BUY"
    assert record["entry"] == 1.0974
    assert record["sl"] == 1.08
    assert record["tp"] == 1.13
    assert record["volume"] == 0.01
    assert record["risk_usd"] == 75.0
    assert record["status"] == "pending"
    assert record["ticket"] is None
    # expires_utc ~ ttl_min (15 mac dinh) sau created_utc
    created = datetime.fromisoformat(record["created_utc"])
    expires = datetime.fromisoformat(record["expires_utc"])
    assert timedelta(minutes=14, seconds=59) < expires - created < \
        timedelta(minutes=15, seconds=1)


def test_create_custom_ttl(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order(), ttl_min=30)
    record = store.get(order_id)
    created = datetime.fromisoformat(record["created_utc"])
    expires = datetime.fromisoformat(record["expires_utc"])
    assert expires - created == timedelta(minutes=30)


def test_get_round_trip_and_missing(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order())
    assert store.get(order_id)["symbol"] == "EURUSD"
    assert store.get("khong-co-id") is None


def test_resolve_happy_path(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order())
    order, err = store.resolve(order_id)
    assert err is None
    assert order["id"] == order_id
    assert order["status"] == "pending"
    assert order["symbol"] == "EURUSD"


def test_resolve_missing(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order, err = store.resolve("khong-co-id")
    assert order is None
    assert err == "khong tim thay lenh"


def test_resolve_expired_marks_expired(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order(), ttl_min=0)
    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    order, err = store.resolve(order_id, now=future)
    assert order is None
    assert err == "lenh da het han"
    assert store.get(order_id)["status"] == "expired"
    # Lan 2: da het han thi coi nhu da xu ly
    order, err = store.resolve(order_id, now=future)
    assert order is None
    assert err == "lenh da duoc xu ly"


def test_double_use_after_mark_placed(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order())
    assert store.mark_placed(order_id, 123456) is True
    assert store.get(order_id)["status"] == "placed"
    assert store.get(order_id)["ticket"] == 123456
    order, err = store.resolve(order_id)
    assert order is None
    assert err == "lenh da duoc xu ly"


def test_double_use_after_mark_cancelled(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    order_id = store.create(_order())
    assert store.mark_cancelled(order_id) is True
    assert store.get(order_id)["status"] == "cancelled"
    order, err = store.resolve(order_id)
    assert order is None
    assert err == "lenh da duoc xu ly"


def test_mark_unknown_returns_false(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    assert store.mark_placed("khong-co-id", 1) is False
    assert store.mark_cancelled("khong-co-id") is False


def test_prune_expired_marks_only_expired_pendings(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    old_id = store.create(_order(), ttl_min=0)
    fresh_id = store.create(_order(symbol="XAUUSD"), ttl_min=60)
    placed_id = store.create(_order(symbol="BTCUSD"), ttl_min=0)
    store.mark_placed(placed_id, 99)
    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert store.prune_expired(now=future) == 1
    assert store.get(old_id)["status"] == "expired"
    assert store.get(fresh_id)["status"] == "pending"
    assert store.get(placed_id)["status"] == "placed"
    # Khong con lenh het han nua
    assert store.prune_expired(now=future) == 0


def test_corrupt_store_loads_as_empty_no_raise(tmp_path):
    path = tmp_path / "pending-orders.json"
    path.write_text("day khong phai json {{{", encoding="utf-8")
    store = PendingOrderStore(path=path)
    assert store.get("bat-ky-id") is None
    order, err = store.resolve("bat-ky-id")
    assert order is None
    assert err == "khong tim thay lenh"
    assert store.prune_expired() == 0
    # Store hong van ghi duoc lenh moi (ghi de file hong)
    order_id = store.create(_order())
    assert store.get(order_id) is not None


def test_missing_file_loads_as_empty(tmp_path):
    store = PendingOrderStore(path=tmp_path / "khong-co-file.json")
    assert store.get("bat-ky-id") is None
    order, err = store.resolve("bat-ky-id")
    assert (order, err) == (None, "khong tim thay lenh")


def test_data_survives_reload(tmp_path):
    path = tmp_path / "pending-orders.json"
    store = PendingOrderStore(path=path)
    order_id = store.create(_order())
    store2 = PendingOrderStore(path=path)
    record = store2.get(order_id)
    assert record is not None
    assert record["symbol"] == "EURUSD"
    assert record["status"] == "pending"
    order, err = store2.resolve(order_id)
    assert err is None
    assert order["id"] == order_id
    # File tren dia la JSON object {id: order_dict}
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert raw[order_id]["symbol"] == "EURUSD"


def test_unique_ids(tmp_path):
    store = PendingOrderStore(path=tmp_path / "pending-orders.json")
    ids = {store.create(_order()) for _ in range(50)}
    assert len(ids) == 50
