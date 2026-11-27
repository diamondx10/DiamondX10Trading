# Nền tảng giao dịch DiamondX10 — khung thảo luận cả nhóm

> Mục đích: cả nhóm thảo luận để chốt **một nền tảng giao dịch vững chắc**,
> gồm phân tích cơ bản và phân tích kỹ thuật, rồi LJ và Kel hiện thực
> thành nguyên tắc trong quant tool. File này là **khung thảo luận** —
> chưa phải quyết định. Quyết định đã chốt sẽ ghi vào
> `docs/trading-principles.md` (bản chuẩn) rồi mới cài vào code.
>
> Ngày lập khung: 2026-11-26. Trạng thái: **đang chờ thảo luận cả nhóm**.

---

## 1. Danh mục giao dịch đã chốt (2026-11-26)

Danh mục này đã cập nhật vào `config.example.yaml` và `config.yaml` local.

| Mảng | Symbol | Người phụ trách | Ghi chú |
|---|---|---|---|
| Forex | EURUSD | Yuling Pan | Chỉ giao dịch EURUSD (bỏ USDJPY, GBPUSD khỏi cấu hình) |
| Vàng | XAUUSD | Yumi | |
| Crypto | BTCUSD, BNBUSD, ETHUSD | Rich | Thêm BNB so với trước (trước chỉ có BTC, ETH) |
| Chứng khoán Mỹ | AMD, CDNS, SNPS, INTC, NVDA | Kathy | Thêm SNPS, INTC so với trước (trước chỉ có NVDA, AMD, CDNS). Toàn cổ phiếu AI / chip / EDA tool |

**Cần kiểm tra trên MT5 demo trước khi giao dịch** (`mt5-symbols`):
tên symbol thực tế trên server Exness có thể khác mã niêm yết — đặc biệt
BNB (ghi tạm `BNBUSD`) và nhóm cổ phiếu Mỹ (CDNS, SNPS, INTC có thể
không có trên server demo, giống lưu ý về CDNS trong `docs/mt5-demo.md`).
Symbol nào không có thì hoặc đổi tên theo đúng tên trên MT5, hoặc loại
khỏi danh mục desk đó.

**Đa symbol đã làm xong 2026-11-26:** `mt5-dry-run` / `mt5-trade` giờ chạy
lần lượt mọi symbol của desk, vốn desk chia đều cho từng symbol
(2.500 USD/desk: crypto 833 USD/coin, chứng khoán 500 USD/mã).
Hệ quả cần nhớ: BTC với 833 USD vẫn tính ra dưới 0,01 lot ở stop 5%
nên chưa đặt được — xem `docs/mt5-demo.md` §5.

## 2. Phân tích cơ bản — đã chốt 2026-11-26

**Yuling làm khung phân tích cơ bản chung + vĩ mô** (lãi suất, lạm phát,
USD, dòng tiền lớn — phần nối cả 4 mảng lại với nhau) **và cơ bản Forex**.
**Mỗi desk tự làm cơ bản mảng mình**, Yuling duyệt cuối về mặt lý thuyết.

**Nguồn tin — khác nhau hoàn toàn (chốt 2026-11-26):** Yuling tìm
thông tin **chính ngạch về vĩ mô** (lãi suất, lạm phát, USD, dòng tiền
lớn, báo cáo chính thức). Rich tìm thông tin **rò rỉ về crypto trên
x.com** (tin rò rỉ, tin đồn) để cấp cho team. Thông tin rò rỉ phải
ghi rõ là **chưa xác minh** cho tới khi có xác nhận — không được viết
như sự thật đã kiểm chứng, và không được dùng làm căn cứ duy nhất
cho một quyết định giao dịch. Xem `DiamondX-VR-Office/docs/real-outputs.md`.

**Luồng lấy tin thị trường trong tool (merge 2026-11-27, từ
ThaoResearch — xem `docs/market-news.md`):** lệnh `news [--desk]
[--days]` lấy feed RSS công khai (Bloomberg/FT/WSJ/Investing.com/
Nasdaq/Mining.com/OilPrice/Guardian + truy vấn Google News theo từng
desk), lọc theo từ khóa từng desk, gắn tag desk, đánh dấu tin khẩn,
dedup bằng SQLite (`data/news-history.db`). **Phân tầng độ tin cậy —
bắt buộc, repo gốc không có:** tier 1 CHÍNH THỐNG (Yuling đọc tay từ
Fed/ECB/SEC..., không có feed tự động), tier 2 BÁO CHÍ (feed RSS),
tier 3 RÒ RỈ (x.com — Rich tìm tay, luôn gắn nhãn CHƯA XÁC MINH).
Chu kỳ chạy: trước phiên giao dịch + trước giờ tin lớn
(CPI/FOMC/Nonfarm). Tin chỉ là bối cảnh cho người phụ trách desk đọc
trước khi duyệt tín hiệu — **không tự đổi tín hiệu, không tự đặt lệnh**,
và **không bao giờ lấy "giá" từ tiêu đề báo** (giá chỉ từ MT5).
Mỗi mảng cần trả lời, bằng văn bản, trước khi chốt nguyên tắc:

