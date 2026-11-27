"""Test chinh tham so TA tu log (ai/params.py, ai/tune.py).

- Test thuan (ung vien, counterfactual, no-lookahead, kiem chung
  OOS, ghi de xuat) chay LUON, khong can torch.
- Test xep hang bang mo hinh skip ro rang neu torch chua cai.
- Bar gia + tmp_path; khong mang, khong MT5 that, khong file
  repo that (config ap chi tren ban sao tmp_path).

Quy uoc: chuoi tieng Viet KHONG dau; file that chi dung tmp_path.
"""
import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.ai import tune as tune_mod
from diamondx10.ai.model import is_torch_ready
from diamondx10.ai.params import (
    candidate_param_sets,
    current_params,
    param_key,
    strategy_with_params,
)
from diamondx10.ai.train import train as train_model
from test_ai_model import make_bars, make_cfg

TORCH_REASON = "torch chua cai — chay python -m diamondx10 ai-setup"


# --- Ung vien tham so ------------------------------------------------------

def test_candidates_include_current_and_validate():
    """Tap ung vien: dau tien la current, con lai deu hop le
    (khoang + thu tu), khong trung nhau."""
    cfg = make_cfg()
    cands, stats = candidate_param_sets(cfg, "forex", "EURUSD")
    assert cands[0] == {"name": "current", "overrides": {}}
    assert len(cands) >= 10
    keys = {param_key(c["overrides"]) for c in cands}
    assert len(keys) == len(cands)
    for cand in cands:
        _strat, merged = strategy_with_params(
            cfg, "forex", "EURUSD", cand["overrides"])
        assert isinstance(merged, dict)


def test_candidates_vary_one_param_at_a_time():
    """Bien doi mot luc: moi ung vien (tru current) chi doi 1 tham so."""
    cfg = make_cfg()
    cands, _stats = candidate_param_sets(cfg, "forex", "EURUSD")
    for cand in cands[1:]:
        assert len(cand["overrides"]) == 1


def test_strategy_with_params_rejects_bad_override():
    """Ghi de vi pham thu tu (rsi_buy_low vuot rsi_buy_high) -> loi."""
    cfg = make_cfg()
    with pytest.raises(ValueError):
        strategy_with_params(cfg, "forex", "EURUSD",
                             {"rsi_buy_low": 90, "rsi_buy_high": 70})


# --- Counterfactual ---------------------------------------------------------

def test_counterfactual_samples_match_live_rule():
    """Mau counterfactual khop quy tac that: tai moi mau, chay lai
    Strategy.signal tren dung 60 bar thi action + levels khop."""
    cfg = make_cfg()
    bars = make_bars(400)
    X, y, meta, stats = tune_mod.counterfactual_samples(
        cfg, "EURUSD", bars)
    assert stats["fired"] > 0
    assert len(X) == len(y) == len(meta) == stats["fired"]
    assert all(len(row) == 48 for row in X)
    assert set(y) <= {0, 1, 2}
    strat, _merged = strategy_with_params(cfg, "forex", "EURUSD", {})
    checked = 0
    for m in meta:
        if m["candidate"] != "current":
            continue
        idx = next(i for i, b in enumerate(bars)
                   if b["time"] == m["time"])
        win60 = bars[max(0, idx - 59):idx + 1]
        action, _reason, levels = strat.signal(win60)
        assert action == m["direction"]
        assert levels["entry"] == pytest.approx(m["entry"])
        assert levels["sl"] == pytest.approx(m["sl"])
        assert levels["tp"] == pytest.approx(m["tp"])
        checked += 1
        if checked >= 5:
            break
    assert checked > 0


def test_counterfactual_no_lookahead_in_features():
    """Chen spike vao TUONG LAI sau t: feature cua cac mau ket thuc
    truoc spike khong doi (nhan thi duoc doi — dung thiet ke)."""
    cfg = make_cfg()
    bars = make_bars(400)
    X1, _y1, meta1, _s1 = tune_mod.counterfactual_samples(
        cfg, "EURUSD", bars)
    bars2 = copy.deepcopy(bars)
    for b in bars2[300:]:
        b["close"] *= 1.5
        b["high"] *= 1.5
        b["low"] *= 1.5
        b["open"] *= 1.5
    X2, _y2, meta2, _s2 = tune_mod.counterfactual_samples(
        cfg, "EURUSD", bars2)
    key1 = {(m["time"], m["direction"], m["candidate"]): row
            for m, row in zip(meta1, X1)}
    key2 = {(m["time"], m["direction"], m["candidate"]): row
            for m, row in zip(meta2, X2)}
    spike_time = bars[300]["time"]
    compared = 0
    for key, row in key1.items():
        if key[0] < spike_time - 21 * 900 and key in key2:
            assert row == key2[key]
            compared += 1
    assert compared > 0


