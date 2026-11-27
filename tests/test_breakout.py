"""Test Donchian breakout (merge tu DiamondX10, chi dung backtest):
pha dinh/day kenh Donchian 20, loc bien dong thap, HOLD trong kenh."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.strategies.breakout import DonchianBreakout


def bars_from_closes(closes, half_range=0.5):
    return [{"time": i, "open": c, "high": c + half_range,
             "low": c - half_range, "close": c}
            for i, c in enumerate(closes)]


def test_breakout_up_gives_buy_with_levels():
    # 20 nen di ngang quanh 100, nen 21 dong cua 102 > dinh Donchian
    # (100,5) -> BUY, kem SL/TP theo ATR.
    closes = [100.0] * 20 + [102.0]
    strat = DonchianBreakout()
    action, reason, levels = strat.signal(bars_from_closes(closes))
    assert action == "BUY"
    assert levels is not None
    assert levels["sl"] < 102.0 < levels["tp"]
    assert "Donchian" in reason


def test_breakout_down_gives_sell_with_levels():
    closes = [100.0] * 20 + [98.0]
    strat = DonchianBreakout()
    action, reason, levels = strat.signal(bars_from_closes(closes))
    assert action == "SELL"
    assert levels is not None
    assert levels["tp"] < 98.0 < levels["sl"]


def test_inside_channel_hold():
    closes = [100.0] * 20 + [100.2]
    strat = DonchianBreakout()
    action, reason, levels = strat.signal(bars_from_closes(closes))
    assert action == "HOLD"
    assert levels is None
    assert "kenh Donchian" in reason


def test_too_few_bars_hold():
    strat = DonchianBreakout()
    action, _, levels = strat.signal(bars_from_closes([100.0] * 10))
    assert action == "HOLD"
    assert levels is None


def test_low_volatility_hold():
    # Bien dong cuc thap (half_range 0.01 -> ATR/gia ~ 0,0002 < 0,003):
    # du pha kenh cung HOLD, khong mo lenh breakout.
    closes = [100.0] * 20 + [102.0]
    strat = DonchianBreakout()
    action, reason, levels = strat.signal(
        bars_from_closes(closes, half_range=0.01))
    assert action == "HOLD"
    assert levels is None
    assert "bien dong qua thap" in reason


def test_levels_use_atr_sl_mult():
    closes = [100.0] * 20 + [102.0]
    strat = DonchianBreakout(params={"atr_sl_mult": 1.5, "tp_mult": 2.0})
    _, _, levels = strat.signal(bars_from_closes(closes))
    assert levels is not None
    # ATR(14): 13 nen phang TR=1,0 + nen cuoi TR=2,5 (pha kenh)
    # -> ATR = 15,5/14 ~ 1,107. SL = 102 - 1,5xATR; TP = 102 + 2x1,5xATR.
    atr_val = 15.5 / 14.0
    assert abs(levels["sl"] - (102.0 - 1.5 * atr_val)) < 1e-9
    assert abs(levels["tp"] - (102.0 + 2.0 * 1.5 * atr_val)) < 1e-9


def test_inherits_trailing_and_reversal():
    # Donchian dung lai trailing stop / thoat dao chieu cua lop co so.
    strat = DonchianBreakout()
    # BUY 100, SL 98 (khoang cach 2), gia len 103, ATR 1: doi SL ve
    # max(entry, gia - 1,5xATR) = max(100, 101,5) = 101,5.
    new_sl = strat.trailing_stop(100.0, 98.0, "BUY", 103.0, 1.0)
    assert new_sl == 101.5
    # Gia chua chay du 1 khoang SL thi SL giu nguyen.
    assert strat.trailing_stop(100.0, 98.0, "BUY", 101.0, 1.0) == 98.0
    # Nen pha day Donchian -> tin SELL: dong vi the BUY, giu vi the SELL.
    sell_bars = bars_from_closes([100.0] * 20 + [98.0])
    assert strat.reversal_exit("BUY", sell_bars) is True
    assert strat.reversal_exit("SELL", sell_bars) is False
