"""Listener Telegram — nhan nut DAT LENH / BO QUA tu khuyen nghi (DEMO).

Chay tren CUNG MAY voi MT5 terminal (may Windows / VPS Windows), vi
dat lenh demo can goi MetaTrader5 local qua execution.place_demo_order.
Khong chay duoc tren may khong co MT5 terminal — luc do moi callback
ord: deu bi tu choi (khong xac minh duoc tai khoan demo / gia).

Luong xu ly 1 callback (ord:<id> / skip:<id>):
  1. Chi chat trong config telegram.chat_id moi co quyen (so sanh dang
     str ca 2 ben, vi config luu chat_id dang chuoi).
  2. skip: mark_cancelled + sua tin goc (bo nut, ghi "Ignored").
  3. ord: resolve lenh cho -> kiem tra lai luc dat lenh theo thu tu:
     kill switch -> tai khoan demo -> ky quy -> do lech entry.
     Dat lenh bang tham so DA LUU (symbol/action/volume/SL/TP), gia
     vao lenh la gia thi truong luc dat (KHONG tinh lai SL/TP/volume).
     Dat xong: mark_placed(ticket), ghi decisions log voi marker
     ORDER-PLACED-VIA-TELEGRAM TRUOC khi sua tin nhan, roi sua tin
     (bo nut, them "ORDER PLACED — ticket #...") + tra loi callback.
  4. Dat lenh that bai (MT5 tu choi / loi): lenh cho GIU NGUYEN
     trang thai pending (khong mark placed/cancelled) de co the
     thu lai trong TTL cua no.

An toan:
- Chi DEMO: tai khoan phai vuot chan check_demo_only cua execution.py.
- Log-first: log_decision ghi truoc khi sua tin nhan Telegram.
- Khong bao gio crash vi 1 update xau hay store hong: moi update
  xu ly trong try/except, ghi loi roi xu ly tiep update sau.
- Chi dung stdlib. Khong ghi token / chat_id / mat khau vao log.

Cac ham Telegram (get_updates / answer_callback_query /
edit_message_text / edit_message_reply_markup) va PendingOrderStore
duoc truyen vao (de test) hoac import lazy luc chay — xem run_listener.
"""
import time

from . import execution, killswitch
from .decisions import log_decision

DEFAULT_MAX_ENTRY_DEVIATION_PCT = 1.0
EMPTY_KEYBOARD = {"inline_keyboard": []}

# Ly do tu kho lenh cho (pending.py, tieng Viet khong dau — giu nguyen
# ben trong store) dich sang tieng Anh tai bien Telegram: chi text
# nguoi dung thay tren Telegram moi doi, logic/store khong doi.
_REASON_EN = {
    "khong tim thay lenh": "Order not found",
    "lenh da het han": "Order expired",
    "lenh da duoc xu ly": "Order already processed",
}


def _to_telegram_reason(reason):
    """Dich ly do noi bo (tieng Viet) sang tieng Anh de gui Telegram."""
    return _REASON_EN.get(reason or "", reason or "")


def _telegram_cfg(cfg):
    return (cfg or {}).get("telegram") or {}


def _allowed_chat_id(cfg):
    return str(_telegram_cfg(cfg).get("chat_id") or "")


def _max_deviation_pct(cfg):
    try:
        return float(_telegram_cfg(cfg).get(
            "max_entry_deviation_pct") or DEFAULT_MAX_ENTRY_DEVIATION_PCT)
    except (TypeError, ValueError):
        return DEFAULT_MAX_ENTRY_DEVIATION_PCT


