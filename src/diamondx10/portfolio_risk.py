"""Portfolio Risk Engine — rui ro toan danh muc (khong phai rui ro 1 lenh).

Chi la CHI SO BAO CAO + canh bao — khong chan lenh, khong doi size,
khong sua vi the. Cac chan cung (drawdown, kill switch, demo-only,
margin, gioi han quy) van nam o risk.py / live.py / execution.py.

Chi dung STDLIB (math, random, statistics + sqlite qua HistoryStore):
khong numpy/scipy. Moi phep tinh ma tran (covariance, Cholesky,
Monte Carlo da bien) deu viet tay o day.

Quy uoc:
- Notional co dau (signed notional): BUY +, SELL -.
- VaR tra ve so duong (muc lo USD), CVaR (Expected Shortfall) cung vay.
- Loi nhuan log (log return) tinh tu gia dong cua cac nen M15.
- Monte Carlo: hiep phuong sai M15 nhan len theo ngay bang sqrt(96)
  (96 nen M15/ngay). DAY LA XAP XI: crypto giao dich 24/7 nen gan
  dung, con FX / co phieu My khong giao dich 24/7 (nghi cuoi tuan,
  ngoai phien) nen he so nay danh gia CAO bien dong ngay cua chung.
  Ket qua MC la uoc luong bao cao, khong phai du bao chinh xac.
"""
import math
import random
import statistics
from datetime import datetime, timezone

from . import decisions
from .data.history import DEFAULT_DB_PATH, HistoryStore
from .risk import expected_shortfall as _hist_expected_shortfall
from .risk import value_at_risk as _hist_value_at_risk

# 10 symbol trong danh muc dx10 (xem config data.symbols).
KNOWN_SYMBOLS = (
    "EURUSD", "XAUUSD", "BTCUSD", "ETHUSD", "BNBUSD",
    "AMD", "CDNS", "SNPS", "INTC", "NVDA",
)

# Desk mac dinh theo symbol (dung khi config khong co data.symbols).
_DEFAULT_DESK = {
    "EURUSD": "forex",
    "XAUUSD": "xauusd",
    "BTCUSD": "crypto", "ETHUSD": "crypto", "BNBUSD": "crypto",
    "AMD": "us_securities", "CDNS": "us_securities",
    "SNPS": "us_securities", "INTC": "us_securities",
    "NVDA": "us_securities",
}

# Contract size mac dinh theo desk (xem execution.CONTRACT_SIZES).
_CONTRACT_SIZE_BY_DESK = {
    "forex": 100000,
    "xauusd": 100,
    "crypto": 1,
    "us_securities": 1,
}
DEFAULT_CONTRACT_SIZE = 1

# So nen M15 trong 1 ngay (24h * 4 nen/gio) — he so scale MC.
M15_BARS_PER_DAY = 96

DEFAULT_PORTFOLIO_VAR_LIMIT_PCT = 2.0
DEFAULT_MC_PATHS = 10000
DEFAULT_MC_HORIZON_DAYS = 1
DEFAULT_MC_SEED = 42

# Kich ban stress mac dinh (giong config.example.yaml risk.stress_scenarios).
# Shock tinh theo % (vd -30 = -30%).
DEFAULT_STRESS_SCENARIOS = [
    {"name": "Crypto crash",
     "shocks": {"BTCUSD": -30, "ETHUSD": -30, "BNBUSD": -30}},
    {"name": "Co phieu My crash",
     "shocks": {"AMD": -20, "NVDA": -20, "INTC": -20, "CDNS": -20,
                "SNPS": -20}},
    {"name": "Vang tang manh", "shocks": {"XAUUSD": 10}},
    {"name": "Vang giam manh", "shocks": {"XAUUSD": -10}},
    {"name": "USD manh len", "shocks": {"EURUSD": -2}},
    {"name": "Tat ca rui ro giam",
     "shocks": {s: -10 for s in KNOWN_SYMBOLS}},
    {"name": "Soc kieu 2020",
     "shocks": {"AMD": -30, "NVDA": -30, "INTC": -30, "CDNS": -30,
                "SNPS": -30, "BTCUSD": -40, "ETHUSD": -40,
                "BNBUSD": -40, "XAUUSD": 5, "EURUSD": -3}},
]

_Z_95 = 1.645
_Z_99 = 2.33


def _z_value(confidence):
    """z cho muc tin cay: 1.645 (95%), 2.33 (99%) theo dung quy dinh;
    muc khac dung NormalDist (stdlib)."""
    if abs(float(confidence) - 0.95) < 1e-9:
        return _Z_95
    if abs(float(confidence) - 0.99) < 1e-9:
        return _Z_99
    return statistics.NormalDist().inv_cdf(float(confidence))


def _norm_pdf(z):
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _percentile(sorted_values, pct):
    """Phan vi noi suy tuyen tinh (giong risk._percentile)."""
    vals = sorted(float(v) for v in (sorted_values or []))
    n = len(vals)
    if n == 0:
        return None
    if n == 1:
        return float(vals[0])
    rank = pct / 100.0 * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(vals[lo] * (1 - frac) + vals[hi] * frac)


