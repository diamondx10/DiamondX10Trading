"""Test backtest engine Phase 3: chay bar-by-bar, SL/TP, trailing,
thoat khi dao chieu, metrics, tach train/test, CLI. Dung du lieu
tong hop + SimulatedFeed (khong can MT5 that, khong co credential)."""
import copy
import math
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import main
from diamondx10.backtest import (
    SHARPE_BARS_PER_YEAR,
    _run_segment,
    compute_metrics,
    format_backtest_report,
    run_backtest,
)
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed
from diamondx10.strategies.forex import ForexTrend


def bars_from_closes(closes, half_range=0.5):
    return [{"time": i, "open": c, "high": c + half_range,
             "low": c - half_range, "close": c}
            for i, c in enumerate(closes)]


def closes_from_changes(start, changes):
    out = [start]
    for d in changes:
        out.append(round(out[-1] + d, 6))
    return out


def buy_rsi60_closes():
    # RSI = 60, SMA5 > SMA20 -> BUY (lay tu tests/test_strategies.py).
    return closes_from_changes(100, [1] * 6 + [0.75, -2 / 3] * 6 + [0.75, 0.75])


def sell_rsi40_closes():
    # RSI = 40, SMA5 < SMA20 -> SELL (lay tu tests/test_strategies.py).
    return closes_from_changes(100, [-1] * 6 + [2 / 3, -0.75] * 6 + [-0.75, -0.75])


def _test_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"],
                               "crypto": ["BTCUSD", "ETHUSD"]}}
    cfg["backtest"] = {"fee_pct": 0.02, "slippage_pct": 0.01}
    return cfg


def _seg(bars, strategy=None, capital=2500.0, risk_pct=1.0,
         contract_size=1, fee_pct=0.0, slippage_pct=0.0):
    return _run_segment(strategy or ForexTrend(), bars, symbol="TEST",
                        capital=capital, risk_pct=risk_pct,
                        contract_size=contract_size, fee_pct=fee_pct,
                        slippage_pct=slippage_pct)


# --- Engine: cac kich ban xac dinh ---

def test_uptrend_buy_hits_tp():
    closes = buy_rsi60_closes() + closes_from_changes(
        buy_rsi60_closes()[-1], [1.0] * 10)[1:]
    res = _seg(bars_from_closes(closes))
    assert len(res["trades"]) >= 1
    trade = res["trades"][0]
    assert trade["direction"] == "BUY"
    assert trade["exit_reason"] == "TP"
    assert trade["exit"] == pytest.approx(trade["tp"])
    assert trade["pnl"] > 0
    assert len(res["equity_curve"]) == len(closes)
    assert res["equity_curve"][0] == pytest.approx(2500.0)


def test_downtrend_sell_hits_tp():
    closes = sell_rsi40_closes() + closes_from_changes(
        sell_rsi40_closes()[-1], [-1.0] * 10)[1:]
    res = _seg(bars_from_closes(closes))
    assert len(res["trades"]) >= 1
    trade = res["trades"][0]
    assert trade["direction"] == "SELL"
    assert trade["exit_reason"] == "TP"
    assert trade["exit"] == pytest.approx(trade["tp"])
    assert trade["pnl"] > 0


def test_sharp_drop_hits_sl():
    closes = buy_rsi60_closes() + closes_from_changes(
        buy_rsi60_closes()[-1], [-3.0] * 5)[1:]
    res = _seg(bars_from_closes(closes))
    assert len(res["trades"]) >= 1
    trade = res["trades"][0]
    assert trade["direction"] == "BUY"
    assert trade["exit_reason"] == "SL"
    assert trade["exit"] == pytest.approx(trade["sl"])
    assert trade["pnl"] < 0


def test_trailing_stop_moves_sl_up_then_sl_hit():
    # TP xa (tp_mult 4.0) de gia kip chay len truoc khi cham TP; sau do
    # gia roi manh: lenh phai dong o SL DA DOI LEN, khong phai SL goc.
    strat = ForexTrend(params={"tp_mult": 4.0})
    start = buy_rsi60_closes()[-1]
    closes = (buy_rsi60_closes()
              + closes_from_changes(start, [1.0] * 6)[1:]
              + closes_from_changes(start + 6.0, [-4.0] * 3)[1:])
    res = _seg(bars_from_closes(closes), strategy=strat)
    assert len(res["trades"]) >= 1
    trade = res["trades"][0]
    assert trade["direction"] == "BUY"
    assert trade["exit_reason"] == "SL"
    assert trade["sl"] > trade["sl_initial"]
    assert trade["exit"] == pytest.approx(trade["sl"])
    assert trade["pnl"] > 0  # dong o SL da doi len tren gia vao


