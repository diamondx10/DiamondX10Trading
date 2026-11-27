"""Test i18n backend (i18n.py + cac diem tich hop).

- (a) Day du: moi khoa co o CA 2 ngon ngu, placeholder khop nhau.
- (b) Telegram ca 2 ngon ngu: signal / blocked / test message /
  keyboard; ban tieng Anh giu NGUYEN nhu cu (so sanh chuoi day du).
- (c) Briefing ca 2 ngon ngu: template dich, noi dung tin KHONG dich,
  verdict JSON schema giu nguyen.
- (d) get_language: mac dinh + xac thuc.
- (e) Listener + muse-auto: cau tra loi / canh bao dich theo config.
"""
import copy
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions, killswitch
from diamondx10.briefing import build_briefing
from diamondx10.config import DEFAULT
from diamondx10.i18n import (
    STRINGS,
    get_language,
    normalize_language,
    resolve_language,
    t,
)
from diamondx10.listener import (
    _to_telegram_reason,
    _translate_listener_reason,
    run_listener,
)
from diamondx10.muse_auto import SESSION_EXPIRED_ALERT, session_expired_alert
from diamondx10.telegram import (
    format_blocked_alert,
    format_signal_alert,
    format_test_message,
    order_keyboard,
)

RESULT = {"symbol": "BTCUSD", "action": "BUY", "status": "RECOMMENDED",
          "reason": "SMA5 > SMA20, RSI 59", "volume": 0.02,
          "price": 61594.0, "sl": 60000.0, "tp": 64782.0,
          "risk_usd": 67.0,
          "time": "2026-11-27T09:00:00+00:00"}

EXPECTED_EN_SIGNAL = """💎 DiamondX10 — BUY RECOMMENDATION (DEMO)
Desk: crypto — Rich
Not placed yet — tap the button to place the order
Pending order ID: abcdef01
Symbol: BTCUSD | Order: BUY
Entry: 61594
SL: 60000 | TP: 64782
Volume: 0.02 lot
Max risk: ~67 USD
Risk:Reward (R:R): 1:2
Time (UTC): 2026-11-27T09:00:00+00:00
Reason: SMA5 > SMA20, RSI 59"""

EXPECTED_VI_SIGNAL = """💎 DiamondX10 — BUY KHUYẾN NGHỊ (DEMO)
Desk: crypto — Rich
Chưa đặt lệnh — bấm nút để đặt lệnh
Mã lệnh chờ: abcdef01
Mã: BTCUSD | Lệnh: BUY
Giá vào: 61594
SL: 60000 | TP: 64782
Khối lượng: 0.02 lot
Rủi ro tối đa: ~67 USD
Rủi ro:Lợi nhuận (R:R): 1:2
Thời gian (UTC): 2026-11-27T09:00:00+00:00
Lý do: SMA5 > SMA20, RSI 59"""


# --- (a) Day du -------------------------------------------------------

def test_every_key_exists_in_both_languages():
    assert set(STRINGS) == {"vi", "en"}
    vi_keys = set(STRINGS["vi"])
    en_keys = set(STRINGS["en"])
    assert vi_keys == en_keys, (
        f"chi co o vi: {sorted(vi_keys - en_keys)}; "
        f"chi co o en: {sorted(en_keys - vi_keys)}")


def test_no_empty_strings_and_placeholders_match():
    placeholder = re.compile(r"\{(\w+)\}")
    for lang in ("vi", "en"):
        for key, value in STRINGS[lang].items():
            assert isinstance(value, str) and value.strip(), \
                f"{lang}:{key} rong"
    for key in STRINGS["vi"]:
        vi_fields = set(placeholder.findall(STRINGS["vi"][key]))
        en_fields = set(placeholder.findall(STRINGS["en"][key]))
        assert vi_fields == en_fields, \
            f"{key}: placeholder vi {vi_fields} != en {en_fields}"


def test_t_falls_back_to_key_for_unknown_key():
    assert t("khong.co.khoa.nay", "vi") == "khong.co.khoa.nay"
    assert t("khong.co.khoa.nay", "en") == "khong.co.khoa.nay"


# --- (a2) Ten hien thi tien trinh Manager ------------------------------

