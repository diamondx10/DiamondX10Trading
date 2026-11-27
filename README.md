# DiamondX10 Trading

Công cụ giao dịch định lượng (quant trading) của quỹ mô phỏng DiamondX.
Do **LJ và Kel** viết bằng kỹ thuật và khoa học máy tính, dựa trên lý thuyết
giao dịch do **Yuling Pan** nghiên cứu.

> **Lưu ý:** Đây là bộ khung chạy được với dữ liệu **mô phỏng / ví dụ**.
> Nghiên cứu và giao dịch thật dùng dữ liệu thời gian thực qua interface
> `src/diamondx10/data/`, cấu hình trong `config.example.yaml`.
> Không có giá thật, lệnh thật hay API key nào trong repo này.
> Connector MT5 **chỉ chạy tài khoản DEMO** (Exness demo) — xem `docs/mt5-demo.md`.
> Chưa nối broker nào: `RealTimeFeed` trước đây là placeholder, nay là
> MT5Feed khi `data.provider: mt5`; mặc định vẫn là `simulated`.

## Quỹ giả định (hypothetical)

| Desk | Người phụ trách | Chuyên môn | Vốn giả định |
|---|---|---|---|
| Forex | Yuling Pan | Forex | 2.500 USD |
| US Securities | Kathy | Chứng khoán Mỹ — AI, chip, EDA tool | 2.500 USD |
| XAUUSD | Yumi | Vàng (XAUUSD) | 2.500 USD |
| Crypto | Rich | Crypto | 2.500 USD |
| **Tổng DiamondX10** | | | **10.000 USD** |

LJ và Kel xây nền tảng, không giao dịch trong 10.000 USD này.

## Chức vụ trong tổ chức (khác chuyên môn)

CEO — Yuling Pan · Giám đốc giao dịch — Kathy · Truyền thông — Yumi ·
Nghiên cứu — Rich · Viết tool lượng tử — LJ và Kel.

