"""Test parameter sweep Phase B: luoi nho, xep hang theo OOS, bao cao
co ca train va test de lo overfitting. Cong cu nghien cuu — khong tu
dong ap tham so thang vao config."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import format_sweep_report, sweep_params
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed


def _test_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    return cfg


def test_sweep_small_grid_ranked_by_oos():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    sweep = sweep_params("forex", bars, "default",
                         {"atr_sl_mult": [1.0, 2.0],
                          "rsi_buy_low": [45, 50]},
                         cfg=cfg, symbols=["EURUSD"],
                         train_bars=30, test_bars=10, step_bars=10)
    assert sweep["n_combinations"] == 4
    assert len(sweep["results"]) == 4
    assert len(sweep["top"]) == 3
    # Xep hang giam dan theo return OOS (test), khong theo train.
    test_returns = [e["test"]["total_return_pct"]
                    for e in sweep["results"]]
    assert test_returns == sorted(test_returns, reverse=True)
    # Moi muc co ca train va test, voi cung bo chi so.
    for entry in sweep["results"]:
        assert set(entry["params"]) == {"atr_sl_mult", "rsi_buy_low"}
        for side in ("train", "test"):
            assert set(entry[side]) == {
                "total_return_pct", "win_rate", "max_drawdown_pct",
                "n_trades", "sharpe", "profit_factor", "total_pnl"}
        assert "overfit_gap_pct" in entry
        assert entry["overfit_gap_pct"] == pytest.approx(
            entry["train"]["total_return_pct"]
            - entry["test"]["total_return_pct"])
    # Top-1 la muc co return OOS cao nhat.
    assert sweep["top"][0] is sweep["results"][0]


def test_sweep_default_grid_is_small():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    sweep = sweep_params("forex", bars, cfg=cfg, symbols=["EURUSD"],
                         train_bars=30, test_bars=10, step_bars=10)
    # Luoi mac dinh: 3 x 3 = 9 to hop.
    assert sweep["n_combinations"] == 9
    assert sweep["param_grid"] == {"atr_sl_mult": [1.0, 1.5, 2.0],
                                   "rsi_buy_low": [45, 50, 55]}


def test_sweep_too_large_grid_raises():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    with pytest.raises(ValueError, match="vuot gioi han"):
        sweep_params("forex", bars, "default",
                     {"atr_sl_mult": [1.0, 1.5, 2.0, 2.5],
                      "rsi_buy_low": [40, 45, 50, 55],
                      "tp_mult": [1.5, 2.0, 2.5]},
                     cfg=cfg, symbols=["EURUSD"],
                     train_bars=30, test_bars=10, step_bars=10,
                     max_combinations=27)


def test_sweep_invalid_param_raises():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    with pytest.raises(ValueError, match="vuot khoang"):
        sweep_params("forex", bars, "default",
                     {"atr_sl_mult": [99.0]},
                     cfg=cfg, symbols=["EURUSD"],
                     train_bars=30, test_bars=10, step_bars=10)
    with pytest.raises(ValueError, match="khong biet"):
        sweep_params("forex", bars, "default",
                     {"kelly_fraction": [0.25]},
                     cfg=cfg, symbols=["EURUSD"],
                     train_bars=30, test_bars=10, step_bars=10)


def test_format_sweep_report_has_train_and_test():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    sweep = sweep_params("forex", bars, "default",
                         {"atr_sl_mult": [1.0, 2.0]},
                         cfg=cfg, symbols=["EURUSD"],
                         train_bars=30, test_bars=10, step_bars=10)
    text = format_sweep_report(sweep)
    assert "PARAMETER SWEEP" in text
    assert "OUT-OF-SAMPLE" in text
    assert "train return" in text and "test return" in text
    assert "OVERFITTING" in text
    assert "atr_sl_mult" in text
