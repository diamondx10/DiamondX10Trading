# Backtest — engine tính lãi/lỗ thật (Phase 3)

> **MO PHONG — KHONG PHAI HIEU SUAT THAT.** Backtest chay tren du lieu
> mo phong (`SimulatedFeed`). Ket qua chi de kiem tra logic chien luoc /
> sizing, khong du doan ket qua giao dich that, khong dung de ra quyet
> dinh giao dich that.

## Chạy

```bash
python3 -m diamondx10 backtest --desk forex --days 60
python3 -m diamondx10 backtest --desk crypto --days 60 --symbol BTCUSD
python3 -m diamondx10 backtest --desk xauusd --days 90 --split 0.5
python3 -m diamondx10 backtest --desk forex --days 120 --walk-forward
python3 -m diamondx10 backtest --desk forex --days 120 --walk-forward --train-bars 60 --test-bars 20 --step-bars 20
python3 -m diamondx10 backtest --desk xauusd --days 60 --strategy donchian
```

- `--desk`: forex | xauusd | crypto | us_securities (mặc định forex).
- `--days`: số ngày (mặc định 30). Engine lấy `days + 20` bar: 20 bar
  đầu là warm-up cho SMA20/RSI/ATR.
- `--symbol`: chỉ backtest 1 symbol của desk (mặc định: tất cả symbol
  của desk trong config).
- `--split`: tỷ lệ train cho tách in-sample / out-of-sample
  (mặc định 0,7 → 70% đầu / 30% cuối).
- `--strategy`: `default` (quy tắc chung đã chốt) hoặc `donchian`
  (breakout Donchian 20 — **chỉ để so sánh trong backtest**, chưa dùng
  live; xem `src/diamondx10/strategies/breakout.py`).
- `--walk-forward`: kiểm định walk-forward thay cho 1 lần tách
  train/test (xem mục dưới). `--train-bars` / `--test-bars` /
  `--step-bars`: số bar train / test / bước trượt mỗi cửa sổ
  (mặc định 30 / 10 / 10 cho demo; kiểm định thật dùng
  `--days 120 --train-bars 60 --test-bars 20`).

## Nguồn dữ liệu: mô phỏng vs kho lịch sử (Phase C)

| | Mô phỏng (`SimulatedFeed`) | Kho lịch sử (`HistoryStore`, MT5 demo) |
|---|---|---|
| Chạy bằng | `run_backtest(desk, days, ...)` / CLI `backtest` (mặc định) | `run_backtest_from_history(desk, cfg, ...)` / `run_walk_forward_from_history(...)` — xem `docs/real-data-backtest.md` |
| Chuỗi giá | Theo **desk**: mọi symbol chạy **cùng một chuỗi giá**, chỉ khác vốn/risk/contract size | Theo **symbol**: mỗi symbol 1 chuỗi bar riêng của nó; đường equity cấp desk nối theo trục thời gian |
| Giá | Quanh 100, không phải giá thật | Giá thật MT5 demo (EURUSD ~1,16, vàng ~5.000, BTC ~120.000) — sizing/lot và cờ `below_min_lot` mới có ý nghĩa thật |
| Kết quả | Chỉ để kiểm tra logic chiến lược / sizing | Vẫn **không phải bảo đảm lợi nhuận tương lai** — chỉ để kiểm định chiến lược trên giá thật; chỉ OOS mới có ý nghĩa |

- `run_backtest` / `run_walk_forward` đã nhận `bars=` từ trước; Phase C
  thêm `bars_by_symbol={symbol: [bars]}` (mỗi symbol 1 chuỗi bar riêng,
  chỉ truyền 1 trong 2). `compare_strategies` / `sweep_params` cũng nhận
  `bars_by_symbol` để so sánh / quét trên dữ liệu thật.
- Báo cáo in tiêu đề **MO PHONG** hay **DU LIEU THAT — MT5 DEMO** tùy
  `result["simulated"]` — đọc tiêu đề trước khi tin con số.
- CLI `--source history` **đã nối** (bước tích hợp sau Phase C):
  `backtest --source history [--timeframe M15] [--walk-forward]`,
  `compare --source history`, `sweep --source history`, và lệnh
  `import-bars --file ... --symbol ... [--timeframe M15]` để nhập CSV
  của `export-bars` vào kho. CLI `backtest` mặc định vẫn chạy mô phỏng.

## Engine hoạt động thế nào (`src/diamondx10/backtest.py`)

