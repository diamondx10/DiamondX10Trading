# Strategy engine v2 — registry, tham số theo symbol, so sánh, sweep (Phase B)

> **MO PHONG — KHONG PHAI HIEU SUAT THAT.** Mọi kết quả so sánh /
> sweep trong file này đều chạy trên dữ liệu mô phỏng (`SimulatedFeed`)
> cho tới khi Phase A nối được dữ liệu MT5 thật. Kết quả chỉ dùng để
> so sánh logic chiến lược, không dùng để kỳ vọng lợi nhuận thật hay
> tự động đổi config.

## 1. Registry chiến lược (`src/diamondx10/strategies/registry.py`)

Mọi chiến lược đăng ký theo **tên** trong `STRATEGY_REGISTRY`:

| Tên | Hiển thị | backtest_only | Dùng live? |
|---|---|---|---|
| `default` | Quy tắc chung đã chốt (SMA + RSI + ATR) | Không | Có — quy tắc chung đã chốt, theo từng desk (crypto ATR 2,0×) |
| `donchian` | DonchianBreakout 20 | **Có** | **Không** — chỉ để so sánh trong backtest, cần Phu duyệt + bằng chứng walk-forward mới xét live |

```python
from diamondx10.strategies import get_strategy, list_strategies

list_strategies()  # [{name, display_name, desks, description, backtest_only}, ...]
strat = get_strategy("default", desk="forex")   # ForexTrend
strat = get_strategy("donchian", desk="forex")  # DonchianBreakout
get_strategy("ema")  # ValueError: Chien luoc khong biet: 'ema' (co: 'default', 'donchian')
```

Thêm chiến lược mới = thêm 1 mục vào `STRATEGY_REGISTRY` (+ lớp
chiến lược), không sửa code gọi ở nơi khác. `strategies/__init__.py`
giữ nguyên API cũ (`STRATEGIES`, `build_strategies`) để test cũ không vỡ;
hàm mới `build_strategy(desk, symbol=..., cfg=..., strategy_name=...)`
lấy instance theo symbol (xem mục 2).

## 2. Tham số riêng theo symbol (`strategy.per_symbol`)

**Override chỉ là tinh chỉnh con số, không thay quy tắc.** Không đổi
loại tín hiệu, không đổi khung thời gian, không thêm Kelly / chốt lời
từng phần / pairs trading. Giá trị mặc định đã chốt **không đổi**:
SMA5/20, RSI BUY 50–70 / SELL 30–50, cực đoan 80/20, ATR(14),
SL 1,5× ATR (crypto 2,0×), TP 2× khoảng cách SL, trailing 1,5× ATR.

Ví dụ config (mục `strategy` trong `config.yaml` — xem
`config.example.yaml`, đã thêm ví dụ `per_symbol` ở bước tích hợp):

```yaml
strategy:
  sma_fast: 5
  sma_slow: 20
  rsi_buy_low: 50
  rsi_buy_high: 70
  atr_sl_mult: 1.5
  tp_mult: 2.0
  desks:
    crypto: {atr_sl_mult: 2.0, trail_mult: 2.0}
  per_symbol:
    BTCUSD: {atr_sl_mult: 2.0}   # vi du: stop BTC rong hon
    XAUUSD: {rsi_buy_low: 55}    # vi du: vang doi RSI cao hon moi BUY
```

Thứ tự ưu tiên (thấp → cao, cao thắng):

```
mặc định đã chốt < tham số chung < ghi đè của lớp theo desk
(vd crypto 2,0×) < ghi đè riêng desk trong config
< ghi đè riêng symbol (per_symbol)
```

Hàm public:

```python
from diamondx10.strategies import resolve_strategy_params, build_strategy

params = resolve_strategy_params(cfg, "crypto", "BTCUSD")
# {'sma_fast': 5, ..., 'atr_sl_mult': 2.0, ...} — dict đầy đủ, bản sao
strat = build_strategy("crypto", symbol="BTCUSD", cfg=cfg)
```

Validate — giá trị lạ thì `ValueError` với message rõ ràng, không lặng
lẽ bỏ qua:

- Symbol phải có trong `config data.symbols` (nếu config khai báo symbols).
- Tên tham số phải biết (gõ sai tên, vd `atr_stop_mult`, thì báo lỗi
  thay vì tưởng đã ghi đè). Tham số biết được: `sma_fast/slow`,
  `rsi_period`, `rsi_buy_low/high`, `rsi_sell_low/high`,
  `rsi_extreme_high/low`, `atr_period`, `atr_sl_mult`, `tp_mult`,
  `trail_mult`, `donchian_period`, `min_atr_pct`.
- Giá trị phải là số, trong khoảng hợp lý (vd `atr_sl_mult` 0,5–5,0;
  `rsi_*` 0–100; `sma_fast`/`sma_slow`/`rsi_period`/`atr_period`/
  `donchian_period` phải là số nguyên), và thứ tự ngưỡng phải hợp lý
  (vd `rsi_buy_low < rsi_buy_high`, `sma_fast < sma_slow`).

Nối sẵn (không cần CLI):

- `signals.generate_signals(desk, bars, symbol="EURUSD", cfg=cfg)` —
  tín hiệu dùng đúng tham số của symbol đó; kết quả thêm khóa
  `"symbol"` và `"params"` (tham số thực tế đã dùng).