## Chạy thử (không cần dữ liệu thật)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # điền provider thật của bạn vào đây
python3 -m diamondx10 --help
python3 -m diamondx10 demo          # chạy demo với dữ liệu mô phỏng
python3 -m diamondx10 backtest --desk forex --days 30
python3 -m diamondx10 backtest --desk crypto --days 60 --symbol BTCUSD --split 0.5  # xem docs/backtest.md
python3 -m diamondx10 backtest --desk forex --days 120 --walk-forward  # kiem dinh walk-forward
python3 -m diamondx10 backtest --desk xauusd --days 60 --strategy donchian  # so sanh breakout Donchian
python3 -m diamondx10 news --desk xauusd  # tin thi truong theo desk (xem docs/market-news.md)
python3 -m diamondx10 report       # bao cao hang ngay: von, drawdown, vi the mo, lenh hom nay, cac lan bi chan
python3 -m diamondx10 report --save decisions/report-2026-11-27.md  # ghi bao cao ra file (xem docs/fund-risk-ops.md)
python3 -m diamondx10 kill-switch status   # xem kill switch: bat hay tat
python3 -m diamondx10 audit --lines 10     # 10 dong audit gan nhat
python3 -m pytest -q
```

## MT5 demo (Exness demo + MetaTrader 5) — chỉ demo, không tiền thật

Chi tiết đầy đủ trong `docs/mt5-demo.md`. Tóm tắt: MT5 terminal và tool
phải chạy trên **cùng 1 máy Windows**; tạo tài khoản demo Exness, điền
`login` / `server` vào `config.yaml` local (không commit), mật khẩu qua
biến môi trường `MT5_PASSWORD`.

```bash
pip install MetaTrader5   # chỉ trên máy chạy MT5 terminal (Windows)
python3 -m diamondx10 mt5-symbols                    # kiểm tra symbol có trên server demo (CDNS có thể không có)
python3 -m diamondx10 mt5-dry-run --desk forex       # lấy giá thật, chỉ in tín hiệu, KHÔNG đặt lệnh
python3 -m diamondx10 mt5-trade --desk forex         # đặt lệnh DEMO (có chặn demo-only, stop loss bắt buộc)
python3 -m diamondx10 live --desk forex --once       # 1 chu kỳ live M15: tín hiệu + lệnh DEMO + cảnh báo Telegram (xem docs/live-loop.md)
python3 -m diamondx10 live --desk forex              # vòng lặp live tới khi Ctrl+C (máy Windows có MT5)
```

## Vòng lặp live M15 — tín hiệu + lệnh DEMO + cảnh báo Telegram (Phase D)

Chi tiết đầy đủ trong `docs/live-loop.md`. Tóm tắt: mỗi 15 phút, tool chạy
1 chu kỳ cho 1 desk — đối chiếu vị thế mở, chặn drawdown / cửa sổ cấm /
giới hạn 1 lệnh/ngày, tính tín hiệu SMA+RSI, đặt lệnh DEMO khi có BUY/SELL
(cùng đường xử lý với `mt5-trade`), rồi gửi cảnh báo Telegram khi có tín
hiệu, lệnh đã đặt, hoặc lệnh bị chặn. HOLD thì không gửi. Tin tức không
gửi tự động. Telegram mặc định tắt (`telegram.enabled: false`); token chỉ
qua biến môi trường `DIAMONDX10_TELEGRAM_TOKEN`, không ghi vào config.

```bash
python3 -m diamondx10 live --desk forex --once   # 1 chu kỳ rồi thoát (Task Scheduler / cron, mỗi 15 phút)
python3 -m diamondx10 live --desk crypto         # lặp tới biên nến M15 tiếp theo, dừng bằng Ctrl+C
```

## Giới hạn quỹ, kill switch, audit log, báo cáo ngày (Phase F)

Chi tiết đầy đủ trong `docs/fund-risk-ops.md`. Tóm tắt: 3 giới hạn toàn
quỹ chặn mở lệnh mới — lỗ trong ngày ≥ 3% vốn quỹ (300 USD),
tối đa 10 vị thế mở toàn quỹ, tối đa 2 vị thế mở mỗi desk — các con số
này là **giá trị mặc định đề xuất, [CẦN CHỐT], chưa được Phu duyệt**
(cấu hình ở mục `risk:` trong `config.yaml`). Kill switch dừng mọi lệnh
mới nhưng vị thế đang mở vẫn được đối chiếu/đóng theo SL/TP. Mọi sự
kiện vận hành ghi vào audit log append-only
`decisions/audit-log.jsonl`.

```bash
python3 -m diamondx10 kill-switch on --reason "su co thi truong" --by "Phu"  # dung mo lenh moi
python3 -m diamondx10 kill-switch status   # xem trang thai
python3 -m diamondx10 kill-switch off --by "Phu"   # mo lai giao dich
python3 -m diamondx10 audit --lines 10     # dong audit gan nhat, moi nhat len dau
python3 -m diamondx10 report --save decisions/report-2026-11-27.md  # bao cao ngay ra file (co kill switch + gioi han quy + audit)
```

Báo cáo ngày chạy tự động sau phiên bằng Windows Task Scheduler (máy
Windows chạy MT5) hoặc cron (Linux) — hướng dẫn trong
`docs/fund-risk-ops.md` §4; tool không tự tạo lịch chạy.

## Dashboard web — xem vốn, vị thế, tín hiệu, backtest, rủi ro (Phase E)

Chi tiết đầy đủ trong `docs/dashboard.md`. Tóm tắt: dashboard **chỉ đọc** — không đặt lệnh, không sửa state/log/kho, không gọi MT5, không tự chạy tín hiệu hay backtest khi load trang; chỉ hiển thị dữ liệu local đã có. Chạy bằng entry point riêng (không nối CLI), stdlib `http.server`, không framework:

```bash
python3 -m diamondx10 dashboard            # http://127.0.0.1:8000/ (mặc định, chỉ local)
python3 -m diamondx10 dashboard --port 8123
```

Trang duy nhất `/`, tự làm mới mỗi 60 giây, gồm: vị thế đang mở (P&L chưa thực hiện ước tính theo giá đóng nến mới nhất trong kho local, không có giá thì ghi "chưa có giá"), vốn hiện tại từng desk + toàn quỹ và P&L đã thực hiện theo ngày từ log, 10 tín hiệu/lệnh gần nhất từ decisions log, kết quả backtest gần nhất (đọc file `results/backtest-latest.json` nếu có — CLI backtest hiện chưa tự lưu file, xem `docs/dashboard.md` §3), trạng thái rủi ro từng desk (drawdown so với giới hạn 10% quỹ / cảnh báo 5% desk, số lệnh mới + số lần bị chặn hôm nay). Mục thiếu dữ liệu hiện "chưa có dữ liệu", file thiếu/hỏng thì trang vẫn trả 200. **Chưa có auth nên chỉ bind `127.0.0.1`, KHÔNG bind `0.0.0.0` hay mở cổng ra ngoài.**

## Kho nến OHLC local — backfill / xuất CSV (Phase A)

Nến thật từ MT5 demo được lưu vào SQLite local (`data/history.db`,
file runtime, đã gitignore) để backtest trên dữ liệu thật. Chi tiết trong
`docs/history-store.md`. Chạy trên **máy Windows có MT5 terminal**:

```bash
python3 -m diamondx10 backfill --desk forex --timeframe M15 --days 30   # kéo nến MT5 demo vào kho
python3 -m diamondx10 backfill --symbol XAUUSD --timeframe H1 --days 90
python3 -m diamondx10 export-bars --desk crypto --timeframe M15 --days 30  # xuất CSV ra data/exports/
python3 -m diamondx10 export-bars --symbol EURUSD --from mt5 --days 30     # luôn kéo live (làm mới kho)
python3 -m diamondx10 export-bars --symbol EURUSD --from simulated --days 30  # CHỈ demo/test, không phải giá thật
```

Mặc định `export-bars` lấy từ kho (`--from store`); symbol nào chưa có
bar trong kho thì thử kéo 1 lần từ MT5 live rồi lưu vào kho. Khung nến hỗ
trợ: M1, M5, M15, H1, D1 (mặc định M15, 90 ngày theo mục `history:` trong
config). Trên máy không có MT5, `backfill` / `export-bars --from mt5` báo
lỗi sạch và dừng, không in traceback.

Lưu ý: rủi ro theo từng symbol (mức chung 1%/lệnh; EURUSD 3%, XAUUSD 10%, BTCUSD 8%), stop loss theo ATR (1,5× ATR, crypto 2,0× ATR; TP gấp đôi khoảng cách stop) thay cho mức 5% cố định cũ — xem `docs/trading-principles.md` mục 9, 11, 13. Mức 5% cũ đã bị thay thế ngày 2026-11-27. Với stop ATR (thường hẹp hơn 5%) khối lượng tính ra to hơn nên vẫn trên 0,01 lot theo cùng công thức; kiểm chứng lại bằng số ATR thật từ MT5 demo khi chạy lần đầu.

## Cấu trúc

```
src/diamondx10/
  config.py      # đọc config.yaml, placeholder cho provider thật
  data/feeds.py  # DataFeed interface + SimulatedFeed (dữ liệu mô phỏng)
  data/history.py # HistoryStore — kho nến OHLC SQLite local (docs/history-store.md)
  data/mt5_feed.py # MT5Feed — dữ liệu thật từ MT5 terminal (demo)
  data/news.py   # tin thi truong RSS theo desk + phan tang do tin cay (docs/market-news.md)
  data/providers.py # build_feed(): 'simulated' | 'mt5'; RealTimeFeed = MT5Feed
  execution.py   # khớp lệnh DEMO qua MT5, chặn demo-only, sizing theo risk
  live.py        # vong lap live M15: process_symbol + run_live_cycle/loop (docs/live-loop.md)
  killswitch.py  # kill switch: dung mo lenh moi, vi the mo van doi chieu (docs/fund-risk-ops.md)
  audit.py       # audit log append-only JSONL cho su kien van hanh (docs/fund-risk-ops.md)
  telegram.py    # canh bao Telegram ve tin hieu/lenh/bi chan (stdlib urllib)
  strategies/    # base + 1 chiến lược mẫu cho mỗi desk + breakout Donchian (chi backtest)
  models/quant.py# chỉ báo: SMA, RSI, ATR, volatility, ADX/regime
  models/macro.py# macro edge DXY/US10Y/VIX/SPX (chi boi canh, xem docs/trading-principles.md muc 22)
  portfolio.py   # chia vốn theo desk, 2.500 USD/desk
  risk.py        # position sizing, max drawdown, stop-loss, VaR/CVaR bao cao + gioi han quy Phase F
  positions.py   # doi chieu vi the mo theo nen (SL/TP/trailing/dao chieu)
  dashboard.py   # dashboard web chi doc (Phase E, docs/dashboard.md):
                 # von, vi the mo, tin hieu gan nhat, backtest gan nhat,
                 # rui ro tung desk — stdlib http.server, chi local
  report.py      # bao cao hang ngay: von, drawdown, vi the mo, lenh hom nay + kill switch/gioi han quy/audit (Phase F)
  signals.py     # tín hiệu BUY/SELL/HOLD + lý do + regime
  decisions.py   # ghi quyết định mua/bán vào decisions/
  backtest.py    # backtest co P&L that tren du lieu mo phong (docs/backtest.md) + walk-forward
docs/mt5-demo.md # hướng dẫn Exness demo + MT5, từng bước
docs/market-news.md # tin thi truong theo desk, phan tang do tin cay
docs/merge-diamondx10-2026-11-27.md # ho so merge tu repo DiamondX10 cu + ThaoResearch
research/        # bài nghiên cứu / nhận định, ai phụ trách mảng nào viết mảng đó
decisions/       # decisions log: quyết định mua/bán được thông báo
```

## Quyết định mua / bán

Mọi quyết định mua/bán đều được ghi vào `decisions/decisions-log.csv`
và thông báo theo mẫu trong `decisions/README.md`.
