"""Test Phase F — gioi han rui ro toan quy (risk.py).

Ham thuan, khong can MT5: gioi han lo ngay, so vi the mo toan quy
va theo desk, tinh lo ngay tu decisions log.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.risk import (
    DrawdownGuard,
    check_fund_limits,
    fund_limits_from_config,
    today_pnl_from_log_rows,
)

CFG = {"fund": {"total_capital_usd": 10000},
       "risk": {"fund_daily_loss_pct": 3.0,
                "max_open_positions_fund": 10,
                "max_open_positions_desk": 2}}


def _guard():
    return DrawdownGuard(10000, {"forex": 2500, "crypto": 2500})


def _pos(desk, symbol):
    return {"desk": desk, "symbol": symbol, "direction": "BUY",
            "entry": 100.0, "sl": 99.0, "tp": 102.0, "volume": 0.01,
            "contract_size": 100000, "atr": 0.1,
            "opened_date": "2026-11-27"}


def test_fund_limits_defaults_when_config_missing():
    limits = fund_limits_from_config({})
    assert limits == {"fund_daily_loss_pct": 3.0,
                      "max_open_positions_fund": 10,
                      "max_open_positions_desk": 2}


def test_fund_limits_config_overrides_defaults():
    cfg = {"risk": {"fund_daily_loss_pct": 5.0,
                    "max_open_positions_fund": 6,
                    "max_open_positions_desk": 1}}
    assert fund_limits_from_config(cfg) == {
        "fund_daily_loss_pct": 5.0, "max_open_positions_fund": 6,
        "max_open_positions_desk": 1}


def test_today_pnl_sums_close_rows_of_the_day_only():
    rows = [
        {"date": "2026-11-27", "action": "CLOSE",
         "reason": "Dong BUY EURUSD @ 1.10 P&L -120.50 USD (SL)"},
        {"date": "2026-11-27", "action": "CLOSE",
         "reason": "Dong SELL BTCUSD @ 60000 P&L 25.00 USD (TP)"},
        {"date": "2026-11-26", "action": "CLOSE",
         "reason": "Dong BUY EURUSD @ 1.10 P&L -999.00 USD (SL)"},
        {"date": "2026-11-27", "action": "BUY", "reason": "lenh moi"},
        {"date": "2026-11-27", "action": "CLOSE",
         "reason": "Dong BUY XAUUSD @ 3600 (khong ghi P&L)"},
    ]
    assert today_pnl_from_log_rows(rows, "2026-11-27") == -95.50
    assert today_pnl_from_log_rows(rows, "2026-11-26") == -999.00
    assert today_pnl_from_log_rows([], "2026-11-27") == 0.0


def test_daily_loss_blocks_when_over_limit():
    # Lo 350 USD > gioi han 3% von quy (300 USD) -> chan toan quy.
    ok, reason = check_fund_limits(_guard(), [], CFG, -350.0, desk="forex")
    assert not ok
    assert reason.startswith("BLOCKED-DAILY-LOSS-FUND")


def test_daily_loss_at_exact_limit_blocks():
    # Lo dung 300 USD = gioi han -> chan (than trong: cham muc la chan).
    ok, reason = check_fund_limits(_guard(), [], CFG, -300.0, desk="forex")
    assert not ok
    assert reason.startswith("BLOCKED-DAILY-LOSS-FUND")


def test_daily_loss_below_limit_does_not_block():
    # Lo 250 USD < 300 USD -> khong chan.
    ok, reason = check_fund_limits(_guard(), [], CFG, -250.0, desk="forex")
    assert ok
    assert reason == "gioi han quy trong muc cho phep"


def test_daily_profit_never_blocks():
    ok, _ = check_fund_limits(_guard(), [], CFG, 500.0, desk="forex")
    assert ok


def test_max_open_positions_fund_blocks():
    positions = [_pos("forex", f"S{i}") for i in range(10)]
    ok, reason = check_fund_limits(_guard(), positions, CFG, 0.0,
                                   desk="crypto")
    assert not ok
    assert reason.startswith("BLOCKED-MAX-POSITIONS-FUND")


def test_nine_open_positions_does_not_block_fund():
    positions = [_pos("forex", f"S{i}") for i in range(9)]
    ok, _ = check_fund_limits(_guard(), positions, CFG, 0.0, desk="crypto")
    assert ok


def test_max_open_positions_desk_blocks_only_that_desk():
    positions = [_pos("forex", "EURUSD"), _pos("forex", "GBPUSD")]
    ok, reason = check_fund_limits(_guard(), positions, CFG, 0.0,
                                   desk="forex")
    assert not ok
    assert reason.startswith("BLOCKED-MAX-POSITIONS-DESK")
    # Desk khac van mo duoc.
    ok, _ = check_fund_limits(_guard(), positions, CFG, 0.0, desk="crypto")
    assert ok


def test_desk_check_skipped_when_desk_not_given():
    positions = [_pos("forex", "EURUSD"), _pos("forex", "GBPUSD")]
    ok, _ = check_fund_limits(_guard(), positions, CFG, 0.0)
    assert ok
