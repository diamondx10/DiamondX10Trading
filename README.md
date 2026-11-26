# DiamondX10 Trading

Công cụ giao dịch định lượng (quant trading) của quỹ mô phỏng DiamondX.
Do **LJ và Kel** viết bằng kỹ thuật và khoa học máy tính, dựa trên lý thuyết
giao dịch do **Yuling Pan** nghiên cứu.

> **Lưu ý:** Đây là bộ khung chạy được với dữ liệu **mô phỏng / ví dụ**.
> Nghiên cứu và giao dịch thật dùng dữ liệu thời gian thực qua interface
> `src/diamondx10/data/`, cấu hình trong `config.example.yaml`.
> Không có giá thật, lệnh thật hay API key nào trong repo này.

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

## Cấu trúc

```
src/diamondx10/
  config.py      # đọc config.yaml, placeholder cho provider thật
  data/feeds.py  # DataFeed interface + SimulatedFeed (dữ liệu mô phỏng)
  strategies/    # base + 1 chiến lược mẫu cho mỗi desk
  models/quant.py# chỉ báo: SMA, RSI, ATR, volatility
  portfolio.py   # chia vốn theo desk, 500 USD/desk
  risk.py        # position sizing, max drawdown, stop-loss
  signals.py     # tín hiệu BUY/SELL/HOLD + lý do
  decisions.py   # ghi quyết định mua/bán vào decisions/
  backtest.py    # backtest placeholder trên dữ liệu mô phỏng
research/        # bài nghiên cứu / nhận định, ai phụ trách mảng nào viết mảng đó
decisions/       # decisions log: quyết định mua/bán được thông báo
```

## Quyết định mua / bán

Mọi quyết định mua/bán đều được ghi vào `decisions/decisions-log.csv`
và thông báo theo mẫu trong `decisions/README.md`.
