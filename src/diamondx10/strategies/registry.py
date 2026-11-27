"""Registry chien luoc + tham so rieng theo symbol (Phase B).

Registry la noi duy nhat dang ky chien luoc theo TEN:
- "default": quy tac chung da chot (SMA5/SMA20 + loc RSI + SL/TP theo
  ATR + trailing + thoat dao chieu), theo tung desk nhu build_strategies
  hien tai (crypto ATR 2,0x). Dung cho duong live demo.
- "donchian": breakout Donchian 20 — CHI DE SO SANH TRONG BACKTEST,
  chua dung live (xem strategies/breakout.py).

Tham so rieng theo symbol (config `strategy.per_symbol`):
chi la TINH CHINH con so (vd he so ATR, nguong RSI), KHONG thay quy
tac (khong doi loai tin hieu, khong them Kelly/chot loi tung phan).
Thu tu uu tien khi resolve:
  mac dinh da chot < tham so chung < ghi de cua lop theo desk
  (vd crypto 2,0x) < ghi de rieng desk trong config
  < ghi de rieng symbol trong config (`strategy.per_symbol`).
Gia tri mac dinh da chot KHONG doi o day — xem strategies/base.py.
"""
from .base import SHARED_DEFAULTS, Strategy
from .breakout import DonchianBreakout
from .crypto import CryptoMomentum
from .forex import ForexTrend
from .us_securities import USSecTrend
from .xauusd import XauusdTrend

# Lop chien luoc mac dinh ("default") theo tung desk.
DESK_STRATEGY_CLASSES = {
    "forex": ForexTrend,
    "us_securities": USSecTrend,
    "xauusd": XauusdTrend,
    "crypto": CryptoMomentum,
}

STRATEGY_REGISTRY = {
    "default": {
        "display_name": "Quy tac chung da chot (SMA + RSI + ATR)",
        "desk_classes": dict(DESK_STRATEGY_CLASSES),
        "desks": sorted(DESK_STRATEGY_CLASSES),
        "description": ("SMA5/SMA20 + loc RSI(14) + SL/TP theo ATR + "
                        "trailing + thoat dao chieu; theo tung desk "
                        "(crypto ATR 2,0x). Dung cho duong live demo."),
        "backtest_only": False,
    },
    "donchian": {
        "display_name": "DonchianBreakout 20",
        "class": DonchianBreakout,
        "desks": sorted(DESK_STRATEGY_CLASSES),
        "description": ("Pha dinh/day Donchian 20 nen truoc -> BUY/SELL; "
                        "CHI DE SO SANH TRONG BACKTEST, chua dung live."),
        "backtest_only": True,
    },
}

# Tham so biet duoc: mac dinh chung + rieng Donchian. Tham so la trong
# `per_symbol` / `desks` / muc chung ma khong co trong danh sach nay
# thi bi tu choi (tranh go sai ten tham so roi tuong da ghi de).
KNOWN_PARAMS = set(SHARED_DEFAULTS) | {"donchian_period", "min_atr_pct"}

# Khoang hop ly cho tung tham so (so). Vuot khoang -> ValueError.
# Day la gioi han ve sinh (tranh so vo nghia), khong phai khuyen nghi
# gia tri tot — gia tri tot chi biet sau walk-forward tren du lieu that.
PARAM_RANGES = {
    "sma_fast": (2, 50),
    "sma_slow": (5, 200),
    "rsi_period": (2, 50),
    "rsi_buy_low": (0, 100),
    "rsi_buy_high": (0, 100),
    "rsi_sell_low": (0, 100),
    "rsi_sell_high": (0, 100),
    "rsi_extreme_high": (50, 100),
    "rsi_extreme_low": (0, 50),
    "atr_period": (2, 50),
    "atr_sl_mult": (0.5, 5.0),
    "tp_mult": (0.5, 5.0),
    "trail_mult": (0.5, 5.0),
    "donchian_period": (5, 100),
    "min_atr_pct": (0.0, 0.05),
}

# Tham so phai la so nguyen (khong le).
_INT_PARAMS = {"sma_fast", "sma_slow", "rsi_period", "atr_period",
               "donchian_period"}


