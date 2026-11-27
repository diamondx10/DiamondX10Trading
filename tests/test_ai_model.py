"""Test mo hinh outcome GRU + training (ai/model.py, ai/train.py).

- Cac test thuan (scaler, tach thoi gian, metrics, gate, loi file)
  chay LUON, khong can torch.
- Cac test train that (train -> save -> load -> predict) skip ro
  rang neu torch chua cai (pytest.importorskip, huong ve ai-setup)
  — khong lam do suite tren may chua cai torch.
- Khong mang, khong MT5 that, khong file repo that: moi test dung
  bar gia + tmp_path, CPU only, epoch nho.

Quy uoc: chuoi tieng Viet KHONG dau; file that chi dung tmp_path.
"""
import copy
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.ai import train as train_mod
from diamondx10.ai.model import (
    ModelConfig,
    ModelLoadError,
    TorchNotAvailable,
    _torch_import_error,
    build_model,
    install_torch,
    is_torch_ready,
    load_model,
    load_sidecar,
    model_paths,
    save_model,
)
from diamondx10.ai.params import param_vector
from diamondx10.config import DEFAULT as DEFAULT_CONFIG

TORCH_REASON = "torch chua cai — chay python -m diamondx10 ai-setup"


def make_bars(n=400, seed=7):
    """Bar gia xac dinh: 200 bar trend len + 200 bar trend xuong
    (quy tac SMA/RSI kich hoat duoc o ca 2 chieu)."""
    rng = random.Random(seed)
    bars = []
    price = 100.0
    for i in range(n):
        drift = 0.0012 if i < n // 2 else -0.0012
        open_price = price
        price *= 1 + drift + rng.gauss(0, 0.0015)
        close = round(price, 4)
        half = (abs(close - open_price)
                + abs(rng.gauss(0, 0.001)) * open_price) / 2
        bars.append({"time": i * 900,
                     "open": round(open_price, 4),
                     "high": round(max(open_price, close) + half, 4),
                     "low": round(min(open_price, close) - half, 4),
                     "close": close, "volume": 1000.0})
    return bars


