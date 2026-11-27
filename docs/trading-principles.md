# Nguyên tắc giao dịch DiamondX10

> Bản chuẩn duy nhất về nguyên tắc giao dịch của tool quant DiamondX10.
> Ngày chốt bản này: 2026-11-26. Trạng thái: **demo-only** (Exness demo + MT5),
> không bao giờ giao dịch tiền thật.
>
> Quy ước ghi trạng thái từng nguyên tắc:
> - **[ĐÃ CÓ]** — đã cài trong code và đang chạy.
> - **[ĐÃ CHỐT]** — đã chốt (người phụ trách desk + Yuling + Phu) nhưng code
>   **chưa** cài theo; khi code xong thì đổi thành [ĐÃ CÓ].
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

4. **[ĐÃ CÓ] Quy tắc tín hiệu duy nhất hiện nay — giao cắt SMA + lọc RSI,
   stop/take-profit theo ATR** (`src/diamondx10/strategies/base.py`,
   `signals.py`):
   - Lấy 60 nến M15 gần nhất từ `MT5Feed` (chế độ demo: `SimulatedFeed`).
   - SMA5 > SMA20 và 50 < RSI(14) < 70 → **BUY**. SMA5 < SMA20 và
     30 < RSI(14) < 50 → **SELL**. RSI > 80 hoặc < 20 (cực đoan),
     SMA5 == SMA20 hoặc chưa đủ dữ liệu → **HOLD**, không đặt lệnh.
     BUY/SELL kèm levels `{entry, sl, tp, atr}`: SL = entry ± 1,5 × ATR(14)
     (crypto 2,0 ×), TP = entry ± 2 × khoảng cách SL (xem mục 5, 9, 11, 13).
   - Cả 4 desk (Forex — Yuling, XAUUSD — Yumi, Crypto — Rich,
     chứng khoán Mỹ — Kathy) dùng **chung một quy tắc này**, chỉ khác
     symbol và người phụ trách. **[ĐÃ CHỐT — Phu duyệt 2026-11-27]**
     Quy tắc chung này được nâng lên bản có lọc RSI + stop theo ATR
     (mục 5, 9, 11, 13) và giữ dùng chung cho cả 4 desk ở Phase 0;
     tách riêng theo symbol sau chỉ khi backtest cho thấy cần
     (xem `docs/phase0-desk-rules.md`).
   - Danh mục symbol đã chốt 2026-11-26 (xem `docs/trading-foundation.md`):
     Forex EURUSD; XAUUSD; Crypto BTCUSD, BNBUSD, ETHUSD; chứng khoán Mỹ
     AMD, CDNS, SNPS, INTC, NVDA. **Đa symbol đã làm xong 2026-11-26:**
     `mt5-dry-run` / `mt5-trade` chạy lần lượt mọi symbol của desk
     (`__main__._desk_symbols`), vốn desk chia đều cho từng symbol.
     `--symbol` vẫn dùng được để chạy riêng một mã.
   - **Phase B (2026-11-27):** cơ chế tham số riêng theo symbol đã có
     (`strategy.per_symbol`, `strategies/registry.py`
     `resolve_strategy_params`, xem `docs/strategy-engine.md` §2):
     mặc định vẫn dùng chung một quy tắc; override chỉ tinh chỉnh con
     số (vd hệ số ATR, ngưỡng RSI), không thay quy tắc, và giá trị lạ
     thì báo lỗi thay vì lặng lẽ áp dụng. Backtest/signal đã nối
     per-symbol; luồng live `mt5-*` nối ở bước tích hợp sau.
5. **[ĐÃ CÓ] Lọc RSI.** Bài nghiên cứu Forex của Yuling
   (`research/forex-yuling.md`) viết: chỉ xem xét mua khi RSI không quá
   mua. Ngưỡng đã chốt, áp chung cho cả 4 desk: BUY chỉ khi
   50 < RSI(14) < 70; SELL chỉ khi 30 < RSI(14) < 50. RSI > 80 hoặc < 20
   (cực đoan) thì không mở lệnh mới. **Phase 2:** `rsi()` đã nối vào tín
   hiệu trong `src/diamondx10/strategies/base.py` (SMA + RSI), có test
   trong `tests/test_strategies.py`.
6. **[ĐÃ CÓ — một phần, Phase 4] Lọc theo biến động / phiên / tin tức.**
   Đã chốt: **tối đa 1 lệnh mới / symbol / ngày**; **mặc định không lọc
   phiên**, chỉ lọc tin. **Phase 4:** giới hạn 1 lệnh mới/symbol/ngày đã
   cài (`decisions.count_trades_today`, chặn thì log
   `BLOCKED-DAILY-LIMIT`) và cơ chế lọc tin đã cài
   (`risk.in_no_trade_window` với danh sách `no_trade_events` trong
   config, mặc định rỗng — Phu/Kathy bổ sung CPI/FOMC/NFP/lịch earnings
   sau; chặn thì log `BLOCKED-NO-TRADE-WINDOW`), cả hai đều chạy trong
   luồng `mt5-trade` trước khi xem tín hiệu. ATR và volatility đã có sẵn
   trong `models/quant.py`; quy tắc "không giao dịch khi biến động quá
   thấp/quá cao" vẫn là mục theo dõi, chưa có ngưỡng cụ thể.

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
   **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Bảng rủi ro giữ nguyên, KHÔNG hạ
   rủi ro desk vàng lúc này.** Việc hạ xuống 2–3% cần số ATR thật từ MT5
   demo trước (xem `docs/phase0-desk-rules.md`, mục theo dõi).
9. **[ĐÃ CÓ] Stop loss bắt buộc, tính theo ATR**
   (thay cho mức 5% cố định, xem mục 11): SL = giá vào ± 1,5 × ATR(14),
   riêng crypto 2,0 × ATR(14). Lệnh nào không có stop loss thì không gửi
   (`execution.place_demo_order` từ chối khi `sl` thiếu). Mức 5% cũ
   (`risk.default_stop_loss_pct: 5.0`, chốt ngày 2026-11-26) **đã bị thay
   thế ngày 2026-11-27**; **Phase 2:** code đã chuyển sang ATR
   (`strategies/base.py` `levels_for_entry`, `mt5-trade` dùng SL/TP này),
   có test trong `tests/test_strategies.py`.
   **Hệ quả:** stop càng rộng thì khối lượng tính ra càng nhỏ (mục 10).
   Đòn bẩy **không** sửa được điểm này: đòn bẩy chỉ giảm tiền ký quỹ
   cần có, còn khoản lỗ khi chạm stop vẫn = khối lượng × khoảng cách stop,
   và khối lượng vẫn tính theo quy tắc rủi ro theo từng symbol.
   **[ĐÃ CÓ — Phase 4]** Tool không giả định mức đòn bẩy nào khi tính
   size; trước khi gửi lệnh, tool kiểm tra ký quỹ khả dụng và từ chối
   nếu không đủ (`execution.check_margin` dùng `mt5.order_check`, gọi
   trong `place_demo_order` sau chặn demo-only và trước `order_send`;
   không đủ thì log `BLOCKED-MARGIN`; ở chế độ mô phỏng thì bỏ qua và
   ghi rõ vào log). Trước đây tool chưa kiểm tra ký quỹ — MT5 là bên
   duy nhất từ chối lệnh khi ký quỹ không đủ.
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
11. **[ĐÃ CÓ] Cắt lỗ theo ATR.** Bài nghiên cứu
    Forex viết "cắt lỗ theo ATR" — nay đã chốt thành quy tắc: SL =
    1,5 × ATR(14), crypto 2,0 × ATR(14) (xem mục 9). **Phase 2:** `atr()`
    đã nối vào tính stop loss trong `strategies/base.py`, có test trong
    `tests/test_strategies.py`.
