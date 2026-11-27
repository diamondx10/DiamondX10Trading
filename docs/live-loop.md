# Vòng lặp live — tín hiệu M15 + lệnh DEMO + cảnh báo Telegram (Phase D)

> **CHI DEMO.** Vòng lặp live chỉ chạy với tài khoản DEMO Exness trên MT5
> terminal. Không bao giờ đặt lệnh thật. Xem chặn DEMO-ONLY trong
> `src/diamondx10/execution.py` (có test trong `tests/test_mt5.py`).

## 1. Vòng lặp làm gì

Mỗi chu kỳ (mặc định 15 phút, theo biên nến M15), tool chạy lần lượt mọi
symbol của 1 desk:

```
run_live_cycle()
  └─ với mỗi symbol: process_symbol()
       (1) đối chiếu vị thế mở (MT5 deals → nến: SL/TP/trailing/đảo chiều)
       (2) chặn drawdown (quỹ 10% → BLOCKED-DRAWDOWN-FUND, desk 5% → BLOCKED-DRAWDOWN-DESK)
       (3) chặn cửa sổ cấm giao dịch (BLOCKED-NO-TRADE-WINDOW)
       (4) chặn giới hạn 1 lệnh mới/symbol/ngày (BLOCKED-DAILY-LIMIT)
       (5) tín hiệu SMA5/SMA20 + lọc RSI (HOLD thì dừng)
       (6) SL/TP theo ATR + sizing (volume 0 thì dừng)
       (7) place_demo_order — chặn demo-only + kiểm tra ký quỹ nằm trong này
  └─ lưu state sau mỗi symbol, gửi cảnh báo Telegram, in tóm tắt chu kỳ
```

`run_live_loop()` lặp chu kỳ, ngủ tới biên nến M15 tiếp theo
(`:00/:15/:30/:45`), tới khi user Ctrl+C hoặc hết `--max-cycles`.
Lỗi 1 symbol (mất kết nối, symbol không có, đặt lệnh lỗi) chỉ ghi vào
`errors[]` của chu kỳ, không crash chu kỳ hay vòng lặp. Lỗi lấy feed thì
ghi log + bỏ symbol/chu kỳ đó.

Lệnh `mt5-trade` dùng **chung** `process_symbol()` với vòng lặp live, nên
chạy tay 1 lần và chạy vòng lặp cho cùng một kết quả với cùng một trạng
thái. `mt5-dry-run` giữ nguyên như cũ: chỉ đối chiếu + in tín hiệu,
không đặt lệnh.

## 2. Chạy trên máy Windows (có MT5 terminal)

MT5 terminal và tool phải chạy trên **cùng 1 máy Windows**, tài khoản
DEMO Exness đã đăng nhập trong terminal. Cài đặt như `docs/mt5-demo.md`
§3 (điền `login`/`server` vào `config.yaml` local, mật khẩu qua biến môi
trường `MT5_PASSWORD`, `data.provider: mt5`).

```powershell
# Chay thu 1 chu ky truoc (khuyen dung): xem tin hieu + lenh DEMO neu co
python -m diamondx10 live --desk forex --symbol EURUSD --once
python -m diamondx10 live --desk crypto --once

# Chay vong lap lien tuc trong terminal (dung khi Ctrl+C)
python -m diamondx10 live --desk forex
python -m diamondx10 live --desk xauusd --timeframe M15 --interval-min 15
```

### Chạy tự động mỗi 15 phút bằng Task Scheduler (khuyên dùng)

Chạy vòng lặp nền liên tục thì chỉ cần 1 tiến trình `live` chạy mãi, nhưng
cách bền hơn trên Windows là hẹn giờ chạy `live --once` mỗi 15 phút (mỗi
lần chạy xong thì thoát; nếu máy khởi động lại, lịch vẫn chạy tiếp):

1. Task Scheduler → Create Task → Trigger: Daily, Repeat task every
   **15 minutes**, for a duration of **Indefinitely**.
2. Action: Start a program — Program: `python.exe` (đường dẫn đầy đủ tới
   Python trong venv, vd `C:\DiamondX10Trading\.venv\Scripts\python.exe`),
   Arguments: `-m diamondx10 live --desk forex --once`,
   Start in: thư mục repo (vd `C:\DiamondX10Trading`).
3. Lặp lại cho mỗi desk (1 task/desk), hoặc 1 task chạy 4 desk bằng 4
   lệnh `live --once` nối tiếp trong 1 file `.bat`.
4. Điều kiện: chỉ chạy khi MT5 terminal đang mở — Task Scheduler không
   tự mở MT5 được; mở MT5 terminal trước (có thể cho MT5 tự chạy khi
   Windows khởi động), rồi lịch `live --once` mới có dữ liệu.