def _desk_for_symbol(symbol, cfg=None):
    """Desk cua symbol: doc tu config data.symbols truoc, roi fallback
    bang mac dinh. Symbol la thi ValueError."""
    data_cfg = (cfg or {}).get("data") or {}
    symbols_cfg = data_cfg.get("symbols") or {}
    for desk, syms in symbols_cfg.items():
        if symbol in (syms or []):
            return desk
    desk = _DEFAULT_DESK.get(symbol)
    if desk is None:
        raise ValueError(f"symbol khong biet desk: {symbol!r}")
    return desk


def _contract_size_for_symbol(symbol, cfg=None):
    return _CONTRACT_SIZE_BY_DESK.get(
        _desk_for_symbol(symbol, cfg), DEFAULT_CONTRACT_SIZE)


def _risk_cfg(cfg):
    return (cfg or {}).get("risk") or {}


def _equity_usd(cfg):
    return float((cfg or {}).get("fund", {}).get("total_capital_usd") or 0.0)


def _max_drawdown_pct(cfg):
    return float(_risk_cfg(cfg).get("max_drawdown_pct", 10.0))


# ---------------------------------------------------------------------------
# Loi nhuan log + ma tran hiep phuong sai / tuong quan
# ---------------------------------------------------------------------------

def log_returns_from_store(store, symbols, timeframe="M15", limit=None):
    """Loi nhuan log theo symbol, inner-join tren timestamp CHUNG.

    Lay bar tu store (get_bars), chi giu cac timestamp co mat o TAT CA
    symbol; timestamp lech / thieu bi loai, khong bao gio crash.
    limit: so bar gan nhat moi symbol (None = tat ca).
    Tra (timestamps, {symbol: [log returns]}), timestamps la thoi diem
    cua cac muc return (bo timestamp chung dau tien, vi return can
    gia truoc do). Gia dong <= 0 bi bo qua.
    """
    closes = {}
    for symbol in symbols or []:
        try:
            bars = store.get_bars(symbol, timeframe) if store is not None else []
        except Exception:
            bars = []
        bars = sorted(bars or [], key=lambda b: b["time"])
        if limit is not None:
            bars = bars[-int(limit):]
        closes[symbol] = {int(b["time"]): float(b["close"])
                          for b in bars
                          if float(b.get("close") or 0) > 0}
    symbols = [s for s in (symbols or []) if closes.get(s)]
    if not symbols:
        return [], {}
    common = None
    for s in symbols:
        times = set(closes[s])
        common = times if common is None else (common & times)
    if not common:
        return [], {s: [] for s in symbols}
    common = sorted(common)
    if len(common) < 2:
        return [], {s: [] for s in symbols}
    timestamps = common[1:]
    out = {}
    for s in symbols:
        series = [closes[s][t] for t in common]
        out[s] = [math.log(series[i] / series[i - 1])
                  for i in range(1, len(series))]
    return timestamps, out


def covariance_matrix(returns_dict):
    """Ma tran hiep phuong sai mau (chia n-1) cua cac chuoi return.

    Tra dict long nhau {symbol: {symbol: float}}. Chuoi ngan hon bi
    cat theo do dai ngan nhat; < 2 quan sat -> hiep phuong sai 0.
    """
    symbols = list(returns_dict or {})
    n = min((len(returns_dict[s]) for s in symbols), default=0)
    cov = {s: {} for s in symbols}
    if n < 2:
        for s in symbols:
            for t in symbols:
                cov[s][t] = 0.0
        return cov
    means = {s: statistics.fmean(returns_dict[s][:n]) for s in symbols}
    for s in symbols:
        xs = returns_dict[s][:n]
        for t in symbols:
            ys = returns_dict[t][:n]
            m_s, m_t = means[s], means[t]
            cov[s][t] = sum((x - m_s) * (y - m_t)
                            for x, y in zip(xs, ys)) / (n - 1)
    return cov


def correlation_matrix(cov):
    """Ma tran tuong quan tu ma tran hiep phuong sai (dict long nhau)."""
    symbols = list(cov or {})
    corr = {s: {} for s in symbols}
    for s in symbols:
        for t in symbols:
            var_s = cov[s][s]
            var_t = cov[t][t]
            if var_s <= 0 or var_t <= 0:
                corr[s][t] = 1.0 if s == t else 0.0
            else:
                corr[s][t] = cov[s][t] / math.sqrt(var_s * var_t)
    return corr


def cholesky(matrix):
    """Phan tich Cholesky (ha tam giac L sao cho L @ L.T = matrix).

    Nhan dict long nhau {symbol: {symbol: float}} hoac list 2 chieu;
    tra ve cung dang (dict long nhau neu nhan dict, list neu nhan list).
    Ma tran khong xac dinh duong: thu lai voi jitter duong cheo nho
    tang dan (1e-12, 1e-10, 1e-8, 1e-6); van that bai thi ValueError.
    """
    is_dict = isinstance(matrix, dict)
    if is_dict:
        symbols = list(matrix.keys())
        mat = [[float(matrix[s][t]) for t in symbols] for s in symbols]
    else:
        symbols = None
        mat = [[float(v) for v in row] for row in matrix]
    n = len(mat)
    if n == 0:
        return {} if is_dict else []
    scale = max((abs(mat[i][i]) for i in range(n)), default=0.0) or 1.0
    for jitter in (0.0, 1e-12, 1e-10, 1e-8, 1e-6):
        try:
            L = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(i + 1):
                    s = sum(L[i][k] * L[j][k] for k in range(j))
                    if i == j:
                        val = mat[i][i] + jitter * scale - s
                        if val <= 0:
                            raise ValueError(
                                "ma tran khong xac dinh duong")
                        L[i][j] = math.sqrt(val)
                    else:
                        L[i][j] = (mat[i][j] - s) / L[j][j]
            if is_dict:
                return {symbols[i]: {symbols[j]: L[i][j]
                                     for j in range(n)}
                        for i in range(n)}
            return L
        except ValueError:
            continue
    raise ValueError("ma tran khong xac dinh duong (ke ca sau jitter)")


