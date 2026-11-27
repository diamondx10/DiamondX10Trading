"""Canh bao Telegram cho vong lap live (Phase D).

Chi gui canh bao ve tin hieu / lenh / bi chan — KHONG gui tin tuc tu dong
(tin chay tay truoc phien, theo quyet dinh da chot).

An toan:
- Token KHONG hardcode, KHONG doc tu file: chi lay tu tham so truyen vao
  hoac bien moi truong (ten bien lay tu config telegram.bot_token_env,
  mac dinh DIAMONDX10_TELEGRAM_TOKEN). Chat ID lay tu config
  telegram.chat_id (hoac tham so truyen vao).
- Chi gui khi config telegram.enabled = true (mac dinh false) va co du
  token + chat_id.
- Loi gui (mang / timeout / HTTP != 200) tra False + in canh bao,
  KHONG bao gio raise — khong lam crash vong lap live.
- Chi dung stdlib (urllib), khong them dependency.
"""
import json
import os
import urllib.error
import urllib.request

from .i18n import resolve_language, t

DEFAULT_TOKEN_ENV = "DIAMONDX10_TELEGRAM_TOKEN"
TELEGRAM_API = "https://api.telegram.org"
TIMEOUT_SECONDS = 10


def telegram_enabled(cfg):
    """True neu user bat canh bao Telegram trong config (mac dinh false)."""
    return bool(((cfg or {}).get("telegram") or {}).get("enabled", False))


def setup_status(cfg):
    """Trang thai cau hinh Telegram: cai gi da co, thieu cai gi.

    Tra dict {enabled, has_token, has_chat_id, ready, missing} voi
    missing la danh sach ten muc thieu (tieng Viet, de in huong dan).
    ready = True khi du ca 3: enabled + token + chat_id.
    """
    enabled = telegram_enabled(cfg)
    has_token = bool(_resolve_token(cfg))
    has_chat_id = bool(_resolve_chat_id(cfg))
    missing = []
    if not enabled:
        missing.append("telegram.enabled chua bat (config.yaml)")
    if not has_token:
        missing.append("token bot (bien moi truong "
                       "DIAMONDX10_TELEGRAM_TOKEN)")
    if not has_chat_id:
        missing.append("chat_id (muc telegram.chat_id trong config.yaml)")
    return {"enabled": enabled, "has_token": has_token,
            "has_chat_id": has_chat_id,
            "ready": enabled and has_token and has_chat_id,
            "missing": missing}


def format_test_message(lang=None, cfg=None):
    """Tin nhan thu — gui bang lenh `telegram-test` de kiem tra ket noi.

    lang: "vi" | "en" (uu tien); khong truyen thi doc config qua
    get_language (mac dinh "vi").
    """
    from datetime import datetime, timezone
    lang = resolve_language(lang, cfg)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return t("tg.test_message", lang, time=now)


def _resolve_token(cfg, token=None):
    """Token theo thu tu: tham so truyen vao > bien moi truong.

    Ten bien moi truong lay tu config telegram.bot_token_env (mac dinh
    DIAMONDX10_TELEGRAM_TOKEN); muc nay chi la TEN bien, khong phai
    token — khong bao gio ghi token vao config.yaml.
    """
    if token:
        return token
    env_name = ((cfg or {}).get("telegram") or {}).get(
        "bot_token_env") or DEFAULT_TOKEN_ENV
    return os.environ.get(env_name) or ""


def _resolve_chat_id(cfg, chat_id=None):
    """Chat ID theo thu tu: tham so truyen vao > config telegram.chat_id."""
    if chat_id:
        return str(chat_id)
    return str(((cfg or {}).get("telegram") or {}).get("chat_id") or "")


def _post(method, payload, token):
    """POST 1 lenh Bot API, tra (status, body) hoac (None, None) khi loi.

    Khong bao gio raise — loi mang / timeout / JSON loi chi in canh bao.
    """
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{TELEGRAM_API}/bot{token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
            return resp.status, body
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError) as exc:  # noqa: BLE001 — gui loi thi bao, khong crash
        print(f"CANH BAO Telegram: khong goi duoc {method} ({exc}).")
        return None, None