12. **[ĐÃ CÓ — Phase 4] Giới hạn drawdown tối đa 10% theo toàn quỹ**
    (`risk.max_drawdown_pct: 10.0` = 1.000 USD trên vốn 10.000 USD),
    cộng **cảnh báo từng desk ở 5%** (125 USD). Chạm giới hạn quỹ → tool
    chặn lệnh mới toàn bộ; chạm cảnh báo desk → chỉ chặn lệnh mới của desk
    đó; lệnh đang mở chỉ được quản lý, không bị đóng ép. **Phase 4:**
    `risk.DrawdownGuard` nối vào luồng `mt5-trade`/`mt5-dry-run` (dựa trên
    `risk.check_drawdown()`), chặn thì log `BLOCKED-DRAWDOWN-FUND` /
    `BLOCKED-DRAWDOWN-DESK`; đường cong vốn của quỹ và từng desk lưu ở
    `decisions/equity-state.json` (file runtime, không commit).

## 4. Thoát lệnh và chốt lời

13. **[ĐÃ CÓ] Chốt lời = 2 × khoảng cách stop loss**
    (tỉ lệ lời:lỗ 2:1): TP = giá vào ± 2 × (khoảng cách SL theo ATR).
    Mức TP 5% cố định (`risk.default_take_profit_pct: 5.0`, chốt ngày
    2026-11-26) **đã bị thay thế ngày 2026-11-27** cùng với SL 5%.
    `execution.place_demo_order` vẫn gửi `tp` lên MT5 như trước.
    **Phase 2:** TP theo ATR đã cài trong `strategies/base.py`
    (`levels_for_entry`, `tp_mult` 2.0), có test trong
    `tests/test_strategies.py`.
    Trailing stop xem quy tắc 14.
14. **[ĐÃ CÓ] Quy tắc thoát lệnh ngoài stop loss / take profit.**
    **Trailing stop:** khi giá chạy có lợi được 1 × khoảng cách SL thì
    dời SL về giá hòa vốn, sau đó trailing SL cách giá hiện tại 1,5 × ATR
    (crypto 2,0 × ATR). **Thoát khi đảo chiều:** tín hiệu ngược đầy đủ
    (SMA cắt ngược + RSI xác nhận) thì đóng lệnh đang mở ở giá thị trường.
    **Phase 2:** trailing stop và thoát khi đảo chiều đã cài dạng hàm
    thuần trong `strategies/base.py` (`trailing_stop`,
    `reversal_exit`), có test trong `tests/test_strategies.py`.
    **Quản lý vị thế đang mở:** theo dõi từ decisions log (Phase 4/5);
    `portfolio.positions` tồn tại nhưng chưa được cập nhật trong luồng chạy.

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

## 7. Bối cảnh, kiểm định và tin tức — merge từ repo DiamondX10 cũ + ThaoResearch (2026-11-27)

> Các quy tắc dưới đây lấy từ 2 repo cũ của nhóm (xem
> `docs/merge-diamondx10-2026-11-27.md` để biết từng mục lấy từ đâu,
> cái gì không lấy và vì sao). Nguyên tắc chung: **chỉ reflect những gì
> khớp với quy tắc nhóm đã chốt**; chỗ nào mâu thuẫn thì ghi [NGHIÊN CỨU]
> hoặc [CẦN CHỐT] để Phu quyết, không tự đổi quy tắc.

21. **[ĐÃ CÓ] Nhận diện regime (ADX) chỉ là bối cảnh, không chặn tín hiệu**
    (`models/quant.py` `detect_regime`, `signals.py` thêm khóa `"regime"`):
    ADX ≥ 25 TRENDING, 15–25 TRANSITIONAL, < 15 RANGING (ngưỡng của repo
    DiamondX10 cũ, `regime_detector.py`); hướng theo SMA20 so với SMA50;
    biến động theo phân vị ATR (cao ≥ 80, thấp ≤ 20, lookback 100).
    Regime chỉ in kèm tín hiệu để Yuling/Kathy đọc thêm — **không chặn
    hay đổi tín hiệu**. Dùng regime để chặn/giảm lệnh cần Phu duyệt riêng.
22. **[ĐÃ CÓ] Macro edge chỉ là bối cảnh, không đổi tín hiệu**
    (`models/macro.py` `macro_edge`, `report.py` in khi config có mục
    `macro`): tương quan kỳ vọng DXY/US10Y/VIX/SPX với XAUUSD
    (−0,70/−0,60/+0,40/−0,10) và EURUSD (−0,90/−0,30/−0,30/+0,20),
    trọng số 0,35/0,25/0,25/0,15, điểm số −1..1. Snapshot vĩ mô do
    Yuling cung cấp trong config (chưa có thì báo cáo không in mục này).
    **Khác biệt so với bản gốc:** bản gốc nhân thêm −1 cho VIX, làm đảo
    dấu edge vàng so với chính bảng tương quan của nó — ở đây bỏ phép
    nhân đó. Nguồn dữ liệu vĩ mô live (yfinance hay nhập tay) chưa chốt
    — Phu quyết (xem `docs/merge-diamondx10-2026-11-27.md`).
23. **[ĐÃ CÓ — chỉ dùng trong backtest] Chiến lược breakout Donchian 20
    là ứng viên so sánh** (`strategies/breakout.py`, chạy qua
    `backtest --strategy donchian` hoặc
    `run_backtest(..., strategy_name="donchian")`): đóng cửa phá trên
    đỉnh / dưới đáy Donchian 20 nến trước → BUY/SELL; trong kênh thì
    HOLD; ATR/giá < 0,3% thì HOLD (biến động quá thấp, không mở breakout).
    SL/TP theo ATR, trailing stop, thoát khi đảo chiều: dùng lại hàm của
    lớp cơ sở như chiến lược chung (mục 9, 13, 14). Không có xác nhận
    khối lượng (bar của tool không có volume) và không xác nhận retest.
    **Chưa dùng cho đường live** — cần Phu duyệt + bằng chứng
    walk-forward (mục 24). Nguồn: repo DiamondX10 cũ (`breakout.py`).
    **Phase B (2026-11-27):** Donchian đã vào registry chiến lược
    (`strategies/registry.py`, `backtest_only: True`) và chạy được qua
    walk-forward + so sánh chiến lược (`backtest.py`
    `compare_strategies`, chỉ tính OOS).
24. **[ĐÃ CÓ] Kiểm định walk-forward cho chiến lược**
    (`backtest.py` `run_walk_forward`, `backtest --walk-forward`): nhiều
    cửa sổ train/test trượt liên tiếp (mặc định CLI train 30 / test 10 /
    bước 10 bar cho demo; kiểm định thật dùng
    `--days 120 --train-bars 60 --test-bars 20`); mỗi cửa sổ chạy lại từ
    đầu, chỉ đoạn test (out-of-sample) gộp vào kết quả tổng hợp, đường
    equity OOS nối bằng cách cộng dồn biến động từng cửa sổ. Ý tưởng từ
    repo DiamondX10 cũ (`walk_forward.py`) nhưng **chạy trên engine
    backtest của tool này** — không copy code gốc (lot cố định 0,01, SL
    tính từ biên độ bar thay vì ATR, P&L nhân ×100000 sai với vàng).
    **Phase B (2026-11-27):** walk-forward chạy được với mọi chiến lược
    trong registry + tham số per-symbol; thêm so sánh chiến lược
    (`compare_strategies`, bảng chỉ dùng OOS) và sweep tham số
    (`sweep_params`, chỉ xếp hạng theo OOS, báo cả train/test để lộ
    overfitting — công cụ nghiên cứu, không tự áp tham số thắng vào
    config). Xem `docs/strategy-engine.md` §3–§5.
