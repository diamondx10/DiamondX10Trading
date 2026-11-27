"""i18n — dich cac chuoi hien thi cho nguoi dung (Telegram / briefing).

Ngon ngu ho tro: "vi" (mac dinh) va "en". Moi chuoi nguoi dung thay
deu nam trong STRINGS, co ca 2 ban — test/test_i18n.py kiem tra tinh
day du (thieu khoa o 1 ngon ngu thi test do).

Quy tac:
- `get_language(cfg)`: doc khoa `language:` o cap cao nhat cua config;
  chi "vi" / "en" la hop le, moi gia tri khac (thieu, sai, khong phai
  chuoi) deu ve "vi".
- `t(key, lang)`: lay chuoi theo khoa + ngon ngu, format voi kwargs;
  khoa khong co thi tra chinh khoa do (khong raise — de test bat).
- CLI / console / log KHONG qua day: van tieng Viet khong dau.
- Noi dung tin tuc (tieu de / nguon / tom tat lay tu RSS) KHONG dich:
  chi template moi dich. Ten truong trong verdict JSON giu nguyen.
"""
SUPPORTED_LANGUAGES = ("vi", "en")
DEFAULT_LANGUAGE = "vi"

STRINGS = {
    "vi": {
        # --- Telegram: khuyen nghi mua/ban ---
        "tg.signal_header": "💎 DiamondX10 — {action} KHUYẾN NGHỊ (DEMO)",
        "tg.not_placed": "Chưa đặt lệnh — bấm nút để đặt lệnh",
        "tg.pending_id": "Mã lệnh chờ: {id}",
        "tg.symbol_order": "Mã: {symbol} | Lệnh: {action}",
        "tg.entry": "Giá vào: {value}",
        "tg.sl_tp": "SL: {sl} | TP: {tp}",
        "tg.volume": "Khối lượng: {value} lot",
        "tg.max_risk": "Rủi ro tối đa: ~{value} USD",
        "tg.risk_reward": "Rủi ro:Lợi nhuận (R:R): {value}",
        "tg.status_placed": "Trạng thái: Đã đặt lệnh DEMO.",
        "tg.ticket": " Ticket: {ticket}.",
        "tg.time_utc": "Thời gian (UTC): {value}",
        "tg.reason": "Lý do: {value}",
        # --- Telegram: lenh bi chan / tin thu / nut bam ---
        "tg.blocked_header": "DiamondX10 [{desk}] {symbol}: "
                             "LỆNH BỊ CHẶN ({status})",
        "tg.signal": "Tín hiệu: {action}",
        "tg.test_message": (
            "DiamondX10 — Tin nhắn thử Telegram.\n"
            "Kết nối bot OK. Bot sẽ gửi khuyến nghị mua/bán "
            "khi có tín hiệu đạt tiêu chuẩn.\nThời gian: {time}"),
        "tg.place_button": "✅ Đặt lệnh {action} {symbol} {volume} lot",
        "tg.ignore_button": "❌ Bỏ qua",
        # --- Listener: tra loi callback / sua tin nhan ---
        "listener.order_placed": "Đã đặt lệnh",
        "listener.order_placed_heading": "ĐÃ ĐẶT LỆNH — ticket #{ticket}",
        "listener.no_permission": "Không có quyền",
        "listener.invalid_order": "Lệnh không hợp lệ",
        "listener.order_not_found": "Không tìm thấy lệnh",
        "listener.order_expired": "Lệnh đã hết hạn",
        "listener.order_processed": "Lệnh đã được xử lý",
        "listener.kill_switch_on": "Kill switch đang BẬT",
        "listener.not_demo": "Không phải tài khoản demo",
        "listener.insufficient_margin": "Không đủ ký quỹ",
        "listener.price_moved": "Giá đã lệch quá xa so với khuyến nghị",
        "listener.no_market_price": "Không lấy được giá thị trường",
        "listener.ignored": "Đã bỏ qua",
        "listener.error_reading": "Lỗi đọc lệnh chờ",
        "listener.order_failed_prefix": "Đặt lệnh thất bại: ",
        "listener.could_not_place": "Không thể đặt lệnh: {reason}",
        "listener.could_not_process": "Không thể xử lý lệnh: {reason}",
        # --- muse-auto: canh bao het phien Muse ---
        "muse.session_expired": (
            "DiamondX10 — Phiên trình duyệt Muse đã hết hạn.\n"
            "Chu kỳ PTCB tự động không gửi được briefing: phiên Muse "
            "đã hết (hiện trang đăng nhập / không tìm thấy ô soạn tin).\n"
            "Vui lòng đăng nhập lại thủ công: chạy "
            "`python -m diamondx10 muse-send --file <briefing.md> "
            "--no-wait` ở chế độ headed một lần rồi đăng nhập muse.ai "
            "trong cửa sổ trình duyệt.\n"
            "Vòng live vẫn dùng verdict trước đó trong lúc chờ."),
        # --- Briefing PTCB: template .md ---
        "briefing.title": "# BRIEFING PHAN TICH — DESK {desk}",
        "briefing.greeting": "Chao {analyst},",
        "briefing.intro": (
            "Briefing nay tong hop gia + tin hieu ky thuat (TA), tin thi "
            "truong va boi canh vi mo de ban dua ra verdict cho desk "
            "{desk} truoc phien giao dich."),
        "briefing.desk": "- Desk: {desk}",
        "briefing.analyst": "- Analyst: {analyst}",
        "briefing.created": "- Ngay tao (UTC): {stamp}",
        "briefing.symbols": "- Symbols: {symbols}",
        "briefing.ta_heading": "## TONG QUAN KY THUAT (TA)",
        "briefing.symbol_price": "- Gia moi nhat: {price}",
        "briefing.symbol_signal": "- Tin hieu: {action} — {reason}",
        "briefing.symbol_regime": "- Regime: {regime}",
        "briefing.patterns": "- Patterns:",
        "briefing.levels": "- Levels: entry={entry} SL={sl} TP={tp} "
                           "ATR={atr}",
        "briefing.news_heading": "## TIN THI TRUONG",
        "briefing.news_errors": "Loi lay tin:",
        "briefing.tier_1_label": "CHINH THONG",
        "briefing.tier_2_label": "BAO CHI",
        "briefing.tier_3_label": "RO RI — CHUA XAC MINH",
        "briefing.tier_3_warning": (
            "CANH BAO: tin ro ri CHUA XAC MINH — khong dung lam can cu "
            "duy nhat cho quyet dinh giao dich."),
        "briefing.no_news": "(khong co tin.)",
        "briefing.urgent_flag": "[KHAN]",
        "briefing.macro_heading": "## VI MO (MACRO)",
        "briefing.macro_edge": "- {symbol}: macro edge score {score} — "
                               "{summary}",
        "briefing.verdict_heading": "## KET LUAN CAN TRA VE (VERDICT)",
        "briefing.verdict_intro": (
            "{analyst} tra ve verdict theo dung mau JSON duoi day "
            "(1 object JSON duy nhat, khong them truong ngoai mau)."),
        "briefing.verdict_rules": (
            'direction chi nhan "buy" | "sell" | "neutral"; '
            "confidence la so 0..1; drivers / risks la danh sach chuoi; "
            "created_utc la thoi gian ISO UTC luc tao verdict."),
        "briefing.regime_none": "(khong co thong tin regime)",
        "briefing.regime_direction": "huong {value}",
        "briefing.regime_volatility": "bien dong {value}",
        "briefing.regime_confidence": "do tin cay {value}",
        "briefing.pattern_times": "x{count} lan",
        "briefing.pattern_latest_bar": "bar moi nhat {bar}",
    },
    "en": {
        # --- Telegram: buy/sell recommendation ---
        "tg.signal_header": "💎 DiamondX10 — {action} RECOMMENDATION (DEMO)",
        "tg.not_placed": "Not placed yet — tap the button to place "
                         "the order",
        "tg.pending_id": "Pending order ID: {id}",
        "tg.symbol_order": "Symbol: {symbol} | Order: {action}",
        "tg.entry": "Entry: {value}",
        "tg.sl_tp": "SL: {sl} | TP: {tp}",
        "tg.volume": "Volume: {value} lot",
        "tg.max_risk": "Max risk: ~{value} USD",
        "tg.risk_reward": "Risk:Reward (R:R): {value}",
        "tg.status_placed": "Status: DEMO order placed.",
        "tg.ticket": " Ticket: {ticket}.",
        "tg.time_utc": "Time (UTC): {value}",
        "tg.reason": "Reason: {value}",
        # --- Telegram: blocked / test message / buttons ---
        "tg.blocked_header": "DiamondX10 [{desk}] {symbol}: "
                             "ORDER BLOCKED ({status})",
        "tg.signal": "Signal: {action}",
        "tg.test_message": (
            "DiamondX10 — Telegram test message.\n"
            "Bot connection OK. The bot will send buy/sell recommendations "
            "when a signal meets the criteria.\nTime: {time}"),
        "tg.place_button": "✅ Place {action} {symbol} {volume} lot",
        "tg.ignore_button": "❌ Ignore",
        # --- Listener: callback answers / message edits ---
        "listener.order_placed": "Order placed",
        "listener.order_placed_heading": "ORDER PLACED — ticket #{ticket}",
        "listener.no_permission": "No permission",
        "listener.invalid_order": "Invalid order",
        "listener.order_not_found": "Order not found",
        "listener.order_expired": "Order expired",
        "listener.order_processed": "Order already processed",
        "listener.kill_switch_on": "Kill switch is ON",
        "listener.not_demo": "Not a demo account",
        "listener.insufficient_margin": "Insufficient margin",
        "listener.price_moved": "Price moved too far from recommendation",
        "listener.no_market_price": "Could not get market price",
        "listener.ignored": "Ignored",
        "listener.error_reading": "Error reading pending order",
        "listener.order_failed_prefix": "Order failed: ",
        "listener.could_not_place": "Order could not be placed: {reason}",
        "listener.could_not_process": "Order could not be processed: "
                                      "{reason}",
        # --- muse-auto: Muse session-expired alert ---
        "muse.session_expired": (
            "DiamondX10 — Muse browser session expired.\n"
            "The automatic FA cycle could not send the briefing: the Muse "
            "session is gone (sign-in page shown / composer not found).\n"
            "Please re-sign in manually: run "
            "`python -m diamondx10 muse-send --file <briefing.md> --no-wait` "
            "headed once and sign in to muse.ai in the browser window.\n"
            "The live loop keeps using the previous verdict meanwhile."),
        # --- Briefing: .md template ---
        "briefing.title": "# ANALYSIS BRIEFING — DESK {desk}",
        "briefing.greeting": "Hello {analyst},",
        "briefing.intro": (
            "This briefing brings together prices + technical signals "
            "(TA), market news and the macro backdrop so you can give a "
            "verdict for desk {desk} before the trading session."),
        "briefing.desk": "- Desk: {desk}",
        "briefing.analyst": "- Analyst: {analyst}",
        "briefing.created": "- Created (UTC): {stamp}",
        "briefing.symbols": "- Symbols: {symbols}",
        "briefing.ta_heading": "## TECHNICAL OVERVIEW (TA)",
        "briefing.symbol_price": "- Latest price: {price}",
        "briefing.symbol_signal": "- Signal: {action} — {reason}",
        "briefing.symbol_regime": "- Regime: {regime}",
        "briefing.patterns": "- Patterns:",
        "briefing.levels": "- Levels: entry={entry} SL={sl} TP={tp} "
                           "ATR={atr}",
        "briefing.news_heading": "## MARKET NEWS",
        "briefing.news_errors": "News fetch errors:",
        "briefing.tier_1_label": "OFFICIAL",
        "briefing.tier_2_label": "PRESS",
        "briefing.tier_3_label": "LEAK — UNVERIFIED",
        "briefing.tier_3_warning": (
            "WARNING: leaked news NOT VERIFIED — do not use as the sole "
            "basis for a trading decision."),
        "briefing.no_news": "(no news.)",
        "briefing.urgent_flag": "[URGENT]",
        "briefing.macro_heading": "## MACRO",
        "briefing.macro_edge": "- {symbol}: macro edge score {score} — "
                               "{summary}",
        "briefing.verdict_heading": "## VERDICT TO RETURN",
        "briefing.verdict_intro": (
            "{analyst} returns the verdict using exactly the JSON "
            "template below (a single JSON object, no fields outside "
            "the template)."),
        "briefing.verdict_rules": (
            'direction only accepts "buy" | "sell" | "neutral"; '
            "confidence is a number 0..1; drivers / risks are lists of "
            "strings; created_utc is the ISO UTC time when the verdict "
            "was created."),
        "briefing.regime_none": "(no regime information)",
        "briefing.regime_direction": "direction {value}",
        "briefing.regime_volatility": "volatility {value}",
        "briefing.regime_confidence": "confidence {value}",
        "briefing.pattern_times": "x{count} times",
        "briefing.pattern_latest_bar": "latest bar {bar}",
    },
}


