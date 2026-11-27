"""Smoke test cho CLI `compare` / `sweep` (tich hop Phase B).

Chi chay tren du lieu mo phong, khong can MT5, khong dat lenh.
"""
from diamondx10.__main__ import main


def test_compare_cli_runs_on_simulated(capsys):
    rc = main(["compare", "--desk", "forex", "--strategies", "default",
               "donchian", "--days", "120"])
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert "default" in out
    assert "donchian" in out


def test_compare_cli_unknown_strategy_fails_cleanly(capsys):
    rc = main(["compare", "--desk", "forex", "--strategies", "ema"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "LOI" in out


def test_sweep_cli_runs_on_simulated(capsys):
    rc = main(["sweep", "--desk", "forex", "--days", "120"])
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert "top" in out.lower() or "OOS" in out or "test" in out.lower()
