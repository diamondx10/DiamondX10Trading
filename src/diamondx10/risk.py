"""Risk: position sizing theo % rui ro, stop-loss, gioi han drawdown."""


def position_size(capital_usd, risk_pct, entry, stop_loss):
    """So tien vao lenh sao cho lo toi da = capital * risk_pct."""
    risk_per_unit = abs(entry - stop_loss)
    if risk_per_unit <= 0:
        return 0.0
    max_loss = capital_usd * risk_pct / 100.0
    return max_loss / risk_per_unit


def check_drawdown(equity_curve, max_drawdown_pct=10.0):
    peak = equity_curve[0]
    for v in equity_curve:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100 if peak else 0
        if dd > max_drawdown_pct:
            return False, f"drawdown {dd:.1f}% vuot gioi han {max_drawdown_pct}%"
    return True, "drawdown trong gioi han"