25. **[ĐÃ CÓ] VaR95/CVaR95 trong báo cáo backtest**
    (`risk.py` `value_at_risk`/`expected_shortfall`, `backtest.py`
    `compute_metrics` thêm `var_95_pct`/`cvar_95_pct`; None khi lịch sử
    < 20 returns): VaR lịch sử theo quantile nội suy tuyến tính, CVaR là
    trung bình các khoản lỗ vượt VaR. Chỉ là **chỉ số báo cáo** — giới
    hạn chặn lệnh vẫn là drawdown 10% (mục 12). **Khác biệt so với bản
    gốc:** khi lịch sử không có khoản lỗ nào thì VaR = 0 (bản gốc dùng
    `abs()` nên trả số dương gây hiểu lầm). Stress test của bản gốc quá
    yếu (`base_vol × shock × 10`) nên không lấy. Nguồn: repo DiamondX10
    cũ (`portfolio_risk.py`).
26. **[ĐÃ CÓ] Lấy tin thị trường theo desk, phân tầng độ tin cậy**
    (`data/news.py`, lệnh `news [--desk] [--days]`, xem
    `docs/market-news.md`): feed RSS công khai (không cần credential),
    retry 3 + backoff 2^n, tối đa 50 bài/nguồn; lọc keyword word-boundary
    + blacklist + từ khóa khẩn + độ tuổi tin (mặc định 2 ngày); dedup
    MD5 + SQLite `data/news-history.db` (file runtime, đã gitignore).
    **Phân tầng độ tin cậy (mới — repo gốc không có):** tier 1 CHÍNH
    THỐNG (Fed/ECB/SEC... — đọc tay, không có feed), tier 2 BÁO CHÍ
    (feed RSS Bloomberg/FT/WSJ... và Google News), tier 3 RÒ RỈ
    (x.com — Rich tìm tay, **luôn đánh dấu CHƯA XÁC MINH, không làm căn
    cứ duy nhất cho quyết định giao dịch**). Tin chỉ là bối cảnh, không
    đổi tín hiệu hay tự đặt lệnh. **Không trích "giá" từ tiêu đề báo**
    (repo gốc làm vậy) — giá chỉ lấy từ MT5. Nguồn pattern: ThaoResearch
    (`core/crawler.py`, `core/filter_engine.py`, `utils/database.py`,
    `models/article.py`).
27. **[NGHIÊN CỨU] Kelly 25% + risk parity** (từ repo DiamondX10 cũ,
    `rules/_reviewed/risk`): Kelly fraction 25%, vị thế tối đa 5%, đòn
    bẩy 3×, phân bổ risk parity theo desk. Chưa áp dụng — mâu thuẫn với
    bảng rủi ro cố định theo symbol (mục 8). Cần Phu quyết.
28. **[CẦN CHỐT] Chốt lời từng phần TP1/TP2** (từ repo DiamondX10 cũ:
    TP1 2,0×ATR, TP2 3,0×ATR) so với TP duy nhất 2×SL hiện tại (mục 13).
    Cần Yuling/Phu quyết.
29. **[ĐÃ CÓ] Kho nến OHLC local + backfill/export từ MT5**
    (`data/history.py` `HistoryStore`, lệnh `backfill` /
    `export-bars`, xem `docs/history-store.md`): nến thật từ MT5 demo
    lưu vào SQLite `data/history.db` (file runtime, đã gitignore),
    bảng `bars` khóa chính (symbol, timeframe, time) nên backfill lặp
    không nhân đôi bar; khung hỗ trợ M1/M5/M15/H1/D1 (mặc định M15,
    90 ngày theo mục `history:` trong config). `export-bars` xuất 1
    file CSV/symbol `{SYMBOL}_{TIMEFRAME}.csv`, cột
    `time,open,high,low,close,volume`, `time` ISO UTC; mặc định lấy từ
    kho (`--from store`, thiếu thì kéo 1 lần từ MT5 live), `--from mt5`
    luôn kéo live, `--from simulated` chỉ khi user truyền rõ và output
    luôn ghi rõ nguồn simulated (không phải giá thật). Backfill/export
    chỉ đọc dữ liệu, không đặt lệnh; trên máy không có MT5 thì báo lỗi
    sạch, không traceback. Mục đích: backtest/đo ATR thật trên dữ liệu
    thật thay cho `SimulatedFeed` (mục 17).
30. **[ĐÃ CÓ — Phase B, 2026-11-27] Registry chiến lược + tham số riêng
    theo symbol + so sánh chiến lược + sweep chống overfitting**
    (`strategies/registry.py`, `backtest.py` `compare_strategies` /
    `sweep_params`, xem `docs/strategy-engine.md`): mọi chiến lược đăng
    ký theo tên (`default` dùng live, `donchian` chỉ backtest);
    `strategy.per_symbol` chỉ tinh chỉnh con số (mặc định < chung <
    desk < symbol), giá trị lạ báo lỗi, giá trị mặc định đã chốt không
    đổi; so sánh chiến lược chỉ tính OOS; sweep chỉ xếp hạng theo OOS,
    báo cả train/test, không tự áp tham số thắng vào config.
31. **[ĐÃ CÓ — Phase D, 2026-11-27] Vòng lặp live M15 + cảnh báo Telegram**
    (`live.py` `process_symbol` / `run_live_cycle` / `run_live_loop`,
    `telegram.py`, lệnh `live`, xem `docs/live-loop.md`): mỗi chu kỳ 15
    phút chạy lần lượt mọi symbol của 1 desk, qua đúng trình tự gate như
    `mt5-trade` (đối chiếu vị thế mở → chặn drawdown → chặn no-trade
    window → chặn 1 lệnh/symbol/ngày → tín hiệu → SL/TP ATR + sizing →
    `place_demo_order` với chặn demo-only + margin check); `mt5-trade`
    và vòng lặp dùng **chung** `process_symbol()` nên kết quả giống nhau.
    `live --once` chạy 1 chu kỳ rồi thoát (Task Scheduler/cron mỗi 15
    phút); không `--once` thì lặp tới biên nến M15 tiếp theo tới khi
    Ctrl+C. Lỗi 1 symbol không crash chu kỳ; lỗi lấy feed thì ghi log +
    bỏ symbol/chu kỳ đó; trên máy không có MT5 thì báo lỗi sạch, không
    traceback. **Cảnh báo Telegram — khuyến nghị mua/bán:** khi tín hiệu
    BUY/SELL đạt chuẩn và lệnh DEMO đã đặt, tool gửi 1 tin khuyến nghị
    tới chat Telegram đã cấu hình (`telegram.py` `format_signal_alert`):
    desk + người phụ trách, entry, SL, TP, khối lượng, rủi ro tối đa
    (USD), tỉ lệ R:R, số ticket, thời gian UTC, lý do (SMA/RSI/ATR) —
    luôn đánh dấu DEMO. Lệnh bị chặn (BLOCKED-*) cũng gửi 1 tin kèm lý
    do đầy đủ (kèm entry/SL/TP nếu tín hiệu đã có). HOLD thì không gửi;
    lỗi kỹ thuật chỉ ghi log. Khuyến nghị gửi từ cả vòng `live` lẫn lệnh
    1 lần `mt5-trade` (dùng chung `process_symbol`); `mt5-dry-run`
    không gửi. Mọi khuyến nghị đều ghi vào `decisions/decisions-log.csv`
    **trước** khi gửi Telegram. Kiểm tra kết nối bằng lệnh
    `telegram-test` (báo rõ thiếu enabled/token/chat_id rồi gửi 1 tin
    thử). **Tin tức không gửi tự động** — tin chạy tay trước phiên (mục
    26). Telegram mặc định **tắt** (`telegram.enabled: false`); token chỉ
    qua biến môi trường (`telegram.bot_token_env`, mặc định
    `DIAMONDX10_TELEGRAM_TOKEN`), chat nhận tin ở `telegram.chat_id`
    trong `config.yaml` local; `quickstart.py --live` hỏi token +
    chat_id và tự ghi `enabled: true` + `chat_id` vào config local.
    Gửi lỗi thì chỉ cảnh báo, không bao giờ crash vòng lặp. Vòng lặp
    không đổi quy tắc: không tự đổi tham số, không dùng Donchian/regime/
    macro để chặn tín hiệu (mục 21–23).