def test_reversal_exit_closes_position():
    # SL rat rong (atr_sl_mult 10) de gia giam dan khong cham SL truoc
    # khi tin hieu dao chieu day du xuat hien.
    strat = ForexTrend(params={"atr_sl_mult": 10.0})
    start = buy_rsi60_closes()[-1]
    sell_part = closes_from_changes(start, [-1] * 6 + [2 / 3, -0.75] * 6
                                    + [-0.75, -0.75])[1:]
    closes = buy_rsi60_closes() + sell_part
    res = _seg(bars_from_closes(closes), strategy=strat)
    # Len dau: BUY dong bang dao chieu. Sau do engine dung tin hieu
    # SELL hien tai mo lenh SELL moi — do la hanh vi dung, khong phai loi.
    assert len(res["trades"]) >= 1
    trade = res["trades"][0]
    assert trade["direction"] == "BUY"
    assert trade["exit_reason"] == "reversal"
    assert trade["exit"] == pytest.approx(
        closes[trade["exit_index"]])


def test_hold_produces_no_trade():
    res = _seg(bars_from_closes([100.0] * 40))
    assert res["trades"] == []
    assert res["equity_curve"] == [2500.0] * 40
    metrics = compute_metrics([], res["equity_curve"], 2500.0)
    assert metrics["n_trades"] == 0
    assert metrics["total_return_pct"] == pytest.approx(0.0)
    assert metrics["win_rate"] == pytest.approx(0.0)
    assert metrics["profit_factor"] is None
    assert metrics["sharpe"] is None
    assert metrics["max_drawdown_pct"] == pytest.approx(0.0)


def test_warmup_skips_signals_before_20_bars():
    # Chi 10 bar tang manh: du SMA cat nhau nhung chua du 20 bar.
    res = _seg(bars_from_closes([100.0 + i for i in range(10)]))
    assert res["trades"] == []


def test_zero_fee_slippage_pnl_is_exact():
    closes = buy_rsi60_closes() + closes_from_changes(
        buy_rsi60_closes()[-1], [1.0] * 10)[1:]
    res = _seg(bars_from_closes(closes), fee_pct=0.0, slippage_pct=0.0)
    trade = res["trades"][0]
    assert trade["fee"] == pytest.approx(0.0)
    assert trade["slippage_cost"] == pytest.approx(0.0)
    assert trade["pnl"] == pytest.approx(
        trade["units"] * (trade["tp"] - trade["entry"]))


def test_fee_and_slippage_reduce_pnl():
    closes = buy_rsi60_closes() + closes_from_changes(
        buy_rsi60_closes()[-1], [1.0] * 10)[1:]
    bars = bars_from_closes(closes)
    clean = _seg(bars, fee_pct=0.0, slippage_pct=0.0)["trades"][0]
    costed = _seg(bars, fee_pct=0.02, slippage_pct=0.01)["trades"][0]
    assert costed["fee"] == pytest.approx(
        costed["units"] * costed["entry"] * 0.02 / 100.0)
    assert costed["slippage_cost"] == pytest.approx(
        2 * costed["units"] * costed["entry"] * 0.01 / 100.0)
    assert costed["pnl"] < clean["pnl"]
    assert costed["pnl"] == pytest.approx(clean["pnl"] - costed["fee"]
                                          - costed["slippage_cost"])


def test_below_min_lot_flagged_not_skipped():
    # Contract forex 100000, gia ~100: lot tinh ra << 0,01 — lenh van
    # mo trong backtest nhung bi danh dau.
    closes = buy_rsi60_closes() + closes_from_changes(
        buy_rsi60_closes()[-1], [1.0] * 10)[1:]
    res = _seg(bars_from_closes(closes), contract_size=100000)
    assert len(res["trades"]) >= 1
    assert res["trades"][0]["below_min_lot"] is True
    assert res["trades"][0]["lots"] < 0.01


def test_open_position_forced_closed_at_end_of_data():
    # Tang vua du de mo BUY nhung khong cham TP/SL truoc bar cuoi.
    strat = ForexTrend(params={"tp_mult": 10.0, "atr_sl_mult": 10.0})
    closes = buy_rsi60_closes() + closes_from_changes(
        buy_rsi60_closes()[-1], [0.1] * 5)[1:]
    res = _seg(bars_from_closes(closes), strategy=strat)
    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    assert trade["exit_reason"] == "end_of_data"
    assert trade["exit"] == pytest.approx(closes[-1])
    assert trade["exit_index"] == len(closes) - 1


# --- Metrics: toan tren danh sach lenh co dinh ---

def test_metrics_math_on_fixed_trades():
    trades = [{"pnl": 100.0}, {"pnl": -50.0},
              {"pnl": 200.0}, {"pnl": -50.0}]
    curve = [1000.0, 1100.0, 1050.0, 1250.0, 1200.0]
    m = compute_metrics(trades, curve, 1000.0)
    assert m["n_trades"] == 4
    assert m["wins"] == 2 and m["losses"] == 2
    assert m["win_rate"] == pytest.approx(50.0)
    assert m["profit_factor"] == pytest.approx(3.0)
    assert m["total_pnl"] == pytest.approx(200.0)
    assert m["total_return_pct"] == pytest.approx(20.0)
    assert m["gross_profit"] == pytest.approx(300.0)
    assert m["gross_loss"] == pytest.approx(100.0)
    assert m["avg_win"] == pytest.approx(150.0)
    assert m["avg_loss"] == pytest.approx(50.0)
    assert m["max_drawdown_pct"] == pytest.approx((1100 - 1050) / 1100 * 100)
    returns = [(b - a) / a for a, b in zip(curve, curve[1:])]
    expected_sharpe = (statistics.mean(returns) / statistics.pstdev(returns)
                       * math.sqrt(SHARPE_BARS_PER_YEAR))
    assert m["sharpe"] == pytest.approx(expected_sharpe)


