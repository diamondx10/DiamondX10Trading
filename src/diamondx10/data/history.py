"""Kho nen OHLC local bang SQLite — Phase A (MT5-only, xem docs/history-store.md).

Luu nen lay tu MT5 demo vao file SQLite de backtest / kiem dinh tren
du lieu that, thay vi chay lai MT5 moi lan hay dung du lieu mo phong.

- File mac dinh: data/history.db (file RUNTIME — da them vao .gitignore,
  giong data/news-history.db cua tin tuc). Duong dan tuong doi trong
  config (history.db_path) hieu theo goc repo.
- Bang duy nhat `bars`, khoa chinh (symbol, timeframe, time) nen
  backfill lap lai cung khoang thoi gian khong nhan doi bar.
- Chi dung sqlite3 (stdlib), khong them dependency.

Luu y: 'time' la epoch UTC (giay). Volume cua MT5 la tick_volume;
neu nguon khong co volume thi luu 0.0.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Goc repo: file nay o src/diamondx10/data/history.py -> parents[3].
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "history.db"

_CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS bars ("
    "  symbol TEXT NOT NULL,"
    "  timeframe TEXT NOT NULL,"
    "  time INTEGER NOT NULL,"
    "  open REAL NOT NULL,"
    "  high REAL NOT NULL,"
    "  low REAL NOT NULL,"
    "  close REAL NOT NULL,"
    "  volume REAL NOT NULL DEFAULT 0.0,"
    "  PRIMARY KEY (symbol, timeframe, time)"
    ")"
)


def _as_epoch(value):
    """Chuyen int epoch hoac datetime ve int epoch UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    return int(value)


class HistoryStore:
    """Kho nen OHLC: 1 file SQLite, 1 bang `bars`.

    Dung lam context manager (`with HistoryStore(...) as store:`)
    hoac goi close() khi xong.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DEFAULT_DB_PATH
        if not self.path.is_absolute():
            self.path = REPO_ROOT / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=10)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def upsert_bars(self, symbol, timeframe, bars):
        """Ghi (chen hoac ghi de) 1 loat bar.

        bars: list dict {time, open, high, low, close, volume?}.
        Bar trung (symbol, timeframe, time) thi ghi de, khong nhan doi.
        Tra ve so bar da ghi.
        """
        if not symbol:
            raise ValueError("upsert_bars can symbol, vd 'EURUSD'")
        if not timeframe:
            raise ValueError("upsert_bars can timeframe, vd 'M15'")
        rows = []
        for bar in bars or []:
            rows.append((symbol, timeframe, _as_epoch(bar["time"]),
                         float(bar["open"]), float(bar["high"]),
                         float(bar["low"]), float(bar["close"]),
                         float(bar.get("volume") or 0.0)))
        if not rows:
            return 0
        self._conn.executemany(
            "INSERT OR REPLACE INTO bars (symbol, timeframe, time, open,"
            "  high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows)
        self._conn.commit()
        return len(rows)

    def get_bars(self, symbol, timeframe, start=None, end=None, limit=None):
        """Lay bar theo thu tu thoi gian tang dan.

        start/end: epoch int hoac datetime (loc time >= start,
        time <= end). limit: toi da N bar. Tra list dict
        {time, open, high, low, close, volume}.
        """
        sql = ("SELECT time, open, high, low, close, volume FROM bars"
               " WHERE symbol = ? AND timeframe = ?")
        params = [symbol, timeframe]
        if start is not None:
            sql += " AND time >= ?"
            params.append(_as_epoch(start))
        if end is not None:
            sql += " AND time <= ?"
            params.append(_as_epoch(end))
        sql += " ORDER BY time ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"time": int(r[0]), "open": float(r[1]),
                 "high": float(r[2]), "low": float(r[3]),
                 "close": float(r[4]), "volume": float(r[5])}
                for r in rows]

    def latest_time(self, symbol, timeframe):
        """Epoch cua bar moi nhat; None neu chua co bar nao."""
        row = self._conn.execute(
            "SELECT MAX(time) FROM bars WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def count(self, symbol, timeframe):
        """So bar da luu cho (symbol, timeframe)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe)).fetchone()
        return int(row[0]) if row else 0

    def coverage(self, symbol, timeframe):
        """Do phu cua kho: {count, start, end}.

        start/end la epoch UTC cua bar dau/cuoi; None khi chua co bar.
        """
        row = self._conn.execute(
            "SELECT COUNT(*), MIN(time), MAX(time) FROM bars"
            " WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe)).fetchone()
        if not row or not row[0]:
            return {"count": 0, "start": None, "end": None}
        return {"count": int(row[0]), "start": int(row[1]),
                "end": int(row[2])}
