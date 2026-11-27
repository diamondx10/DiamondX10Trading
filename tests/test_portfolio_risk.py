"""Test rui ro danh muc — VaR / Monte Carlo / stress (quy tac 66).

Viet theo hop dong cua worker song song (src/diamondx10/portfolio_risk.py):
  build_portfolio_risk_report(cfg, *, mc_paths=None, horizon_days=None,
      demo=False, store=None, positions=None, prices=None) -> dict
  + cac ham module: log_returns_from_store, covariance_matrix,
  correlation_matrix, cholesky, parametric_var, historical_var,
  monte_carlo_var, component_var, apply_stress, load_stress_scenarios,
  validate_portfolio_risk_config, format_portfolio_risk_report.

LUU Y HOP DONG (da doi chieu voi module that src/diamondx10/
portfolio_risk.py — doc ky truoc khi sua test):
- Khoa cau hinh nam duoi muc `risk:` trong config (xem
  config.example.yaml): portfolio_var_limit_pct (0, 100], mac dinh
  2.0; mc_paths >= 100 (mac dinh 10000); mc_horizon_days > 0 (mac
  dinh 1); stress_scenarios [{name, shocks: {SYMBOL: shock_pct}}].
  Symbol la trong scenario -> ValueError LOUD (chi 10 symbol quen).
- weights_usd o cac ham VaR la NOTIONAL USD CO DAU theo symbol
  (dict {symbol: signed_notional} hoac list), KHONG phai ty trong
  0..1; cov la dict long nhau {s: {t: float}} (covariance_matrix tra
  dang nay, hiep phuong sai MAU chia n-1).
- cholesky(matrix) nhan dict long nhau hoac list 2 chieu, tra cung
  dang; ma tran khong xac dinh duong thi thu jitter roi ValueError.
- log_returns_from_store(store, symbols, timeframe="M15", limit=None)
  tra (timestamps, {symbol: [log return]}) — inner-join tren
  timestamp chung cua moi symbol.
- correlation_matrix(cov) nhan dict hiep phuong sai, tra dict tuong
  quan long nhau.
- parametric_var(weights_usd, cov, confidence=0.95) tra tuple
  (var_usd, cvar_usd); historical_var(portfolio_returns,
  confidence=0.95) tra tuple (var, cvar) CUNG DON VI voi dau vao
  (return phan so -> phan so, P&L USD -> USD), < 2 ky -> (0.0, 0.0).
- monte_carlo_var(weights_usd, cov, n_paths=10000, horizon_days=1,
  seed=42, equity_usd=None, max_drawdown_pct=10.0) tra dict co
  var_95/cvar_95/mean_pnl/sd_pnl/p5/p50/p95/paths/seed/horizon_days/
  prob_breach_drawdown_pct (None neu khong biet equity); cov M15
  scale len ngay bang 96*horizon_days (phuong sai).
- component_var(weights_usd, cov, var_usd) tra list[{symbol, var_usd,
  share_pct}] (Euler, tong = var_usd truyen vao).
- apply_stress(exposures, shocks) tra (pnl_usd, {symbol: pnl_usd});
  co breach_drawdown CHI co o muc bao cao (pnl <= -gioi han drawdown).
- load_stress_scenarios(cfg) tra list [{name, shocks}];
  validate_portfolio_risk_config(cfg) tra True, raise ValueError khi
  cau hinh sai.
- build_portfolio_risk_report: khong vi the + khong demo -> VaR 0.0,
  warning "khong co vi the mo"; co vi the nhung thieu lich su chung
  (>= 2 ky) -> cac muc VaR la None kem warning "khong co du lich su
  gia chung"; VaR bao cao quy ve 1 ngay bang sqrt(96*horizon_days)
  (ca 3 cach tinh, cung chan); demo=True lap danh muc gia 10 symbol
  can deu equity/10, gia lay tu store (thieu gia thi bo symbol do);
  stress them 1 dong "Ngay te nhat lich su" khi du lich su.
- Notional vi the tinh theo quy uoc repo (muc 10 trading-principles):
  volume(lot) x contract_size x gia — forex 100000, XAUUSD 100.
- Neu module chua ha canh, cac test can module se SKIP (khong fail);
  test muc bao cao ngay khong co vi the + test CLI xu ly thieu module
  rieng. Khong dung MT5 that, khong dung mang; chi tmp HistoryStore
  + vi the gia. Test CLI subprocess dung config/store THAT cua repo:
  data/history.db hien chua co bar nao nen demo khong dinh gia duoc
  -> chi khang dinh rc 0 + dong VaR + canh bao thoai hoa, con dong
  stress khang dinh o test in-process co store gia.
"""
import math
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.data.history import HistoryStore  # noqa: E402
from diamondx10.report import build_report, format_report  # noqa: E402

try:
    from diamondx10 import portfolio_risk as pr
except ImportError:
    pr = None

NEED_PR = pytest.mark.skipif(
    pr is None, reason="module portfolio_risk chua ha canh (worker song song)")

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_EPOCH = 1_700_000_000  # moc thoi gian co dinh cho bar gia (UTC)

# --- Cau hinh mau -------------------------------------------------------

STRESS_SCENARIOS = [
    {"name": "Crypto crash",
     "shocks": {"BTCUSD": -30, "ETHUSD": -30, "BNBUSD": -30}},
    {"name": "Vang giam manh", "shocks": {"XAUUSD": -10}},
    {"name": "Vang tang manh", "shocks": {"XAUUSD": 10}},
    {"name": "USD manh len", "shocks": {"EURUSD": -2}},
    {"name": "Euro sup do", "shocks": {"EURUSD": -100}},
]


