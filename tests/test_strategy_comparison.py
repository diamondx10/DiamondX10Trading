"""Test so sanh chien luoc Phase B: compare tren cung du lieu mo phong,
bang CHI dung ket qua out-of-sample (test windows)."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import (
    compare_strategies,
    format_strategy_comparison,
    run_walk_forward,
)
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed


def _test_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    return cfg


def test_compare_two_strategies_oos_only():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    comp = compare_strategies("forex", ["default", "donchian"], cfg=cfg,
                              symbols=["EURUSD"], train_bars=30,
                              test_bars=10, step_bars=10, bars=bars)
    assert comp["desk"] == "forex"
    assert comp["n_windows"] == 5
    assert len(comp["rows"]) == 2
    by_name = {r["strategy_name"]: r for r in comp["rows"]}
    assert set(by_name) == {"default", "donchian"}
    assert by_name["donchian"]["backtest_only"] is True
    assert by_name["default"]["backtest_only"] is False
    for row in comp["rows"]:
        # Moi dong chi co chi so OOS (khong co train).
        assert set(row) == {"strategy", "strategy_name", "backtest_only",
                            "n_windows", "oos_return_pct", "oos_win_rate",
                            "oos_max_drawdown_pct", "oos_n_trades",
                            "oos_sharpe", "oos_profit_factor",
                            "oos_total_pnl"}
    # Gia tri dong = aggregated OOS cua run_walk_forward rieng tung
    # chien luoc tren cung du lieu (khong phai train).
    for name in ("default", "donchian"):
        wf = run_walk_forward("forex", 80, cfg=cfg, symbols=["EURUSD"],
                              train_bars=30, test_bars=10, step_bars=10,
                              bars=bars, strategy_name=name)
        row = by_name[name]
        assert row["oos_return_pct"] == pytest.approx(
            wf["aggregated"]["total_return_pct"])
        assert row["oos_win_rate"] == pytest.approx(
            wf["aggregated"]["win_rate"])
        assert row["oos_max_drawdown_pct"] == pytest.approx(
            wf["aggregated"]["max_drawdown_pct"])
        assert row["oos_n_trades"] == wf["aggregated"]["n_trades"]
        # Walk-forward cung gop ca train (de doi chieu train/test),
        # nhung bang so sanh khong dung so train do.
        assert "aggregated_train" in wf
        assert wf["aggregated_train"]["n_trades"] >= 0
    # Sap theo return OOS giam dan.
    returns = [r["oos_return_pct"] for r in comp["rows"]]
    assert returns == sorted(returns, reverse=True)


def test_compare_unknown_strategy_raises():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    with pytest.raises(ValueError, match="Chien luoc khong biet"):
        compare_strategies("forex", ["default", "ema"], cfg=cfg,
                           symbols=["EURUSD"], bars=bars)
    with pytest.raises(ValueError, match="it nhat 1 chien luoc"):
        compare_strategies("forex", [], cfg=cfg, symbols=["EURUSD"],
                           bars=bars)


def test_compare_uses_per_symbol_params():
    cfg = _test_cfg()
    cfg["strategy"] = dict(cfg["strategy"])
    cfg["strategy"]["per_symbol"] = {"EURUSD": {"atr_sl_mult": 2.0}}
    bars = SimulatedFeed("forex").bars(80)
    comp = compare_strategies("forex", ["default"], cfg=cfg,
                              symbols=["EURUSD"], train_bars=30,
                              test_bars=10, step_bars=10, bars=bars)
    wf = comp["walk_forward"]["default"]
    assert wf["strategy_params"]["EURUSD"]["atr_sl_mult"] == 2.0


def test_format_strategy_comparison_text():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(80)
    comp = compare_strategies("forex", ["default", "donchian"], cfg=cfg,
                              symbols=["EURUSD"], train_bars=30,
                              test_bars=10, step_bars=10, bars=bars)
    text = format_strategy_comparison(comp)
    assert "SO SANH CHIEN LUOC" in text
    assert "OUT-OF-SAMPLE" in text
    assert "default" in text and "donchian" in text
    assert "[CHI BACKTEST]" in text
    assert "MO PHONG" in text
