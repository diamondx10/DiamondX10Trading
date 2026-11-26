# Nguyên tắc giao dịch DiamondX10

> Bản chuẩn duy nhất về nguyên tắc giao dịch của tool quant DiamondX10.
> Ngày chốt bản này: 2026-11-26. Trạng thái: **demo-only** (Exness demo + MT5),
> không bao giờ giao dịch tiền thật.
>
> Quy ước ghi trạng thái từng nguyên tắc:
> - **[ĐÃ CÓ]** — đã cài trong code và đang chạy.
> - **[NGHIÊN CỨU]** — đã viết trong bài nghiên cứu, code **chưa** làm theo.
> - **[CẦN CHỐT]** — chưa có quy tắc, cần Yuling chốt rồi LJ/Kel cài đặt.
>
> Mọi thay đổi nguyên tắc phải sửa cả file này **và** code tương ứng,
> kèm test. Không sửa code mà không sửa file này, và ngược lại.

---

## 1. Triết lý

1. **[ĐÃ CÓ] Theo xu hướng, không đoán đỉnh/đáy.** Tool chỉ giao dịch
   thuận xu hướng. Không có chiến lược bắt đáy, bắt đỉnh hay giao dịch
   ngược xu hướng trong code.
2. **[ĐÃ CÓ] Kỷ luật hệ thống, không cảm tính.** Tín hiệu do code sinh ra
   từ dữ liệu, không có can thiệp tay vào tín hiệu lúc chạy. Người chỉ
   quyết định **trước** giờ chạy: duyệt chiến lược, duyệt cấu hình rủi ro.
3. **[ĐÃ CÓ] Quản lý rủi ro đặt trước lợi nhuận.** Không có lệnh nào được
   gửi khi chưa tính xong khối lượng theo mức lỗ cho phép và stop loss.

## 2. Tín hiệu vào lệnh

4. **[ĐÃ CÓ] Quy tắc tín hiệu duy nhất hiện nay — giao cắt SMA**
   (`src/diamondx10/strategies/base.py`, `signals.py`):
   - Lấy 60 nến M15 gần nhất từ `MT5Feed` (chế độ demo: `SimulatedFeed`).
   - SMA5 > SMA20 → **BUY**. SMA5 < SMA20 → **SELL**.
     SMA5 == SMA20 hoặc chưa đủ dữ liệu → **HOLD**, không đặt lệnh.
   - Cả 4 desk (Forex — Yuling, XAUUSD — Yumi, Crypto — Rich,
     chứng khoán Mỹ — Kathy) dùng **chung một quy tắc này**, chỉ khác
     symbol và người phụ trách. Đây là điểm khởi đầu, chưa phải chiến
     lược riêng theo từng mảng.
   - Danh mục symbol đã chốt 2026-11-26 (xem `docs/trading-foundation.md`):
     Forex EURUSD; XAUUSD; Crypto BTCUSD, BNBUSD, ETHUSD; chứng khoán Mỹ
     AMD, CDNS, SNPS, INTC, NVDA. **Đa symbol đã làm xong 2026-11-26:**
     `mt5-dry-run` / `mt5-trade` chạy lần lượt mọi symbol của desk
     (`__main__._desk_symbols`), vốn desk chia đều cho từng symbol.
     `--symbol` vẫn dùng được để chạy riêng một mã.
5. **[NGHIÊN CỨU] Lọc RSI.** Bài nghiên cứu Forex của Yuling
   (`research/forex-yuling.md`) viết: chỉ xem xét mua khi RSI không quá
   mua. Code hiện tại **chưa** nối RSI vào tín hiệu — `rsi()` đã có sẵn
   trong `src/diamondx10/models/quant.py` nhưng chưa được gọi.
   Ngưỡng cụ thể (ví dụ: không BUY khi RSI > 70, không SELL khi RSI < 30)
   thuộc mục 8, cần Yuling chốt số.
