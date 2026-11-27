"""Huan luyen mo hinh outcome GRU (ai/train.py).

Mo hinh hoc P(ket qua lenh | context thi truong, tham so TA) tu
dataset tune (ai/tune.py: mau counterfactual + log da danh gia).
Dau vao moi hang = 35 cot context + 13 cot tham so (48 cot);
mo hinh an chuoi 32 hang lien tiep (cung huong + cung bo tham so).

KY LUAT OOS (bat buoc):
- Tach CHRONOLOGICAL ONLY: train 70% dau, val 15% giua, test
  (OOS) 15% cuoi — khong bao gio shuffle qua thoi gian. Ham
  walk_forward_folds() dung cung ngu nghia cua so nhu
  backtest.run_walk_forward (train_bars -> test_bars -> truot
  step_bars).
- Scaler (mean/std theo cot) chi fit tren TRAIN fold.
- Bao cao KHONG BAO GIO chi co accuracy: accuracy + precision/
  recall tung lop + confusion + win rate giao dich OOS so voi
  baseline quy tac hien tai va baseline naive tren CUNG fold OOS.
- Cua so gate (promotion): file mo hinh moi chi thay file live
  khi win rate OOS cua no thang CA baseline quy tac VA mo hinh
  live hien co (neu co); khong thi giu file cu + ghi ro ly do.
  (Tham so TA thi KHONG BAO GIO tu ap — de xuat tham so qua
  ai-tune / ta-review, kiem chung OOS rieng; xem ai/tune.py.)

Train OFFLINE, theo lich (ai-train tay hoac Task Scheduler hang
tuan) — KHONG BAO GIO trong vong live M15 (khong dong den live.py).
"""
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from .dataset import (
    FEATURE_VERSION,
    LABEL_NAMES_TP_SL,
    InsufficientHistoryError,
    build_dataset,
)
from .features import FEATURE_NAMES
from .model import (
    DEFAULT_MODELS_DIR,
    DEFAULT_SEQ_LEN,
    ModelConfig,
    TorchNotAvailable,
    build_model,
    load_model,
    model_paths,
    require_torch,
    resolve_models_dir,
    save_model,
)
from .params import (
    PARAM_FEATURE_NAMES,
    PARAM_FEATURE_VERSION,
    param_vector,
)
from .tune import (
    build_tuning_dataset,
    event_sequences,
    fallback_dataset,
    load_history_bars,
)

CLASSES = list(LABEL_NAMES_TP_SL)
TP_INDEX = CLASSES.index("tp_first")
SL_INDEX = CLASSES.index("sl_first")
TIMEOUT_INDEX = CLASSES.index("timeout")
N_FEATURES = len(FEATURE_NAMES) + len(PARAM_FEATURE_NAMES)

DEFAULT_EPOCHS = 50
DEFAULT_BATCH = 128
DEFAULT_LR = 1e-3
DEFAULT_WEIGHT_DECAY = 1e-4
DEFAULT_PATIENCE = 5
DEFAULT_SEED = 42


# --- Chuoi + tach thoi gian -------------------------------------------
# Chuoi 32 bar lien tiep cho moi su kien vao lenh nam o
# tune.event_sequences (xay day tu bar + meta su kien, co cache
# hang): khong nhom truc tiep cac hang mau (mau thua, khong lien
# tuc) vi nhom (huong, tham so) thuong ngan hon seq_len.


def chronological_split(n, train_frac=0.7, val_frac=0.15):
    """Chi so train/val/test theo THOI GIAN (khong shuffle):
    train = 70% dau, val = 15% giua, test = 15% cuoi. Tra 3 list
    chi so (co the rong khi n nho — caller kiem tra)."""
    n = int(n)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    return (list(range(0, n_train)),
            list(range(n_train, n_train + n_val)),
            list(range(n_train + n_val, n)))


def walk_forward_folds(n, train_bars, test_bars, step_bars):
    """Cac fold walk-forward tren chi so (cung ngu nghia nhu
    backtest.run_walk_forward): cua so train_bars bar, test_bars
    bar tiep theo, roi truot step_bars. Tra list (train_idx,
    test_idx)."""
    if train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
        raise ValueError("train_bars/test_bars/step_bars phai > 0")
    folds = []
    start = 0
    while start + train_bars + test_bars <= n:
        folds.append((list(range(start, start + train_bars)),
                      list(range(start + train_bars,
                                 start + train_bars + test_bars))))
        start += step_bars
    return folds