def test_proc_display_name_translated():
    from diamondx10.i18n import proc_display_name

    assert proc_display_name("live", "vi") == "Live"
    assert proc_display_name("live", "en") == "Live"
    assert proc_display_name("listener", "vi") == "Telegram listener"
    assert proc_display_name("listener", "en") == "Telegram listener"
    assert proc_display_name("diagnostics", "vi") == "Kiểm tra hệ thống"
    assert proc_display_name("diagnostics", "en") == "System check"
    # Ten la: tra nguyen, khong dich, khong raise.
    assert proc_display_name("chua-biet", "vi") == "chua-biet"
    assert proc_display_name("chua-biet", "en") == "chua-biet"


def test_manager_reason_keys_translated():
    """Cac khoa ly do Manager: vi co dau day du, en dich het, khong
    con manh tieng Viet khong dau nao trong ban en."""
    assert t("mgr.proc_started", "vi", proc="Live") == "Đã khởi động Live"
    assert t("mgr.proc_started", "en", proc="Live") == "Live started"
    assert t("mgr.proc_running", "vi", proc="Live") == "Live đang chạy"
    assert t("mgr.proc_running", "en",
             proc="Live") == "Live is already running"
    assert t("mgr.proc_exited", "en", proc="Live",
             code=1) == ("Live exited immediately (code 1) — "
                         "check config / MT5 / log")
    assert t("mgr.telegram_test_sent", "vi") == (
        "Đã gửi tin nhắn thử lên Telegram")
    assert t("mgr.telegram_test_sent", "en") == (
        "Test message sent to Telegram")
    for key, value in STRINGS["en"].items():
        if not key.startswith("mgr."):
            continue
        for fragment in ("da khoi dong", "da chay", "khong khoi dong",
                         "thoat ngay", "chua san sang"):
            assert fragment not in value, f"{key}: {value!r}"


# --- (d) get_language -------------------------------------------------

@pytest.mark.parametrize("cfg,expected", [
    (None, "vi"),
    ({}, "vi"),
    ({"language": "vi"}, "vi"),
    ({"language": "en"}, "en"),
    ({"language": "EN"}, "en"),
    ({"language": " vi "}, "vi"),
    ({"language": "fr"}, "vi"),
    ({"language": ""}, "vi"),
    ({"language": None}, "vi"),
    ({"language": 123}, "vi"),
    ("en", "vi"),
])
def test_get_language_defaults_and_validation(cfg, expected):
    assert get_language(cfg) == expected


def test_normalize_and_resolve_language():
    assert normalize_language("en") == "en"
    assert normalize_language("xx") == "vi"
    assert normalize_language(None) == "vi"
    # lang truyen vao thang thang cfg.
    assert resolve_language("en", {"language": "vi"}) == "en"
    assert resolve_language(None, {"language": "en"}) == "en"
    assert resolve_language(None, {}) == "vi"
    assert resolve_language("fr", {"language": "en"}) == "vi"


# --- (b) Telegram -----------------------------------------------------

def test_signal_alert_english_unchanged():
    text = format_signal_alert(RESULT, "crypto", manager="Rich",
                               recommended=True, pending_id="abcdef01",
                               lang="en")
    assert text == EXPECTED_EN_SIGNAL


def test_signal_alert_vietnamese():
    text = format_signal_alert(RESULT, "crypto", manager="Rich",
                               recommended=True, pending_id="abcdef01",
                               lang="vi")
    assert text == EXPECTED_VI_SIGNAL


def test_signal_alert_language_from_config():
    assert format_signal_alert(RESULT, "crypto", manager="Rich",
                               recommended=True, pending_id="abcdef01",
                               cfg={"language": "vi"}) == EXPECTED_VI_SIGNAL
    assert format_signal_alert(RESULT, "crypto", manager="Rich",
                               recommended=True, pending_id="abcdef01",
                               cfg={"language": "en"}) == EXPECTED_EN_SIGNAL
    # Mac dinh (khong truyen lang/cfg) la tieng Viet.
    assert format_signal_alert(RESULT, "crypto", manager="Rich",
                               recommended=True,
                               pending_id="abcdef01") == EXPECTED_VI_SIGNAL
    # lang thang thang cfg.
    assert format_signal_alert(RESULT, "crypto", manager="Rich",
                               recommended=True, pending_id="abcdef01",
                               lang="en",
                               cfg={"language": "vi"}) == EXPECTED_EN_SIGNAL


