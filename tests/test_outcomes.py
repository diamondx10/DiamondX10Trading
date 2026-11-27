"""Test outcome logging (outcomes.py) + hook trong live.process_symbol.

Dung MT5 gia + feed gia (fake tu tests/test_live.py), khong can
terminal that, khong co lenh that. Fixture chi dung so gia.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diamondx10 import decisions
from diamondx10.config import load_config
from diamondx10.live import process_symbol
from diamondx10.outcomes import (
    OutcomeStore,
    build_record,
    load,
    log_signal,
)
from diamondx10.pending import PendingOrderStore
from diamondx10.risk import DrawdownGuard
from test_live import FakeLiveFeed, FakeMT5Live, make_guard, trend_bars

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500, "us_securities": 2500}


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG + equity state tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    return log_path, state_path


def _fake_result(**overrides):
    result = {
        "symbol": "EURUSD", "action": "BUY", "status": "TRADED",
        "reason": "SMA5 > SMA20, RSI (59.0) trong 50-70",
        "volume": 0.01, "price": 103.0, "sl": 101.5, "tp": 106.0,
        "risk_usd": 75.0, "manager": "Yuling Pan",
        "time": "2026-11-27T10:00:00+00:00", "fa_note": "FA: buy 0.8",
        "size_scale": 0.5, "pending_id": None,
    }
    result.update(overrides)
    return result


def _fake_sig(**overrides):
    sig = {
        "desk": "forex", "strategy": "default", "action": "BUY",
        "reason": "SMA5 > SMA20, RSI (59.0) trong 50-70",
        "levels": {"entry": 103.0, "sl": 101.5, "tp": 106.0, "atr": 1.0,
                   "size_scale": 0.5},
        "size_scale": 0.5,
        "regime": {"regime": "TRENDING", "direction": "BULLISH",
                   "adx": 28.5, "atr_percentile": 60.0,
                   "volatility": "NORMAL", "confidence": 0.6},
        "patterns": [{"name": "hammer", "direction": "bullish",
                      "strength": 0.8, "bar_index": 59},
                     {"name": "support", "direction": "neutral",
                      "strength": 0.5, "bar_index": 55}],
        "pattern_score": 0.5,
        "symbol": "EURUSD",
        "params": {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14,
                   "atr_sl_mult": 1.5, "tp_mult": 2.0},
        "context": {"rsi": 59.0, "sma_fast": 103.5, "sma_slow": 102.0,
                    "adx": 28.5},
    }
    sig.update(overrides)
    return sig


# ---------------- build_record ----------------

def test_build_record_copies_all_schema_fields():
    record = build_record(_fake_result(), _fake_sig(), cfg=None,
                          desk="forex", symbol="EURUSD")
    assert len(record["id"]) == 8
    assert all(c in "0123456789abcdef" for c in record["id"])
    assert record["created_utc"]
    assert record["desk"] == "forex"
    assert record["symbol"] == "EURUSD"
    assert record["action"] == "BUY"
    assert record["status"] == "TRADED"
    assert record["entry"] == pytest.approx(103.0)
    assert record["sl"] == pytest.approx(101.5)
    assert record["tp"] == pytest.approx(106.0)
    assert record["volume"] == pytest.approx(0.01)
    assert record["risk_usd"] == pytest.approx(75.0)
    assert record["manager"] == "Yuling Pan"
    assert record["time"] == "2026-11-27T10:00:00+00:00"
    assert record["size_scale"] == pytest.approx(0.5)
    assert record["pending_id"] is None
    ctx = record["context"]
    assert ctx["rsi"] == pytest.approx(59.0)
    assert ctx["sma_fast"] == pytest.approx(103.5)
    assert ctx["sma_slow"] == pytest.approx(102.0)
    assert ctx["sma_relation"] == "fast>slow"
    assert ctx["atr"] == pytest.approx(1.0)
    assert ctx["atr_sl_mult"] == pytest.approx(1.5)
    assert ctx["regime"] == "TRENDING"
    assert ctx["adx"] == pytest.approx(28.5)
    assert ctx["patterns"] == ["hammer", "support"]
    assert ctx["pattern_score"] == pytest.approx(0.5)
    assert ctx["strategy_name"] == "default"
    assert ctx["resolved_params"]["atr_sl_mult"] == pytest.approx(1.5)
    assert ctx["soft_rules"] == []
    assert ctx["fa"] == {"direction": "buy", "confidence": 0.8}
    assert record["params_hash"] != "none"
    assert len(record["params_hash"]) == 8


def test_build_record_minimal_sig_never_invents_context():
    record = build_record(_fake_result(fa_note="FA: chua co"),
                          {"action": "BUY", "levels": {"atr": 2.0}},
                          cfg=None, desk="forex", symbol="EURUSD")
    ctx = record["context"]
    assert ctx["rsi"] is None
    assert ctx["sma_fast"] is None
    assert ctx["sma_slow"] is None
    assert ctx["sma_relation"] is None
    assert ctx["atr"] == pytest.approx(2.0)
    assert ctx["atr_sl_mult"] is None
    assert ctx["regime"] is None
    assert ctx["adx"] is None
    assert ctx["patterns"] == []
    assert ctx["pattern_score"] is None
    assert ctx["strategy_name"] == "default"
    assert ctx["resolved_params"] == {}
    assert ctx["soft_rules"] == []
    assert ctx["fa"] is None
    assert record["params_hash"] == "none"


def test_build_record_soft_rules_populated_when_present():
    sig = _fake_sig(soft_rules=[
        {"name": "rsi-cautious", "fired": True, "effect": "scale"},
        {"name": "adx-weak", "fired": False, "effect": "block"},
    ])
    record = build_record(_fake_result(), sig, cfg=None,
                          desk="forex", symbol="EURUSD")
    assert record["context"]["soft_rules"] == [
        {"name": "rsi-cautious", "fired": True, "effect": "scale"},
        {"name": "adx-weak", "fired": False, "effect": "block"},
    ]


def test_build_record_soft_rules_string_list():
    sig = _fake_sig(soft_rules=["rsi-cautious"])
    record = build_record(_fake_result(), sig, cfg=None,
                          desk="forex", symbol="EURUSD")
    assert record["context"]["soft_rules"] == [
        {"name": "rsi-cautious", "fired": True, "effect": None}]


def test_build_record_params_hash_stable_and_sensitive_keys_dropped():
    sig_a = _fake_sig()
    sig_b = _fake_sig(params={"atr_sl_mult": 1.5, "tp_mult": 2.0,
                              "sma_fast": 5, "sma_slow": 20,
                              "rsi_period": 14,
                              "bot_token_env": "NOPE"})
    rec_a = build_record(_fake_result(), sig_a, cfg=None,
                         desk="forex", symbol="EURUSD")
    rec_b = build_record(_fake_result(), sig_b, cfg=None,
                         desk="forex", symbol="EURUSD")
    assert rec_a["params_hash"] == rec_b["params_hash"]
    assert "bot_token_env" not in rec_b["context"]["resolved_params"]
    canonical = json.dumps(rec_a["context"]["resolved_params"],
                           sort_keys=True, ensure_ascii=False, default=str)
    assert rec_a["params_hash"] == hashlib.sha256(
        canonical.encode("utf-8")).hexdigest()[:8]


def test_build_record_fa_note_variants():
    assert build_record(_fake_result(fa_note="FA: cu"), _fake_sig(),
                        None, "forex", "EURUSD")["context"]["fa"] is None
    rec = build_record(_fake_result(fa_note="FA: sell 0.65"), _fake_sig(),
                       None, "forex", "EURUSD")
    assert rec["context"]["fa"] == {"direction": "sell",
                                     "confidence": 0.65}


# ---------------- append / load ----------------

def test_append_load_round_trip_three_records(tmp_path):
    path = tmp_path / "signal-outcomes.jsonl"
    store = OutcomeStore(path)
    records = [build_record(_fake_result(), _fake_sig(), None,
                            "forex", "EURUSD") for _ in range(3)]
    for record in records:
        assert store.append(record) is True
    loaded = store.load()
    assert len(loaded) == 3
    assert [r["id"] for r in loaded] == [r["id"] for r in records]
    assert load(path)[2]["entry"] == pytest.approx(103.0)


def test_load_missing_file_is_empty(tmp_path):
    assert load(tmp_path / "khong-co.jsonl") == []
    assert OutcomeStore(tmp_path / "khong-co.jsonl").load() == []


def test_load_skips_corrupt_lines(tmp_path):
    path = tmp_path / "signal-outcomes.jsonl"
    good = build_record(_fake_result(), _fake_sig(), None,
                        "forex", "EURUSD")
    path.write_text(json.dumps(good, ensure_ascii=False) + "\n"
                    + "{dong hong\n"
                    + json.dumps(good, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    loaded = load(path)
    assert len(loaded) == 2
    assert all(r["id"] == good["id"] for r in loaded)


def test_log_signal_failure_warns_and_does_not_raise(tmp_path, capsys):
    bad_path = tmp_path / "thu-muc-khong-co" / "signal-outcomes.jsonl"
    record = build_record(_fake_result(), _fake_sig(), None,
                          "forex", "EURUSD")
    assert log_signal(bad_path, record) is False
    assert OutcomeStore(bad_path).append(record) is False
    assert "Canh bao outcomes" in capsys.readouterr().out
    assert not bad_path.exists()


# ---------------- hook trong live.process_symbol ----------------

def _call_process_symbol(cfg, mt5, feed, outcome_store, tmp_path,
                         guard=None, positions=None, **kwargs):
    guard = guard if guard is not None else make_guard()
    positions = positions if positions is not None else []
    return process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5,
        account=mt5.account_info(), server="Exness-MT5Trial7",
        manager="Yuling Pan", guard=guard, positions=positions,
        volume=0.01, per_symbol_cap=2500.0, outcome_store=outcome_store,
        **kwargs)


def test_hook_traded_writes_exactly_one_record(tmp_decisions, tmp_path):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path)
    assert result["status"] == "TRADED"
    records = load(outcome_path)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "TRADED"
    assert record["action"] == "BUY"
    assert record["symbol"] == "EURUSD"
    assert record["entry"] == pytest.approx(103.0)
    assert record["sl"] == pytest.approx(101.5)
    assert record["tp"] == pytest.approx(106.0)
    assert record["volume"] == pytest.approx(0.01)
    assert record["risk_usd"] == pytest.approx(75.0)
    assert record["pending_id"] is None
    ctx = record["context"]
    assert ctx["atr"] == pytest.approx(1.0)
    assert ctx["atr_sl_mult"] == pytest.approx(1.5)
    assert isinstance(ctx["regime"], str) and ctx["regime"]
    assert isinstance(ctx["adx"], float)
    assert isinstance(ctx["patterns"], list)
    assert ctx["pattern_score"] is not None
    assert ctx["strategy_name"] == "ForexTrend (Yuling — Forex)"
    assert ctx["resolved_params"]["atr_sl_mult"] == pytest.approx(1.5)
    assert ctx["soft_rules"] == []
    assert ctx["fa"] is None  # chua co nhan dinh PTCB
    assert record["params_hash"] != "none"


def test_hook_recommended_writes_exactly_one_record(tmp_decisions, tmp_path):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    pending = PendingOrderStore(tmp_path / "pending-orders.json")
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path,
                                  recommend_only=True,
                                  pending_store=pending)
    assert result["status"] == "RECOMMENDED"
    assert result["pending_id"]
    assert mt5.sent_orders == []  # khuyen nghi thi khong dat lenh
    records = load(outcome_path)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "RECOMMENDED"
    assert record["action"] == "BUY"
    assert record["entry"] == pytest.approx(103.0)
    assert record["pending_id"] == result["pending_id"]
    assert record["context"]["atr"] == pytest.approx(1.0)


def test_hook_held_writes_nothing(tmp_decisions, tmp_path):
    from test_live import flat_bars

    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(flat_bars(), latest=103.2, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path)
    assert result["status"] == "HELD"
    assert load(outcome_path) == []
