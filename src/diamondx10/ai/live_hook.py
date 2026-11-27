"""Mo hinh AI outcome trong vong live M15 (ai/live_hook.py).

VAI TRO (muc 65): mo hinh chi la CO VAN — du doan P(tp_first)
(xac suat thang) cua tin hieu BUY/SELL VUA DUOC quy tac TA tao ra,
voi tham so TA HIEN TAI. Mac dinh du doan chi gan vao tin hieu
dang boi canh (`ai_win_prob` / `ai_probs` / `ai_model_version`),
KHONG doi bat ky hanh vi giao dich nao: khong vuot gate cung,
khong dat lenh, khong doi size/risk, khong ghi de ma tran tong
hop TA+FA (muc 39-40, 61-63).

Chan lenh theo AI chi khi Phu BAT TAY trong config
(`ai.block_on_low_win_prob: true`, mac dinh false) — luc do tin
hieu vuot MOI gate (ke ca PTCB) ma `ai_win_prob <
ai.min_win_prob` (mac dinh 0.30) thi bi chan thanh
BLOCKED-AI-LOW-WIN-PROB, TRUOC khi dat lenh / tao khuyen nghi.
Chan nay nam SAU moi gate cung nen no khong bao gio mo duong
cho lenh nao, chi chan them.

SUY GIAM AN TOAN (graceful degradation): thieu file mo hinh /
model het han / file hong / khong tai duoc / chua cai torch /
khong du bar — vong live chay tiep KHONG CO AI, chi in 1 dong
canh bao (moi ly do 1 lan / process / symbol), KHONG BAO GIO
raise, khong traceback. Torch chi duoc cham khi that su load /
du doan (lazy, qua ai/model.py); import module nay luon an toan
khi chua cai torch.

CACHE: mo hinh nap 1 lan / process / symbol, cache theo
fingerprint (mtime + kich thuoc) cua file .pt/.json — file thay
doi (train lai, promote file moi) thi chu ky sau nap lai; file
khong doi thi khong nap lai. Loai du doan can it nhat
FEATURE_WINDOW + seq_len - 1 bar (mac dinh 50 + 32 - 1 = 81 bar
M15); live lay du so bar nay chi khi co file mo hinh (xem
live.process_symbol), khong thi lay 60 bar nhu cu.
"""
from datetime import datetime, timezone
from pathlib import Path

from .features import FEATURE_WINDOW, build_features
from .model import (
    ModelLoadError,
    TorchNotAvailable,
    load_model,
    load_sidecar,
    model_paths,
    predict_proba,
    resolve_models_dir,
)
from .params import param_vector

# Thu tu lop chuan cua dau ra: [P(sl_first), P(timeout), P(tp_first)].
CLASSES = ("sl_first", "timeout", "tp_first")
DEFAULT_SEQ_LEN = 32
DEFAULT_MIN_WIN_PROB = 0.30
DEFAULT_MAX_AGE_DAYS = 90

# Diem tiem cho test: monkeypatch 2 bien nay de dung mo hinh gia
# ma khong can torch that (xem tests/test_ai_live.py).
load_model_fn = load_model
predict_proba_fn = predict_proba

# Cache: (str(models_dir), symbol) -> (fingerprint, (model, sidecar)
# | None). Fingerprint gom mtime + kich thuoc 2 file — file doi
# thi nap lai, file giong thi dung lai gia tri da cache (ke ca
# None khi load loi, de khong thu lai moi chu ky).
_CACHE = {}
# (symbol, ly do) da canh bao 1 lan trong process nay.
_WARNED = set()


def clear_ai_cache():
    """Xoa cache mo hinh + danh sach da canh bao (chi dung cho test)."""
    _CACHE.clear()
    _WARNED.clear()


def resolve_ai_config(cfg=None):
    """Muc `ai:` trong config, gop voi mac dinh.

    Thieu muc `ai:` thi dung mac dinh het (models_dir mac dinh
    data/ai-models, seq_len 32, chan AI TAT, nguong 0.30, han
    90 ngay). max_age_days None = khong gioi han tuoi mo hinh.
    """
    ai_cfg = (cfg or {}).get("ai") or {}
    try:
        seq_len = int(ai_cfg.get("seq_len") or DEFAULT_SEQ_LEN)
    except (TypeError, ValueError):
        seq_len = DEFAULT_SEQ_LEN
    try:
        min_win_prob = float(ai_cfg.get("min_win_prob",
                                        DEFAULT_MIN_WIN_PROB))
    except (TypeError, ValueError):
        min_win_prob = DEFAULT_MIN_WIN_PROB
    max_age_days = ai_cfg.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    if max_age_days is not None:
        try:
            max_age_days = int(max_age_days)
        except (TypeError, ValueError):
            max_age_days = DEFAULT_MAX_AGE_DAYS
    return {"models_dir": resolve_models_dir(cfg),
            "seq_len": max(1, seq_len),
            "block_on_low_win_prob": bool(
                ai_cfg.get("block_on_low_win_prob", False)),
            "min_win_prob": min(1.0, max(0.0, min_win_prob)),
            "max_age_days": max_age_days}


