"""Test quy tac cung + quy tac mem TA (hard/soft rules) va gate
adx_min / min_atr_pct — xem strategies/soft_rules.py.

Fixture: so gia / chat_id GIA (khong dung so that cua user).
"""
import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import run_backtest
from diamondx10.config import DEFAULT, load_config
from diamondx10.data.feeds import SimulatedFeed
from diamondx10.signals import generate_signals
from diamondx10.strategies import (
    build_strategy,
    build_strategy_for_symbol,
    resolve_soft_rules,
    resolve_strategy_params,
)
from diamondx10.strategies.breakout import DonchianBreakout
from diamondx10.strategies.soft_rules import (
    evaluate_condition,
    validate_soft_rules,
)

REPO = Path(__file__).resolve().parents[1]


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
    # RSI = 60, SMA5 > SMA20 -> BUY; ADX(14) ~ 19.0, ATR/gia ~ 0.0112.
    return closes_from_changes(100, [1] * 6 + [0.75, -2 / 3] * 6
                               + [0.75, 0.75])


def buy_bars():
    return bars_from_closes(buy_rsi60_closes())


def _cfg(symbols=None, strategy_extra=None, per_symbol=None,
         soft_rules=None):
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": symbols or {
                       "forex": ["EURUSD"], "xauusd": ["XAUUSD"],
                       "crypto": ["BTCUSD", "ETHUSD", "BNBUSD"],
                       "us_securities": ["AMD", "CDNS", "SNPS", "INTC",
                                         "NVDA"]}}
    cfg["strategy"] = dict(cfg["strategy"])
    if strategy_extra:
        cfg["strategy"].update(strategy_extra)
    if per_symbol is not None:
        cfg["strategy"]["per_symbol"] = per_symbol
    if soft_rules is not None:
        cfg["strategy"]["soft_rules"] = soft_rules
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    return cfg


# --- Quy tac cung -------------------------------------------------------

