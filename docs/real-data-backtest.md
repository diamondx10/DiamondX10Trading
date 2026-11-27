# Backtest trên dữ liệu thật — Phase C (MT5 demo)

> **DU LIEU THAT (MT5 DEMO) — KHONG PHAI BAO DAM LOI NHUAN TUONG LAI.**
> Backtest o day chay tren nen that lay tu MT5 demo, khong phai
> `SimulatedFeed`. Ket qua van chi dung de kiem dinh chien luoc /
> sizing — khong phai bang chung hieu suat that hay loi nhuan tuong lai.

Quy tac da chot (khong doi): **MT5 cho tat ca**, crypto la cap USD
(BTCUSD/ETHUSD/BNBUSD), **khong Binance**. Chi tai khoan DEMO.

## Tong quan pipeline (4 buoc)

```
Windows (MT5 demo)                May nay (Linux, khong co MT5)
┌─────────────────────┐            ┌──────────────────────────────┐
│ 1. backfill          │            │ 2. import CSV vao kho        │
│    python -m         │  CSV       │    import_csv_bars(...)      │
│    diamondx10        │ ────────►  │                              │
│    backfill ...      │  gui file  │ 3. backtest / walk-forward / │
│    export-bars ...   │            │    compare / sweep TU KHO    │
└─────────────────────┘            │    run_*_from_history(...)   │
                                   └──────────────────────────────┘
```

## Buoc 1 — Backfill / export tren may Windows (MT5 demo dang mo)

```bash
pip install MetaTrader5   # chi tren may chay MT5 terminal (Windows)
python -m diamondx10 backfill --desk forex --timeframe M15 --days 90
python -m diamondx10 backfill   # mac dinh: ca 10 symbol, M15, 90 ngay
python -m diamondx10 export-bars --desk crypto --timeframe M15 --days 90
python -m diamondx10 export-bars --symbol XAUUSD --timeframe H1 --days 90 --out data/exports/
```

- 1 file CSV cho moi symbol: `{SYMBOL}_{TIMEFRAME}.csv`, cot
  `time,open,high,low,close,volume`; `time` la ISO UTC
  (vd `2026-11-27T00:00:00Z`). Chi tiet: `docs/history-store.md`.
- **Do dai khuyen nghi:** 90 ngay M15 ~ 8.640 bar/symbol — du cho
  backtest + walk-forward nhieu cua so. It hon 40 bar thi tool bao
  loi thay vi tra bao cao rong (xem muc "Loi thuong gap").
- Kiem tra truoc khi gui CSV: symbol co tren server demo khong
  (`python -m diamondx10 mt5-symbols`) — vd CDNS co the khong co
  tren Exness MT5 demo; symbol vang/missing thi backfill bao loi
  tung symbol, khong crash ca lenh.

## Buoc 2 — Chuyen CSV ve / import vao kho

Phu gui file CSV cho Muse (hoac Muse doc truc tiep neu co quyen doc
file). Import bang ham public `import_csv_bars` (module moi
`src/diamondx10/data/csv_import.py`):

```python
from diamondx10.data.csv_import import import_csv_bars
from diamondx10.data.history import HistoryStore

with HistoryStore("data/history.db") as store:  # mac dinh theo config
    result = import_csv_bars(store, "data/exports/EURUSD_M15.csv",
                             "EURUSD", "M15")
    print(result)
    # {'symbol': 'EURUSD', 'timeframe': 'M15',
    #  'path': 'data/exports/EURUSD_M15.csv',
    #  'imported': 8640, 'skipped': 0, 'total_rows': 8640,
    #  'start': 1756..., 'end': 1795...}  (start/end la epoch UTC)
```

- Bar trung (symbol, timeframe, time) da co trong kho thi **bo qua**,
  khong nhan doi — import 2 lan cung file thi lan 2 `imported: 0`,
  `skipped: <so bar>`; so bar trong kho khong doi.
- File sai cot (`time/open/high/low/close` thieu 1 cot), time khong
  doc duoc, hoac OHLC vo ly (high < open/close, low > open/close)
  thi `ValueError` neu ro so dong — **khong ghi nua chung**.
- Kho luu o `data/history.db` (SQLite, file runtime, da gitignore);
  duong dan lay tu muc `history.db_path` trong config.