# --- Scaler (fit TRAIN fold only) --------------------------------------

def fit_scaler(X):
    """Mean/std theo cot tren cac cua so train (X: list chuoi).
    std == 0 -> 1.0 (cot hang so). Tra (mean, std) list[float]."""
    n_feat = len(X[0][0]) if X and X[0] else 0
    # Tinh theo cot: gom tat ca gia tri cua cot j.
    mean, std = [], []
    for j in range(n_feat):
        values = [row[j] for seq in X for row in seq]
        m = sum(values) / len(values) if values else 0.0
        var = (sum((v - m) ** 2 for v in values) / len(values)
               if values else 0.0)
        mean.append(float(m))
        std.append(float(math.sqrt(var)) if var > 0 else 1.0)
    return mean, std


def apply_scaler(X, mean, std):
    """Ap scaler (mean/std) len cac cua so; mean/std None thi tra
    nguyen X (de test / truong hop chua fit)."""
    if mean is None or std is None:
        return X
    return [[[(v - mean[j]) / std[j] for j, v in enumerate(row)]
             for row in seq] for seq in X]


def _class_weights(y, n_classes=3, cap=3.0):
    """Trong so lop = tan suat nghich, cat ~3x (FLAT/timeout
    thuong ap dao). Lop 0 mau -> trong so 0.0."""
    counts = [0] * n_classes
    for code in y:
        counts[int(code)] += 1
    total = len(y) or 1
    weights = []
    for c in counts:
        if c == 0:
            weights.append(0.0)
        else:
            weights.append(min(total / (n_classes * c), cap))
    return weights, counts


# --- Metrics -------------------------------------------------------------