6. **[CẦN CHỐT] Lọc theo biến động / phiên / tin tức.** ATR và volatility
   đã có sẵn trong `models/quant.py` nhưng chưa dùng. Chưa có quy tắc nào
   về: không giao dịch khi biến động quá thấp/quá cao, không giao dịch
   quanh tin mạnh, hay giới hạn phiên giao dịch.

## 3. Quản lý rủi ro và vốn

7. **[ĐÃ CÓ] Vốn chia desk độc lập** (`config.example.yaml`, `portfolio.py`):
   4 desk giao dịch × 2.500 USD = 10.000 USD (tăng từ 2.000 USD ngày
   2026-11-26 theo quyết định của nhóm). LJ và Kel xây nền tảng,
   **không** giao dịch trong 10.000 USD này.
8. **[ĐÃ CÓ] Rủi ro theo từng symbol, mức chung 1%/lệnh**
   (`risk.max_risk_per_trade_pct: 1.0`, `risk.per_symbol_pct`):
   mức chung là 1% vốn của symbol. Chỉ 3 symbol cần cao hơn mới đặt
   được 0,01 lot ở stop 5% nên mới có trong bảng riêng — tính theo giá
   tham chiếu EURUSD 1,16 / XAUUSD 5.000 / BTCUSD 120.000:
   EURUSD 3% (lỗ tối đa 75 USD), XAUUSD 10% (250 USD), BTCUSD 8%
   (67 USD). Còn lại giữ 1% (ETH/BNB 8 USD, mỗi mã chứng khoán 5 USD).
   Trước đó nhóm đã thử một con số chung 10% cho mọi lệnh (2026-11-26)
   rồi bỏ, vì nó bắt cả những mã không cần phải chịu rủi ro cao.
   **Kỷ luật đi kèm:** bảng này là quyết định cố định trong config, không
   tự tăng theo giá. Nếu giá chạy vượt giá tham chiếu (vàng trên 5.000 USD,
   BTC trên ~150.000 USD) thì symbol đó lại về volume 0 — tool báo volume 0
   chứ không tự tăng rủi ro, lúc đó nhóm quyết lại số.
   **Tồn dư cần nhóm biết:** một lệnh vàng thua là lỗ 250 USD = 10% vốn
   desk = đúng giới hạn drawdown tối đa (quy tắc 12). Desk crypto an toàn
   hơn: cả 3 coin cùng chạm stop mới lỗ 3,3% vốn desk.
   **Vốn desk chia đều cho các symbol của desk khi tính size**
   (`__main__.split_desk_capital`): crypto 3 coin → 833 USD/coin,
   chứng khoán 5 mã → 500 USD/mã.
9. **[ĐÃ CÓ] Stop loss bắt buộc 5%** (`risk.default_stop_loss_pct: 5.0`,
   đổi từ 2% ngày 2026-11-26 theo quyết định của nhóm):
   giá vào ± 5%. Lệnh nào không có stop loss thì không gửi
   (`execution.place_demo_order` từ chối khi `sl` thiếu).
   **Hệ quả:** stop càng rộng thì khối lượng tính ra càng nhỏ (mục 10) —
   với stop 5%, EURUSD (2.500 USD/desk) cũng tính ra dưới 0,01 lot.
   Đòn bẩy **không** sửa được điểm này: đòn bẩy chỉ giảm tiền ký quỹ
   cần có, còn khoản lỗ khi chạm stop vẫn = khối lượng × khoảng cách stop,
   và khối lượng vẫn tính theo quy tắc rủi ro theo từng symbol — tool hiện cũng chưa
   kiểm tra ký quỹ/đòn bẩy của tài khoản, MT5 sẽ từ chối lệnh nếu ký quỹ
   không đủ. Muốn lệnh to hơn thì phải tăng % rủi ro mỗi lệnh hoặc đổi
   cách tính size, không phải tăng đòn bẩy.