> CLI import (`import-bars`) chua co — se noi o buoc tich hop sau
> (cung dot voi CLI `--source history` cho backtest, xem muc duoi).

## Buoc 3 — Chay backtest / walk-forward / compare / sweep tren du lieu that

**Chua co CLI** — goi truc tiep ham Python (xem muc "CLI se co").
CLI `backtest --source history` se goi dung cac ham nay o buoc tich
hop sau; ham public da on dinh de noi.

```python
from diamondx10.backtest import (
    compare_strategies,
    format_backtest_report,
    format_strategy_comparison,
    format_walk_forward_report,
    run_backtest_from_history,
    run_walk_forward_from_history,
    sweep_params,
)
from diamondx10.config import load_config
from diamondx10.data.history import HistoryStore

cfg = load_config()

# 3a. Backtest 1 lan (train/test 70/30) tren nen that.
result = run_backtest_from_history("forex", cfg, symbols=["EURUSD"],
                                   timeframe="M15")
print(format_backtest_report(result))

# 3b. Walk-forward: nhieu cua so train/test, chi OOS moi co y nghia.
wf = run_walk_forward_from_history("forex", cfg, symbols=["EURUSD"],
                                   timeframe="M15",
                                   train_bars=60, test_bars=20,
                                   step_bars=20)
print(format_walk_forward_report(wf))
print("OOS gop:", wf["aggregated"])

# 3c. So sanh chien luoc tren CUNG du lieu that (chi tinh OOS).
#     Donchian chi de so sanh trong backtest, khong dung live.
with HistoryStore("data/history.db") as store:
    bars = {s: store.get_bars(s, "M15") for s in ["EURUSD"]}
comp = compare_strategies("forex", ["default", "donchian"], cfg=cfg,
                          symbols=["EURUSD"], train_bars=60, test_bars=20,
                          step_bars=20, bars_by_symbol=bars)
print(format_strategy_comparison(comp))

# 3d. Sweep tham so tren du lieu that (xep hang CHI theo OOS).
sw = sweep_params("forex", None, "default",
                  {"atr_sl_mult": [1.0, 1.5, 2.0],
                   "rsi_buy_low": [45, 50, 55]},
                  cfg=cfg, symbols=["EURUSD"],
                  train_bars=60, test_bars=20, step_bars=20,
                  bars_by_symbol=bars)
```

Tham so chinh:

| Ham | Tham so dang chu y |
|---|---|
| `run_backtest_from_history(desk, cfg, *, symbols=None, timeframe="M15", start=None, end=None, train_fraction=0.7, strategy_name="default", store=None)` | `symbols=None` = tat ca symbol cua desk trong config; `start`/`end` = epoch int hoac datetime (loc bar trong khoang); `store=None` = tu mo kho theo `history.db_path` trong config |
| `run_walk_forward_from_history(desk, cfg, *, symbols=None, timeframe="M15", start=None, end=None, train_bars=60, test_bars=20, step_bars=20, strategy_name="default", store=None)` | nhu tren; moi symbol can it nhat `train_bars + test_bars` bar |
| `import_csv_bars(store, path, symbol, timeframe)` | tra `{imported, skipped, total_rows, start, end, ...}` |

### CLI se co (buoc tich hop sau — chua chay duoc)

```bash
python -m diamondx10 backtest --desk forex --source history --timeframe M15
python -m diamondx10 backtest --desk forex --source history --walk-forward --train-bars 60 --test-bars 20
python -m diamondx10 compare --desk forex --strategies default donchian --source history
```

Cho toi luc do, dung ham Python o tren. **Khong** dung CLI `backtest`
hien tai de ket luan ve du lieu that — no van chay `SimulatedFeed`.

### Engine dung lai — khong viet engine thu hai

`run_backtest_from_history` / `run_walk_forward_from_history` chi doc
bar tu kho roi goi lai `run_backtest` / `run_walk_forward` voi
`bars_by_symbol={symbol: [bars]}` — cung engine, cung quy tac vao/
thoat, cung sizing/phi/truot gia (`backtest.py`). Khac duy nhat so
voi du lieu mo phong:

- **Moi symbol 1 chuoi bar RIENG cua no** (du lieu mo phong theo
  desk: moi symbol chay cung chuoi gia). Ket qua per-symbol gio la
  so sanh that giua cac symbol.
