# Kiến trúc DiamondX10 Trading

Nền tảng quant trading kiểu Aladdin của BlackRock, thu nhỏ cho DiamondX:
LJ và Kel xây, Yuling nghiên cứu lý thuyết.

```
Yuling (lý thuyết) ──> strategies/ + models/quant.py
LJ (data scientist, model/AI) ──> strategies, models, signals
Kel (data analysis, data/infra) ──> data/feeds, providers, backtest
Kathy/Yumi/Rich    ──> research/ theo mảng + decisions log
```

Luồng dữ liệu: provider thời gian thực → `DataFeed` → chiến lược →
tín hiệu → `risk.py` (sizing/stop) → `decisions.py` (ghi log + thông báo).