def classification_metrics(y_true, y_pred, classes=None):
    """Accuracy + precision/recall/support tung lop + confusion
    (hang = that, cot = du doan). Khong bao gio chi bao accuracy."""
    classes = list(classes or CLASSES)
    k = len(classes)
    conf = [[0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred):
        conf[int(t)][int(p)] += 1
    n = len(y_true)
    correct = sum(conf[i][i] for i in range(k))
    per_class = {}
    for i, name in enumerate(classes):
        tp = conf[i][i]
        fp = sum(conf[r][i] for r in range(k)) - tp
        fn = sum(conf[i]) - tp
        per_class[name] = {
            "precision": (tp / (tp + fp) if tp + fp > 0 else None),
            "recall": (tp / (tp + fn) if tp + fn > 0 else None),
            "support": int(sum(conf[i])),
        }
    return {"accuracy": (correct / n if n else None),
            "n": n, "per_class": per_class, "confusion": conf}


def trade_score(y_true, y_pred):
    """Diem giao dich OOS: du doan tp_first (2) = vao lenh theo
    huong mau; thang neu that la tp_first, thua neu that la
    sl_first, timeout neu that la timeout. Win rate = thang /
    (thang + thua) — timeout LOAI khoi mau so (giong evaluator /
    ta_review). Tra {n_trades, wins, losses, timeouts, win_rate}."""
    wins = losses = timeouts = 0
    for t, p in zip(y_true, y_pred):
        if int(p) != TP_INDEX:
            continue
        if int(t) == TP_INDEX:
            wins += 1
        elif int(t) == SL_INDEX:
            losses += 1
        else:
            timeouts += 1
    closed = wins + losses
    return {"n_trades": wins + losses + timeouts, "wins": wins,
            "losses": losses, "timeouts": timeouts,
            "win_rate": (wins / closed if closed else None)}


def naive_baselines(y_true):
    """2 baseline naive tren cung fold OOS (de so sanh, khong
    phai de chon mo hinh): always-timeout (khong vao lenh) va
    previous-label (du doan = nhan cua so truoc)."""
    always = [TIMEOUT_INDEX] * len(y_true)
    prev = [TIMEOUT_INDEX] + [int(v) for v in y_true[:-1]]
    return {
        "always_timeout": {
            "accuracy": classification_metrics(y_true, always)["accuracy"],
            "trade_score": trade_score(y_true, always)},
        "previous_label": {
            "accuracy": classification_metrics(y_true, prev)["accuracy"],
            "trade_score": trade_score(y_true, prev)},
    }


def rule_baseline_oos(cfg, symbol, bars, all_meta, all_y, oos_meta):
    """Baseline QUY TAC hien tai tren cung fold OOS.

    Voi moi cua so OOS (lay time t cua hang cuoi), chay chien
    luoc hien tai tren 60 bar ket thuc o t (nhu live): BUY/SELL
    thi vao lenh theo huong do, diem bang nhan cua mau tham so
    HIEN TAI tai (t, huong do) — tra trong TOAN BO dataset
    (all_meta/all_y), khong chi trong fold OOS (mau hien tai tai
    t co the nam o fold train/val); HOLD thi khong vao lenh. Tra
    {n_trades, wins, losses, timeouts, win_rate, n_windows}.
    Loi chien luoc o 1 cua so thi coi nhu HOLD (khong crash)."""
    from .params import strategy_with_params
    from .tune import LIVE_WINDOW_BARS, _desk_for_symbol
    desk = _desk_for_symbol(cfg, symbol)
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    time_to_idx = {}
    for i, b in enumerate(ordered):
        time_to_idx.setdefault(b.get("time"), i)
    # Nhan cua mau tham so hien tai tai (time, direction).
    lookup = {}
    for m, code in zip(all_meta, all_y):
        key = (m.get("time"), m.get("direction"))
        if m.get("param_key") == ("current",) or key not in lookup:
            lookup[key] = int(code)
    try:
        strat, _merged = strategy_with_params(cfg, desk, symbol, {})
    except Exception:  # noqa: BLE001 — khong dung duoc chien luoc
        return {"n_trades": 0, "wins": 0, "losses": 0, "timeouts": 0,
                "win_rate": None, "n_windows": len(oos_meta),
                "error": "khong dung duoc chien luoc hien tai"}
    wins = losses = timeouts = trades = 0
    for m in oos_meta:
        t = m.get("time")
        idx = time_to_idx.get(t)
        if idx is None:
            continue
        win = ordered[max(0, idx - LIVE_WINDOW_BARS + 1):idx + 1]
        try:
            action, _reason, _levels = strat.signal(win)
        except Exception:  # noqa: BLE001 — coi nhu HOLD
            continue
        if action not in ("BUY", "SELL"):
            continue
        code = lookup.get((t, action))
        if code is None:
            continue
        trades += 1
        if code == TP_INDEX:
            wins += 1
        elif code == SL_INDEX:
            losses += 1
        else:
            timeouts += 1
    closed = wins + losses
    return {"n_trades": trades, "wins": wins, "losses": losses,
            "timeouts": timeouts,
            "win_rate": (wins / closed if closed else None),
            "n_windows": len(oos_meta)}


# --- Vong train torch -----------------------------------------------------

def _train_one_fold(X_train, y_train, X_val, y_val, n_features,
                    classes, epochs, seed, class_weights):
    """Train 1 fold bang torch; early stopping patience 5 tren
    val loss. Tra (model, info {epochs_run, best_val_loss,
    train_loss, val_loss})."""
    torch = require_torch()
    random.seed(seed)
    torch.manual_seed(seed)
    try:
        torch.set_num_threads(os.cpu_count() or 1)
    except Exception:  # noqa: BLE001 — set thread loi thi thoi
        pass
    config = ModelConfig(n_features=n_features, classes=tuple(classes))
    model = build_model(config)
    weights = torch.tensor(class_weights, dtype=torch.float32)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    opt = torch.optim.Adam(model.parameters(), lr=DEFAULT_LR,
                           weight_decay=DEFAULT_WEIGHT_DECAY)
    train_ds = torch.utils.data.TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.long))
    val_ds = torch.utils.data.TensorDataset(
        torch.tensor(X_val, dtype=torch.float32),
        torch.tensor(y_val, dtype=torch.long))
    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=DEFAULT_BATCH, shuffle=True, num_workers=0)
    val_loader = torch.utils.data.DataLoader(
        val_ds, batch_size=DEFAULT_BATCH, shuffle=False, num_workers=0)
    best_loss, best_state, patience_left = None, None, DEFAULT_PATIENCE
    epochs_run = 0
    last_train_loss = None
    for epoch in range(max(1, int(epochs))):
        epochs_run = epoch + 1
        model.train()
        total_loss, total_n = 0.0, 0
        for xb, yb in train_loader:
            opt.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total_loss += loss.item() * len(yb)
            total_n += len(yb)
        last_train_loss = total_loss / total_n if total_n else None
        model.eval()
        val_loss, val_n = 0.0, 0
        with torch.no_grad():
            for xb, yb in val_loader:
                val_loss += float(loss_fn(model(xb), yb)) * len(yb)
                val_n += len(yb)
        val_loss = val_loss / val_n if val_n else float("inf")
        if best_loss is None or val_loss < best_loss - 1e-6:
            best_loss = val_loss
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
            patience_left = DEFAULT_PATIENCE
        else:
            patience_left -= 1
            if patience_left <= 0:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, {"epochs_run": epochs_run, "best_val_loss": best_loss,
                   "train_loss": last_train_loss}