Ví dụ file `.bat` chạy 4 desk (đặt trong thư mục repo):

```bat
@echo off
cd /d C:\DiamondX10Trading
.venv\Scripts\python.exe -m diamondx10 live --desk forex --once
.venv\Scripts\python.exe -m diamondx10 live --desk xauusd --once
.venv\Scripts\python.exe -m diamondx10 live --desk crypto --once
.venv\Scripts\python.exe -m diamondx10 live --desk us_securities --once
```

### Chạy tự động trên Linux (cron) — chỉ khi đã có MT5

Trên Linux không có MT5 terminal nên `live` chỉ báo lỗi sạch (xem §5).
Nếu sau này có cầu nối MT5 trên Linux, lệnh cron tương đương:

```cron
*/15 * * * * cd /path/to/DiamondX10Trading && .venv/bin/python -m diamondx10 live --desk forex --once >> logs/live.log 2>&1
```

## 3. Cấu hình

Thêm vào `config.yaml` local (xem `config.example.yaml` — chỉ file
example mới có sẵn 2 mục này):

```yaml
live:
  timeframe: M15       # khung nen moi chu ky
  interval_min: 15     # so phut giua 2 chu ky o che do lap
telegram:
  enabled: false       # mac dinh TAT — chi gui khi bat len
  chat_id: ""          # ID chat nhan canh bao
  bot_token_env: DIAMONDX10_TELEGRAM_TOKEN
```

CLI ghi đè config: `--timeframe`, `--interval-min`, `--max-cycles`,
`--symbol`, `--desk`. `--once` = chạy 1 chu kỳ rồi thoát.

## 4. Cảnh báo Telegram

### Thiết lập (làm 1 lần)

1. Mở Telegram, chat với **@BotFather**, gửi `/newbot`, đặt tên bot
   (vd `DiamondX10 Advisor` — có thể dùng lại bot `@DiamondX10_bot`
   đã có sẵn của nhóm).
2. BotFather trả **token** — giữ bí mật, **không ghi vào config.yaml,
   không commit, không gửi trong chat nhóm**.
3. Lấy **chat_id**: nhắn 1 tin cho bot, rồi mở trên trình duyệt
   `https://api.telegram.org/bot<TOKEN>/getUpdates` và đọc `chat.id`
   (chat riêng với bot; muốn gửi vào nhóm thì thêm bot vào nhóm rồi đọc
   `chat.id` âm của nhóm).
4. Đặt token vào biến môi trường trên máy chạy tool (Windows):

   ```powershell
   setx DIAMONDX10_TELEGRAM_TOKEN "token-bot-cua-ban"
   ```

   (Đóng terminal mở lại để biến có hiệu lực.) Điền `chat_id` vào
   `config.yaml` local, bật `telegram.enabled: true`. Chạy
   `python quickstart.py --live` cũng hỏi token + chat_id và tự ghi
   `telegram.enabled: true` + `chat_id` vào `config.yaml` local; bước 7
   của quickstart còn lưu token vừa nhập vào biến môi trường (setx)
   trên Windows nên các lần chạy sau không cần nhập lại.
5. Kiểm tra kết nối ngay bằng lệnh thử (không cần đợi tín hiệu thật):

   ```bash
   python -m diamondx10 telegram-test
   ```

   Lệnh này báo rõ thiếu cái gì (chưa bật enabled / thiếu token /
   thiếu chat_id) rồi mới gửi 1 tin thử. Gửi được thì chat nhận tin
   "DiamondX10 — Telegram test message."

### Các loại cảnh báo (chỉ 3 trường hợp — tin tức chỉ kích hoạt qua
đường đăng bài khi đủ chuẩn, xem mục dưới)

| Khi nào | Nội dung |
|---|---|
| Tín hiệu BUY/SELL đạt chuẩn + lệnh DEMO đã đặt | **Khuyến nghị mua/bán**: `💎 DiamondX10 — BUY/SELL RECOMMENDATION (DEMO)` + desk + người phụ trách + entry + SL + TP + volume + max risk (USD) + R:R + số ticket + time UTC + reason (SMA/RSI/ATR) |
| Lệnh bị chặn (BLOCKED-*) | `DiamondX10 [desk] SYMBOL: ORDER BLOCKED (BLOCKED-...)` + desk + người phụ trách + lý do đầy đủ; nếu tín hiệu đã có entry/SL/TP (vd BLOCKED-VOLUME-ZERO, BLOCKED-MARGIN) thì kèm theo |
| Tín hiệu HOLD | **Không gửi** — HOLD là bình thường, không làm phiền |
| Lỗi kỹ thuật (mất feed, đặt lệnh lỗi) | **Không gửi** — chỉ ghi vào `errors[]` của chu kỳ + in log |