def test_build_tuning_dataset_shape_and_timeframe():
    """Dataset tune: du 48 cot, co timeframe M15, co class counts."""
    cfg = make_cfg()
    bars = make_bars(400)
    ds = tune_mod.build_tuning_dataset(cfg, "EURUSD", bars,
                                       include_outcomes=False)
    assert ds["timeframe"] == "M15"
    assert ds["feature_version"] == 1
    assert len(ds["feature_names"]) == 35
    assert len(ds["param_feature_names"]) == 13
    assert ds["n_samples"] > 0
    assert sum(ds["class_counts"].values()) == ds["n_samples"]
    assert ds["current_params"]["sma_fast"] == 5


def test_log_samples_use_historical_params(tmp_path):
    """Mau log dung tham so THAT trong record (khong phai tham so
    hien tai): record ghi sma_fast=8 thi vector cot sma_fast = 8/50."""
    cfg = make_cfg()
    bars = make_bars(400)
    record = {"id": "abc123", "symbol": "EURUSD", "action": "BUY",
              "outcome": "win", "entry": bars[200]["close"],
              "sl": bars[200]["close"] * 0.99,
              "tp": bars[200]["close"] * 1.01,
              "time": bars[200]["time"],
              "context": {"resolved_params": {
                  "sma_fast": 8, "sma_slow": 21, "rsi_period": 14,
                  "rsi_buy_low": 50, "rsi_buy_high": 70,
                  "rsi_sell_low": 30, "rsi_sell_high": 50,
                  "rsi_extreme_high": 80, "rsi_extreme_low": 20,
                  "atr_period": 14, "atr_sl_mult": 1.5, "tp_mult": 2.0,
                  "trail_mult": 1.5, "adx_min": 0}}}
    X, y, meta, stats = tune_mod.log_samples(
        cfg, "EURUSD", bars, outcomes_records=[record])
    assert stats["included"] == 1
    assert y == [2]
    assert meta[0]["source"] == "outcomes-log"
    assert meta[0]["params"]["sma_fast"] == 8
    assert X[0][35] == pytest.approx(8 / 50)  # cot tham so dau tien


# --- Kiem chung OOS + de xuat (khong can torch) -----------------------------

def test_validate_oos_current_vs_itself_not_validated():
    """Ung vien = tham so hien tai: return bang baseline -> khong
    validated (can thang HAN)."""
    cfg = make_cfg()
    bars = make_bars(400)
    result = tune_mod.validate_candidate_oos(cfg, "EURUSD", {}, bars)
    assert result["validated"] is False
    assert result["oos_n"] >= 0
    assert result["oos_return"] == result["baseline_oos_return"]


def test_validate_oos_unblocking_candidate_beats_blocked_current():
    """Hien tai bi min_atr_pct chan het (khong lenh nao) + RSI cuc
    doan cung chan; ung vien mo gate va mo rong vung RSI thi co lenh
    thang tren trend manh -> validated True."""
    cfg = make_cfg()
    cfg["strategy"] = dict(cfg["strategy"])
    cfg["strategy"]["per_symbol"] = {
        "EURUSD": {"min_atr_pct": 0.05, "rsi_extreme_high": 100,
                   "rsi_extreme_low": 0, "rsi_buy_high": 90,
                   "rsi_sell_low": 10}}
    bars = make_bars(400)
    result = tune_mod.validate_candidate_oos(
        cfg, "EURUSD", {"min_atr_pct": 0.0}, bars)
    assert result["baseline_oos_n"] == 0
    assert result["oos_n"] > 0
    assert result["validated"] is True


def test_validate_oos_too_few_bars():
    """It bar qua -> validated False + ly do ro rang."""
    cfg = make_cfg()
    result = tune_mod.validate_candidate_oos(cfg, "EURUSD", {},
                                             make_bars(10))
    assert result["validated"] is False
    assert "walk-forward" in result["reason"]