def test_signal_alert_traded_status_line_both_languages():
    traded = dict(RESULT, status="TRADED", order=123456)
    en = format_signal_alert(traded, "crypto", manager="Rich", lang="en")
    assert "Status: DEMO order placed. Ticket: 123456." in en
    assert "Not placed yet" not in en
    vi = format_signal_alert(traded, "crypto", manager="Rich", lang="vi")
    assert "Trạng thái: Đã đặt lệnh DEMO. Ticket: 123456." in vi
    assert "Chưa đặt lệnh" not in vi


def test_blocked_alert_both_languages():
    result = {"symbol": "XAUUSD", "action": "BUY",
              "status": "BLOCKED-VOLUME-ZERO",
              "reason": "volume tinh duoc = 0 (kiem tra risk/entry/SL)",
              "price": 3650.98, "sl": 3600.0, "tp": 3752.94, "volume": 0}
    en = format_blocked_alert(result, "xauusd", manager="Yumi", lang="en")
    assert en == (
        "DiamondX10 [xauusd] XAUUSD: ORDER BLOCKED (BLOCKED-VOLUME-ZERO)\n"
        "Desk: xauusd — Yumi\n"
        "Signal: BUY\n"
        "Entry: 3650.98\n"
        "SL: 3600 | TP: 3752.94\n"
        "Reason: volume tinh duoc = 0 (kiem tra risk/entry/SL)")
    vi = format_blocked_alert(result, "xauusd", manager="Yumi", lang="vi")
    assert vi == (
        "DiamondX10 [xauusd] XAUUSD: LỆNH BỊ CHẶN (BLOCKED-VOLUME-ZERO)\n"
        "Desk: xauusd — Yumi\n"
        "Tín hiệu: BUY\n"
        "Giá vào: 3650.98\n"
        "SL: 3600 | TP: 3752.94\n"
        "Lý do: volume tinh duoc = 0 (kiem tra risk/entry/SL)")
    # Mac dinh qua config la tieng Viet.
    assert format_blocked_alert(result, "xauusd", manager="Yumi",
                                cfg={"language": "vi"}) == vi


def test_test_message_both_languages():
    en = format_test_message(lang="en")
    assert "DiamondX10 — Telegram test message." in en
    assert "Bot connection OK." in en
    assert "recommendations" in en
    vi = format_test_message(lang="vi")
    assert "DiamondX10 — Tin nhắn thử Telegram." in vi
    assert "Kết nối bot OK." in vi
    assert "khuyến nghị mua/bán" in vi
    assert "test message" not in vi
    assert format_test_message(cfg={"language": "vi"}) == vi
    assert format_test_message(cfg={}) == vi  # mac dinh vi


def test_order_keyboard_both_languages():
    en = order_keyboard("abcdef01", "BUY", "BTCUSD", 0.02, lang="en")
    assert [b["text"] for row in en["inline_keyboard"] for b in row] == [
        "✅ Place BUY BTCUSD 0.02 lot", "❌ Ignore"]
    vi = order_keyboard("abcdef01", "BUY", "BTCUSD", 0.02, lang="vi")
    assert [b["text"] for row in vi["inline_keyboard"] for b in row] == [
        "✅ Đặt lệnh BUY BTCUSD 0.02 lot", "❌ Bỏ qua"]
    # callback_data KHONG doi theo ngon ngu.
    assert [b["callback_data"] for row in vi["inline_keyboard"]
            for b in row] == ["ord:abcdef01", "skip:abcdef01"]
    assert order_keyboard("abcdef01", "SELL", "XAUUSD", 0.1,
                          cfg={"language": "vi"}) == order_keyboard(
        "abcdef01", "SELL", "XAUUSD", 0.1, lang="vi")


# --- (c) Briefing -----------------------------------------------------

