# Dashboard web — Phase E (chỉ đọc)

> **CHỈ ĐỌC.** Dashboard không đặt lệnh, không sửa state/log/kho,
> không gọi MT5, không tự chạy tín hiệu hay backtest khi load trang.
> Nó chỉ hiển thị dữ liệu đã có trên máy local.

## 1. Chạy

```bash
python -m diamondx10.dashboard            # http://127.0.0.1:8000/
python -m diamondx10.dashboard --port 8123
python -m diamondx10.dashboard --host 127.0.0.1 --port 8000
```

- Entry point riêng của module (`src/diamondx10/dashboard.py`,
  stdlib `http.server`, không framework, không nối CLI).
- Bind mặc định `127.0.0.1` — **chỉ local**. Dashboard **chưa có
  auth** nên **KHÔNG bind `0.0.0.0`** và không mở cổng ra ngoài.
- Trang duy nhất `/` (HTML + CSS inline, không JS framework); trang
  tự làm mới mỗi **60 giây** bằng `<meta http-equiv="refresh">`,
  có cả link Refresh bấm tay.
- Hàm public để test / dùng lại: `start_dashboard(host, port)`,
  `create_server(...)`, `build_dashboard_data(cfg, ...)`,
  `render_dashboard(data)`.

## 2. Các mục trên trang lấy số từ đâu

| Mục | Nguồn số liệu |
|---|---|
| Vị thế đang mở | `decisions/equity-state.json` qua `decisions.load_equity_state` (desk, symbol, hướng, giá vào, SL/TP, volume, ngày mở). P&L chưa thực hiện = hướng × (giá đóng nến mới nhất trong kho lịch sử local − giá vào) × volume × contract size; giá mới nhất lấy từ `HistoryStore` (khung mặc định `history.default_timeframe`, M15). Không lấy được giá thì ghi "chưa có giá" |
| Vốn | Vốn hiện tại từng desk + toàn quỹ từ `DrawdownGuard` trong state (đường cong `fund_curve` / `desk_curves`); chưa có state thì vốn ban đầu theo config (10.000 USD, 2.500 USD/desk) và ghi rõ. P&L đã thực hiện hôm nay + theo ngày rút từ các dòng `CLOSE` trong `decisions-log.csv` (reason có dạng `... P&L 25.00 USD (TP)`) |
| Tín hiệu / lệnh gần nhất | 10 dòng mới nhất trong `decisions-log.csv` — **chỉ đọc log, không tự chạy tín hiệu mới khi load trang** |
| Kết quả backtest gần nhất | File JSON kết quả `run_backtest` / `run_backtest_from_history` (xem §3). **Không tự chạy backtest khi load trang** (chậm) |
| Trạng thái rủi ro từng desk | Drawdown lớn nhất so với giới hạn 10% toàn quỹ / cảnh báo 5% mỗi desk (từ `DrawdownGuard`), số lệnh mới hôm nay + số lần bị chặn hôm nay đếm từ log theo ngày hiện tại |

Mục nào thiếu dữ liệu thì hiện **"chưa có dữ liệu"** thay vì số 0
gây hiểu lầm. File thiếu hoặc hỏng (JSON/CSV lỗi, kho lịch sử lỗi)
thì mục đó hiện "chưa có dữ liệu", trang vẫn trả **200**, không
crash. Đường cong vốn trong state **không kèm ngày** nên dashboard
không bịa đường cong theo ngày — chỉ hiện vốn hiện tại + P&L đã thực
hiện theo ngày từ log.

## 3. Kết quả backtest gần nhất — cần lưu file tay

CLI `backtest` hiện chỉ in kết quả ra màn hình, **chưa tự lưu file**,
nên mục backtest mặc định hiện "chưa có dữ liệu" kèm hướng dẫn.
Để hiện mục này, lưu kết quả JSON (dict trả về của `run_backtest` /
`run_backtest_from_history`) vào `results/backtest-latest.json`
(hoặc file `results/backtest-*.json` mới nhất — dashboard tự tìm):

```python
import json
from diamondx10.backtest import run_backtest_from_history
from diamondx10.config import load_config

result = run_backtest_from_history("forex", load_config())
with open("results/backtest-latest.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
```

Dashboard đọc các trường `desk`, `strategy`, `simulated`/`source`,
`timeframe`, `n_bars`, `symbols`, `metrics` (return, win rate, max
DD, số lệnh, P&L, Sharpe) và `segments.test.metrics` (return + số
lệnh OOS). File sai định dạng thì mục này hiện "chưa có dữ liệu".

## 4. Giới hạn

- **Không có auth** — chỉ chạy local (`127.0.0.1`), không mở cổng
  ra ngoài, không dùng trên máy chia sẻ.
- **Không đặt lệnh, không sửa state/log/kho** — mọi thay đổi vẫn qua
  CLI (`live`, `mt5-trade`, `backtest`).
- **Số liệu chỉ đúng tới lần chạy tool gần nhất** — dashboard không
  tự chạy tool; muốn số mới thì chạy `live --once` / `mt5-trade` /
  `backfill` rồi tải lại trang (trang tự refresh mỗi 60 giây).
- **Không có giá live** — P&L chưa thực hiện dùng giá đóng nến mới
  nhất trong kho local (từ lần `backfill` gần nhất), không phải giá
  MT5 hiện tại; chưa có bar trong kho thì ghi "chưa có giá".
- Trên máy Linux không có MT5, trang vẫn mở được với dữ liệu local
  (state/log/kho có gì hiện nấy).

## 5. Hướng mở rộng sau này (chưa làm)

- CLI `backtest` tự lưu kết quả JSON vào `results/` để dashboard
  luôn có mục backtest mới nhất mà không cần lưu tay (§3).
- Auth đơn giản (token) nếu cần mở dashboard ngoài localhost.
- Giá mới nhất từ MT5 live thay cho giá đóng nến trong kho (chỉ khi
  chạy trên máy Windows có MT5 terminal).
- Biểu đồ đường cong vốn theo ngày (cần state ghi kèm ngày cho mỗi
  điểm trên đường cong — hiện state chưa có).
- Lọc theo desk / symbol trên trang.

## 6. File liên quan

- `src/diamondx10/dashboard.py` — `build_dashboard_data()`,
  `render_dashboard()`, `create_server()`, `start_dashboard()`.
- `tests/test_dashboard.py` — state/log/kho giả trong tmp, server
  trên cổng tạm, thiếu/hỏng file, chứng minh GET không đổi file.
- `docs/trading-principles.md` mục 33 — quy tắc dashboard chỉ đọc
  [ĐÃ CÓ].