def _predict(model, X):
    """Du doan lop cho cac cua so (tra list[int])."""
    from .model import predict_logits
    logits = predict_logits(model, X)
    return [int(v) for v in logits.argmax(dim=1).tolist()]


def evaluate_model_promotion(symbol, report, models_dir=None):
    """Gate cho FILE mo hinh: mo hinh moi chi thay file live khi
    win rate OOS cua no thang CA baseline quy tac VA mo hinh live
    hien co (neu co). Tra {promote, reason, new_win_rate,
    rule_win_rate, live_win_rate}."""
    new_wr = (report.get("oos") or {}).get("trade_score", {}).get("win_rate")
    rule_wr = ((report.get("oos") or {}).get("baselines") or {}).get(
        "rule_based", {}).get("trade_score", {}).get("win_rate")
    live_wr = None
    _pt, live_json = model_paths(symbol, models_dir)
    if live_json.exists():
        try:
            from .model import load_sidecar
            live = load_sidecar(live_json)
            live_wr = ((live.get("oos_metrics") or {})
                       .get("trade_score", {}).get("win_rate"))
        except Exception:  # noqa: BLE001 — sidecar live hong thi coi nhu khong co
            live_wr = None
    if new_wr is None:
        return {"promote": False,
                "reason": "mo hinh moi khong du doan duoc lenh nao "
                          "tren OOS (khong co win rate) — giu file cu",
                "new_win_rate": None, "rule_win_rate": rule_wr,
                "live_win_rate": live_wr}
    if rule_wr is not None and new_wr <= rule_wr:
        return {"promote": False,
                "reason": f"win rate OOS moi ({new_wr:.1%}) khong thang "
                          f"baseline quy tac ({rule_wr:.1%}) — giu file cu",
                "new_win_rate": new_wr, "rule_win_rate": rule_wr,
                "live_win_rate": live_wr}
    if live_wr is not None and new_wr <= live_wr:
        return {"promote": False,
                "reason": f"win rate OOS moi ({new_wr:.1%}) khong thang "
                          f"mo hinh live hien co ({live_wr:.1%}) — "
                          "giu file cu",
                "new_win_rate": new_wr, "rule_win_rate": rule_wr,
                "live_win_rate": live_wr}
    reason = (f"win rate OOS moi ({new_wr:.1%}) thang baseline quy tac "
              f"({rule_wr:.1%})" if rule_wr is not None
              else f"win rate OOS moi ({new_wr:.1%}) (baseline quy tac "
                   "khong co lenh OOS)")
    if live_wr is not None:
        reason += f" va mo hinh live ({live_wr:.1%})"
    else:
        reason += " (chua co mo hinh live)"
    return {"promote": True, "reason": reason,
            "new_win_rate": new_wr, "rule_win_rate": rule_wr,
            "live_win_rate": live_wr}