RSS_T2_FOREX = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Forex News</title>
<item><title>Federal Reserve holds rates steady</title>
<link>https://example.com/fed-1</link>
<description>ECB and Fed signal no change to interest rates.</description>
</item></channel></rss>"""

RSS_T3_FOREX = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Leaks</title>
<item><title>Euro leak: ECB insider hints at rate move</title>
<link>https://x.com/leak-euro-1</link>
<description>Unverified euro rumour from social media.</description>
</item></channel></rss>"""


def _fake_fetcher(url, timeout):
    if "forex-t3" in url:
        return RSS_T3_FOREX
    if "forex" in url:
        return RSS_T2_FOREX
    raise RuntimeError(f"khong co feed gia cho {url}")


def _briefing_cfg(language=None):
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"],
                               "xauusd": ["XAUUSD"],
                               "crypto": ["BTCUSD"],
                               "us_securities": ["NVDA"]}}
    cfg["news"] = {
        "max_age_days": 3,
        "filters": {"blacklist_keywords": ["sponsored"],
                    "high_priority_keywords": ["Federal Reserve"]},
        "desks": {"forex": {"keywords": ["EURUSD", "euro", "ECB",
                                         "Federal Reserve", "Fed",
                                         "interest rate"]}},
        "sources": [
            {"name": "Fake Forex T2",
             "url": "https://example.com/forex-t2.rss",
             "tier": 2, "desks": ["forex"]},
            {"name": "Fake Forex T3",
             "url": "https://example.com/forex-t3.rss",
             "tier": 3, "desks": ["forex"]},
        ],
    }
    if language is None:
        cfg.pop("language", None)
    else:
        cfg["language"] = language
    return cfg


def _trend_bars(n=60, start=100.0):
    closes, c = [], start
    for i in range(n):
        c += (0.2, 0.2, -0.25)[i % 3]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class _FakeFeed:
    def __init__(self, bars=None):
        self._bars = bars if bars is not None else _trend_bars()

    def bars(self, n=60):
        return list(self._bars[-n:])

    def latest_price(self, symbol):
        return self._bars[-1]["close"]


def _build(tmp_path, language):
    result = build_briefing(_briefing_cfg(language), "forex",
                            feed=_FakeFeed(), news_fetcher=_fake_fetcher,
                            out_dir=tmp_path)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    return md, data


def test_briefing_vietnamese_default_template(tmp_path):
    # Khong co khoa language -> mac dinh vi == template cu (khong dau).
    md, data = _build(tmp_path, None)
    assert "# BRIEFING PHAN TICH — DESK FOREX" in md
    assert "Chao Yuling Pan," in md
    assert "## TONG QUAN KY THUAT (TA)" in md
    assert "## TIN THI TRUONG" in md
    assert "CHUA XAC MINH" in md
    assert "## KET LUAN CAN TRA VE (VERDICT)" in md
    assert "Federal Reserve holds rates steady" in md
    assert "Euro leak: ECB insider hints at rate move" in md


def test_briefing_english_template(tmp_path):
    md, data = _build(tmp_path, "en")
    assert "# ANALYSIS BRIEFING — DESK FOREX" in md
    assert "Hello Yuling Pan," in md
    assert "## TECHNICAL OVERVIEW (TA)" in md
    assert "- Latest price:" in md
    assert "- Signal:" in md
    assert "## MARKET NEWS" in md
    assert "Tier 2 — PRESS" in md
    assert "Tier 3 — LEAK — UNVERIFIED" in md
    assert "WARNING: leaked news NOT VERIFIED" in md
    assert "## VERDICT TO RETURN" in md
    assert 'direction only accepts "buy" | "sell" | "neutral"' in md
    # Template cu (tieng Viet) khong con trong ban tieng Anh.
    for vietnamese in ("BRIEFING PHAN TICH", "TONG QUAN KY THUAT",
                       "TIN THI TRUONG", "CHUA XAC MINH",
                       "KET LUAN CAN TRA VE"):
        assert vietnamese not in md
    # Noi dung tin KHONG dich: tieu de goc giu nguyen.
    assert "Federal Reserve holds rates steady" in md
    assert "Euro leak: ECB insider hints at rate move" in md