32. **[ĐÃ CÓ — Phase C, 2026-11-27] Backtest / walk-forward trên dữ liệu
    thật từ kho lịch sử** (`backtest.py` `run_backtest_from_history` /
    `run_walk_forward_from_history`, `data/csv_import.py`
    `import_csv_bars`, xem `docs/real-data-backtest.md`): đọc bar từ
    `HistoryStore` (mặc định theo `history.db_path` trong config) rồi
    chạy lại đúng engine `run_backtest` / `run_walk_forward` với
    `bars_by_symbol` — mỗi symbol 1 chuỗi bar riêng (khác dữ liệu mô
    phỏng theo desk), đường equity cấp desk nối theo trục thời gian,
    walk-forward lấy số cửa sổ theo symbol ngắn nhất; kho trống /
    symbol thiếu bar thì `ValueError` nêu rõ số bar hiện có và số tối
    thiểu cần (backtest: 40 bar; walk-forward: `train_bars +
    test_bars` bar/symbol). `import_csv_bars` đọc đúng định dạng CSV
    của `export-bars` (cột `time,open,high,low,close,volume`, time ISO
    UTC), bar trùng thì bỏ qua không nhân đôi, file sai cột / time /
    OHLC thì `ValueError` nêu số dòng, không ghi nửa chừng.
    `compare_strategies` / `sweep_params` cũng nhận `bars_by_symbol`
    để so sánh / quét trên dữ liệu thật. CLI `--source history` đã nối
    ở bước tích hợp sau Phase C (xem `__main__.py`).
    Giới hạn: dữ liệu thật vẫn cần đủ dài, chứng khoán chỉ có bar
    trong phiên Mỹ, chỉ OOS mới có ý nghĩa.
33. **[ĐÃ CÓ — Phase F, 2026-11-27] Giới hạn rủi ro toàn quỹ**
    (`risk.py` `check_fund_limits`, `fund_limits_from_config`, xem
    `docs/fund-risk-ops.md` §1): code đã cài và nối vào luồng live
    (`live.process_symbol` gate 2c, trước khi mở lệnh mới; bị chặn thì
    log decision + audit `FUND_LIMIT_BLOCKED`, không crash). **Các con
    số giới hạn [CẦN CHỐT] — chưa được Phu duyệt, chỉ là giá trị mặc
    định thận trọng đề xuất:** (a) lỗ trong ngày toàn quỹ ≥ **3% vốn
    quỹ** (300 USD trên vốn 10.000 USD) thì chặn mở lệnh mới toàn quỹ
    đến hết ngày; lỗ tính bằng tổng P&L đã thực hiện của các lệnh đóng
    trong ngày, đọc từ dòng `CLOSE` trong decisions log; chạm mức là
    chặn; (b) tối đa **10 vị thế mở** toàn quỹ (1/symbol); (c) tối đa
    **2 vị thế mở** mỗi desk (chỉ chặn desk đó). Cấu hình ở mục `risk:`
    trong config (`fund_daily_loss_pct`, `max_open_positions_fund`,
    `max_open_positions_desk`). Giới hạn này **không thay thế**
    drawdown 10% (mục 12): drawdown tính từ đỉnh vốn, lỗ ngày tính từ
    0h00 hôm nay.
34. **[ĐÃ CÓ — Phase F, 2026-11-27] Kill switch — nút dừng khẩn cấp**
    (`killswitch.py`, lệnh `kill-switch on|off|status`, xem
    `docs/fund-risk-ops.md` §2): trạng thái lưu file JSON
    `decisions/kill-switch.json` (file runtime, đã gitignore; chưa có
    file = chưa bật). Khi bật, **không mở lệnh mới nào** — cả vòng
    `live` lẫn `mt5-trade` (dùng chung `process_symbol`, trả
    `BLOCKED-KILL-SWITCH`); **vị thế đang mở vẫn được đối chiếu và
    đóng theo SL/TP đã có** (lựa chọn có chủ ý: dừng mở mới, không bỏ
    mặc vị thế đang mở). Bật/tắt ghi audit `KILL_SWITCH_ON/OFF`
    (kèm lý do + người bật/tắt). Bất cứ ai chạy được lệnh trên máy
    live đều bật được; thực tế chỉ Phu (hoặc người Phu chỉ định) bật/
    tắt và luôn ghi `--reason` + `--by`.
35. **[ĐÃ CÓ — Phase F, 2026-11-27] Audit log + báo cáo ngày tự động**
    (`audit.py`, `report.py`, lệnh `audit` và `report --save`, xem
    `docs/fund-risk-ops.md` §3–§4): audit log append-only
    `decisions/audit-log.jsonl` (file runtime, đã gitignore), mỗi dòng
    1 JSON `{ts, actor, event, details}`; sự kiện ghi:
    `KILL_SWITCH_ON/OFF`, `FUND_LIMIT_BLOCKED`, `LIVE_CYCLE_STARTED`
    (mỗi chu kỳ), `LIVE_CYCLE_STOPPED` (chỉ khi chu kỳ có giao dịch,
    có lệnh bị chặn, hoặc kill switch đang bật — tránh spam chu kỳ
    HOLD), `REPORT_GENERATED`. Lệnh `audit [--lines N]` in N dòng gần
    nhất, mới nhất lên đầu. Lệnh `report --save PATH` ghi báo cáo ra
    file thay vì in stdout (tự tạo thư mục cha) và thêm 3 mục: trạng
    thái kill switch, giới hạn quỹ (giá trị cấu hình + trạng thái hiện
    tại), 5 dòng audit gần nhất. Lịch chạy tự động (Task Scheduler /
    cron sau phiên) do Phu tạo trên máy live — tool không tự tạo.