def _latest_price(mt5, symbol, price_fn=None):
    """Gia thi truong moi nhat (bid) — giong MT5Feed.latest_price.

    price_fn (neu co, de test): ham lay gia theo symbol. Neu khong,
    doc truc tiep mt5.symbol_info_tick(symbol). Tra None neu khong
    lay duoc gia (nguoi goi tu choi lenh thay vi doan gia).
    """
    if price_fn is not None:
        try:
            return float(price_fn(symbol))
        except (TypeError, ValueError):
            return None
    if mt5 is None or not hasattr(mt5, "symbol_info_tick"):
        return None
    try:
        tick = mt5.symbol_info_tick(symbol)
    except Exception:  # noqa: BLE001 — khong lay duoc tick thi tra None
        return None
    if tick is None:
        return None
    for field in ("bid", "ask"):
        try:
            return float(tick[field])
        except (TypeError, KeyError, IndexError):
            pass
        value = getattr(tick, field, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return None


def _answer(tg, callback_query_id, text, cfg=None):
    """Tra loi callback (best-effort, khong bao gio raise)."""
    if not callback_query_id:
        return False
    try:
        return bool(tg.answer_callback_query(callback_query_id,
                                             text=text, cfg=cfg))
    except Exception as exc:  # noqa: BLE001 — tra loi loi thi chi ghi log
        print(f"LOI listener answer_callback_query: {exc}")
        return False


def _edit_message(tg, chat_id, message_id, text, cfg=None):
    """Sua tin goc + go bo nut (inline_keyboard rong).

    Best-effort, khong bao gio raise. Neu edit_message_text loi thi
    thu edit_message_reply_markup de it nhat go duoc nut.
    """
    if chat_id is None or message_id is None:
        return False
    try:
        return bool(tg.edit_message_text(chat_id, message_id, text,
                                         reply_markup=EMPTY_KEYBOARD,
                                         cfg=cfg))
    except Exception as exc:  # noqa: BLE001 — sua tin loi thi chi ghi log
        print(f"LOI listener edit_message_text: {exc}")
    try:
        return bool(tg.edit_message_reply_markup(
            chat_id, message_id, reply_markup=EMPTY_KEYBOARD, cfg=cfg))
    except Exception as exc:  # noqa: BLE001 — go nut loi thi chi ghi log
        print(f"LOI listener edit_message_reply_markup: {exc}")
        return False


def _refuse(tg, callback_query_id, chat_id, message_id, orig_text, reason,
            cfg=None):
    """Tu choi lenh: tra loi ly do + sua tin goc (bo nut, ghi ly do)."""
    _answer(tg, callback_query_id, reason, cfg=cfg)
    note = f"\n\nOrder could not be placed: {reason}"
    _edit_message(tg, chat_id, message_id, (orig_text or "") + note,
                  cfg=cfg)


def _resolve_order(tg, store, callback_query_id, chat_id, message_id,
                   orig_text, order_id, cfg=None):
    """Resolve lenh cho. Tra (order, True) neu ok, (None, False) neu
    khong xu ly duoc (da tra loi + sua tin roi)."""
    try:
        order, reason = store.resolve(order_id)
    except Exception as exc:  # noqa: BLE001 — store hong cung khong crash
        print(f"LOI listener resolve lenh {order_id!r}: {exc}")
        _answer(tg, callback_query_id, "Error reading pending order",
                cfg=cfg)
        _edit_message(tg, chat_id, message_id,
                      (orig_text or "") + "\n\nError reading pending order.",
                      cfg=cfg)
        return None, False
    if order is None:
        reason = _to_telegram_reason(reason or "khong tim thay lenh")
        _answer(tg, callback_query_id, reason, cfg=cfg)
        _edit_message(tg, chat_id, message_id,
                      (orig_text or "") + "\n\nOrder could not be "
                      f"processed: {reason}",
                      cfg=cfg)
        return None, False
    return order, True


def _handle_skip(tg, store, callback_query_id, chat_id, message_id,
                 orig_text, order_id, order, cfg=None):
    try:
        store.mark_cancelled(order_id)
    except Exception as exc:  # noqa: BLE001 — mark loi thi chi ghi log
        print(f"LOI listener mark_cancelled {order_id!r}: {exc}")
    _answer(tg, callback_query_id, "Ignored", cfg=cfg)
    _edit_message(tg, chat_id, message_id,
                  (orig_text or "") + "\n\nIgnored.", cfg=cfg)


def place_pending_order(cfg, mt5, store, order_id, kill_switch_path=None,
                        price_fn=None):
    """Dat 1 lenh cho — phan loai (core) khong phu thuoc Telegram.

    Dung chung cho nut Telegram (listener._handle_place) va API web
    (webapi POST /api/pending/{id}/place): resolve lenh cho roi kiem
    tra lai theo thu tu kill switch -> tai khoan demo -> gia thi
    truong -> ky quy -> do lech entry, sau do dat lenh bang tham so
    DA LUU (gia vao lenh la gia thi truong luc dat, KHONG tinh lai
    SL/TP/volume). Dat xong: mark_placed + ghi decisions log.

    Tra dict {"ok", "ticket", "reason", "kind"}:
      kind "placed"  — dat xong, ticket la so lenh MT5.
      kind "refused" — bi chan o 1 buoc kiem tra (kill switch, demo,
        gia, ky quy, do lech); lenh cho GIU NGUYEN pending.
      kind "failed"  — MT5 tu choi / loi khi dat (them khoa "error"
        la thong bao loi goc); lenh cho GIU NGUYEN pending de thu lai.
      kind "not_found" — resolve that bai (khong co / het han / da xu
        ly); reason la ly do (tieng Anh).
      kind "error"   — store hong, khong doc duoc lenh.
    """
    try:
        order, reason = store.resolve(order_id)
    except Exception as exc:  # noqa: BLE001 — store hong cung khong crash
        print(f"LOI listener resolve lenh {order_id!r}: {exc}")
        return {"ok": False, "ticket": None,
                "reason": "Error reading pending order", "kind": "error"}
    if order is None:
        return {"ok": False, "ticket": None,
                "reason": _to_telegram_reason(reason or "khong tim thay lenh"),
                "kind": "not_found"}
    symbol = order.get("symbol")
    action = order.get("action")
    desk = order.get("desk") or "DEMO"
    manager = order.get("manager") or ""
    # 1. Kill switch.
    try:
        engaged = killswitch.is_engaged(kill_switch_path)
    except Exception as exc:  # noqa: BLE001 — doc kill switch loi thi chan
        print(f"LOI listener kill switch: {exc}")
        engaged = True
    if engaged:
        return {"ok": False, "ticket": None, "reason": "Kill switch is ON",
                "kind": "refused"}
    # 2. Tai khoan demo (lay account_info 1 lan, dung chung cho ca
    #    chan demo-only, margin check va place_demo_order).
    account_info = None
    server = None
    if mt5 is not None and hasattr(mt5, "account_info"):
        try:
            account_info = mt5.account_info()
            server = getattr(account_info, "server", None)
        except Exception as exc:  # noqa: BLE001 — khong doc duoc thi chan
            print(f"LOI listener account_info: {exc}")
            account_info = None
    try:
        execution.check_demo_only(cfg, mt5, account_info, server)
    except Exception:
        return {"ok": False, "ticket": None,
                "reason": "Not a demo account", "kind": "refused"}
    # 3. Gia thi truong luc dat (dung cho ca margin check, do lech
    #    entry va gia vao lenh).
    price = _latest_price(mt5, symbol, price_fn)
    if price is None:
        return {"ok": False, "ticket": None,
                "reason": "Could not get market price", "kind": "refused"}
    # 4. Ky quy (helper cua execution.py).
    try:
        margin_ok, _margin_msg = execution.check_margin(
            mt5, symbol, order.get("volume"), price, account_info)
    except Exception as exc:  # noqa: BLE001 — kiem tra loi thi chan
        print(f"LOI listener check_margin: {exc}")
        margin_ok = False
    if not margin_ok:
        return {"ok": False, "ticket": None,
                "reason": "Insufficient margin", "kind": "refused"}
    # 5. Do lech entry so voi khuyen nghi.
    try:
        entry = float(order.get("entry"))
    except (TypeError, ValueError):
        entry = 0.0
    if entry:
        deviation = abs(price - entry) / abs(entry) * 100.0
        if deviation > _max_deviation_pct(cfg):
            return {"ok": False, "ticket": None,
                    "reason": "Price moved too far from recommendation",
                    "kind": "refused"}
    # Dat lenh bang tham so DA LUU (khong tinh lai SL/TP/volume);
    # gia vao lenh la gia thi truong luc dat.
    try:
        result = execution.place_demo_order(
            mt5, symbol=symbol, action=action,
            volume=order.get("volume"), price=price,
            sl=order.get("sl"), tp=order.get("tp"),
            desk=desk, manager=manager, cfg=cfg,
            account_info=account_info, server=server)
    except Exception as exc:
        # Dat that bai: GIU NGUYEN pending de thu lai trong TTL.
        print(f"LOI listener place_demo_order {order_id!r}: {exc}")
        return {"ok": False, "ticket": None,
                "reason": f"Order failed: {exc}", "kind": "failed",
                "error": str(exc)}
    ticket = result.get("order")
    try:
        store.mark_placed(order_id, ticket)
    except Exception as exc:  # noqa: BLE001 — lenh da dat, chi ghi log
        print(f"LOI listener mark_placed {order_id!r}: {exc}")
    # Log-first: ghi decisions log TRUOC khi sua tin nhan Telegram.
    log_decision(symbol, "ORDER-PLACED-VIA-TELEGRAM",
                 f"Telegram ord:{order_id} ticket {ticket} — DEMO {action} "
                 f"{symbol} {order.get('volume')} lot @ {price} "
                 f"(SL {order.get('sl')}, TP {order.get('tp')})",
                 desk=desk, manager=manager)
    return {"ok": True, "ticket": ticket, "reason": "Order placed",
            "kind": "placed"}


def _handle_place(tg, cfg, mt5, store, callback_query_id, chat_id,
                  message_id, orig_text, order_id, order,
                  kill_switch_path=None, price_fn=None):
    """Dat lenh ord: — goi core place_pending_order roi tra loi Telegram
    theo ket qua (giong hanh vi cu: tu choi / loi / dat xong)."""
    result = place_pending_order(
        cfg, mt5, store, order_id, kill_switch_path=kill_switch_path,
        price_fn=price_fn)
    kind = result.get("kind")
    reason = result.get("reason") or ""
    if kind == "placed":
        _edit_message(tg, chat_id, message_id,
                      f"ORDER PLACED — ticket #{result.get('ticket')}\n"
                      f"{orig_text or ''}",
                      cfg=cfg)
        _answer(tg, callback_query_id, "Order placed", cfg=cfg)
        return
    if kind == "not_found":
        _answer(tg, callback_query_id, reason, cfg=cfg)
        _edit_message(tg, chat_id, message_id,
                      (orig_text or "") + "\n\nOrder could not be "
                      f"processed: {reason}",
                      cfg=cfg)
        return
    if kind == "error":
        _answer(tg, callback_query_id, reason, cfg=cfg)
        _edit_message(tg, chat_id, message_id,
                      (orig_text or "") + "\n\nError reading pending order.",
                      cfg=cfg)
        return
    if kind == "failed":
        _answer(tg, callback_query_id, reason[:180], cfg=cfg)
        _edit_message(tg, chat_id, message_id,
                      (orig_text or "") + "\n\nOrder could not be placed: "
                      f"{result.get('error') or reason}",
                      cfg=cfg)
        return
    _refuse(tg, callback_query_id, chat_id, message_id, orig_text,
            reason, cfg=cfg)


def _handle_callback(tg, cfg, mt5, store, update,
                     kill_switch_path=None, price_fn=None):
    """Xu ly 1 update co callback_query. Khong raise."""
    cb = update.get("callback_query") or {}
    callback_query_id = cb.get("id")
    message = cb.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    orig_text = message.get("text") or ""
    # Chi chat trong config moi co quyen.
    allowed = _allowed_chat_id(cfg)
    if not allowed or str(chat_id) != allowed:
        _answer(tg, callback_query_id, "No permission", cfg=cfg)
        print("Listener: bo qua callback tu chat khong co quyen "
              f"(chat_id={chat_id!r}).")
        return
    data = cb.get("data") or ""
    if data.startswith("ord:"):
        kind, order_id = "ord", data[len("ord:"):]
    elif data.startswith("skip:"):
        kind, order_id = "skip", data[len("skip:"):]
    else:
        _answer(tg, callback_query_id, "Invalid order", cfg=cfg)
        return
    if not order_id:
        _answer(tg, callback_query_id, "Invalid order", cfg=cfg)
        return
    order, ok = _resolve_order(tg, store, callback_query_id, chat_id,
                               message_id, orig_text, order_id, cfg=cfg)
    if not ok:
        return
    if kind == "skip":
        _handle_skip(tg, store, callback_query_id, chat_id, message_id,
                     orig_text, order_id, order, cfg=cfg)
        return
    _handle_place(tg, cfg, mt5, store, callback_query_id, chat_id,
                  message_id, orig_text, order_id, order,
                  kill_switch_path=kill_switch_path, price_fn=price_fn)


def _handle_update(tg, cfg, mt5, store, update,
                   kill_switch_path=None, price_fn=None):
    """Xu ly 1 update: chi callback_query moi xu ly, con lai bo qua.
    Khong raise — moi loi deu ghi log roi tra ve."""
    if not isinstance(update, dict):
        print(f"LOI listener: update khong phai dict: {update!r}")
        return
    if "callback_query" not in update:
        return  # update thuong (tin nhan, ...) — bo qua lang le
    _handle_callback(tg, cfg, mt5, store, update,
                     kill_switch_path=kill_switch_path, price_fn=price_fn)


def run_listener(cfg, telegram=None, mt5_module=None, pending_store=None,
                 once=False, interval_sec=5, kill_switch_path=None,
                 price_fn=None):
    """Chay listener Telegram: long-poll get_updates, xu ly nut bam.

    Parameters
    ----------
    cfg : dict config (can telegram.chat_id, telegram.max_entry_deviation_pct).
    telegram : module/object co get_updates(offset, timeout, cfg) /
        answer_callback_query(id, text, cfg) / edit_message_text(chat_id,
        message_id, text, reply_markup, cfg) /
        edit_message_reply_markup(chat_id, message_id, reply_markup, cfg)
        — neu None thi import diamondx10.telegram (phai co cac ham nay).
        cfg duoc truyen xuong de telegram.py giai quyet dung ten bien
        moi truong token (config telegram.bot_token_env).
    mt5_module : module MetaTrader5 (that hoac gia) — neu None thi thu
        load that qua data.mt5_feed.load_mt5(); load khong duoc thi
        chay tiep voi mt5=None (moi ord: deu bi tu choi vi khong
        xac minh duoc demo/gia).
    pending_store : PendingOrderStore (that hoac gia) — neu None thi
        tao PendingOrderStore() mac dinh.
    once : True thi chi xu ly dung 1 batch (1 lan goi get_updates)
        roi tra ve; False thi lap den khi Ctrl+C.
    interval_sec : nghi giua cac vong long-poll (mac dinh 5).
    kill_switch_path : duong dan file kill-switch.json (mac dinh file
        that); truyen duong dan tam de test.
    price_fn : ham lay gia theo symbol (mac dinh doc
        mt5.symbol_info_tick); chi dung de test.

    Tra 0 khi dung sach (once xong / Ctrl+C), 1 khi get_updates loi
    o che do once. Khong bao gio crash vi 1 update xau.
    """
    tg = telegram
    if tg is None:
        from . import telegram as telegram_mod
        tg = telegram_mod
    for name in ("get_updates", "answer_callback_query",
                 "edit_message_text"):
        if not hasattr(tg, name):
            raise RuntimeError(
                f"telegram module chua co ham {name} — can ban cap nhat "
                "cua telegram.py (get_updates / answer_callback_query / "
                "edit_message_text / edit_message_reply_markup).")
    store = pending_store
    if store is None:
        from .pending import PendingOrderStore
        store = PendingOrderStore()
    mt5 = mt5_module
    if mt5 is None:
        try:
            from .data.mt5_feed import load_mt5
            mt5 = load_mt5()
        except Exception as exc:  # noqa: BLE001 — chay tiep, ord: se bi chan
            print(f"CANH BAO listener: khong load duoc MT5 ({exc}) — "
                  "chi nhan lenh sau khi co MT5 terminal.")
            mt5 = None
    offset = None
    try:
        while True:
            try:
                updates = tg.get_updates(offset=offset, timeout=30,
                                       cfg=cfg)
            except Exception as exc:  # noqa: BLE001 — get_updates loi
                print(f"LOI listener get_updates: {exc}")
                if once:
                    return 1
                time.sleep(interval_sec)
                continue
            for update in updates or []:
                try:
                    _handle_update(tg, cfg, mt5, store, update,
                                   kill_switch_path=kill_switch_path,
                                   price_fn=price_fn)
                except Exception as exc:  # noqa: BLE001 — 1 update xau
                    print(f"LOI listener xu ly update: {exc}")
                if isinstance(update, dict):
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = update_id + 1 if offset is None else max(
                            offset, update_id + 1)
            if once:
                return 0
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("Listener dung (Ctrl+C).")
        return 0