- `backtest.run_backtest(...)` / `run_walk_forward(...)` — mỗi symbol
  chạy đúng tham số của nó; kết quả thêm khóa `"strategy_params"`
  (`{symbol: params}`) để đối chiếu.
- **Đã nối (bước tích hợp sau Phase B):** luồng live `mt5-dry-run` /
  `mt5-trade` trong `__main__.py` build chiến lược riêng theo symbol
  trong vòng lặp (`build_strategy(args.desk, symbol=symbol, cfg=cfg)`)
  và `generate_signals(..., symbol=symbol, cfg=cfg)` — mỗi symbol
  dùng đúng tham số của nó cả lúc đối chiếu vị thế, lúc ra tín hiệu
  và lúc tính levels. Ví dụ `strategy.per_symbol` đã có trong
  `config.example.yaml` (đang comment).

CLI (đã nối ở bước tích hợp, xem `__main__.py`):

- `python -m diamondx10 compare --desk forex --strategies default donchian --days 120`
- `python -m diamondx10 sweep --desk forex --strategy default --days 120`

## 3. Walk-forward mở rộng + so sánh chiến lược

`run_walk_forward(...)` giữ nguyên API cũ, nay thêm:

- Chạy được với **mọi chiến lược trong registry** qua tham số
  `strategy_name` (đã có từ trước cho `donchian`, nay đi qua registry
  nên chiến lược mới thêm vào registry là chạy được ngay).
- Chạy được với **tham số per-symbol** (mỗi symbol dùng params đã
  resolve — xem mục 2).
- Kết quả thêm `"aggregated_train"` (gộp các đoạn train — chỉ để đối
  chiếu train/test khi sweep; các cửa sổ train **chồng lấp** nhau nên
  số này chỉ tham khảo) và `"strategy_params"`.

So sánh nhiều chiến lược trên cùng dữ liệu — **chỉ tính
out-of-sample**:

```python
from diamondx10.backtest import compare_strategies, format_strategy_comparison

comp = compare_strategies("forex", ["default", "donchian"], cfg=cfg,
                          symbols=["EURUSD"], train_bars=60, test_bars=20,
                          step_bars=20, bars=bars)
print(format_strategy_comparison(comp))
```

Mỗi chiến lược 1 dòng: return OOS, win rate OOS, max drawdown OOS,
số lệnh OOS (+ Sharpe / profit factor / P&L OOS tham khảo). Các dòng
sắp theo return OOS giảm dần. Đoạn train **không** tính vào bảng này.

## 4. Parameter sweep có chống overfitting (mức nhẹ — công cụ nghiên cứu)

```python
from diamondx10.backtest import sweep_params, format_sweep_report

sweep = sweep_params("forex", bars, "default",
                     {"atr_sl_mult": [1.0, 1.5, 2.0],
                      "rsi_buy_low": [45, 50, 55]},
                     cfg=cfg, symbols=["EURUSD"],
                     train_bars=60, test_bars=20, step_bars=20)
print(format_sweep_report(sweep))
```

- Mỗi bộ tham số chạy **walk-forward đầy đủ**; **chỉ xếp hạng theo
  kết quả OOS** (đoạn test).
- Báo cáo top-3 kèm **cả train return và test return** để lộ
  overfitting: bộ nào train cao hơn test quá 5 điểm % thì bị đánh dấu
  `[NGHI OVERFITTING]`.
- Lưới mặc định nhỏ (`DEFAULT_SWEEP_GRID`: `atr_sl_mult` ×
  `rsi_buy_low` = 9 tổ hợp) để chạy nhanh. Tổng số tổ hợp vượt
  `max_combinations` (mặc định 27) thì báo lỗi — lưới càng lớn / mẫu
  càng nhỏ thì bộ thắng OOS càng có thể chỉ là ngẫu nhiên.
- **Sweep KHÔNG tự động áp tham số thắng vào config.** Người đọc báo
  cáo tự quyết có đổi config không, sau khi kiểm chứng lại trên dữ
  liệu thật (MT5) và được Phu/Yuling duyệt.

## 5. Cảnh báo overfitting (đọc trước khi tin bất kỳ bảng nào ở đây)

1. Dữ liệu mô phỏng quanh giá 100, không phải giá thật — sizing/lot
   và P&L tuyệt đối không phản ánh giao dịch thật.
2. `SimulatedFeed` là theo desk: mọi symbol của desk chạy **cùng một
   chuỗi giá**, chỉ khác vốn/risk/contract size.
3. Walk-forward trên mẫu nhỏ (vài chục–vài trăm bar) cho ra ít lệnh;
   một bộ tham số thắng OOS với 3–5 lệnh chưa nói lên điều gì.
4. Quét càng nhiều tham số thì càng dễ "tìm" được bộ thắng do ngẫu
   nhiên — đó là lý do lưới mặc định nhỏ và có giới hạn tổ hợp.
5. Quy tắc đã chốt không đổi vì sweep: sweep chỉ tinh chỉnh con số
   trong khoảng đã validate (mục 2).

## Tài liệu liên quan

- `docs/backtest.md` — engine backtest, walk-forward, so sánh, sweep.
- `docs/trading-principles.md` — quy tắc 4 (tách theo symbol),
  23 (Donchian), 24 (walk-forward), 29 (Phase B — mới).
- `docs/phase0-desk-rules.md` — quy tắc đã chốt theo desk; tách theo
  symbol vẫn chỉ làm khi backtest cho thấy cần (nay đã có cơ chế).