36. **[ĐÃ CÓ — Phase E, 2026-11-27] Dashboard web chỉ đọc**
    (`dashboard.py` `build_dashboard_data` / `render_dashboard` /
    `create_server` / `start_dashboard`, xem `docs/dashboard.md`):
    entry point riêng `python -m diamondx10.dashboard` (stdlib
    `http.server`, không framework, không nối CLI), trang duy nhất
    `/` tự làm mới mỗi 60 giây bằng meta refresh; **chỉ đọc — không
    đặt lệnh, không ghi equity-state.json / decisions-log.csv / kho
    lịch sử, không gọi MT5, không tự chạy tín hiệu hay backtest khi
    load trang** (chỉ hiển thị dữ liệu đã có); các mục: vị thế đang
    mở (P&L chưa thực hiện ước tính theo giá đóng nến mới nhất trong
    kho local, không có giá thì "chưa có giá"), vốn hiện tại từng
    desk + toàn quỹ và P&L đã thực hiện theo ngày rút từ dòng CLOSE
    trong log (không bịa đường cong vốn theo ngày vì đường cong
    trong state không kèm ngày), 10 tín hiệu/lệnh gần nhất từ log,
    kết quả backtest gần nhất đọc từ `results/backtest-latest.json`
    (CLI backtest hiện chưa tự lưu file), rủi ro từng desk
    (drawdown so với giới hạn 10% quỹ / cảnh báo 5% desk, số lệnh
    mới + số lần bị chặn hôm nay từ log). Mục thiếu dữ liệu hiện
    "chưa có dữ liệu", file thiếu/hỏng thì trang vẫn trả 200.
    **Chưa có auth nên chỉ bind `127.0.0.1`, KHÔNG bind `0.0.0.0`.**
37. **[ĐÃ CÓ — 2026-11-27] Mẫu hình nến + hỗ trợ/kháng cự offline
    (PTKT)** (`patterns.py` `detect_patterns` / `pattern_summary`,
    xem `docs/analysis-workflow.md`): trên nến OHLC phát hiện
    engulfing tăng/giảm, hammer, shooting star, doji, morning star,
    evening star; pivot swing (N=5 nến mỗi bên) → mức hỗ trợ/kháng cự;
    double top/bottom (2 pivot cách nhau ≥5 nến, giá chênh ≤1%);
    breakout lên trên swing high gần nhất / xuống dưới swing low gần
    nhất. `detect_patterns` trả list `{name, direction, strength 0..1,
    bar_index, time, detail}`; `pattern_summary` trả text ngắn + điểm
    ròng −1..1 (tăng dương). Kết quả gắn vào `generate_signals` qua
    key `"patterns"` / `"pattern_score"` — **chỉ làm bối cảnh, không
    đổi action** (cùng cách đối xử với `"regime"` mục 21).
38. **[ĐÃ CÓ — 2026-11-27] Phân tích cơ bản qua briefing + verdict
    (PTCB)** (`briefing.py` `build_briefing` / `cmd_briefing`,
    `synthesis.py` `validate_verdict` / `save_verdict`, lệnh
    `briefing` / `verdict`, xem `docs/analysis-workflow.md`): trước
    phiên, tool gom giá + tín hiệu kỹ thuật + tin thị trường
    (`run_news`, phân tầng tin cậy mục 26) + macro (nếu có) thành 1
    briefing md+json cho từng desk, ghi rõ người phân tích (forex —
    Yuling Pan, xauusd — Yumi, crypto — Rich, us_securities — Kathy).
    Briefing là **file bàn giao**: Phu gửi file cho Muse trong chat,
    Muse đóng vai nhà phân tích của desk đó và trả về verdict JSON;
    tool không gọi API nào tới Muse (không có API đó). Lệnh `verdict`
    kiểm tra chặt verdict (desk phải có, direction chỉ buy/sell/
    neutral, confidence 0..1, thiếu trường → lỗi sạch) rồi gộp theo
    desk, giữ bản mới nhất mỗi desk, vào
    `decisions/fundamental-verdicts.json` (file runtime, đã gitignore).
    Không có mục `news:` trong config thì `briefing` báo lỗi sạch
    (copy từ `config.example.yaml`).
39. **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Ma trận tổng hợp Yuling (PTKT + PTCB)**
    (`synthesis.py` `synthesize`, lệnh `synthesize`, mục `synthesis:`
    trong `config.example.yaml`, xem `docs/analysis-workflow.md`):
    Yuling là người tổng hợp cuối. Giá trị mặc định đã chốt (chỉnh được trong
    config): PTKT BUY + PTCB buy tin cậy ≥0,6 → MUA size 1,0; tin cậy
    thấp → MUA size 0,5; PTCB neutral → MUA size 0,5; PTCB sell tin
    cậy ≥0,6 → KHÔNG MUA (chặn) size 0; tin cậy thấp → MUA size 0,5
    (cảnh báo). PTKT SELL đối xứng. PTKT HOLD + PTCB bất kỳ → CHỜ
    (mục 40). Verdict thiếu hoặc cũ hơn `verdict_max_age_hours`
    (24 giờ) thì coi như chưa có PTCB mới: size 0,5 kèm cảnh
    báo; `require_fa: false` — thiếu/cũ không chặn (size 0 chỉ khi
    `require_fa: true`).
40. **[ĐÃ CHỐT — 2026-11-27] PTCB một mình không bao giờ tạo lệnh
    vào.** PTKT HOLD thì CHỜ dù PTCB mạnh đến đâu (mục 39). Trong vòng
    live, cổng PTCB chỉ có quyền **chặn**: khi PTCB mâu thuẫn mạnh với
    PTKT (tin cậy ≥ ngưỡng) thì lệnh không được đặt, trả
    `BLOCKED-FA-CONFLICT`, ghi log và gửi cảnh báo chặn Telegram;
    thiếu verdict hoặc verdict cũ thì vòng live vẫn chạy như cũ, chỉ
    ghi rõ `FA: chua co` / `FA: cu` vào kết quả (xem
    `docs/live-loop.md` §5).

41. **[ĐÃ CÓ — 2026-11-27] Chế độ khuyến nghị + nút đặt lệnh Telegram**
    (`pending.py` `PendingOrderStore`, `live.py` bước 7 trong
    `process_symbol`, `listener.py` `run_listener`, lệnh `live` /
    `mt5-trade --recommend-only` + `telegram-listen`, xem
    `docs/live-loop.md` §6): khi `trading.require_confirmation: true`
    (hoặc có `--recommend-only`), tín hiệu BUY/SELL qua hết các cổng
    thì tool KHÔNG đặt lệnh mà tạo lệnh chờ trong
    `decisions/pending-orders.json`, ghi log `RECOMMENDED`, gửi khuyến
    nghị Telegram kèm nút "Place order" / "Ignore". Chỉ khi bấm nút "Place
    order" thì listener mới đặt lệnh DEMO theo đúng thông số đã lưu.
    Chế độ tự động (mặc định) không đổi: lệnh đặt ngay, cảnh báo không
    nút. Dry-run không bao giờ tạo lệnh chờ.
42. **[ĐÃ CHỐT — 2026-11-27] Mô hình bảo mật nút đặt lệnh.**
    Chỉ chat có `telegram.chat_id` trong config mới bấm nút được; chat
    khác bị từ chối ("No permission"). Nút chỉ mang mã lệnh ngắn
    (`ord:<id>` / `skip:<id>`), thông số lệnh luôn lấy từ kho lệnh chờ
    local, không tin dữ liệu từ Telegram. Lệnh chờ chỉ dùng 1 lần.
    Lúc đặt lệnh, kill switch, tài khoản DEMO, ký quỹ và độ lệch giá
    được kiểm tra lại (không dùng kết quả kiểm tra lúc gửi khuyến nghị).
43. **[ĐÃ CHỐT — Phu duyệt 2026-11-27] Hạn lệnh chờ 15 phút + độ lệch giá 1,0%.**
    Lệnh chờ hết hạn sau `telegram.pending_order_ttl_min` (15 phút);
    quá hạn thì nút hết tác dụng. Lúc bấm nút, giá thị trường lệch
    khỏi giá khuyến nghị quá `telegram.max_entry_deviation_pct` (1,0%)
    thì listener tự chối đặt lệnh. Hai số này chỉnh được trong config.
