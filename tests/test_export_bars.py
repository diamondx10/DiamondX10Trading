"""Test export-bars — xuat CSV tu kho / MT5 gia / mo phong."""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import main, run_export_bars
from diamondx10.data.history import HistoryStore

NOW = datetime(2026, 11, 27, 0, 0, 0, tzinfo=timezone.utc)
BASE = 1795000000  # nam trong 30 ngay truoc NOW
COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def make_bars(n=6, start=BASE, step=900):
    return [{"time": start + i * step, "open": 100.0 + i,
             "high": 101.0 + i, "low": 99.0 + i, "close": 100.5 + i,
             "volume": 5.0 + i}
            for i in range(n)]


class FakeFeed:
    def __init__(self, bars):
        self._bars = list(bars)

    def bars_range(self, timeframe, start, end):
        lo, hi = int(start.timestamp()), int(end.timestamp())
        return [b for b in self._bars if lo <= b["time"] <= hi]

    def close(self):
        pass


def _cfg(tmp_path):
    return {"data": {"provider": "simulated",
                     "symbols": {"forex": ["EURUSD"],
                                 "crypto": ["BTCUSD"]}},
            "mt5": {"login": 123, "server": "Exness-MT5Trial7"},
            "history": {"db_path": str(tmp_path / "history.db"),
                        "default_timeframe": "M15", "backfill_days": 30}}


def _read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COLUMNS
        return list(reader)


def test_export_from_store(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    with HistoryStore(tmp_path / "history.db") as store:
        store.upsert_bars("EURUSD", "M15", make_bars(6))
        out = tmp_path / "exports"
        result = run_export_bars(cfg, ["EURUSD"], "M15", 30, out,
                                 "store", store=store, now=NOW)
    assert result["failed"] == 0
    assert result["results"][0]["source"] == "store"
    assert result["results"][0]["bars"] == 6
    csv_path = out / "EURUSD_M15.csv"
    rows = _read_csv(csv_path)
    assert len(rows) == 6
    assert rows[0]["time"] == "2026-11-18T11:06:40Z"  # BASE = epoch UTC
    assert rows[0]["close"] == "100.5"
    assert rows[0]["volume"] == "5.0"
    out_text = capsys.readouterr().out
    assert "EURUSD: 6 bar M15" in out_text and "nguon: store" in out_text


def test_export_store_empty_falls_back_to_mt5(tmp_path, capsys):
    # Kho trong: export --from store tu keo MT5 live, luu vao kho,
    # ghi ro nguon "mt5 (fallback)" trong output.
    cfg = _cfg(tmp_path)
    feed = FakeFeed(make_bars(4))
    with HistoryStore(tmp_path / "history.db") as store:
        out = tmp_path / "exports"
        result = run_export_bars(cfg, ["EURUSD"], "M15", 30, out,
                                 "store", store=store,
                                 feed_factory=lambda s: feed, now=NOW)
    assert result["failed"] == 0
    assert result["results"][0]["source"] == "mt5 (fallback)"
    assert (tmp_path / "exports" / "EURUSD_M15.csv").exists()
    with HistoryStore(tmp_path / "history.db") as store:
        assert store.count("EURUSD", "M15") == 4
    assert "mt5 (fallback)" in capsys.readouterr().out


def test_export_from_mt5_always_live(tmp_path):
    cfg = _cfg(tmp_path)
    feed = FakeFeed(make_bars(5))
    with HistoryStore(tmp_path / "history.db") as store:
        # Kho da co bar cu: --from mt5 van keo live (ghi de bang bar moi).
        store.upsert_bars("EURUSD", "M15", make_bars(2))
        out = tmp_path / "exports"
        result = run_export_bars(cfg, ["EURUSD"], "M15", 30, out,
                                 "mt5", store=store,
                                 feed_factory=lambda s: feed, now=NOW)
    assert result["results"][0]["source"] == "mt5"
    assert result["results"][0]["bars"] == 5
    with HistoryStore(tmp_path / "history.db") as store:
        assert store.count("EURUSD", "M15") == 5


def test_export_simulated_labels_source(tmp_path, capsys):
    # --from simulated chi khi user truyen ro: CSV tu SimulatedFeed,
    # time ISO UTC, ghi ro nguon simulated (KHONG phai gia that).
    cfg = _cfg(tmp_path)
    with HistoryStore(tmp_path / "history.db") as store:
        out = tmp_path / "exports"
        result = run_export_bars(cfg, ["EURUSD"], "M15", 30, out,
                                 "simulated", store=store, now=NOW)
    assert result["failed"] == 0
    assert result["results"][0]["source"] == "simulated"
    rows = _read_csv(out / "EURUSD_M15.csv")
    assert len(rows) == 500  # SimulatedFeed co 500 bar
    assert rows[-1]["time"] == "2026-11-27T00:00:00Z"  # bar cuoi o `now`
    assert rows[0]["time"] < rows[-1]["time"]
    assert "nguon: simulated" in capsys.readouterr().out


def test_export_store_empty_without_mt5_skips_cleanly(tmp_path, capsys):
    # Kho trong + khong co MT5 (may Linux): canh bao tung symbol,
    # khong crash, khong tao CSV rong.
    cfg = _cfg(tmp_path)
    with HistoryStore(tmp_path / "history.db") as store:
        out = tmp_path / "exports"
        result = run_export_bars(cfg, ["EURUSD"], "M15", 30, out,
                                 "store", store=store, now=NOW)
    assert result["failed"] == 1 and result["results"] == []
    assert not (out / "EURUSD_M15.csv").exists()
    out_text = capsys.readouterr().out
    assert "CANH BAO (EURUSD)" in out_text
    assert "Traceback" not in out_text


def test_main_export_bars_simulated_smoke(tmp_path, monkeypatch, capsys):
    # Smoke qua CLI that: export-bars --from simulated chay duoc
    # tren may khong co MT5.
    monkeypatch.setattr("diamondx10.__main__.load_config",
                        lambda: _cfg(tmp_path))
    out = tmp_path / "exports"
    # main() tra None khi thanh cong (giong cac lenh cu: demo/backtest),
    # tra 1 khi loi.
    assert main(["export-bars", "--symbol", "EURUSD", "--from",
                 "simulated", "--out", str(out)]) in (None, 0)
    rows = _read_csv(out / "EURUSD_M15.csv")
    assert len(rows) == 500
    assert "simulated" in capsys.readouterr().out