def _cov_value(cov, sym_i, sym_j, symbols=None):
    """Doc 1 o hiep phuong sai: cov la dict long nhau hoac list 2 chieu."""
    if isinstance(cov, dict):
        return float(cov[sym_i][sym_j])
    i = symbols.index(sym_i)
    j = symbols.index(sym_j)
    return float(cov[i][j])


def _portfolio_variance(weights_usd, cov):
    """w'Σw. weights_usd: dict {symbol: signed notional USD} (list cung
    duoc: phai kem cov dang list va thu tu giong nhau — khong khuyen dung)."""
    if isinstance(weights_usd, dict):
        symbols = list(weights_usd.keys())
        w = [float(weights_usd[s]) for s in symbols]
    else:
        symbols = None
        w = [float(v) for v in weights_usd]
        symbols = list(range(len(w)))
    var = 0.0
    for i, si in enumerate(symbols):
        for j, sj in enumerate(symbols):
            if isinstance(cov, dict):
                c = float(cov[si][sj])
            else:
                c = float(cov[i][j])
            var += w[i] * w[j] * c
    return max(var, 0.0), symbols, w


# ---------------------------------------------------------------------------
# VaR: tham so (parametric), lich su, Monte Carlo, component
# ---------------------------------------------------------------------------

def parametric_var(weights_usd, cov, confidence=0.95):
    """VaR + CVaR tham so (gia dinh chuan): VaR = z*sigma,
    CVaR = phi(z)/(1-conf)*sigma, sigma = sqrt(w'Σw).
    z = 1.645 (95%) / 2.33 (99%). Tra (var_usd, cvar_usd), so duong."""
    conf = float(confidence)
    if not 0 < conf < 1:
        raise ValueError(f"confidence phai trong (0, 1), nhan {conf}")
    var_port, _, _ = _portfolio_variance(weights_usd, cov)
    sigma = math.sqrt(var_port)
    z = _z_value(conf)
    var_usd = z * sigma
    cvar_usd = _norm_pdf(z) / (1.0 - conf) * sigma
    return float(var_usd), float(cvar_usd)


def historical_var(portfolio_returns, confidence=0.95):
    """VaR + CVaR lich su tu chuoi P&L (USD) hoac return tung ky cua
    danh muc: phan vi lo + trung binh lo vuot VaR. Dung lai
    risk.value_at_risk / risk.expected_shortfall (chung lam viec tren
    moi don vi — USD vao thi USD ra). Tra (0.0, 0.0) neu < 2 ky."""
    vals = [float(r) for r in (portfolio_returns or [])]
    if len(vals) < 2:
        return 0.0, 0.0
    var = _hist_value_at_risk(vals, float(confidence))
    cvar = _hist_expected_shortfall(vals, float(confidence))
    return float(var or 0.0), float(cvar or 0.0)


