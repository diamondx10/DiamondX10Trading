# Phase 0 — Chốt quy tắc từng desk (bản làm việc)

> **Trạng thái: ĐÃ CHỐT MỘT PHẦN — Phu duyệt 2026-11-27.**
> Các quy tắc khớp với quyết định đã duyệt được ghi
> **[ĐÃ CHỐT — Phu duyệt 2026-11-27]**. Các mục còn **[ĐỀ XUẤT]** là
> những điểm chưa chốt: danh sách sự kiện cấm giao dịch cụ thể (cơ chế
> kiểm tra ở Phase 4, danh sách mặc định rỗng); tách quy tắc riêng theo
> symbol (mặc định dùng chung); hạ rủi ro desk vàng (chờ số ATR thật từ
> MT5 demo). Không có gì trong file này được coi là đã chốt nếu không
> mang tag [ĐÃ CHỐT].
>
> Quy trình theo `docs/trading-foundation.md` §4: thảo luận → chốt từng
> quy tắc → Yuling duyệt lý thuyết → LJ cài model/chiến lược, Kel cài
> dữ liệu/rủi ro → test + dry-run MT5 demo → mới cho chạy `mt5-trade`.
>
> Cơ sở đã đọc khi lập bản này: `docs/trading-principles.md` §8 (checklist
> cần chốt), `docs/trading-foundation.md` §2–§3, `research/` 4 mảng.
> Bài nghiên cứu hiện chỉ có khung lý thuyết, chưa có con số cụ thể —
> trừ Forex của Yuling: "SMA ngắn vượt SMA dài và RSI không quá mua thì
> mới xem xét mua; cắt lỗ theo ATR".
>
> **Cập nhật 2026-11-27 — bảng per-symbol đã thay các quy tắc chung
> dưới đây:** các bảng kỹ thuật trong file này ghi quy tắc chung
> Phase 0 (SMA5/20 + RSI 50–70 cho mọi desk). Từ 2026-11-27,
> `strategy.per_symbol` trong `config.example.yaml` ghi đè theo
> symbol (EURUSD 8/21, XAUUSD 10/30 + RSI 55–75, BTC/ETH 9/21,
> NVDA/AMD/INTC riêng, CDNS/SNPS giữ mặc định chung — xem
> `docs/per-symbol-ta.md`, `docs/trading-principles.md` mục 61–62).
> Khi hai chỗ khác nhau thì **bảng per-symbol là bản đang chạy**;
> các bảng dưới đây giữ nguyên như hồ sơ Phase 0.

## Quy tắc chung đã chốt (không thảo luận lại ở đây)

- Vốn 10.000 USD, 2.500 USD/desk, 4 desk giao dịch (LJ/Kel không giao dịch).
- Rủi ro chung 1%/lệnh; riêng EURUSD 3%, XAUUSD 10%, BTCUSD 8%
  (`risk.per_symbol_pct`, tính theo giá tham chiếu EURUSD 1,16 /
  XAUUSD 5.000 / BTCUSD 120.000). Bảng này cố định, không tự tăng theo giá.
  **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Bảng rủi ro giữ nguyên, KHÔNG hạ
  rủi ro desk vàng lúc này** — việc đó cần số ATR thật từ MT5 demo trước;
  ghi là mục theo dõi ở cuối file.
- TP/SL 5% / 5% cũ **đã bị thay thế (Phu duyệt 2026-11-27)**: SL theo ATR,
  TP = 2 × khoảng cách SL, tỉ lệ 2:1. Xem Q2.
- Khung thời gian làm việc của feed: M15, 60 nến gần nhất.
  **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Giữ M15 cho cả 4 desk** để khớp
  pipeline dữ liệu sẵn có.
- Mọi tín hiệu/lệnh đều ghi log kèm lý do (`decisions-log.csv`); dry-run
  trước, đặt lệnh sau; demo-only.

## Quy ước đọc bảng quy tắc từng desk

Mỗi desk có 2 phần: **(a) Cơ bản** — động lực theo dõi + điều kiện cấm
giao dịch (theo `trading-foundation.md` §2); **(b) Kỹ thuật** — mọi quy
tắc viết dạng "nếu … thì …" với con số cụ thể để LJ/Kel cài thẳng vào code.

---

## Desk 1 — Forex, EURUSD (Yuling Pan)

