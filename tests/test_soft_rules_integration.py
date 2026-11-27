"""Test tich hop quy tac cung + quy tac mem TA (hard/soft rules) —
phan engine child CHUA viet (xem tests/test_soft_rules.py).

Phan nay bao phu, o muc tich hop:
  (a) bang per_symbol doc tu config.example.yaml THAT, theo thu tu
      uu tien mac dinh < chung < desk < symbol;
  (b) soft rule chan tin hieu trong vong live (process_symbol);
  (c) soft rule scale giam volume trong vong live (ke ca gioi han
      lam tron xuong buoc 0.01 lot);
  (d) compare/sweep ton trong soft rule;
  (e) soft rule go sai trong YAML bao loi LOUD o duong resolve
      (load_config chi kiem tra quy tac cung — xem ghi chu o test);
  (g) 3 rule vi du (comment) trong config.example.yaml chay dung
      nhu viet.

KHONG lap lai tests/test_soft_rules.py: gate adx_min/min_atr_pct,
validate_soft_rules don le, block/scale qua generate_signals,
backtest scale units, va (f) config khong co khoa moi chay nhu cu
(test_no_soft_rules_behaves_as_before + test_gates_default_off_
backward_compatible o file do) — o day chi trich dan, khong viet lai.

Fixture: so gia / chat_id GIA (khong dung so that cua user).
"""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.backtest import compare_strategies, sweep_params
from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed
from diamondx10.live import process_symbol
from diamondx10.risk import DrawdownGuard
from diamondx10.signals import generate_signals
from diamondx10.strategies import (
    build_strategy_for_symbol,
    resolve_strategy_params,
)

REPO = Path(__file__).resolve().parents[1]
DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500,
         "us_securities": 2500}


