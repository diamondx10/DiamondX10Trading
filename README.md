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
| Forex | Yuling Pan | Forex | 500 USD |
| US Securities | Kathy | Chứng khoán Mỹ — AI, chip, EDA tool | 500 USD |
| XAUUSD | Yumi | Vàng (XAUUSD) | 500 USD |
| Crypto | Rich | Crypto | 500 USD |
| **Tổng DiamondX10** | | | **2.000 USD** |

LJ và Kel xây nền tảng, không giao dịch trong 2.000 USD này.

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
```

Lưu ý: vốn desk 500 USD, rủi ro 1%/lệnh thì volume tính ra có thể < 0.01 lot
với stop loss 2% — lúc đó tool không đặt lệnh (xem mục 5 trong `docs/mt5-demo.md`).

## Cấu trúc

```
src/diamondx10/
  config.py      # đọc config.yaml, placeholder cho provider thật
  data/feeds.py  # DataFeed interface + SimulatedFeed (dữ liệu mô phỏng)
  data/mt5_feed.py # MT5Feed — dữ liệu thật từ MT5 terminal (demo)
  data/providers.py # build_feed(): 'simulated' | 'mt5'; RealTimeFeed = MT5Feed
  execution.py   # khớp lệnh DEMO qua MT5, chặn demo-only, sizing theo risk
  strategies/    # base + 1 chiến lược mẫu cho mỗi desk
  models/quant.py# chỉ báo: SMA, RSI, ATR, volatility
  portfolio.py   # chia vốn theo desk, 500 USD/desk
  risk.py        # position sizing, max drawdown, stop-loss
  signals.py     # tín hiệu BUY/SELL/HOLD + lý do
  decisions.py   # ghi quyết định mua/bán vào decisions/
  backtest.py    # backtest placeholder trên dữ liệu mô phỏng
docs/mt5-demo.md # hướng dẫn Exness demo + MT5, từng bước
research/        # bài nghiên cứu / nhận định, ai phụ trách mảng nào viết mảng đó
decisions/       # decisions log: quyết định mua/bán được thông báo
```

## Quyết định mua / bán

Mọi quyết định mua/bán đều được ghi vào `decisions/decisions-log.csv`
và thông báo theo mẫu trong `decisions/README.md`.