### (a) Cơ bản

- Động lực theo dõi: chênh lệch lãi suất Fed–ECB, lạm phát, tăng trưởng,
  dòng tiền trú ẩn.
- **[ĐỀ XUẤT — ví dụ cho danh sách sự kiện ở Phase 4, mặc định rỗng]
  Không mở lệnh mới:** 30 phút trước và sau tin CPI Mỹ, quyết định lãi
  suất Fed/ECB, Nonfarm Payrolls. Chỉ quản lý lệnh cũ trong các cửa sổ này.
- **[ĐỀ XUẤT — quyết định thủ công, không cài vào code] Cấm mở lệnh mới
  khi:** khung vĩ mô của Yuling đánh giá "không rõ xu hướng" (Fed và ECB
  phát tín hiệu trái chiều trong cùng tuần).

### (b) Kỹ thuật

- Khung thời gian: M15. Chỉ báo: SMA5, SMA20, RSI(14), ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Vào lệnh BUY — nếu** SMA5 > SMA20
  **và** 50 < RSI(14) < 70, **thì** BUY. (RSI > 70 là quá mua → không BUY;
  RSI < 50 là mất động lượng tăng → không BUY.)
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Vào lệnh SELL — nếu** SMA5 < SMA20
  **và** 30 < RSI(14) < 50, **thì** SELL. (RSI < 30 là quá bán → không SELL.)
- **Không đủ dữ liệu** (< 20 nến) hoặc SMA5 == SMA20 → HOLD.
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Stop loss:** SL = giá vào ± 1,5 × ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Chốt lời:** TP = giá vào ± 3,0 × ATR(14)
  (tỉ lệ lời:lỗ 2:1).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Trailing stop — nếu** giá chạy có lợi
  được 1 × khoảng cách SL, **thì** dời SL về giá hòa vốn; sau đó **nếu** giá
  tiếp tục chạy có lợi, **thì** trailing SL cách giá hiện tại 1,5 × ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Thoát khi đảo chiều — nếu** đang mở
  lệnh BUY mà xuất hiện tín hiệu SELL đầy đủ (SMA5 < SMA20 và 30 < RSI < 50),
  **thì** đóng lệnh BUY ở giá thị trường (và ngược lại cho lệnh SELL).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Không giao dịch — nếu** RSI(14) > 80
  hoặc < 20 (cực đoan), **thì** không mở lệnh mới cho tới khi RSI quay về
  trong 20–80.

---

## Desk 2 — Vàng, XAUUSD (Yumi)

### (a) Cơ bản

- Động lực theo dõi: lãi suất thực USD, USD Index, rủi ro địa chính trị,
  nhu cầu mua của ngân hàng trung ương; Yumi cập nhật kèm desk châu Á
  (Nhật–Hàn–Trung).
- **[ĐỀ XUẤT — ví dụ cho danh sách sự kiện ở Phase 4, mặc định rỗng]
  Không mở lệnh mới:** 30 phút trước và sau CPI Mỹ, FOMC, Nonfarm.
- **[ĐỀ XUẤT — quyết định thủ công, không cài vào code] Nếu** vàng đi
  ngược USD (USD tăng mà vàng cũng tăng), **thì** không mở lệnh mới cho
  tới khi Yumi xác nhận lại luận điểm trong khung chat.
- Vàng có biên độ ngày lớn và chạy mạnh theo phiên Mỹ — đó là lý do
  stop theo ATR (mục b) quan trọng hơn với vàng so với các desk khác.

### (b) Kỹ thuật

- Khung thời gian: M15. Chỉ báo: SMA5, SMA20, RSI(14), ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Vào lệnh:** giống desk Forex (BUY:
  SMA5 > SMA20 và 50 < RSI < 70; SELL: SMA5 < SMA20 và 30 < RSI < 50).
  Ngưỡng RSI riêng cho vàng: **không tách — dùng chung với Forex**;
  tách sau chỉ khi backtest cho thấy cần.
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Stop loss:** SL = giá vào ± 1,5 × ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Chốt lời:** TP = giá vào ± 3,0 × ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Trailing stop và thoát khi đảo chiều:**
  giống desk Forex.
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Không giao dịch:** giống desk Forex
  (RSI cực đoan, cửa sổ tin).
