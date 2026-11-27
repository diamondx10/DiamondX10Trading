"""Smoke test cho CLI history (tich hop Phase C): import-bars +
backtest/compare/sweep --source history, tren du lieu mo phong
xuat ra CSV roi nhap lai vao kho tam (khong cham data/history.db that).
"""
import diamondx10.__main__ as cli
from diamondx10.__main__ import main
from diamondx10.data.history import HistoryStore


def _patch_store(monkeypatch, tmp_path):
    db = tmp_path / "history.db"

    def _store(cfg):
        return HistoryStore(str(db))

    monkeypatch.setattr(cli, "_history_store", _store)
    return db


def test_import_bars_then_backtest_history(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch, tmp_path)
    out_dir = tmp_path / "exports"
    rc = main(["export-bars", "--desk", "forex", "--from", "simulated",
               "--out", str(out_dir)])
    assert rc in (0, None)
    csv_file = out_dir / "EURUSD_M15.csv"
    assert csv_file.exists()
    rc = main(["import-bars", "--file", str(csv_file), "--symbol", "EURUSD",
               "--timeframe", "M15"])
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert "OK: nhap" in out
    rc = main(["backtest", "--desk", "forex", "--source", "history",
               "--symbol", "EURUSD"])
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert "DU LIEU THAT" in out  # tieu de DU LIEU THAT — MT5 DEMO


def test_backtest_history_empty_store_fails_cleanly(tmp_path, monkeypatch,
                                                   capsys):
    _patch_store(monkeypatch, tmp_path)
    rc = main(["backtest", "--desk", "forex", "--source", "history",
               "--symbol", "EURUSD"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "LOI" in out


def test_compare_history_uses_store(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch, tmp_path)
    out_dir = tmp_path / "exports"
    main(["export-bars", "--desk", "forex", "--from", "simulated",
          "--out", str(out_dir)])
    main(["import-bars", "--file", str(out_dir / "EURUSD_M15.csv"),
          "--symbol", "EURUSD", "--timeframe", "M15"])
    rc = main(["compare", "--desk", "forex", "--source", "history",
               "--symbol", "EURUSD"])
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert "default" in out