@pytest.mark.parametrize("key", [
    "risk_per_symbol_pct", "per_symbol_pct", "max_risk_per_trade_pct",
    "max_drawdown_pct", "desk_warning_pct", "fund_daily_loss_pct",
    "max_open_positions_fund", "max_open_positions_desk",
    "kill_switch", "demo_only", "max_daily_trades", "daily_trade_limit",
    "no_trade_events", "require_fa", "verdict_max_age_hours",
    "fa_high_confidence", "pending_order_ttl_min",
    "max_entry_deviation_pct", "require_confirmation",
])
def test_hard_rule_key_in_shared_strategy_rejected(key):
    cfg = _cfg(strategy_extra={key: 1})
    with pytest.raises(ValueError, match="hard rule"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    with pytest.raises(ValueError, match=key):
        resolve_strategy_params(cfg, "forex", "EURUSD")


def test_hard_rule_key_in_desk_and_per_symbol_rejected():
    cfg = _cfg(strategy_extra={"desks": {"forex": {"demo_only": True}}})
    with pytest.raises(ValueError, match="hard rule"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    cfg = _cfg(per_symbol={"EURUSD": {"max_drawdown_pct": 5.0}})
    with pytest.raises(ValueError, match="max_drawdown_pct"):
        resolve_strategy_params(cfg, "forex", "EURUSD")
    # Khoa cung trong 1 soft rule cung bi chan (quet de quy).
    cfg = _cfg(soft_rules=[{"name": "x", "condition": {"type": "adx_min",
                                                        "value": 20},
                            "effect": "block",
                            "require_fa": True}])
    with pytest.raises(ValueError, match="hard rule"):
        resolve_soft_rules(cfg, "forex", "EURUSD")


def test_hard_rule_key_rejected_at_config_load(tmp_path):
    cfg = _cfg(strategy_extra={"kill_switch": True})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match="hard rule"):
        load_config(str(path))


# --- Gate adx_min / min_atr_pct ------------------------------------------

def test_adx_min_gate_blocks_and_passes():
    # ADX(14) cua bars mua ~19.0: adx_min 20 chan, 10 cho qua.
    cfg = _cfg(strategy_extra={"adx_min": 20})
    strat = build_strategy("forex", symbol="EURUSD", cfg=cfg)
    action, reason, _ = strat.signal(buy_bars())
    assert action == "HOLD"
    assert "adx_min" in reason
    cfg = _cfg(strategy_extra={"adx_min": 10})
    strat = build_strategy("forex", symbol="EURUSD", cfg=cfg)
    assert strat.signal(buy_bars())[0] == "BUY"


def test_min_atr_pct_gate_blocks_and_passes():
    # ATR/gia cua bars mua ~0.0112: 0.02 chan, 0.001 cho qua.
    cfg = _cfg(strategy_extra={"min_atr_pct": 0.02})
    strat = build_strategy("forex", symbol="EURUSD", cfg=cfg)
    action, reason, _ = strat.signal(buy_bars())
    assert action == "HOLD"
    assert "min_atr_pct" in reason
    cfg = _cfg(strategy_extra={"min_atr_pct": 0.001})
    assert build_strategy("forex", symbol="EURUSD", cfg=cfg) \
        .signal(buy_bars())[0] == "BUY"


def test_gates_default_off_backward_compatible():
    cfg = _cfg()
    strat = build_strategy("forex", symbol="EURUSD", cfg=cfg)
    assert strat.params["adx_min"] == 0
    assert "min_atr_pct" not in strat.params
    action, _reason, levels = strat.signal(buy_bars())
    assert action == "BUY"
    assert "size_scale" not in levels


def test_donchian_min_atr_pct_default_preserved():
    strat = DonchianBreakout()
    assert strat.params["min_atr_pct"] == 0.003


# --- Bang per_symbol nghien cuu (config.example.yaml) ---------------------

def test_per_symbol_table_from_example_yaml():
    with open(REPO / "config.example.yaml", encoding="utf-8") as f:
        example = yaml.safe_load(f)
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": example["data"]["symbols"]}
    cfg["strategy"] = example["strategy"]
    expected = {
        "EURUSD": {"sma_fast": 8, "sma_slow": 21, "adx_min": 20,
                   "min_atr_pct": 0.0001},
        "XAUUSD": {"sma_fast": 10, "sma_slow": 30, "rsi_buy_low": 55,
                   "rsi_buy_high": 75, "rsi_sell_low": 25,
                   "rsi_sell_high": 45, "rsi_extreme_high": 85,
                   "rsi_extreme_low": 15, "atr_sl_mult": 2.0,
                   "tp_mult": 1.5, "trail_mult": 2.0, "adx_min": 30,
                   "min_atr_pct": 0.0003},
        "BTCUSD": {"sma_fast": 9, "sma_slow": 21, "rsi_buy_low": 55,
                   "rsi_buy_high": 75, "rsi_sell_low": 25,
                   "rsi_sell_high": 45, "rsi_extreme_high": 85,
                   "rsi_extreme_low": 15, "atr_sl_mult": 2.0,
                   "trail_mult": 2.0, "adx_min": 25,
                   "min_atr_pct": 0.0010},
        "ETHUSD": {"sma_fast": 9, "sma_slow": 21, "rsi_buy_low": 55,
                   "rsi_buy_high": 75, "rsi_sell_low": 25,
                   "rsi_sell_high": 45, "rsi_extreme_high": 85,
                   "rsi_extreme_low": 15, "atr_sl_mult": 2.0,
                   "tp_mult": 1.5, "trail_mult": 2.0, "adx_min": 25,
                   "min_atr_pct": 0.0015},
        "BNBUSD": {"sma_fast": 10, "sma_slow": 30, "adx_min": 20,
                   "min_atr_pct": 0.0010},
        "AMD": {"sma_fast": 8, "sma_slow": 21, "rsi_buy_low": 55,
                "rsi_buy_high": 75, "rsi_sell_low": 25,
                "rsi_sell_high": 45, "rsi_extreme_high": 85,
                "rsi_extreme_low": 15, "adx_min": 20,
                "min_atr_pct": 0.0020},
        "NVDA": {"sma_fast": 9, "sma_slow": 21, "rsi_buy_low": 55,
                 "rsi_buy_high": 75, "rsi_sell_low": 25,
                 "rsi_sell_high": 45, "rsi_extreme_high": 85,
                 "rsi_extreme_low": 15, "atr_sl_mult": 2.0,
                 "trail_mult": 2.0, "adx_min": 25,
                 "min_atr_pct": 0.0020},
        "INTC": {"sma_fast": 10, "sma_slow": 30, "rsi_buy_high": 65,
                 "rsi_sell_low": 35, "atr_sl_mult": 2.0, "tp_mult": 1.5,
                 "trail_mult": 2.0, "adx_min": 20,
                 "min_atr_pct": 0.0015},
    }
    desk_of = {"EURUSD": "forex", "XAUUSD": "xauusd",
               "BTCUSD": "crypto", "ETHUSD": "crypto",
               "BNBUSD": "crypto", "AMD": "us_securities",
               "NVDA": "us_securities", "INTC": "us_securities"}
    for symbol, want in expected.items():
        got = resolve_strategy_params(cfg, desk_of[symbol], symbol)
        for key, value in want.items():
            assert got[key] == value, (symbol, key, got[key], value)
    # CDNS / SNPS: khong co ghi de — giu mac dinh chung.
    for symbol in ("CDNS", "SNPS"):
        got = resolve_strategy_params(cfg, "us_securities", symbol)
        assert got["sma_fast"] == 5 and got["sma_slow"] == 20
        assert got["adx_min"] == 0
        assert got["min_atr_pct"] == 0.0  # gate tat (mac dinh chung)


# --- Soft rules: block / require / scale ----------------------------------

def _soft_cfg(rules, desk="forex", symbol="EURUSD"):
    return _cfg(soft_rules=rules)


def test_soft_rule_block_names_rule_in_reason():
    # ADX ~19 <= 20 nen adx_max 20 dung -> block.
    rules = [{"name": "eurusd-weak-trend-block",
              "scope": {"symbol": "EURUSD"},
              "condition": {"type": "adx_max", "value": 20},
              "effect": "block"}]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "HOLD"
    assert "eurusd-weak-trend-block" in sig["reason"]


def test_soft_rule_require_blocks_when_condition_false():
    # Tin hieu BUY (SMA bullish) nhung rule doi sma_cross bearish.
    rules = [{"name": "need-bearish",
              "condition": {"type": "sma_cross", "direction": "bearish"},
              "effect": "require"}]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "HOLD"
    assert "need-bearish" in sig["reason"]


def test_soft_rule_require_passes_when_condition_true():
    rules = [{"name": "need-bullish",
              "condition": {"type": "sma_cross", "direction": "bullish"},
              "effect": "require"}]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "BUY"


def test_soft_rule_scale_halves_size_in_levels():
    # ADX ~19 <= 25 nen scale 0.5 ap dung; ly do + levels neu ten rule.
    rules = [{"name": "weak-adx-scale",
              "condition": {"type": "adx_max", "value": 25},
              "effect": {"type": "scale", "factor": 0.5}}]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "BUY"
    assert sig["levels"]["size_scale"] == 0.5
    assert sig["size_scale"] == 0.5
    assert "weak-adx-scale" in sig["reason"]


def test_soft_rule_scale_never_raises_size():
    # Scale factor > 1 phai bao loi luc validate (khong lang le cat).
    rules = [{"name": "too-big",
              "condition": {"type": "adx_max", "value": 25},
              "effect": {"type": "scale", "factor": 1.5}}]
    with pytest.raises(ValueError, match="scale factor"):
        validate_soft_rules(rules)


def test_soft_rule_pattern_condition():
    # Bars mua co doji (open == close) nhung khong co hammer.
    assert evaluate_condition(
        {"type": "pattern", "name": "doji"},
        {"patterns": [{"name": "doji"}]}) is True
    rules = [{"name": "need-hammer",
              "condition": {"type": "pattern", "name": "hammer"},
              "effect": "require"}]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "HOLD"
    assert "need-hammer" in sig["reason"]
    rules = [{"name": "need-doji",
              "condition": {"type": "pattern", "name": "doji"},
              "effect": "require"}]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "BUY"


def test_soft_rule_scope_filtering():
    rules = [
        {"name": "all-symbols",
         "condition": {"type": "adx_max", "value": 25},
         "effect": {"type": "scale", "factor": 0.5}},
        {"name": "crypto-only", "scope": {"desk": "crypto"},
         "condition": {"type": "adx_max", "value": 25},
         "effect": "block"},
        {"name": "btc-only", "scope": {"symbol": "BTCUSD"},
         "condition": {"type": "adx_max", "value": 25},
         "effect": "block"},
    ]
    cfg = _cfg(soft_rules=rules)
    assert [r["name"] for r in resolve_soft_rules(cfg, "forex", "EURUSD")] \
        == ["all-symbols"]
    assert [r["name"] for r in resolve_soft_rules(cfg, "crypto", "ETHUSD")] \
        == ["all-symbols", "crypto-only"]
    assert [r["name"] for r in resolve_soft_rules(cfg, "crypto", "BTCUSD")] \
        == ["all-symbols", "crypto-only", "btc-only"]
    # Instance theo desk (khong symbol) khong nhan rule scope-symbol.
    strat = build_strategy("crypto", cfg=cfg)
    assert [r["name"] for r in strat.soft_rules] == ["all-symbols",
                                                     "crypto-only"]


# --- Soft rules: validation fail LOUD --------------------------------------

@pytest.mark.parametrize("rules,match", [
    ([{"name": "x", "condition": {"type": "moon_phase"},
       "effect": "block"}], "khong biet"),
    ([{"name": "x", "condition": {"type": "rsi_range", "low": 70,
                                  "high": 50}, "effect": "block"}],
     "phai nho hon high"),
    ([{"name": "x", "condition": {"type": "rsi_range", "low": -5,
                                  "high": 50}, "effect": "block"}],
     "vuot khoang"),
    ([{"name": "x", "condition": {"type": "adx_min", "value": 120},
       "effect": "block"}], "vuot khoang"),
    ([{"name": "x", "condition": {"type": "atr_pct_min", "value": 0},
       "effect": "block"}], "phai > 0"),
    ([{"name": "x", "condition": {"type": "sma_cross",
                                  "direction": "sideways"},
       "effect": "block"}], "direction"),
    ([{"name": "x", "condition": {"type": "pattern", "name": "ufo"},
       "effect": "block"}], "pattern khong biet"),
    ([{"name": "x", "condition": {"type": "adx_min", "value": 20},
       "effect": "scale"}], "scale"),
    ([{"name": "x", "condition": {"type": "adx_min", "value": 20},
       "effect": {"type": "scale", "factor": 0}}], "scale factor"),
    ([{"name": "x", "condition": {"type": "adx_min", "value": 20},
       "effect": "block", "typo_key": 1}], "khoa khong biet"),
    ([{"name": "x", "condition": {"type": "adx_min", "value": 20,
                                  "extra": 1},
       "effect": "block"}], "khoa khong biet"),
    ([{"name": "dup", "condition": {"type": "adx_min", "value": 20},
       "effect": "block"},
      {"name": "dup", "condition": {"type": "adx_min", "value": 20},
       "effect": "block"}], "trung ten"),
    ([{"name": "x", "scope": {"desk": "metals"},
       "condition": {"type": "adx_min", "value": 20},
       "effect": "block"}], "desk khong biet"),
    ([{"name": "x", "scope": {"symbol": "DOGEUSD"},
       "condition": {"type": "adx_min", "value": 20},
       "effect": "block"}], "symbol khong biet"),
    ([{"name": "x", "scope": {"desk": "crypto", "symbol": "BTCUSD"},
       "condition": {"type": "adx_min", "value": 20},
       "effect": "block"}], "chi duoc 1"),
    ([{"condition": {"type": "adx_min", "value": 20},
       "effect": "block"}], "thieu 'name'"),
    ([{"name": "x", "effect": "block"}], "thieu 'condition'"),
    ([{"name": "x", "condition": {"type": "adx_min", "value": 20}}],
     "thieu 'effect'"),
])
def test_soft_rule_validation_rejects(rules, match):
    with pytest.raises(ValueError, match=match):
        validate_soft_rules(rules)


def test_soft_rule_block_runs_before_later_scale():
    # Rule block dung truoc -> HOLD, rule scale sau khong duoc ap.
    rules = [
        {"name": "first-block",
         "condition": {"type": "adx_max", "value": 20},
         "effect": "block"},
        {"name": "later-scale",
         "condition": {"type": "adx_max", "value": 25},
         "effect": {"type": "scale", "factor": 0.5}},
    ]
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD",
                           cfg=_soft_cfg(rules))
    assert sig["action"] == "HOLD"
    assert "first-block" in sig["reason"]
    assert sig["levels"] is None