def train_walk_forward(cfg, symbol, bars=None, *, epochs=DEFAULT_EPOCHS,
                       seq_len=DEFAULT_SEQ_LEN, seed=DEFAULT_SEED,
                       folds=3, train_bars=60, test_bars=20,
                       step_bars=20, candidates=None, stride=1,
                       include_outcomes=True, days=90, source="history"):
    """Kiem dinh walk-forward cho mo hinh outcome (validation
    only — KHONG ghi file mo hinh, KHONG promote).

    Moi fold: train tren train_bars cua so (tach 15% cuoi lam val
    cho early stopping), danh gia tren test_bars cua so tiep theo.
    Tra {n_folds, folds: [metrics moi fold], pooled: {accuracy,
    confusion, trade_score, n}} — pooled gop moi du doan OOS."""
    require_torch()
    if bars is None:
        bars = load_history_bars(cfg, symbol, days=days, source=source)
    dataset = build_tuning_dataset(
        cfg, symbol, bars, candidates=candidates, stride=stride,
        include_outcomes=include_outcomes)
    if dataset["n_samples"] == 0:
        dataset = fallback_dataset(cfg, symbol, bars)
    Xseq, yseq, _mseq = event_sequences(
        cfg, symbol, bars, dataset["meta"], dataset["y"],
        seq_len=seq_len)
    if len(Xseq) < train_bars + test_bars:
        raise ValueError(
            f"Khong du cua so cho walk-forward ({symbol}): can toi "
            f"thieu {train_bars + test_bars}, chi co {len(Xseq)}")
    fold_idx = walk_forward_folds(len(Xseq), train_bars, test_bars,
                                  step_bars)[:max(1, int(folds))]
    pooled_true, pooled_pred = [], []
    fold_reports = []
    for fi, (tr_idx, te_idx) in enumerate(fold_idx):
        n_val = max(1, int(len(tr_idx) * 0.15))
        tr_main, va_idx = tr_idx[:-n_val], tr_idx[-n_val:]
        mean, std = fit_scaler([Xseq[i] for i in tr_main])
        Xtr = apply_scaler([Xseq[i] for i in tr_main], mean, std)
        Xva = apply_scaler([Xseq[i] for i in va_idx], mean, std)
        Xte = apply_scaler([Xseq[i] for i in te_idx], mean, std)
        ytr = [yseq[i] for i in tr_main]
        yva = [yseq[i] for i in va_idx]
        yte = [yseq[i] for i in te_idx]
        weights, _counts = _class_weights(ytr)
        model, info = _train_one_fold(
            Xtr, ytr, Xva, yva, N_FEATURES, CLASSES, epochs,
            seed + fi, weights)
        pred = _predict(model, Xte)
        pooled_true.extend(yte)
        pooled_pred.extend(pred)
        fold_reports.append({
            "fold": fi, "n_train": len(tr_idx), "n_test": len(te_idx),
            "metrics": classification_metrics(yte, pred),
            "trade_score": trade_score(yte, pred),
            "epochs_run": info["epochs_run"],
            "best_val_loss": info["best_val_loss"]})
    pooled = {"accuracy": classification_metrics(
                  pooled_true, pooled_pred)["accuracy"],
              "confusion": classification_metrics(
                  pooled_true, pooled_pred)["confusion"],
              "per_class": classification_metrics(
                  pooled_true, pooled_pred)["per_class"],
              "trade_score": trade_score(pooled_true, pooled_pred),
              "n": len(pooled_true)}
    return {"n_folds": len(fold_reports), "folds": fold_reports,
            "pooled": pooled}


