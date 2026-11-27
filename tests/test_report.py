"""Test bao cao hang ngay (Phase 5): doc decisions log + equity state."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.report import build_report, format_report


CFG = {
    "fund": {"total_capital_usd": 10000, "desks": {
        "forex": {"manager": "Yuling Pan", "capital_usd": 2500},
        "xauusd": {"manager": "Yumi", "capital_usd": 2500},
        "crypto": {"manager": "Rich", "capital_usd": 2500},
        "us_securities": {"manager": "Kathy", "capital_usd": 2500}}},
    "risk": {"max_drawdown_pct": 10.0, "desk_warning_pct": 5.0},
}

LOG_ROWS = [
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "BUY", "reason": "lenh 1", "manager": "Yuling Pan"},
    {"date": "2026-11-27", "desk": "xauusd", "symbol": "XAUUSD",
     "action": "SELL", "reason": "lenh 2", "manager": "Yumi"},
    {"date": "2026-11-27", "desk": "crypto", "symbol": "BTCUSD",
     "action": "BLOCKED-DAILY-LIMIT", "reason": "da dat 1 lenh hom nay",
     "manager": "Rich"},
    {"date": "2026-11-26", "desk": "forex", "symbol": "EURUSD",
     "action": "BUY", "reason": "lenh hom qua", "manager": "Yuling Pan"},
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "CLOSE", "reason": "Dong BUY EURUSD @ 1.10 P&L 25.00 USD (TP)",
     "manager": "Yuling Pan"},
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
            # Quy: 10000 -> 9900 -> 9850 (DD lon nhat 1,5%).
            "fund_curve": [10000.0, 9900.0, 9850.0],
            # Forex: 2500 -> 2400 (DD 4%, duoi canh bao 5%).
            # Vang: 2500 -> 2300 (DD 8%, tren canh bao 5% -> chan desk).
            "desk_curves": {
                "forex": [2500.0, 2400.0],
                "xauusd": [2500.0, 2300.0],
                "crypto": [2500.0],
                "us_securities": [2500.0],
            },
        },
        "positions": [
            {"desk": "forex", "symbol": "EURUSD", "direction": "BUY",
             "entry": 1.10, "sl": 1.09, "tp": 1.12, "volume": 0.01,
             "contract_size": 100000, "atr": 0.001,
             "opened_date": "2026-11-27"},
        ],
    }
    path = tmp_path / "equity-state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    return path


def test_report_equity_and_drawdown(tmp_path):
    rep = build_report(CFG, log_path=_write_log(tmp_path),
                       state_path=_write_state(tmp_path),
                       today="2026-11-27")
    assert rep["has_state"] is True
    assert rep["fund"]["equity"] == 9850.0
    assert rep["fund"]["pnl"] == -150.0
    assert rep["fund"]["max_dd_pct"] == 1.5
    assert rep["fund"]["blocked"] is False
    assert rep["desks"]["forex"]["equity"] == 2400.0
    assert rep["desks"]["forex"]["max_dd_pct"] == 4.0
    assert rep["desks"]["forex"]["blocked"] is False
    assert rep["desks"]["xauusd"]["max_dd_pct"] == 8.0
    assert rep["desks"]["xauusd"]["blocked"] is True


def test_report_trades_today_and_blocked(tmp_path):
    rep = build_report(CFG, log_path=_write_log(tmp_path),
                       state_path=_write_state(tmp_path),
                       today="2026-11-27")
    # Chi dem lenh that BUY/SELL trong ngay; lenh hom qua khong dem,
    # BLOCKED/CLOSE khong dem.
    assert rep["trades_today"] == {"EURUSD": 1, "XAUUSD": 1}
    assert rep["totals"]["trades"] == 3  # 2 hom nay + 1 hom qua
    assert rep["totals"]["closes"] == 1
    assert rep["totals"]["blocked"] == 1
    assert len(rep["blocked"]) == 1
    assert rep["blocked"][0]["action"] == "BLOCKED-DAILY-LIMIT"
    assert len(rep["open_positions"]) == 1
    assert rep["open_positions"][0]["symbol"] == "EURUSD"


def test_report_without_state_file(tmp_path):
    log = _write_log(tmp_path)
    rep = build_report(CFG, log_path=log,
                       state_path=tmp_path / "khong-co.json",
                       today="2026-11-27")
    assert rep["has_state"] is False
    assert rep["fund"]["equity"] == 10000.0
    assert rep["fund"]["max_dd_pct"] == 0.0
    assert rep["open_positions"] == []
    assert rep["trades_today"] == {"EURUSD": 1, "XAUUSD": 1}


def test_report_without_log_file(tmp_path):
    rep = build_report(CFG, log_path=tmp_path / "khong-co.csv",
                       state_path=_write_state(tmp_path),
                       today="2026-11-27")
    assert rep["trades_today"] == {}
    assert rep["totals"] == {"trades": 0, "closes": 0, "blocked": 0}
    assert rep["fund"]["equity"] == 9850.0


def test_format_report_contains_key_lines(tmp_path):
    rep = build_report(CFG, log_path=_write_log(tmp_path),
                       state_path=_write_state(tmp_path),
                       today="2026-11-27")
    text = format_report(rep)
    assert "BAO CAO NGAY 2026-11-27" in text
    assert "equity 9850.00 USD" in text
    assert "drawdown lon nhat 1.50%" in text
    assert "xauusd" in text and "CHAN LENH MOI" in text
    assert "BUY EURUSD" in text
    assert "BLOCKED-DAILY-LIMIT" in text


def test_report_cli(monkeypatch, tmp_path, capsys):
    log = _write_log(tmp_path)
    state = _write_state(tmp_path)
    monkeypatch.setattr(decisions, "LOG", log)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state)
    from diamondx10.__main__ import main
    assert main(["report"]) is None
    out = capsys.readouterr().out
    assert "BAO CAO NGAY" in out
    assert "9850.00" in out