def monte_carlo_var(weights_usd, cov, n_paths=10000, horizon_days=1,
                    seed=42, equity_usd=None, max_drawdown_pct=10.0):
    """Monte Carlo VaR da bien chuan qua Cholesky.

    Hiep phuong sai M15 duoc scale len theo ngay bang sqrt(96) moi ngay
    (phuong sai nhan 96 * horizon_days). DAY LA XAP XI: crypto giao
    dich 24/7 nen gan dung, con FX / co phieu My khong giao dich 24/7
    (nghi cuoi tuan, ngoai phien) nen he so nay danh gia CAO bien dong
    ngay cua chung — ket qua la uoc luong bao cao, khong phai du bao.

    equity_usd + max_drawdown_pct (mac dinh 10% von quy) dung de tinh
    prob_breach_drawdown_pct = ti le path co lo >= gioi han drawdown
    cua quy; khong biet equity thi None.
    Tra dict {paths, seed, horizon_days, mean_pnl, sd_pnl, p5, p50,
    p95, var_95, cvar_95, prob_breach_drawdown_pct}.
    """
    n_paths = int(n_paths)
    horizon_days = float(horizon_days)
    if n_paths < 1:
        raise ValueError(f"n_paths phai >= 1, nhan {n_paths}")
    if horizon_days <= 0:
        raise ValueError(
            f"horizon_days phai > 0, nhan {horizon_days}")
    if isinstance(weights_usd, dict):
        symbols = list(weights_usd.keys())
        w = [float(weights_usd[s]) for s in symbols]
    else:
        symbols = list(range(len(weights_usd)))
        w = [float(v) for v in weights_usd]
    n = len(w)
    if n == 0:
        return {"paths": n_paths, "seed": seed,
                "horizon_days": horizon_days, "mean_pnl": 0.0,
                "sd_pnl": 0.0, "p5": 0.0, "p50": 0.0, "p95": 0.0,
                "var_95": 0.0, "cvar_95": 0.0,
                "prob_breach_drawdown_pct": None}
    scale = M15_BARS_PER_DAY * horizon_days
    if isinstance(cov, dict):
        mat = [[float(cov[si][sj]) * scale for sj in symbols]
               for si in symbols]
    else:
        mat = [[float(cov[i][j]) * scale for j in range(n)]
               for i in range(n)]
    L = cholesky(mat)
    rng = random.Random(seed)
    pnls = []
    for _ in range(n_paths):
        z = [rng.gauss(0.0, 1.0) for _ in range(n)]
        rets = [sum(L[i][k] * z[k] for k in range(i + 1))
                for i in range(n)]
        pnls.append(sum(wi * ri for wi, ri in zip(w, rets)))
    pnls_sorted = sorted(pnls)
    p5 = _percentile(pnls_sorted, 5)
    p50 = _percentile(pnls_sorted, 50)
    p95 = _percentile(pnls_sorted, 95)
    var_95 = -p5 if p5 < 0 else 0.0
    tail = [p for p in pnls if p <= -var_95] if var_95 > 0 else []
    cvar_95 = -sum(tail) / len(tail) if tail else 0.0
    dd_limit = None
    if equity_usd is not None and float(equity_usd) > 0:
        dd_limit = float(equity_usd) * float(max_drawdown_pct) / 100.0
    prob_breach = None
    if dd_limit is not None:
        breached = sum(1 for p in pnls if -p >= dd_limit)
        prob_breach = breached / n_paths * 100.0
    return {
        "paths": n_paths,
        "seed": seed,
        "horizon_days": horizon_days,
        "mean_pnl": float(statistics.fmean(pnls)),
        "sd_pnl": float(statistics.pstdev(pnls)) if n_paths > 1 else 0.0,
        "p5": float(p5),
        "p50": float(p50),
        "p95": float(p95),
        "var_95": float(var_95),
        "cvar_95": float(cvar_95),
        "prob_breach_drawdown_pct": prob_breach,
    }


def component_var(weights_usd, cov, var_usd):
    """Phan bo VaR theo Euler: marginal_i = var * (Σw)_i / (w'Σw),
    component_i = w_i * marginal_i (w co dau: BUY +, SELL -).
    Tong cac component = VaR (sai so lam tron). Tra list
    [{symbol, var_usd, share_pct}]."""
    if isinstance(weights_usd, dict):
        symbols = list(weights_usd.keys())
        w = {s: float(weights_usd[s]) for s in symbols}
    else:
        symbols = list(range(len(weights_usd)))
        w = {i: float(v) for i, v in enumerate(weights_usd)}
    var_usd = float(var_usd or 0.0)
    var_port, _, _ = _portfolio_variance(weights_usd, cov)
    out = []
    if var_port <= 0 or var_usd <= 0:
        for s in symbols:
            out.append({"symbol": s, "var_usd": 0.0, "share_pct": 0.0})
        return out
    for s in symbols:
        sig_w = sum(w[t] * _cov_value(cov, s, t, symbols)
                    for t in symbols)
        comp = w[s] * var_usd * sig_w / var_port
        out.append({"symbol": s, "var_usd": float(comp),
                    "share_pct": float(comp / var_usd * 100.0)})
    return out


# ---------------------------------------------------------------------------
# Stress test
# ---------------------------------------------------------------------------

def apply_stress(exposures, shocks):
    """Ap shock % theo symbol len notional co dau.
    exposures: list dict {symbol, signed_notional_usd} (chap nhan ca
    {symbol, notional_usd, direction} — SELL doi dau). shocks: {symbol:
    pct} (vd -30 = -30%). Symbol trong shocks ma khong co exposure
    thi bo qua (pnl 0). Tra (pnl_usd, {symbol: pnl_usd})."""
    per_symbol = {}
    total = 0.0
    for exp in exposures or []:
        symbol = exp.get("symbol")
        if symbol is None:
            continue
        signed = exp.get("signed_notional_usd")
        if signed is None:
            notional = float(exp.get("notional_usd") or 0.0)
            direction = str(exp.get("direction") or "BUY").upper()
            signed = notional if direction == "BUY" else -notional
        shock = shocks.get(symbol)
        if shock is None:
            continue
        pnl = float(signed) * float(shock) / 100.0
        per_symbol[symbol] = per_symbol.get(symbol, 0.0) + pnl
        total += pnl
    return float(total), per_symbol