def make_cfg():
    """Config toi thieu (doc lap config.yaml local): strategy mac
    dinh + symbols + learning."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"],
                               "xauusd": ["XAUUSD"],
                               "crypto": ["BTCUSD", "ETHUSD", "BNBUSD"],
                               "us_securities": ["AMD", "CDNS", "SNPS",
                                                "INTC", "NVDA"]}}
    cfg["learning"] = {"outcome_window_bars": 20,
                       "min_sample_for_proposal": 5}
    cfg["history"] = {"db_path": "data/history.db",
                      "default_timeframe": "M15", "backfill_days": 90}
    cfg["ai"] = {"models_dir": "data/ai-models", "seq_len": 32,
                 "rank_bars": 2000}
    return cfg


# --- Torch: loi sach + cai dat -------------------------------------------

def test_torch_error_names_ai_setup():
    """Thong bao loi khi thieu torch phai ten `ai-setup`."""
    assert "ai-setup" in _torch_import_error()


def test_install_torch_argv_fake_runner():
    """ai-setup goi dung lenh pip (runner gia, khong mang that)."""
    seen = []

    class _Run:
        returncode = 0

    def _fake(argv):
        seen.append(list(argv))
        return _Run()

    assert install_torch(runner=_fake) is True
    assert seen == [[sys.executable, "-m", "pip", "install", "torch",
                     "--index-url",
                     "https://download.pytorch.org/whl/cpu",
                     "numpy", "pandas"]]


def test_install_torch_failed_runner_returns_false(capsys):
    """pip that -> False + huong dan, khong raise."""

    class _Run:
        returncode = 1

    assert install_torch(runner=lambda argv: _Run()) is False
    assert "ai-setup" in capsys.readouterr().out


def test_model_config_roundtrip():
    """ModelConfig -> dict -> ModelConfig giu nguyen gia tri."""
    cfg = ModelConfig(n_features=48, hidden=32, layers=1, dropout=0.1,
                      seq_len=16, label_mode="direction")
    cfg2 = ModelConfig.from_dict(cfg.to_dict())
    assert cfg2.n_features == 48 and cfg2.hidden == 32
    assert cfg2.layers == 1 and cfg2.seq_len == 16
    assert cfg2.label_mode == "direction"


def test_param_vector_is_normalized():
    """Vector tham so ve [0, 1], dung thu tu, dung so cot."""
    vec = param_vector({"sma_fast": 5, "sma_slow": 20,
                        "rsi_buy_low": 50, "atr_sl_mult": 1.5,
                        "adx_min": 20, "min_atr_pct": 0.001})
    assert len(vec) == 13
    assert all(0.0 <= v <= 1.0 for v in vec)
    assert vec[0] == pytest.approx(5 / 50)
    assert vec[1] == pytest.approx(20 / 200)
    assert vec[8] == pytest.approx(1.5 / 5.0)


# --- Tach thoi gian + scaler + metrics (khong can torch) -----------------

def test_chronological_split_is_ordered_no_overlap():
    """Tach train/val/test theo thoi gian: khong shuffle, khong
    chong lan, train < val < test."""
    tr, va, te = train_mod.chronological_split(100)
    assert tr == list(range(0, 70))
    assert va == list(range(70, 85))
    assert te == list(range(85, 100))
    assert not (set(tr) & set(va) or set(tr) & set(te)
                or set(va) & set(te))


def test_walk_forward_folds_mirror_backtest_windows():
    """Fold walk-forward: train -> test ke nhau, truot dung buoc."""
    folds = train_mod.walk_forward_folds(100, 60, 20, 20)
    assert folds == [(list(range(0, 60)), list(range(60, 80))),
                     (list(range(20, 80)), list(range(80, 100)))]
    assert train_mod.walk_forward_folds(50, 60, 20, 20) == []


def test_scaler_fit_on_train_fold_only():
    """Scaler fit tren train: mean = mean train (KHONG phai mean
    toan bo); cua so test bi dich thi sau scale van lech."""
    train_X = [[[0.0, 10.0], [2.0, 12.0]]]
    test_X = [[[100.0, 110.0]]]
    mean, std = train_mod.fit_scaler(train_X)
    assert mean == pytest.approx([1.0, 11.0])
    scaled = train_mod.apply_scaler(test_X, mean, std)
    assert scaled[0][0][0] > 10.0  # test dich xa train -> lech lon
    scaled_train = train_mod.apply_scaler(train_X, mean, std)
    assert sum(v for row in scaled_train[0] for v in row) == pytest.approx(0.0)


def test_classification_metrics_hand_computed():
    """Metrics dung tren vi du tinh tay duoc."""
    y_true = [2, 2, 0, 1, 1, 0]
    y_pred = [2, 0, 0, 1, 2, 0]
    m = train_mod.classification_metrics(y_true, y_pred)
    assert m["accuracy"] == pytest.approx(4 / 6)
    assert m["confusion"] == [[2, 0, 0], [0, 1, 1], [1, 0, 1]]
    assert m["per_class"]["tp_first"]["precision"] == pytest.approx(1 / 2)
    assert m["per_class"]["tp_first"]["recall"] == pytest.approx(1 / 2)
    assert m["per_class"]["timeout"]["support"] == 2


def test_trade_score_timeouts_excluded_from_denominator():
    """Win rate = thang / (thang + thua); timeout loai khoi mau so."""
    score = train_mod.trade_score([2, 0, 1, 2], [2, 2, 2, 0])
    assert score == {"n_trades": 3, "wins": 1, "losses": 1,
                     "timeouts": 1, "win_rate": pytest.approx(0.5)}
    assert train_mod.trade_score([2, 0], [1, 1])["win_rate"] is None


def test_naive_baselines_structure():
    """Baseline naive: always-timeout khong vao lenh nao."""
    base = train_mod.naive_baselines([2, 0, 1, 2, 0])
    assert base["always_timeout"]["trade_score"]["n_trades"] == 0
    assert base["always_timeout"]["trade_score"]["win_rate"] is None
    assert base["previous_label"]["trade_score"]["n_trades"] >= 0


def test_event_sequences_dense_consecutive_bars():
    """Chuoi su kien: 32 hang LIEN TIEP theo thoi gian ket thuc o
    bar kich hoat; hang cuoi = dung hang feature cua su kien do;
    chuoi sap theo time; khong tron huong / bo tham so."""
    from diamondx10.ai.tune import (
        build_tuning_dataset,
        counterfactual_samples,
        event_sequences,
    )
    cfg = make_cfg()
    bars = make_bars(400)
    ds = build_tuning_dataset(cfg, "EURUSD", bars,
                              include_outcomes=False)
    Xseq, yseq, mseq = event_sequences(
        cfg, "EURUSD", bars, ds["meta"], ds["y"], seq_len=32)
    assert len(Xseq) > 0
    assert all(len(seq) == 32 for seq in Xseq)
    assert all(len(row) == 48 for seq in Xseq for row in seq)
    assert [m["time"] for m in mseq] == sorted(
        m["time"] for m in mseq)
    # Hang cuoi cua chuoi phai bang hang feature cua chinh su kien.
    by_key = {(m["time"], m["direction"], m["candidate"]): row
              for m, row in zip(ds["meta"], ds["X"])}
    for seq, m in zip(Xseq, mseq):
        key = (m["time"], m["direction"], m["candidate"])
        assert seq[-1] == by_key[key]
        # Cot direction_long (34) khop huong su kien o moi hang.
        want = 1.0 if m["direction"] == "BUY" else -1.0
        assert all(row[34] == want for row in seq)
        # 13 cot tham so cuoi hang so trong chuoi.
        assert all(row[35:] == seq[0][35:] for row in seq)
    # Nhan cua chuoi = nhan su kien.
    code_of = {"sl_first": 0, "timeout": 1, "tp_first": 2}
    assert yseq == [code_of[m["label_name"]] for m in mseq]


# --- Promotion gate + loi file (khong can torch) -------------------------

def _report_with_win_rate(new_wr, rule_wr):
    return {"oos": {
        "trade_score": {"win_rate": new_wr},
        "baselines": {"rule_based": {"trade_score": {"win_rate": rule_wr}}}}}


def _write_live_sidecar(path, win_rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = {"symbol": "EURUSD", "oos_metrics": {
        "trade_score": {"win_rate": win_rate}}}
    path.write_text(json.dumps(sidecar), encoding="utf-8")


def test_promotion_gate_beats_both(tmp_path):
    """Moi thang ca rule lan live -> promote."""
    _write_live_sidecar(tmp_path / "EURUSD.json", 0.5)
    gate = train_mod.evaluate_model_promotion(
        "EURUSD", _report_with_win_rate(0.6, 0.4), tmp_path)
    assert gate["promote"] is True
    assert gate["live_win_rate"] == 0.5


def test_promotion_gate_loses_to_rule_keeps_old(tmp_path):
    """Moi thua baseline quy tac -> giu file cu."""
    _write_live_sidecar(tmp_path / "EURUSD.json", 0.4)
    gate = train_mod.evaluate_model_promotion(
        "EURUSD", _report_with_win_rate(0.45, 0.5), tmp_path)
    assert gate["promote"] is False
    assert "quy tac" in gate["reason"]


def test_promotion_gate_tie_with_live_keeps_old(tmp_path):
    """Hoa voi live (khong thang han) -> giu file cu."""
    _write_live_sidecar(tmp_path / "EURUSD.json", 0.6)
    gate = train_mod.evaluate_model_promotion(
        "EURUSD", _report_with_win_rate(0.6, 0.4), tmp_path)
    assert gate["promote"] is False


def test_promotion_gate_no_live_model_needs_only_rule(tmp_path):
    """Chua co mo hinh live: chi can thang rule."""
    gate = train_mod.evaluate_model_promotion(
        "EURUSD", _report_with_win_rate(0.6, 0.4), tmp_path)
    assert gate["promote"] is True
    assert gate["live_win_rate"] is None


def test_promotion_gate_no_predicted_trades(tmp_path):
    """Khong du doan duoc lenh nao tren OOS -> khong promote."""
    gate = train_mod.evaluate_model_promotion(
        "EURUSD", _report_with_win_rate(None, 0.4), tmp_path)
    assert gate["promote"] is False


def test_corrupt_sidecar_clean_error_naming_file(tmp_path):
    """Sidecar JSON hong -> ModelLoadError ghi ro ten file."""
    bad = tmp_path / "EURUSD.json"
    bad.write_text("{khong phai json", encoding="utf-8")
    with pytest.raises(ModelLoadError) as exc:
        load_sidecar(bad)
    assert str(bad) in str(exc.value)


def test_missing_sidecar_clean_error_naming_file(tmp_path):
    """Thieu sidecar -> ModelLoadError ghi ro ten file."""
    missing = tmp_path / "EURUSD.json"
    with pytest.raises(ModelLoadError) as exc:
        load_sidecar(missing)
    assert str(missing) in str(exc.value)


def test_model_paths_use_models_dir(tmp_path):
    """model_paths ton trong models_dir truyen vao."""
    pt, js = model_paths("EURUSD", tmp_path)
    assert pt == tmp_path / "EURUSD.pt"
    assert js == tmp_path / "EURUSD.json"


# --- Train that (can torch) ------------------------------------------------

@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_train_end_to_end_tiny_fake_bars(tmp_path):
    """Train tren bar gia (epochs nho): bao cao day du, khong
    crash; promote=False thi khong ghi file mo hinh."""
    cfg = make_cfg()
    bars = make_bars(400)
    report = train_mod.train(cfg, "EURUSD", bars, epochs=2,
                             models_dir=tmp_path, promote=False)
    assert report["symbol"] == "EURUSD"
    assert report["n_windows"] > 0
    assert report["oos"]["n"] > 0
    assert report["oos"]["trade_score"]["win_rate"] is None or 0.0 <= \
        report["oos"]["trade_score"]["win_rate"] <= 1.0
    assert report["train_seconds"] >= 0
    assert report["promotion"]["promoted"] is False
    assert report["model_path"] is None
    assert Path(report["report_path"]).exists()
    assert "rule_based" in report["oos"]["baselines"]
    assert "previous_label" in report["oos"]["baselines"]


@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_save_load_predict_roundtrip(tmp_path):
    """Save -> load -> predict: weights-only, sidecar day du,
    xac suat chuan hoa, load 2 lan cho cung ket qua."""
    from diamondx10.ai.features import FEATURE_NAMES
    from diamondx10.ai.model import predict_proba
    from diamondx10.ai.params import PARAM_FEATURE_NAMES
    model = build_model(ModelConfig(n_features=48))
    sidecar = {"symbol": "EURUSD", "feature_version": 1,
               "feature_names": list(FEATURE_NAMES),
               "param_feature_names": list(PARAM_FEATURE_NAMES),
               "mean": [0.0] * 48, "std": [1.0] * 48}
    pt, js = save_model(model, ModelConfig(n_features=48), sidecar,
                        tmp_path / "EURUSD.pt")
    assert pt.exists() and js.exists()
    model2, sidecar2 = load_model(pt, js)
    assert sidecar2["symbol"] == "EURUSD"
    assert sidecar2["feature_version"] == 1
    assert len(sidecar2["feature_names"]) == 35
    assert len(sidecar2["param_feature_names"]) == 13
    assert len(sidecar2["mean"]) == 48
    assert sidecar2["torch_version"]
    probs1 = predict_proba(model2, [[[0.0] * 48] * 32])
    model3, _ = load_model(pt, js)
    probs2 = predict_proba(model3, [[[0.0] * 48] * 32])
    assert len(probs1) == 1 and len(probs1[0]) == 3
    assert sum(probs1[0]) == pytest.approx(1.0, abs=1e-5)
    assert probs1 == probs2


@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_train_fixed_seed_deterministic_predictions(tmp_path):
    """Cung seed -> cung du doan (xac suat gan nhu giong het)."""
    cfg = make_cfg()
    bars = make_bars(400)
    r1 = train_mod.train(cfg, "EURUSD", bars, epochs=2, seed=123,
                         models_dir=tmp_path / "m1", promote=True)
    r2 = train_mod.train(cfg, "EURUSD", bars, epochs=2, seed=123,
                         models_dir=tmp_path / "m2", promote=True)
    assert r1["oos"]["accuracy"] == r2["oos"]["accuracy"]
    assert r1["epochs_run"] == r2["epochs_run"]


@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_train_worse_model_does_not_replace_live(tmp_path):
    """Gate that: mo hinh live tot -> mo hinh moi kem khong thay."""
    cfg = make_cfg()
    bars = make_bars(400)
    # Live gia: win rate OOS 0.99 (gan nhu khong the vuot).
    _write_live_sidecar(tmp_path / "EURUSD.json", 0.99)
    (tmp_path / "EURUSD.pt").write_bytes(b"gia-tri-giu-cho")
    report = train_mod.train(cfg, "EURUSD", bars, epochs=2,
                             models_dir=tmp_path, promote=True)
    assert report["promotion"]["promoted"] is False
    assert report["model_path"] is None
    assert (tmp_path / "EURUSD.pt").read_bytes() == b"gia-tri-giu-cho"


@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_corrupt_weights_clean_error_naming_file(tmp_path):
    """Sidecar dung + weights hong -> ModelLoadError ten file .pt."""
    from diamondx10.ai.features import FEATURE_NAMES
    from diamondx10.ai.model import save_model
    from diamondx10.ai.params import PARAM_FEATURE_NAMES
    model = build_model(ModelConfig(n_features=48))
    sidecar = {"symbol": "EURUSD", "feature_version": 1,
               "feature_names": list(FEATURE_NAMES),
               "param_feature_names": list(PARAM_FEATURE_NAMES),
               "mean": [0.0] * 48, "std": [1.0] * 48}
    pt, js = save_model(model, ModelConfig(n_features=48), sidecar,
                        tmp_path / "EURUSD.pt")
    pt.write_bytes(b"khong phai torch state dict")
    with pytest.raises(ModelLoadError) as exc:
        load_model(pt, js)
    assert str(pt) in str(exc.value)


@pytest.mark.skipif(not is_torch_ready(), reason=TORCH_REASON)
def test_feature_version_mismatch_refuses_load(tmp_path):
    """Sidecar version cu -> load tu choi (khong dung weights cu)."""
    from diamondx10.ai.model import save_model
    model = build_model(ModelConfig(n_features=48))
    sidecar = {"symbol": "EURUSD", "feature_version": 999,
               "feature_names": ["cot-cu"] * 35,
               "mean": [0.0] * 48, "std": [1.0] * 48}
    pt, js = save_model(model, ModelConfig(n_features=48), sidecar,
                        tmp_path / "EURUSD.pt")
    with pytest.raises(ModelLoadError):
        load_model(pt, js)