Khuyến nghị gửi từ cả 2 đường đặt lệnh: vòng lặp `live` (mỗi chu kỳ
M15) và lệnh 1 lần `mt5-trade` — cả hai dùng chung `process_symbol`
nên cùng 1 định dạng. `mt5-dry-run` **không gửi** (chỉ xem trước, không
đặt lệnh). Mọi khuyến nghị đều được ghi vào `decisions/decisions-log.csv`
**trước** khi gửi Telegram (log trong `process_symbol`, gửi sau khi
`process_symbol` trả về). Khuyến nghị live ở trên **tách biệt với tóm
tắt bài phân tích trên feed trang chủ** (xem `docs/web-ui.md` §8, quy
tắc 53–54): vòng live **không** đăng bài phân tích và **không** gửi
tóm tắt bài đăng — bài BUY/SELL chỉ gửi tóm tắt khi được đăng qua
`synthesize --publish` / `publish-post` / composer, nên không có
double-send.

Tin chạy tay trước phiên (lệnh `news`, xem `docs/market-news.md`) —
**vòng lặp không gửi tin tức tự động**, theo quyết định đã chốt.
Ngoại lệ duy nhất là chuẩn tin đủ điều kiện ở mục dưới — và cũng
chỉ gửi qua đường đăng bài hiện có, không phải đường gửi tin riêng.

### Tin tức đủ chuẩn cũng kích hoạt khuyến nghị (quy tắc 58)

Một tin tức **không bao giờ tự gửi Telegram một mình**. Nhưng khi
một tin đủ chuẩn, khuyến nghị Telegram được gửi qua **đường đăng bài
hiện có** (`synthesize --publish` / `POST /api/publish`, xem
`docs/web-ui.md` §8, quy tắc 53–54) — tức là tin đó đi kèm bài đăng
phân tích BUY/SELL của desk, và bài đăng đó gửi tóm tắt như mọi bài
BUY/SELL khác. Chuẩn đã chốt 2026-11-27 (cả 3 điều kiện phải cùng
đúng, kiểm tra bằng `newsfeed.news_qualifies`):

1. Verdict tác động của Muse cho chính tin đó là **buy/sell** với
   **độ tin cậy ≥ 0,6** (cùng ngưỡng `fa_high_confidence` của tổng
   hợp Yuling).
2. Tin thuộc **tier 1** (chính thống) hoặc **tier 2** (báo chí).
3. **Tổng hợp Yuling của desk đồng thuận** — hướng tổng hợp trùng
   với hướng verdict tác động (quy tắc 40: PTCB một mình không tạo
   lệnh).

Tin **tier 3** (rò rỉ, chưa xác minh) **KHÔNG BAO GIỜ kích hoạt
Telegram một mình**, dù verdict tác động có mạnh đến đâu. Module
thẻ tin (`src/diamondx10/newsfeed.py`) không gọi Telegram trực
tiếp — nó chỉ lưu thẻ + gắn impact; việc gửi vẫn thuộc về đường
đăng bài. Vòng tự động tải tin (`GET|POST /api/news-auto-fetch`,
quy tắc 60) cũng **không bao giờ gửi Telegram** — nó chỉ lấy tin
+ đăng thẻ; impact và Telegram vẫn đi qua chu kỳ briefing/verdict
và đường đăng bài hiện có.

Ngôn ngữ Telegram theo lựa chọn của user (quy tắc 44, 51): tin nhắn,
nút bấm và câu trả lời callback dùng ngôn ngữ trong `language:` của
`config.yaml` (mặc định tiếng Việt); đổi bằng nút toggle trên web UI
(`POST /api/language`, xem `docs/web-ui.md` §7).

### Khi Telegram lỗi

Gửi lỗi (mất mạng, timeout, HTTP != 200, token/chat_id sai) thì tool in
`CANH BAO Telegram: ...` và tiếp tục chạy — **không bao giờ crash vòng
lặp vì Telegram lỗi**. Thiếu token/chat_id thì cũng chỉ cảnh báo, không
gửi. Kiểm tra: token đã đặt đúng biến môi trường chưa, `chat_id` đúng
chưa, `telegram.enabled` đã `true` chưa.

## 5. Cổng phân tích cơ bản (FA gate)

