"""Ghi log ket qua tin hieu (outcome logging) cho vong hoc TA cua dx10.

Moi tin hieu BUY/SELL vuot qua moi gate trong live.process_symbol va
tro thanh TRADED (lenh demo da dat) hoac RECOMMENDED (lenh cho xac
nhan) thi duoc ghi 1 dong JSON vao decisions/signal-outcomes.jsonl,
TRUOC khi Telegram gui canh bao (log-first, cung ky luat nhu
decisions-log.csv). Ban ghi giu lai toan bo boi canh TA luc phat tin
hieu (RSI/SMA/ATR/regime/mau hinh/tham so da resolve/soft rule/PTCB)
de vong hoc sau nay doi chieu tin hieu voi ket qua that.

Chi doc GENERIC tu dict tin hieu (dung .get voi mac dinh, khong gia
dinh khoa ton tai) de module chay duoc ca khi duong signal co hay
khong co boi canh chi bao day du. Khong bao gio ghi token / password /
login / chat id vao ban ghi. Duong ghi log KHONG BAO GIO raise: loi
ghi chi in 1 dong canh bao roi nuot — vong live khong duoc crash vi
loi ghi log.
"""
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STORE = (Path(__file__).resolve().parents[2] / "decisions"
                 / "signal-outcomes.jsonl")

# Khoa nhay cam — neu lot vao resolved_params thi loai truoc khi ghi.
_SENSITIVE_SUBSTRINGS = ("token", "password", "passwd", "secret",
                         "chat_id", "login", "api_key", "apikey",
                         "private", "credential")

# Cac khoa co the mang boi canh chi bao / soft rule trong dict tin hieu.
# generate_signals() hien tai tra regime (dict), patterns (list dict),
# pattern_score, params, levels{atr, size_scale}; RSI/SMA/ADX nam
# trong Strategy._soft_context (noi bo) nen o day chi doc khi tin hieu
# mang theo (duong signal tuong lai / fake trong test).
_CONTEXT_KEYS = ("context", "ta_context", "indicators", "ta")

# Cac khoa co the mang soft rule trong dict tin hieu / ket qua.
_SOFT_RULE_KEYS = ("soft_rules", "soft_rules_applied", "soft_rules_fired",
                   "applied_soft_rules", "soft_rule")