# --- Backtest / backward compat --------------------------------------------

def test_backtest_applies_soft_scale_to_units():
    bars = SimulatedFeed("crypto").bars(60)
    base = run_backtest("crypto", 60, cfg=_cfg(),
                        symbols=["BTCUSD"], bars=bars)
    scaled_cfg = _cfg(soft_rules=[
        {"name": "always-scale",
         "condition": {"type": "adx_max", "value": 100},
         "effect": {"type": "scale", "factor": 0.5}}])
    scaled = run_backtest("crypto", 60, cfg=scaled_cfg,
                          symbols=["BTCUSD"], bars=bars)
    assert base["trades"] and scaled["trades"]
    assert len(base["trades"]) == len(scaled["trades"])
    for t0, t1 in zip(base["trades"], scaled["trades"]):
        assert t1["size_scale"] == 0.5
        assert t1["units"] == pytest.approx(t0["units"] * 0.5)


def test_backtest_block_rule_removes_trades():
    bars = SimulatedFeed("crypto").bars(60)
    blocked_cfg = _cfg(soft_rules=[
        {"name": "always-block",
         "condition": {"type": "adx_max", "value": 100},
         "effect": "block"}])
    result = run_backtest("crypto", 60, cfg=blocked_cfg,
                          symbols=["BTCUSD"], bars=bars)
    assert result["trades"] == []


def test_no_soft_rules_behaves_as_before():
    cfg = _cfg()
    sig = generate_signals("forex", buy_bars(), symbol="EURUSD", cfg=cfg)
    assert sig["action"] == "BUY"
    assert sig["size_scale"] == 1.0
    assert "size_scale" not in sig["levels"]
    strat = build_strategy_for_symbol(cfg, "forex", "EURUSD")
    assert strat.soft_rules == []