- **Theo dõi — hạ rủi ro desk vàng (chưa chốt, cần số ATR thật):** với SL 5%
  cố định cũ, một lệnh vàng thua lỗ 250 USD = 10% vốn desk. **Nếu** stop theo
  ATR được kiểm chứng bằng số thật (SL thực tế hẹp hơn 5% nhiều — ATR(14)
  M15 của vàng thường chỉ vài chục USD so với SL 5% = 250 USD), **thì** rủi
  ro 10% là không còn cần thiết: desk vàng có thể hạ xuống **2–3% mà vẫn
  đặt được 0,01 lot**, và một lệnh thua chỉ còn khoảng 50–75 USD. Chỉ
  quyết sau khi Phase 1 lấy được số ATR thật từ MT5 demo (xem Q1).

---

## Desk 3 — Crypto, BTCUSD / BNBUSD / ETHUSD (Rich)

### (a) Cơ bản

- Động lực theo từng coin: BTC theo vĩ mô / dòng tiền tổ chức; ETH theo
  hệ sinh thái và nâng cấp mạng; BNB theo sàn Binance và hệ sinh thái BNB.
- **[ĐỀ XUẤT — ví dụ cho danh sách sự kiện ở Phase 4, mặc định rỗng]
  Không mở lệnh mới:** 30 phút trước và sau CPI Mỹ, FOMC.
- **[ĐÃ CHỐT — theo quy tắc sourcing đã chốt 2026-11-26] Tin rò rỉ:**
  tin về sàn hoặc pháp lý chưa xác minh (tin rò rỉ trên x.com phải ghi rõ
  **chưa xác minh**, không được làm căn cứ duy nhất cho lệnh).
- Crypto chạy 24/7, biến động lớn hơn hẳn 3 mảng còn lại — đó là lý do
  hệ số ATR cho stop rộng hơn (mục b).

### (b) Kỹ thuật

- Khung thời gian: M15. Chỉ báo: SMA5, SMA20, RSI(14), ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Vào lệnh:** giống desk Forex (BUY:
  SMA5 > SMA20 và 50 < RSI < 70; SELL: SMA5 < SMA20 và 30 < RSI < 50).
  **3 coin dùng chung một quy tắc**; tách riêng (BTC theo vĩ mô, ETH/BNB
  theo hệ sinh thái) sau chỉ khi backtest cho thấy cần.
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Stop loss:** SL = giá vào ± 2,0 × ATR(14)
  (rộng hơn Forex/vàng vì crypto biến động mạnh).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Chốt lời:** TP = giá vào ± 4,0 × ATR(14)
  (tỉ lệ lời:lỗ 2:1).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Trailing stop và thoát khi đảo chiều:**
  giống desk Forex, với hệ số ATR của crypto (trailing cách giá 2,0 × ATR).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Không giao dịch:** giống desk Forex
  (RSI cực đoan, cửa sổ tin).

---

## Desk 4 — Chứng khoán Mỹ, AMD / CDNS / SNPS / INTC / NVDA (Kathy)

### (a) Cơ bản

- Luận điểm từng công ty: AI / chip / EDA tool, chu kỳ bán dẫn, nhu cầu
  hạ tầng AI, cạnh tranh trong ngành.
- **[ĐỀ XUẤT — ví dụ cho danh sách sự kiện ở Phase 4, mặc định rỗng]
  Không mở lệnh mới trong tuần báo cáo thu nhập (earnings) của chính mã đó**
  — chỉ quản lý lệnh cũ. Lịch earnings do Kathy bổ sung vào config khi có.
- **[ĐỀ XUẤT — quyết định thủ công, không cài vào code] Loại một mã khỏi
  danh mục nếu:** báo cáo tài chính xấu 2 quý liên tiếp, mất thị phần
  rõ rệt, hoặc định giá vượt ngưỡng Kathy đặt ra (ngưỡng này Kathy ghi
  rõ theo từng mã khi chốt).
- **[ĐỀ XUẤT — chưa chốt; Q4 mặc định không lọc phiên] Không mở lệnh mới
  trong 15 phút đầu phiên Mỹ** (biến động mở cửa lớn, giá chưa ổn định).

### (b) Kỹ thuật

