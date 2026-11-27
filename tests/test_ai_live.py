"""Test tich hop live cho mo hinh AI outcome (muc 65).

Dung mo hinh gia / loader gia + nen gia — khong can torch that,
khong can MT5, khong mang. Chi 1 test dung torch that
(test_real_tiny_model_end_to_end) va tu skip khi chua cai torch.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.ai import live_hook
from diamondx10.ai.features import FEATURE_NAMES, FEATURE_VERSION
from diamondx10.ai.model import TorchNotAvailable
from diamondx10.ai.params import PARAM_FEATURE_NAMES, PARAM_FEATURE_VERSION
from diamondx10.config import load_config
from diamondx10.live import process_symbol
from diamondx10.outcomes import build_record, load as load_outcomes
from diamondx10.risk import DrawdownGuard

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500,
         "us_securities": 2500}


def trend_bars(pattern=(0.2, 0.2, -0.25), n=100, start=100.0):
    """Nen theo mau tang lap lai — cho tin hieu BUY that."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


def flat_bars(n=100, close=103.2):
    """Nen di ngang — SMA5 == SMA20 nen tin hieu HOLD."""
    return [{"time": 1700000000 + i * 900, "open": close,
             "high": close + 0.5, "low": close - 0.5, "close": close}
            for i in range(n)]


class FakeMT5Live:
    """MT5 gia cho live: tai khoan demo, order_check tuy chinh duoc."""

    TIMEFRAME_M15 = 15
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 1

    def __init__(self, trade_mode=0, server="Exness-MT5Trial7",
                 order_check_retcode=0):
        self._trade_mode = trade_mode
        self._server = server
        self._order_check_retcode = order_check_retcode
        self.sent_orders = []

    def initialize(self, path=None):
        return True

    def login(self, login, password="x", server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol)

    def symbol_select(self, symbol, enable):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return [{"time": 1700000000 + i * 900, "open": 100.0,
                 "high": 100.5, "low": 99.5, "close": 100.0}
                for i in range(count)]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=103.0, ask=103.1)

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode,
                               server=self._server, demo=True)

    def history_deals_get(self, *args, **kwargs):
        return []

    def order_check(self, request):
        return SimpleNamespace(retcode=self._order_check_retcode)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=777001,
                               comment="Done")

    def shutdown(self):
        return True


class FakeLiveFeed:
    """Feed gia: bars/latest thay doi duoc, co mt5 + account_info demo."""

    def __init__(self, bars_data, latest, mt5=None):
        self.bars_data = bars_data
        self._latest = latest
        self.mt5 = mt5
        self.bars_requested = []

    def bars(self, n=60):
        self.bars_requested.append(n)
        return list(self.bars_data[-n:])

    def latest_price(self, symbol=None):
        return self._latest

    def account_info(self):
        return self.mt5.account_info() if self.mt5 is not None else None

    def close(self):
        return True


@pytest.fixture(autouse=True)
def _clear_ai_cache():
    live_hook.clear_ai_cache()
    yield
    live_hook.clear_ai_cache()


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG + equity state tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    return log_path, state_path


def make_guard():
    return DrawdownGuard(10000, DESKS, max_drawdown_pct=10.0,
                         desk_warning_pct=5.0)


def cfg_with_models(tmp_path, **ai_overrides):
    """Config that + muc ai tro ve thu muc model tam."""
    cfg = load_config()
    ai_cfg = {"models_dir": str(tmp_path / "models"),
              "seq_len": 32,
              "block_on_low_win_prob": False,
              "min_win_prob": 0.30,
              "max_age_days": 90}
    ai_cfg.update(ai_overrides)
    cfg["ai"] = ai_cfg
    return cfg