def test_briefing_verdict_schema_unchanged_in_both_languages(tmp_path):
    for language in ("vi", "en", None):
        md, data = _build(tmp_path, language)
        template = data["verdict_template"]
        assert set(template) == {"desk", "analyst", "direction",
                                 "confidence", "drivers", "risks", "note",
                                 "created_utc"}
        assert template["direction"] in ("buy", "sell", "neutral")
        assert 0 <= template["confidence"] <= 1
        block = re.search(r"```json\n(.*?)\n```", md, re.S).group(1)
        assert json.loads(block) == template


# --- (e) Listener + muse-auto -----------------------------------------

def test_to_telegram_reason_both_languages():
    assert _to_telegram_reason("lenh da het han") == "Order expired"
    assert _to_telegram_reason("lenh da het han", "vi") == "Lệnh đã hết hạn"
    assert _to_telegram_reason("lenh da duoc xu ly", "vi") == \
        "Lệnh đã được xử lý"
    assert _to_telegram_reason("khong tim thay lenh", "vi") == \
        "Không tìm thấy lệnh"
    assert _to_telegram_reason("Order not found", "vi") == \
        "Không tìm thấy lệnh"
    assert _to_telegram_reason("ly do la", "vi") == "ly do la"


def test_translate_listener_reason():
    assert _translate_listener_reason("Kill switch is ON", "vi") == \
        "Kill switch đang BẬT"
    assert _translate_listener_reason("Insufficient margin", "vi") == \
        "Không đủ ký quỹ"
    assert _translate_listener_reason(
        "Price moved too far from recommendation", "vi") == \
        "Giá đã lệch quá xa so với khuyến nghị"
    assert _translate_listener_reason("Order failed: retcode 10013",
                                      "vi") == "Đặt lệnh thất bại: retcode 10013"
    assert _translate_listener_reason("Kill switch is ON", "en") == \
        "Kill switch is ON"
    # Ly do dong (ten server) giu nguyen.
    dynamic = "Symbol EURUSD not found on MT5 server 'X' (tried 'EURUSDm')"
    assert _translate_listener_reason(dynamic, "vi") == dynamic


CHAT_ID = "1234567890"
ORIG_TEXT = "💎 DiamondX10 — BUY KHUYẾN NGHỊ (DEMO)\nEURUSD BUY @ 1.10"


def _listener_cfg(language):
    return {"language": language,
            "telegram": {"enabled": True, "chat_id": CHAT_ID,
                         "max_entry_deviation_pct": 1.0},
            "mt5": {"demo_only": True}}


def _order(order_id="ord-1", entry=1.10, **overrides):
    order = {"desk": "forex", "manager": "Yuling Pan", "symbol": "EURUSD",
             "action": "BUY", "entry": entry, "sl": 1.05, "tp": 1.20,
             "volume": 0.01, "risk_usd": 75.0, "status": "pending",
             "ticket": None, "expires_at": time.time() + 3600}
    order.update(overrides)
    return order


class _FakePendingStore:
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


class _FakeTelegram:
    def __init__(self, batches):
        self._batches = list(batches)
        self.answers = []
        self.edits = []
        self.markup_edits = []

    def get_updates(self, offset=None, timeout=30, cfg=None):
        return self._batches.pop(0) if self._batches else []

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


class _FakeMT5:
    TRADE_RETCODE_DONE = 10009
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, bid=1.10):
        self._bid = bid
        self.sent_orders = []

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self._bid, ask=self._bid + 0.001)

    def account_info(self):
        return SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7",
                               demo=True)

    def order_check(self, request):
        return SimpleNamespace(retcode=0)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=777001, comment="Done")

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
def _tmp_decisions(monkeypatch, tmp_path):
    log_path = tmp_path / "decisions-log.csv"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(killswitch, "is_engaged",
                        lambda path=None: False)
    return log_path, tmp_path / "kill-switch.json"


def _run_listener(tg, store, mt5, cfg, ks_path):
    return run_listener(cfg, telegram=tg, mt5_module=mt5,
                        pending_store=store, once=True,
                        kill_switch_path=ks_path)