44. **[ĐÃ CHỐT — sua doi 2026-11-27] Giao dien Telegram theo ngon
    ngu da chon (tieng Viet mac dinh hoac tieng Anh); khong con
    tieng Anh bat buoc nhu ban chot 2026-11-27 truoc do.** Muc
    `language:` o cap cao nhat cua `config.yaml` quyet dinh ngon ngu
    (`vi` mac dinh, `en` neu chon — xem quy tac 51): tin khuyen nghi
    (`BUY/SELL RECOMMENDATION (DEMO)` / ban tieng Viet tuong duong),
    tin chan (`ORDER BLOCKED`), tin thu, nut bam
    (`Place <HƯỚNG> <SYMBOL> <lot> lot` / `Ignore` va ban tieng Viet),
    cau tra loi callback (`Order placed`, `No permission`,
    `Order expired`, `Order not found`, `Kill switch is ON`,
    `Not a demo account`, `Insufficient margin`,
    `Price moved too far from recommendation`, `Order failed: ...`,
    `Ignored`) va tin nhan da sua (`ORDER PLACED — ticket #X`,
    `Ignored.`, `Order could not be placed: ...`) deu theo ngon ngu
    da chon. **CLI/console/log van tieng Viet khong dau.** Ly do noi
    bo cua kho lenh cho (`pending.py`: `khong tim thay lenh` / `lenh
    da het han` / `lenh da duoc xu ly`) giu nguyen tieng Viet khong
    dau, chi dich sang ngon ngu da chon tai bien Telegram
    (`listener.py`).
45. **[ĐÃ CÓ — 2026-11-27] Tu dong hoa trinh duyet cho khau ban giao
    PTCB** (`muse_browser.py` `send_briefing`, lenh `muse-send` /
    `briefing --send`, xem `docs/muse-browser.md`): dx10 dieu khien
    cua so Chromium qua Playwright de gui file briefing vao chat
    Muse (muse.ai), thay cho viec Phu gui file bang tay (muc 38).
    Playwright la phu thuoc tu chon (opt-in): cai bang lenh
    `muse-setup` (`pip install playwright` + `playwright install
    chromium`), KHONG nam trong luong mac dinh cua `quickstart.py`.
    dx10 la CLI khong co GUI — "mo trinh duyet" nghia la dx10 khoi
    dong va dieu khien 1 cua so Chromium rieng o che do headed
    (`muse.headless: false`) de user nhin thay; dang nhap Muse lam
    bang tay 1 lan trong cua so do, phien dang nhap luu local o
    `muse.profile_dir` (mac dinh `data/muse-profile`, file runtime
    da gitignore). Tool khong hoi, khong nhan, khong luu mat khau
    Muse; khong co token hay chat ID trong config (muc `muse:` chi
    co `chat_url`, `profile_dir`, `headless`, `wait_min`).
46. **[ĐÃ CHỐT — 2026-11-27] Trich xuat verdict tu dong chi la
    best-effort; hong thi nap tay, khong bao gio luu verdict chua
    kiem tra** (`muse_browser.py` `wait_for_verdict`, xem
    `docs/muse-browser.md` §4): sau khi gui briefing, tool dinh ky
    doc tin nhan tro ly moi trong chat, lay khoi ```json cuoi cung,
    kiem tra bang `synthesis.validate_verdict` (cung ham kiem tra
    nhu lenh `verdict --file`) roi moi luu vao
    `decisions/fundamental-verdicts.json`. Doc DOM la best-effort:
    neu muse.ai doi giao dien thi viec doc (hoac gui) co the hong
    ma khong bao truoc. Moi truong hop that bai — gui loi, het gio
    doi (`muse.wait_min`, mac dinh 10 phut), verdict khong hop le —
    thi lenh thoat 1 va fallback la nap tay bang `verdict --file`;
    verdict khong hop le bi loai, khong ghi vao file. Ma thoat 0
    chi khi verdict da luu, hoac `--no-wait` va file da gui thanh cong.
47. **[ĐÃ CÓ — 2026-11-27] Web UI quan ly giao dich — React + FastAPI,
    chi chay localhost** (`webui/` + `src/diamondx10/webapi.py`, xem
    `docs/web-ui.md`): giao dien web chay tren
    `http://127.0.0.1:8000`, frontend React + Vite + TypeScript build
    ra `src/diamondx10/static/` va duoc FastAPI phuc vu o `/`, API
    JSON o `/api/*`. Chay bang `python -m diamondx10.webapi
    [--port 8000] [--host 127.0.0.1]`. Mac dinh chi bind 127.0.0.1
    (localhost), khong co auth — cung ranh gioi bao mat nhu dashboard
    chi doc (`dashboard.py`): khong mo port ra ngoai, khong bind
    0.0.0.0. Backend quan ly vong live va `telegram-listen` duoi dang
    tien trinh con (subprocess), bat/tat duoc tu UI.
48. **[ĐÃ CHỐT — 2026-11-27] Hanh dong tu UI dung lai dung ham kiem tra
    cua backend — khong co duong tat.** Dat lenh tu UI
    (`POST /api/pending/{id}/place`) chay dung cac buoc kiem tra nhu
    nut Telegram (`listener.py`): kill switch TAT, tai khoan DEMO, du
    ky quy, gia thi truong lech khoi gia khuyen nghi <= 1,0% (quy tac
    43). Kill switch la cung 1 file CLI dung
    (`decisions/kill-switch.json`, `killswitch.py`): bat/tat tu UI hay
    tu CLI deu co hieu luc ngay cho ca hai. UI khong tu dat lenh live,
    khong bo qua cong nao — no chi la mat truoc cua cung backend CLI.
49. **[ĐÃ CÓ — 2026-11-27] Chu ky PTCB tu dong qua `muse-auto` +
    Task Scheduler** (`muse_auto.py` `cmd_muse_auto`, lenh
    `muse-auto`, xem `docs/muse-browser.md` §8): moi desk chay dung
    1 duong — tao briefing bang `build_briefing` (chung code voi
    lenh `briefing`), gui bang `send_briefing`, doi verdict bang
    `wait_for_verdict` (toi da `muse.wait_min`, mac dinh 10 phut),
    khong lap lai logic gui/doi. Chay dinh ky mac dinh **headless**
    (Task Scheduler khong co desktop tuong tac); dang nhap lan dau
    van lam bang tay headed 1 lan (muc 45) — cung profile luu san
    chay duoc ca headed lan headless. Ma thoat: **0 khi tat ca
    briefing da gui** — thieu verdict / het gio doi chi la CANH BAO,
    vong live van dung verdict cu, khong bao gio bi chan vi thieu
    verdict moi; **1 khi bat ky lenh gui nao that bai** (loi trinh
    duyet, chua dang nhap, khong tim thay composer, khong tao duoc
    briefing). Het phien dang nhap (khong tim thay composer — co
    `session_expired` trong ket qua gui) thi gui them canh bao
    Telegram theo ngon ngu da chon (quy tac 44, 51) de Phu dang nhap
    lai bang tay; loi Telegram la best-effort, khong bao gio che mat
    loi goc.
    Sau moi lan chay ghi `decisions/fa-cycle-state.json`
    (`started_utc` + tung desk `{sent, verdict_stored, reason}`,
    khong chua token hay du lieu phien, file runtime da gitignore)
    de web UI hien thi trang thai lan chay cuoi. Khong bao gio luu
    verdict chua kiem tra (muc 46).
