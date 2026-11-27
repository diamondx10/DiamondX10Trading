"""Chinh tham so TA tu log + lich su bang mo hinh outcome (ai/tune.py).

VAI TRO (user chot 2026-11-27): AI khong tao tin hieu doc lap —
no hoc anh xa (context thi truong + tham so TA) -> ket qua lenh
(P(thang | context, params)) roi dung anh xa do de TIM tham so
tot hon. De xuat di qua duong ta-review co san (kiem chung OOS
bang walk-forward, ghi file decisions/ta-tuning-proposals-*.yaml,
KHONG BAO GIO tu ap).

DU LIEU HUAN LUYEN — can BIEN DOI THAM SO, neu khong mo hinh
khong hoc duoc params -> outcome. 2 nguon, deu offline tu bar
lich su M15 + log outcome, deu giu no-lookahead (feature chi
bar <= t, nhan chi bar > t):
  (a) COUNTERFACTUAL: tai moi bar t, chay chien luoc quy tac
      hien co voi tung bo tham so ung vien (candidate_param_sets)
      tren dung 60 bar gan nhat (= DEFAULT_BARS cua vong live,
      live.py — cung cua so, cung cach tinh chi bao nhu live that).
      Ung vien nao kich hoat (BUY/SELL) thi sinh 1 mau: feature
      35 cot context (tinh theo tham so ung vien) + 13 cot tham
      so, nhan TP/SL-first tren 20 bar sau (giong evaluator).
      Mau chi ton tai o noi quy tac kich hoat duoi tham so do —
      dung nhu thiet ke (mo hinh hoc P(thang | context, params)
      tai chinh nhung diem quy tac se vao lenh).
  (b) LOG DA DANH GIA: ban ghi trong
      decisions/signal-outcomes-evaluated.jsonl (co `outcome` +
      context.resolved_params = tham so THAT da dung luc phat tin
      hieu — outcomes.py ghi lai). Moi ban ghi -> 1 mau, feature
      xay theo tham so lich su do, nhan lay thang tu evaluator
      (khong cham lai). Trung (symbol, time, direction) voi mau
      counterfactual thi giu mau log (ket qua that + tham so that).

LUONG TUNE (ai-tune):
  1. Xep hang ung vien bang mo hinh: tren cac bar gan nhat
     (rank_bars), voi moi ung vien, chay quy tac de biet no kich
     hoat o dau, xay chuoi 32 hang, mo hinh du doan P(tp_first)
     trung binh — do la win rate du doan cua bo tham so do.
  2. Lay top-K ung vien -> kiem chung OOS THAT bang duong
     walk-forward co san (backtest.run_walk_forward, giong
     ta_review._validate_oos): return OOS cua bo ung vien phai
     thang return OOS cua tham so hien tai, voi du lenh OOS.
  3. Chi ung vien QUA kiem chung moi duoc ghi de xuat (1 de xuat
     / tham so doi, cung oos_validation — de ta-review --apply
     ap duoc tung tham so). Khong co ung vien nao qua thi khong
     ghi file.

CANH BAO TRUNG THUC (ghi ca trong doc): mo hinh duoc train tren
toan bo lich su, nen xep hang tren bar gan nhat KHONG hoan toan
OOS — walk-forward o buoc 2 la bo loc thu 2 cho hieu nang THAT
cua quy tac (khong phai cua du doan mo hinh), nhung viec chon
ung vien van dua tren mo hinh da thay lich su nay (selection
bias). De xuat van can Phu/Yuling duyet tay nhu moi de xuat
ta-review khac.
"""
import copy
from datetime import datetime, timezone
from pathlib import Path