- Khung thời gian: M15 trong phiên Mỹ. Chỉ báo: SMA5, SMA20, RSI(14), ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Vào lệnh:** giống desk Forex (BUY:
  SMA5 > SMA20 và 50 < RSI < 70; SELL: SMA5 < SMA20 và 30 < RSI < 50).
  **5 mã dùng chung một quy tắc**; NVDA tách ngưỡng riêng sau chỉ khi
  backtest cho thấy cần.
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Stop loss:** SL = giá vào ± 1,5 × ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Chốt lời:** TP = giá vào ± 3,0 × ATR(14).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Trailing stop và thoát khi đảo chiều:**
  giống desk Forex.
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Không giao dịch:** giống desk Forex,
  cộng 2 điều kiện riêng ở mục (a).

---

## Quyết định chung (Phu duyệt 2026-11-27)

### Q1. Drawdown 10%: tính theo desk hay toàn quỹ — và desk vàng

Tình trạng trước khi chốt (`trading-principles.md` mục 8, 12): giới hạn 10%
đã ghi trong config, hàm `check_drawdown()` đã viết nhưng chưa chỗ nào
gọi; chưa chốt tính theo desk hay toàn quỹ; một lệnh vàng thua (250 USD)
bằng đúng 10% vốn desk.

**[ĐÃ CHỐT — Phu duyệt 2026-11-27] Phương án A: tính 10% theo toàn quỹ
(1.000 USD), cộng cảnh báo từng desk ở 5% (125 USD).** Một lệnh vàng thua
250 USD lúc này chỉ bằng 2,5% quỹ — vấn đề "một lệnh chạm trần" biến mất,
desk vẫn được theo dõi riêng qua mức cảnh báo. Khi chạm giới hạn quỹ thì
tool chặn lệnh mới toàn bộ; khi chạm cảnh báo desk thì chỉ chặn lệnh mới
của desk đó. Lệnh đang mở chỉ được quản lý, không bị đóng ép bởi quy tắc này.

Phương án B (giữ giới hạn theo từng desk 10% + tăng vốn desk vàng lên
5.000 USD) và phương án C (giữ nguyên theo desk, chấp nhận ở giai đoạn
demo): **không chọn.**

Cơ chế chặn được cài ở Phase 4 (nối `check_drawdown()` vào luồng chạy).

### Q2. Stop loss: theo ATR hay giữ 5% cố định (kèm TP)

**[ĐÃ CHỐT — Phu duyệt 2026-11-27] Phương án ATR:** SL = 1,5 × ATR(14)
(crypto 2,0 × ATR), TP = 2 × khoảng cách SL (tỉ lệ 2:1). Stop ôm theo biến
động thật của từng symbol thay cho 5% cố định; đồng thời giải quyết được
vấn đề sizing của desk vàng và BTC. Số ATR thật từ MT5 demo dùng để kiểm
chứng ở Phase 1.

Phương án giữ 5% (SL 5% / TP 5%, tỉ lệ 1:1): **đã bị thay thế.**

### Q3. Chính sách đòn bẩy và kiểm tra ký quỹ

- Đòn bẩy **không** thay đổi cách tính khối lượng (khối lượng tính theo
  % rủi ro; đòn bẩy chỉ giảm tiền ký quỹ cần có).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27]** Tool không giả định mức đòn bẩy nào
  trong tính toán; trước khi gửi lệnh, tool kiểm tra ký quỹ khả dụng trên
  tài khoản demo và từ chối lệnh nếu không đủ (MT5 hiện là bên duy nhất
  từ chối, sau khi lệnh đã gửi). Mức đòn bẩy thực tế lấy theo tài khoản
  demo Exness. Ở chế độ mô phỏng (không có tài khoản MT5) thì bỏ qua bước
  kiểm tra này và ghi rõ vào log.

### Q4. Giới hạn số lệnh và lọc phiên/tin

- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Tối đa 1 lệnh mới / symbol / ngày**
  (kỷ luật demo).
- **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Mặc định không lọc phiên**, chỉ lọc
  tin. Cơ chế lọc tin: danh sách sự kiện trong config (ngày giờ + số phút
  cửa sổ), **mặc định rỗng** — Phu/Kathy bổ sung sự kiện cụ thể sau; các
  cửa sổ 30 phút ở bảng từng desk là ví dụ cho danh sách này.

---

## Checklist Phase 0 → xong khi nào

- [x] Quy tắc kỹ thuật từng desk (4 bảng trên) được chốt, Yuling duyệt
      lý thuyết, Phu duyệt 2026-11-27.
