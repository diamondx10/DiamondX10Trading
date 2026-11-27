"""Test walk-forward (merge y tuong tu DiamondX10, chay tren engine
cua tool nay): nhieu cua so train/test lan luot, OOS gop, bao loi khi
thieu bars, format bao cao, CLI --walk-forward / --strategy."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import main
from diamondx10.backtest import format_walk_forward_report, run_walk_forward
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed


def bars_from_closes(closes, half_range=0.5):
    return [{"time": i, "open": c, "high": c + half_range,
             "low": c - half_range, "close": c}
            for i, c in enumerate(closes)]


def closes_from_changes(start, changes):
    out = [start]
    for d in changes:
        out.append(round(out[-1] + d, 6))
    return out


def _test_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    return cfg


def test_walk_forward_windows_and_oos_concat():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(100)
    result = run_walk_forward("forex", 100, cfg=cfg, symbols=["EURUSD"],
                              train_bars=30, test_bars=10, step_bars=10,
                              bars=bars)
    # 100 bar: cua so bat dau 0,10,...,60 -> 7 cua so (60+30+10=100).
    assert result["n_windows"] == 7
    assert len(result["windows"]) == 7
    assert result["train_bars"] == 30
    assert result["test_bars"] == 10
    # OOS gop: tong lenh = tong lenh test tung cua so.
    total = sum(w["per_symbol"]["EURUSD"]["test_trades"]
                for w in result["windows"])
    assert result["aggregated"]["n_trades"] == total
    assert result["strategy"] == "ForexTrend (Yuling — Forex)"


def test_walk_forward_needs_enough_bars():
    cfg = _test_cfg()
    # 39 bar < train 30 + test 10 = 40: khong du cho 1 cua so.
    bars = bars_from_closes([100.0] * 39)
    with pytest.raises(ValueError, match="Khong du bars"):
        run_walk_forward("forex", 39, cfg=cfg, symbols=["EURUSD"],
                         train_bars=30, test_bars=10, step_bars=10,
                         bars=bars)


def test_walk_forward_donchian_strategy():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    result = run_walk_forward("forex", 80, cfg=cfg, symbols=["EURUSD"],
                              train_bars=30, test_bars=10, step_bars=10,
                              bars=bars, strategy_name="donchian")
    assert "Donchian" in result["strategy"]
    assert result["n_windows"] == 5


def test_walk_forward_unknown_strategy():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    with pytest.raises(ValueError, match="Chien luoc khong biet"):
        run_walk_forward("forex", 80, cfg=cfg, symbols=["EURUSD"],
                         bars=bars, strategy_name="ema")


def test_walk_forward_report_text():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    result = run_walk_forward("forex", 80, cfg=cfg, symbols=["EURUSD"],
                              train_bars=30, test_bars=10, step_bars=10,
                              bars=bars)
    text = format_walk_forward_report(result)
    assert "WALK-FORWARD" in text
    assert "OUT-OF-SAMPLE" in text
    assert "Cua so 0" in text
    assert "MO PHONG" in text


def test_walk_forward_oos_equity_starts_at_desk_capital():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    result = run_walk_forward("forex", 80, cfg=cfg, symbols=["EURUSD"],
                              train_bars=30, test_bars=10, step_bars=10,
                              bars=bars)
    assert result["oos_equity_curve"][0] == 2500.0
    # Duong OOS: 1 diem von khoi dau + moi cua so them (test_bars - 1)
    # diem noi tiep (bo diem dau cua cua so vi da noi vao diem cuoi
    # cua so truoc).
    assert len(result["oos_equity_curve"]) == 1 + 5 * (10 - 1)


def test_backtest_cli_walk_forward_and_donchian(capsys):
    # main() tra None khi chay xong, 1 khi loi (theo thong le cua repo).
    assert main(["backtest", "--desk", "forex", "--days", "30",
                 "--walk-forward"]) is None
    out = capsys.readouterr().out
    assert "WALK-FORWARD" in out
    assert main(["backtest", "--desk", "forex", "--days", "30",
                 "--strategy", "donchian"]) is None
    out = capsys.readouterr().out
    assert "DonchianBreakout" in out
    assert main(["backtest", "--desk", "forex", "--days", "30",
                 "--strategy", "khong-co"]) == 1
    out = capsys.readouterr().out
    assert "LOI" in out