def write_model_files(tmp_path, symbol="EURUSD", **sidecar_overrides):
    """Ghi .pt gia + sidecar JSON hop le vao thu muc model tam."""
    models_dir = Path(tmp_path / "models")
    models_dir.mkdir(parents=True, exist_ok=True)
    sidecar = {"symbol": symbol, "label_mode": "tp_sl",
               "classes": ["sl_first", "timeout", "tp_first"],
               "feature_version": FEATURE_VERSION,
               "feature_names": list(FEATURE_NAMES),
               "param_feature_names": list(PARAM_FEATURE_NAMES),
               "param_feature_version": PARAM_FEATURE_VERSION,
               "mean": None, "std": None, "seq_len": 32,
               "trained_at": datetime.now(timezone.utc).isoformat(),
               "bars_used": 5000, "walkforward_metrics": None,
               "oos_metrics": None, "torch_version": "2.15.0+cpu"}
    sidecar.update(sidecar_overrides)
    (models_dir / f"{symbol}.pt").write_bytes(b"fake-weights")
    (models_dir / f"{symbol}.json").write_text(
        json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    return models_dir / f"{symbol}.pt", models_dir / f"{symbol}.json", sidecar


def install_fake_model(monkeypatch, tmp_path, probs=(0.1, 0.2, 0.7),
                       **sidecar_overrides):
    """Ghi file mo hinh gia + monkeypatch loader/predictor gia.

    probs: [P(sl_first), P(timeout), P(tp_first)] theo thu tu lop
    trong sidecar. Tra (pt_path, json_path, sidecar, calls).
    """
    _pt, _js, sidecar = write_model_files(
        tmp_path, **sidecar_overrides)
    calls = {"load": 0}

    def fake_load(pt_path, json_path):
        calls["load"] += 1
        return object(), dict(sidecar)

    def fake_predict(model, X):
        assert len(X) == 1 and len(X[0]) == 32 and len(X[0][0]) == 48
        return [list(probs)]

    monkeypatch.setattr(live_hook, "load_model_fn", fake_load)
    monkeypatch.setattr(live_hook, "predict_proba_fn", fake_predict)
    return _pt, _js, sidecar, calls


def call_process_symbol(cfg, mt5, feed, guard=None, positions=None,
                        tmp_path=None, **kwargs):
    guard = guard if guard is not None else make_guard()
    positions = positions if positions is not None else []
    account = mt5.account_info()
    outcome_store = (str(tmp_path / "outcomes.jsonl")
                     if tmp_path is not None else None)
    return process_symbol(
        cfg, "forex", "EURUSD", feed=feed, mt5=mt5, account=account,
        server="Exness-MT5Trial7", manager="Yuling Pan", guard=guard,
        positions=positions, volume=0.01, per_symbol_cap=2500.0,
        outcome_store=outcome_store, **kwargs)


# ---------------- hook: suy giam an toan ----------------

def test_absent_model_returns_none_and_warns_once(tmp_path, capfd):
    cfg = cfg_with_models(tmp_path)
    bars = trend_bars()
    assert live_hook.predict_win_prob(cfg, "EURUSD", bars, "BUY") is None
    assert live_hook.predict_win_prob(cfg, "EURUSD", bars, "BUY") is None
    out = capfd.readouterr().out
    assert out.count("chua co mo hinh outcome") == 1
    assert "Traceback" not in out


def test_corrupt_weights_degrade_without_crash(tmp_path, capfd):
    cfg = cfg_with_models(tmp_path)
    write_model_files(tmp_path)  # sidecar hop le, .pt la rac
    assert live_hook.predict_win_prob(
        cfg, "EURUSD", trend_bars(), "BUY") is None
    out = capfd.readouterr().out
    assert "Traceback" not in out
    assert "EURUSD" in out  # co 1 dong canh bao ghi ro symbol


def test_torch_absent_degrades_cleanly(tmp_path, monkeypatch, capfd):
    cfg = cfg_with_models(tmp_path)
    write_model_files(tmp_path)

    def no_torch(pt_path, json_path):
        raise TorchNotAvailable("torch chua cai — chay ai-setup")

    monkeypatch.setattr(live_hook, "load_model_fn", no_torch)
    assert live_hook.predict_win_prob(
        cfg, "EURUSD", trend_bars(), "BUY") is None
    out = capfd.readouterr().out
    assert "ai-setup" in out
    assert "Traceback" not in out


def test_stale_model_degrades_and_loader_not_called(tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    write_model_files(tmp_path, trained_at=old)
    called = {"n": 0}

    def counting_load(pt_path, json_path):
        called["n"] += 1
        return object(), {}

    monkeypatch.setattr(live_hook, "load_model_fn", counting_load)
    assert live_hook.predict_win_prob(
        cfg, "EURUSD", trend_bars(), "BUY") is None
    assert called["n"] == 0  # het han thi khong dong den weights


def test_not_enough_bars_returns_none(tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path)
    install_fake_model(monkeypatch, tmp_path)
    # 60 bar < 81 bar can thiet (50 cua so + 32 chuoi - 1).
    assert live_hook.predict_win_prob(
        cfg, "EURUSD", trend_bars(n=60), "BUY") is None


def test_hold_gets_no_prediction(tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path)
    install_fake_model(monkeypatch, tmp_path)
    sig = {"action": "HOLD", "reason": "cho"}
    assert live_hook.attach_ai_prediction(
        cfg, "EURUSD", trend_bars(), sig) is None
    assert "ai_win_prob" not in sig


# ---------------- hook: du doan ----------------

def test_fake_model_prediction_canonical_order(tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path)
    # Sidecar xep lop theo thu tu khac — ket qua van ve chuan
    # [P(sl), P(timeout), P(tp)].
    install_fake_model(
        monkeypatch, tmp_path, probs=(0.7, 0.1, 0.2),
        classes=["tp_first", "sl_first", "timeout"])
    pred = live_hook.predict_win_prob(cfg, "EURUSD", trend_bars(), "BUY")
    assert pred is not None
    assert pred["ai_win_prob"] == pytest.approx(0.7)
    assert pred["ai_probs"] == pytest.approx([0.1, 0.2, 0.7])
    assert "202" in pred["ai_model_version"]  # trained_at
    assert "feature v1" in pred["ai_model_version"]
    assert "params v1" in pred["ai_model_version"]


def test_model_load_cached_once_per_process(tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path)
    _pt, _js, _sidecar, calls = install_fake_model(monkeypatch, tmp_path)
    live_hook.predict_win_prob(cfg, "EURUSD", trend_bars(), "BUY")
    live_hook.predict_win_prob(cfg, "EURUSD", trend_bars(), "BUY")
    assert calls["load"] == 1


def test_should_block_ai_defaults_and_opt_in():
    assert live_hook.should_block_ai({}, {"ai_win_prob": 0.01}) is False
    cfg_on = {"ai": {"block_on_low_win_prob": True, "min_win_prob": 0.30}}
    assert live_hook.should_block_ai(cfg_on, {"ai_win_prob": 0.05}) is True
    assert live_hook.should_block_ai(cfg_on, {"ai_win_prob": 0.70}) is False
    assert live_hook.should_block_ai(cfg_on, None) is False


def test_bars_needed_only_when_model_files_exist(tmp_path):
    cfg = cfg_with_models(tmp_path)
    assert live_hook.bars_needed(cfg, "EURUSD") is None
    write_model_files(tmp_path)
    assert live_hook.bars_needed(cfg, "EURUSD") == 81


# ---------------- outcomes log ----------------

def test_outcome_record_carries_ai_fields():
    result = {"action": "BUY", "status": "TRADED", "price": 103.0,
              "sl": 101.5, "tp": 106.0, "volume": 0.01,
              "ai_win_prob": 0.7, "ai_probs": [0.1, 0.2, 0.7],
              "ai_model_version": "2026-11-27T00:00:00+00:00 "
                                  "(feature v1, params v1)"}
    sig = {"action": "BUY", "reason": "x", "levels": {"atr": 1.0},
           "params": {}}
    record = build_record(result, sig, {}, "forex", "EURUSD")
    assert record["context"]["ai_win_prob"] == pytest.approx(0.7)
    assert record["context"]["ai_probs"] == pytest.approx([0.1, 0.2, 0.7])
    assert "feature v1" in record["context"]["ai_model_version"]


def test_outcome_record_without_ai_is_unchanged():
    result = {"action": "BUY", "status": "TRADED", "price": 103.0,
              "sl": 101.5, "tp": 106.0, "volume": 0.01}
    sig = {"action": "BUY", "reason": "x", "levels": {"atr": 1.0},
           "params": {}}
    record = build_record(result, sig, {}, "forex", "EURUSD")
    assert "ai_win_prob" not in record["context"]
    assert "ai_probs" not in record["context"]
    assert "ai_model_version" not in record["context"]


def test_outcome_record_rejects_malformed_ai_probs():
    result = {"action": "BUY", "status": "TRADED",
              "ai_win_prob": 0.7, "ai_probs": [0.5]}
    sig = {"action": "BUY", "reason": "x", "levels": {"atr": 1.0},
           "params": {}}
    record = build_record(result, sig, {}, "forex", "EURUSD")
    assert record["context"]["ai_win_prob"] == pytest.approx(0.7)
    assert "ai_probs" not in record["context"]


# ---------------- live tich hop ----------------

def test_live_trades_with_ai_context_by_default(tmp_decisions, tmp_path,
                                                monkeypatch):
    cfg = cfg_with_models(tmp_path)
    install_fake_model(monkeypatch, tmp_path, probs=(0.1, 0.2, 0.7))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    positions = []
    result = call_process_symbol(cfg, mt5, feed, positions=positions,
                                 tmp_path=tmp_path,
                                 bars=trend_bars())
    assert result["status"] == "TRADED"
    assert result["action"] == "BUY"
    assert len(mt5.sent_orders) == 1  # hanh vi dat lenh khong doi
    assert result["ai_win_prob"] == pytest.approx(0.7)
    assert result["ai_probs"] == pytest.approx([0.1, 0.2, 0.7])
    assert "feature v1" in result["ai_model_version"]
    records = load_outcomes(tmp_path / "outcomes.jsonl")
    assert len(records) == 1
    assert records[0]["context"]["ai_win_prob"] == pytest.approx(0.7)
    assert records[0]["context"]["ai_probs"] == pytest.approx(
        [0.1, 0.2, 0.7])
    assert "feature v1" in records[0]["context"]["ai_model_version"]


def test_live_low_win_prob_still_trades_by_default(tmp_decisions, tmp_path,
                                                   monkeypatch):
    cfg = cfg_with_models(tmp_path)  # block_on_low_win_prob mac dinh False
    install_fake_model(monkeypatch, tmp_path, probs=(0.9, 0.05, 0.05))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path,
                                 bars=trend_bars())
    assert result["status"] == "TRADED"
    assert result["ai_win_prob"] == pytest.approx(0.05)
    assert len(mt5.sent_orders) == 1


def test_live_opt_in_block_low_win_prob(tmp_decisions, tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path, block_on_low_win_prob=True,
                          min_win_prob=0.30)
    install_fake_model(monkeypatch, tmp_path, probs=(0.9, 0.05, 0.05))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    positions = []
    result = call_process_symbol(cfg, mt5, feed, positions=positions,
                                 tmp_path=tmp_path, bars=trend_bars())
    assert result["status"] == "BLOCKED-AI-LOW-WIN-PROB"
    assert result["ai_win_prob"] == pytest.approx(0.05)
    assert len(mt5.sent_orders) == 0
    assert positions == []
    assert "0.30" in result["reason"] or "30%" in result["reason"]


def test_live_opt_in_block_allows_high_win_prob(tmp_decisions, tmp_path,
                                                monkeypatch):
    cfg = cfg_with_models(tmp_path, block_on_low_win_prob=True,
                          min_win_prob=0.30)
    install_fake_model(monkeypatch, tmp_path, probs=(0.1, 0.2, 0.7))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path,
                                 bars=trend_bars())
    assert result["status"] == "TRADED"
    assert len(mt5.sent_orders) == 1