- [x] Q1 (drawdown toàn quỹ 10% + cảnh báo desk 5%), Q2 (ATR thay 5%),
      Q3 (đòn bẩy/ký quỹ), Q4 (1 lệnh/symbol/ngày, không lọc phiên)
      được chốt 2026-11-27.
- [ ] Mọi quy tắc [ĐÃ CHỐT] được chép sang `docs/trading-principles.md`
      (đổi trạng thái [CẦN CHỐT]/[NGHIÊN CỨU] → [ĐÃ CHỐT]; → [ĐÃ CÓ]
      khi code cài xong ở Phase 2/4) và checklist §8 trong file đó được
      cập nhật.
- [ ] Không còn mục [CẦN CHỐT] nào liên quan đến danh mục này trong
      `trading-principles.md` (§6.1 của `trading-foundation.md`).
- [ ] Sau đó mới sang Phase 1 (feed OHLC + kiểm tra symbol trên MT5 demo)
      và Phase 2 (cài chiến lược riêng từng desk).

## Mục theo dõi (chưa chốt, cần dữ liệu thật)

- **Hạ rủi ro desk vàng (2–3% thay cho 10%):** chỉ quyết sau khi có số
  ATR thật từ MT5 demo — Phase 1 lấy số, Phase 3 backtest kiểm chứng.
- **Tách quy tắc riêng theo symbol** (ngưỡng RSI riêng cho vàng, tách
  BTC/ETH/BNB, tách NVDA): **ĐÃ XONG 2026-11-27** — bang
  `strategy.per_symbol` trong `config.example.yaml` (xem
  `docs/per-symbol-ta.md`, quy tac 61); mac dinh chung chi con dung
  cho CDNS/SNPS va nhung truong khong ghi de. Luu y: bang nay la
  diem xuat phat theo tai lieu/thuc hanh, chua kiem chung tren du
  lieu that — kiem chung bang walk-forward OOS van cho o muc tren.
- **Danh sách sự kiện cấm giao dịch:** mặc định rỗng; Phu/Kathy bổ sung
  CPI/FOMC/NFP/lịch earnings cụ thể vào config khi có lịch.
- **Ứng viên từ repo DiamondX10 cũ (merge 2026-11-27 — chưa chốt,
  xem `docs/merge-diamondx10-2026-11-27.md`):**
  - **Breakout Donchian 20** (`strategies/breakout.py`): hiện chỉ là
    chiến lược so sánh trong backtest (`backtest --strategy donchian`).
    Dùng live cần Phu duyệt + bằng chứng walk-forward.
  - **Regime ADX làm bối cảnh:** `signals` đã in kèm regime (TRENDING /
    TRANSITIONAL / RANGING + hướng SMA20/50). Dùng regime để chặn/giảm
    lệnh cần Phu quyết — hiện không chặn gì.
  - **Macro edge DXY/US10Y/VIX/SPX:** chỉ in trong báo cáo ngày khi
    Yuling cung cấp snapshot (`macro:` trong config). Nguồn dữ liệu live
    (yfinance hay nhập tay) chưa chốt.
  - **Kelly 25% + risk parity, TP1/TP2 chốt lời từng phần:** ghi
    [NGHIÊN CỨU]/[CẦN CHỐT] trong `docs/trading-principles.md` mục
    27–28, mâu thuẫn quy tắc đã chốt — cần Phu/Yuling quyết.

## Tài liệu liên quan

- `docs/trading-principles.md` — bản chuẩn (chỉ sửa khi có quy tắc [ĐÃ CHỐT]).
- `docs/trading-foundation.md` — khung thảo luận gốc (§2 cơ bản, §3 kỹ thuật,
  §5 checklist, §6 định nghĩa xong việc).
- `research/` — bài nghiên cứu theo từng mảng (cần bổ sung số cụ thể khi chốt).
- `src/diamondx10/models/quant.py` — SMA, RSI, ATR, volatility, ADX/regime đã có sẵn.
- `src/diamondx10/risk.py` — `check_drawdown()` đã viết, chưa được gọi.
- `docs/market-news.md` — nguồn tin thị trường theo desk, phân tầng độ tin cậy.
- `docs/merge-diamondx10-2026-11-27.md` — hồ sơ merge từ repo DiamondX10 cũ + ThaoResearch.