Trước khi đặt lệnh DEMO, `process_symbol` (bước 6b, sau khi tính xong
volume) đọc nhận định cơ bản (PTCB) mới nhất của desk trong
`decisions/fundamental-verdicts.json` và tổng hợp với tín hiệu kỹ
thuật (PTKT) theo ma trận Yuling (xem `docs/analysis-workflow.md`,
mục `synthesis:` trong config):

- **PTCB mâu thuẫn mạnh với PTKT** (VD: PTKT BUY nhưng PTCB sell với
  tin cậy ≥ 0,6) → lệnh **bị chặn**, kết quả `BLOCKED-FA-CONFLICT`,
  ghi vào `decisions/decisions-log.csv` và gửi 1 cảnh báo chặn qua
  Telegram (như mọi trạng thái `BLOCKED-*` khác). Không đặt lệnh.
- **PTCB đồng thuận hoặc trung lập** → lệnh chạy như bình thường,
  kết quả ghi thêm `fa_note` (VD: `FA: buy 0.8`).
- **Chưa có verdict hoặc verdict cũ** (quá `verdict_max_age_hours`,
  mặc định 24 giờ) → vòng live vẫn chạy như cũ, kết quả ghi
  `FA: chua co` / `FA: cu`. Chỉ khi `synthesis.require_fa: true`
  (mặc định false) thì thiếu/cũ mới chặn lệnh.
- **PTCB một mình không bao giờ tạo lệnh:** PTKT HOLD thì không đặt
  lệnh dù PTCB có mạnh đến đâu.
- Kho nhận định lỗi/không đọc được thì cổng tự coi như chưa có PTCB
  (in cảnh báo, chạy tiếp) — lỗi PTCB không bao giờ crash vòng live.

Nhận định PTCB đến từ lệnh `verdict` (file JSON do Muse trả về sau
khi đọc briefing) — xem `docs/analysis-workflow.md`.

## 6. Chế độ khuyến nghị + nút đặt lệnh Telegram

Mặc định tool TỰ đặt lệnh DEMO khi có tín hiệu đạt chuẩn, cảnh báo
Telegram chỉ để đọc. Chế độ khuyến nghị đổi chiều đó: tool chỉ gửi
khuyến nghị kèm nút "Place order", không đặt lệnh trước; chỉ khi bấm nút
thì lệnh mới được đặt (xem `docs/trading-principles.md` mục 41–44).

- **Bật chế độ khuyến nghị:** `trading.require_confirmation: true`
  trong config, hoặc có `--recommend-only` cho 1 lần chạy
  (`live --recommend-only`, `mt5-trade --recommend-only`). Dry-run
  (`mt5-dry-run`) không bao giờ tạo lệnh chờ.
- **Khi có tín hiệu đạt chuẩn:** tool chạy hết các cổng như đường đặt
  lệnh (kill switch, drawdown, margin, giới hạn ngày, cổng PTCB) rồi
  tạo 1 lệnh chờ trong `decisions/pending-orders.json` (mã 8 ký tự),
  ghi log `RECOMMENDED` vào `decisions/decisions-log.csv` (không tính
  vào lệnh đã đặt / P&L / vị thế mở), trả kết quả `RECOMMENDED` và gửi
  khuyến nghị Telegram kèm 2 nút: **Place \<HƯỚNG> \<SYMBOL> \<lot>
  lot** và **Ignore**. Tin nhắn ghi rõ "Not placed yet — tap the button
  to place the order" (hoặc bản tiếng Việt tương đương khi
  `language: vi` — xem quy tắc 44, 51 và `docs/web-ui.md` §7).
- **Lệnh chờ chỉ sống 15 phút** (`telegram.pending_order_ttl_min`,
  mặc định 15): quá hạn thì nút hết tác dụng, bấm vào chỉ nhận được
  "Order expired". Mỗi lệnh chờ chỉ dùng được 1 lần.
- **Listener** — phải chạy RIÊNG trong 1 cửa sổ terminal nữa, TRÊN
  CÙNG MÁY Windows có MT5 terminal (vì nó cần đặt lệnh qua terminal
  đó):

  ```bash
  python -m diamondx10 telegram-listen   # long-poll nút bấm, Ctrl+C để dừng
  python -m diamondx10 telegram-listen --once   # xử lý 1 đợt rồi thoát
  ```

  Listener long-poll `getUpdates` (timeout 30 giây) và xử lý nút bấm:
  nút "Place order" kiểm tra lại trước khi đặt — kill switch phải TẮT,
  tài khoản phải DEMO, đủ ký quỹ, giá thị trường lệch khỏi giá khuyến
  nghị không quá `telegram.max_entry_deviation_pct` (mặc định 1,0%) —
  rồi đặt lệnh DEMO theo đúng thông số đã lưu (entry/SL/TP/volume),
  ghi log `ORDER-PLACED-VIA-TELEGRAM`, sửa tin nhắn gốc thành
  "ORDER PLACED — ticket #X" và gỡ nút. Nút "Ignore" hủy lệnh chờ.
  Lỗi 1 nút bấm (ví dụ kho lệnh hỏng) không crash listener.