def load_stress_scenarios(cfg):
    """Doc risk.stress_scenarios tu config. Tra list {name, shocks}.
    Scenario co symbol LA thi ValueError NEU TEN symbol do — khong
    bao gio lang le bo qua. Thieu muc trong config thi tra []."""
    raw = _risk_cfg(cfg).get("stress_scenarios")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("risk.stress_scenarios phai la list")
    scenarios = []
    for i, sc in enumerate(raw):
        if not isinstance(sc, dict):
            raise ValueError(f"stress_scenarios[{i}] phai la dict")
        name = sc.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(
                f"stress_scenarios[{i}] thieu name (chuoi khong rong)")
        shocks = sc.get("shocks")
        if not isinstance(shocks, dict) or not shocks:
            raise ValueError(
                f"stress scenario {name!r} thieu shocks (dict khong rong)")
        clean = {}
        for symbol, pct in shocks.items():
            if symbol not in KNOWN_SYMBOLS:
                raise ValueError(
                    f"stress scenario {name!r}: symbol khong biet "
                    f"{symbol!r} (chi chap nhan {', '.join(KNOWN_SYMBOLS)})")
            try:
                clean[symbol] = float(pct)
            except (TypeError, ValueError):
                raise ValueError(
                    f"stress scenario {name!r}: shock cua {symbol} "
                    f"khong phai so ({pct!r})")
            if not math.isfinite(clean[symbol]):
                raise ValueError(
                    f"stress scenario {name!r}: shock cua {symbol} "
                    "khong huu han")
        scenarios.append({"name": name, "shocks": clean})
    return scenarios


def validate_portfolio_risk_config(cfg):
    """Bao loi LOUD khi config rui ro danh muc sai — khong lang le
    dung mac dinh thay the gia tri sai.

    - portfolio_var_limit_pct: (0, 100] (mac dinh 2.0 neu thieu).
    - mc_paths: >= 100 (mac dinh 10000 neu thieu).
    - mc_horizon_days: > 0 (mac dinh 1 neu thieu).
    - stress_scenarios: dung dang, symbol phai biet (xem
      load_stress_scenarios).
    Tra True neu hop le.
    """
    risk_cfg = _risk_cfg(cfg)
    limit = risk_cfg.get("portfolio_var_limit_pct",
                         DEFAULT_PORTFOLIO_VAR_LIMIT_PCT)
    try:
        limit = float(limit)
    except (TypeError, ValueError):
        raise ValueError(
            "risk.portfolio_var_limit_pct phai la so, nhan "
            f"{limit!r}")
    if not math.isfinite(limit) or limit <= 0 or limit > 100:
        raise ValueError(
            "risk.portfolio_var_limit_pct phai trong (0, 100], nhan "
            f"{limit}")
    paths = risk_cfg.get("mc_paths", DEFAULT_MC_PATHS)
    if isinstance(paths, bool) or not isinstance(paths, int):
        try:
            paths = int(paths)
        except (TypeError, ValueError):
            raise ValueError(
                f"risk.mc_paths phai la so nguyen, nhan {paths!r}")
    if paths < 100:
        raise ValueError(
            f"risk.mc_paths phai >= 100, nhan {paths}")
    horizon = risk_cfg.get("mc_horizon_days", DEFAULT_MC_HORIZON_DAYS)
    try:
        horizon = float(horizon)
    except (TypeError, ValueError):
        raise ValueError(
            f"risk.mc_horizon_days phai la so, nhan {horizon!r}")
    if not math.isfinite(horizon) or horizon <= 0:
        raise ValueError(
            f"risk.mc_horizon_days phai > 0, nhan {horizon}")
    load_stress_scenarios(cfg)  # bao loi neu scenario sai / la symbol
    return True


# ---------------------------------------------------------------------------
# Bao cao tong hop (hop dong cong khai cho CLI / report / web)
# ---------------------------------------------------------------------------

def _latest_close(store, symbol, timeframe="M15"):
    """Gia dong moi nhat tu store; None neu khong co bar nao.
    (get_bars(limit=1) tra bar CU nhat, nen phai lay het roi lay [-1].)"""
    if store is None:
        return None
    try:
        bars = store.get_bars(symbol, timeframe)
    except Exception:
        return None
    if not bars:
        return None
    return float(bars[-1]["close"])


def _load_positions_and_equity(cfg, positions):
    """Vi the mo + equity: neu positions truyen vao thi dung no (equity
    lay theo config); khong thi doc decisions/equity-state.json giong
    report.build_report (guard.fund_curve[-1] la equity hien tai)."""
    total_cap = _equity_usd(cfg)
    if positions is not None:
        if isinstance(positions, dict):
            positions = positions.get("positions") or []
        return list(positions or []), total_cap, False
    state = None
    try:
        state = decisions.load_equity_state()
    except Exception:
        state = None
    if state and state.get("guard"):
        try:
            from .risk import DrawdownGuard
            guard = DrawdownGuard.from_state(state["guard"])
            equity = float(guard.fund_curve[-1])
        except Exception:
            equity = total_cap
        return list(state.get("positions") or []), equity, True
    return list((state or {}).get("positions") or []), total_cap, False


def _worst_day_stress(timestamps, returns_dict, weights_usd):
    """Ngay te nhat lich su: gop log return theo ngay UTC, lay ngay co
    P&L danh muc te nhat. Tra (pnl_usd, ngay_iso) hoac None neu khong
    du du lieu (can it nhat 1 ngay co du return)."""
    if not timestamps or not returns_dict or not weights_usd:
        return None
    symbols = [s for s in returns_dict if s in weights_usd]
    if not symbols:
        return None
    per_day = {}
    for i, ts in enumerate(timestamps):
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        per_day.setdefault(day, []).append(i)
    worst = None
    for day, idxs in per_day.items():
        pnl = 0.0
        for s in symbols:
            log_sum = sum(returns_dict[s][i] for i in idxs)
            simple = math.exp(log_sum) - 1.0
            pnl += float(weights_usd[s]) * simple
        if worst is None or pnl < worst[0]:
            worst = (pnl, day)
    return worst