- Duong equity cap desk noi theo **truc thoi gian** (hop nhat cac moc
  thoi gian cua moi symbol, forward-fill symbol nao chua co bar tai
  moc do) thay cho gop theo chi so bar. Khi moi symbol cung moc thoi
  gian thi ket qua y het duong cu (da co test doi chieu).
- Walk-forward: so cua so lay theo symbol **ngan nhat** (moi cua so
  phai du bar cho moi symbol).

## Buoc 4 — Doc ket qua + canh bao

Bao cao in giong `docs/backtest.md` (Full / Train / Test, theo symbol,
lenh da dong) nhung tieu de doi thanh **DU LIEU THAT — MT5 DEMO** va
ghi ro nguon: khung nen, khoang thoi gian (UTC), so bar/symbol.
Ket qua tra ve them: `simulated=False`, `source="history"`,
`timeframe`, `start`/`end` (epoch UTC), `n_bars_by_symbol`.

Canh bao — doc truoc khi tin bat ky con so nao:

1. **Du lieu that van can du dai.** 40 bar la muc toi thieu de tool
   chay (warm-up 20 + chia train/test), khong phai muc du de ket
   luan. Walk-forward chi co y nghia khi co nhieu cua so (vd 90 ngay
   M15, `train 60 / test 20 / step 20` cho ~400 cua so) va du lenh
   OOS (vài chuc lenh tro len). Thang OOS voi 3–5 lenh chua noi len
   gi.
2. **Chung khoan chi giao dich phien My.** AMD/CDNS/SNPS/INTC/NVDA
   khong co bar ngoai phien My, nghi cuoi tuan/le — khoang trong
   khong phai thieu du lieu. Sharpe annualize bang √24192 gia dinh
   lich giao dich deu (252 ngay × 96 bar M15/ngay); voi chung khoan
   thi con so nay chi de tham khao.
3. **Chi OOS moi co y nghia.** Train tot ma test kem (sweep danh dau
   `[NGHI OVERFITTING]` khi train hon test qua 5 diem %) thi khong
   doi config. Sweep khong tu dong ap tham so thang vao config.
4. **Co `below_min_lot` gio co y nghia that.** Tren gia that (EURUSD
   ~1,16, vang ~5.000, BTC ~120.000) thi sizing/lot moi phan anh
   duoc lenh co dat duoc tren MT5 khong — khac voi du lieu mo phong
   quanh gia 100. Lenh duoi 0,01 lot van mo trong backtest nhung bi
   danh dau, khong dat duoc tren MT5 that.
5. **Chua co loc phien / loc tin trong backtest** (co che loc o
   Phase 4); gioi han 1 lenh moi/symbol/ngay cung chua ap trong
   backtest. Ket qua backtest tot khong co nghia la duoc phep giao
   dich that — day van la tai khoan DEMO, khong dat lenh that.

## Loi thuong gap

| Loi | Nghia / cach sua |
|---|---|
| `Kho lich su chua co bar nao cho EURUSD (M15) — chay backfill / export-bars...` | Kho trong (hoac sai khung/start/end). Chay buoc 1 tren Windows roi import lai buoc 2. |
| `Symbol EURUSD (M15) chi co 10 bar trong kho, can toi thieu 40 bar...` | Khoang du lieu qua ngan. Backfill them (90 ngay M15 ~ 8.640 bar). |
| `Khong du bars cho walk-forward (EURUSD): can toi thieu 80, chi co 50` | Walk-forward can `train_bars + test_bars` bar/symbol. Giam `train_bars`/`test_bars` hoac backfill them. |
| `File CSV ... thieu cot: close` | File khong phai do `export-bars` xuat (sai cot). Xuat lai bang `export-bars`, khong sua tay cot. |
| `CSV dong N: time khong doc duoc` / `OHLC vo ly` | Dong N trong file loi. Kiem tra file goc tu Windows; khong sua tay gia. |

## Tai lieu lien quan

- `docs/history-store.md` — kho nen, backfill, export-bars.
- `docs/backtest.md` — engine backtest, cach doc bao cao (ap dung ca
  2 nguon du lieu).
- `docs/strategy-engine.md` — so sanh chien luoc, sweep, chong
  overfitting.
- `docs/trading-principles.md` muc 31 — quy tac Phase C.