def normalize_language(value):
    """Chuan hoa 1 gia tri ngon ngu ve "vi" | "en" (la -> "vi")."""
    if isinstance(value, str) and value.strip().lower() in SUPPORTED_LANGUAGES:
        return value.strip().lower()
    return DEFAULT_LANGUAGE


def get_language(cfg):
    """Ngon ngu tu config: khoa `language:` cap cao nhat, mac dinh "vi".

    cfg None / khong phai dict / thieu khoa / gia tri la deu ve "vi".
    Khong bao gio raise.
    """
    if not isinstance(cfg, dict):
        return DEFAULT_LANGUAGE
    return normalize_language(cfg.get("language"))


def resolve_language(lang=None, cfg=None):
    """Ngon ngu hieu luc: lang truyen vao thang thang `lang` (neu hop
    le), khong thi doc tu config qua get_language (mac dinh "vi")."""
    if lang is not None:
        return normalize_language(lang)
    return get_language(cfg)


def t(key, lang="vi", **kwargs):
    """Lay chuoi theo khoa + ngon ngu, format voi kwargs.

    Ngon ngu la ve "vi"; khoa khong co thi tra chinh khoa do.
    """
    lang = normalize_language(lang)
    template = STRINGS.get(lang, {}).get(key)
    if template is None:
        return key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template
