"""Sinh tin hieu cho 1 desk tu feed hien tai.

Kem theo regime thi truong (ADX) lam BOI CANH — regime chi duoc ghi
nhan va hien thi, KHONG dung de chan hay doi tin hieu (xem
docs/trading-principles.md, quy tac 21; nguon: repo DiamondX10 cu,
regime_detector.py).

Tham so rieng theo symbol (Phase B): truyen symbol + cfg (config day
du) thi tin hieu dung tham so da resolve cho symbol do
(mac dinh < chung < desk < symbol — xem
strategies/registry.py). Khong truyen thi dung chien luoc theo desk
nhu truoc (tuong thich cu).
"""
from .models.quant import detect_regime
from .patterns import detect_patterns, pattern_summary
from .strategies import STRATEGIES, build_strategy


def generate_signals(desk, bars, strategies=None, *, symbol=None,
                     cfg=None, strategy_name="default"):
    """Tin hieu cho 1 desk (va 1 symbol neu truyen symbol + cfg).

    strategies: dict desk -> instance (uu tien sau cfg+symbol);
    neu khong truyen gi thi dung STRATEGIES mac dinh theo desk.
    Ket qua them khoa "symbol" va "params" (tham so thuc te da dung)
    khi co symbol.
    """
    if cfg is not None and symbol is not None:
        strat = build_strategy(desk, symbol=symbol, cfg=cfg,
                               strategy_name=strategy_name)
    elif strategies is not None:
        strat = strategies[desk]
    else:
        strat = STRATEGIES[desk]
    action, reason, levels = strat.signal(bars)
    patterns = detect_patterns(bars)
    _, pattern_score = pattern_summary(patterns)
    result = {"desk": desk, "strategy": strat.name, "action": action,
              "reason": reason, "levels": levels,
              "regime": detect_regime(bars),
              "patterns": patterns, "pattern_score": pattern_score}
    if symbol is not None:
        result["symbol"] = symbol
        result["params"] = dict(strat.params)
    return result
