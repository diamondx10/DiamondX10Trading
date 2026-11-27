"""Tham so TA lam input cho mo hinh hoc ket qua lenh (ai/params.py).

Mo hinh outcome (ai/model.py + ai/train.py) hoc anh xa
(context thi truong + tham so TA) -> ket qua lenh, nen tham so
phai la FEATURE, khong phai sieu tham so ngoai mo hinh. Module
nay dinh nghia 2 thu (chi stdlib, khong can torch):

1. PARAM_FEATURE_NAMES — 13 tham so TA dang vector chuan hoa
   [0, 1] (chia cho max cua PARAM_RANGES trong
   strategies/registry.py — gioi han ve sinh, khong phai khuyen
   nghi gia tri tot). Thu tu co dinh, phien ban
   PARAM_FEATURE_VERSION = 1. Mo hinh an 35 cot context
   (features.py) + 13 cot nay = 48 cot.
2. candidate_param_sets() — tap ung vien de lay mau
   counterfactual + de tune: tham so hien tai + bien doi MOT
   tham so mot luc (coordinate variations) quanh gia tri hien
   tai. Bien doi mot luc chu khong phai luoi day du: mo hinh
   hoc duoc tac dong rieng cua tung tham so; tuong tac cap 2
   khong duoc lay mau o v1 (ghi ro trong docs/ai-ta-model.md).

Tham so KHONG duoc tune o day (hard rules — xem
strategies/soft_rules.py HARD_RULE_KEYS): drawdown, kill switch,
demo-only, margin, daily limit, no-trade windows, FA gate,
bang risk, ... — candidate nao cham khoa cung thi
validate_strategy_params / check_hard_rule_keys raise va bi loai.
"""
from ..strategies.registry import (
    PARAM_RANGES,
    _check_param_ordering,
    _strategy_class,
    resolve_soft_rules,
    resolve_strategy_params,
    validate_strategy_params,
)

PARAM_FEATURE_VERSION = 1

# Thu tu co dinh — doi thu tu la doi y nghia cot, phai tang version.
PARAM_FEATURE_NAMES = (
    "sma_fast", "sma_slow",
    "rsi_buy_low", "rsi_buy_high", "rsi_sell_low", "rsi_sell_high",
    "rsi_extreme_high", "rsi_extreme_low",
    "atr_sl_mult", "tp_mult", "trail_mult",
    "adx_min", "min_atr_pct",
)

# Mau so chuan hoa = max cua PARAM_RANGES (moi gia tri hop le
# deu ve [0, 1]). min_atr_pct co max 0.05; gia tri am khong hop le
# (validate se chan truoc).
_PARAM_SCALES = {
    "sma_fast": 50.0, "sma_slow": 200.0,
    "rsi_buy_low": 100.0, "rsi_buy_high": 100.0,
    "rsi_sell_low": 100.0, "rsi_sell_high": 100.0,
    "rsi_extreme_high": 100.0, "rsi_extreme_low": 100.0,
    "atr_sl_mult": 5.0, "tp_mult": 5.0, "trail_mult": 5.0,
    "adx_min": 100.0, "min_atr_pct": 0.05,
}


def param_feature_names():
    """Ban sao danh sach ten cot tham so (thu tu co dinh)."""
    return list(PARAM_FEATURE_NAMES)


def param_vector(params):
    """Vector tham so chuan hoa [0, 1] (list[float], dai 13).

    params: dict tham so TA da resolve (resolve_strategy_params).
    Thieu khoa -> dung gia tri mac dinh cua chien luoc (xem
    strategies/base.py SHARED_DEFAULTS). Gia tri vuot khoang thi
    cat ve [0, 1] (khong raise — validate nam o cho khac).
    """
    defaults = {"sma_fast": 5, "sma_slow": 20, "rsi_buy_low": 50,
                "rsi_buy_high": 70, "rsi_sell_low": 30,
                "rsi_sell_high": 50, "rsi_extreme_high": 80,
                "rsi_extreme_low": 20, "atr_sl_mult": 1.5,
                "tp_mult": 2.0, "trail_mult": 1.5, "adx_min": 0,
                "min_atr_pct": 0.0}
    merged = dict(defaults)
    merged.update(params or {})
    out = []
    for name in PARAM_FEATURE_NAMES:
        try:
            value = float(merged.get(name, defaults[name]))
        except (TypeError, ValueError):
            value = float(defaults[name])
        scale = _PARAM_SCALES[name]
        scaled = value / scale if scale else 0.0
        out.append(min(1.0, max(0.0, scaled)))
    return out