def trend_bars(pattern=(0.2, 0.2, -0.25), n=60, start=100.0):
    """Nen theo mau tang lap lai — cho tin hieu BUY that
    (RSI ~59, SMA5 > SMA20, ADX(14) ~19), giong tests/test_live.py."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class FakeMT5:
    """MT5 gia cho live: tai khoan demo, order_check luon du ky quy."""

    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, server="Exness-MT5Trial7"):
        self._server = server
        self.sent_orders = []

    def initialize(self, path=None):
        return True

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol)

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=103.0, ask=103.1)

    def account_info(self):
        return SimpleNamespace(trade_mode=0, server=self._server,
                               demo=True)

    def history_deals_get(self, *args, **kwargs):
        return []

    def order_check(self, request):
        return SimpleNamespace(retcode=0)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=777001,
                               comment="Done")

    def shutdown(self):
        return True


class FakeFeed:
    """Feed gia: bars/latest thay doi duoc, co mt5 + account_info demo."""

    def __init__(self, bars_data, latest, mt5=None):
        self.bars_data = bars_data
        self._latest = latest
        self.mt5 = mt5

    def bars(self, n=60):
        return list(self.bars_data[-n:])

    def latest_price(self, symbol=None):
        return self._latest

    def account_info(self):
        return self.mt5.account_info() if self.mt5 is not None else None

    def close(self):
        return True


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG + equity state tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    return tmp_path


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


def _cfg_from_example():
    """Config doc tu config.example.yaml THAT (khong phai ban che)."""
    with open(REPO / "config.example.yaml", encoding="utf-8") as f:
        example = yaml.safe_load(f)
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": example["data"]["symbols"]}
    cfg["strategy"] = example["strategy"]
    cfg["backtest"] = {"fee_pct": 0.0, "slippage_pct": 0.0}
    return cfg


def _run_live(cfg, tmp_path, mt5=None, feed=None, volume=None,
              per_symbol_cap=2500.0, desk="forex", symbol="EURUSD",
              manager="Yuling Pan"):
    """Chay process_symbol 1 lan tren feed gia, kho verdict rong."""
    mt5 = mt5 or FakeMT5()
    feed = feed or FakeFeed(trend_bars(), latest=103.0, mt5=mt5)
    guard = DrawdownGuard(10000, DESKS, max_drawdown_pct=10.0,
                          desk_warning_pct=5.0)
    positions = []
    result = process_symbol(
        cfg, desk, symbol, feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager=manager, guard=guard, positions=positions,
        volume=volume, per_symbol_cap=per_symbol_cap,
        verdict_store=str(tmp_path / "verdicts.json"))
    return result, mt5, positions


# --- (a) Bang per_symbol tu config.example.yaml THAT -----------------------

def test_per_symbol_priority_from_real_example_yaml():
    cfg = _cfg_from_example()
    # EURUSD: symbol thang chung (SMA 8/21 thay 5/20, ADX 20, ATR%
    # 0.0001); RSI thua huong chung 50-70.
    eur = resolve_strategy_params(cfg, "forex", "EURUSD")
    assert (eur["sma_fast"], eur["sma_slow"]) == (8, 21)
    assert eur["adx_min"] == 20 and eur["min_atr_pct"] == 0.0001
    assert (eur["rsi_buy_low"], eur["rsi_buy_high"]) == (50, 70)
    assert eur["atr_sl_mult"] == 1.5  # khong ghi de -> chung
    # XAUUSD: symbol thang chung (SMA 10/30, RSI 55-75, TP 1.5 thay 2.0).
    xau = resolve_strategy_params(cfg, "xauusd", "XAUUSD")
    assert (xau["sma_fast"], xau["sma_slow"]) == (10, 30)
    assert (xau["rsi_buy_low"], xau["rsi_buy_high"]) == (55, 75)
    assert (xau["rsi_sell_low"], xau["rsi_sell_high"]) == (25, 45)
    assert xau["tp_mult"] == 1.5 and xau["atr_sl_mult"] == 2.0
    assert xau["adx_min"] == 30 and xau["min_atr_pct"] == 0.0003
    # BTCUSD: symbol thang chung (SMA 9/21, RSI 55-75, ADX 25).
    btc = resolve_strategy_params(cfg, "crypto", "BTCUSD")
    assert (btc["sma_fast"], btc["sma_slow"]) == (9, 21)
    assert (btc["rsi_buy_low"], btc["rsi_buy_high"]) == (55, 75)
    assert btc["adx_min"] == 25 and btc["min_atr_pct"] == 0.0010
    # BNBUSD: khong ghi de ATR -> thua huong DESK crypto (2.0 thang
    # chung 1.5); TP thua huong chung 2.0 (desk khong ghi de TP).
    bnb = resolve_strategy_params(cfg, "crypto", "BNBUSD")
    assert bnb["atr_sl_mult"] == 2.0 and bnb["trail_mult"] == 2.0
    assert bnb["tp_mult"] == 2.0
    # NVDA (1 ma chung khoan My): symbol thang chung.
    nvda = resolve_strategy_params(cfg, "us_securities", "NVDA")
    assert (nvda["sma_fast"], nvda["sma_slow"]) == (9, 21)
    assert nvda["atr_sl_mult"] == 2.0 and nvda["adx_min"] == 25
    assert nvda["min_atr_pct"] == 0.0020
    # ETHUSD: TP 1.5 la ghi de symbol (khac chung 2.0), khac BTC.
    eth = resolve_strategy_params(cfg, "crypto", "ETHUSD")
    assert eth["tp_mult"] == 1.5 and eth["min_atr_pct"] == 0.0015


def test_symbol_override_beats_desk_override_on_real_example():
    # Them ghi de desk crypto 2.5 vao ban sao cua bang that: symbol
    # (BTC 2.0) phai thang desk; BNB (khong ghi de symbol) lay desk.
    cfg = _cfg_from_example()
    cfg["strategy"]["desks"] = {"crypto": {"atr_sl_mult": 2.5}}
    assert resolve_strategy_params(cfg, "crypto", "BTCUSD")[
        "atr_sl_mult"] == 2.0
    assert resolve_strategy_params(cfg, "crypto", "ETHUSD")[
        "atr_sl_mult"] == 2.0
    assert resolve_strategy_params(cfg, "crypto", "BNBUSD")[
        "atr_sl_mult"] == 2.5


# --- (b) Soft rule chan tin hieu trong vong live ---------------------------

def test_live_soft_rule_blocks_signal_end_to_end(tmp_decisions):
    # ADX(14) cua bars nay ~22.4: adx_max 25 dung -> block.
    rules = [{"name": "eurusd-weak-trend-block",
              "scope": {"symbol": "EURUSD"},
              "condition": {"type": "adx_max", "value": 25},
              "effect": "block"}]
    cfg = _cfg(soft_rules=rules)
    result, mt5, positions = _run_live(cfg, tmp_decisions)
    assert result["status"] == "HELD"
    assert result["action"] == "HOLD"
    assert "eurusd-weak-trend-block" in result["reason"]
    assert mt5.sent_orders == []
    assert positions == []


def test_live_same_bars_trade_without_rule(tmp_decisions):
    # Doi chung cho test chan o tren: cung bars, khong rule -> TRADED.
    # Von/symbol 2.500 USD cho vol 0 nen truyen volume 0.01 nhu
    # tests/test_live.py (volume tay chi de doi chung, khong phai
    # phan test scale).
    result, mt5, positions = _run_live(_cfg(), tmp_decisions,
                                       volume=0.01,
                                       per_symbol_cap=2500.0)
    assert result["status"] == "TRADED"
    assert result["action"] == "BUY"
    assert len(mt5.sent_orders) == 1
    assert len(positions) == 1


# --- (c) Soft rule scale giam volume trong vong live ------------------------

def test_live_soft_rule_scale_reduces_volume(tmp_decisions, monkeypatch):
    # Von/symbol 150.000 USD (fixture GIA): risk 3% = 4.500 USD,
    # SL 1.5 x ATR(~1.0) tren contract forex 100.000 -> vol goc 0.03.
    # Scale 0.5 -> int(0.03*0.5*100)/100 = 0.01 lot, risk 2.250 USD.
    rules = [{"name": "weak-adx-scale",
              "condition": {"type": "adx_max", "value": 25},
              "effect": {"type": "scale", "factor": 0.5}}]
    base, _, _ = _run_live(_cfg(), tmp_decisions,
                           per_symbol_cap=150000.0)
    assert base["status"] == "TRADED" and base["volume"] == 0.03
    assert base["risk_usd"] == pytest.approx(4500.0)
    assert base["size_scale"] == 1.0
    # Lan chay thu 2 ghi vao LOG moi: khong thi gioi han
    # 1 lenh/symbol/ngay (tinh tu LOG) chan no.
    monkeypatch.setattr(decisions, "LOG",
                        tmp_decisions / "decisions-log-2.csv")
    scaled, mt5, _ = _run_live(_cfg(soft_rules=rules), tmp_decisions,
                               per_symbol_cap=150000.0)
    assert scaled["status"] == "TRADED"
    assert scaled["size_scale"] == 0.5
    assert scaled["volume"] == 0.01
    assert scaled["risk_usd"] == pytest.approx(2250.0)
    assert mt5.sent_orders[0]["volume"] == 0.01


def test_live_scale_below_min_lot_blocks_instead_of_rounding_up(
        tmp_decisions):
    # Vol goc 0.01 lot (von/symbol 50.000 USD): scale 0.5 -> 0.005,
    # lam tron XUONG buoc 0.01 ra 0.0 -> KHONG dat lenh (khong lam
    # tron LEN thanh 0.01), tra BLOCKED-VOLUME-ZERO.
    rules = [{"name": "weak-adx-scale",
              "condition": {"type": "adx_max", "value": 25},
              "effect": {"type": "scale", "factor": 0.5}}]
    result, mt5, _ = _run_live(_cfg(soft_rules=rules), tmp_decisions,
                               per_symbol_cap=50000.0)
    assert result["status"] == "BLOCKED-VOLUME-ZERO"
    assert mt5.sent_orders == []


def test_live_manual_volume_override_not_scaled(tmp_decisions):
    # volume truyen tay la ghi de thu cong: soft rule scale KHONG
    # doi no (chi size tu dong moi bi scale); size_scale van ghi.
    rules = [{"name": "weak-adx-scale",
              "condition": {"type": "adx_max", "value": 25},
              "effect": {"type": "scale", "factor": 0.5}}]
    result, mt5, _ = _run_live(_cfg(soft_rules=rules), tmp_decisions,
                               volume=0.05, per_symbol_cap=150000.0)
    assert result["status"] == "TRADED"
    assert result["volume"] == 0.05
    assert result["size_scale"] == 0.5
    assert mt5.sent_orders[0]["volume"] == 0.05


# --- (d) compare / sweep ton trong soft rule ---------------------------------

def test_compare_with_block_rule_zeroes_oos_trades():
    # Cua so walk-forward train 60 / test 20 tren 120 bar: ban khong
    # rule co lenh OOS (cua so nho 30/10 cho 0 lenh OOS tren du lieu
    # mo phong nay nen khong dung lam doi chung duoc).
    bars = SimulatedFeed("forex").bars(120)
    cfg = _cfg(symbols={"forex": ["EURUSD"]})
    base = compare_strategies("forex", ["default"], cfg=cfg,
                              symbols=["EURUSD"], train_bars=60,
                              test_bars=20, step_bars=20, bars=bars)
    assert base["rows"][0]["oos_n_trades"] > 0
    blocked_cfg = _cfg(symbols={"forex": ["EURUSD"]}, soft_rules=[
        {"name": "always-block",
         "condition": {"type": "adx_max", "value": 100},
         "effect": "block"}])
    blocked = compare_strategies("forex", ["default"], cfg=blocked_cfg,
                                 symbols=["EURUSD"], train_bars=60,
                                 test_bars=20, step_bars=20, bars=bars)
    assert blocked["rows"][0]["oos_n_trades"] == 0
    assert blocked["rows"][0]["oos_total_pnl"] == pytest.approx(0.0)


def test_sweep_with_scale_rule_keeps_trade_count():
    bars = SimulatedFeed("forex").bars(120)
    grid = {"atr_sl_mult": [1.0, 2.0], "rsi_buy_low": [45, 50]}
    cfg = _cfg(symbols={"forex": ["EURUSD"]})
    base = sweep_params("forex", bars, "default", grid, cfg=cfg,
                        symbols=["EURUSD"], train_bars=60, test_bars=20,
                        step_bars=20)
    scaled_cfg = _cfg(symbols={"forex": ["EURUSD"]}, soft_rules=[
        {"name": "always-scale",
         "condition": {"type": "adx_max", "value": 100},
         "effect": {"type": "scale", "factor": 0.5}}])
    scaled = sweep_params("forex", bars, "default", grid, cfg=scaled_cfg,
                          symbols=["EURUSD"], train_bars=60, test_bars=20,
                          step_bars=20)
    assert scaled["n_combinations"] == base["n_combinations"] == 4
    # Scale chi giam size, khong xoa lenh: so lenh OOS moi to hop
    # giong het ban khong rule.
    base_trades = sorted(e["test"]["n_trades"] for e in base["results"])
    scaled_trades = sorted(e["test"]["n_trades"]
                           for e in scaled["results"])
    assert scaled_trades == base_trades
    assert sum(scaled_trades) > 0


# --- (e) Soft rule go sai trong YAML bao loi LOUD o duong resolve -----------

@pytest.mark.parametrize("rules,match", [
    ([{"name": "x", "condition": {"type": "moon_phase"},
       "effect": "block"}], "khong biet"),
    ([{"name": "x", "scope": {"symbol": "DOGEUSD"},
       "condition": {"type": "adx_min", "value": 20},
       "effect": "block"}], "symbol khong biet"),
    ([{"name": "x", "condition": {"type": "adx_max", "value": 25},
       "effect": {"type": "scale", "factor": 1.5}}], "scale factor"),
])
def test_invalid_soft_rule_yaml_fails_loud_at_resolve(tmp_path, rules,
                                                      match):
    # GHI CHU: load_config() chi kiem tra quy tac CUNG (hard key) khi
    # doc file — soft rule go sai van doc duoc; loi chi no ra khi
    # resolve (build_strategy_for_symbol / resolve_soft_rules), la
    # duong moi noi dung tin hieu/live/backtest deu di qua. Test nay
    # khang dinh duong do bao loi LOUD, neu ro khoa loi, thay vi lang
    # le chay khong co rule.
    cfg = _cfg(soft_rules=rules)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    from diamondx10.config import load_config
    loaded = load_config(str(path))  # doc duoc: chua resolve soft rule
    assert loaded["strategy"]["soft_rules"] == rules
    with pytest.raises(ValueError, match=match):
        build_strategy_for_symbol(loaded, "forex", "EURUSD")


# --- (g) 3 rule vi du (comment) trong config.example.yaml --------------------

def test_commented_example_rules_work_as_written():
    # 2 rule vi du tu config.example.yaml (ban sao nguyen van).
    # Rule EURUSD (eurusd-weak-trend-block) da co trong
    # tests/test_soft_rules.py::test_soft_rule_block_names_rule_in_reason.
    cfg = _cfg(soft_rules=[
        {"name": "xauusd-vol-spike-block",
         "scope": {"symbol": "XAUUSD"},
         "condition": {"type": "atr_pct_min", "value": 0.005},
         "effect": "block"},
        {"name": "crypto-adx-weak-scale", "scope": {"desk": "crypto"},
         "condition": {"type": "adx_max", "value": 25},
         "effect": {"type": "scale", "factor": 0.5}},
    ])
    # XAUUSD: ATR/gia ~0.0097 >= 0.005 -> block, ly do neu ten rule.
    sig = generate_signals("xauusd", trend_bars(), symbol="XAUUSD",
                           cfg=cfg)
    assert sig["action"] == "HOLD"
    assert "xauusd-vol-spike-block" in sig["reason"]
    # Crypto: ADX ~19 <= 25 -> scale 0.5, van BUY.
    sig = generate_signals("crypto", trend_bars(), symbol="BTCUSD",
                           cfg=cfg)
    assert sig["action"] == "BUY"
    assert sig["size_scale"] == 0.5
    assert "crypto-adx-weak-scale" in sig["reason"]
