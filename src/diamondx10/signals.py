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
from .multitimeframe import htf_filter
from .patterns import detect_patterns, pattern_summary
from .strategies import STRATEGIES, build_strategy


def generate_signals(desk, bars, strategies=None, *, symbol=None,
                     cfg=None, strategy_name="default", htf_trend=None):
    """Tin hieu cho 1 desk (va 1 symbol neu truyen symbol + cfg).

    strategies: dict desk -> instance (uu tien sau cfg+symbol);
    neu khong truyen gi thi dung STRATEGIES mac dinh theo desk.
    Ket qua them khoa "symbol" va "params" (tham so thuc te da dung)
    khi co symbol, va khoa "context" (RSI/SMA/ADX/ATR% cua lan tinh
    nay, lay tu strat.last_context — rong {} khi HOLD dung som).
    htf_trend: dict trend H1 tu multitimeframe.compute_htf_trend
    (hoac None = tat loc); khi co, tin hieu BUY/SELL nguoc trend
    manh bi chan thanh HOLD (ly do kem ghi chu HTF), ket qua luon
    mang khoa "htf_trend" (dict hoac None).
    """
    if cfg is not None and symbol is not None:
        strat = build_strategy(desk, symbol=symbol, cfg=cfg,
                               strategy_name=strategy_name)
    elif strategies is not None:
        strat = strategies[desk]
    else:
        strat = STRATEGIES[desk]
    action, reason, levels = strat.signal(bars)
    # Loc HTF (multi-timeframe v1): chi ap khi caller truyen trend
    # H1 (compute_htf_trend). htf_trend None -> hanh vi cu nguyen ven.
    if action in ("BUY", "SELL") and htf_trend is not None:
        allowed, note = htf_filter(action, htf_trend)
        if not allowed:
            action, levels = "HOLD", None
            reason = f"{reason} {note}"
        elif note:
            reason = f"{reason} {note}"
    patterns = detect_patterns(bars)
    _, pattern_score = pattern_summary(patterns)
    result = {"desk": desk, "strategy": strat.name, "action": action,
              "reason": reason, "levels": levels,
              "size_scale": (levels.get("size_scale", 1.0)
                             if levels else 1.0),
              "regime": detect_regime(bars),
              "patterns": patterns, "pattern_score": pattern_score,
              "context": dict(getattr(strat, "last_context", None)
                              or {}),
              "htf_trend": htf_trend}
    if symbol is not None:
        result["symbol"] = symbol
        result["params"] = dict(strat.params)
    return result