def _to_float(value):
    """float(value) neu duoc, khong thi None — khong bao gio raise."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _to_str(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _pick(*sources, key):
    """Lay key tu source dict dau tien co no (doc generic, co mac dinh)."""
    for src in sources:
        if isinstance(src, dict) and key in src and src[key] is not None:
            return src[key]
    return None


def _context_dict(sig):
    """Gop cac dict boi canh chi bao co trong sig (neu co)."""
    merged = {}
    for key in _CONTEXT_KEYS:
        ctx = (sig or {}).get(key)
        if isinstance(ctx, dict):
            merged.update(ctx)
    return merged


def _clean_params(params):
    """Ban sao dict tham so, chi giu gia tri vo hai + loai khoa nhay cam."""
    if not isinstance(params, dict):
        return {}
    out = {}
    for key, value in params.items():
        if not isinstance(key, str):
            continue
        lowered = key.lower()
        if any(bad in lowered for bad in _SENSITIVE_SUBSTRINGS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, dict)):
            try:
                out[key] = json.loads(json.dumps(value))
            except (TypeError, ValueError):
                continue
    return out


def _params_hash(resolved_params):
    """8 ky tu dau sha256 cua JSON chuan cua resolved_params."""
    if not resolved_params:
        return "none"
    canonical = json.dumps(resolved_params, sort_keys=True,
                           ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def _pattern_names(patterns):
    """List ten mau hinh tu list dict {name, ...} hoac list str."""
    names = []
    if not isinstance(patterns, (list, tuple)):
        return names
    for item in patterns:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def _parse_fa_note(fa_note):
    """Parse chuoi fa_note cua live ("FA: buy 0.8" / "FA: chua co" /
    "FA: cu") thanh {direction, confidence} hoac None."""
    if not isinstance(fa_note, str):
        return None
    text = fa_note.strip()
    match = re.match(r"^FA:\s+(buy|sell|neutral)\s+([0-9]*\.?[0-9]+)\s*$",
                     text, re.IGNORECASE)
    if match:
        return {"direction": match.group(1).lower(),
                "confidence": _to_float(match.group(2))}
    return None


def _fa_from(result, sig):
    """PTCB cua tin hieu: dict fa san co, hoac parse tu fa_note."""
    for src in (result, sig):
        if not isinstance(src, dict):
            continue
        fa = src.get("fa")
        if isinstance(fa, dict):
            direction = _to_str(fa.get("direction"))
            if direction:
                return {"direction": direction.lower(),
                        "confidence": _to_float(fa.get("confidence"))}
        verdict = src.get("verdict") or src.get("fundamental_verdict")
        if isinstance(verdict, dict):
            direction = _to_str(verdict.get("direction"))
            if direction:
                return {"direction": direction.lower(),
                        "confidence": _to_float(verdict.get("confidence"))}
    if isinstance(result, dict):
        return _parse_fa_note(result.get("fa_note"))
    return None


def _normalise_soft_rules(raw):
    """Chuan hoa soft rule ve list {name, fired, effect}.

    Chap nhan: list dict {name, fired, effect} (fired mac dinh True khi
    co trong danh sach "applied/fired"), list str (ten rule, fired True,
    effect None), dict {name: effect} / dict don {name, effect}.
    Khong hieu thi bo qua muc do, khong bao gio raise.
    """
    out = []
    if isinstance(raw, dict):
        if raw.get("name"):
            raw = [raw]
        else:
            raw = [{"name": name, "fired": True, "effect": effect}
                   for name, effect in raw.items()]
    if not isinstance(raw, (list, tuple)):
        return out
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({"name": item, "fired": True, "effect": None})
        elif isinstance(item, dict) and item.get("name"):
            effect = item.get("effect")
            if isinstance(effect, dict):
                effect = effect.get("type") or effect.get("factor")
                effect = _to_str(effect)
            elif effect is not None:
                effect = _to_str(effect)
            fired = item.get("fired")
            if fired is None:
                fired = item.get("applied", True)
            out.append({"name": str(item["name"]),
                        "fired": bool(fired),
                        "effect": effect})
    return out


def _soft_rules_from_reason(reason):
    """Fallback: ten soft rule scale ghi trong reason cua tin hieu.

    Strategy._apply_soft_rules ghi "[soft rule <ten>: scale x0.50]"
    vao reason khi co rule scale tac dong — ten do la bang chung that,
    khong phai suy doan. Chi dung khi tin hieu khong mang soft rule
    co cau truc.
    """
    if not isinstance(reason, str):
        return []
    match = re.search(r"soft rule ([^:\]]+):\s*scale", reason)
    if not match:
        return []
    return [{"name": name.strip(), "fired": True, "effect": "scale"}
            for name in match.group(1).split(",") if name.strip()]


def _soft_rules_from(result, sig):
    """Soft rule cua tin hieu: doc generic tu result/sig, neu khong co
    thi [] — khong bao gio tu che ten rule."""
    for src in (sig, result):
        if not isinstance(src, dict):
            continue
        for key in _SOFT_RULE_KEYS:
            rules = _normalise_soft_rules(src.get(key))
            if rules:
                return rules
    rules = _soft_rules_from_reason(
        (sig or {}).get("reason") if isinstance(sig, dict) else None)
    if rules:
        return rules
    return []


def _resolved_params(cfg, desk, symbol, sig):
    """Tham so TA da resolve cho (desk, symbol).

    Uu tien: sig["params"] (generate_signals da gan dict strat.params);
    neu khong co thi thu resolve_strategy_params(cfg, ...) — loi gi
    (config thieu/symbol la) thi tra {} chu khong raise.
    """
    params = (sig or {}).get("params") if isinstance(sig, dict) else None
    if isinstance(params, dict) and params:
        return _clean_params(params)
    if cfg is None:
        return {}
    try:
        from .strategies.registry import resolve_strategy_params
        resolved = resolve_strategy_params(cfg, desk, symbol)
    except Exception:  # noqa: BLE001 — khong co params van ghi log duoc
        return {}
    return _clean_params(resolved)


def _htf_from(sig, action):
    """Boi canh HTF cho ban ghi outcome: doc tu sig["htf_trend"].

    Tra {"timeframe", "direction", "adx", "trusted", "agreement"}:
    agreement "agree" khi BUY+up / SELL+down, "against" khi
    BUY+down / SELL+up, "neutral" khi trend trung lap, "not_applied"
    khi khong co trend / direction "unknown" / trusted False / action
    khong phai BUY-SELL. Khong co trend -> moi gia tri None (tru
    agreement) + "not_applied". Khong bao gio raise.
    """
    missing = {"timeframe": None, "direction": None, "adx": None,
               "trusted": None, "agreement": "not_applied"}
    try:
        trend = (sig or {}).get("htf_trend")
        if not isinstance(trend, dict):
            return dict(missing)
        direction = _to_str(trend.get("direction"))
        trusted_raw = trend.get("trusted")
        trusted = None if trusted_raw is None else bool(trusted_raw)
        if direction is None or direction == "unknown" or not trusted:
            return {"timeframe": _to_str(trend.get("timeframe")),
                    "direction": direction, "adx": _to_float(trend.get("adx")),
                    "trusted": trusted, "agreement": "not_applied"}
        if direction == "neutral":
            agreement = "neutral"
        elif (action == "BUY" and direction == "up") or \
                (action == "SELL" and direction == "down"):
            agreement = "agree"
        elif (action == "BUY" and direction == "down") or \
                (action == "SELL" and direction == "up"):
            agreement = "against"
        else:
            agreement = "not_applied"
        return {"timeframe": _to_str(trend.get("timeframe")),
                "direction": direction, "adx": _to_float(trend.get("adx")),
                "trusted": trusted, "agreement": agreement}
    except Exception:  # noqa: BLE001 — boi canh HTF khong duoc crash log
        return dict(missing)


def build_record(result, sig, cfg, desk, symbol):
    """Xay 1 ban ghi outcome tu dict ket qua live + dict tin hieu + cfg.

    result: dict process_symbol tra ve (status TRADED/RECOMMENDED,
    price/sl/tp/volume/risk_usd/manager/time/size_scale/pending_id).
    sig: dict generate_signals tra ve (action/reason/levels/regime/
    patterns/pattern_score/params/strategy). cfg: config day du (co
    the None). Khong bao gio ghi token/password/login/chat id.
    """
    result = result if isinstance(result, dict) else {}
    sig = sig if isinstance(sig, dict) else {}
    levels = sig.get("levels") if isinstance(sig.get("levels"), dict) else {}
    ctx = _context_dict(sig)
    regime_raw = _pick(sig, ctx, key="regime")
    regime_name, regime_adx = None, None
    if isinstance(regime_raw, dict):
        regime_name = _to_str(regime_raw.get("regime"))
        regime_adx = _to_float(regime_raw.get("adx"))
    elif isinstance(regime_raw, str):
        regime_name = regime_raw
    sma_fast = _to_float(_pick(sig, ctx, key="sma_fast"))
    sma_slow = _to_float(_pick(sig, ctx, key="sma_slow"))
    if sma_fast is not None and sma_slow is not None:
        if sma_fast > sma_slow:
            sma_relation = "fast>slow"
        elif sma_fast < sma_slow:
            sma_relation = "fast<slow"
        else:
            sma_relation = None
    else:
        sma_relation = None
    resolved = _resolved_params(cfg, desk, symbol, sig)
    atr = _to_float(levels.get("atr"))
    if atr is None:
        atr = _to_float(_pick(sig, ctx, key="atr"))
    context = {
        "rsi": _to_float(_pick(sig, ctx, key="rsi")),
        "sma_fast": sma_fast,
        "sma_slow": sma_slow,
        "sma_relation": sma_relation,
        "atr": atr,
        "atr_sl_mult": _to_float(resolved.get("atr_sl_mult")),
        "regime": regime_name,
        "adx": regime_adx if regime_adx is not None else _to_float(
            _pick(sig, ctx, key="adx")),
        "patterns": _pattern_names(sig.get("patterns")),
        "pattern_score": _to_float(sig.get("pattern_score")),
        "strategy_name": _to_str(_pick(
            sig, key="strategy") or _pick(sig, key="strategy_name")
            or "default"),
        "resolved_params": resolved,
        "soft_rules": _soft_rules_from(result, sig),
        "fa": _fa_from(result, sig),
        "htf": _htf_from(sig, result.get("action") or sig.get("action")),
    }
    # Du doan AI outcome (muc 65): chi ghi khi tin hieu / ket qua
    # mang theo — ban ghi khong co AI giu nguyen nhu cu (khong them
    # khoa None). ai_probs phai la list 3 so moi ghi.
    ai_win_prob = _to_float(_pick(result, sig, key="ai_win_prob"))
    if ai_win_prob is not None:
        context["ai_win_prob"] = ai_win_prob
    ai_probs = _pick(result, sig, key="ai_probs")
    if isinstance(ai_probs, (list, tuple)) and len(ai_probs) == 3:
        ai_probs = [_to_float(v) for v in ai_probs]
        if all(v is not None for v in ai_probs):
            context["ai_probs"] = ai_probs
    ai_model_version = _to_str(_pick(result, sig,
                                     key="ai_model_version"))
    if ai_model_version:
        context["ai_model_version"] = ai_model_version
    return {
        "id": secrets.token_hex(4),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "desk": desk,
        "symbol": symbol,
        "action": result.get("action") or sig.get("action"),
        "status": result.get("status"),
        "entry": _to_float(result.get("price", levels.get("entry"))),
        "sl": _to_float(result.get("sl", levels.get("sl"))),
        "tp": _to_float(result.get("tp", levels.get("tp"))),
        "volume": _to_float(result.get("volume")),
        "risk_usd": _to_float(result.get("risk_usd")),
        "manager": result.get("manager"),
        "time": result.get("time"),
        "size_scale": _to_float(result.get("size_scale",
                                           levels.get("size_scale"))) or 1.0,
        "pending_id": result.get("pending_id"),
        "context": context,
        "params_hash": _params_hash(resolved),
    }


def load(path=None):
    """Doc tat ca ban ghi tu file JSONL; thieu file / file hong ->
    []; bo qua tung dong hong, khong bao gio raise."""
    store_path = Path(path) if path is not None else DEFAULT_STORE
    try:
        with open(store_path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, ValueError):
        return []
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def log_signal(store_path, record):
    """Ghi them 1 ban ghi (1 dong JSON) vao store.

    Tra True neu ghi duoc, False neu loi (in 1 dong canh bao, KHONG
    raise). store_path None thi dung duong dan mac dinh.
    """
    path = Path(store_path) if store_path is not None else DEFAULT_STORE
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 — ghi log khong duoc crash
        print(f"Canh bao outcomes: khong ghi duoc {path} ({exc})")
        return False


class OutcomeStore:
    """Store ban ghi outcome (JSONL, 1 ban ghi / dong)."""

    def __init__(self, store_path=None):
        self.path = (Path(store_path) if store_path is not None
                     else DEFAULT_STORE)

    def append(self, record):
        """Ghi them 1 ban ghi; loi thi canh bao + tra False, KHONG raise."""
        return log_signal(self.path, record)

    def load(self):
        """Doc tat ca ban ghi; thieu/hong file -> [], khong raise."""
        return load(self.path)


__all__ = ["DEFAULT_STORE", "OutcomeStore", "build_record", "load",
           "log_signal"]
