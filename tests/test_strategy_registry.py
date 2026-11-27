"""Test registry chien luoc Phase B: dang ky, get/list, ten la bao loi,
donchian backtest_only, API cu khong vo."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.strategies import (
    STRATEGIES,
    build_strategies,
    get_strategy,
    list_strategies,
)
from diamondx10.strategies.breakout import DonchianBreakout
from diamondx10.strategies.crypto import CryptoMomentum
from diamondx10.strategies.forex import ForexTrend
from diamondx10.strategies.registry import STRATEGY_REGISTRY


def test_registry_has_default_and_donchian():
    assert set(STRATEGY_REGISTRY) == {"default", "donchian"}
    assert STRATEGY_REGISTRY["default"]["backtest_only"] is False
    assert STRATEGY_REGISTRY["donchian"]["backtest_only"] is True
    assert STRATEGY_REGISTRY["donchian"]["class"] is DonchianBreakout


def test_list_strategies_metadata():
    listed = list_strategies()
    assert [s["name"] for s in listed] == ["default", "donchian"]
    by_name = {s["name"]: s for s in listed}
    assert by_name["default"]["backtest_only"] is False
    assert by_name["donchian"]["backtest_only"] is True
    for s in listed:
        assert set(s) == {"name", "display_name", "desks", "description",
                          "backtest_only"}
        assert set(s["desks"]) == {"forex", "xauusd", "crypto",
                                   "us_securities"}
    assert "SMA" in by_name["default"]["display_name"]
    assert "Donchian" in by_name["donchian"]["display_name"]


def test_get_strategy_default_per_desk():
    assert isinstance(get_strategy("default", desk="forex"), ForexTrend)
    assert isinstance(get_strategy("default", desk="crypto"),
                      CryptoMomentum)
    assert get_strategy("default", desk="crypto").params["atr_sl_mult"] == 2.0
    assert get_strategy("default", desk="forex").params["atr_sl_mult"] == 1.5


def test_get_strategy_donchian():
    strat = get_strategy("donchian", desk="forex")
    assert isinstance(strat, DonchianBreakout)
    # Donchian khong can desk cung duoc (dung cho moi desk).
    assert isinstance(get_strategy("donchian"), DonchianBreakout)


def test_get_strategy_unknown_name_raises():
    with pytest.raises(ValueError, match="Chien luoc khong biet"):
        get_strategy("ema")
    with pytest.raises(ValueError, match="Chien luoc khong biet"):
        get_strategy("kelly")


def test_get_strategy_default_needs_desk():
    with pytest.raises(ValueError, match="can chi ro desk"):
        get_strategy("default")
    with pytest.raises(ValueError, match="Desk khong biet"):
        get_strategy("default", desk="metals")


def test_get_strategy_params_override():
    strat = get_strategy("default", desk="forex",
                         params={"atr_sl_mult": 2.5},
                         symbol_params={"rsi_buy_low": 55})
    assert strat.params["atr_sl_mult"] == 2.5
    assert strat.params["rsi_buy_low"] == 55
    # Symbol thang ca DESK_OVERRIDES cua lop (crypto 2.0 -> 2.5).
    strat = get_strategy("default", desk="crypto",
                         symbol_params={"atr_sl_mult": 2.5})
    assert strat.params["atr_sl_mult"] == 2.5


def test_legacy_api_unchanged():
    # STRATEGIES + build_strategies giu nguyen de test cu khong vo.
    assert set(STRATEGIES) == {"forex", "xauusd", "crypto",
                               "us_securities"}
    assert STRATEGIES["crypto"].params["atr_sl_mult"] == 2.0
    built = build_strategies({"atr_sl_mult": 1.0,
                              "desks": {"crypto": {"atr_sl_mult": 2.5}}})
    assert built["forex"].params["atr_sl_mult"] == 1.0
    assert built["crypto"].params["atr_sl_mult"] == 2.5
    # Khoa per_symbol trong build_strategies khong rot vao params.
    built = build_strategies({"per_symbol": {"EURUSD": {"atr_sl_mult": 3.0}}})
    assert "per_symbol" not in built["forex"].params
    assert built["forex"].params["atr_sl_mult"] == 1.5