def test_metrics_all_wins_profit_factor_undefined():
    m = compute_metrics([{"pnl": 10.0}, {"pnl": 20.0}],
                        [1000.0, 1010.0, 1030.0], 1000.0)
    assert m["profit_factor"] is None
    assert m["win_rate"] == pytest.approx(100.0)


# --- run_backtest: API, split, per-symbol ---

def test_run_backtest_returns_dict_and_split_sizes():
    bars = SimulatedFeed("forex").bars(100)
    result = run_backtest("forex", 30, cfg=_test_cfg(), bars=bars)
    assert isinstance(result, dict)
    assert result["desk"] == "forex"
    assert result["n_bars"] == 100
    assert result["symbols"] == ["EURUSD"]
    assert result["simulated"] is True
    assert result["assumptions"]["fee_pct"] == pytest.approx(0.02)
    assert result["assumptions"]["slippage_pct"] == pytest.approx(0.01)
    assert result["segments"]["train"]["n_bars"] == 70
    assert result["segments"]["test"]["n_bars"] == 30
    assert result["segments"]["train"]["n_bars"] > 0
    assert result["segments"]["test"]["n_bars"] > 0
    assert set(result["metrics"]) >= {
        "total_return_pct", "win_rate", "profit_factor", "sharpe",
        "max_drawdown_pct", "n_trades"}
    assert result["per_symbol"]["EURUSD"]["capital_usd"] == pytest.approx(2500.0)
    assert result["per_symbol"]["EURUSD"]["risk_pct"] == pytest.approx(3.0)
    assert len(result["trades"]) == result["metrics"]["n_trades"]


def test_run_backtest_split_fraction_respected():
    bars = SimulatedFeed("crypto").bars(80)
    result = run_backtest("crypto", 30, cfg=_test_cfg(), bars=bars,
                          train_fraction=0.5)
    assert result["segments"]["train"]["n_bars"] == 40
    assert result["segments"]["test"]["n_bars"] == 40
    # Crypto 2 symbol, von chia deu 1250/symbol, risk BTC 8% / ETH 1%.
    assert result["per_symbol"]["BTCUSD"]["capital_usd"] == pytest.approx(1250.0)
    assert result["per_symbol"]["BTCUSD"]["risk_pct"] == pytest.approx(8.0)
    assert result["per_symbol"]["ETHUSD"]["risk_pct"] == pytest.approx(1.0)


def test_run_backtest_old_call_still_works():
    result = run_backtest("forex", 30, cfg=_test_cfg(),
                          bars=SimulatedFeed("forex").bars(50))
    assert isinstance(result, dict)
    assert "metrics" in result and "trades" in result


def test_run_backtest_rejects_bad_desk_and_split():
    with pytest.raises(ValueError):
        run_backtest("khong-co-desk", 30, cfg=_test_cfg(),
                     bars=SimulatedFeed("forex").bars(50))
    with pytest.raises(ValueError):
        run_backtest("forex", 30, cfg=_test_cfg(), train_fraction=1.0,
                     bars=SimulatedFeed("forex").bars(50))
    with pytest.raises(ValueError):
        run_backtest("forex", 30, cfg=_test_cfg(), symbols=[],
                     bars=SimulatedFeed("forex").bars(50))


def test_format_backtest_report_states_simulated():
    bars = SimulatedFeed("crypto").bars(100)
    result = run_backtest("crypto", 30, cfg=_test_cfg(), bars=bars)
    text = format_backtest_report(result)
    assert "MO PHONG" in text
    assert "KHONG PHAI HIEU SUAT THAT" in text
    assert "crypto" in text
    assert "BTCUSD" in text and "ETHUSD" in text
    assert "Train" in text and "Test" in text
    assert "GIA DINH" in text or "Gia dinh" in text


# --- CLI end-to-end tren du lieu mo phong ---

def test_cli_backtest_one_desk(monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["backtest", "--desk", "crypto", "--days", "60"]) is None
    out = capsys.readouterr().out
    assert "MO PHONG" in out
    assert "KHONG PHAI HIEU SUAT THAT" in out
    assert "crypto" in out
    assert "BTCUSD" in out


def test_cli_backtest_symbol_and_split(monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["backtest", "--desk", "crypto", "--days", "60",
                 "--symbol", "BTCUSD", "--split", "0.5"]) is None
    out = capsys.readouterr().out
    assert "BTCUSD" in out
    assert "ETHUSD" not in out
    assert "50% / 50%" in out


def test_cli_backtest_bad_desk_returns_1(monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["backtest", "--desk", "khong-co"]) == 1
    assert "LOI" in capsys.readouterr().out
