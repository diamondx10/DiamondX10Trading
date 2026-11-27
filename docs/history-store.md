# Kho nen OHLC local — Phase A (MT5-only)

Backtest va kiem dinh chien luoc can **du lieu that**, khong phai du lieu
mo phong. Phase A luu nen OHLC lay tu MT5 demo vao 1 file SQLite local
de chay lai backtest bat ky luc nao ma khong can mo MT5 moi lan.

> Quy tac da chot (khong doi): **MT5 cho tat ca**, crypto la cap USD
> (BTCUSD/ETHUSD/BNBUSD), **khong Binance**. Chi tai khoan DEMO.

## Kho luu o dau

| Thu | Vi tri |
|---|---|
| File kho | `data/history.db` (SQLite, file RUNTIME — da gitignore, khong commit) |
| Cau hinh | muc `history:` trong `config.example.yaml` / `config.yaml` local |
| Code | `src/diamondx10/data/history.py` (`HistoryStore`) |
| CSV xuat ra | `data/exports/` (mac dinh, da gitignore) |

```yaml
# config.example.yaml
history:
  db_path: data/history.db
  default_timeframe: M15
  backfill_days: 90
```

`db_path` tuong doi hieu theo goc repo. Khong truyen `--timeframe` /
`--days` thi lenh dung `default_timeframe` / `backfill_days` o tren.

## Schema

1 bang duy nhat `bars`:

```sql
CREATE TABLE bars (
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  time INTEGER NOT NULL,          -- epoch UTC (giay)
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL DEFAULT 0.0,  -- tick_volume cua MT5
  PRIMARY KEY (symbol, timeframe, time)
);
```

Khoa chinh `(symbol, timeframe, time)` nen backfill lap lai cung khoang
thoi gian chi **ghi de, khong nhan doi bar**.

`HistoryStore` (stdlib `sqlite3`, dung duoc lam context manager):

- `upsert_bars(symbol, timeframe, bars)` — ghi 1 loat bar, tra so bar da ghi.
- `get_bars(symbol, timeframe, start=None, end=None, limit=None)` —
  list dict `{time, open, high, low, close, volume}` theo thu tu thoi gian.
- `latest_time(symbol, timeframe)` / `count(symbol, timeframe)` /
  `coverage(symbol, timeframe)` — `{count, start, end}` (epoch UTC).

## Backfill tu MT5 (chay tren may Windows co MT5 terminal)

```bash
pip install MetaTrader5   # chi tren may chay MT5 terminal (Windows)
python -m diamondx10 backfill --desk forex --timeframe M15 --days 30
python -m diamondx10 backfill --symbol XAUUSD --timeframe H1 --days 90
python -m diamondx10 backfill   # mac dinh: ca 10 symbol, M15, 90 ngay
```

- Khung nen ho tro: M1, M5, **M15, H1, D1** (mac dinh M15).
- Lay bar qua `MT5Feed.bars_range()` (`copy_rates_range` cua MT5) trong
  N ngay gan nhat, ghi vao kho. Moi symbol in 1 dong: so bar lay duoc /
  so bar da luu. Symbol loi (mat ket noi, symbol khong co tren server
  demo) thi in `LOI (SYMBOL): ...` va chay tiep symbol khac; cuoi lenh
  tra exit code 1 neu co symbol loi.
- Tren may khong co MT5 (vd may Linux nay) lenh bao loi sach va dung:
  `LOI: Chua cai goi MetaTrader5. Cai tren may chay MT5 terminal
  (Windows): pip install MetaTrader5 ...` — khong in traceback.
- Backfill **khong dat lenh**, chi doc du lieu. Tai khoan demo van
  ap dung quy tac chung (mat khau qua `MT5_PASSWORD`, xem
  `docs/mt5-demo.md`).

## Xuat CSV de backtest

```bash
python -m diamondx10 export-bars --desk crypto --timeframe M15 --days 30
python -m diamondx10 export-bars --symbol EURUSD --timeframe H1 --days 90 --out data/exports/
python -m diamondx10 export-bars --symbol BTCUSD --from mt5 --days 30
python -m diamondx10 export-bars --symbol EURUSD --from simulated --days 30  # chi de demo/test
```

- 1 file CSV cho moi symbol: `{SYMBOL}_{TIMEFRAME}.csv`, cot
  `time,open,high,low,close,volume`; `time` la ISO UTC
  (vd `2026-11-27T00:00:00Z`). Thu muc `--out` tu tao neu chua co
  (mac dinh `data/exports/`).
- Nguon du lieu (`--from`), mac dinh `store`:
  - `store` — xuat tu kho; symbol nao **chua co bar trong kho** thi thu
    keo 1 lan tu MT5 live roi luu vao kho (in nguon `mt5 (fallback)`).
    Neu MT5 cung khong co thi canh bao va bo qua symbol do.
  - `mt5` — luon keo tu MT5 live roi luu vao kho (lam moi kho).
  - `simulated` — du lieu mo phong (toi da 500 bar, moc thoi gian gan
    lai de bar cuoi o thoi diem chay). **Chi khi user truyen ro**;
    output luon ghi ro `nguon: simulated` — khong phai gia that,
    khong dung de ra quyet dinh.
- Moi symbol in 1 dong tom tat: so bar, khoang thoi gian, nguon du lieu,
  duong dan file.

## Cach Muse dung CSV de backtest

1. Phu chay `backfill` tren may Windows (MT5 demo dang mo), roi chay
   `export-bars` (mac dinh `--from store`) de co CSV that cho symbol
   can kiem dinh.
2. Phu gui CSV cho Muse (hoac Muse doc truc tiep neu co quyen doc file).
   Moi file la 1 symbol + 1 khung nen, cot `time` ISO UTC nen doc duoc
   ngay ma khong can doi epoch.
3. Muse chay backtest tren CSV that thay cho `SimulatedFeed` (Phase C);
   den khi Phase C xong, CSV dung de kiem tra thu cong / tinh ATR that
   (can cho viec ha rui ro desk vang xuong 2–3% — xem
   `docs/trading-principles.md` muc 8).

## Gioi han da biet

- Chua co lenh dong bo tang dan (incremental sync): backfill ghi de
  toan bo khoang `--days` moi lan (nho khoa chinh nen khong nhan doi).
- Volume la `tick_volume` cua MT5, khong phai khoi luong giao dich that
  cua san.
- Chua co co che xoa bar cu / gioi han dung luong file DB.
- Chay that lan dau tien phai o may Windows cua Phu (MT5 terminal +
  tai khoan demo Exness); tren Linux chi test duoc bang MT5 gia.