1. **Warm-up:** bỏ qua tín hiệu cho đến khi có ít nhất 20 bar lịch sử.
2. **Vào lệnh:** tín hiệu BUY/SELL (SMA5/SMA20 + lọc RSI, xem
   `docs/phase0-desk-rules.md`) mà chưa có vị thế mở thì mở ở giá đóng
   cửa của bar đó, SL/TP theo ATR từ chiến lược (SL 1,5× ATR, crypto
   2,0×; TP = 2× khoảng cách SL).
3. **Quản lý vị thế mở** ở mỗi bar sau đó, theo thứ tự:
   trailing SL theo giá đóng cửa → chạm SL (ưu tiên trước TP nếu cùng
   1 bar chạm cả hai) → chạm TP → tín hiệu đảo chiều đầy đủ thì đóng
   ở giá đóng cửa.
4. **Vị thế còn mở ở bar cuối** được đóng ép ở giá đóng cửa cuối
   (lý do `end_of_data`) để mọi lệnh đều được hạch toán.
5. **Sizing:** `risk.position_size` với vốn symbol (vốn desk chia đều
   cho các symbol), % risk của symbol (bảng `risk.per_symbol_pct`
   trong config: EURUSD 3%, XAUUSD 10%, BTCUSD 8%, còn lại 1%) và
   contract size theo desk (`execution.CONTRACT_SIZES`).
   Lot MT5 = units / contract size, chỉ để tham khảo: lệnh dưới
   0,01 lot **vẫn mở trong backtest** nhưng bị đánh dấu
   `below_min_lot` — lệnh đó **không đặt được trên MT5 thật**.

## Phí và trượt giá (giả định, mục `backtest` trong config)

| Tham số | Mặc định | Nghĩa |
|---|---|---|
| `fee_pct` | 0,02 | % trên notional (units × giá vào), trừ 1 lần mỗi lệnh tròn |
| `slippage_pct` | 0,01 | % trên giá vào, áp dụng bất lợi cả 2 chân (vào + ra) |

Cả hai đều là mức giả định **bảo thủ**, cấu hình được trong
`config.example.yaml` / `config.yaml` (mục `backtest`). Đổi số là đổi
kết quả — ghi rõ số đang dùng trong báo cáo (mục "GIA DINH").

## Đọc báo cáo

Báo cáo in theo desk (gộp mọi symbol) rồi theo từng symbol, mỗi mục
có 3 dòng: **Full** (toàn bộ bars), **Train** (70% đầu),
**Test** (30% cuối). Train/Test chạy engine **riêng** trên từng đoạn
(vốn khởi đầu lại từ đầu, warm-up lại từ đầu) nên lệnh ở đoạn Test
không phải là lát cắt của lệnh Full.

| Chỉ số | Nghĩa |
|---|---|
| return % | (equity cuối − vốn) / vốn, tính trên vốn desk/symbol đã dùng |
| win rate | % lệnh lãi trên tổng lệnh đã đóng |
| profit factor | tổng lãi / tổng lỗ (n/a nếu không có lệnh thua) |
| Sharpe | từ lợi nhuận theo từng bar của đường equity, annualize bằng √24192 (252 ngày × 96 bar M15/ngày) — **chỉ minh họa**, dữ liệu mô phỏng không có lịch thật |
| max DD % | drawdown lớn nhất của đường equity (đỉnh → đáy) |
| VaR95 / CVaR95 | Value-at-Risk 95% / Conditional VaR 95% của lợi nhuận theo bar (VaR lịch sử, quantile nội suy tuyến tính; CVaR = trung bình các khoản lỗ vượt VaR). Chỉ số báo cáo — **không phải giới hạn chặn lệnh** (giới hạn chặn vẫn là drawdown 10%, xem `docs/trading-principles.md` mục 12). Hiển thị `n/a` khi lịch sử < 20 returns |
| P&L | tổng lãi/lỗ ròng sau phí + trượt giá |

## Walk-forward (`backtest --walk-forward`)

Ý tưởng lấy từ repo DiamondX10 cũ (`walk_forward.py`) nhưng chạy trên
engine của tool này (không copy code gốc — xem
`docs/merge-diamondx10-2026-11-27.md`).

- Chia dữ liệu thành nhiều cửa sổ **train → test** trượt liên tiếp:
  cửa sổ bắt đầu tại bar 0, 10, 20... (bước `--step-bars`), mỗi cửa sổ
  train `N` bar rồi test `M` bar ngay sau đó.
- Mỗi cửa sổ chạy engine **riêng** trên từng đoạn (vốn khởi đầu lại,
  warm-up lại). Chỉ đoạn **test** (out-of-sample) được gộp vào kết quả
  tổng hợp — đoạn train chỉ để xem chiến lược có ổn định qua các đoạn
  thời gian hay không, không tính vào kết quả chính.