def list_strategies():
    """Metadata cua moi chien luoc trong registry (khong kem lop).

    Tra ve list dict: name, display_name, desks, description,
    backtest_only — sap theo ten (default truoc donchian)."""
    out = []
    for name in sorted(STRATEGY_REGISTRY):
        meta = STRATEGY_REGISTRY[name]
        out.append({
            "name": name,
            "display_name": meta["display_name"],
            "desks": list(meta["desks"]),
            "description": meta["description"],
            "backtest_only": meta["backtest_only"],
        })
    return out


def _strategy_class(name, desk=None):
    """Lop chien luoc cho (ten, desk). Raise ValueError neu ten/desk la."""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"Chien luoc khong biet: {name!r} "
            f"(co: {', '.join(sorted(STRATEGY_REGISTRY))})")
    meta = STRATEGY_REGISTRY[name]
    if "desk_classes" in meta:
        if desk is None:
            raise ValueError(
                f"Chien luoc {name!r} can chi ro desk "
                f"(co: {', '.join(sorted(meta['desk_classes']))})")
        if desk not in meta["desk_classes"]:
            raise ValueError(
                f"Desk khong biet: {desk!r} cho chien luoc {name!r} "
                f"(co: {', '.join(sorted(meta['desk_classes']))})")
        return meta["desk_classes"][desk]
    if desk is not None and desk not in meta["desks"]:
        raise ValueError(
            f"Desk khong biet: {desk!r} cho chien luoc {name!r} "
            f"(co: {', '.join(sorted(meta['desks']))})")
    return meta["class"]


def get_strategy(name, desk=None, params=None, desk_params=None,
                 symbol_params=None):
    """Khoi tao 1 instance chien luoc tu registry.

    params: tham so chung; desk_params: ghi de rieng desk;
    symbol_params: ghi de rieng symbol (thang cao nhat, ap sau cung).
    Thu tu gop trong Strategy.__init__: mac dinh < params <
    DESK_OVERRIDES cua lop < desk_params — nen symbol_params duoc
    gop chung vao desk_params de thang ca DESK_OVERRIDES.
    """
    cls = _strategy_class(name, desk)
    merged_desk = dict(desk_params or {})
    merged_desk.update(symbol_params or {})
    return cls(params=params, desk_params=merged_desk)


def validate_strategy_params(params, strategy_name="default"):
    """Kiem tra 1 dict tham so (rieng le): ten biet, gia tri so,
    trong khoang hop ly, tham so nguyen khong le. Raise ValueError
    voi message ro rang khi gap gia tri la. Khong kiem tra thu tu
    giua cac tham so o day (chi kiem khi da gop du — xem
    _check_param_ordering)."""
    if params is None:
        return
    if not isinstance(params, dict):
        raise ValueError(
            f"Tham so chien luoc phai la dict, nhan {type(params).__name__}")
    for key, value in params.items():
        if key not in KNOWN_PARAMS:
            raise ValueError(
                f"Tham so chien luoc khong biet: {key!r} "
                f"(co: {', '.join(sorted(KNOWN_PARAMS))})")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"Tham so {key!r} phai la so, nhan {value!r}")
        lo, hi = PARAM_RANGES[key]
        if not lo <= value <= hi:
            raise ValueError(
                f"Tham so {key!r} = {value} vuot khoang hop ly "
                f"[{lo}, {hi}]")
        if key in _INT_PARAMS and float(value) != int(value):
            raise ValueError(
                f"Tham so {key!r} phai la so nguyen, nhan {value!r}")


def _check_param_ordering(params):
    """Kiem tra thu tu giua cac tham so SAU KHI da gop du
    (vd nguong duoi phai nho hon nguong tren)."""
    checks = [
        ("sma_fast", "sma_slow", "sma_fast phai nho hon sma_slow"),
        ("rsi_buy_low", "rsi_buy_high",
         "rsi_buy_low phai nho hon rsi_buy_high"),
        ("rsi_sell_low", "rsi_sell_high",
         "rsi_sell_low phai nho hon rsi_sell_high"),
        ("rsi_extreme_low", "rsi_extreme_high",
         "rsi_extreme_low phai nho hon rsi_extreme_high"),
    ]
    for low_key, high_key, msg in checks:
        if params[low_key] >= params[high_key]:
            raise ValueError(
                f"{msg}: {low_key}={params[low_key]}, "
                f"{high_key}={params[high_key]}")


