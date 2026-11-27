"""Test dashboard web chi doc (Phase E).

Kiem tra: build_dashboard_data doc state/log gia trong tmp, server
tra 200 + du cac muc chinh, thieu/hong file state thi trang van 200
va co chu "chua co du lieu", GET / khong lam thay doi file state.
"""
import csv
import hashlib
import json
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from diamondx10 import decisions
from diamondx10.dashboard import (
    build_dashboard_data,
    create_server,
    render_dashboard,
)
from diamondx10.data.history import HistoryStore

CFG = {
    "fund": {"total_capital_usd": 10000, "desks": {
        "forex": {"manager": "Yuling Pan", "capital_usd": 2500},
        "xauusd": {"manager": "Yumi", "capital_usd": 2500},
        "crypto": {"manager": "Rich", "capital_usd": 2500},
        "us_securities": {"manager": "Kathy", "capital_usd": 2500}}},
    "risk": {"max_drawdown_pct": 10.0, "desk_warning_pct": 5.0},
    "history": {"db_path": "data/history.db", "default_timeframe": "M15"},
}

LOG_ROWS = [
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "BUY", "reason": "lenh 1", "manager": "Yuling Pan"},
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "BLOCKED-DAILY-LIMIT", "reason": "da dat 1 lenh hom nay",
     "manager": "Yuling Pan"},
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "CLOSE", "reason": "Dong BUY EURUSD @ 1.10 P&L 25.00 USD (TP)",
     "manager": "Yuling Pan"},
    {"date": "2026-11-26", "desk": "crypto", "symbol": "BTCUSD",
     "action": "SELL", "reason": "lenh hom qua", "manager": "Rich"},
]


def _write_log(tmp_path):
    path = tmp_path / "decisions-log.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=decisions.HEADER)
        w.writeheader()
        w.writerows(LOG_ROWS)
    return path


def _write_state(tmp_path):
    state = {
        "guard": {
            "fund_capital": 10000.0,
            "desk_capitals": {"forex": 2500.0, "xauusd": 2500.0,
                              "crypto": 2500.0, "us_securities": 2500.0},
            "max_drawdown_pct": 10.0,
            "desk_warning_pct": 5.0,
            "fund_curve": [10000.0, 10025.0],
            "desk_curves": {"forex": [2500.0, 2525.0],
                            "xauusd": [2500.0],
                            "crypto": [2500.0],
                            "us_securities": [2500.0]},
        },
        "positions": [{
            "desk": "forex", "symbol": "EURUSD", "direction": "BUY",
            "entry": 1.08, "sl": 1.07, "tp": 1.10, "volume": 0.01,
            "contract_size": 100000.0, "atr": 0.001,
            "opened_date": "2026-11-27"}],
    }
    path = tmp_path / "equity-state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    return path


def _write_history(tmp_path):
    """Kho lich su gia: EURUSD dong nen moi nhat 1.10."""
    path = tmp_path / "history.db"
    with HistoryStore(str(path)) as store:
        store.upsert_bars("EURUSD", "M15", [
            {"time": 1790000000, "open": 1.09, "high": 1.11,
             "low": 1.08, "close": 1.10, "volume": 100.0}])
    return path


def _build(tmp_path):
    log = _write_log(tmp_path)
    state = _write_state(tmp_path)
    hist = _write_history(tmp_path)
    data = build_dashboard_data(
        CFG, state_path=state, log_path=log, history_db_path=hist,
        backtest_result_path=tmp_path / "khong-co.json",
        today="2026-11-27")
    return data, log, state, hist


def test_build_dashboard_data_fake_state(tmp_path):
    data, _, _, _ = _build(tmp_path)
    assert data["has_state"] is True
    assert data["fund"]["equity"] == 10025.0
    assert data["fund"]["pnl"] == 25.0
    assert data["desks"]["forex"]["equity"] == 2525.0
    # Vi the mo + P&L chua thuc hien theo gia kho moi nhat (1.10):
    # (1.10 - 1.08) * 0.01 lot * 100000 = 20 USD.
    assert len(data["positions"]) == 1
    pos = data["positions"][0]
    assert pos["symbol"] == "EURUSD" and pos["direction"] == "BUY"
    assert pos["latest_price"] == 1.10
    assert pos["unrealized_pnl"] == pytest.approx(20.0)
    # P&L hom nay rut tu dong CLOSE trong log.
    assert data["pnl_today"] == 25.0
    assert data["daily_pnl"] == {"2026-11-27": 25.0}
    # Tin hieu gan nhat: doc tu log, moi nhat len dau.
    assert data["recent_signals"][0]["action"] == "SELL"  # dong cuoi file
    assert data["recent_signals"][-1]["action"] == "BUY"
    # Rui ro desk forex: 1 lenh moi + 1 lan bi chan hom nay.
    risk = data["risk"]["forex"]
    assert risk["trades_today"] == 1
    assert risk["blocked_today"] == 1
    assert risk["can_open"] is True
    # Chua co file ket qua backtest.
    assert data["backtest"] is None


