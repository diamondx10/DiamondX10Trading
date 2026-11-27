"""Test Telegram listener (listener.py) — nut DAT LENH / BO QUA.

Dung Telegram gia + MT5 gia + pending store gia, khong goi mang that,
khong co lenh that, khong dong vao decisions/ that.
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions, killswitch
from diamondx10.listener import run_listener

CHAT_ID = "1234567890"
ORIG_TEXT = "💎 DiamondX10 — BUY RECOMMENDATION (DEMO)\nEURUSD BUY @ 1.10"


def _cfg(max_deviation=1.0):
    return {"language": "en",
            "telegram": {"enabled": True, "chat_id": CHAT_ID,
                         "max_entry_deviation_pct": max_deviation},
            "mt5": {"demo_only": True}}


def _order(order_id="ord-1", entry=1.10, **overrides):
    order = {"desk": "forex", "manager": "Yuling Pan", "symbol": "EURUSD",
             "action": "BUY", "entry": entry, "sl": 1.05, "tp": 1.20,
             "volume": 0.01, "risk_usd": 75.0, "status": "pending",
             "ticket": None, "expires_at": time.time() + 3600}
    order.update(overrides)
    return order


class FakePendingStore:
    """Store gia theo dung hop dong cua pending.py."""

    def __init__(self, orders=None):
        self.orders = dict(orders or {})

    def get(self, order_id):
        return self.orders.get(order_id)

    def resolve(self, order_id):
        order = self.orders.get(order_id)
        if order is None:
            return None, "Order not found"
        if order.get("expires_at", 0) < time.time():
            return None, "lenh da het han"
        if order.get("status") != "pending":
            return None, "lenh da duoc xu ly"
        return order, None

    def mark_placed(self, order_id, ticket):
        self.orders[order_id]["status"] = "placed"
        self.orders[order_id]["ticket"] = ticket

    def mark_cancelled(self, order_id):
        self.orders[order_id]["status"] = "cancelled"


class FakeBrokenStore(FakePendingStore):
    """Store hong: resolve luon raise (gia lap file hong)."""

    def resolve(self, order_id):
        raise ValueError("file pending hong, doc khong duoc")


class FakeTelegram:
    """Telegram gia: get_updates tra cac batch dinh san, ghi lai moi goi."""

    def __init__(self, batches):
        self._batches = list(batches)
        self.get_updates_calls = []
        self.answers = []  # (callback_query_id, text)
        self.edits = []  # (chat_id, message_id, text, reply_markup)
        self.markup_edits = []

    def get_updates(self, offset=None, timeout=30, cfg=None):
        self.get_updates_calls.append({"offset": offset, "timeout": timeout,
                                       "cfg": cfg})
        if not self._batches:
            return []
        return self._batches.pop(0)

    def answer_callback_query(self, callback_query_id, text=None, cfg=None):
        self.answers.append((callback_query_id, text))
        return True

    def edit_message_text(self, chat_id, message_id, text,
                          reply_markup=None, cfg=None):
        self.edits.append((chat_id, message_id, text, reply_markup))
        return True

    def edit_message_reply_markup(self, chat_id, message_id,
                                  reply_markup=None, cfg=None):
        self.markup_edits.append((chat_id, message_id, reply_markup))
        return True


class FakeMT5:
    """MT5 gia: tai khoan demo, gia + order_check tuy chinh duoc."""

    TRADE_RETCODE_DONE = 10009
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, bid=1.10, trade_mode=0, server="Exness-MT5Trial7",
                 order_check_retcode=0, order_send_retcode=10009):
        self._bid = bid
        self._trade_mode = trade_mode
        self._server = server
        self._order_check_retcode = order_check_retcode
        self._order_send_retcode = order_send_retcode
        self.sent_orders = []

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self._bid, ask=self._bid + 0.001)

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode,
                               server=self._server, demo=True)

    def order_check(self, request):
        return SimpleNamespace(retcode=self._order_check_retcode)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=self._order_send_retcode,
                               order=777001, comment="Done")

    def last_error(self):
        return (0, "ok")


def _callback(update_id, cb_id, chat_id, data, message_id=11,
              text=ORIG_TEXT):
    return {"update_id": update_id,
            "callback_query": {"id": cb_id, "data": data,
                               "message": {"message_id": message_id,
                                           "chat": {"id": chat_id},
                                           "text": text}}}


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG tam + kill switch tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    monkeypatch.setattr(decisions, "LOG", log_path)
    ks_path = tmp_path / "kill-switch.json"
    return log_path, ks_path


@pytest.fixture
def kill_off(monkeypatch):
    monkeypatch.setattr(killswitch, "is_engaged",
                        lambda path=None: False)


def _run(tg, store, mt5, cfg=None, once=True, ks_path=None, **kwargs):
    return run_listener(cfg or _cfg(), telegram=tg, mt5_module=mt5,
                        pending_store=store, once=once,
                        kill_switch_path=ks_path, **kwargs)


def _log_text(log_path):
    return log_path.read_text(encoding="utf-8") if log_path.exists() else ""


# --- Happy path -------------------------------------------------------
def test_happy_path_places_order(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert len(mt5.sent_orders) == 1
    req = mt5.sent_orders[0]
    assert req["symbol"] == "EURUSD" and req["type"] == 0  # BUY
    assert req["volume"] == 0.01 and req["sl"] == 1.05
    assert req["tp"] == 1.20 and req["price"] == 1.10
    assert store.orders["ord-1"]["status"] == "placed"
    assert store.orders["ord-1"]["ticket"] == 777001
    assert "ORDER-PLACED-VIA-TELEGRAM" in _log_text(log_path)
    assert "777001" in _log_text(log_path)
    assert tg.answers == [("cb-1", "Order placed")]
    assert len(tg.edits) == 1
    _chat, _mid, text, markup = tg.edits[0]
    assert "ORDER PLACED" in text and "777001" in text
    assert markup == {"inline_keyboard": []}  # nut da go


def test_once_processes_exactly_one_batch(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order(), "ord-2": _order("ord-2")})
    mt5 = FakeMT5(bid=1.10)
    batch1 = [_callback(1, "cb-1", 1234567890, "ord:ord-1")]
    batch2 = [_callback(2, "cb-2", 1234567890, "ord:ord-2")]
    tg = FakeTelegram([batch1, batch2])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert len(tg.get_updates_calls) == 1
    assert tg.get_updates_calls[0]["timeout"] == 30
    assert len(mt5.sent_orders) == 1  # chi batch 1 duoc xu ly
    assert store.orders["ord-2"]["status"] == "pending"


def test_offset_advances_to_max_update_id(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)

    class TwoBatchTelegram(FakeTelegram):
        def get_updates(self, offset=None, timeout=30, cfg=None):
            self.get_updates_calls.append(
                {"offset": offset, "timeout": timeout, "cfg": cfg})
            if len(self.get_updates_calls) == 1:
                return [_callback(7, "cb-1", 1234567890, "ord:ord-1"),
                        _callback(9, "cb-2", 1234567890, "skip:ord-1")]
            raise KeyboardInterrupt

    tg = TwoBatchTelegram([])
    assert _run(tg, store, mt5, once=False, interval_sec=0,
                ks_path=ks_path) == 0
    assert tg.get_updates_calls[0]["offset"] is None
    assert tg.get_updates_calls[1]["offset"] == 10  # max update_id + 1


# --- Quyen / resolve --------------------------------------------------
def test_wrong_chat_refused(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 111111, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [("cb-1", "No permission")]
    assert mt5.sent_orders == []
    assert store.orders["ord-1"]["status"] == "pending"
    assert tg.edits == []  # bo qua hoan toan, khong sua tin


def test_missing_order_refused(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-99")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers[0][1] == "Order not found"
    assert mt5.sent_orders == []
    assert len(tg.edits) == 1
    assert tg.edits[0][3] == {"inline_keyboard": []}


def test_expired_order_refused(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore(
        {"ord-1": _order(expires_at=time.time() - 10)})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert "expired" in tg.answers[0][1]
    assert mt5.sent_orders == []
    assert len(tg.edits) == 1
    assert tg.edits[0][3] == {"inline_keyboard": []}  # nut da go
    assert "expired" in tg.edits[0][2]


def test_double_use_only_places_once(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    tg2 = FakeTelegram([[_callback(2, "cb-2", 1234567890, "ord:ord-1")]])
    assert _run(tg2, store, mt5, ks_path=ks_path) == 0
    assert len(mt5.sent_orders) == 1
    assert "already processed" in tg2.answers[0][1]


def test_unknown_callback_data(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "xyz:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [("cb-1", "Invalid order")]
    assert mt5.sent_orders == []


# --- Kiem tra lai luc dat lenh ---------------------------------------
def test_kill_switch_on_refused(tmp_decisions, monkeypatch):
    log_path, ks_path = tmp_decisions
    monkeypatch.setattr(killswitch, "is_engaged",
                        lambda path=None: True)
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [("cb-1", "Kill switch is ON")]
    assert mt5.sent_orders == []
    assert store.orders["ord-1"]["status"] == "pending"


def test_non_demo_account_refused(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10, trade_mode=1, server="Exness-MT5Real7")
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [("cb-1", "Not a demo account")]
    assert mt5.sent_orders == []


def test_margin_check_fails_refused(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10, order_check_retcode=10019)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [("cb-1", "Insufficient margin")]
    assert mt5.sent_orders == []


def test_entry_deviation_beyond_tolerance_refused(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order(entry=1.10)})
    mt5 = FakeMT5(bid=1.12)  # lech 1.8% > 1.0% mac dinh
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [("cb-1", "Price moved too far from recommendation")]
    assert mt5.sent_orders == []
    assert store.orders["ord-1"]["status"] == "pending"


def test_entry_deviation_within_tolerance_placed(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order(entry=1.10)})
    mt5 = FakeMT5(bid=1.105)  # lech 0.45% < 1.0%
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert len(mt5.sent_orders) == 1
    assert mt5.sent_orders[0]["price"] == 1.105  # gia thi truong luc dat
    assert mt5.sent_orders[0]["sl"] == 1.05  # SL/TP/volume giu nguyen
    assert tg.answers == [("cb-1", "Order placed")]


def test_place_failure_keeps_pending(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10, order_send_retcode=10013)  # MT5 tu choi
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert len(mt5.sent_orders) == 1  # da thu gui
    assert "Order failed" in tg.answers[0][1]
    assert store.orders["ord-1"]["status"] == "pending"  # thu lai duoc
    assert store.orders["ord-1"]["ticket"] is None
    assert "ORDER-PLACED-VIA-TELEGRAM" not in _log_text(log_path)


# --- skip -------------------------------------------------------------
def test_skip_marks_cancelled(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "skip:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert store.orders["ord-1"]["status"] == "cancelled"
    assert mt5.sent_orders == []
    assert tg.answers == [("cb-1", "Ignored")]
    assert len(tg.edits) == 1
    assert "Ignored" in tg.edits[0][2]
    assert tg.edits[0][3] == {"inline_keyboard": []}


# --- Do ben: update xau / store hong / update thuong -----------------
def test_corrupt_store_does_not_crash(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakeBrokenStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert mt5.sent_orders == []
    assert tg.answers == [("cb-1", "Error reading pending order")]


def test_bad_update_in_batch_logged_and_skipped(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    batch = [{"update_id": 5},  # khong co callback_query — bo qua
             {"update_id": 6, "callback_query": {
                 "id": "cb-bad", "message": {
                     "message_id": 11, "chat": {"id": 1234567890},
                     "text": ORIG_TEXT}}},  # co chat, thieu data
             {"update_id": 7, "message": {"text": "hello"}},  # update thuong
             _callback(8, "cb-1", 1234567890, "ord:ord-1")]
    tg = FakeTelegram([batch])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert len(mt5.sent_orders) == 1  # update tot trong batch van chay
    assert ("cb-bad", "Invalid order") in tg.answers


def test_non_callback_update_ignored_silently(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[{"update_id": 1, "message": {"text": "hi"}}]])
    assert _run(tg, store, mt5, ks_path=ks_path) == 0
    assert tg.answers == [] and tg.edits == []
    assert mt5.sent_orders == []


def test_get_updates_error_once_returns_1(tmp_decisions, kill_off):
    log_path, ks_path = tmp_decisions
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)

    class FailingTelegram(FakeTelegram):
        def get_updates(self, offset=None, timeout=30, cfg=None):
            raise RuntimeError("mat mang")

    tg = FailingTelegram([])
    assert _run(tg, store, mt5, ks_path=ks_path) == 1
    assert mt5.sent_orders == []


def test_custom_bot_token_env_reaches_get_updates(monkeypatch,
                                                  tmp_decisions):
    """cfg telegram.bot_token_env khong mac dinh phai toi duoc get_updates,
    va telegram._resolve_token(cfg) phai doc dung bien moi truong do
    (khong roi ve DIAMONDX10_TELEGRAM_TOKEN mac dinh)."""
    from diamondx10 import telegram as telegram_mod

    log_path, ks_path = tmp_decisions
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("DX10_CUSTOM_TOKEN_ENV", "sentinel-custom-token")
    cfg = _cfg()
    cfg["telegram"]["bot_token_env"] = "DX10_CUSTOM_TOKEN_ENV"
    store = FakePendingStore({"ord-1": _order()})
    mt5 = FakeMT5(bid=1.10)
    tg = FakeTelegram([[]])
    assert _run(tg, store, mt5, cfg=cfg, ks_path=ks_path) == 0
    assert len(tg.get_updates_calls) == 1
    received_cfg = tg.get_updates_calls[0]["cfg"]
    assert received_cfg is cfg
    assert (received_cfg.get("telegram") or {}).get(
        "bot_token_env") == "DX10_CUSTOM_TOKEN_ENV"
    assert telegram_mod._resolve_token(received_cfg) == \
        "sentinel-custom-token"


# --- Tich hop voi store + telegram THAT (HTTP gia) ---------------------
def test_integration_real_store_and_real_telegram(monkeypatch, tmp_path):
    """Chay dau-cuoi voi PendingOrderStore that + telegram.py that,
    chi gia lop HTTP (urlopen) + MT5 gia."""
    import json
    import urllib.request

    from diamondx10 import telegram as telegram_mod
    from diamondx10.pending import PendingOrderStore

    log_path = tmp_path / "decisions-log.csv"
    monkeypatch.setattr(decisions, "LOG", log_path)
    ks_path = tmp_path / "kill-switch.json"
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "tok-test")
    store = PendingOrderStore(path=tmp_path / "pending.json")
    order_id = store.create(
        {"desk": "forex", "manager": "Yuling Pan", "symbol": "EURUSD",
         "action": "BUY", "entry": 1.10, "sl": 1.05, "tp": 1.20,
         "volume": 0.01, "risk_usd": 75.0}, ttl_min=15)
    update = _callback(1, "cb-1", 1234567890, f"ord:{order_id}")
    seen = {"requests": [], "get_updates_calls": 0}

    class FakeResponse:
        def __init__(self, body):
            self.status = 200
            self._body = body

        def read(self):
            return json.dumps(self._body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        seen["requests"].append(request)
        if "getUpdates" in request.full_url:
            seen["get_updates_calls"] += 1
            body = {"ok": True, "result": [update]}
        else:
            body = {"ok": True, "result": True}
        return FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    mt5 = FakeMT5(bid=1.10)
    assert run_listener(_cfg(), telegram=telegram_mod, mt5_module=mt5,
                        pending_store=store, once=True,
                        kill_switch_path=ks_path) == 0
    assert seen["get_updates_calls"] == 1
    assert len(mt5.sent_orders) == 1
    assert store.get(order_id)["status"] == "placed"
    assert store.get(order_id)["ticket"] == 777001
    assert "ORDER-PLACED-VIA-TELEGRAM" in _log_text(log_path)
    payloads = {req.full_url.split("/")[-1]:
                json.loads(req.data.decode("utf-8"))
                for req in seen["requests"]}
    assert payloads["answerCallbackQuery"]["text"] == "Order placed"
    edit = payloads["editMessageText"]
    assert "ORDER PLACED" in edit["text"] and "777001" in edit["text"]
    assert edit["reply_markup"] == {"inline_keyboard": []}