def test_live_hard_gate_still_blocks_with_model(tmp_decisions, tmp_path,
                                                monkeypatch):
    cfg = cfg_with_models(tmp_path)
    install_fake_model(monkeypatch, tmp_path, probs=(0.1, 0.2, 0.7))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    guard = make_guard()
    guard.record_pnl("forex", -1100.0)  # vuot gioi han quy 10%
    result = call_process_symbol(cfg, mt5, feed, guard=guard,
                                 tmp_path=tmp_path, bars=trend_bars())
    assert result["status"] == "BLOCKED-DRAWDOWN-FUND"
    assert len(mt5.sent_orders) == 0  # AI khong bao gio vuot gate cung


def test_live_absent_model_trades_normally(tmp_decisions, tmp_path, capfd):
    cfg = cfg_with_models(tmp_path)  # khong ghi file mo hinh nao
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path,
                                 bars=trend_bars())
    assert result["status"] == "TRADED"
    assert "ai_win_prob" not in result
    assert len(mt5.sent_orders) == 1
    out = capfd.readouterr().out
    assert "Traceback" not in out


def test_live_corrupt_model_trades_normally(tmp_decisions, tmp_path, capfd):
    cfg = cfg_with_models(tmp_path)
    write_model_files(tmp_path)  # sidecar hop le, .pt la rac
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path,
                                 bars=trend_bars())
    assert result["status"] == "TRADED"
    assert "ai_win_prob" not in result
    assert len(mt5.sent_orders) == 1
    out = capfd.readouterr().out
    assert "Traceback" not in out