def build_portfolio_risk_report(cfg, *, mc_paths=None, horizon_days=None,
                                demo=False, store=None, positions=None,
                                prices=None):
    """Xay bao cao rui ro danh muc (dict JSON-serializable).

    Vi the: tham so `positions` neu co, khong thi doc
    decisions/equity-state.json. Gia moi symbol: tham so `prices` neu
    co, khong thi gia dong moi nhat tu store; khong co gia thi bo
    symbol do kem warning. Store: neu khong truyen va file history.db
    mac dinh ton tai thi mo no (chi doc); khong thi lich su khong co,
    cac muc VaR = None kem warning, khong crash.
    """
    cfg = cfg or {}
    validate_portfolio_risk_config(cfg)
    risk_cfg = _risk_cfg(cfg)
    limit_pct = float(risk_cfg.get(
        "portfolio_var_limit_pct", DEFAULT_PORTFOLIO_VAR_LIMIT_PCT))
    n_paths = int(mc_paths if mc_paths is not None else risk_cfg.get(
        "mc_paths", DEFAULT_MC_PATHS))
    horizon = float(horizon_days if horizon_days is not None
                    else risk_cfg.get("mc_horizon_days",
                                      DEFAULT_MC_HORIZON_DAYS))
    if n_paths < 100:
        raise ValueError(f"mc_paths phai >= 100, nhan {n_paths}")
    if horizon <= 0:
        raise ValueError(f"mc_horizon_days phai > 0, nhan {horizon}")
    max_dd = _max_drawdown_pct(cfg)
    warnings = []
    notes = []

    raw_positions, equity, _from_state = _load_positions_and_equity(
        cfg, positions)
    if equity <= 0:
        equity = _equity_usd(cfg)
    if demo:
        notes.append("DEMO: danh muc gia lap can deu 10 symbol, "
                     "khong phai vi the that")

    # --- Xay danh sach vi the can danh gia ---
    eval_positions = []
    if demo:
        for symbol in KNOWN_SYMBOLS:
            eval_positions.append({
                "desk": _desk_for_symbol(symbol, cfg),
                "symbol": symbol,
                "direction": "BUY",
                "entry": None,
                "volume": None,
                "contract_size": _contract_size_for_symbol(symbol, cfg),
                "_demo_notional": equity / len(KNOWN_SYMBOLS),
            })
    else:
        eval_positions = list(raw_positions or [])

    # --- Store lich su (chi mo file mac dinh neu no ton tai) ---
    store_opened_here = False
    if store is None and DEFAULT_DB_PATH.exists():
        try:
            store = HistoryStore()
            store_opened_here = True
        except Exception:
            store = None
            warnings.append("khong mo duoc history.db — bo qua lich su gia")

    # --- Exposures ---
    exposures = []
    for pos in eval_positions:
        symbol = pos.get("symbol")
        if symbol not in KNOWN_SYMBOLS:
            warnings.append(f"bo qua vi the symbol la {symbol!r}")
            continue
        if prices is not None and symbol in prices:
            price = float(prices[symbol])
        else:
            price = _latest_close(store, symbol)
        if price is None or price <= 0:
            warnings.append(
                f"bo qua {symbol}: khong co gia hien tai")
            continue
        contract_size = float(pos.get("contract_size") or
                              _contract_size_for_symbol(symbol, cfg))
        if demo:
            notional = float(pos.get("_demo_notional") or 0.0)
            volume = (notional / (price * contract_size)
                      if price * contract_size > 0 else 0.0)
        else:
            volume = float(pos.get("volume") or 0.0)
            notional = volume * contract_size * price
        direction = str(pos.get("direction") or "BUY").upper()
        signed = notional if direction == "BUY" else -notional
        exposures.append({
            "symbol": symbol,
            "desk": pos.get("desk") or _desk_for_symbol(symbol, cfg),
            "direction": direction,
            "volume": float(volume),
            "price": float(price),
            "notional_usd": float(notional),
            "signed_notional_usd": float(signed),
        })
    if store_opened_here:
        try:
            store.close()
        except Exception:
            pass
        store = None  # da dung xong cho gia; lich su can store rieng
    symbols = [e["symbol"] for e in exposures]
    has_positions = bool(exposures)
    limit_usd = equity * limit_pct / 100.0

    var_block = {
        "parametric_95": None, "parametric_cvar_95": None,
        "historical_95": None, "historical_cvar_95": None,
        "mc_95": None, "mc_cvar_95": None,
        "limit_usd": float(limit_usd), "limit_pct": float(limit_pct),
        "breached": False,
    }
    mc_block = {
        "paths": None, "seed": DEFAULT_MC_SEED,
        "horizon_days": float(horizon),
        "mean_pnl": None, "sd_pnl": None, "p5": None, "p50": None,
        "p95": None, "prob_breach_drawdown_pct": None,
    }
    comp_var = []
    concentration = {"largest_symbol": None, "largest_share_pct": None}

    if not has_positions:
        if not demo and not raw_positions:
            warnings.append("khong co vi the mo")
            return {
                "has_positions": False, "demo": bool(demo),
                "equity_usd": float(equity), "symbols": [],
                "exposures": [],
                "var": {**var_block, "parametric_95": 0.0,
                        "parametric_cvar_95": 0.0, "historical_95": 0.0,
                        "historical_cvar_95": 0.0, "mc_95": 0.0,
                        "mc_cvar_95": 0.0},
                "mc": {**mc_block, "paths": n_paths},
                "component_var": [],
                "concentration": concentration,
                "stress": [],
                "warnings": warnings,
                "notes": notes,
            }
        warnings.append("khong tinh duoc exposure: vi the co nhung "
                        "khong co gia — xem warnings")

    # --- Tap trung ---
    gross = sum(abs(e["signed_notional_usd"]) for e in exposures)
    if gross > 0:
        largest = max(exposures,
                      key=lambda e: abs(e["signed_notional_usd"]))
        concentration = {
            "largest_symbol": largest["symbol"],
            "largest_share_pct": float(
                abs(largest["signed_notional_usd"]) / gross * 100.0),
        }

    # --- Lich su + VaR (can store; mo lai neu vua dong) ---
    timestamps, returns_dict = [], {}
    hist_store = store
    if hist_store is None and DEFAULT_DB_PATH.exists():
        try:
            hist_store = HistoryStore()
        except Exception:
            hist_store = None
    try:
        if hist_store is not None and symbols:
            timestamps, returns_dict = log_returns_from_store(
                hist_store, symbols)
    finally:
        if hist_store is not None and hist_store is not store:
            try:
                hist_store.close()
            except Exception:
                pass

    weights = {e["symbol"]: e["signed_notional_usd"] for e in exposures}
    n_obs = len(timestamps)
    if has_positions and n_obs >= 2 and returns_dict:
        cov = covariance_matrix(returns_dict)
        # Hiep phuong sai / return deu theo nen M15; VaR bao cao quy ve
        # 1 ngay (cung chan voi MC) bang sqrt(96 * horizon_days) —
        # cung xap xi nhu MC (xem docstring monte_carlo_var).
        day_scale = math.sqrt(M15_BARS_PER_DAY * horizon)
        p_var, p_cvar = parametric_var(weights, cov, 0.95)
        var_block["parametric_95"] = float(p_var * day_scale)
        var_block["parametric_cvar_95"] = float(p_cvar * day_scale)
        port_pnl = []
        for i in range(n_obs):
            port_pnl.append(sum(weights[s] * returns_dict[s][i]
                                for s in weights if s in returns_dict))
        h_var, h_cvar = historical_var(port_pnl, 0.95)
        var_block["historical_95"] = float(h_var * day_scale)
        var_block["historical_cvar_95"] = float(h_cvar * day_scale)
        mc = monte_carlo_var(weights, cov, n_paths=n_paths,
                             horizon_days=horizon, seed=DEFAULT_MC_SEED,
                             equity_usd=equity, max_drawdown_pct=max_dd)
        var_block["mc_95"] = float(mc["var_95"])
        var_block["mc_cvar_95"] = float(mc["cvar_95"])
        mc_block.update({
            "paths": mc["paths"], "seed": mc["seed"],
            "horizon_days": mc["horizon_days"],
            "mean_pnl": mc["mean_pnl"], "sd_pnl": mc["sd_pnl"],
            "p5": mc["p5"], "p50": mc["p50"], "p95": mc["p95"],
            "prob_breach_drawdown_pct": mc["prob_breach_drawdown_pct"],
        })
        notes.append(
            f"VaR tinh tren {n_obs} ky M15 chung cua {len(symbols)} symbol, "
            f"quy ve 1 ngay (x{day_scale:.1f} = sqrt(96)); "
            "MC scale sqrt(96)/ngay la xap xi (crypto 24/7, FX/co phieu "
            "khong giao dich 24/7)")
        desk_of = {e["symbol"]: e["desk"] for e in exposures}
        for row in component_var(weights, cov, p_var):
            comp_var.append({
                "symbol": row["symbol"],
                "desk": desk_of.get(row["symbol"], ""),
                "var_usd": row["var_usd"] * day_scale,
                "share_pct": row["share_pct"],
            })
    elif has_positions:
        warnings.append(
            "khong co du lich su gia chung de tinh VaR "
            f"(chi co {n_obs} ky chung) — cac muc VaR la None")
        mc_block["paths"] = n_paths

    # --- Breach ---
    for key in ("parametric_95", "historical_95", "mc_95"):
        v = var_block[key]
        if v is not None and v > limit_usd:
            var_block["breached"] = True
            warnings.append(
                f"VaR {key} {v:.2f} USD vuot gioi han {limit_usd:.2f} USD "
                f"({limit_pct:g}% von quy)")
    if var_block["breached"]:
        notes.append("VaR vuot gioi han la CANH BAO bao cao — khong chan "
                     "lenh (chan lenh van theo drawdown/kill switch)")

    # --- Stress ---
    stress_out = []
    if has_positions:
        if _risk_cfg(cfg).get("stress_scenarios") is not None:
            scenarios = load_stress_scenarios(cfg)
        else:
            scenarios = [dict(s) for s in DEFAULT_STRESS_SCENARIOS]
            notes.append("dung kich ban stress mac dinh (config chua co "
                         "risk.stress_scenarios)")
        dd_limit_usd = equity * max_dd / 100.0
        for sc in scenarios:
            pnl, _per = apply_stress(exposures, sc["shocks"])
            stress_out.append({
                "name": sc["name"],
                "pnl_usd": float(pnl),
                "pnl_pct": float(pnl / equity * 100.0) if equity else 0.0,
                "breaches_drawdown": bool(pnl <= -dd_limit_usd),
            })
        worst = _worst_day_stress(timestamps, returns_dict, weights)
        if worst is not None:
            pnl, day = worst
            stress_out.append({
                "name": "Ngay te nhat lich su",
                "pnl_usd": float(pnl),
                "pnl_pct": float(pnl / equity * 100.0) if equity else 0.0,
                "breaches_drawdown": bool(pnl <= -dd_limit_usd),
            })
            notes.append(f"ngay te nhat lich su trong du lieu: {day}")
        else:
            notes.append("khong tinh duoc ngay te nhat lich su "
                         "(thieu lich su gia chung)")

    return {
        "has_positions": has_positions,
        "demo": bool(demo),
        "equity_usd": float(equity),
        "symbols": symbols,
        "exposures": exposures,
        "var": var_block,
        "mc": mc_block,
        "component_var": comp_var,
        "concentration": concentration,
        "stress": stress_out,
        "warnings": warnings,
        "notes": notes,
    }


