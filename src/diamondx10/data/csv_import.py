"""Import nen OHLC tu file CSV vao kho lich su — Phase C.

Cau noi cho workflow: Phu chay `export-bars` tren may Windows
(MT5 demo) -> gui CSV cho Muse -> Muse import vao kho SQLite
(`HistoryStore`) -> backtest tren du lieu that (xem
`docs/real-data-backtest.md`).

Dinh dang CSV dung nhu `export-bars` xuat (`__main__._write_bars_csv`):
1 dong/symbol, cot `time,open,high,low,close,volume`, `time` la ISO UTC
(vd `2026-11-27T00:00:00Z`). Chi dung stdlib + `HistoryStore`.

- Bar trung (symbol, timeframe, time) da co trong kho thi BO QUA,
  khong nhan doi (dem vao `skipped`); chi bar moi duoc ghi.
- Bar trung nhau trong chinh file CSV thi chi lay ban ghi CUOI cung
  (ban ghi trung truoc do cung dem vao `skipped`).
- File sai cot / gia tri khong doc duoc / OHLC vo ly thi ValueError
  neu ro so dong — khong ghi nua chung roi moi bao loi: doc + kiem
  tra HET truoc khi ghi bat ky bar nao.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close")
OPTIONAL_COLUMNS = ("volume",)


def _parse_time(value, line_no):
    """Cot time cua CSV -> epoch UTC (int).

    Chap nhan ISO UTC (`2026-11-27T00:00:00Z`, `...+00:00`, khong
    mui gio thi hieu la UTC) va epoch giay dang so (de phong file
    xuat bang tay). Khong doc duoc thi ValueError neu so dong.
    """
    text = str(value).strip()
    if not text:
        raise ValueError(f"CSV dong {line_no}: cot time rong")
    if text.lstrip("-").isdigit():
        return int(text)
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        raise ValueError(
            f"CSV dong {line_no}: time khong doc duoc: {value!r} "
            "(can ISO UTC, vd 2026-11-27T00:00:00Z)") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _parse_float(value, column, line_no):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(
            f"CSV dong {line_no}: cot {column} khong phai so: "
            f"{value!r}") from None


def import_csv_bars(store, path, symbol, timeframe):
    """Doc file CSV cua `export-bars` va upsert vao kho.

    store: `HistoryStore` da mo. path: duong dan file CSV. symbol /
    timeframe: symbol + khung nen cua file (1 file = 1 symbol +
    1 khung, ten file `{SYMBOL}_{TIMEFRAME}.csv`).
    Tra dict: {symbol, timeframe, path, imported, skipped,
    total_rows, start, end} — `imported` la so bar moi da ghi,
    `skipped` la so bar bo qua vi trung (da co trong kho hoac lap
    trong file), `start`/`end` la epoch UTC cua bar dau/cuoi trong
    file (None neu file khong co bar nao).
    """
    if not symbol:
        raise ValueError("import_csv_bars can symbol, vd 'EURUSD'")
    if not timeframe:
        raise ValueError("import_csv_bars can timeframe, vd 'M15'")
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Khong tim thay file CSV: {path}")
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"File CSV rong (khong co dong tieu de): {path}")
        header = [h.strip() if h else h for h in reader.fieldnames]
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise ValueError(
                f"File CSV {path} thieu cot: {', '.join(missing)} "
                f"(can: {', '.join(REQUIRED_COLUMNS)}; "
                f"hien co: {', '.join(header)})")
        by_time = {}
        intra_file_dupes = 0
        for line_no, row in enumerate(reader, start=2):
            if row is None or all(
                    v is None or str(v).strip() == ""
                    for v in row.values()):
                continue  # bo dong trong
            epoch = _parse_time(row["time"], line_no)
            bar = {"time": epoch,
                   "open": _parse_float(row["open"], "open", line_no),
                   "high": _parse_float(row["high"], "high", line_no),
                   "low": _parse_float(row["low"], "low", line_no),
                   "close": _parse_float(row["close"], "close", line_no),
                   "volume": _parse_float(row["volume"], "volume", line_no)
                   if row.get("volume") not in (None, "") else 0.0}
            if (bar["high"] < max(bar["open"], bar["close"])
                    or bar["low"] > min(bar["open"], bar["close"])):
                raise ValueError(
                    f"CSV dong {line_no}: OHLC vo ly (high {bar['high']} "
                    f"thap hon open/close, hoac low {bar['low']} cao hon "
                    "open/close)")
            if epoch in by_time:
                intra_file_dupes += 1
            by_time[epoch] = bar  # trung trong file: ban ghi sau thang
    bars = [by_time[t] for t in sorted(by_time)]
    existing = {b["time"] for b in store.get_bars(symbol, timeframe)}
    new_bars = [b for b in bars if b["time"] not in existing]
    skipped = len(bars) - len(new_bars) + intra_file_dupes
    if new_bars:
        store.upsert_bars(symbol, timeframe, new_bars)
    return {"symbol": symbol,
            "timeframe": timeframe,
            "path": str(path),
            "imported": len(new_bars),
            "skipped": skipped,
            # Tong so dong du lieu da doc = bar moi + bar bo qua
            # (gom ca bar lap trong file).
            "total_rows": len(new_bars) + skipped,
            "start": bars[0]["time"] if bars else None,
            "end": bars[-1]["time"] if bars else None}