def test_live_fetches_81_bars_when_model_present(tmp_decisions, tmp_path,
                                                 monkeypatch):
    cfg = cfg_with_models(tmp_path)
    install_fake_model(monkeypatch, tmp_path, probs=(0.1, 0.2, 0.7))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path)
    assert result["status"] == "TRADED"
    assert feed.bars_requested == [81]
    assert result["ai_win_prob"] == pytest.approx(0.7)


def test_live_recommend_mode_carries_ai(tmp_decisions, tmp_path, monkeypatch):
    cfg = cfg_with_models(tmp_path)
    install_fake_model(monkeypatch, tmp_path, probs=(0.1, 0.2, 0.7))
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path,
                                 bars=trend_bars(), recommend_only=True)
    assert result["status"] == "RECOMMENDED"
    assert len(mt5.sent_orders) == 0
    assert result["ai_win_prob"] == pytest.approx(0.7)
    records = load_outcomes(tmp_path / "outcomes.jsonl")
    assert len(records) == 1
    assert records[0]["context"]["ai_win_prob"] == pytest.approx(0.7)


# ---------------- mo hinh torch that (chi venv torch) ----------------

def test_real_tiny_model_end_to_end(tmp_decisions, tmp_path):
    torch = pytest.importorskip("torch")
    from diamondx10.ai.model import ModelConfig, save_model
    from diamondx10.ai.model import DirectionGRU  # noqa: F401 — dam bao lop ton tai

    cfg = cfg_with_models(tmp_path)
    models_dir = Path(tmp_path / "models")
    models_dir.mkdir(parents=True, exist_ok=True)
    config = ModelConfig(n_features=48, seq_len=32)
    model = DirectionGRU(config)
    sidecar = {"symbol": "EURUSD", "label_mode": "tp_sl",
               "classes": ["sl_first", "timeout", "tp_first"],
               "feature_version": FEATURE_VERSION,
               "feature_names": list(FEATURE_NAMES),
               "param_feature_names": list(PARAM_FEATURE_NAMES),
               "param_feature_version": PARAM_FEATURE_VERSION,
               "mean": None, "std": None, "seq_len": 32,
               "bars_used": 5000, "walkforward_metrics": None,
               "oos_metrics": None}
    save_model(model, config, sidecar,
               models_dir / "EURUSD.pt", models_dir / "EURUSD.json")
    pred = live_hook.predict_win_prob(cfg, "EURUSD", trend_bars(), "BUY")
    assert pred is not None
    assert sum(pred["ai_probs"]) == pytest.approx(1.0)
    assert 0.0 <= pred["ai_win_prob"] <= 1.0
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    result = call_process_symbol(cfg, mt5, feed, tmp_path=tmp_path,
                                 bars=trend_bars())
    assert result["status"] == "TRADED"
    assert result["ai_win_prob"] == pytest.approx(pred["ai_win_prob"])
    assert len(mt5.sent_orders) == 1