def train(cfg, symbol, bars=None, *, epochs=DEFAULT_EPOCHS,
          seq_len=DEFAULT_SEQ_LEN, models_dir=None, promote=True,
          seed=DEFAULT_SEED, folds=1, candidates=None, stride=1,
          include_outcomes=True, days=90, source="history"):
    """Train mo hinh outcome cho 1 symbol. Tra report dict.

    bars: list bar M15 (None thi doc kho lich su theo days/source).
    folds > 1: chay train_walk_forward truoc de lay
    walkforward_metrics roi moi train model chinh (tach 70/15/15).
    promote=True: ap gate — chi ghi .pt/.json khi thang baseline
    quy tac + mo hinh live; report JSON thi luon ghi.
    Raise TorchNotAvailable (ten ai-setup) neu chua cai torch;
    InsufficientHistoryError neu lich su qua ngan."""
    require_torch()
    started = time.perf_counter()
    if bars is None:
        bars = load_history_bars(cfg, symbol, days=days, source=source)
    bars = sorted(bars or [], key=lambda b: b.get("time", 0))
    wf_metrics = None
    if int(folds) > 1:
        try:
            wf_metrics = train_walk_forward(
                cfg, symbol, bars, epochs=epochs, seq_len=seq_len,
                seed=seed, folds=folds, candidates=candidates,
                stride=stride, include_outcomes=include_outcomes)
        except ValueError as exc:
            wf_metrics = {"error": str(exc), "n_folds": 0}
    try:
        dataset = build_tuning_dataset(
            cfg, symbol, bars, candidates=candidates, stride=stride,
            include_outcomes=include_outcomes)
        used_fallback = False
        if dataset["n_samples"] == 0:
            dataset = fallback_dataset(cfg, symbol, bars)
            used_fallback = True
    except InsufficientHistoryError:
        raise
    if dataset["n_samples"] == 0:
        raise ValueError(
            f"Khong xay duoc mau huan luyen nao cho {symbol} "
            f"({len(bars)} bar) — quy tac khong kich hoat lan nao "
            "voi bat ky bo tham so ung vien nao va log outcome "
            "trong. Thu giam nguong gate (adx_min / min_atr_pct) "
            "hoac backfill them lich su.")
    Xseq, yseq, mseq = event_sequences(
        cfg, symbol, bars, dataset["meta"], dataset["y"],
        seq_len=seq_len)
    if len(Xseq) < 10:
        raise ValueError(
            f"Khong du cua so huan luyen cho {symbol}: can it nhat "
            f"10, chi co {len(Xseq)} (mau {dataset['n_samples']}, "
            f"seq_len {seq_len}) — backfill them lich su.")
    tr_idx, va_idx, te_idx = chronological_split(len(Xseq))
    if not tr_idx or not va_idx or not te_idx:
        raise ValueError(
            f"Khong du cua so de tach train/val/test cho {symbol} "
            f"({len(Xseq)} cua so) — backfill them lich su.")
    mean, std = fit_scaler([Xseq[i] for i in tr_idx])
    Xtr = apply_scaler([Xseq[i] for i in tr_idx], mean, std)
    Xva = apply_scaler([Xseq[i] for i in va_idx], mean, std)
    Xte = apply_scaler([Xseq[i] for i in te_idx], mean, std)
    ytr = [yseq[i] for i in tr_idx]
    yva = [yseq[i] for i in va_idx]
    yte = [yseq[i] for i in te_idx]
    mte = [mseq[i] for i in te_idx]
    weights, train_counts = _class_weights(ytr)
    model, info = _train_one_fold(Xtr, ytr, Xva, yva, N_FEATURES,
                                  CLASSES, epochs, seed, weights)
    pred = _predict(model, Xte)
    oos_metrics = classification_metrics(yte, pred)
    oos_trade = trade_score(yte, pred)
    baselines = naive_baselines(yte)
    baselines["rule_based"] = {
        "trade_score": rule_baseline_oos(
            cfg, symbol, bars, dataset["meta"], dataset["y"], mte)}
    oos = {"accuracy": oos_metrics["accuracy"], "n": oos_metrics["n"],
           "per_class": oos_metrics["per_class"],
           "confusion": oos_metrics["confusion"],
           "trade_score": oos_trade, "baselines": baselines}
    config = ModelConfig(n_features=N_FEATURES, seq_len=seq_len,
                         classes=tuple(CLASSES), label_mode="tp_sl")
    sidecar = {
        "symbol": symbol, "label_mode": "tp_sl",
        "classes": list(CLASSES),
        "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "param_feature_names": list(PARAM_FEATURE_NAMES),
        "param_feature_version": PARAM_FEATURE_VERSION,
        "mean": list(mean), "std": list(std), "seq_len": int(seq_len),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "bars_used": len(bars),
        "walkforward_metrics": wf_metrics,
        "oos_metrics": oos,
    }
    models_base = resolve_models_dir(cfg, models_dir)
    models_base.mkdir(parents=True, exist_ok=True)
    report_path = models_base / f"{symbol}.report.json"
    pt_path, json_path = model_paths(symbol, models_base)
    report = {
        "symbol": symbol, "label_mode": "tp_sl",
        "classes": list(CLASSES), "seq_len": int(seq_len),
        "feature_version": FEATURE_VERSION,
        "n_features": N_FEATURES,
        "bars_used": len(bars),
        "n_samples": dataset["n_samples"],
        "n_windows": len(Xseq),
        "used_fallback_dataset": used_fallback,
        "dataset_stats": dataset.get("stats"),
        "class_counts": dataset.get("class_counts"),
        "split": {"train": len(tr_idx), "val": len(va_idx),
                  "test": len(te_idx)},
        "class_counts_train": dict(zip(CLASSES, train_counts)),
        "class_weights": [round(w, 3) for w in weights],
        "epochs_run": info["epochs_run"],
        "epochs_requested": int(epochs),
        "best_val_loss": info["best_val_loss"],
        "train_seconds": round(time.perf_counter() - started, 2),
        "oos": oos,
        "walkforward_metrics": wf_metrics,
        "promotion": None,
        "model_path": None, "sidecar_path": None,
        "report_path": str(report_path),
    }
    gate = evaluate_model_promotion(symbol, report, models_base)
    if promote and gate["promote"]:
        save_model(model, config, sidecar, pt_path, json_path)
        report["promotion"] = dict(gate, promoted=True)
        report["model_path"] = str(pt_path)
        report["sidecar_path"] = str(json_path)
    else:
        reason = gate["reason"] if promote else (
            "promote=False (chi train, khong ghi file mo hinh)")
        report["promotion"] = dict(gate, promoted=False,
                                   reason=reason)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def format_report(report):
    """In bao cao train thanh van ban (tieng Viet khong dau)."""
    oos = report.get("oos") or {}
    trade = oos.get("trade_score") or {}
    rule = ((oos.get("baselines") or {}).get("rule_based") or {}).get(
        "trade_score") or {}
    naive = ((oos.get("baselines") or {}).get("previous_label") or {}).get(
        "trade_score") or {}
    promo = report.get("promotion") or {}
    def _pct(v):
        return f"{v:.1%}" if v is not None else "n/a"
    lines = [
        f"AI-TRAIN {report.get('symbol')}: {report.get('n_windows')} "
        f"cua so ({report.get('n_samples')} mau, "
        f"{report.get('bars_used')} bar) — "
        f"train {report.get('split', {}).get('train')} / val "
        f"{report.get('split', {}).get('val')} / OOS "
        f"{report.get('split', {}).get('test')} — "
        f"{report.get('epochs_run')}/{report.get('epochs_requested')} "
        f"epoch, {report.get('train_seconds')}s",
        f"  OOS accuracy: {_pct(oos.get('accuracy'))} (n={oos.get('n')})",
    ]
    for name, pc in (oos.get("per_class") or {}).items():
        p = pc.get("precision")
        r = pc.get("recall")
        lines.append(
            f"    {name}: precision "
            f"{f'{p:.1%}' if p is not None else 'n/a'} | recall "
            f"{f'{r:.1%}' if r is not None else 'n/a'} | "
            f"n={pc.get('support')}")
    lines.append(
        f"  OOS win rate (mo hinh): {_pct(trade.get('win_rate'))} "
        f"({trade.get('wins')} thang / {trade.get('losses')} thua / "
        f"{trade.get('timeouts')} timeout, {trade.get('n_trades')} lenh)")
    lines.append(
        f"  OOS win rate (quy tac hien tai): {_pct(rule.get('win_rate'))} "
        f"({rule.get('wins')} thang / {rule.get('losses')} thua / "
        f"{rule.get('timeouts')} timeout, {rule.get('n_trades')} lenh)")
    lines.append(
        f"  OOS win rate (naive previous-label): "
        f"{_pct(naive.get('win_rate'))} ({naive.get('n_trades')} lenh)")
    lines.append(
        "  PROMOTION: " + ("GHI FILE MO HINH" if promo.get("promoted")
                           else "GIU FILE CU") +
        f" — {promo.get('reason')}")
    if report.get("model_path"):
        lines.append(f"  Model: {report['model_path']}")
    lines.append(f"  Bao cao: {report.get('report_path')}")
    return "\n".join(lines)


__all__ = ["CLASSES", "N_FEATURES", "DEFAULT_EPOCHS",
           "chronological_split",
           "walk_forward_folds", "fit_scaler", "apply_scaler",
           "classification_metrics", "trade_score", "naive_baselines",
           "rule_baseline_oos", "train_walk_forward", "train",
           "evaluate_model_promotion", "format_report"]
