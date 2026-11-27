"""Test macro edge (merge tu DiamondX10, bo phep nhan -1 cho VIX cua
ban goc — xem models/macro.py). Ham thuan, khong can du lieu live."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.models.macro import macro_edge


def test_gold_usd_strong_is_bearish():
    # DXY cao hon diem giua nhieu (120 vs 100) -> vang chiu ap luc.
    edge = macro_edge("XAUUSD", dxy=120.0, us10y=3.5, vix=18.0, spx=4500.0)
    assert edge["symbol"] == "XAUUSD"
    assert edge["score"] < 0
    assert edge["edges"]["dxy"] < 0
    assert "Bearish" in edge["summary"] or "Neutral" in edge["summary"]


def test_gold_vix_high_is_bullish():
    # VIX cao (risk-off) -> vang huong loi: edge vix duong, theo dung
    # bang tuong quan (+0.40). Ban goc nhan -1 se cho dau nguoc — o day
    # phai duong.
    edge = macro_edge("XAUUSD", dxy=100.0, us10y=3.5, vix=43.0, spx=4500.0)
    assert edge["edges"]["vix"] > 0
    assert edge["score"] > 0


def test_eurusd_dxy_strong_is_bearish():
    edge = macro_edge("EURUSD", dxy=120.0, us10y=3.5, vix=18.0, spx=4500.0)
    assert edge["edges"]["dxy"] < 0
    assert edge["score"] < 0


def test_midpoints_neutral():
    # Tat ca o diem giua -> score 0, neutral.
    edge = macro_edge("XAUUSD", dxy=100.0, us10y=3.5, vix=18.0, spx=4500.0)
    assert edge["score"] == 0.0
    assert "Neutral" in edge["summary"]


def test_score_clamped():
    # Gia tri cuc doan van nam trong [-1, 1].
    edge = macro_edge("XAUUSD", dxy=200.0, us10y=15.0, vix=100.0,
                      spx=10000.0)
    assert -1.0 <= edge["score"] <= 1.0
    for value in edge["edges"].values():
        assert -1.0 <= value <= 1.0


def test_unknown_symbol_no_model():
    edge = macro_edge("BTCUSD", dxy=100.0, us10y=3.5, vix=18.0, spx=4500.0)
    assert edge["score"] == 0.0
    assert "Chua co mo hinh" in edge["summary"]


def test_missing_values_zero_edge():
    # Thieu snapshot -> edge 0, khong crash.
    edge = macro_edge("XAUUSD")
    assert edge["score"] == 0.0
    assert edge["edges"] == {"dxy": 0.0, "us10y": 0.0, "vix": 0.0, "spx": 0.0}


def test_us10y_high_bearish_for_gold():
    edge = macro_edge("XAUUSD", dxy=100.0, us10y=8.5, vix=18.0, spx=4500.0)
    assert edge["edges"]["us10y"] < 0