def bars_needed(cfg, symbol):
    """So bar M15 toi thieu de du doan cho symbol (81 mac dinh).

    Tra None khi chua co file mo hinh (.pt + .json) — live lay 60
    bar nhu cu. Chi kiem tra file ton tai (re, khong cham torch).
    """
    ai_cfg = resolve_ai_config(cfg)
    pt_path, json_path = model_paths(symbol, ai_cfg["models_dir"])
    if pt_path.exists() and json_path.exists():
        return FEATURE_WINDOW + ai_cfg["seq_len"] - 1
    return None


def _warn_once(symbol, kind, message):
    """In 1 dong canh bao, toi da 1 lan / (symbol, ly do) / process."""
    key = (symbol, kind)
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"Canh bao AI ({symbol}): {message}")


def model_version_str(sidecar):
    """Chuoi phien ban mo hinh tu sidecar (de gan vao tin hieu/log)."""
    sidecar = sidecar or {}
    trained_at = sidecar.get("trained_at") or "?"
    feature_v = sidecar.get("feature_version")
    param_v = sidecar.get("param_feature_version")
    return (f"{trained_at} (feature v{feature_v}, "
            f"params v{param_v})")


def _parse_trained_at(value):
    """ISO datetime -> datetime (aware); khong parse duoc -> None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fingerprint(pt_path, json_path):
    """(mtime, size) 2 file mo hinh; thieu file -> None."""
    try:
        pt_stat = pt_path.stat()
        js_stat = json_path.stat()
    except OSError:
        return None
    return (pt_stat.st_mtime_ns, pt_stat.st_size,
            js_stat.st_mtime_ns, js_stat.st_size)


def _load_cached(cfg, symbol):
    """Tai (model, sidecar) cho symbol — cache theo fingerprint.

    Tra None khi: thieu file, sidecar hong, model het han
    (trained_at cu hon ai.max_age_days), torch chua cai, weights
    hong / khong khop. Moi truong hop chi canh bao 1 lan (xem
    _warn_once) roi tra None — KHONG BAO GIO raise.
    """
    ai_cfg = resolve_ai_config(cfg)
    models_dir = ai_cfg["models_dir"]
    pt_path, json_path = model_paths(symbol, models_dir)
    cache_key = (str(models_dir), symbol)
    fingerprint = _fingerprint(pt_path, json_path)
    if fingerprint is None:
        if cache_key not in _CACHE:
            _warn_once(symbol, "missing",
                       f"chua co mo hinh outcome ({pt_path.name}) — "
                       "chay tiep khong co AI (train bang "
                       f"`python -m diamondx10 ai-train --symbol "
                       f"{symbol} --days 90`).")
            _CACHE[cache_key] = (None, None)
        return None
    cached = _CACHE.get(cache_key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    try:
        sidecar = load_sidecar(json_path)
    except ModelLoadError as exc:
        _warn_once(symbol, "corrupt", f"{exc} — chay tiep khong co AI.")
        _CACHE[cache_key] = (fingerprint, None)
        return None
    max_age_days = ai_cfg["max_age_days"]
    if max_age_days is not None:
        trained_at = _parse_trained_at(sidecar.get("trained_at"))
        if trained_at is not None:
            age_days = (datetime.now(timezone.utc) - trained_at).days
            if age_days > max_age_days:
                _warn_once(
                    symbol, "stale",
                    f"mo hinh cu {age_days} ngay (qua han "
                    f"{max_age_days} ngay) — chay tiep khong co AI "
                    "(train lai bang ai-train).")
                _CACHE[cache_key] = (fingerprint, None)
                return None
    try:
        loaded = load_model_fn(pt_path, json_path)
    except TorchNotAvailable as exc:
        _warn_once(symbol, "no-torch", f"{exc} — chay tiep khong co AI.")
        _CACHE[cache_key] = (fingerprint, None)
        return None
    except ModelLoadError as exc:
        _warn_once(symbol, "corrupt", f"{exc} — chay tiep khong co AI.")
        _CACHE[cache_key] = (fingerprint, None)
        return None
    except Exception as exc:  # noqa: BLE001 — load loi kieu gi cung suy giam
        _warn_once(symbol, "load-error",
                   f"khong tai duoc mo hinh {pt_path} "
                   f"({type(exc).__name__}: {exc}) — chay tiep "
                   "khong co AI.")
        _CACHE[cache_key] = (fingerprint, None)
        return None
    _CACHE[cache_key] = (fingerprint, loaded)
    return loaded


def _build_sequence(bars, params, direction, seq_len):
    """1 chuoi (1, seq_len, 48) ket thuc o bar cuoi cung.

    Moi hang s = build_features(50 bar ket thuc o s, params,
    direction) + param_vector(params) — giong event_sequences()
    cua tune.py (hang chi dung bar <= s, khong lookahead). Can it
    nhat FEATURE_WINDOW + seq_len - 1 bar; thieu thi ValueError.
    """
    ordered = list(bars or [])
    needed = FEATURE_WINDOW + seq_len - 1
    if len(ordered) < needed:
        raise ValueError(
            f"can it nhat {needed} bar de du doan AI, chi co "
            f"{len(ordered)} bar")
    rows = []
    last = len(ordered)
    for s in range(last - seq_len, last):
        window = ordered[s - FEATURE_WINDOW + 1:s + 1]
        if len(window) < FEATURE_WINDOW:
            raise ValueError("khong du bar cho cua so feature AI")
        rows.append(list(build_features(window, params=params,
                                       direction=direction))
                    + param_vector(params))
    return [rows]


def predict_win_prob(cfg, symbol, bars, direction, params=None):
    """Du doan P(tp_first) cho 1 tin hieu BUY/SELL.

    Tra {"ai_win_prob", "ai_probs", "ai_model_version"} hoac None
    khi: huong khong phai BUY/SELL, khong du bar, khong co / het
    han / hong mo hinh, chua cai torch, hoac du doan loi. KHONG
    BAO GIO raise — loi chi canh bao 1 lan (moi ly do).
    """
    if direction not in ("BUY", "SELL"):
        return None
    ai_cfg = resolve_ai_config(cfg)
    loaded = _load_cached(cfg, symbol)
    if loaded is None:
        return None
    model, sidecar = loaded
    seq_len = int(sidecar.get("seq_len") or ai_cfg["seq_len"])
    try:
        sequence = _build_sequence(bars, params, direction, seq_len)
    except ValueError as exc:
        _warn_once(symbol, "not-enough-bars",
                   f"{exc} — chay tiep khong co AI.")
        return None
    try:
        from .train import apply_scaler
        sequence = apply_scaler(sequence, sidecar.get("mean"),
                                sidecar.get("std"))
        probs = predict_proba_fn(model, sequence)[0]
    except Exception as exc:  # noqa: BLE001 — du doan loi thi bo AI
        _warn_once(symbol, "predict-error",
                   f"khong du doan duoc ({type(exc).__name__}: {exc}) "
                   "— chay tiep khong co AI.")
        return None
    classes = list(sidecar.get("classes") or CLASSES)
    try:
        i_sl = classes.index("sl_first")
        i_to = classes.index("timeout")
        i_tp = classes.index("tp_first")
    except ValueError:
        i_sl, i_to, i_tp = 0, 1, 2
    try:
        ai_probs = [float(probs[i_sl]), float(probs[i_to]),
                    float(probs[i_tp])]
    except (TypeError, ValueError, IndexError):
        _warn_once(symbol, "predict-error",
                   "mo hinh tra xac suat khong hop le — chay tiep "
                   "khong co AI.")
        return None
    return {"ai_win_prob": ai_probs[2], "ai_probs": ai_probs,
            "ai_model_version": model_version_str(sidecar)}


def attach_ai_prediction(cfg, symbol, bars, sig):
    """Gan du doan AI vao dict tin hieu `sig` (sua tai cho).

    Chi chay khi tin hieu la BUY/SELL (HOLD khong co huong de
    du doan). Tra dict du doan hoac None. KHONG BAO GIO raise.
    """
    if not isinstance(sig, dict):
        return None
    if sig.get("action") not in ("BUY", "SELL"):
        return None
    try:
        params = sig.get("params")
        if not isinstance(params, dict):
            params = None
        prediction = predict_win_prob(cfg, symbol, bars,
                                      sig["action"], params)
    except Exception as exc:  # noqa: BLE001 — hook khong duoc crash live
        _warn_once(symbol, "predict-error",
                   f"khong gan duoc du doan AI ({exc}) — chay tiep "
                   "khong co AI.")
        return None
    if prediction is None:
        return None
    sig.update(prediction)
    return prediction


def should_block_ai(cfg, prediction):
    """True khi chan opt-in bat VA du doan AI duoi nguong.

    Mac dinh (block_on_low_win_prob false) luon False — AI chi la
    boi canh. prediction None thi False (khong co AI thi khong
    chan gi ca).
    """
    if not prediction:
        return False
    ai_cfg = resolve_ai_config(cfg)
    if not ai_cfg["block_on_low_win_prob"]:
        return False
    try:
        win_prob = float(prediction.get("ai_win_prob"))
    except (TypeError, ValueError):
        return False
    return win_prob < ai_cfg["min_win_prob"]


__all__ = ["CLASSES", "DEFAULT_MAX_AGE_DAYS", "DEFAULT_MIN_WIN_PROB",
           "DEFAULT_SEQ_LEN", "attach_ai_prediction", "bars_needed",
           "clear_ai_cache", "load_model_fn", "model_version_str",
           "predict_proba_fn", "predict_win_prob", "resolve_ai_config",
           "should_block_ai"]