- Đường equity OOS tổng hợp được nối bằng cách cộng dồn biến động của
  từng cửa sổ test (mỗi cửa sổ bắt đầu lại từ vốn desk).
- Báo cáo in: tổng hợp OOS (return / win rate / Sharpe / max DD /
  VaR95 / CVaR95 / P&L) rồi từng cửa sổ (số lệnh OOS, return, win rate,
  Sharpe, max DD, P&L).
- Dùng để **so sánh chiến lược** (mặc định vs Donchian) và kiểm tra độ
  ổn định trước khi đề xuất dùng live — không phải bằng chứng hiệu suất
  thật (dữ liệu vẫn là mô phỏng).
- Walk-forward Phase B còn gộp cả các đoạn train vào khóa
  `"aggregated_train"` (chỉ để đối chiếu train/test khi sweep — các cửa
  sổ train chồng lấp nhau nên số này chỉ tham khảo) và ghi tham số thực
  tế từng symbol vào `"strategy_params"`.

## So sánh chiến lược (`compare_strategies`, Phase B)

Chạy walk-forward cho nhiều chiến lược trên **cùng dữ liệu** và trả
bảng so sánh **chỉ trên kết quả out-of-sample** (đoạn test):

```python
from diamondx10.backtest import compare_strategies, format_strategy_comparison

comp = compare_strategies("forex", ["default", "donchian"], cfg=cfg,
                          symbols=["EURUSD"], train_bars=60, test_bars=20,
                          step_bars=20, bars=bars)
print(format_strategy_comparison(comp))
```

Mỗi chiến lược 1 dòng: return OOS, win rate OOS, max drawdown OOS,
số lệnh OOS (+ Sharpe / profit factor / P&L OOS tham khảo), sắp theo
return OOS giảm dần. Đoạn train không tính vào bảng. Chi tiết từng
chiến lược nằm ở `comp["walk_forward"][ten]`. CLI cho so sánh đã nối:
`compare [--strategies ...] [--source simulated|history]` (xem
`docs/strategy-engine.md`).

## Parameter sweep (`sweep_params`, Phase B — công cụ nghiên cứu)

Quét lưới tham số nhỏ, mỗi bộ tham số chạy walk-forward đầy đủ, **chỉ
xếp hạng theo OOS**, báo cáo kèm cả train và test để lộ overfitting:

```python
from diamondx10.backtest import sweep_params, format_sweep_report

sweep = sweep_params("forex", bars, "default",
                     {"atr_sl_mult": [1.0, 1.5, 2.0],
                      "rsi_buy_low": [45, 50, 55]},
                     cfg=cfg, symbols=["EURUSD"],
                     train_bars=60, test_bars=20, step_bars=20)
print(format_sweep_report(sweep))
```

Lưới mặc định (`DEFAULT_SWEEP_GRID`) có 9 tổ hợp; vượt
`max_combinations` (mặc định 27) thì báo lỗi. Bộ nào train hơn test
quá 5 điểm % thì bị đánh dấu nghi overfitting. **Sweep không tự động
áp tham số thắng vào config** — xem cảnh báo overfitting trong
`docs/strategy-engine.md` §5.

## Giới hạn phải biết

- **SimulatedFeed là theo DESK, không theo symbol.** Mọi symbol của
  một desk chạy **cùng một chuỗi giá mô phỏng**, chỉ khác vốn/risk/
  contract size. Kết quả per-symbol không phải so sánh thật giữa
  các symbol, và không nói gì về giá thật của symbol đó.
- Giá mô phỏng quanh 100, không phải giá thật (EURUSD ~1,16, vàng
  ~5.000, BTC ~120.000) nên sizing/lot trên dữ liệu mô phỏng —
  đặc biệt là cờ `below_min_lot` ở desk forex — không phản ánh
  sizing trên giá thật.
- Không có lọc phiên / lọc tin trong backtest (cơ chế lọc ở Phase 4);
  giới hạn 1 lệnh mới/symbol/ngày cũng chưa áp trong backtest.
- Sharpe và mọi chỉ số đều tính trên dữ liệu mô phỏng: dùng để so
  sánh logic chiến lược, không dùng để kỳ vọng lợi nhuận thật.
- Trên dữ liệu thật (Phase C, `docs/real-data-backtest.md`): dữ liệu
  vẫn cần đủ dài (90 ngày M15 ~ 8.640 bar), chứng khoán chỉ có bar
  trong phiên Mỹ, và chỉ kết quả out-of-sample mới có ý nghĩa.
