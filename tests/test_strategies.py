"""Test chien luoc Phase 2: SMA + RSI, SL/TP theo ATR, trailing stop,
thoat khi dao chieu, config theo desk. Dung du lieu tong hop (khong
can MT5 that, khong co credential)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.config import DEFAULT
from diamondx10.data.feeds import SimulatedFeed
from diamondx10.models.quant import atr, rsi
from diamondx10.signals import generate_signals
from diamondx10.strategies import STRATEGIES, build_strategies
from diamondx10.strategies.base import Strategy
from diamondx10.strategies.crypto import CryptoMomentum
from diamondx10.strategies.forex import ForexTrend


def bars_from_closes(closes, half_range=0.5):
    """Bar OHLC tu chuoi gia dong: open = close, high/low cach 0.5."""
    return [{"time": i, "open": c, "high": c + half_range,
             "low": c - half_range, "close": c}
            for i, c in enumerate(closes)]


def closes_from_changes(start, changes):
    out = [start]
    for d in changes:
        out.append(round(out[-1] + d, 6))
    return out


def rsi_of(closes):
    return rsi(closes, 14)


# --- Chuoi gia tong hop (RSI tinh tren 14 thay doi cuoi; da kiem
# chung RSI dung bang so voi ham rsi() that) ---
def buy_rsi60_closes():
    # 6 nen tang +1, roi 8 tang +0.75 / 6 giam -2/3 -> RSI = 60, SMA5 > SMA20.
    return closes_from_changes(100, [1] * 6 + [0.75, -2 / 3] * 6 + [0.75, 0.75])


def buy_rsi75_closes():
    # RSI = 75 (qua mua nhung chua cuc doan): SMA bao BUY nhung RSI chan.
    return closes_from_changes(
        100, [1] * 6 + [0.6] * 5 + [-0.5] * 2 + [0.6] * 5 + [-0.5] * 2)


def buy_rsi70_closes():
    # RSI = 70 dung bien tren cua vung BUY (50 < RSI < 70, bien loai tru).
    return closes_from_changes(100, [1] * 6 + [1, -3 / 7] * 7)


def buy_rsi50_closes():
    # RSI = 50 dung bien duoi cua vung BUY.
    return closes_from_changes(100, [2] * 6 + [1, -1] * 7)


def sell_rsi40_closes():
    # 6 nen giam -1, roi 6 tang +2/3 / 8 giam -0.75 -> RSI = 40, SMA5 < SMA20.
    return closes_from_changes(100, [-1] * 6 + [2 / 3, -0.75] * 6 + [-0.75, -0.75])


def sell_rsi25_closes():
    # RSI = 25 (qua ban nhung chua cuc doan): SMA bao SELL nhung RSI chan.
    return closes_from_changes(
        100, [-1] * 6 + [0.5] * 2 + [-0.6] * 5 + [0.5] * 2 + [-0.6] * 5)


def sell_rsi30_closes():
    # RSI = 30 dung bien duoi cua vung SELL (30 < RSI < 50).
    return closes_from_changes(100, [-1] * 6 + [3 / 7, -1] * 7)


def sell_rsi50_closes():
    # RSI = 50 dung bien tren cua vung SELL.
    return closes_from_changes(100, [-2] * 6 + [1, -1] * 7)


def test_rsi_blocks_overbought_buy():
    closes = buy_rsi75_closes()
    assert rsi_of(closes) == pytest.approx(75.0)
    action, reason, levels = ForexTrend().signal(bars_from_closes(closes))
    assert action == "HOLD"
    assert levels is None
    assert "qua mua" in reason


def test_rsi_extreme_blocks_buy_and_sell():
    # Tang deu -> RSI = 100 (> 80, cuc doan): khong BUY du SMA bao BUY.
    rising = [100 + i * 1.0 for i in range(30)]
    assert rsi_of(rising) == pytest.approx(100.0)
    action, _r, levels = ForexTrend().signal(bars_from_closes(rising))
    assert action == "HOLD" and levels is None
    # Giam deu -> RSI = 0 (< 20, cuc doan): khong SELL du SMA bao SELL.
    falling = [130 - i * 1.0 for i in range(30)]
    assert rsi_of(falling) == pytest.approx(0.0)
    action, _r, levels = ForexTrend().signal(bars_from_closes(falling))
    assert action == "HOLD" and levels is None


def test_rsi_blocks_oversold_sell():
    closes = sell_rsi25_closes()
    assert rsi_of(closes) == pytest.approx(25.0)
    action, reason, levels = ForexTrend().signal(bars_from_closes(closes))
    assert action == "HOLD"
    assert levels is None
    assert "qua ban" in reason


@pytest.mark.parametrize("closes_fn,target", [
    (buy_rsi50_closes, 50.0),
    (buy_rsi70_closes, 70.0),
])
def test_buy_rsi_band_edges_hold(closes_fn, target):
    # Bien 50 va 70 loai tru: RSI dung bang bien thi khong BUY.
    closes = closes_fn()
    assert rsi_of(closes) == pytest.approx(target)
    action, _r, levels = ForexTrend().signal(bars_from_closes(closes))
    assert action == "HOLD" and levels is None


@pytest.mark.parametrize("closes_fn,target", [
    (sell_rsi30_closes, 30.0),
    (sell_rsi50_closes, 50.0),
])
def test_sell_rsi_band_edges_hold(closes_fn, target):
    # Bien 30 va 50 loai tru: RSI dung bang bien thi khong SELL.
    closes = closes_fn()
    assert rsi_of(closes) == pytest.approx(target)
    action, _r, levels = ForexTrend().signal(bars_from_closes(closes))
    assert action == "HOLD" and levels is None


def test_valid_buy_and_sell_signals_with_levels():
    closes = buy_rsi60_closes()
    assert rsi_of(closes) == pytest.approx(60.0)
    bars = bars_from_closes(closes)
    action, _r, levels = ForexTrend().signal(bars)
    assert action == "BUY"
    assert levels["entry"] == pytest.approx(closes[-1])
    atr_val = atr([b["high"] for b in bars], [b["low"] for b in bars],
                  closes, 14)
    assert levels["atr"] == pytest.approx(atr_val)
    # He so 1.5: SL = entry - 1.5*ATR, TP = entry + 2*(1.5*ATR).
    assert levels["sl"] == pytest.approx(closes[-1] - 1.5 * atr_val)
    assert levels["tp"] == pytest.approx(closes[-1] + 3.0 * atr_val)

    closes = sell_rsi40_closes()
    assert rsi_of(closes) == pytest.approx(40.0)
    bars = bars_from_closes(closes)
    action, _r, levels = ForexTrend().signal(bars)
    assert action == "SELL"
    atr_val = atr([b["high"] for b in bars], [b["low"] for b in bars],
                  closes, 14)
    assert levels["sl"] == pytest.approx(closes[-1] + 1.5 * atr_val)
    assert levels["tp"] == pytest.approx(closes[-1] - 3.0 * atr_val)


def test_levels_for_entry_math_buy_sell_both_mults():
    # Desk he so 1.5 (forex): entry 100, ATR 10 -> SL cach 15, TP cach 30.
    fx = ForexTrend()
    assert fx.levels_for_entry("BUY", 100.0, 10.0) == {
        "entry": 100.0, "sl": 85.0, "tp": 130.0, "atr": 10.0}
    assert fx.levels_for_entry("SELL", 100.0, 10.0) == {
        "entry": 100.0, "sl": 115.0, "tp": 70.0, "atr": 10.0}
    # Crypto he so 2.0: entry 100, ATR 10 -> SL cach 20, TP cach 40.
    cr = CryptoMomentum()
    assert cr.levels_for_entry("BUY", 100.0, 10.0) == {
        "entry": 100.0, "sl": 80.0, "tp": 140.0, "atr": 10.0}
    assert cr.levels_for_entry("SELL", 100.0, 10.0) == {
        "entry": 100.0, "sl": 120.0, "tp": 60.0, "atr": 10.0}
    # HOLD / ATR khong hop le thi khong co levels.
    assert fx.levels_for_entry("HOLD", 100.0, 10.0) is None
    assert fx.levels_for_entry("BUY", 100.0, None) is None
    assert fx.levels_for_entry("BUY", 100.0, 0.0) is None


def test_crypto_signal_uses_2x_atr_levels():
    bars = bars_from_closes(buy_rsi60_closes())
    action, _r, levels = CryptoMomentum().signal(bars)
    assert action == "BUY"
    atr_val = levels["atr"]
    assert levels["sl"] == pytest.approx(levels["entry"] - 2.0 * atr_val)
    assert levels["tp"] == pytest.approx(levels["entry"] + 4.0 * atr_val)


def test_trailing_stop_buy():
    fx = ForexTrend()  # trail_mult 1.5, ATR 5
    # Chua chay du 1x khoang cach SL (10): SL giu nguyen.
    assert fx.trailing_stop(100.0, 90.0, "BUY", 105.0, 5.0) == 90.0
    # Chay dung 1x: SL ve hoa von / bat dau trail: max(100, 110-7.5)=102.5.
    assert fx.trailing_stop(100.0, 90.0, "BUY", 110.0, 5.0) == pytest.approx(102.5)
    # Chay tiep: trail cach gia 1.5*ATR.
    assert fx.trailing_stop(100.0, 90.0, "BUY", 120.0, 5.0) == pytest.approx(112.5)
    # Khong bao gio doi SL nguoc: SL da o 112.5, gia 115 chi trail toi
    # 107.5 -> giu 112.5.
    assert fx.trailing_stop(100.0, 112.5, "BUY", 115.0, 5.0) == pytest.approx(112.5)
    # Gia quay dau duoi entry: SL giu nguyen.
    assert fx.trailing_stop(100.0, 102.5, "BUY", 99.0, 5.0) == pytest.approx(102.5)


def test_trailing_stop_sell_and_crypto():
    fx = ForexTrend()
    assert fx.trailing_stop(100.0, 110.0, "SELL", 95.0, 5.0) == 110.0
    assert fx.trailing_stop(100.0, 110.0, "SELL", 90.0, 5.0) == pytest.approx(97.5)
    assert fx.trailing_stop(100.0, 110.0, "SELL", 80.0, 5.0) == pytest.approx(87.5)
    # Khong doi SL nguoc cho SELL: SL da o 97.5, gia 93 chi trail toi
    # 100.5 -> giu 97.5.
    assert fx.trailing_stop(100.0, 97.5, "SELL", 93.0, 5.0) == pytest.approx(97.5)
    # Crypto trail 2.0*ATR: entry 100, SL 80 (cach 20), ATR 10.
    # Gia len 120 (+20 = 1x khoang cach SL) -> SL ve hoa von 100.
    cr = CryptoMomentum()
    assert cr.trailing_stop(100.0, 80.0, "BUY", 120.0, 10.0) == pytest.approx(100.0)
    assert cr.trailing_stop(100.0, 80.0, "BUY", 130.0, 10.0) == pytest.approx(110.0)
    # Gia chay nguoc huong vi the (BUY ma gia giam) -> SL giu nguyen.
    assert cr.trailing_stop(100.0, 80.0, "BUY", 80.0, 10.0) == pytest.approx(80.0)
    # Huong khong hop le / ATR khong hop le: tra SL cu.
    assert fx.trailing_stop(100.0, 90.0, "HOLD", 120.0, 5.0) == 90.0
    assert fx.trailing_stop(100.0, 90.0, "BUY", 120.0, None) == 90.0


def test_reversal_exit():
    fx = ForexTrend()
    buy_bars = bars_from_closes(buy_rsi60_closes())
    sell_bars = bars_from_closes(sell_rsi40_closes())
    # Dang SELL ma xuat hien tin hieu BUY day du -> dong SELL.
    assert fx.reversal_exit("SELL", buy_bars) is True
    # Dang BUY ma xuat hien tin hieu SELL day du -> dong BUY.
    assert fx.reversal_exit("BUY", sell_bars) is True
    # Cung huong hoac HOLD thi khong dong.
    assert fx.reversal_exit("BUY", buy_bars) is False
    assert fx.reversal_exit("SELL", sell_bars) is False
    assert fx.reversal_exit("BUY", bars_from_closes([100 + i for i in range(30)])) is False
    assert fx.reversal_exit("HOLD", buy_bars) is False


def test_hold_on_insufficient_data():
    fx = ForexTrend()
    for n in (0, 5, 19):
        bars = bars_from_closes([100.0 + i * 0.1 for i in range(n)])
        action, reason, levels = fx.signal(bars)
        assert action == "HOLD" and levels is None
        assert "chua du du lieu" in reason
    # SMA5 == SMA20 (gia phang) -> HOLD.
    bars = bars_from_closes([100.0] * 30)
    action, reason, levels = fx.signal(bars)
    assert action == "HOLD" and levels is None


def test_config_overrides_applied():
    built = build_strategies(DEFAULT["strategy"])
    assert built["crypto"].params["atr_sl_mult"] == 2.0
    assert built["crypto"].params["trail_mult"] == 2.0
    for desk in ("forex", "xauusd", "us_securities"):
        assert built[desk].params["atr_sl_mult"] == 1.5
        assert built[desk].params["trail_mult"] == 1.5
        assert built[desk].params["sma_fast"] == 5
        assert built[desk].params["rsi_buy_low"] == 50
    # Khong co config: registry mac dinh van cho crypto he so 2.0
    # (DESK_OVERRIDES cua lop), cac desk khac 1.5.
    assert STRATEGIES["crypto"].params["atr_sl_mult"] == 2.0
    assert STRATEGIES["forex"].params["atr_sl_mult"] == 1.5
    assert build_strategies(None)["crypto"].params["trail_mult"] == 2.0
    # Ghi de rieng desk trong config thang tham so chung; tham so chung
    # khong thang ghi de cua lop theo desk (crypto giu trail 2.0 cua lop
    # khi config chi doi tham so chung).
    custom = build_strategies({"atr_sl_mult": 1.0, "trail_mult": 1.0,
                               "desks": {"crypto": {"atr_sl_mult": 2.5}}})
    assert custom["forex"].params["atr_sl_mult"] == 1.0
    assert custom["crypto"].params["atr_sl_mult"] == 2.5
    assert custom["crypto"].params["trail_mult"] == 2.0
    # Nhung ghi de rieng desk trong config thang ca ghi de cua lop.
    custom2 = build_strategies({"desks": {"crypto": {"trail_mult": 3.0}}})
    assert custom2["crypto"].params["trail_mult"] == 3.0
    assert custom2["crypto"].params["atr_sl_mult"] == 2.0


def test_generate_signals_includes_levels():
    sig = generate_signals("forex", bars_from_closes(buy_rsi60_closes()))
    assert sig["action"] == "BUY"
    assert set(sig) >= {"desk", "strategy", "action", "reason", "levels"}
    assert sig["levels"]["entry"] == pytest.approx(buy_rsi60_closes()[-1])
    sig = generate_signals("forex", bars_from_closes([100.0] * 30))
    assert sig["action"] == "HOLD" and sig["levels"] is None


def test_end_to_end_all_desks_simulated_feed():
    for desk in ("forex", "xauusd", "crypto", "us_securities"):
        bars = SimulatedFeed(desk).bars(60)
        sig = generate_signals(desk, bars)
        assert sig["action"] in ("BUY", "SELL", "HOLD")
        assert "levels" in sig
        if sig["action"] == "HOLD":
            assert sig["levels"] is None
        else:
            lv = sig["levels"]
            assert set(lv) == {"entry", "sl", "tp", "atr"}
            assert lv["entry"] == pytest.approx(bars[-1]["close"])
            assert lv["atr"] > 0
            strat = STRATEGIES[desk]
            if sig["action"] == "BUY":
                assert lv["sl"] < lv["entry"] < lv["tp"]
                assert lv["entry"] - lv["sl"] == pytest.approx(
                    strat.params["atr_sl_mult"] * lv["atr"])
            else:
                assert lv["tp"] < lv["entry"] < lv["sl"]
                assert lv["sl"] - lv["entry"] == pytest.approx(
                    strat.params["atr_sl_mult"] * lv["atr"])
            # TP cach entry gap doi khoang cach SL (ti le 2:1).
            assert abs(lv["tp"] - lv["entry"]) == pytest.approx(
                2.0 * abs(lv["entry"] - lv["sl"]))


def test_base_strategy_default_params():
    s = Strategy()
    assert s.params["sma_fast"] == 5 and s.params["sma_slow"] == 20
    assert s.params["rsi_period"] == 14 and s.params["atr_period"] == 14
    assert s.params["tp_mult"] == 2.0