10. **[ĐÃ CÓ] Khối lượng tính ngược từ mức lỗ cho phép**
    (`risk.position_size`, `execution.position_size_lots`):
    `khối lượng = (vốn desk × 1%) / |giá vào − stop loss|`, rồi đổi sang
    lot MT5 theo contract size (Forex 100.000, XAUUSD 100, Crypto 1,
    chứng khoán Mỹ 1), làm tròn **xuống** bước 0,01 lot.
    Tính ra dưới 0,01 lot → volume = 0, **không đặt lệnh**. Đây là giới
    hạn thật của vốn nhỏ, không phải lỗi code (xem `docs/mt5-demo.md` §5).
    Với rủi ro theo từng symbol hiện tại, mọi symbol trong danh mục đều
    tính ra từ 0,01 lot trở lên ở stop 5% (đã kiểm chứng bằng test
    `test_per_symbol_risk_all_symbols_min_lot`).
11. **[NGHIÊN CỨU] Cắt lỗ theo ATR.** Bài nghiên cứu Forex viết "cắt lỗ
    theo ATR", nhưng code hiện dùng stop loss cố định 5%. `atr()` đã có
    sẵn trong `models/quant.py`, chưa được nối vào tính stop loss.
12. **[CẦN CHỐT] Giới hạn drawdown tối đa 10%** (`risk.max_drawdown_pct: 10.0`):
    con số đã ghi trong config và hàm `risk.check_drawdown()` đã viết,
    nhưng **chưa có chỗ nào trong luồng chạy gọi hàm này** — thực tế nó
    chưa chặn được lệnh nào. Cần chốt: drawdown tính theo desk hay toàn
    quỹ, và khi chạm giới hạn thì dừng desk đó hay dừng toàn bộ tool.

## 4. Thoát lệnh và chốt lời

13. **[ĐÃ CÓ] Chốt lời 5%** (`risk.default_take_profit_pct: 5.0`,
    chốt ngày 2026-11-26 theo quyết định của nhóm): lệnh BUY chốt lời ở
    giá vào + 5%, lệnh SELL chốt lời ở giá vào − 5%
    (`__main__.stop_and_target`, `execution.place_demo_order` gửi `tp`
    lên MT5). Tỉ lệ lời:lỗ hiện là 1:1 (TP 5% / SL 5%).
    Chưa có trailing stop — đó vẫn là mục [CẦN CHỐT] ở quy tắc 14.
14. **[CẦN CHỐT] Chưa có quy tắc thoát lệnh ngoài stop loss / take profit.** Chưa có
    trailing stop, chưa có thoát khi tín hiệu đảo chiều, chưa có quản lý
    vị thế đang mở (`portfolio.positions` tồn tại nhưng chưa được cập nhật
    trong luồng chạy). Hiện tại stop loss và take profit là hai cơ chế
    thoát duy nhất trong code.

## 5. Kỷ luật vận hành và ghi chép

15. **[ĐÃ CÓ] Mọi quyết định đều có log và được thông báo**
    (`decisions.py`, `decisions/decisions-log.csv`): ngày, desk, symbol,
    action, lý do, người phụ trách. Cả dry-run cũng ghi log.
    Không có lệnh "không lý do".
16. **[ĐÃ CÓ] Phân công rõ ràng** (`docs/workflow.md`, `docs/architecture.md`,
    `docs/trading-foundation.md` §2–§3):
    Yuling nghiên cứu lý thuyết giao dịch và làm **khung phân tích cơ bản
    chung + vĩ mô + cơ bản Forex**; **mỗi desk tự làm cơ bản mảng mình**
    (Kathy — chứng khoán, Yumi — vàng/châu Á, Rich — crypto), Yuling duyệt
    cuối về lý thuyết. Phân tích kỹ thuật: Yuling — Forex, Kathy — chứng
    khoán, Yumi — vàng, Rich — crypto. LJ (data scientist) cài model /
    chiến lược; Kel (data analysis) lo dữ liệu, pipeline, hạ tầng;
    ai phụ trách mảng nào viết bài nghiên cứu/nhận định mảng đó.