- **Mô hình bảo mật:** chỉ chat có `telegram.chat_id` trong config
  mới bấm nút được; chat khác nhận "No permission" và bị bỏ qua. Nút
  chỉ mang mã lệnh ngắn (`ord:<id>` / `skip:<id>`, <= 64 byte), KHÔNG
  mang thông số lệnh — thông số luôn lấy từ kho lệnh chờ local
  (`decisions/pending-orders.json`), không tin dữ liệu từ Telegram.
  Lệnh chờ dùng 1 lần + hết hạn sau 15 phút. Lúc đặt lệnh, kill switch,
  tài khoản DEMO, ký quỹ và độ lệch giá được kiểm tra LẠI (không dùng
  kết quả kiểm tra lúc gửi khuyến nghị).

## 7. Giới hạn cần biết

- **Trên Linux không có MT5:** `live` báo lỗi sạch 1 dòng
  (`LOI: Chua cai goi MetaTrader5...`) và thoát mã 1, không in
  traceback dài. Chạy live thật lần đầu phải ở máy Windows có MT5.
- **Chưa kiểm chứng live:** chu kỳ thật với giá MT5 demo, lệnh demo
  thật qua `order_send`, và cảnh báo Telegram với token thật — tất cả
  mới chỉ test bằng MT5/feed/Telegram giả (`tests/test_live.py`,
  `tests/test_telegram.py`). Cần chạy `--once` trên máy Windows để
  kiểm chứng lần đầu.
- **MT5 terminal phải mở trong suốt lúc chạy.** Tắt terminal là mất kết
  nối dữ liệu và không đặt lệnh được.
- **Mỗi chu kỳ mở lại feed MT5 cho từng symbol** (đơn giản, bền khi
  terminal chập chờn) — không giữ kết nối xuyên suốt vòng lặp.
- **Giới hạn 1 lệnh mới/symbol/ngày vẫn áp dụng:** chu kỳ chạy mỗi
  15 phút nhưng sau khi đã đặt 1 lệnh cho symbol đó trong ngày thì các
  chu kỳ sau chỉ báo `BLOCKED-DAILY-LIMIT` (có cảnh báo Telegram).
- **Vòng lặp không đổi quy tắc:** không tự đổi tham số chiến lược, không
  gửi tin tức tự động, không dùng Donchian cho đường live (chỉ backtest),
  không dùng regime/macro để chặn tín hiệu, không giao dịch tiền thật.

## 8. File liên quan

- `src/diamondx10/live.py` — `process_symbol()`, `run_live_cycle()`,
  `run_live_loop()`, đối chiếu vị thế, nạp/lưu guard + positions,
  cổng PTCB (`_apply_fa_gate`, bước 6b), chế độ khuyến nghị (bước 7).
- `src/diamondx10/synthesis.py` — `synthesize()`, kho nhận định
  `decisions/fundamental-verdicts.json` (xem `docs/analysis-workflow.md`).
- `src/diamondx10/telegram.py` — `send_message()` (stdlib urllib),
  `format_signal_alert()`, `format_blocked_alert()`, `order_keyboard()`,
  `get_updates()`, `answer_callback_query()`, `edit_message_text()`.
- `src/diamondx10/pending.py` — `PendingOrderStore`,
  `decisions/pending-orders.json` (lệnh chờ xác nhận).
- `src/diamondx10/listener.py` — `run_listener()`, lệnh
  `telegram-listen` (long-poll nút bấm, đặt lệnh DEMO theo lệnh chờ).
- `src/diamondx10/__main__.py` — lệnh `live`, nhánh `mt5-trade` gọi
  `process_symbol()`, lệnh `telegram-listen`.
- `tests/test_live.py`, `tests/test_live_fa.py`, `tests/test_telegram.py`,
  `tests/test_telegram_keyboard.py`, `tests/test_pending.py`,
  `tests/test_recommend.py`, `tests/test_listener.py`.
- `docs/trading-principles.md` mục 31 (vòng lặp live [ĐÃ CÓ]),
  mục 39–40 (tổng hợp Yuling + cổng PTCB), mục 41–44 (chế độ khuyến
  nghị + nút đặt lệnh + giao diện Telegram theo ngôn ngữ đã chọn),
  mục 51 (song ngữ Anh/Việt).
