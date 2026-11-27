"""Test VaR/CVaR lich su (merge tu DiamondX10, portfolio_risk.py):
ham thuan + xuat hien trong compute_metrics cua backtest."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.backtest import compute_metrics
from diamondx10.risk import expected_shortfall, value_at_risk


def test_var_known_series():
    # 20 gia tri: -0.10 ... -0.01, 0.01 ... 0.10. Quantile 5%
    # (noi suy tuyen tinh, giong numpy percentile) nam gan -0.0955.
    returns = [-0.10, -0.09, -0.08, -0.07, -0.06, -0.05, -0.04, -0.03,
               -0.02, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07,
               0.08, 0.09, 0.10]
    var = value_at_risk(returns, confidence=0.95)
    assert var is not None
    assert 0.09 < var < 0.10
    cvar = expected_shortfall(returns, confidence=0.95)
    assert cvar is not None
    # CVaR = trung binh cac lo vuot VaR -> >= VaR.
    assert cvar >= var


def test_var_all_gains_is_zero():
    # Khong co lo nao trong lich su: VaR = 0 (khac ban goc dung abs(),
    # se tra so duong — xem docstring cua value_at_risk).
    assert value_at_risk([0.01, 0.02, 0.03]) == 0.0
    assert expected_shortfall([0.01, 0.02, 0.03]) == 0.0


def test_var_too_few_returns_none():
    assert value_at_risk([0.01]) is None
    assert value_at_risk([]) is None
    assert expected_shortfall([0.01]) is None
    assert expected_shortfall([]) is None


def test_var_confidence_99_bigger_than_95():
    returns = [-0.05, -0.04, -0.03, -0.02, -0.01] * 10
    var95 = value_at_risk(returns, confidence=0.95)
    var99 = value_at_risk(returns, confidence=0.99)
    assert var95 is not None and var99 is not None
    assert var99 >= var95


def test_compute_metrics_has_var_cvar():
    # Du 20 lenh thua lo deu -> equity giam dan, VaR/CVaR co gia tri.
    trades = [{"pnl": -10.0, "exit_time": i} for i in range(25)]
    equity = [2500.0]
    for t in trades:
        equity.append(equity[-1] - 10.0)
    metrics = compute_metrics(trades, equity, 2500.0)
    assert "var_95_pct" in metrics
    assert "cvar_95_pct" in metrics
    assert metrics["var_95_pct"] is not None
    assert metrics["cvar_95_pct"] is not None
    assert metrics["cvar_95_pct"] >= metrics["var_95_pct"]


def test_compute_metrics_var_none_when_short():
    # It hon 20 lenh -> VaR/CVaR None (giong guard <20 cua ban goc).
    trades = [{"pnl": -10.0, "exit_time": i} for i in range(5)]
    equity = [2500.0 - 10.0 * i for i in range(6)]
    metrics = compute_metrics(trades, equity, 2500.0)
    assert metrics["var_95_pct"] is None
    assert metrics["cvar_95_pct"] is None