def _strategy_section(cfg):
    """Lay muc "strategy" tu config day du; neu cfg chinh la muc
    strategy (co khoa tham so) thi dung thang cfg."""
    cfg = cfg or {}
    section = cfg.get("strategy")
    if isinstance(section, dict):
        return section
    if any(k in KNOWN_PARAMS or k in ("desks", "per_symbol")
           for k in cfg):
        return cfg
    return {}


def _all_config_symbols(cfg):
    """Toan bo symbol trong config data.symbols (moi desk gop lai)."""
    symbols_cfg = (cfg or {}).get("data") or {}
    symbols = symbols_cfg.get("symbols") or {}
    out = []
    if isinstance(symbols, dict):
        for desk_symbols in symbols.values():
            out.extend(desk_symbols or [])
    return out


def resolve_strategy_params(cfg, desk, symbol, strategy_name="default"):
    """Gop tham so day du cho 1 (desk, symbol, chien luoc).

    cfg: config day du (co "strategy" + "data.symbols") hoac muc
    "strategy" rieng. Thu tu: mac dinh da chot < tham so chung <
    DESK_OVERRIDES cua lop < ghi de desk < ghi de symbol.
    Validate: symbol phai co trong config data.symbols (neu config
    co khai bao symbols), ten tham so biet, gia tri so trong khoang,
    thu tu nguong hop ly. Raise ValueError neu vi pham.
    Tra ve dict tham so day du (ban sao — sua khong anh huong config).
    """
    if strategy_name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"Chien luoc khong biet: {strategy_name!r} "
            f"(co: {', '.join(sorted(STRATEGY_REGISTRY))})")
    cls = _strategy_class(strategy_name, desk)
    known_symbols = _all_config_symbols(cfg)
    if symbol is not None and known_symbols and symbol not in known_symbols:
        raise ValueError(
            f"Symbol {symbol!r} khong co trong config data.symbols "
            f"(co: {', '.join(known_symbols)})")
    section = _strategy_section(cfg)
    shared = {k: v for k, v in section.items()
              if k not in ("desks", "per_symbol")}
    per_desk = section.get("desks") or {}
    if not isinstance(per_desk, dict):
        raise ValueError("Muc strategy.desks phai la dict")
    desk_params = per_desk.get(desk) or {}
    per_symbol = section.get("per_symbol") or {}
    if not isinstance(per_symbol, dict):
        raise ValueError("Muc strategy.per_symbol phai la dict")
    symbol_params = per_symbol.get(symbol) or {} if symbol is not None else {}
    for label, part in (("chung", shared), (f"desk {desk}", desk_params),
                        (f"symbol {symbol}", symbol_params)):
        if not isinstance(part, dict):
            raise ValueError(
                f"Tham so {label} phai la dict, nhan {type(part).__name__}")
        validate_strategy_params(part, strategy_name)
    merged = dict(SHARED_DEFAULTS)
    merged.update(shared)
    merged.update(cls.DESK_OVERRIDES or {})
    merged.update(desk_params)
    merged.update(symbol_params)
    _check_param_ordering(merged)
    return merged


def build_strategy_for_symbol(cfg, desk, symbol, strategy_name="default"):
    """Khoi tao chien luoc cho 1 symbol cu the: tham so da resolve
    (mac dinh < chung < desk < symbol) roi truyen thang vao lop.
    Day la ham backtest / signals dung de moi symbol chay dung
    tham so cua no."""
    params = resolve_strategy_params(cfg, desk, symbol, strategy_name)
    cls = _strategy_class(strategy_name, desk)
    # Truyen qua desk_params (muc uu tien cao nhat trong
    # Strategy.__init__): neu truyen qua params thi DESK_OVERRIDES
    # cua lop (vd crypto 2,0x) se ghi de len gia tri symbol da
    # resolve (vd ETHUSD 1,0) — sai thu tu uu tien.
    return cls(params={}, desk_params=params)


__all__ = [
    "DESK_STRATEGY_CLASSES",
    "STRATEGY_REGISTRY",
    "KNOWN_PARAMS",
    "PARAM_RANGES",
    "list_strategies",
    "get_strategy",
    "validate_strategy_params",
    "resolve_strategy_params",
    "build_strategy_for_symbol",
    "Strategy",
]
