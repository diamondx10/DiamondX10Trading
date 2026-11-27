"""Macro edge — do lech vi mo (DXY, US10Y, VIX, SPX) anh huong the nao
toi tung symbol.

Nguon: repo DiamondX10 (cu), src/analysis/macro_edge.py
(MacroEdgeCalculator, khung tuong quan cheo cua Ernie Chan). Chi lay
KHUNG (bang tuong quan ky vong + trong so + cong thuc), viet lai
thanh ham thuan dung thu vien chuan.

Khac biet co chu y so voi ban goc: ban goc nhan them -1 cho VIX
trong _calc_factor_edge, lam dao dau edge vang so voi chinh bang
tuong quan cua no (VIX len thi vang len, tuong quan +0,40 — nhan -1
se thanh edge am). O day bo phep nhan -1 do: edge = do lech chuan hoa
x tuong quan ky vong, dung dau bang. Xem docs/merge-diamondx10-2026-11-27.md.

Ham nay KHONG lay du lieu — snapshot vi mo (DXY, US10Y, VIX, SPX)
do Yuling cung cap (xem muc "macro" trong config.example.yaml).
Khong noi vao tin hieu giao dich: tin hieu live van la SMA + RSI
theo quy tac da chot; macro edge chi la boi canh cho Yuling duyet
(xem docs/trading-principles.md, quy tac 22).
"""

# Tuong quan ky vong giua symbol va tung yeu to vi mo (ban goc).
EXPECTED_CORRELATIONS = {
    "XAUUSD": {"DXY": -0.70, "US10Y": -0.60, "VIX": 0.40, "SPX": -0.10},
    "EURUSD": {"DXY": -0.90, "US10Y": -0.30, "VIX": -0.30, "SPX": 0.20},
}

# Trong so tong hop (ban goc): DXY 0,35 / US10Y 0,25 / VIX 0,25 / SPX 0,15.
WEIGHTS = {"dxy": 0.35, "us10y": 0.25, "vix": 0.25, "spx": 0.15}

# Mien gia tri va diem giua de chuan hoa do lech (ban goc).
_RANGES = {"DXY": 100.0, "US10Y": 5.0, "VIX": 25.0, "SPX": 5000.0}
_MIDPOINTS = {"DXY": 100.0, "US10Y": 3.5, "VIX": 18.0, "SPX": 4500.0}

_FACTOR_KEYS = (("DXY", "dxy"), ("US10Y", "us10y"),
                ("VIX", "vix"), ("SPX", "spx"))


def _factor_edge(factor, current, expected_corr):
    """Edge cua 1 yeu to: do lech khoi diem giua (chia cho mien gia tri)
    nhan tuong quan ky vong, gioi han [-1, 1]. Tra 0.0 neu thieu so
    hoac tuong quan bang 0."""
    if current is None or expected_corr == 0:
        return 0.0
    deviation = (float(current) - _MIDPOINTS[factor]) / _RANGES[factor]
    return max(-1.0, min(1.0, deviation * expected_corr))


def _summary(score, dxy_edge, vix_edge):
    if score > 0.3:
        bias = "Bullish macro bias"
    elif score < -0.3:
        bias = "Bearish macro bias"
    else:
        bias = "Neutral macro environment"
    parts = [bias]
    if abs(dxy_edge) > 0.2:
        parts.append(f"USD {'strong' if dxy_edge > 0 else 'weak'}")
    if abs(vix_edge) > 0.2:
        parts.append(
            f"VIX {'elevated (risk-off)' if vix_edge > 0 else 'subdued (risk-on)'}")
    return "; ".join(parts)


def macro_edge(symbol, *, dxy=None, us10y=None, vix=None, spx=None):
    """Tinh macro edge cho 1 symbol tu snapshot vi mo hien tai.

    Tra dict {symbol, score (-1..1), edges {dxy, us10y, vix, spx},
    summary}. Symbol chua co bang tuong quan (chi co XAUUSD, EURUSD)
    thi score 0.0 va summary ghi ro chua co mo hinh.
    """
    expected = EXPECTED_CORRELATIONS.get(symbol)
    if not expected:
        return {"symbol": symbol, "score": 0.0,
                "edges": {"dxy": 0.0, "us10y": 0.0, "vix": 0.0, "spx": 0.0},
                "summary": f"Chua co mo hinh macro cho symbol {symbol}"}
    current = {"DXY": dxy, "US10Y": us10y, "VIX": vix, "SPX": spx}
    edges = {}
    for factor, key in _FACTOR_KEYS:
        edges[key] = round(
            _factor_edge(factor, current[factor], expected.get(factor, 0)), 3)
    score = sum(edges[key] * WEIGHTS[key] for key in
                ("dxy", "us10y", "vix", "spx"))
    score = max(-1.0, min(1.0, score))
    return {"symbol": symbol, "score": round(score, 3), "edges": edges,
            "summary": _summary(score, edges["dxy"], edges["vix"])}
