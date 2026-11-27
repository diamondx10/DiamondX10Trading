"""Test tham so rieng theo symbol (Phase B): override dung symbol,
fallback mac dinh/desk, gia tri la bao loi, noi vao signals/backtest."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import run_backtest
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed
from diamondx10.models.quant import atr
from diamondx10.signals import generate_signals
from diamondx10.strategies import build_strategy, resolve_strategy_params


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
    # RSI = 60, SMA5 > SMA20 -> BUY (lay tu test_strategies).
    return closes_from_changes(100, [1] * 6 + [0.75, -2 / 3] * 6 + [0.75, 0.75])


def _cfg_with_per_symbol(per_symbol, symbols=None):
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": symbols or {"forex": ["EURUSD"],
                                          "xauusd": ["XAUUSD"],
                                          "crypto": ["BTCUSD", "ETHUSD",
                                                     "BNBUSD"]}}
    cfg["strategy"] = dict(cfg["strategy"])
    cfg["strategy"]["per_symbol"] = per_symbol
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    return cfg


def test_resolve_override_applies_to_symbol_only():
    cfg = _cfg_with_per_symbol({"BTCUSD": {"atr_sl_mult": 2.0},
                                "XAUUSD": {"rsi_buy_low": 55}})
    btc = resolve_strategy_params(cfg, "crypto", "BTCUSD")
    assert btc["atr_sl_mult"] == 2.0
    xau = resolve_strategy_params(cfg, "xauusd", "XAUUSD")
    assert xau["rsi_buy_low"] == 55
    # Symbol khong override thi giu nguyen gia tri cua no.
    assert xau["atr_sl_mult"] == 1.5
    assert btc["rsi_buy_low"] == 50


def test_resolve_fallback_chain():
    cfg = _cfg_with_per_symbol({})
    # Khong override: crypto giu DESK_OVERRIDES 2.0, forex giu 1.5.
    assert resolve_strategy_params(cfg, "crypto", "BTCUSD")["atr_sl_mult"] == 2.0
    assert resolve_strategy_params(cfg, "forex", "EURUSD")["atr_sl_mult"] == 1.5
    # Ghi de desk thang mac dinh; ghi de symbol thang ghi de desk.
    cfg["strategy"]["desks"] = {"crypto": {"atr_sl_mult": 2.5}}
    assert resolve_strategy_params(cfg, "crypto", "ETHUSD")["atr_sl_mult"] == 2.5
    cfg["strategy"]["per_symbol"] = {"ETHUSD": {"atr_sl_mult": 1.0}}
    assert resolve_strategy_params(cfg, "crypto", "ETHUSD")["atr_sl_mult"] == 1.0
    assert resolve_strategy_params(cfg, "crypto", "BTCUSD")["atr_sl_mult"] == 2.5


def test_resolve_defaults_unchanged():
    # Gia tri mac dinh da chot khong doi khi khong co override.
    cfg = _cfg_with_per_symbol({})
    p = resolve_strategy_params(cfg, "forex", "EURUSD")
    assert p["sma_fast"] == 5 and p["sma_slow"] == 20
    assert p["rsi_buy_low"] == 50 and p["rsi_buy_high"] == 70
    assert p["rsi_sell_low"] == 30 and p["rsi_sell_high"] == 50
    assert p["tp_mult"] == 2.0 and p["trail_mult"] == 1.5


def test_resolve_unknown_symbol_raises():
    cfg = _cfg_with_per_symbol({"BTCUSD": {"atr_sl_mult": 2.0}})
    with pytest.raises(ValueError, match="khong co trong config"):
        resolve_strategy_params(cfg, "crypto", "DOGEUSD")


def test_resolve_bad_values_raise():
    # Khong phai so.
    cfg = _cfg_with_per_symbol({"EURUSD": {"atr_sl_mult": "rong"}})
    with pytest.raises(ValueError, match="phai la so"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    # Vuot khoang hop ly.
    cfg = _cfg_with_per_symbol({"EURUSD": {"atr_sl_mult": 99.0}})
    with pytest.raises(ValueError, match="vuot khoang"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    cfg = _cfg_with_per_symbol({"EURUSD": {"atr_sl_mult": 0.1}})
    with pytest.raises(ValueError, match="vuot khoang"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    # Tham so khong biet (go sai ten).
    cfg = _cfg_with_per_symbol({"EURUSD": {"atr_stop_mult": 2.0}})
    with pytest.raises(ValueError, match="khong biet"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    # Thu tu nguong vo ly: buy_low >= buy_high.
    cfg = _cfg_with_per_symbol({"EURUSD": {"rsi_buy_low": 75}})
    with pytest.raises(ValueError, match="rsi_buy_low phai nho hon"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    # SMA nguyen, khong le.
    cfg = _cfg_with_per_symbol({"EURUSD": {"sma_fast": 5.5}})
    with pytest.raises(ValueError, match="so nguyen"):
        resolve_strategy_params(cfg, "forex", "EURUSD")


def test_build_strategy_for_symbol():
    cfg = _cfg_with_per_symbol({"BTCUSD": {"atr_sl_mult": 2.0},
                                "XAUUSD": {"rsi_buy_low": 55}})
    strat = build_strategy("crypto", symbol="BTCUSD", cfg=cfg)
    assert strat.params["atr_sl_mult"] == 2.0
    strat = build_strategy("xauusd", symbol="XAUUSD", cfg=cfg)
    assert strat.params["rsi_buy_low"] == 55
    # Khong symbol -> instance mac dinh cua desk.
    assert build_strategy("forex").params["atr_sl_mult"] == 1.5


def test_generate_signals_uses_per_symbol_params():
    cfg = _cfg_with_per_symbol({"EURUSD": {"atr_sl_mult": 2.5}})
    bars = bars_from_closes(buy_rsi60_closes())
    sig = generate_signals("forex", bars, symbol="EURUSD", cfg=cfg)
    assert sig["action"] == "BUY"
    assert sig["symbol"] == "EURUSD"
    assert sig["params"]["atr_sl_mult"] == 2.5
    atr_val = atr([b["high"] for b in bars], [b["low"] for b in bars],
                  [b["close"] for b in bars], 14)
    assert sig["levels"]["sl"] == pytest.approx(
        sig["levels"]["entry"] - 2.5 * atr_val)
    # Khong truyen symbol/cfg: hanh vi cu, khong co khoa symbol.
    sig2 = generate_signals("forex", bars)
    assert sig2["action"] == "BUY"
    assert "symbol" not in sig2


def test_run_backtest_uses_per_symbol_params():
    cfg = _cfg_with_per_symbol({"BTCUSD": {"atr_sl_mult": 2.0},
                                "ETHUSD": {"atr_sl_mult": 1.0}})
    bars = SimulatedFeed("crypto").bars(60)
    result = run_backtest("crypto", 60, cfg=cfg,
                          symbols=["BTCUSD", "ETHUSD"], bars=bars)
    assert result["strategy_params"]["BTCUSD"]["atr_sl_mult"] == 2.0
    assert result["strategy_params"]["ETHUSD"]["atr_sl_mult"] == 1.0
    assert result["strategy_params"]["BTCUSD"]["rsi_buy_low"] == 50