def format_portfolio_risk_report(rep):
    """In bao cao rui ro danh muc thanh text tieng Viet khong dau."""
    lines = ["DiamondX10 — BAO CAO RUI RO DANH MUC"]
    if rep.get("demo"):
        lines.append("(DEMO — danh muc gia lap can deu, khong phai vi the that)")
    lines.append(f"Von (equity): {rep['equity_usd']:.2f} USD")
    lines.append(f"Vi the mo: {len(rep['exposures'])}"
                 + ("" if rep["has_positions"] else " (khong co)"))
    for e in rep["exposures"]:
        lines.append(
            f"  - {e['direction']} {e['symbol']} ({e['desk']}): "
            f"{e['volume']:g} lot @ {e['price']:g} | notional "
            f"{e['notional_usd']:.2f} USD (co dau "
            f"{e['signed_notional_usd']:+.2f} USD)")
    conc = rep.get("concentration") or {}
    if conc.get("largest_symbol"):
        lines.append(
            f"Tap trung lon nhat: {conc['largest_symbol']} "
            f"{conc['largest_share_pct']:.1f}% tong notional")
    v = rep["var"]
    lines.append(
        f"Gioi han VaR: {v['limit_usd']:.2f} USD ({v['limit_pct']:g}% von quy)"
        + (" — VUOT GIOI HAN" if v["breached"] else ""))
    def _fmt(x):
        return f"{x:.2f} USD" if x is not None else "(chua tinh duoc)"
    lines.append(f"VaR tham so 95%: {_fmt(v['parametric_95'])} "
                 f"(CVaR 95%: {_fmt(v['parametric_cvar_95'])})")
    lines.append(f"VaR lich su 95%: {_fmt(v['historical_95'])} "
                 f"(CVaR 95%: {_fmt(v['historical_cvar_95'])})")
    lines.append(f"VaR Monte Carlo 95%: {_fmt(v['mc_95'])} "
                 f"(CVaR 95%: {_fmt(v['mc_cvar_95'])})")
    mc = rep.get("mc") or {}
    if mc.get("mean_pnl") is not None:
        lines.append(
            f"Monte Carlo ({mc['paths']} path, {mc['horizon_days']:g} ngay): "
            f"P&L trung binh {mc['mean_pnl']:+.2f} USD, do lech chuan "
            f"{mc['sd_pnl']:.2f} USD, p5 {mc['p5']:+.2f} / p50 "
            f"{mc['p50']:+.2f} / p95 {mc['p95']:+.2f} USD")
        if mc.get("prob_breach_drawdown_pct") is not None:
            lines.append(
                "Xac suat cham gioi han drawdown quy "
                f"({mc['prob_breach_drawdown_pct']:.2f}% so path)")
    else:
        lines.append("Monte Carlo: (chua tinh duoc — thieu lich su gia)")
    if rep.get("component_var"):
        lines.append("Component VaR (tham so 95%):")
        for row in rep["component_var"]:
            lines.append(
                f"  - {row['symbol']} ({row['desk']}): "
                f"{row['var_usd']:+.2f} USD ({row['share_pct']:+.1f}%)")
    if rep.get("stress"):
        lines.append("Stress test:")
        for s in rep["stress"]:
            lines.append(
                f"  - {s['name']}: {s['pnl_usd']:+.2f} USD "
                f"({s['pnl_pct']:+.2f}% von quy)"
                + (" — CHAM GIOI HAN DRAWDOWN" if s["breaches_drawdown"]
                   else ""))
    if rep.get("warnings"):
        lines.append("Canh bao:")
        for w in rep["warnings"]:
            lines.append(f"  - {w}")
    if rep.get("notes"):
        lines.append("Ghi chu:")
        for n in rep["notes"]:
            lines.append(f"  - {n}")
    return "\n".join(lines)