def test_listener_vietnamese_happy_path(_tmp_decisions):
    _, ks_path = _tmp_decisions
    store = _FakePendingStore({"ord-1": _order()})
    mt5 = _FakeMT5(bid=1.10)
    tg = _FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run_listener(tg, store, mt5, _listener_cfg("vi"), ks_path) == 0
    assert len(mt5.sent_orders) == 1
    assert tg.answers == [("cb-1", "Đã đặt lệnh")]
    assert len(tg.edits) == 1
    assert "ĐÃ ĐẶT LỆNH — ticket #777001" in tg.edits[0][2]
    assert tg.edits[0][3] == {"inline_keyboard": []}


def test_listener_vietnamese_skip_and_no_permission(_tmp_decisions):
    _, ks_path = _tmp_decisions
    store = _FakePendingStore({"ord-1": _order()})
    mt5 = _FakeMT5(bid=1.10)
    tg = _FakeTelegram([[_callback(1, "cb-1", 1234567890, "skip:ord-1")]])
    assert _run_listener(tg, store, mt5, _listener_cfg("vi"), ks_path) == 0
    assert tg.answers == [("cb-1", "Đã bỏ qua")]
    assert "Đã bỏ qua." in tg.edits[0][2]

    store2 = _FakePendingStore({"ord-1": _order()})
    tg2 = _FakeTelegram([[_callback(1, "cb-1", 111111, "ord:ord-1")]])
    assert _run_listener(tg2, store2, mt5, _listener_cfg("vi"),
                         ks_path) == 0
    assert tg2.answers == [("cb-1", "Không có quyền")]
    assert mt5.sent_orders == []


def test_listener_vietnamese_expired_and_kill_switch(_tmp_decisions,
                                                     monkeypatch):
    _, ks_path = _tmp_decisions
    store = _FakePendingStore(
        {"ord-1": _order(expires_at=time.time() - 10)})
    mt5 = _FakeMT5(bid=1.10)
    tg = _FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run_listener(tg, store, mt5, _listener_cfg("vi"), ks_path) == 0
    assert "hết hạn" in tg.answers[0][1]
    assert "hết hạn" in tg.edits[0][2]

    monkeypatch.setattr(killswitch, "is_engaged",
                        lambda path=None: True)
    store2 = _FakePendingStore({"ord-1": _order()})
    tg2 = _FakeTelegram([[_callback(1, "cb-1", 1234567890, "ord:ord-1")]])
    assert _run_listener(tg2, store2, mt5, _listener_cfg("vi"),
                         ks_path) == 0
    assert tg2.answers == [("cb-1", "Kill switch đang BẬT")]


def test_session_expired_alert_both_languages():
    en = session_expired_alert(lang="en")
    assert en == SESSION_EXPIRED_ALERT
    assert "session expired" in en.lower()
    assert "re-sign in" in en.lower()
    vi = session_expired_alert(lang="vi")
    assert "Phiên trình duyệt Muse đã hết hạn" in vi
    assert "đăng nhập lại thủ công" in vi
    assert "muse-send --file <briefing.md> --no-wait" in vi
    assert "session expired" not in vi.lower()
    assert session_expired_alert(cfg={"language": "vi"}) == vi
    assert session_expired_alert(cfg={}) == vi  # mac dinh vi
    assert session_expired_alert(cfg={"language": "en"}) == en


# --- (f) WebUI: ma OTP dang nhap -------------------------------------

def test_auth_otp_message_both_languages():
    """Khoa auth.otp_message co ca 2 ngon ngu, dung placeholder, ban
    tieng Viet co dau (test day du chung da bao phu, day la kiem tra
    rieng cho khoa moi)."""
    assert "auth.otp_message" in STRINGS["vi"]
    assert "auth.otp_message" in STRINGS["en"]
    vi = t("auth.otp_message", "vi", code="123456", seconds=60)
    assert "123456" in vi
    assert "60" in vi
    assert "Mã đăng nhập của bạn" in vi
    assert "Không chia sẻ mã này" in vi
    en = t("auth.otp_message", "en", code="123456", seconds=60)
    assert "123456" in en
    assert "60" in en
    assert "Your sign-in code" in en
    assert "Never share this code" in en
    # Ban tieng Viet khong lan tieng Anh cua ban en.
    assert "Your sign-in code" not in vi
    assert "Mã đăng nhập" not in en
