"""Test Phase F — bao cao ngay: --save + muc kill switch / gioi han
quy / audit (report.py + CLI `report --save`, `kill-switch`, `audit`).
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import audit, decisions, killswitch
from diamondx10.__main__ import main
from diamondx10.report import build_report, format_report

CFG = {
    "fund": {"total_capital_usd": 10000, "desks": {
        "forex": {"manager": "Yuling Pan", "capital_usd": 2500},
        "xauusd": {"manager": "Yumi", "capital_usd": 2500},
        "crypto": {"manager": "Rich", "capital_usd": 2500},
        "us_securities": {"manager": "Kathy", "capital_usd": 2500}}},
    "risk": {"max_drawdown_pct": 10.0, "desk_warning_pct": 5.0,
             "fund_daily_loss_pct": 3.0, "max_open_positions_fund": 10,
             "max_open_positions_desk": 2},
}

LOG_ROWS = [
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "BUY", "reason": "lenh 1", "manager": "Yuling Pan"},
    {"date": "2026-11-27", "desk": "forex", "symbol": "EURUSD",
     "action": "CLOSE",
     "reason": "Dong BUY EURUSD @ 1.10 P&L -120.00 USD (SL)",
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
            "max_drawdown_pct": 10.0, "desk_warning_pct": 5.0,
            "fund_curve": [10000.0, 9880.0],
            "desk_curves": {"forex": [2500.0, 2380.0],
                            "xauusd": [2500.0], "crypto": [2500.0],
                            "us_securities": [2500.0]},
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


def _patch_all(monkeypatch, tmp_path):
    log_path = _write_log(tmp_path)
    state_path = _write_state(tmp_path)
    ks_path = tmp_path / "kill-switch.json"
    audit_path = tmp_path / "audit-log.jsonl"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    monkeypatch.setattr(killswitch, "KILL_SWITCH_FILE", ks_path)
    monkeypatch.setattr(audit, "AUDIT_LOG", audit_path)
    return log_path, state_path, ks_path, audit_path


def test_build_report_has_fund_limits_kill_switch_audit(tmp_path,
                                                        monkeypatch):
    _, _, ks_path, audit_path = _patch_all(monkeypatch, tmp_path)
    killswitch.engage("test bao cao", by="Phu", path=ks_path)
    rep = build_report(CFG, log_path=_write_log(tmp_path),
                       state_path=_write_state(tmp_path),
                       today="2026-11-27",
                       kill_switch_path=ks_path, audit_path=audit_path)
    assert rep["kill_switch"]["engaged"] is True
    assert rep["kill_switch"]["reason"] == "test bao cao"
    fl = rep["fund_limits"]
    assert fl["config"] == {"fund_daily_loss_pct": 3.0,
                            "max_open_positions_fund": 10,
                            "max_open_positions_desk": 2}
    assert fl["today_pnl"] == -120.00
    assert fl["daily_loss_limit_usd"] == 300.00
    assert fl["daily_loss_blocked"] is False  # 120 < 300
    assert fl["open_positions"] == 1
    assert fl["open_by_desk"] == {"forex": 1}
    assert fl["fund_blocked"] is False
    assert fl["desk_blocked"] == {"forex": False}
    assert rep["audit_recent"][0]["event"] == "KILL_SWITCH_ON"


def test_format_report_shows_kill_switch_limits_audit(tmp_path,
                                                      monkeypatch):
    _, _, ks_path, audit_path = _patch_all(monkeypatch, tmp_path)
    rep = build_report(CFG, log_path=_write_log(tmp_path),
                       state_path=_write_state(tmp_path),
                       today="2026-11-27",
                       kill_switch_path=ks_path, audit_path=audit_path)
    text = format_report(rep)
    assert "Kill switch: TAT." in text
    assert "Gioi han quy" in text
    assert "Lo trong ngay: -120.00 USD / gioi han 300.00 USD" in text
    assert "Vi the mo: 1 / 10 toan quy" in text
    assert "forex: 1 / 2 vi the" in text
    assert "Audit gan day" in text
    assert "(chua co su kien audit nao)" in text


def test_report_save_cli_writes_file(tmp_path, monkeypatch, capsys):
    _patch_all(monkeypatch, tmp_path)
    out = tmp_path / "reports" / "report-2026-11-27.md"
    rc = main(["report", "--save", str(out)])
    assert rc in (0, None)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "BAO CAO NGAY" in text
    assert "Kill switch" in text
    assert "Gioi han quy" in text
    assert "Audit gan day" in text
    assert "Da ghi bao cao ra" in capsys.readouterr().out
    # --save ghi audit REPORT_GENERATED.
    events = audit.read_events(path=tmp_path / "audit-log.jsonl")
    assert events[0]["event"] == "REPORT_GENERATED"


def test_kill_switch_cli_on_off_status(tmp_path, monkeypatch, capsys):
    _, _, ks_path, audit_path = _patch_all(monkeypatch, tmp_path)
    rc = main(["kill-switch", "on", "--reason", "su co",
               "--by", "Phu"])
    assert rc in (0, None)
    assert "BAT" in capsys.readouterr().out
    assert killswitch.is_engaged(path=ks_path) is True
    rc = main(["kill-switch", "status"])
    out = capsys.readouterr().out
    assert "BAT" in out
    assert "su co" in out
    rc = main(["kill-switch", "off", "--by", "Phu"])
    assert "TAT" in capsys.readouterr().out
    assert killswitch.is_engaged(path=ks_path) is False
    rc = main(["kill-switch", "status"])
    assert "TAT" in capsys.readouterr().out
    events = audit.read_events(path=audit_path)
    assert [e["event"] for e in events] == [
        "KILL_SWITCH_OFF", "KILL_SWITCH_ON"]


def test_audit_cli_prints_newest_first(tmp_path, monkeypatch, capsys):
    _, _, _, audit_path = _patch_all(monkeypatch, tmp_path)
    audit.log_event("A", {"n": 1}, path=audit_path)
    audit.log_event("B", {"n": 2}, path=audit_path)
    rc = main(["audit", "--lines", "2"])
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert out.index("B") < out.index("A")  # moi nhat len dau
