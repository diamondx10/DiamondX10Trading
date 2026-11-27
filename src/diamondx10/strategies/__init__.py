"""Dang ky chien luoc theo desk. Yuling nghien cuu ly thuyet,
LJ/Kel cai dat thanh code o day.

Registry that o strategies/registry.py (STRATEGY_REGISTRY):
"default" = quy tac chung da chot theo tung desk, "donchian" =
breakout Donchian chi de so sanh trong backtest. File nay giu
nguyen API cu (STRATEGIES, build_strategies) de test cu khong vo,
dong thoi re-export cac ham moi cua registry.
"""
from .base import Strategy
from .registry import (
    DESK_STRATEGY_CLASSES,
    STRATEGY_REGISTRY,
    build_strategy_for_symbol,
    get_strategy,
    list_strategies,
    resolve_strategy_params,
    validate_strategy_params,
)

_STRATEGY_CLASSES = DESK_STRATEGY_CLASSES

STRATEGIES = {desk: cls() for desk, cls in _STRATEGY_CLASSES.items()}


def build_strategies(strategy_cfg=None):
    """Xay instance chien luoc moi desk tu config (muc "strategy").

    strategy_cfg dang:
        {<tham so chung>, "desks": {<desk>: {<ghi de rieng desk>}}}
    vd {"sma_fast": 5, ..., "desks": {"crypto": {"atr_sl_mult": 2.0}}}.
    Tham so truyen vao thang (khong qua "desks") cung duoc chap nhan
    nhu tham so chung. Ghi de rieng desk thang tham so chung; neu
    khong co config thi dung mac dinh cua lop (crypto van co he so 2.0
    nho DESK_OVERRIDES). STRATEGIES giu nguyen la registry mac dinh.
    Khoa "per_symbol" (neu co) KHONG ap o day — build_strategies tra
    ve 1 instance/desk, khong phan biet symbol; dung
    build_strategy(desk, symbol=..., cfg=...) de lay instance theo
    symbol (tham so rieng symbol thang cao nhat).
    """
    cfg = dict(strategy_cfg or {})
    shared = {k: v for k, v in cfg.items() if k not in ("desks", "per_symbol")}
    per_desk = dict(cfg.get("desks") or {})
    built = {}
    for desk, cls in _STRATEGY_CLASSES.items():
        built[desk] = cls(params=shared,
                          desk_params=per_desk.get(desk) or {})
    return built


def build_strategy(desk, symbol=None, cfg=None, strategy_cfg=None,
                   strategy_name="default"):
    """Xay 1 instance chien luoc cho 1 desk (va 1 symbol neu co).

    - Khong co symbol/cfg: instance mac dinh cua desk (nhu
      build_strategies(...)[desk]).
    - Co symbol + cfg (config day du) hoac strategy_cfg (muc
      "strategy"): tham so resolve theo thu tu mac dinh < chung <
      ghi de lop theo desk < ghi de desk < ghi de symbol
      (xem registry.resolve_strategy_params).
    """
    if symbol is None and cfg is None and strategy_cfg is None:
        return get_strategy(strategy_name, desk=desk)
    if cfg is not None:
        return build_strategy_for_symbol(cfg, desk, symbol,
                                         strategy_name)
    section = dict(strategy_cfg or {})
    full_cfg = {"strategy": section}
    return build_strategy_for_symbol(full_cfg, desk, symbol,
                                     strategy_name)


__all__ = ["Strategy", "STRATEGIES", "build_strategies", "build_strategy",
           "STRATEGY_REGISTRY", "get_strategy", "list_strategies",
           "resolve_strategy_params", "validate_strategy_params",
           "build_strategy_for_symbol"]