def _cfg(**risk_overrides):
    """Cfg toi thieu giong cau truc config.example.yaml."""
    risk = {
        "max_drawdown_pct": 10.0,
        "desk_warning_pct": 5.0,
        "portfolio_var_limit_pct": 2.0,
        "mc_paths": 2000,
        "mc_horizon_days": 1,
        "stress_scenarios": list(STRESS_SCENARIOS),
    }
    risk.update(risk_overrides)
    return {
        "fund": {
            "total_capital_usd": 10000,
            "desks": {
                "forex": {"manager": "Yuling Pan", "capital_usd": 2500},
                "xauusd": {"manager": "Yumi", "capital_usd": 2500},
                "crypto": {"manager": "Rich", "capital_usd": 2500},
                "us_securities": {"manager": "Kathy", "capital_usd": 2500},
            },
        },
        "risk": risk,
        "data": {"symbols": {
            "forex": ["EURUSD"], "xauusd": ["XAUUSD"],
            "crypto": ["BTCUSD", "BNBUSD", "ETHUSD"],
            "us_securities": ["AMD", "CDNS", "SNPS", "INTC", "NVDA"]}},
        "history": {"db_path": "data/history.db"},
    }


def _eur_position(volume=0.01, direction="BUY", price=1.16):
    return {"desk": "forex", "symbol": "EURUSD", "direction": direction,
            "entry": price, "sl": price - 0.01, "tp": price + 0.02,
            "volume": volume, "contract_size": 100000,
            "opened_date": "2026-11-27"}


def _xau_position(volume=0.01, direction="SELL", price=5000.0):
    return {"desk": "xauusd", "symbol": "XAUUSD", "direction": direction,
            "entry": price, "sl": price + 50.0, "tp": price - 100.0,
            "volume": volume, "contract_size": 100,
            "opened_date": "2026-11-27"}


# --- Seed kho lich su gia -----------------------------------------------

def _seed_bars(store, symbol, closes, start=BASE_EPOCH, step=900):
    """Ghi bar OHLC (open=high=low=close) tu list gia dong."""
    bars = [{"time": start + i * step, "open": c, "high": c,
             "low": c, "close": c, "volume": 0.0}
            for i, c in enumerate(closes)]
    store.upsert_bars(symbol, "M15", bars)
    return bars


def _seed_alternating(store, symbol, base_price, n_bars=21):
    """21 bar -> 20 log return luan phien chinh xac +0.02 / -0.02.

    Tong log return luan phien 0, +0.02, 0, +0.02, ... nen do lech
    chuan (population) = 0.02 chinh xac; do lech chuan mau (N-1) =
    0.02*sqrt(20/19) = 0.02052. Bar cuoi ve dung gia goc.
    """
    closes = [base_price * math.exp(0.02 if i % 2 else 0.0)
              for i in range(n_bars)]
    return _seed_bars(store, symbol, closes)


def _tmp_store(tmp_path, name="history.db"):
    return HistoryStore(str(tmp_path / name))


# --- Bo chuan hoa ket qua (chap nhan 2 dang tra ve hop ly) ---------------

def _var_pair(result):
    """(var_95, cvar_95) tu dict {"var_95"/"var", "cvar_95"/"cvar"}
    hoac tuple/list (var, cvar)."""
    if isinstance(result, dict):
        var = result.get("var_95", result.get("var"))
        cvar = result.get("cvar_95", result.get("cvar"))
        return float(var), float(cvar)
    var, cvar = result
    return float(var), float(cvar)