**Forex — EURUSD (Yuling)**
- Động lực chính theo dõi là gì: chênh lệch lãi suất Fed–ECB, lạm phát,
  tăng trưởng, dòng tiền trú ẩn?
- Tin / dữ liệu nào thì **đứng ngoài** (không giao dịch): CPI, Fed, ECB,
  Nonfarm?
- Điều kiện vĩ mô nào thì cấm mở lệnh mới, chỉ quản lý lệnh cũ?

**Vàng — XAUUSD (Yumi)**
- Vàng chạy theo gì trong khung của nhóm: lãi suất thực USD, USD index,
  rủi ro địa chính trị, nhu cầu ngân hàng trung ương?
- Khi nào vàng đi ngược USD thì xử lý thế nào?

**Crypto — BTC, BNB, ETH (Rich)**
- Phân biệt động lực từng coin: BTC (vĩ mô / dòng tiền tổ chức),
  ETH (hệ sinh thái, nâng cấp mạng), BNB (sàn Binance, hệ sinh thái BNB)?
  Hay giao dịch cả 3 theo cùng một khung?
- Rủi ro riêng cần nguyên tắc: biến động mạnh, thanh khoản, tin về sàn / pháp lý?

**Chứng khoán Mỹ — AMD, CDNS, SNPS, INTC, NVDA (Kathy)**
- Luận điểm từng công ty: AI / chip / EDA tool, chu kỳ bán dẫn, cạnh tranh?
- Mốc cơ bản nào thì loại một mã khỏi danh mục: báo cáo tài chính xấu,
  mất thị phần, định giá vượt ngưỡng?
- Mùa báo cáo thu nhập (earnings) thì giao dịch hay đứng ngoài?

**Đầu ra yêu cầu:** mỗi mảng một bản tóm tắt cơ bản tối đa 1 trang,
kèm danh sách "điều kiện cấm giao dịch" cụ thể. Bản này lưu vào `research/`
theo đúng người phụ trách mảng đó.

## 3. Phân tích kỹ thuật — Kathy, Yumi, Rich (và một chỗ trống)

Mỗi người phụ trách kỹ thuật cho mảng của mình. **Mọi quy tắc kỹ thuật
đưa ra phải viết được thành dạng "nếu … thì …" với con số cụ thể**,
để LJ/Kel cài thẳng vào code — quy tắc mơ hồ ("xu hướng mạnh thì mua")
không hiện thực được.

**Kathy — chứng khoán Mỹ (AMD, CDNS, SNPS, INTC, NVDA)**
- Khung thời gian chính: ngày? H1? M15 như hiện tại?
- Tín hiệu vào lệnh: xu hướng (SMA), động lượng (RSI), hay breakout?
  Ngưỡng số cụ thể cho từng chỉ báo?
- Mỗi mã dùng chung một quy tắc hay mã biến động mạnh (NVDA) có ngưỡng riêng?

**Yumi — vàng XAUUSD**
- Vàng có đặc thù gì khác cổ phiếu/forex: biên độ ngày lớn, chạy mạnh
  theo phiên Mỹ, nhạy tin? Stop loss tính theo ATR hay % cố định?
- Khung thời gian và ngưỡng chỉ báo riêng cho vàng?

**Rich — crypto (BTC, BNB, ETH)**
- Crypto chạy 24/7, biến động lớn: khung thời gian nào, ngưỡng chỉ báo
  nào khác hẳn 3 mảng còn lại?
- 3 coin dùng chung quy tắc hay tách riêng (BTC theo vĩ mô, ETH/BNB
  theo hệ sinh thái)?

**Phân tích kỹ thuật Forex (EURUSD) — đã chốt 2026-11-26: Yuling làm.**
Yuling phụ trách cả cơ bản và kỹ thuật cho desk Forex của mình.

**Bối cảnh bổ sung từ repo DiamondX10 cũ (merge 2026-11-27 — chỉ là
bối cảnh, chưa phải quy tắc chặn lệnh; xem
`docs/trading-principles.md` mục 21–23):** regime theo ADX (≥ 25
trending, 15–25 transitional, < 15 ranging) + hướng SMA20/SMA50 in kèm
tín hiệu; macro edge DXY/US10Y/VIX/SPX in trong báo cáo ngày khi Yuling
cung cấp snapshot; breakout Donchian 20 là **ứng viên so sánh trong
backtest** (`backtest --strategy donchian`), chưa dùng live. Nếu backtest
(walk-forward) cho thấy Donchian hoặc regime giúp ích, nhóm chốt lại ở
đây rồi mới cài vào đường live.

