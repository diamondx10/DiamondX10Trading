"""Test import CSV vao kho (Phase C) — file CSV mau do chinh
`export-bars` tao ra, import 2 lan khong nhan doi, time ISO parse
dung, file sai cot bao loi.
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import run_export_bars
from diamondx10.backtest import run_backtest_from_history
from diamondx10.config import DEFAULT
from diamondx10.data.csv_import import import_csv_bars
from diamondx10.data.history import HistoryStore
import copy

NOW = datetime(2026, 11, 27, 0, 0, 0, tzinfo=timezone.utc)
COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def _cfg(tmp_path):
    return {"data": {"provider": "simulated",
                     "symbols": {"forex": ["EURUSD"]}},
            "mt5": {"login": 123, "server": "Exness-MT5Trial7"},
            "history": {"db_path": str(tmp_path / "history.db"),
                        "default_timeframe": "M15", "backfill_days": 30}}


def _export_simulated_csv(tmp_path):
    """CSV mau do export-bars tao (nguon simulated, chi de test):
    500 bar M15, bar cuoi o NOW."""
    cfg = _cfg(tmp_path)
    out = tmp_path / "exports"
    result = run_export_bars(cfg, ["EURUSD"], "M15", 30, out,
                             "simulated", now=NOW)
    assert len(result["results"]) == 1
    return Path(result["results"][0]["path"])


def _read_csv_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COLUMNS
        return list(reader)


def test_import_then_reimport_does_not_double(tmp_path):
    csv_path = _export_simulated_csv(tmp_path)
    with HistoryStore(tmp_path / "history.db") as store:
        first = import_csv_bars(store, csv_path, "EURUSD", "M15")
        assert first["imported"] == 500
        assert first["skipped"] == 0
        assert first["total_rows"] == 500
        assert store.count("EURUSD", "M15") == 500
        second = import_csv_bars(store, csv_path, "EURUSD", "M15")
        assert second["imported"] == 0
        assert second["skipped"] == 500
        assert second["total_rows"] == 500
        assert store.count("EURUSD", "M15") == 500


def test_import_iso_time_parsed_to_epoch(tmp_path):
    csv_path = _export_simulated_csv(tmp_path)
    rows = _read_csv_rows(csv_path)
    first_iso = rows[0]["time"]
    last_iso = rows[-1]["time"]
    assert first_iso.endswith("Z")  # dinh dang cua export-bars
    with HistoryStore(tmp_path / "history.db") as store:
        result = import_csv_bars(store, csv_path, "EURUSD", "M15")
        bars = store.get_bars("EURUSD", "M15")
    first_epoch = int(datetime.fromisoformat(
        first_iso.replace("Z", "+00:00")).timestamp())
    last_epoch = int(datetime.fromisoformat(
        last_iso.replace("Z", "+00:00")).timestamp())
    assert result["start"] == first_epoch == bars[0]["time"]
    assert result["end"] == last_epoch == bars[-1]["time"]
    assert bars[0]["close"] == pytest.approx(float(rows[0]["close"]))
    # Bar cuoi o NOW (export simulated gan lai moc thoi gian).
    assert last_epoch == int(NOW.timestamp())


def test_import_duplicate_row_inside_file_kept_last(tmp_path):
    csv_path = _export_simulated_csv(tmp_path)
    rows = _read_csv_rows(csv_path)
    # Trung time voi dong dau, close khac nhung van trong [low, high].
    dup = dict(rows[0], close=rows[0]["open"])
    dup_path = tmp_path / "dup.csv"
    with open(dup_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(dup)  # trung time voi dong dau, close khac
    with HistoryStore(tmp_path / "history.db") as store:
        result = import_csv_bars(store, dup_path, "EURUSD", "M15")
        bars = store.get_bars("EURUSD", "M15")
    assert result["total_rows"] == 501
    assert result["imported"] == 500
    assert result["skipped"] == 1
    assert bars[0]["close"] == pytest.approx(float(rows[0]["open"]))


def test_import_missing_column_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    with open(bad, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low"])  # thieu close
        writer.writerow(["2026-11-27T00:00:00Z", 100, 101, 99])
    with HistoryStore(tmp_path / "history.db") as store:
        with pytest.raises(ValueError, match="thieu cot: close"):
            import_csv_bars(store, bad, "EURUSD", "M15")
        assert store.count("EURUSD", "M15") == 0  # khong ghi nua chung


def test_import_bad_time_and_bad_ohlc_raise(tmp_path):
    bad_time = tmp_path / "bad-time.csv"
    with open(bad_time, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerow(["khong-phai-ngay", 100, 101, 99, 100.5, 5])
    bad_ohlc = tmp_path / "bad-ohlc.csv"
    with open(bad_ohlc, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerow(["2026-11-27T00:00:00Z", 100, 99, 98, 100.5, 5])
    with HistoryStore(tmp_path / "history.db") as store:
        with pytest.raises(ValueError, match="time khong doc duoc"):
            import_csv_bars(store, bad_time, "EURUSD", "M15")
        with pytest.raises(ValueError, match="OHLC vo ly"):
            import_csv_bars(store, bad_ohlc, "EURUSD", "M15")
        assert store.count("EURUSD", "M15") == 0


def test_import_missing_file_raises(tmp_path):
    with HistoryStore(tmp_path / "history.db") as store:
        with pytest.raises(ValueError, match="Khong tim thay file CSV"):
            import_csv_bars(store, tmp_path / "khong-co.csv",
                            "EURUSD", "M15")


def test_imported_csv_feeds_backtest_from_history(tmp_path):
    # Workflow tron vong: export-bars -> import -> backtest tu kho.
    csv_path = _export_simulated_csv(tmp_path)
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.02, "slippage_pct": 0.01}
    with HistoryStore(tmp_path / "history.db") as store:
        import_csv_bars(store, csv_path, "EURUSD", "M15")
        result = run_backtest_from_history("forex", cfg,
                                           symbols=["EURUSD"], store=store)
    assert result["simulated"] is False
    assert result["n_bars"] == 500
    assert result["n_bars_by_symbol"] == {"EURUSD": 500}