def test_tune_proposals_use_ta_review_shape_and_apply(tmp_path):
    """De xuat tune ghi dung shape ta-review: apply tren ban sao
    config doi dung tham so, khong dong den config that."""
    from diamondx10.ta_review import apply_proposals, write_proposals
    cfg = make_cfg()
    proposals = [{
        "symbol": "EURUSD", "kind": "param",
        "param_or_rule": "sma_fast", "current_value": 5,
        "proposed_value": 7,
        "evidence": {"metric": "predicted_win_rate", "before": 0.4,
                     "after": 0.6, "n": 10},
        "rationale": "test",
        "oos_validation": {"oos_win_rate": 60.0, "oos_return": 1.5,
                           "oos_n": 25, "validated": True,
                           "baseline_oos_return": 0.5,
                           "baseline_oos_n": 20},
        "validated": True, "ready": True}]
    path = tmp_path / "ta-tuning-proposals-test.yaml"
    write_proposals(proposals, path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["strategy"]["per_symbol"]["EURUSD"]["sma_fast"] == 7
    config_copy = tmp_path / "config.yaml"
    config_copy.write_text(yaml.safe_dump(cfg, allow_unicode=True),
                           encoding="utf-8")
    changed, skipped = apply_proposals(path, config_copy,
                                       confirm="APPLY")
    assert changed == ["strategy.per_symbol.EURUSD.sma_fast"]
    assert not skipped
    after = yaml.safe_load(config_copy.read_text(encoding="utf-8"))
    assert after["strategy"]["per_symbol"]["EURUSD"]["sma_fast"] == 7


# --- Xep hang + tune tron vong (can torch) -----------------------------------

@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_tune_symbol_end_to_end(tmp_path):
    """Train nho -> tune: co bang xep hang; de xuat (neu co) deu
    validated va ghi file dung shape; config that khong doi."""
    from diamondx10.ai.model import load_model
    cfg = make_cfg()
    bars = make_bars(400)
    models_dir = tmp_path / "models"
    report = train_model(cfg, "EURUSD", bars, epochs=2,
                         models_dir=models_dir, promote=True)
    pt = models_dir / "EURUSD.pt"
    js = models_dir / "EURUSD.json"
    if not pt.exists():
        # Gate khong thang: ghi tay model vua train? train khong
        # tra model — train lai voi promote=False roi dung
        # sidecar/report de xep hang thi van can file .pt; truong
        # hop nay thi dung _train_one_fold truc tiep.
        from diamondx10.ai.model import ModelConfig, save_model
        from diamondx10.ai.train import (
            N_FEATURES, _train_one_fold, apply_scaler, fit_scaler,
        )
        from diamondx10.ai.tune import (
            build_tuning_dataset,
            event_sequences,
        )
        ds = build_tuning_dataset(cfg, "EURUSD", bars,
                                  include_outcomes=False)
        Xseq, yseq, _m = event_sequences(
            cfg, "EURUSD", bars, ds["meta"], ds["y"], seq_len=32)
        mean, std = fit_scaler(Xseq[:70])
        model, _info = _train_one_fold(
            apply_scaler(Xseq[:70], mean, std), yseq[:70],
            apply_scaler(Xseq[70:85], mean, std), yseq[70:85],
            N_FEATURES, ["sl_first", "timeout", "tp_first"], 2, 42,
            [1.0, 1.0, 1.0])
        save_model(model, ModelConfig(n_features=N_FEATURES),
                   {"symbol": "EURUSD", "feature_version": 1,
                    "feature_names": ds["feature_names"],
                    "param_feature_names": ds["param_feature_names"],
                    "mean": list(mean), "std": list(std)},
                   pt, js)
    model, sidecar = load_model(pt, js)
    tune_report = tune_mod.tune_symbol(
        cfg, "EURUSD", bars, model, sidecar, top_k=2, rank_bars=200,
        min_trades=1, min_oos_n=1,
        proposals_path=tmp_path / "proposals.yaml")
    assert tune_report["ranked"], "can co ung vien du lenh de xep hang"
    assert tune_report["ranked"][0]["mean_p_tp"] is not None
    assert all(r["mean_p_tp"] is not None for r in tune_report["ranked"])
    assert [r["mean_p_tp"] for r in tune_report["ranked"]] == sorted(
        [r["mean_p_tp"] for r in tune_report["ranked"]], reverse=True)
    for proposal in tune_report["proposals"]:
        assert proposal["validated"] is True
        assert proposal["oos_validation"]["validated"] is True
    if tune_report["proposals"]:
        data = yaml.safe_load(
            Path(tune_report["proposals_path"]).read_text(
                encoding="utf-8"))
        assert "strategy" in data