from .dataset import (
    FEATURE_WINDOW,
    LABEL_NAMES_TP_SL,
    _OUTCOME_TO_TP_SL,
    build_dataset,
    class_counts,
    label_tp_sl,
    levels_for,
)
from .features import FEATURE_NAMES, FEATURE_VERSION, build_features
from .params import (
    PARAM_FEATURE_NAMES,
    PARAM_FEATURE_VERSION,
    candidate_param_sets,
    current_params,
    param_key,
    param_vector,
    strategy_with_params,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DECISIONS_DIR = REPO_ROOT / "decisions"

# Cua so kich hoat = so bar live lay moi chu ky (live.DEFAULT_BARS).
LIVE_WINDOW_BARS = 60
DEFAULT_RANK_BARS = 2000
DEFAULT_TOP_K = 3
DEFAULT_MIN_TRADES = 5


def _desk_for_symbol(cfg, symbol):
    """Desk chua symbol (config truoc, KNOWN_DESKS sau)."""
    from .dataset import _desk_for_symbol as _resolve_desk
    return _resolve_desk(cfg, symbol)


def _learning_window(cfg, outcome_window):
    """Cua so cham diem: tham so > config learning > 20."""
    from .dataset import _learning_window as _lw
    return _lw(cfg, outcome_window)


def load_history_bars(cfg, symbol, days=None, source="history",
                      store=None):
    """Bar M15 cho 1 symbol: 'history' (HistoryStore, can backfill
    truoc) hoac 'simulated' (SimulatedFeed — chi demo/test).
    days: so ngay gan nhat (None = history.backfill_days, mac
    dinh 90). Tra list bar sap theo time."""
    from datetime import timedelta
    if source not in ("history", "simulated"):
        raise ValueError("source phai la 'history' hoac 'simulated', "
                         f"nhan {source!r}")
    if source == "simulated":
        from ..data.feeds import SimulatedFeed
        desk = _desk_for_symbol(cfg, symbol)
        n = max(1, int(days or 90)) * 96  # 96 bar M15 / ngay
        bars = SimulatedFeed(desk).bars(min(n, 500))
        return sorted(bars, key=lambda b: b.get("time", 0))
    history_cfg = (cfg or {}).get("history") or {}
    days = int(days) if days is not None else int(
        history_cfg.get("backfill_days") or 90)
    if days <= 0:
        raise ValueError(f"--days phai > 0 (nhan {days!r})")
    from ..data.history import HistoryStore
    own_store = store is None
    store = store or HistoryStore(history_cfg.get("db_path")
                                  or "data/history.db")
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        bars = store.get_bars(symbol, "M15", start=start, end=end)
    finally:
        if own_store:
            store.close()
    return sorted(bars, key=lambda b: b.get("time", 0))


def counterfactual_samples(cfg, symbol, bars, candidates=None, *,
                           outcome_window=None, stride=1):
    """Mau counterfactual: quy tac chay voi tung bo tham so ung vien.

    bars: list bar sap theo time. candidates: list {name,
    overrides} (None = candidate_param_sets). stride: chi xet
    moi `stride` bar (mac dinh 1 — moi bar). Tra (X, y, meta,
    stats): X hang 48 cot (35 context + 13 tham so), y ma lop
    tp_sl, meta {symbol, time, direction, entry, sl, tp, atr,
    bars_held, label_name, source, candidate, param_key, params,
    feature_version}, stats {bars_scanned, fired, by_candidate,
    skipped_no_levels}.
    """
    desk = _desk_for_symbol(cfg, symbol)
    window = _learning_window(cfg, outcome_window)
    if candidates is None:
        candidates, _cstats = candidate_param_sets(cfg, desk, symbol)
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    n = len(ordered)
    X, y, meta = [], [], []
    stats = {"bars_scanned": 0, "fired": 0, "by_candidate": {},
             "skipped_no_levels": 0}
    last_t = n - window - 1
    for cand in candidates:
        strat, merged = strategy_with_params(
            cfg, desk, symbol, cand["overrides"])
        key = param_key(cand["overrides"])
        pvec = param_vector(merged)
        fired = 0
        for t in range(FEATURE_WINDOW - 1, last_t + 1, max(1, stride)):
            stats["bars_scanned"] += 1
            win60 = ordered[max(0, t - LIVE_WINDOW_BARS + 1):t + 1]
            try:
                action, _reason, levels = strat.signal(win60)
            except Exception:  # noqa: BLE001 — signal loi thi bo bar
                continue
            if action not in ("BUY", "SELL"):
                continue
            levels = levels or {}
            entry = levels.get("entry")
            sl, tp = levels.get("sl"), levels.get("tp")
            atr_val = levels.get("atr")
            if entry is None or sl is None or tp is None:
                stats["skipped_no_levels"] += 1
                continue
            future = ordered[t + 1:t + 1 + window]
            try:
                code, held = label_tp_sl(action, entry, sl, tp, future)
                row = build_features(win60[-FEATURE_WINDOW:],
                                     params=merged, direction=action)
            except ValueError:
                continue
            X.append(list(row) + list(pvec))
            y.append(code)
            meta.append({
                "symbol": symbol,
                "time": win60[-1].get("time"),
                "direction": action,
                "entry": float(entry), "sl": float(sl),
                "tp": float(tp),
                "atr": (float(atr_val) if atr_val is not None else None),
                "bars_held": int(held),
                "label_name": LABEL_NAMES_TP_SL[code],
                "source": "counterfactual",
                "candidate": cand["name"],
                "param_key": key,
                "params": dict(merged),
                "feature_version": FEATURE_VERSION,
            })
            fired += 1
        stats["by_candidate"][cand["name"]] = fired
        stats["fired"] += fired
    return X, y, meta, stats


def log_samples(cfg, symbol, bars=None, *, store=None,
                outcomes_records=None, outcomes_path=None):
    """Mau tu log outcome DA DANH GIA, voi tham so THAT luc phat
    tin hieu (record.context.resolved_params).

    bars: list bar (None thi doc HistoryStore). outcomes_records:
    list ban ghi (None thi doc file mac dinh
    decisions/signal-outcomes-evaluated.jsonl; neu file thieu thi
    thu file signal-outcomes.jsonl goc). Ban ghi chua co outcome /
    khac symbol / thieu bar truoc thoi diem tin hieu thi bo qua,
    dem vao stats. Tra (X, y, meta, stats)."""
    from ..evaluator import _signal_time
    from ..outcomes import DEFAULT_STORE as DEFAULT_OUTCOMES
    from ..outcomes import load as load_outcomes
    desk = _desk_for_symbol(cfg, symbol)
    current = current_params(cfg, desk, symbol)
    if outcomes_records is None:
        evaluated = REPO_ROOT / "decisions" / "signal-outcomes-evaluated.jsonl"
        records = load_outcomes(
            outcomes_path or (evaluated if evaluated.exists()
                              else DEFAULT_OUTCOMES))
    else:
        records = outcomes_records
    if bars is None:
        bars = load_history_bars(cfg, symbol, days=None,
                                 source="history", store=store)
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    times = [b.get("time", 0) for b in ordered]
    stats = {"included": 0, "skipped_unevaluated": 0, "skipped_bad": 0,
             "skipped_no_bars": 0, "skipped_other_symbol": 0}
    X, y, meta = [], [], []
    for record in records or []:
        if not isinstance(record, dict):
            stats["skipped_bad"] += 1
            continue
        if str(record.get("symbol") or "") != symbol:
            stats["skipped_other_symbol"] += 1
            continue
        outcome = record.get("outcome")
        if outcome not in _OUTCOME_TO_TP_SL:
            stats["skipped_unevaluated"] += 1
            continue
        action = (record.get("action") or "").strip().upper()
        signal_epoch = _signal_time(record)
        if action not in ("BUY", "SELL") or signal_epoch is None:
            stats["skipped_bad"] += 1
            continue
        ctx = record.get("context") or {}
        resolved = ctx.get("resolved_params")
        params = dict(resolved) if isinstance(resolved, dict) and resolved \
            else dict(current)
        # Tim cua so 50 bar ket thuc o / truoc thoi diem tin hieu.
        import bisect
        idx = bisect.bisect_right(times, signal_epoch) - 1
        if idx < FEATURE_WINDOW - 1:
            stats["skipped_no_bars"] += 1
            continue
        window = ordered[idx - FEATURE_WINDOW + 1:idx + 1]
        try:
            row = build_features(window, params=params, direction=action)
        except ValueError:
            stats["skipped_bad"] += 1
            continue
        code = _OUTCOME_TO_TP_SL[outcome]
        key = param_key({}) if params == current else param_key(params)
        X.append(list(row) + param_vector(params))
        y.append(code)
        meta.append({
            "symbol": symbol,
            "time": window[-1].get("time"),
            "direction": action,
            "entry": record.get("entry"),
            "sl": record.get("sl"),
            "tp": record.get("tp"),
            "atr": (ctx.get("atr") if isinstance(ctx, dict) else None),
            "bars_held": record.get("bars_held"),
            "label_name": LABEL_NAMES_TP_SL[code],
            "source": "outcomes-log",
            "candidate": "logged",
            "param_key": key,
            "params": dict(params),
            "feature_version": FEATURE_VERSION,
            "outcome_id": record.get("id"),
        })
        stats["included"] += 1
    return X, y, meta, stats


def build_tuning_dataset(cfg, symbol, bars=None, *, candidates=None,
                         outcome_window=None, stride=1,
                         include_outcomes=True, store=None,
                         outcomes_records=None, outcomes_path=None,
                         min_samples=10):
    """Dataset huan luyen mo hinh outcome cho 1 symbol.

    Gop mau counterfactual (nguon chinh — co bien doi tham so) +
    mau log da danh gia (tham so that). Dedupe theo (symbol, time,
    direction): giu mau log. Tra dict {symbol, desk, timeframe,
    feature_version, feature_names, param_feature_names,
    param_feature_version, label_mode, label_names,
    outcome_window_bars, min_samples, n_samples, class_counts,
    current_params, X, y, meta, stats}.
    Raise InsufficientHistoryError khi lich su qua ngan (giong
    build_dataset); n_samples == 0 van tra dict (train() se
    fallback ve build_dataset hoac bao loi sach)."""
    from .dataset import InsufficientHistoryError
    desk = _desk_for_symbol(cfg, symbol)
    window = _learning_window(cfg, outcome_window)
    if bars is None:
        bars = load_history_bars(cfg, symbol, days=None,
                                 source="history", store=store)
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    needed = FEATURE_WINDOW + window + max(1, int(min_samples)) - 1
    if len(ordered) < needed:
        raise InsufficientHistoryError(
            "Lich su M15 cho symbol %s qua ngan de xay dataset tune: "
            "can it nhat %d bar (cua so feature %d + cua so nhan %d + "
            "%d mau toi thieu - 1), hien chi co %d bar — chay "
            "`backfill` them roi thu lai."
            % (symbol, needed, FEATURE_WINDOW, window,
               max(1, int(min_samples)), len(ordered)))
    if candidates is None:
        candidates, cand_stats = candidate_param_sets(cfg, desk, symbol)
    else:
        cand_stats = {"n_generated": len(candidates),
                      "skipped_invalid": 0, "skipped_duplicate": 0}
    X, y, meta, cf_stats = counterfactual_samples(
        cfg, symbol, ordered, candidates, outcome_window=window,
        stride=stride)
    stats = {"candidates": cand_stats, "counterfactual": cf_stats,
             "outcomes": None, "deduped": 0}
    if include_outcomes:
        oX, oy, ometa, ostats = log_samples(
            cfg, symbol, ordered, outcomes_records=outcomes_records,
            outcomes_path=outcomes_path)
        stats["outcomes"] = ostats
        seen = {(m["symbol"], m.get("time"), m["direction"])
                for m in meta}
        kept = [(x, c, m) for x, c, m in zip(oX, oy, ometa)
                if (m["symbol"], m.get("time"), m["direction"])
                not in seen]
        stats["deduped"] = len(oX) - len(kept)
        for x, c, m in kept:
            X.append(x)
            y.append(c)
            meta.append(m)
    return {
        "symbol": symbol, "desk": desk, "timeframe": "M15",
        "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "param_feature_names": list(PARAM_FEATURE_NAMES),
        "param_feature_version": PARAM_FEATURE_VERSION,
        "label_mode": "tp_sl",
        "label_names": list(LABEL_NAMES_TP_SL),
        "outcome_window_bars": window,
        "min_samples": max(1, int(min_samples)),
        "n_samples": len(y),
        "class_counts": class_counts(y, LABEL_NAMES_TP_SL),
        "current_params": dict(current_params(cfg, desk, symbol)),
        "X": X, "y": y, "meta": meta,
        "stats": stats,
    }


def fallback_dataset(cfg, symbol, bars=None, *, outcome_window=None):
    """Dataset du phong khi counterfactual khong sinh duoc mau nao
    (vd quy tac khong kich hoat lan nao): dung build_dataset co
    san — moi bar deu sinh mau voi tham so HIEN TAI (vector tham
    so hang so, mo hinh khong hoc duoc tac dong tham so nhung van
    train duoc). Tra dict cung shape voi build_tuning_dataset
    (X 48 cot) + stats {fallback: True}."""
    from .dataset import build_dataset as _build
    base = _build(cfg, symbol, bars=bars, outcome_window=outcome_window)
    pvec = param_vector(base["params"])
    X = [list(row) + list(pvec) for row in base["X"]]
    meta = []
    for m in base["meta"]:
        m2 = dict(m)
        m2["source"] = "bars-current-params"
        m2["candidate"] = "current"
        m2["param_key"] = param_key({})
        m2["params"] = dict(base["params"])
        meta.append(m2)
    out = dict(base)
    out.update({
        "param_feature_names": list(PARAM_FEATURE_NAMES),
        "param_feature_version": PARAM_FEATURE_VERSION,
        "current_params": dict(base["params"]),
        "X": X, "y": list(base["y"]), "meta": meta,
        "stats": {"fallback": True,
                  "reason": "counterfactual khong sinh duoc mau nao — "
                            "dung mau bar voi tham so hien tai"},
    })
    return out


def event_sequences(cfg, symbol, bars, meta, y, seq_len=32):
    """Chuoi 32 bar lien tiep cho moi su kien vao lenh (mau).

    Moi mau (meta) la 1 lan quy tac kich hoat tai bar t (huong +
    bo tham so trong meta["params"]). Chuoi cua no la 32 hang
    feature LIEN TIEP theo thoi gian ket thuc o t (hang s =
    build_features tren 50 bar ket thuc o s + vector tham so),
    nhan = nhan cua su kien (TP/SL-first tren 20 bar SAU t).
    Hang trong chuoi CHI dung bar <= s (khong lookahead); nhan
    chi dung bar > t. Cac chuoi sap theo time tang dan (de tach
    chronological). Row cache theo (bar, huong, bo tham so) —
    cac su kien kich hoat gan nhau dung chung hang.

    Ly do khong nhom truc tiep cac hang mau roi truot cua so:
    mau chi ton tai o diem quy tac kich hoat (thua, khong lien
    tuc) — nhom (huong, tham so) roi truot se tao chuoi gom cac
    diem kich hoat cach nhau nhieu bar, khong phai 32 bar lien
    tiep, va nhom thuong ngan hon seq_len (0 chuoi). Tra (Xseq,
    yseq, mseq) voi mseq la meta cua su kien (hang cuoi chuoi).
    """
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    time_to_idx = {}
    for i, b in enumerate(ordered):
        time_to_idx.setdefault(b.get("time"), i)
    cache = {}
    seqs = []
    for m, code in zip(meta or [], y or []):
        direction = m.get("direction")
        params = m.get("params") or {}
        key_params = m.get("param_key")
        t = time_to_idx.get(m.get("time"))
        if t is None or direction not in ("BUY", "SELL"):
            continue
        if t - seq_len + 1 < FEATURE_WINDOW - 1:
            continue
        rows = []
        ok = True
        for s in range(t - seq_len + 1, t + 1):
            ck = (s, direction, key_params)
            row = cache.get(ck)
            if row is None:
                win = ordered[s - FEATURE_WINDOW + 1:s + 1]
                if len(win) < FEATURE_WINDOW:
                    ok = False
                    break
                try:
                    row = (list(build_features(win, params=params,
                                               direction=direction))
                           + param_vector(params))
                except ValueError:
                    ok = False
                    break
                cache[ck] = row
            rows.append(row)
        if not ok or len(rows) < seq_len:
            continue
        seqs.append((rows, int(code), dict(m)))
    seqs.sort(key=lambda s: (s[2].get("time") or 0))
    return ([s[0] for s in seqs], [s[1] for s in seqs],
            [s[2] for s in seqs])


def score_candidate(cfg, symbol, bars, candidate, model, sidecar, *,
                    seq_len=32, outcome_window=None):
    """Win rate DU DOAN cua 1 bo tham so ung vien.

    Chay quy tac voi tham so ung vien tren `bars` (bar gan nhat):
    cho nao kich hoat thi xay chuoi 32 hang, mo hinh du doan
    P(tp_first) — trung binh cac cua so la win rate du doan.
    Tra {candidate, n_fired, n_windows, mean_p_tp, mean_p_sl,
    mean_p_timeout, by_direction}. sidecar cho mean/std (scaler)
    + classes (tim cot tp_first). Can torch (model da load)."""
    from .model import predict_proba
    from .train import apply_scaler
    rows_X, rows_y, rows_meta, _stats = counterfactual_samples(
        cfg, symbol, bars, [candidate], outcome_window=outcome_window)
    result = {"candidate": candidate["name"],
              "overrides": dict(candidate["overrides"]),
              "n_fired": len(rows_y), "n_windows": 0,
              "mean_p_tp": None, "mean_p_sl": None,
              "mean_p_timeout": None, "by_direction": {}}
    if not rows_y:
        return result
    Xseq, _yseq, mseq = event_sequences(
        cfg, symbol, bars, rows_meta, rows_y, seq_len=seq_len)
    if not Xseq:
        return result
    mean, std = sidecar.get("mean"), sidecar.get("std")
    Xseq = apply_scaler(Xseq, mean, std)
    probs = predict_proba(model, Xseq)
    classes = list(sidecar.get("classes") or LABEL_NAMES_TP_SL)
    i_tp = classes.index("tp_first") if "tp_first" in classes else 2
    i_sl = classes.index("sl_first") if "sl_first" in classes else 0
    i_to = classes.index("timeout") if "timeout" in classes else 1
    result["n_windows"] = len(probs)
    result["mean_p_tp"] = sum(p[i_tp] for p in probs) / len(probs)
    result["mean_p_sl"] = sum(p[i_sl] for p in probs) / len(probs)
    result["mean_p_timeout"] = sum(p[i_to] for p in probs) / len(probs)
    for direction in ("BUY", "SELL"):
        idx = [k for k, m in enumerate(mseq)
               if m.get("direction") == direction]
        if idx:
            result["by_direction"][direction] = {
                "n_windows": len(idx),
                "mean_p_tp": sum(probs[k][i_tp] for k in idx) / len(idx),
            }
    return result


def rank_candidates(cfg, symbol, bars, candidates, model, sidecar, *,
                    seq_len=32, rank_bars=DEFAULT_RANK_BARS,
                    min_trades=DEFAULT_MIN_TRADES,
                    outcome_window=None):
    """Xep hang ung vien theo win rate du doan (cao -> thap).

    bars: toan bo lich su; chi dung `rank_bars` bar gan nhat de
    xep hang. Ung vien co n_windows < min_trades thi loai khoi
    bang xep hang (ghi vao filtered). Tra (ranked, filtered):
    ranked sap theo mean_p_tp giam dan."""
    recent = list(bars or [])[-max(1, int(rank_bars)):]
    ranked, filtered = [], []
    for cand in candidates:
        scored = score_candidate(cfg, symbol, recent, cand, model,
                                 sidecar, seq_len=seq_len,
                                 outcome_window=outcome_window)
        if scored["n_windows"] < min_trades:
            scored["filter_reason"] = (
                f"it lenh du doan ({scored['n_windows']} < "
                f"{min_trades})")
            filtered.append(scored)
        else:
            ranked.append(scored)
    ranked.sort(key=lambda r: (r["mean_p_tp"] is not None,
                               r["mean_p_tp"] or 0.0), reverse=True)
    return ranked, filtered


def validate_candidate_oos(cfg, symbol, overrides, bars):
    """Kiem chung OOS THAT 1 bo tham so bang walk-forward co san.

    Giong ta_review._validate_oos nhung cho CA BO tham so (khong
    phai 1 tham so): cfg_try = config voi per_symbol[symbol] ap
    toan bo overrides; chay run_walk_forward cho ca cfg goc va
    cfg_try tren cung bar; validated = co lenh OOS va return OOS
    cua ung vien thang return OOS cua tham so hien tai. Tra dict
    cung shape voi ta_review oos_validation (oos_win_rate o day
    la PHAN TRAM nhu backtest aggregated — giong ta_review).
    """
    desk = _desk_for_symbol(cfg, symbol)
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    if len(ordered) < 50:
        return {"oos_win_rate": None, "oos_return": None, "oos_n": 0,
                "validated": False,
                "reason": f"chi co {len(ordered)} bar lich su, can it "
                          "nhat 50 bar de chay walk-forward"}
    # test_bars PHAI lon hon nhieu so voi WARMUP_BARS (= 20) cua
    # backtest._run_segment: doan test chi 20 bar thi tin hieu chi
    # kich hoat duoc o bar cuoi cung roi bi dong ep ngay (lo phi) —
    # can test_bars >= 40 de lenh co du bar chay toi TP/SL.
    if len(ordered) >= 200:
        train_bars, test_bars, step_bars = 60, 40, 20
    elif len(ordered) >= 100:
        train_bars, test_bars, step_bars = 30, 40, 20
    else:
        train_bars, test_bars, step_bars = 10, 40, 10
    try:
        from ..backtest import run_walk_forward
        cfg_try = copy.deepcopy(cfg or {})
        cfg_try.setdefault("strategy", {})
        cfg_try["strategy"].setdefault("per_symbol", {})
        entry = dict(cfg_try["strategy"]["per_symbol"].get(symbol) or {})
        entry.update(overrides or {})
        cfg_try["strategy"]["per_symbol"][symbol] = entry
        bars_by_symbol = {symbol: ordered}
        base = run_walk_forward(
            desk, 0, cfg=cfg, symbols=[symbol],
            train_bars=train_bars, test_bars=test_bars,
            step_bars=step_bars, bars_by_symbol=bars_by_symbol)
        tried = run_walk_forward(
            desk, 0, cfg=cfg_try, symbols=[symbol],
            train_bars=train_bars, test_bars=test_bars,
            step_bars=step_bars, bars_by_symbol=bars_by_symbol)
    except Exception as exc:  # noqa: BLE001 — kiem chung loi thi ghi ly do
        return {"oos_win_rate": None, "oos_return": None, "oos_n": 0,
                "validated": False,
                "reason": f"kiem chung OOS loi: {exc}"}
    agg = tried["aggregated"]
    base_agg = base["aggregated"]
    oos_n = int(agg.get("n_trades") or 0)
    oos_return = agg.get("total_return_pct")
    validated = bool(oos_n > 0 and oos_return is not None
                     and base_agg.get("total_return_pct") is not None
                     and oos_return > base_agg["total_return_pct"])
    result = {"oos_win_rate": agg.get("win_rate"),
              "oos_return": oos_return, "oos_n": oos_n,
              "validated": validated,
              "baseline_oos_return": base_agg.get("total_return_pct"),
              "baseline_oos_n": int(base_agg.get("n_trades") or 0)}
    if not validated:
        result["reason"] = (
            "ung vien khong thang tham so hien tai tren OOS "
            f"(ung vien {oos_return}%, hien tai "
            f"{base_agg.get('total_return_pct')}%, lenh OOS {oos_n})"
            if oos_n > 0 else
            "walk-forward OOS khong co lenh nao — khong ket luan duoc")
    return result


def tune_symbol(cfg, symbol, bars, model, sidecar, *,
                candidates=None, seq_len=32,
                rank_bars=DEFAULT_RANK_BARS, top_k=DEFAULT_TOP_K,
                min_trades=DEFAULT_MIN_TRADES, min_oos_n=20,
                proposals_path=None, outcome_window=None):
    """Chay 1 vong tune cho 1 symbol: xep hang -> kiem chung OOS
    -> ghi de xuat (chi ung vien QUA kiem chung).

    bars: toan bo lich su M15. candidates: None = tap mac dinh.
    min_oos_n: so lenh OOS toi thieu moi duoc de xuat (mac dinh
    learning.min_sample_for_proposal, thuong 20). proposals_path:
    None = decisions/ta-tuning-proposals-<ngay-gio>.yaml mac dinh;
    truyen duong dan cu the cho test. Tra report dict {symbol,
    ranked, filtered, validated, rejected, proposals,
    proposals_path}. Khong bao gio tu doi config."""
    from ..ta_review import min_sample_for_proposal, write_proposals
    desk = _desk_for_symbol(cfg, symbol)
    if candidates is None:
        candidates, _cstats = candidate_param_sets(cfg, desk, symbol)
    if min_oos_n is None:
        min_oos_n = min_sample_for_proposal(cfg)
    ranked, filtered = rank_candidates(
        cfg, symbol, bars, candidates, model, sidecar, seq_len=seq_len,
        rank_bars=rank_bars, min_trades=min_trades,
        outcome_window=outcome_window)
    current = next((r for r in ranked
                    if r["candidate"] == "current"), None)
    current_wr = (current or {}).get("mean_p_tp")
    validated, rejected, proposals = [], [], []
    for scored in ranked[:max(1, int(top_k))]:
        if scored["candidate"] == "current":
            continue
        oos = validate_candidate_oos(cfg, symbol,
                                     scored["overrides"], bars)
        entry = {"candidate": scored["candidate"],
                 "overrides": dict(scored["overrides"]),
                 "predicted_win_rate": scored["mean_p_tp"],
                 "n_windows": scored["n_windows"],
                 "oos_validation": oos}
        if not oos.get("validated"):
            entry["reject_reason"] = oos.get("reason")
            rejected.append(entry)
            continue
        if oos.get("oos_n", 0) < min_oos_n:
            entry["reject_reason"] = (
                f"it lenh OOS ({oos.get('oos_n')} < {min_oos_n}) — "
                "chua du mau de xuat")
            rejected.append(entry)
            continue
        entry["validated"] = True
        validated.append(entry)
        current_p = current_params(cfg, desk, symbol)
        for param, new_value in sorted(scored["overrides"].items()):
            proposals.append({
                "symbol": symbol, "kind": "param",
                "param_or_rule": param,
                "current_value": current_p.get(param),
                "proposed_value": new_value,
                "evidence": {"metric": "predicted_win_rate",
                             "before": current_wr,
                             "after": scored["mean_p_tp"],
                             "n": scored["n_windows"]},
                "rationale": (
                    f"Mo hinh outcome du doan win rate "
                    f"{scored['mean_p_tp']:.0%} vs tham so hien tai "
                    f"{current_wr:.0%}" if current_wr is not None else
                    f"Mo hinh outcome du doan win rate "
                    f"{scored['mean_p_tp']:.0%}"
                    f" (n={scored['n_windows']} lenh du doan tren "
                    f"{min(rank_bars, len(bars or []))} bar gan nhat); "
                    f"walk-forward OOS: return {oos.get('oos_return')}% "
                    f"vs hien tai {oos.get('baseline_oos_return')}% "
                    f"({oos.get('oos_n')} lenh). Chi la de xuat — can "
                    "Phu/Yuling duyet, ap bang ta-review --apply."),
                "oos_validation": oos,
                "validated": True,
                "ready": True,
            })
    path = None
    if proposals:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        path = (Path(proposals_path) if proposals_path is not None
                else DEFAULT_DECISIONS_DIR
                / f"ta-tuning-proposals-{stamp}.yaml")
        write_proposals(proposals, path)
        path = str(path)
    return {"symbol": symbol, "ranked": ranked, "filtered": filtered,
            "validated": validated, "rejected": rejected,
            "proposals": proposals, "proposals_path": path}


__all__ = ["LIVE_WINDOW_BARS", "DEFAULT_RANK_BARS", "DEFAULT_TOP_K",
           "DEFAULT_MIN_TRADES", "load_history_bars",
           "counterfactual_samples", "log_samples",
           "build_tuning_dataset", "fallback_dataset",
           "event_sequences", "score_candidate", "rank_candidates",
           "validate_candidate_oos", "tune_symbol"]