def _ok(status, body):
    """True khi Bot API tra HTTP 200 + ok=true."""
    return status == 200 and isinstance(body, dict) and body.get("ok") is True


def send_message(text, *, token=None, chat_id=None, cfg=None,
                 reply_markup=None):
    """Gui 1 tin nhan Telegram qua Bot API. Tra True neu gui duoc.

    Thieu token/chat_id, mang loi, timeout hoac HTTP != 200 / ok != true
    thi in canh bao va tra False — KHONG raise.

    reply_markup (neu co): dict ban phim inline, gui kem trong payload.
    """
    token = _resolve_token(cfg, token)
    chat_id = _resolve_chat_id(cfg, chat_id)
    if not token or not chat_id:
        print("CANH BAO Telegram: thieu token hoac chat_id — "
              "khong gui duoc canh bao (kiem tra bien moi truong "
              "DIAMONDX10_TELEGRAM_TOKEN va muc telegram.chat_id).")
        return False
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    status, body = _post("sendMessage", payload, token)
    if status is None:
        return False
    if _ok(status, body):
        return True
    print(f"CANH BAO Telegram: gui that bai (HTTP {status}, "
          f"tra ve: {body}).")
    return False


def order_keyboard(pending_id, action, symbol, volume, lang=None,
                   cfg=None):
    """Ban phim inline cho 1 lenh cho: nut dat lenh + nut bo qua.

    callback_data chi mang id ngan ("ord:<id>" / "skip:<id>") — KHONG
    mang tham so lenh (tham so nam trong store, tra theo id).
    lang: "vi" | "en" (uu tien); khong truyen thi doc config qua
    get_language (mac dinh "vi").
    """
    lang = resolve_language(lang, cfg)
    vol = _fmt_number(volume)
    return {"inline_keyboard": [
        [{"text": t("tg.place_button", lang, action=action, symbol=symbol,
                    volume=vol),
          "callback_data": f"ord:{pending_id}"}],
        [{"text": t("tg.ignore_button", lang),
          "callback_data": f"skip:{pending_id}"}],
    ]}


def answer_callback_query(callback_query_id, text=None, *, token=None,
                          cfg=None):
    """Tra loi 1 callback query (an spinner / hien thong bao ngan).

    Token lay tu tham so hoac bien moi truong (nhu send_message).
    Loi thi tra False — KHONG raise.
    """
    token = _resolve_token(cfg, token)
    if not token:
        print("CANH BAO Telegram: thieu token — khong tra loi duoc "
              "callback query.")
        return False
    payload = {"callback_query_id": callback_query_id}
    if text is not None:
        payload["text"] = text
    status, body = _post("answerCallbackQuery", payload, token)
    if status is None:
        return False
    if _ok(status, body):
        return True
    print(f"CANH BAO Telegram: answerCallbackQuery that bai "
          f"(HTTP {status}, tra ve: {body}).")
    return False


