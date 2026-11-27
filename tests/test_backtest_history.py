"""Test Phase C — backtest / walk-forward tren du lieu that tu kho
lich su (HistoryStore). Chi dung du lieu mo phong do vao kho tam
(khong can MT5 that, khong cham data/history.db that); lan chay
tren nen MT5 that phai o sau khi co CSV/kho tu may Windows.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import (
    MIN_HISTORY_BARS,
    compare_strategies,
    format_backtest_report,
    format_walk_forward_report,
    run_backtest,
    run_backtest_from_history,
    run_walk_forward,
    run_walk_forward_from_history,
)
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed
from diamondx10.data.history import HistoryStore


def _test_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"],
                               "crypto": ["BTCUSD", "ETHUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.02, "slippage_pct": 0.01}
    return cfg


def _fill(store, symbol, bars, timeframe="M15"):
    store.upsert_bars(symbol, timeframe, bars)


# --- (a) ket qua tu kho khop voi chay truc tiep tren cung bars ---

def test_backtest_from_history_matches_direct_single_symbol(tmp_path):
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(200)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "EURUSD", bars)
        hist = run_backtest_from_history("forex", cfg, symbols=["EURUSD"],
                                         store=store)
    direct = run_backtest("forex", 30, cfg=cfg, symbols=["EURUSD"],
                          bars=bars)
    assert hist["simulated"] is False
    assert hist["source"] == "history"
    assert hist["timeframe"] == "M15"
    assert hist["n_bars"] == 200
    assert hist["n_bars_by_symbol"] == {"EURUSD": 200}
    assert hist["metrics"] == direct["metrics"]
    assert hist["trades"] == direct["trades"]
    assert hist["segments"] == direct["segments"]
    assert hist["per_symbol"] == direct["per_symbol"]
    text = format_backtest_report(hist)
    assert "DU LIEU THAT" in text
    assert "MO PHONG" not in text


def test_backtest_from_history_matches_direct_multi_symbol(tmp_path):
    # Cung chuoi bar cho ca 2 symbol: ket qua phai y het chay chung
    # 1 chuoi bar nhu duong mo phong cu.
    cfg = _test_cfg()
    bars = SimulatedFeed("crypto").bars(200)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "BTCUSD", bars)
        _fill(store, "ETHUSD", bars)
        hist = run_backtest_from_history(
            "crypto", cfg, symbols=["BTCUSD", "ETHUSD"], store=store)
    direct = run_backtest("crypto", 30, cfg=cfg,
                          symbols=["BTCUSD", "ETHUSD"], bars=bars)
    assert hist["metrics"] == direct["metrics"]
    assert hist["trades"] == direct["trades"]
    assert hist["per_symbol"] == direct["per_symbol"]


def test_backtest_from_history_uses_per_symbol_series(tmp_path):
    # Moi symbol 1 chuoi bar RIENG: do dai khac nhau + chuoi gia khac
    # nhau phai cho ket qua rieng theo symbol (khong phai chung 1
    # chuoi nhu du lieu mo phong theo desk).
    cfg = _test_cfg()
    bars_btc = SimulatedFeed("crypto").bars(200)
    bars_eth = SimulatedFeed("forex").bars(120)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "BTCUSD", bars_btc)
        _fill(store, "ETHUSD", bars_eth)
        hist = run_backtest_from_history(
            "crypto", cfg, symbols=["BTCUSD", "ETHUSD"], store=store)
    assert hist["n_bars_by_symbol"] == {"BTCUSD": 200, "ETHUSD": 120}
    assert hist["n_bars"] == 200
    assert hist["per_symbol"]["BTCUSD"]["segments"]["train"]["n_bars"] == 140
    assert hist["per_symbol"]["ETHUSD"]["segments"]["train"]["n_bars"] == 84
    # Chuoi gia khac nhau -> lenh khac nhau (2 seed co dinh, lap lai duoc).
    assert hist["per_symbol"]["BTCUSD"]["trades"] != \
        hist["per_symbol"]["ETHUSD"]["trades"]
    assert hist["simulated"] is False


def test_backtest_from_history_start_end_filter(tmp_path):
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(200)  # time 300..499
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "EURUSD", bars)
        hist = run_backtest_from_history(
            "forex", cfg, symbols=["EURUSD"], store=store,
            start=350, end=449)
    assert hist["n_bars"] == 100
    assert hist["start"] == 350
    assert hist["end"] == 449


def test_backtest_from_history_opens_store_from_cfg(tmp_path):
    # Khong truyen store: mo theo history.db_path trong cfg.
    cfg = _test_cfg()
    cfg["history"] = {"db_path": str(tmp_path / "history.db")}
    bars = SimulatedFeed("forex").bars(200)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "EURUSD", bars)
    hist = run_backtest_from_history("forex", cfg, symbols=["EURUSD"])
    assert hist["n_bars"] == 200
    assert hist["simulated"] is False


def test_bars_and_bars_by_symbol_mutually_exclusive():
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(50)
    with pytest.raises(ValueError, match="Chi truyen 1 trong 2"):
        run_backtest("forex", 30, cfg=cfg, symbols=["EURUSD"], bars=bars,
                     bars_by_symbol={"EURUSD": bars})
    with pytest.raises(ValueError, match="Chi truyen 1 trong 2"):
        run_walk_forward("forex", 30, cfg=cfg, symbols=["EURUSD"],
                         bars=bars, bars_by_symbol={"EURUSD": bars})


# --- (b) kho trong / thieu bar -> ValueError ro rang ---

def test_empty_store_raises_clear_error(tmp_path):
    cfg = _test_cfg()
    with HistoryStore(tmp_path / "history.db") as store:
        with pytest.raises(ValueError, match="chua co bar"):
            run_backtest_from_history("forex", cfg, symbols=["EURUSD"],
                                      store=store)
        with pytest.raises(ValueError, match="chua co bar"):
            run_walk_forward_from_history("forex", cfg, symbols=["EURUSD"],
                                          store=store)


def test_too_few_bars_raises_with_counts(tmp_path):
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(10)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "EURUSD", bars)
        with pytest.raises(ValueError) as exc:
            run_backtest_from_history("forex", cfg, symbols=["EURUSD"],
                                      store=store)
    assert "10" in str(exc.value)
    assert str(MIN_HISTORY_BARS) in str(exc.value)


def test_walk_forward_from_history_needs_enough_bars_per_symbol(tmp_path):
    # 50 bar du cho backtest (>= 40) nhung khong du 1 cua so
    # walk-forward (train 60 + test 20 = 80).
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(50)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "EURUSD", bars)
        with pytest.raises(ValueError, match="Khong du bars cho walk-forward"):
            run_walk_forward_from_history(
                "forex", cfg, symbols=["EURUSD"], store=store,
                train_bars=60, test_bars=20, step_bars=20)


# --- (c) walk-forward tu kho: chay duoc, co OOS gop ---

def test_walk_forward_from_history_matches_direct(tmp_path):
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(200)
    with HistoryStore(tmp_path / "history.db") as store:
        _fill(store, "EURUSD", bars)
        hist = run_walk_forward_from_history(
            "forex", cfg, symbols=["EURUSD"], store=store,
            train_bars=60, test_bars=20, step_bars=20)
    direct = run_walk_forward("forex", 100, cfg=cfg, symbols=["EURUSD"],
                              train_bars=60, test_bars=20, step_bars=20,
                              bars=bars)
    assert hist["simulated"] is False
    assert hist["source"] == "history"
    assert hist["n_windows"] == direct["n_windows"] == 7
    assert hist["aggregated"] == direct["aggregated"]
    assert hist["oos_equity_curve"] == direct["oos_equity_curve"]
    assert set(hist["aggregated"]) >= {
        "total_return_pct", "win_rate", "max_drawdown_pct", "n_trades",
        "sharpe", "total_pnl"}
    text = format_walk_forward_report(hist)
    assert "DU LIEU THAT" in text
    assert "OUT-OF-SAMPLE" in text


def test_compare_strategies_from_history_bars(tmp_path):
    cfg = _test_cfg()
    bars = SimulatedFeed("forex").bars(200)
    comp = compare_strategies("forex", ["default", "donchian"], cfg=cfg,
                              symbols=["EURUSD"], train_bars=60,
                              test_bars=20, step_bars=20,
                              bars_by_symbol={"EURUSD": bars})
    assert comp["simulated"] is False
    assert len(comp["rows"]) == 2
    assert {r["strategy_name"] for r in comp["rows"]} == {
        "default", "donchian"}
    assert comp["n_windows"] == 7