50. **[ĐÃ CÓ — 2026-11-27] Symbol tren server Exness Trial co hau to
    "m"; ten chuan giu noi bo, chi bien MT5 moi dich**
    (`data/mt5_feed.py` `resolve_mt5_symbol` / `build_symbol_map`,
    `mt5.symbol_suffix` trong `config.example.yaml`, xem
    `docs/mt5-demo.md` §4b): server Trial them "m" vao moi symbol
    (EURUSD -> EURUSDm), server Real thi khong; hau to suy ra tu ten
    server ("Trial" -> "m", "Real" -> "", khong ro -> ""), mac dinh
    `mt5.symbol_suffix: "auto"`, ghi de bang `"m"` hoac `""`. Ten
    chuan (EURUSD...) giu nguyen trong config, decisions log, tong
    hop, briefing, Telegram va bao cao; chi cac loi goi MT5 moi dung
    ten broker. Bang anh xa chuan -> broker lap sau khi dang nhap,
    thu `[ten co hau to, ten chuan]` qua `symbol_info`, ten nao co
    tren server thi dung; ca hai ten deu khong co thi bao loi neu ro
    ca hai ten da thu + server.
51. **[ĐÃ CÓ — 2026-11-27] Giao dien song ngu Anh/Viet, co lua chon
    cua user — mac dinh tieng Viet** (`i18n.py` `get_language` /
    bo dich, `webapi.py` `GET/POST /api/language`, xem
    `docs/web-ui.md` §7): moi giao dien deu ho tro tieng Anh VA
    tieng Viet, user chon 1 lan bang nut doi ngon ngu tren web UI
    (hoac sua truc tiep khoa `language:` o cap cao nhat cua
    `config.yaml` local, gia tri `vi` | `en`, mac dinh `vi` khi
    thieu/sai). Lua chon chay theo ca 3 noi: **web UI** (nhan, tab),
    **Telegram** (tin khuyen nghi/chan/thu, nut bam, cau tra loi
    callback — quy tac 44), **briefing** (noi dung briefing tao ra
    bang ngon ngu da chon — xem `docs/analysis-workflow.md`).
    Web UI doc lai config moi request nen doi ngon ngu co hieu luc
    ngay, khong can khoi dong lai server; tab Muse tao/gui briefing
    cung doc config luc goi nen dung ngon ngu hien tai. **Khong
    dich:** noi dung bai bao goc trong kho tin giu nguyen ngon ngu
    goc; **nhan tieng Viet tren web UI co dau day du;
    CLI/console/log van tieng Viet khong dau.**
52. **[ĐÃ CÓ — 2026-11-27] Trang chu web UI hien tin doi da phan
    tich, kem nhan dinh theo tung desk** (`webapi.py`
    `GET /api/team-news`, xem `docs/web-ui.md` §7): 1 endpoint gop
    tra `{items, verdicts, briefings}` — `items`: bai tin moi nhat
    moi desk tu kho tin (`data/news.py` `NewsStore`: `title`,
    `source`, `tier` 1/2/3, `desk`, `analyst`, `time`,
    `briefing_url` tro toi briefing moi nhat cua desk do, null neu
    chua co); `verdicts`: nhan dinh PTCB moi nhat moi desk
    (`{direction, confidence}` hoac null neu chua co, tu kho
    `decisions/fundamental-verdicts.json`); `briefings`: file
    briefing moi nhat moi desk (`{desk, file, time}`). Thieu du lieu
    thi tra list rong / null, khong bao gio traceback.
53. **[ĐÃ CÓ — 2026-11-27] Bai dang phan tich: moi bai deu mang 1
    ket luan; BUY/SELL thi gui tom tat qua Telegram, NEUTRAL thi
    khong gui** (`posts.py` `PostStore`, `telegram.py`
    `format_post_summary`, xem `docs/web-ui.md` §8,
    `docs/analysis-workflow.md` §3): moi bai dang tren feed trang
    chu deu co `action` BUY | SELL | NEUTRAL — khong co bai dang
    nao khong co ket luan. Bai BUY/SELL moi duoc dang thi gui 1 tin
    tom tat qua Telegram (chi khi `telegram.enabled: true`): tieu
    de + symbol + ket luan, desk + analyst, entry/SL/TP (neu co),
    do tin cay, tom tat; tin chi la thong tin — khong nut dat lenh,
    khong tao lenh cho. Bai NEUTRAL khong gui gi. Gui loi chi in
    canh bao, khong bao gio lam hong viec dang bai. Vong live
    KHONG dang bai va KHONG gui tom tat bai dang — 2 duong Telegram
    (khuyen nghi live, tom tat bai phan tich) tach biet, khong co
    double-send (xem `docs/live-loop.md` §4).
54. **[ĐÃ CÓ — 2026-11-27] Feed bai dang la trang chu; bai dang la
    goc nhin da xuat ban cua doi, moi nhat len dau; dedupe bai
    tong hop** (`webui/src/components/Feed.tsx`,
    `src/diamondx10/posts.py`, xem `docs/web-ui.md` §8): tab
    Overview mo len la feed (composer o tren, danh sach bai duoi),
    bai moi nhat len dau, loc duoc theo desk. Kho bai dang la
    `decisions/analysis-posts.json` (file runtime, da gitignore;
    thieu/hong thi doc nhu kho rong). Dedupe: bai tu tong hop
    (`source: synthesis`, tu `synthesize --publish` /
    `POST /api/publish`) co cung symbol + cung action + cung
    `verdict_created_utc` voi bai moi nhat cua symbol do thi tra
    lai bai cu, khong tao bai moi, khong gui Telegram lai. Bai
    dang tay (`publish-post` / composer / `POST /api/posts`) luon
    tao bai moi, khong dedupe. Feed khong co like / comment /
    reaction / stories.

## 8. Những điểm đang lệch giữa nghiên cứu và code

| Điểm | Nghiên cứu viết | Code hiện tại |
|---|---|---|
| Lọc RSI khi vào lệnh | Chỉ mua khi RSI không quá mua (`research/forex-yuling.md`) | Đã chốt ngưỡng (BUY 50–70, SELL 30–50); code nối ở Phase 2 |
| Cắt lỗ theo ATR | "Cắt lỗ theo ATR" (`research/forex-yuling.md`) | Đã chốt SL 1,5× ATR (crypto 2,0×), TP 2× SL; code ở Phase 2; SL 5% cũ đã bị thay thế |
| Giới hạn drawdown 10% | Ghi trong config | Đã chốt tính theo toàn quỹ + cảnh báo desk 5%; **Phase 4:** `DrawdownGuard` đã nối vào luồng chạy, chặn lệnh mới và log `BLOCKED-DRAWDOWN-*` |

## 9. Checklist cần chốt (Yuling quyết, LJ/Kel cài đặt)