def _strip(text):
    """Bo dau tieng Viet + lower, de so sanh text bao cao thoai hoa."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed
                   if unicodedata.category(c) != "Mn").lower()


def _assert_report_shape(rep):
    """Moi khoa hop dong phai co trong bao cao (muc build_report)."""
    for key in ("has_positions", "demo", "equity_usd", "symbols",
                "exposures", "var", "mc", "component_var",
                "concentration", "stress", "warnings", "notes"):
        assert key in rep, f"thieu khoa bao cao: {key}"
    for key in ("parametric_95", "parametric_cvar_95", "historical_95",
                "historical_cvar_95", "mc_95", "mc_cvar_95",
                "limit_usd", "limit_pct", "breached"):
        assert key in rep["var"], f"thieu khoa var: {key}"
    for key in ("paths", "seed", "horizon_days", "mean_pnl", "sd_pnl",
                "p5", "p50", "p95", "prob_breach_drawdown_pct"):
        assert key in rep["mc"], f"thieu khoa mc: {key}"
    for key in ("largest_symbol", "largest_share_pct"):
        assert key in rep["concentration"], f"thieu khoa concentration: {key}"


# --- 1. Cholesky ---------------------------------------------------------

@NEED_PR
def test_cholesky_2x2_known_matrix():
    # M = [[4, 2], [2, 3]] -> L = [[2, 0], [1, sqrt(2)]]:
    # l11 = sqrt(4) = 2; l21 = 2/2 = 1; l22 = sqrt(3 - 1) = sqrt(2).
    L = pr.cholesky([[4.0, 2.0], [2.0, 3.0]])
    assert L[0][0] == pytest.approx(2.0)
    assert L[0][1] == pytest.approx(0.0)
    assert L[1][0] == pytest.approx(1.0)
    assert L[1][1] == pytest.approx(math.sqrt(2.0))
    # L * L' phai tra lai M.
    assert L[0][0] ** 2 == pytest.approx(4.0)
    assert L[1][0] * L[0][0] == pytest.approx(2.0)
    assert L[1][0] ** 2 + L[1][1] ** 2 == pytest.approx(3.0)


@NEED_PR
def test_cholesky_3x3_reconstructs_matrix():
    # M = [[4,2,0],[2,5,1],[0,1,3]] -> L = [[2,0,0],[1,2,0],
    # [0,0.5,sqrt(2.75)]]: l32 = (1 - 1*0)/2 = 0.5;
    # l33 = sqrt(3 - 0.25) = sqrt(2.75).
    M = [[4.0, 2.0, 0.0], [2.0, 5.0, 1.0], [0.0, 1.0, 3.0]]
    L = pr.cholesky(M)
    assert L[0] == pytest.approx([2.0, 0.0, 0.0])
    assert L[1] == pytest.approx([1.0, 2.0, 0.0])
    assert L[2] == pytest.approx([0.0, 0.5, math.sqrt(2.75)])
    for i in range(3):
        for j in range(3):
            assert sum(L[i][k] * L[j][k] for k in range(3)) == pytest.approx(M[i][j])


@NEED_PR
def test_cholesky_non_positive_definite_raises():
    # [[1, 2], [2, 1]] co dinh thuc -3 -> khong co Cholesky that.
    with pytest.raises(ValueError):
        pr.cholesky([[1.0, 2.0], [2.0, 1.0]])


# --- 2. VaR tham so — tinh tay --------------------------------------------

@NEED_PR
def test_parametric_var_two_assets_hand_computed():
    # weights_usd la NOTIONAL USD CO DAU (khong phai ty trong):
    # EURUSD 6000, XAUUSD 4000; sigma1 = 0.02, sigma2 = 0.03, rho = 0.5
    # -> cov12 = 0.5*0.02*0.03 = 0.0003.
    # Var_p (USD^2) = 6000^2*0.0004 + 4000^2*0.0009
    #                 + 2*6000*4000*0.0003
    #               = 14400 + 14400 + 14400 = 43200.
    # sigma_p = sqrt(43200) = 207.846 USD.
    # VaR95 = 1.645 * sigma_p = 341.91 USD.
    # CVaR95 = sigma_p * phi(1.645)/0.05 = 428.62 USD,
    # voi phi(1.645) = 0.10311 (mat do chuan tai z=1.645).
    cov = {"EURUSD": {"EURUSD": 0.0004, "XAUUSD": 0.0003},
           "XAUUSD": {"EURUSD": 0.0003, "XAUUSD": 0.0009}}
    weights = {"EURUSD": 6000.0, "XAUUSD": 4000.0}
    var95, cvar95 = _var_pair(pr.parametric_var(weights, cov))
    assert var95 == pytest.approx(341.91, rel=1e-3)
    assert cvar95 == pytest.approx(428.62, rel=0.02)
    assert cvar95 >= var95  # duoi phan phoi luon te hon VaR.


@NEED_PR
def test_parametric_var_confidence_99_bigger_than_95():
    cov = {"EURUSD": {"EURUSD": 0.0004, "XAUUSD": 0.0003},
           "XAUUSD": {"EURUSD": 0.0003, "XAUUSD": 0.0009}}
    weights = {"EURUSD": 6000.0, "XAUUSD": 4000.0}
    var95, _ = _var_pair(pr.parametric_var(weights, cov, confidence=0.95))
    var99, cvar99 = _var_pair(pr.parametric_var(weights, cov,
                                                confidence=0.99))
    # VaR99 = 2.33 * sqrt(43200) = 484.28 USD.
    assert var99 == pytest.approx(484.28, rel=1e-3)
    assert var99 > var95
    assert cvar99 >= var99


# --- 3. VaR lich su — tinh tay --------------------------------------------

@NEED_PR
def test_historical_var_tiny_fixed_list():
    # 20 gia tri: -0.10 ... -0.01, 0.01 ... 0.10 (giong test_var.py).
    # Phan vi 5% noi suy tuyen tinh (giong risk._percentile):
    # rank = 0.05*19 = 0.95 -> -0.10*0.05 + -0.09*0.95 = -0.0905.
    # VaR95 = 0.0905 (phan so — cung don vi voi dau vao).
    # CVaR95 = trung binh cac lo <= -0.0905 -> chi -0.10 -> 0.10.
    # Cung list nhan voi 10000 (P&L USD) -> VaR 905.0, CVaR 1000.0 USD.
    returns = [-0.10, -0.09, -0.08, -0.07, -0.06, -0.05, -0.04, -0.03,
               -0.02, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07,
               0.08, 0.09, 0.10]
    var95, cvar95 = _var_pair(pr.historical_var(returns))
    assert var95 == pytest.approx(0.0905, rel=1e-6)
    assert cvar95 == pytest.approx(0.10, rel=1e-6)
    assert cvar95 >= var95
    var_usd, cvar_usd = _var_pair(
        pr.historical_var([r * 10000.0 for r in returns]))
    assert var_usd == pytest.approx(905.0, rel=1e-6)
    assert cvar_usd == pytest.approx(1000.0, rel=1e-6)


@NEED_PR
def test_historical_var_all_gains_is_zero():
    var95, cvar95 = _var_pair(pr.historical_var([0.01, 0.02, 0.03]))
    assert var95 == 0.0
    assert cvar95 == 0.0


@NEED_PR
def test_historical_var_too_few_returns_is_zero():
    # < 2 ky -> (0.0, 0.0), khong raise (khac risk.value_at_risk
    # tra None — day la hop dong rieng cua historical_var).
    assert pr.historical_var([]) == (0.0, 0.0)
    assert pr.historical_var([0.01]) == (0.0, 0.0)


# --- 4. Component VaR cong lai = VaR danh muc ------------------------------

@NEED_PR
def test_component_var_sums_to_portfolio_var():
    # Cung cov/weights nhu test parametric: component Euler
    #   CVaR_i = w_i * var_usd * (Sigma w)_i / (w' Sigma w).
    # (Sigma w) = [0.00036, 0.00054] (voi w USD 6000/4000) -> moi
    # phan = 170.95 USD, cong lai = 341.91 USD = VaR95 danh muc;
    # share moi phan = 50%.
    cov = {"EURUSD": {"EURUSD": 0.0004, "XAUUSD": 0.0003},
           "XAUUSD": {"EURUSD": 0.0003, "XAUUSD": 0.0009}}
    weights = {"EURUSD": 6000.0, "XAUUSD": 4000.0}
    comps = pr.component_var(weights, cov, 341.90682941409636)
    values = [c["var_usd"] for c in comps]
    assert values == pytest.approx([170.95, 170.95], rel=1e-3)
    assert sum(values) == pytest.approx(341.91, rel=1e-3)
    assert [c["share_pct"] for c in comps] == pytest.approx([50.0, 50.0],
                                                           rel=1e-3)
    assert [c["symbol"] for c in comps] == ["EURUSD", "XAUUSD"]


@NEED_PR
def test_component_var_report_sums_to_parametric_var(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    _seed_alternating(store, "XAUUSD", 5000.0)
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=500, store=store,
        positions=[_eur_position(), _xau_position()],
        prices={"EURUSD": 1.16, "XAUUSD": 5000.0})
    total = sum(float(c["var_usd"]) for c in rep["component_var"])
    assert total == pytest.approx(rep["var"]["parametric_95"], rel=0.05)
    shares = sum(float(c["share_pct"]) for c in rep["component_var"])
    assert shares == pytest.approx(100.0, rel=0.02)
    store.close()


# --- 5. Ma tran tuong quan / hiep phuong sai --------------------------------

@NEED_PR
def test_correlation_matrix_properties():
    # A luan phien +-0.01 (40 mau); B = A (tuong quan hoan hao +1);
    # C = -A (tuong quan hoan hao -1). correlation_matrix nhan
    # dict hiep phuong sai (khong nhan dict return truc tiep).
    series_a = [0.01 if i % 2 == 0 else -0.01 for i in range(40)]
    series_b = list(series_a)
    series_c = [-v for v in series_a]
    cov = pr.covariance_matrix({"A": series_a, "B": series_b,
                                "C": series_c})
    corr = pr.correlation_matrix(cov)
    for s in ("A", "B", "C"):
        assert corr[s][s] == pytest.approx(1.0, abs=1e-9)
    assert corr["A"]["B"] == pytest.approx(1.0, abs=1e-9)
    assert corr["A"]["C"] == pytest.approx(-1.0, abs=1e-9)
    for s in ("A", "B", "C"):
        for t in ("A", "B", "C"):
            assert corr[s][t] == pytest.approx(corr[t][s])  # doi xung


@NEED_PR
def test_covariance_matrix_hand_computed():
    # A luan phien +-0.01 (40 mau): phuong sai population = 0.0001,
    # phuong sai MAU (n-1, nhu code) = 0.0001*40/39 = 0.0001025641.
    # B = A -> cov(A,B) = var(A).
    series_a = [0.01 if i % 2 == 0 else -0.01 for i in range(40)]
    cov = pr.covariance_matrix({"A": series_a, "B": list(series_a)})
    assert cov["A"]["A"] == pytest.approx(0.0001 * 40 / 39, rel=1e-9)
    assert cov["A"]["B"] == pytest.approx(0.0001 * 40 / 39, rel=1e-9)
    assert cov["A"]["B"] == pytest.approx(cov["B"]["A"])


# --- 6. Log return tu kho ---------------------------------------------------

@NEED_PR
def test_log_returns_from_store_known_closes(tmp_path):
    store = _tmp_store(tmp_path)
    _seed_bars(store, "EURUSD", [100.0, 101.0, 100.0])
    # Tra (timestamps, {symbol: [returns]}), inner-join timestamp chung.
    timestamps, rets = pr.log_returns_from_store(store, ["EURUSD"])
    assert len(timestamps) == 2
    # ln(101/100) = 0.00995033; ln(100/101) = -0.00995033.
    assert rets["EURUSD"] == pytest.approx(
        [math.log(1.01), math.log(100 / 101)])
    store.close()


@NEED_PR
def test_log_returns_from_store_missing_symbol_no_crash(tmp_path):
    store = _tmp_store(tmp_path)  # kho rong
    timestamps, rets = pr.log_returns_from_store(store, ["EURUSD"])
    assert timestamps == []
    assert rets == {}
    store.close()


@NEED_PR
def test_log_returns_inner_join_common_timestamps(tmp_path):
    # EURUSD co bar o t=0,1,2; XAUUSD chi t=0,2 -> chi t=0,2 la chung,
    # return chi tinh tu cap chung lien ke (1 return).
    store = _tmp_store(tmp_path)
    _seed_bars(store, "EURUSD", [100.0, 101.0, 102.0],
               start=BASE_EPOCH)
    _seed_bars(store, "XAUUSD", [5000.0, 5100.0],
               start=BASE_EPOCH)
    # Xau bar thu 2 o t=BASE+900 (le) — xoa/ghi lai cho dung t=BASE+1800.
    store._conn.execute("DELETE FROM bars WHERE symbol='XAUUSD'")
    store._conn.commit()
    _seed_bars(store, "XAUUSD", [5000.0, 5100.0],
               start=BASE_EPOCH)
    store._conn.execute(
        "UPDATE bars SET time=? WHERE symbol='XAUUSD' AND time=?",
        (BASE_EPOCH + 1800, BASE_EPOCH + 900))
    store._conn.commit()
    timestamps, rets = pr.log_returns_from_store(store, ["EURUSD",
                                                         "XAUUSD"])
    assert len(timestamps) == 1
    assert rets["EURUSD"] == pytest.approx([math.log(102 / 100)])
    assert rets["XAUUSD"] == pytest.approx([math.log(5100 / 5000)])
    store.close()


# --- 7. Monte Carlo: tai lap -------------------------------------------------

@NEED_PR
def test_monte_carlo_same_seed_identical():
    cov = {"EURUSD": {"EURUSD": 0.0004, "XAUUSD": 0.0003},
           "XAUUSD": {"EURUSD": 0.0003, "XAUUSD": 0.0009}}
    weights = {"EURUSD": 6000.0, "XAUUSD": 4000.0}
    first = pr.monte_carlo_var(weights, cov, n_paths=2000,
                               horizon_days=1, seed=7,
                               equity_usd=10000.0)
    second = pr.monte_carlo_var(weights, cov, n_paths=2000,
                                horizon_days=1, seed=7,
                                equity_usd=10000.0)
    assert first["var_95"] == second["var_95"]
    assert first["cvar_95"] == second["cvar_95"]
    assert first["mean_pnl"] == second["mean_pnl"]
    assert first["p5"] == second["p5"]
    assert first["paths"] == 2000
    assert first["seed"] == 7
    assert 0.0 <= first["prob_breach_drawdown_pct"] <= 100.0


@NEED_PR
def test_monte_carlo_different_seed_differs():
    cov = {"EURUSD": {"EURUSD": 0.0004, "XAUUSD": 0.0003},
           "XAUUSD": {"EURUSD": 0.0003, "XAUUSD": 0.0009}}
    weights = {"EURUSD": 6000.0, "XAUUSD": 4000.0}
    a = pr.monte_carlo_var(weights, cov, n_paths=2000,
                           horizon_days=1, seed=7, equity_usd=10000.0)
    b = pr.monte_carlo_var(weights, cov, n_paths=2000,
                           horizon_days=1, seed=123, equity_usd=10000.0)
    # Hai seed khac nhau gan nhu chac chan cho VaR khac nhau.
    assert a["var_95"] != b["var_95"]
    # MC scale cov M15 len 1 ngay (x96 phuong sai): sigma ngay =
    # sqrt(43200*96) = 2036.47 USD -> VaR95 ~ 1.645*2036.47 = 3350 USD.
    assert a["var_95"] == pytest.approx(3350.0, rel=0.15)
    assert a["cvar_95"] >= a["var_95"]


@NEED_PR
def test_monte_carlo_prob_breach_none_without_equity():
    cov = {"EURUSD": {"EURUSD": 0.0004, "XAUUSD": 0.0003},
           "XAUUSD": {"EURUSD": 0.0003, "XAUUSD": 0.0009}}
    out = pr.monte_carlo_var({"EURUSD": 6000.0, "XAUUSD": 4000.0},
                             cov, n_paths=500, horizon_days=1, seed=7)
    assert out["prob_breach_drawdown_pct"] is None
    with pytest.raises(ValueError):
        pr.monte_carlo_var({"EURUSD": 6000.0}, cov, n_paths=0)
    with pytest.raises(ValueError):
        pr.monte_carlo_var({"EURUSD": 6000.0}, cov, horizon_days=0)


@NEED_PR
def test_report_mc_deterministic_across_calls(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    kwargs = dict(mc_paths=500, store=store,
                  positions=[_eur_position()], prices={"EURUSD": 1.16})
    rep1 = pr.build_portfolio_risk_report(cfg, **kwargs)
    rep2 = pr.build_portfolio_risk_report(cfg, **kwargs)
    assert rep1["mc"] == rep2["mc"]
    assert rep1["var"]["mc_95"] == rep2["var"]["mc_95"]
    assert isinstance(rep1["mc"]["seed"], int)
    store.close()


# --- 8. Stress: P&L = exposure x shock ---------------------------------------

@NEED_PR
def test_apply_stress_math():
    # apply_stress tra (pnl_usd, {symbol: pnl_usd}); co breach
    # drawdown CHI co o muc bao cao (build_portfolio_risk_report),
    # khong co o ham thuan nay.
    exposures = [
        {"symbol": "EURUSD", "desk": "forex", "direction": "BUY",
         "volume": 0.01, "price": 1.16, "notional_usd": 10000.0,
         "signed_notional_usd": 10000.0},
        {"symbol": "XAUUSD", "desk": "xauusd", "direction": "SELL",
         "volume": 0.01, "price": 5000.0, "notional_usd": 5000.0,
         "signed_notional_usd": -5000.0},
    ]
    # EURUSD -20% tren +10000 = -2000; XAUUSD -10% tren -5000 (SELL)
    # = +500. Tong -1500 USD.
    total, per_symbol = pr.apply_stress(
        exposures, {"EURUSD": -20, "XAUUSD": -10})
    assert total == pytest.approx(-1500.0)
    assert per_symbol["EURUSD"] == pytest.approx(-2000.0)
    assert per_symbol["XAUUSD"] == pytest.approx(500.0)
    # Shock tren symbol khong co exposure thi bo qua (pnl 0).
    total2, per2 = pr.apply_stress(exposures, {"BTCUSD": -30})
    assert total2 == pytest.approx(0.0)
    assert per2 == {}
    # Khong co signed_notional_usd: suy dau tu direction + notional.
    total3, _ = pr.apply_stress(
        [{"symbol": "EURUSD", "direction": "SELL",
          "notional_usd": 10000.0}], {"EURUSD": -20})
    assert total3 == pytest.approx(2000.0)  # SELL lai khi gia giam


@NEED_PR
def test_report_stress_from_own_exposures(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    _seed_alternating(store, "XAUUSD", 5000.0)
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=500, store=store,
        positions=[_eur_position(), _xau_position()],
        prices={"EURUSD": 1.16, "XAUUSD": 5000.0})
    # Notional theo quy uoc repo: EURUSD 0.01*100000*1.16 = 1160 (BUY
    # -> +1160); XAUUSD 0.01*100*5000 = 5000 (SELL -> -5000).
    exp = {e["symbol"]: e for e in rep["exposures"]}
    assert exp["EURUSD"]["notional_usd"] == pytest.approx(1160.0, rel=0.02)
    assert exp["EURUSD"]["signed_notional_usd"] == pytest.approx(1160.0,
                                                                 rel=0.02)
    assert exp["XAUUSD"]["notional_usd"] == pytest.approx(5000.0, rel=0.02)
    assert exp["XAUUSD"]["signed_notional_usd"] == pytest.approx(-5000.0,
                                                                 rel=0.02)
    stress = {s["name"]: s for s in rep["stress"]}
    # "Vang giam manh" XAUUSD -10%: SELL -5000 * -0.10 = +500 USD (+5%).
    gold_down = stress["Vang giam manh"]
    assert gold_down["pnl_usd"] == pytest.approx(500.0, rel=0.01)
    assert gold_down["pnl_pct"] == pytest.approx(5.0, rel=0.01)
    assert gold_down["breaches_drawdown"] is False
    # "Vang tang manh" XAUUSD +10%: SELL -5000 * +0.10 = -500 USD.
    assert stress["Vang tang manh"]["pnl_usd"] == pytest.approx(-500.0,
                                                                rel=0.01)
    # "Crypto crash": khong giu crypto nao -> P&L 0.
    assert stress["Crypto crash"]["pnl_usd"] == pytest.approx(0.0)
    # Tap trung: XAUUSD 5000/6160 = 81.17% danh muc.
    assert rep["concentration"]["largest_symbol"] == "XAUUSD"
    assert rep["concentration"]["largest_share_pct"] == pytest.approx(
        5000 / 6160 * 100, rel=0.01)
    assert set(rep["symbols"]) == {"EURUSD", "XAUUSD"}
    store.close()


@NEED_PR
def test_report_stress_breach_flag(tmp_path):
    # 1.0 lot EURUSD BUY @1.16 -> notional 116000; shock -100% ->
    # P&L -116000 USD = -1160% von -> vuot drawdown 10%, VaR cung
    # vuot gioi han 2% (200 USD).
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=500, store=store,
        positions=[_eur_position(volume=1.0)], prices={"EURUSD": 1.16})
    stress = {s["name"]: s for s in rep["stress"]}
    worst = stress["Euro sup do"]
    assert worst["pnl_usd"] == pytest.approx(-116000.0, rel=0.02)
    assert worst["breaches_drawdown"] is True
    assert rep["var"]["breached"] is True
    store.close()


# --- 9. Bao cao: khong vi the / demo / thieu lich su --------------------------

@NEED_PR
def test_report_no_positions_no_history(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)  # kho rong
    rep = pr.build_portfolio_risk_report(cfg, store=store, positions=[])
    _assert_report_shape(rep)
    assert rep["has_positions"] is False
    assert rep["demo"] is False
    assert rep["equity_usd"] == pytest.approx(10000.0)
    assert rep["symbols"] == []
    assert rep["exposures"] == []
    assert rep["component_var"] == []
    for key in ("parametric_95", "parametric_cvar_95", "historical_95",
                "historical_cvar_95", "mc_95", "mc_cvar_95"):
        assert rep["var"][key] == 0.0
    assert rep["var"]["breached"] is False
    assert "khong co vi the mo" in " ".join(rep["warnings"]).lower()
    assert all(float(s["pnl_usd"]) == 0.0 for s in rep["stress"])
    store.close()


@NEED_PR
def test_report_no_positions_explicit_empty(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    rep = pr.build_portfolio_risk_report(cfg, store=store,
                                         positions=[], prices=None)
    assert rep["has_positions"] is False
    assert rep["var"]["parametric_95"] == 0.0
    store.close()


@NEED_PR
def test_report_positions_but_no_history_degrades(tmp_path):
    # Co vi the nhung kho rong -> cac muc VaR la None (khong phai 0.0),
    # kem warning "khong co du lich su gia chung", khong raise.
    cfg = _cfg()
    store = _tmp_store(tmp_path)  # kho rong, nhung co vi the
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=500, store=store,
        positions=[_eur_position()], prices={"EURUSD": 1.16})
    _assert_report_shape(rep)
    assert rep["has_positions"] is True
    assert rep["var"]["parametric_95"] is None
    assert rep["var"]["historical_95"] is None
    assert rep["var"]["mc_95"] is None
    assert rep["mc"]["paths"] == 500
    assert any("khong co du lich su" in w for w in rep["warnings"])
    # Stress van tinh duoc (khong can lich su): EURUSD -2% tren +1160.
    stress = {s["name"]: s for s in rep["stress"]}
    assert stress["USD manh len"]["pnl_usd"] == pytest.approx(-23.2,
                                                             rel=0.01)
    store.close()


@NEED_PR
def test_report_single_position_var_relationships(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=2000, store=store,
        positions=[_eur_position()], prices={"EURUSD": 1.16})
    _assert_report_shape(rep)
    assert rep["has_positions"] is True
    assert rep["equity_usd"] == pytest.approx(10000.0)
    # Gioi han VaR theo config: 2% von quy = 200 USD.
    assert rep["var"]["limit_pct"] == pytest.approx(2.0)
    assert rep["var"]["limit_usd"] == pytest.approx(200.0)
    var = rep["var"]
    assert var["parametric_95"] > 0
    assert var["parametric_cvar_95"] >= var["parametric_95"]
    assert var["historical_95"] > 0
    assert var["historical_cvar_95"] >= var["historical_95"]
    assert var["mc_95"] > 0
    assert var["mc_cvar_95"] >= var["mc_95"]
    # So tuyet doi tinh tay (return luan phien +-0.02, notional 1160):
    # hiep phuong sai MAU (n-1, 20 mau) = 0.02^2*20/19 = 0.00042105,
    # sigma_p = 1160*sqrt(0.00042105) = 23.80 USD/ky M15.
    # VaR tham so 95% 1 ngay = 1.645*23.80*sqrt(96) = 383.6 USD.
    assert 370.0 < var["parametric_95"] < 395.0
    # VaR lich su: P&L danh muc luan phien +-23.2 USD -> phan vi 5%
    # = -23.2 -> VaR 1 ngay = 23.2*sqrt(96) = 227.31 USD; CVaR bang
    # VaR vi moi khoan lo trong duoi deu = -23.2.
    assert var["historical_95"] == pytest.approx(227.31, rel=0.02)
    assert var["historical_cvar_95"] == pytest.approx(227.31, rel=0.02)
    assert rep["mc"]["paths"] == 2000
    assert rep["mc"]["horizon_days"] == 1
    assert rep["mc"]["p5"] <= rep["mc"]["p50"] <= rep["mc"]["p95"]
    assert 0.0 <= rep["mc"]["prob_breach_drawdown_pct"] <= 100.0
    store.close()


@NEED_PR
def test_report_var_methods_share_horizon(tmp_path):
    # Ca 3 cach tinh VaR phai noi ve cung chan (mac dinh 1 ngay):
    # parametric gan MC (cung gia dinh chuan), lich su cung bac do
    # (cho phep lech do scale M15->ngay hoac do duoi phan phoi that).
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=5000, store=store,
        positions=[_eur_position()], prices={"EURUSD": 1.16})
    var = rep["var"]
    assert var["parametric_95"] / var["mc_95"] == pytest.approx(1.0, rel=0.3)
    # parametric/historical = 1.645*sigma_mau/0.02 = 1.645*0.02052/0.02
    # = 1.687 (tham so dung do lech chuan mau, lich su dung phan vi).
    assert var["parametric_95"] / var["historical_95"] == pytest.approx(
        1.687, rel=0.05)
    store.close()


@NEED_PR
def test_report_demo_mode_returns_full_shape(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    rep = pr.build_portfolio_risk_report(cfg, mc_paths=500, demo=True,
                                         store=store)
    _assert_report_shape(rep)
    assert rep["demo"] is True
    if rep["has_positions"]:
        assert rep["var"]["parametric_95"] >= 0
        assert rep["var"]["mc_95"] >= 0
    store.close()


# --- 10. Kiem tra cau hinh ---------------------------------------------------

@NEED_PR
def test_validate_config_accepts_valid():
    pr.validate_portfolio_risk_config(_cfg())


@NEED_PR
def test_validate_config_rejects_unknown_symbol_in_scenario():
    cfg = _cfg(stress_scenarios=[
        {"name": "La", "shocks": {"NOPEUSD": -10}}])
    with pytest.raises(ValueError):
        pr.validate_portfolio_risk_config(cfg)


@NEED_PR
def test_validate_config_rejects_negative_mc_paths():
    with pytest.raises(ValueError):
        pr.validate_portfolio_risk_config(_cfg(mc_paths=-5))


@NEED_PR
def test_validate_config_rejects_nonpositive_var_limit():
    with pytest.raises(ValueError):
        pr.validate_portfolio_risk_config(_cfg(portfolio_var_limit_pct=0.0))
    with pytest.raises(ValueError):
        pr.validate_portfolio_risk_config(_cfg(portfolio_var_limit_pct=-1.0))


@NEED_PR
def test_validate_config_rejects_nonpositive_horizon():
    with pytest.raises(ValueError):
        pr.validate_portfolio_risk_config(_cfg(mc_horizon_days=0))


@NEED_PR
def test_load_stress_scenarios_round_trip():
    scenarios = pr.load_stress_scenarios(_cfg())
    names = [s["name"] for s in scenarios]
    assert "Crypto crash" in names
    assert "Vang giam manh" in names
    crypto = next(s for s in scenarios if s["name"] == "Crypto crash")
    assert crypto["shocks"] == {"BTCUSD": -30, "ETHUSD": -30,
                                "BNBUSD": -30}


@NEED_PR
def test_build_rejects_small_mc_paths_kwarg(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    # Gioi han cung: mc_paths >= 100 (ca am lan duoi 100 deu ValueError).
    with pytest.raises(ValueError):
        pr.build_portfolio_risk_report(cfg, mc_paths=-100, store=store)
    with pytest.raises(ValueError):
        pr.build_portfolio_risk_report(cfg, mc_paths=50, store=store)
    store.close()


# --- 11. Dinh dang bao cao -----------------------------------------------------

@NEED_PR
def test_format_report_contains_var_and_stress(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    _seed_alternating(store, "XAUUSD", 5000.0)
    rep = pr.build_portfolio_risk_report(
        cfg, mc_paths=500, store=store,
        positions=[_eur_position(), _xau_position()],
        prices={"EURUSD": 1.16, "XAUUSD": 5000.0})
    text = pr.format_portfolio_risk_report(rep)
    assert "VaR" in text
    assert "EURUSD" in text
    assert "stress" in _strip(text)
    store.close()


@NEED_PR
def test_format_empty_report_mentions_no_positions(tmp_path):
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    rep = pr.build_portfolio_risk_report(cfg, store=store, positions=[])
    text = pr.format_portfolio_risk_report(rep)
    assert "khong co vi the mo" in _strip(text)
    store.close()


# --- 12. CLI: portfolio-risk --demo --------------------------------------------

def test_cli_portfolio_risk_demo_subprocess():
    """Khoi dong that qua `python -m diamondx10 portfolio-risk --demo`.

    Neu module chua ha canh thi lenh tra 1 kem dong "chua co module
    portfolio_risk" -> SKIP (khong phai loi). Khi module da co thi
    phai tra 0 va in dong VaR. Dong stress CHI co khi demo dinh gia
    duoc it nhat 1 symbol — kho that data/history.db hien chua co bar
    nao nen demo tren may nay ve trang thai rong thoai hoa (canh bao
    "khong co gia"); dong stress khang dinh chac o test in-process
    test_cli_cmd_portfolio_risk_in_process (store gia co bar).
    """
    env = {"PYTHONPATH": str(REPO_ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "diamondx10", "portfolio-risk",
         "--demo", "--mc", "200"],
        cwd=str(REPO_ROOT), env={**__import__("os").environ, **env},
        capture_output=True, text=True, timeout=180)
    out = proc.stdout + proc.stderr
    if "chua co module portfolio_risk" in out:
        pytest.skip("module portfolio_risk chua ha canh — CLI cho san")
    assert proc.returncode == 0, out
    assert "VaR" in out
    assert ("stress" in out.lower()
            or "khong co gia" in _strip(out))


@NEED_PR
def test_cli_cmd_portfolio_risk_in_process(tmp_path, capsys):
    from diamondx10.__main__ import cmd_portfolio_risk
    cfg = _cfg()
    store = _tmp_store(tmp_path)
    _seed_alternating(store, "EURUSD", 1.16)
    rc = cmd_portfolio_risk(cfg, mc_paths=200, demo=True, store=store)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "VaR" in out
    assert "stress" in out.lower()
    store.close()


# --- 13. Muc rui ro danh muc trong bao cao ngay --------------------------------

def _report_cfg():
    return {
        "fund": {"total_capital_usd": 10000, "desks": {
            "forex": {"manager": "Yuling Pan", "capital_usd": 2500},
            "xauusd": {"manager": "Yumi", "capital_usd": 2500},
            "crypto": {"manager": "Rich", "capital_usd": 2500},
            "us_securities": {"manager": "Kathy", "capital_usd": 2500}}},
        "risk": {"max_drawdown_pct": 10.0, "desk_warning_pct": 5.0,
                 "portfolio_var_limit_pct": 2.0, "mc_paths": 500,
                 "mc_horizon_days": 1,
                 "stress_scenarios": list(STRESS_SCENARIOS)},
    }


def test_build_report_section_no_positions(tmp_path):
    """Khong co vi the -> muc rong ngay, khong can module."""
    log_path = tmp_path / "decisions-log.csv"
    log_path.write_text("date,desk,symbol,action,reason,manager\n",
                        encoding="utf-8")
    rep = build_report(_report_cfg(), log_path=log_path,
                       state_path=tmp_path / "no-state.json")
    section = rep["portfolio_risk"]
    assert section["available"] is True
    assert section["has_positions"] is False
    assert section["warnings"] == ["khong co vi the mo"]
    text = format_report(rep)
    assert "Rui ro danh muc" in text
    assert "khong co vi the mo" in text


def test_build_report_section_with_positions_graceful(tmp_path):
    """Co vi the: module chua co -> available False (khong crash);
    module da co -> bao cao day du."""
    import json
    log_path = tmp_path / "decisions-log.csv"
    log_path.write_text("date,desk,symbol,action,reason,manager\n",
                        encoding="utf-8")
    state = {
        "guard": {
            "fund_capital": 10000.0,
            "desk_capitals": {"forex": 2500.0, "xauusd": 2500.0,
                              "crypto": 2500.0, "us_securities": 2500.0},
            "max_drawdown_pct": 10.0, "desk_warning_pct": 5.0,
            "fund_curve": [10000.0],
            "desk_curves": {"forex": [2500.0], "xauusd": [2500.0],
                            "crypto": [2500.0], "us_securities": [2500.0]},
        },
        "positions": [_eur_position()],
    }
    state_path = tmp_path / "equity-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    rep = build_report(_report_cfg(), log_path=log_path,
                       state_path=state_path)
    section = rep["portfolio_risk"]
    # Muc bao cao ngay mo kho THAT data/history.db de dinh gia — kho
    # nay hien chua co bar EURUSD nao nen vi the bi bo qua kem warning
    # "khong co gia" (thoai hoa dung, khong crash). Neu may da backfill
    # thi muc phai co vi the + VaR day du.
    assert section["available"] is True
    assert "has_positions" in section
    if section["has_positions"]:
        assert section["var"]["parametric_95"] is not None
        assert section["var"]["parametric_95"] >= 0
    else:
        assert any("khong co gia" in w for w in section["warnings"])
    text = format_report(rep)
    assert "Rui ro danh muc" in text