17. **[ĐÃ CÓ] Dữ liệu thời gian thực; mô phỏng chỉ để demo/test.**
    Nghiên cứu và giao dịch dùng dữ liệu thật qua `DataFeed`; dữ liệu mô
    phỏng không dùng để ra quyết định thật.
18. **[ĐÃ CÓ] Dry-run trước, đặt lệnh sau.** Lệnh `mt5-dry-run` chỉ in tín
    hiệu, không gửi lệnh. Chỉ khi dry-run đúng mới chạy `mt5-trade`.
    Tín hiệu HOLD thì không đặt lệnh.

## 6. An toàn — chỉ demo

19. **[ĐÃ CÓ] Chặn DEMO-ONLY** (`execution.check_demo_only`, có test trong
    `tests/test_mt5.py`): từ chối ngay khi config ghi `demo_only: false`,
    `provider: live/real`, hoặc tài khoản MT5 đang đăng nhập không phải
    demo (trade_mode REAL, server chứa "Real", hoặc không đọc được thông
    tin tài khoản).
20. **[ĐÃ CÓ] Mật khẩu không bao giờ vào repo.** Mật khẩu demo chỉ qua biến
    môi trường `MT5_PASSWORD` lúc chạy (hoặc `config.yaml` local đã
    gitignore). `quickstart.py` hỏi mật khẩu lúc chạy và chỉ giữ trong
    bộ nhớ của tiến trình đó.

## 7. Những điểm đang lệch giữa nghiên cứu và code

| Điểm | Nghiên cứu viết | Code hiện tại |
|---|---|---|
| Lọc RSI khi vào lệnh | Chỉ mua khi RSI không quá mua (`research/forex-yuling.md`) | Chưa nối RSI vào tín hiệu |
| Cắt lỗ theo ATR | "Cắt lỗ theo ATR" (`research/forex-yuling.md`) | Stop loss cố định 5% |
| Giới hạn drawdown 10% | Ghi trong config | Hàm đã có, chưa được gọi trong luồng chạy |

## 8. Checklist cần chốt (Yuling quyết, LJ/Kel cài đặt)

- [ ] Ngưỡng RSI cho BUY/SELL (mục 5).
- [ ] Stop loss theo ATR thay cho 5% cố định, hay giữ 5%? (mục 11).
- [x] Quy tắc chốt lời cố định 5% — chốt xong 2026-11-26 (mục 13).
- [ ] Trailing stop (mục 14).
- [ ] Quy tắc thoát khi tín hiệu đảo chiều; quản lý vị thế mở (mục 14).
- [ ] Drawdown 10%: tính theo desk hay toàn quỹ, dừng ở mức nào (mục 12).
- [ ] Giới hạn số lệnh mỗi ngày / mỗi desk; có lọc phiên, lọc tin không (mục 6).
- [ ] Chiến lược riêng theo từng desk, hay giữ một quy tắc chung (mục 4).
- [ ] Backtest tính lãi/lỗ thật thay cho bản nháp hiện tại
      (`backtest.py` mới chỉ in tín hiệu cuối, chưa có P&L).

## Tài liệu liên quan

- `docs/architecture.md` — kiến trúc, luồng dữ liệu.
- `docs/workflow.md` — quy trình làm việc Yuling → LJ/Kel.
- `docs/mt5-demo.md` — hướng dẫn Exness demo + MT5, giới hạn vốn nhỏ.
- `quickstart.py` — chạy nhanh: cài gói, hỏi login lúc chạy, dry-run 4 desk.
- `config.example.yaml` — mọi con số rủi ro/vốn (mức chung 1%/lệnh, riêng EURUSD 3% / XAUUSD 10% / BTCUSD 8%, TP/SL 5%, drawdown 10%, 2.500 USD/desk).
- `research/` — bài nghiên cứu/nhận định theo từng mảng.