**Đầu ra yêu cầu (mỗi mảng):**
1. Chỉ báo dùng + khung thời gian + ngưỡng số.
2. Điều kiện vào lệnh (BUY/SELL) viết dạng nếu–thì.
3. Điều kiện thoát lệnh: chốt lời, cắt lỗ (theo ATR hay %?), thoát khi
   tín hiệu đảo chiều?
4. Điều kiện **không** giao dịch (sideway, biến động quá thấp/quá cao,
   quanh tin mạnh).

## 4. Từ thảo luận thành nguyên tắc trong tool

Quy trình đã chốt từ trước (`docs/workflow.md`), áp cho lần này:

```
Thảo luận cả nhóm
  → chốt từng quy tắc (ghi vào docs/trading-principles.md)
  → Yuling duyệt lý thuyết
  → LJ cài model/chiến lược (strategies/, models/, signals.py)
  → Kel cài dữ liệu/feed/quản lý vốn (data/, risk.py, execution.py)
  → test (tests/) + dry-run trên MT5 demo
  → mới cho chạy mt5-trade demo
```

Nguyên tắc đặt tên file khi cài đặt:
- Chiến lược riêng từng mảng (nếu chốt tách): `strategies/forex.py`,
  `strategies/xauusd.py`, `strategies/crypto.py`,
  `strategies/us_securities.py` — hiện 4 file này đang dùng chung quy
  tắc SMA ở `strategies/base.py`.
- Chỉ báo dùng chung: `models/quant.py` (SMA, RSI, ATR, volatility
  đã có sẵn).
- Rủi ro/vốn: `risk.py` + `config.example.yaml`.

## 5. Checklist hiện thực (LJ / Kel)

- [x] Vòng lặp đa symbol cho mỗi desk (crypto 3 coin, chứng khoán 5 mã) —
      làm xong 2026-11-26 (`__main__._desk_symbols`).
- [x] Chia vốn desk cho nhiều symbol: chia đều, 2.500 USD/desk
      (crypto 833 USD/coin, chứng khoán 500 USD/mã) — làm xong 2026-11-26
      (`__main__.split_desk_capital`). Hệ quả: BTC vẫn dưới 0,01 lot.
- [ ] Nối RSI vào tín hiệu (đã có trong nghiên cứu Forex, code chưa có).
- [ ] Stop loss theo ATR thay cho 5% cố định (đã có trong nghiên cứu, code chưa có).
- [x] Quy tắc chốt lời cố định 5% (TP 5% / SL 5%, tỉ lệ 1:1) — chốt xong 2026-11-26.
- [ ] Thoát lệnh khi tín hiệu đảo chiều.
- [ ] Chính sách đòn bẩy: tài khoản demo dùng đòn bẩy bao nhiêu, tool có cần
      kiểm tra ký quỹ trước khi gửi lệnh không (hiện tool chưa kiểm tra ký quỹ;
      đòn bẩy không làm khối lượng tính theo % rủi ro to hơn).
- [x] Rủi ro theo từng symbol thay cho một con số chung 10% — làm xong 2026-11-26
      (`risk.per_symbol_pct`: EURUSD 3%, XAUUSD 10%, BTCUSD 8%, còn lại 1%).
- [ ] Xem lại giới hạn drawdown 10%: một lệnh vàng thua (250 USD) đã chạm giới hạn.
- [ ] Chặn drawdown 10% trong luồng chạy (hàm đã có, chưa được gọi).
- [ ] Kiểm tra tên symbol thực tế trên MT5 demo (`mt5-symbols`) cho
      BNBUSD, SNPS, INTC, CDNS; cập nhật lại cấu hình nếu tên khác.
- [ ] Backtest tính lãi/lỗ thật cho danh mục mới, thay cho bản nháp
      hiện tại (mới chỉ in tín hiệu cuối).

## 6. Định nghĩa xong việc

Nền tảng này coi là xong khi cả 4 điều sau đúng:

1. `docs/trading-principles.md` cập nhật đủ: tín hiệu, rủi ro, thoát lệnh,
   chốt lời cho **từng mảng**, không còn mục [CẦN CHỐT] nào liên quan
   đến danh mục này.
2. Code đã cài đúng các quy tắc đó, có test, `pytest` pass.
3. Dry-run trên MT5 demo chạy được cho **mọi symbol** trong danh mục,
   không còn symbol nào báo THIEU mà chưa có quyết định xử lý.
4. Mọi dòng chat/biên bản mới trên trang văn phòng đều nói đúng việc đã
   làm, có bằng chứng kiểm chứng được — quy tắc "nói phải làm"
   (`DiamondX-VR-Office/docs/dialogue-grounding.md`).