def edit_message_text(chat_id, message_id, text, reply_markup=None, *,
                      token=None, cfg=None):
    """Sua text cua 1 tin nhan da gui. Loi thi tra False — KHONG raise."""
    token = _resolve_token(cfg, token)
    if not token:
        print("CANH BAO Telegram: thieu token — khong sua duoc tin nhan.")
        return False
    payload = {"chat_id": str(chat_id), "message_id": message_id,
               "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    status, body = _post("editMessageText", payload, token)
    if status is None:
        return False
    if _ok(status, body):
        return True
    print(f"CANH BAO Telegram: editMessageText that bai "
          f"(HTTP {status}, tra ve: {body}).")
    return False


def edit_message_reply_markup(chat_id, message_id, reply_markup=None, *,
                              token=None, cfg=None):
    """Sua / go ban phim inline cua 1 tin nhan da gui.

    reply_markup None hoac {} thi go nut (gui reply_markup rong).
    Loi thi tra False — KHONG raise.
    """
    token = _resolve_token(cfg, token)
    if not token:
        print("CANH BAO Telegram: thieu token — khong sua duoc ban phim.")
        return False
    payload = {"chat_id": str(chat_id), "message_id": message_id,
               "reply_markup": reply_markup or {}}
    status, body = _post("editMessageReplyMarkup", payload, token)
    if status is None:
        return False
    if _ok(status, body):
        return True
    print(f"CANH BAO Telegram: editMessageReplyMarkup that bai "
          f"(HTTP {status}, tra ve: {body}).")
    return False


def get_updates(offset=None, timeout=30, *, token=None, cfg=None):
    """Lay cac update moi tu Bot API (long polling).

    Tra list "result"; loi mang / HTTP / JSON thi tra [] — KHONG raise.
    """
    token = _resolve_token(cfg, token)
    if not token:
        print("CANH BAO Telegram: thieu token — khong lay duoc updates.")
        return []
    payload = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    status, body = _post("getUpdates", payload, token)
    if status is None or not _ok(status, body):
        if status is not None:
            print(f"CANH BAO Telegram: getUpdates that bai "
                  f"(HTTP {status}, tra ve: {body}).")
        return []
    result = body.get("result")
    return result if isinstance(result, list) else []


def _fmt_number(value):
    """So gia/SL/TP: bo so 0 thua (vd 103.0 -> '103', 1.16 giu nguyen)."""
    if value is None:
        return "-"
    return f"{float(value):g}"


def _risk_reward(entry, sl, tp):
    """Ti le loi:lo tu entry/SL/TP (vd '1:2'). Khong tinh duoc thi None."""
    try:
        risk = abs(float(entry) - float(sl))
        reward = abs(float(tp) - float(entry))
    except (TypeError, ValueError):
        return None
    if risk <= 0:
        return None
    ratio = reward / risk
    ratio_text = f"{ratio:.1f}".rstrip("0").rstrip(".")
    return f"1:{ratio_text}"


def format_signal_alert(result, desk, manager=None, recommended=False,
                        pending_id=None, lang=None, cfg=None):
    """Tin KHUYEN NGHI mua/ban khi co tin hieu BUY/SELL dat chuan.

    result: dict ket qua cua process_symbol (co symbol/action/price/
    sl/tp/volume/risk_usd/time/reason/order khi co). Tin day du theo
    dinh dang khuyen nghi cua Kathy: entry + SL + TP + khoi luong +
    rui ro toi da + ti le R:R + ly do. Luon danh dau DEMO.

    recommended=True: day chi la KHUYEN NGHI — lenh CHUA dat, nguoi
    dung phai bam nut tren Telegram de dat. Them dong "Not placed yet"
    va ma lenh cho (pending_id) de tra theo store.

    lang: "vi" | "en" (uu tien); khong truyen thi doc config qua
    get_language (mac dinh "vi"). Ban tieng Anh giu NGUYEN nhu cu.
    """
    lang = resolve_language(lang, cfg)
    symbol = result.get("symbol", "?")
    action = result.get("action", "?")
    lines = [t("tg.signal_header", lang, action=action)]
    desk_line = f"Desk: {desk}"
    if manager:
        desk_line += f" — {manager}"
    lines.append(desk_line)
    if recommended:
        lines.append(t("tg.not_placed", lang))
        if pending_id:
            lines.append(t("tg.pending_id", lang, id=pending_id))
    lines.append(t("tg.symbol_order", lang, symbol=symbol, action=action))
    if result.get("price") is not None:
        lines.append(t("tg.entry", lang,
                       value=_fmt_number(result.get('price'))))
    if result.get("sl") is not None or result.get("tp") is not None:
        lines.append(t("tg.sl_tp", lang,
                       sl=_fmt_number(result.get('sl')),
                       tp=_fmt_number(result.get('tp'))))
    if result.get("volume"):
        lines.append(t("tg.volume", lang,
                       value=_fmt_number(result.get('volume'))))
    if result.get("risk_usd") is not None:
        lines.append(t("tg.max_risk", lang,
                       value=_fmt_number(result.get('risk_usd'))))
    rr = _risk_reward(result.get("price"), result.get("sl"),
                      result.get("tp"))
    if rr:
        lines.append(t("tg.risk_reward", lang, value=rr))
    if result.get("status") == "TRADED" and not recommended:
        status_line = t("tg.status_placed", lang)
        if result.get("order") is not None:
            status_line += t("tg.ticket", lang, ticket=result['order'])
        lines.append(status_line)
    if result.get("time"):
        lines.append(t("tg.time_utc", lang, value=result['time']))
    if result.get("reason"):
        lines.append(t("tg.reason", lang, value=result['reason']))
    return "\n".join(lines)


def format_post_summary(post, lang=None, cfg=None):
    """Tom tat 1 bai phan tich de gui qua Telegram (CHI THONG TIN).

    post: dict bai dang (co desk/analyst/symbol/action/confidence/
    summary/entry/sl/tp). Chi goi cho bai BUY/SELL (NEUTRAL khong
    gui — posts.PostStore.publish_post tu kiem tra). Tin ngan gon,
    KHONG kem nut dat lenh (khong tao lenh cho tu bai dang).

    lang: "vi" | "en" (uu tien); khong truyen thi doc config qua
    get_language (mac dinh "vi"). Ban tieng Anh giu NGUYEN nhu cu.
    """
    lang = resolve_language(lang, cfg)
    symbol = post.get("symbol", "?")
    action = post.get("action", "?")
    lines = [t("tg.post_header", lang, symbol=symbol, action=action)]
    lines.append(t("tg.post_desk", lang, desk=post.get("desk", "?"),
                   analyst=post.get("analyst", "?")))
    if post.get("entry") is not None:
        lines.append(t("tg.entry", lang,
                       value=_fmt_number(post.get("entry"))))
    if post.get("sl") is not None or post.get("tp") is not None:
        lines.append(t("tg.sl_tp", lang,
                       sl=_fmt_number(post.get("sl")),
                       tp=_fmt_number(post.get("tp"))))
    if post.get("confidence") is not None:
        lines.append(t("tg.post_confidence", lang,
                       value=f"{float(post['confidence']):g}"))
    if post.get("summary"):
        lines.append(t("tg.post_summary", lang, value=post["summary"]))
    return "\n".join(lines)


def format_blocked_alert(result, desk, manager=None, lang=None,
                         cfg=None):
    """Tin canh bao khi lenh bi chan (BLOCKED-*).

    Co symbol / ma chan (status) / ly do day du de Kathy/Yuling biet
    vi sao khong co lenh. Neu tin hieu da co entry/SL/TP (vd
    BLOCKED-VOLUME-ZERO, BLOCKED-MARGIN) thi kem theo de biet lenh
    dinh dat la gi.

    lang: "vi" | "en" (uu tien); khong truyen thi doc config qua
    get_language (mac dinh "vi"). Ban tieng Anh giu NGUYEN nhu cu.
    """
    lang = resolve_language(lang, cfg)
    symbol = result.get("symbol", "?")
    status = result.get("status", "BLOCKED")
    lines = [t("tg.blocked_header", lang, desk=desk, symbol=symbol,
               status=status)]
    desk_line = f"Desk: {desk}"
    if manager:
        desk_line += f" — {manager}"
    lines.append(desk_line)
    if result.get("action") in ("BUY", "SELL"):
        lines.append(t("tg.signal", lang, action=result['action']))
    if result.get("price") is not None:
        lines.append(t("tg.entry", lang,
                       value=_fmt_number(result.get('price'))))
    if result.get("sl") is not None or result.get("tp") is not None:
        lines.append(t("tg.sl_tp", lang,
                       sl=_fmt_number(result.get('sl')),
                       tp=_fmt_number(result.get('tp'))))
    if result.get("volume"):
        lines.append(t("tg.volume", lang,
                       value=_fmt_number(result.get('volume'))))
    if result.get("reason"):
        lines.append(t("tg.reason", lang, value=result['reason']))
    return "\n".join(lines)