def test_build_dashboard_data_backtest_file(tmp_path):
    _, log, state, hist = _build(tmp_path)
    result_path = tmp_path / "backtest-latest.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "desk": "forex", "strategy": "SMA+RSI+ATR",
            "simulated": False, "source": "history",
            "timeframe": "M15", "n_bars": 8640,
            "symbols": ["EURUSD"],
            "metrics": {"total_return_pct": 2.5, "win_rate": 60.0,
                        "max_drawdown_pct": 1.2, "n_trades": 10,
                        "total_pnl": 62.5, "sharpe": 1.1},
            "segments": {"test": {"metrics": {
                "total_return_pct": 1.0, "n_trades": 4}}},
        }, f)
    data = build_dashboard_data(
        CFG, state_path=state, log_path=log, history_db_path=hist,
        backtest_result_path=result_path, today="2026-11-27")
    bt = data["backtest"]
    assert bt is not None
    assert bt["desk"] == "forex" and bt["simulated"] is False
    assert bt["total_return_pct"] == 2.5
    assert bt["test_return_pct"] == 1.0


def _serve_in_thread(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_server_get_root_200(tmp_path):
    _, log, state, hist = _build(tmp_path)
    server = create_server("127.0.0.1", 0, cfg=CFG, state_path=state,
                           log_path=log, history_db_path=hist,
                           backtest_result_path=tmp_path / "khong-co.json")
    _serve_in_thread(server)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=10) as resp:
            assert resp.status == 200
            page = resp.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
    for section in ("Vị thế đang mở", "Vốn", "Tín hiệu / lệnh gần nhất",
                    "Kết quả backtest gần nhất",
                    "Trạng thái rủi ro từng desk"):
        assert section in page
    assert "EURUSD" in page
    assert "20.00" in page  # P&L chua thuc hien uoc tinh


def test_server_missing_state_still_200(tmp_path):
    log = _write_log(tmp_path)
    server = create_server("127.0.0.1", 0, cfg=CFG,
                           state_path=tmp_path / "khong-co-state.json",
                           log_path=log,
                           history_db_path=tmp_path / "khong-co.db",
                           backtest_result_path=tmp_path / "khong-co.json")
    _serve_in_thread(server)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=10) as resp:
            assert resp.status == 200
            page = resp.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
    assert "chưa có dữ liệu" in page


def test_server_corrupt_state_still_200(tmp_path):
    log = _write_log(tmp_path)
    bad_state = tmp_path / "equity-state.json"
    bad_state.write_text("{json hong", encoding="utf-8")
    data = build_dashboard_data(
        CFG, state_path=bad_state, log_path=log,
        history_db_path=tmp_path / "khong-co.db",
        backtest_result_path=tmp_path / "khong-co.json",
        today="2026-11-27")
    assert data["has_state"] is False
    assert "chưa có dữ liệu" in render_dashboard(data)


def test_server_get_twice_does_not_change_state(tmp_path):
    _, log, state, hist = _build(tmp_path)
    before = hashlib.sha256(state.read_bytes()).hexdigest()
    log_before = hashlib.sha256(log.read_bytes()).hexdigest()
    server = create_server("127.0.0.1", 0, cfg=CFG, state_path=state,
                           log_path=log, history_db_path=hist,
                           backtest_result_path=tmp_path / "khong-co.json")
    _serve_in_thread(server)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        for _ in range(2):
            with urllib.request.urlopen(url, timeout=10) as resp:
                assert resp.status == 200
                resp.read()
    finally:
        server.shutdown()
        server.server_close()
    assert hashlib.sha256(state.read_bytes()).hexdigest() == before
    assert hashlib.sha256(log.read_bytes()).hexdigest() == log_before