- [x] Ngưỡng RSI cho BUY/SELL — chốt 2026-11-27: BUY 50 < RSI < 70, SELL 30 < RSI < 50 (mục 5); đã cài ở Phase 2.
- [x] Stop loss theo ATR thay cho 5% cố định — chốt 2026-11-27: SL 1,5× ATR, crypto 2,0× ATR; TP = 2× SL (mục 11, 13); đã cài ở Phase 2.
- [x] Quy tắc chốt lời cố định 5% — chốt xong 2026-11-26 (mục 13), rồi **đã bị thay thế ngày 2026-11-27** bằng TP theo ATR; đã cài ở Phase 2.
- [x] Trailing stop — chốt 2026-11-27 (mục 14); đã cài ở Phase 2.
- [x] Quy tắc thoát khi tín hiệu đảo chiều; quản lý vị thế mở — chốt 2026-11-27 (mục 14); thoát khi đảo chiều đã cài ở Phase 2, quản lý vị thế mở ở Phase 4/5.
- [x] Drawdown 10% — chốt 2026-11-27: tính theo toàn quỹ + cảnh báo desk 5% (mục 12); đã cài ở Phase 4.
- [x] Giới hạn số lệnh mỗi ngày / mỗi desk; có lọc phiên, lọc tin không — chốt 2026-11-27: tối đa 1 lệnh mới/symbol/ngày, mặc định không lọc phiên, danh sách sự kiện lọc tin mặc định rỗng (mục 6); đã cài ở Phase 4.
- [x] Chiến lược riêng theo từng desk, hay giữ một quy tắc chung — chốt 2026-11-27: giữ một quy tắc chung cho cả 4 desk (mục 4); tách sau chỉ khi backtest cho thấy cần.
- [x] Registry chiến lược + tham số riêng theo symbol — Phase B, xong 2026-11-27: `default`/`donchian` trong `STRATEGY_REGISTRY` (donchian `backtest_only`), `strategy.per_symbol` resolve theo thứ tự mặc định < chung < desk < symbol, validate giá trị lạ (mục 4, 30); xem `docs/strategy-engine.md` §1–§2. Luồng live `mt5-*` đã nối per-symbol ở bước tích hợp sau Phase B.
- [x] So sánh chiến lược + sweep tham số chống overfitting — Phase B, xong 2026-11-27: `compare_strategies` (bảng chỉ dùng OOS), `sweep_params` (chỉ xếp hạng theo OOS, báo cả train/test, lưới mặc định 9 tổ hợp, không tự áp tham số thắng vào config) (mục 24, 30); xem `docs/strategy-engine.md` §3–§5, `docs/backtest.md`.
- [x] Backtest trên dữ liệu thật từ kho lịch sử — Phase C, xong 2026-11-27: `run_backtest_from_history` / `run_walk_forward_from_history` (mỗi symbol 1 chuỗi bar riêng, lỗi rõ khi kho trống/thiếu bar), `import_csv_bars` (CSV của `export-bars`, trùng thì bỏ qua, sai thì báo số dòng) (mục 32); xem `docs/real-data-backtest.md`. CLI `--source history` và `import-bars` đã nối ở bước tích hợp.
- [x] Dashboard web chỉ đọc — Phase E, xong 2026-11-27: `python -m diamondx10.dashboard` (stdlib `http.server`, chỉ bind `127.0.0.1`, chưa có auth), trang `/` tự refresh 60 giây: vị thế mở + P&L ước tính theo giá kho mới nhất, vốn + P&L theo ngày từ log, 10 tín hiệu gần nhất, backtest gần nhất từ `results/backtest-latest.json`, rủi ro từng desk (mục 36); xem `docs/dashboard.md`. Giới hạn: không đặt lệnh, không tự chạy tín hiệu/backtest, số liệu chỉ đúng tới lần chạy tool gần nhất.
- [x] Backtest tính lãi/lỗ thật thay cho bản nháp hiện tại
      (`backtest.py` mới chỉ in tín hiệu cuối, chưa có P&L) — Phase 3,
      xong 2026-11-27: engine chạy bar-by-bar (vào ở close, SL/TP theo
      ATR, trailing, thoát khi đảo chiều), sizing theo
      `risk.position_size` + bảng risk theo symbol, phí 0,02% +
      trượt giá 0,01% (config mục `backtest`), metrics return/win
      rate/profit factor/Sharpe/max DD theo desk + symbol + train/test
      (mặc định 70/30), xem `docs/backtest.md`. Giới hạn: dữ liệu mô
      phỏng theo desk (mọi symbol cùng chuỗi giá), kết quả KHÔNG phải
      hiệu suất thật.
- [x] Vòng lặp live M15 + cảnh báo Telegram — Phase D, xong 2026-11-27:
  `process_symbol` dùng chung cho `mt5-trade` và `live`, chu kỳ `--once`
  cho Task Scheduler/cron, cảnh báo chỉ khi có tín hiệu/lệnh/bị chặn,
  Telegram mặc định tắt, token chỉ qua biến môi trường (mục 31); xem
  `docs/live-loop.md`. Chưa kiểm chứng live: chu kỳ thật trên máy Windows
  có MT5 demo + token Telegram thật.
- [ ] Theo dõi: hạ rủi ro desk vàng xuống 2–3% — chỉ quyết sau khi có số ATR thật từ MT5 demo (mục 8).
- [ ] **Giới hạn rủi ro toàn quỹ — các con số mặc định Phase F (mục 33): lỗ trong ngày 3% vốn quỹ, tối đa 10 vị thế mở toàn quỹ, tối đa 2 vị thế mở/desk — cần Phu duyệt (giữ nguyên, tăng hay giảm).**
- [ ] Donchian breakout có dùng cho đường live không — cần Phu duyệt + bằng chứng walk-forward (mục 23).
- [ ] Có dùng regime (ADX) để chặn/giảm lệnh không (mục 21) — cần Phu quyết.
- [ ] Nguồn dữ liệu vĩ mô live cho macro edge: yfinance hay Yuling nhập tay (mục 22) — cần Phu quyết.
- [ ] Kelly 25% + risk parity có thay bảng rủi ro cố định theo symbol không (mục 27) — cần Phu quyết.
- [ ] Chốt lời từng phần TP1/TP2 thay TP duy nhất 2×SL không (mục 28) — cần Yuling/Phu quyết.

## Tài liệu liên quan

- `docs/architecture.md` — kiến trúc, luồng dữ liệu.
- `docs/workflow.md` — quy trình làm việc Yuling → LJ/Kel.
- `docs/live-loop.md` — vòng lặp live M15, cảnh báo Telegram, Task Scheduler/cron (mục 31).
- `docs/fund-risk-ops.md` — giới hạn rủi ro toàn quỹ, kill switch, audit log, báo cáo ngày tự động (mục 33–35).
- `docs/dashboard.md` — dashboard web chỉ đọc (mục 36).
- `docs/mt5-demo.md` — hướng dẫn Exness demo + MT5, giới hạn vốn nhỏ.
- `docs/history-store.md` — kho nến OHLC local, backfill/export CSV (mục 29).
- `quickstart.py` — chạy nhanh: cài gói, hỏi login lúc chạy, dry-run 4 desk.
- `config.example.yaml` — mọi con số rủi ro/vốn (mức chung 1%/lệnh, riêng EURUSD 3% / XAUUSD 10% / BTCUSD 8%, TP/SL 5%, drawdown 10%, 2.500 USD/desk).
- `docs/backtest.md` — engine backtest, walk-forward, VaR/CVaR, so sánh chiến lược, sweep tham số.
- `docs/strategy-engine.md` — registry chiến lược, tham số riêng theo symbol, walk-forward + so sánh + sweep, cảnh báo overfitting (Phase B).
- `docs/market-news.md` — nguồn tin thị trường theo desk, phân tầng độ tin cậy.
- `docs/analysis-workflow.md` — quy trình phân tích PTKT + PTCB + tổng hợp Yuling (mục 37–40).
- `docs/muse-browser.md` — gửi briefing cho Muse bằng trình duyệt tự động, chờ verdict, chu kỳ tự động `muse-auto` (mục 45–46, 49).
- `docs/merge-diamondx10-2026-11-27.md` — hồ sơ merge từ repo DiamondX10 cũ + ThaoResearch (lấy gì, không lấy gì, mâu thuẫn nào cần Phu quyết).
- `research/` — bài nghiên cứu/nhận định theo từng mảng.