def param_key(overrides):
    """Khoa hashable cho 1 tap ghi de tham so (de nhom mau khi
    xay chuoi): tuple sap xep (ten, gia tri); {} -> ("current",)."""
    if not overrides:
        return ("current",)
    return tuple(sorted((str(k), _scalar(v))
                        for k, v in dict(overrides).items()))


def _scalar(value):
    """Gia tri so ve dang hashable on dinh (int giu int)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return int(number) if number == int(number) else number


def strategy_with_params(cfg, desk, symbol, overrides,
                         strategy_name="default"):
    """Chien luoc quy tac voi tham so ung vien.

    Giong build_strategy_for_symbol (resolve dung thu tu uu tien
    mac dinh < chung < desk < symbol + gan soft rule theo scope),
    nhung ap them `overrides` len tren cung truoc khi khoi tao.
    Raise ValueError khi overrides vi pham khoang / thu tu
    (vd rsi_buy_low vuot rsi_buy_high) hoac cham khoa cung.
    Tra (strategy, merged_params)."""
    base = resolve_strategy_params(cfg, desk, symbol, strategy_name)
    merged = dict(base)
    merged.update(overrides or {})
    validate_strategy_params(merged, strategy_name)
    _check_param_ordering(merged)
    soft = resolve_soft_rules(cfg, desk, symbol)
    cls = _strategy_class(strategy_name, desk)
    return cls(params={}, desk_params=merged, soft_rules=soft), merged


def current_params(cfg, desk, symbol, strategy_name="default"):
    """Tham so TA hien tai da resolve cho (desk, symbol)."""
    return resolve_strategy_params(cfg, desk, symbol, strategy_name)


# Bien doi mot luc quanh gia tri hien tai: (tham so, cac delta).
# Gia tri ung vien = current + delta, cat ve khoang PARAM_RANGES;
# trung voi current hoac vi pham thu tu thi bo qua (ghi vao stats).
_COORDINATE_DELTAS = (
    ("sma_fast", (-2, 2)),
    ("sma_slow", (-5, 5)),
    ("rsi_buy_low", (-5, 5)),
    ("rsi_buy_high", (-5, 5)),
    ("rsi_sell_low", (-5, 5)),
    ("rsi_sell_high", (-5, 5)),
    ("atr_sl_mult", (-0.5, 0.5)),
    ("tp_mult", (-0.5, 0.5)),
    ("adx_min", None),  # xu ly rieng: cac moc tuyet doi
)
_ADX_MIN_CANDIDATES = (0, 20, 25, 30)


def candidate_param_sets(cfg, desk, symbol, strategy_name="default"):
    """Tap ung vien tham so cho 1 symbol.

    Tra list dict {name, overrides}: phan tu dau luon la
    {"name": "current", "overrides": {}} (tham so dang chay),
    sau do la cac bien doi mot tham so mot luc. Moi ung vien da
    qua validate (khoang + thu tu); ung vien hong bi loai lang le
    nhung dem vao stats["skipped_invalid"]. Tra (candidates, stats)
    voi stats = {n_generated, skipped_invalid, skipped_duplicate}.
    """
    base = resolve_strategy_params(cfg, desk, symbol, strategy_name)
    candidates = [{"name": "current", "overrides": {}}]
    stats = {"n_generated": 0, "skipped_invalid": 0,
             "skipped_duplicate": 0}
    seen = {param_key({})}

    def _try_add(name, overrides):
        stats["n_generated"] += 1
        key = param_key(overrides)
        if key in seen:
            stats["skipped_duplicate"] += 1
            return
        merged = dict(base)
        merged.update(overrides)
        try:
            validate_strategy_params(merged, strategy_name)
            _check_param_ordering(merged)
        except ValueError:
            stats["skipped_invalid"] += 1
            return
        seen.add(key)
        candidates.append({"name": name, "overrides": dict(overrides)})

    for param, deltas in _COORDINATE_DELTAS:
        if deltas is None:
            current = base.get(param)
            for value in _ADX_MIN_CANDIDATES:
                if value == current:
                    continue
                _try_add(f"{param}={value}", {param: value})
            continue
        current = base.get(param)
        if current is None:
            continue
        low, high = PARAM_RANGES.get(param, (None, None))
        for delta in deltas:
            try:
                value = float(current) + float(delta)
            except (TypeError, ValueError):
                continue
            if isinstance(current, int) and float(delta) == int(delta):
                value = int(value)
            if low is not None:
                value = max(low, value)
            if high is not None:
                value = min(high, value)
            value = round(value, 4) if isinstance(value, float) else value
            _try_add(f"{param}={value}", {param: value})
    return candidates, stats


__all__ = ["PARAM_FEATURE_VERSION", "PARAM_FEATURE_NAMES",
           "param_feature_names", "param_vector", "param_key",
           "strategy_with_params", "current_params",
           "candidate_param_sets"]
