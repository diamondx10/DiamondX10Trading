"""Test Phase 4 — risk enforcement: drawdown guard, equity state,
position reconciliation, margin check, daily limit, no-trade windows,
va tich hop mt5-trade voi MT5 gia. Khong can MT5 that, khong co lenh that."""
import csv
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import decisions
from diamondx10.decisions import count_trades_today, load_equity_state, save_equity_state
from diamondx10.execution import check_margin, place_demo_order
from diamondx10.positions import (
    new_position,
    position_pnl,
    realize_deals,
    reconcile_positions,
)
from diamondx10.risk import DrawdownGuard, check_drawdown, in_no_trade_window
from diamondx10.strategies import build_strategies

DESKS = {"forex": 2500, "xauusd": 2500, "crypto": 2500, "us_securities": 2500}
FUND = 10000


def make_guard():
    return DrawdownGuard(FUND, DESKS, max_drawdown_pct=10.0, desk_warning_pct=5.0)


def make_pos(direction="BUY", entry=100.0, sl=98.5, tp=103.0, volume=1.0,
             contract_size=1, atr=1.0, symbol="EURUSD", desk="forex"):
    return new_position(desk, symbol, direction, entry, sl, tp, volume,
                        contract_size, atr)


def bar(close, high=None, low=None, t=1700000000):
    return {"time": t, "open": close, "high": high if high is not None else close,
            "low": low if low is not None else close, "close": close}


def trend_bars(pattern, n=60, start=100.0):
    """Nen theo mau tang/giam lap lai — pattern A cho tin hieu BUY that
    (RSI ~59, SMA5 > SMA20)."""
    closes, c = [], start
    for i in range(n):
        c += pattern[i % len(pattern)]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


# ---------------- DrawdownGuard ----------------

def test_guard_fresh_allows_open():
    guard = make_guard()
    assert guard.can_open("forex") == (True, "drawdown trong gioi han")


def test_guard_blocks_on_fund_breach():
    guard = make_guard()
    guard.record_pnl("forex", -1100.0)  # quy 8900, drawdown 11% > 10%
    ok, reason = guard.can_open("forex")
    assert ok is False
    assert reason.startswith("BLOCKED-DRAWDOWN-FUND")


def test_guard_fund_boundary_exactly_at_limit_allowed():
    # Canh bao desk (5%) luon cham truoc gioi han quy (10%) khi lo tap
    # trung 1 desk, nen test rieng chan quy bang desk_warning cao.
    guard = DrawdownGuard(10000, {"forex": 10000}, max_drawdown_pct=10.0,
                          desk_warning_pct=50.0)
    guard.record_pnl("forex", -1000.0)  # dung 10% — chua vuot
    assert guard.can_open("forex")[0] is True
    guard.record_pnl("forex", -0.01)  # 10.0001% — vuot
    ok, reason = guard.can_open("forex")
    assert ok is False
    assert reason.startswith("BLOCKED-DRAWDOWN-FUND")


def test_guard_blocks_on_desk_warning_only_that_desk():
    guard = make_guard()
    guard.record_pnl("forex", -126.0)  # desk forex lo 5.04% > 5%; quy chi 1.26%
    ok, reason = guard.can_open("forex")
    assert ok is False
    assert reason.startswith("BLOCKED-DRAWDOWN-DESK")
    # Desk khac van mo duoc.
    assert guard.can_open("crypto")[0] is True


def test_guard_desk_boundary_exactly_at_warning_allowed():
    guard = make_guard()
    guard.record_pnl("xauusd", -125.0)  # dung 5% von desk — chua vuot
    assert guard.can_open("xauusd")[0] is True
    guard.record_pnl("xauusd", -0.01)
    assert guard.can_open("xauusd")[0] is False


def test_guard_state_round_trip():
    guard = make_guard()
    guard.record_pnl("forex", -200.0)
    guard.record_pnl("crypto", 50.0)
    restored = DrawdownGuard.from_state(guard.to_state())
    assert restored.fund_curve == guard.fund_curve
    assert restored.desk_curves == guard.desk_curves
    assert restored.can_open("forex") == guard.can_open("forex")
    restored.record_pnl("forex", -1100.0)
    assert restored.can_open("forex")[0] is False


def test_check_drawdown_boundary_unchanged():
    # Ham goc: vuot moi chan, bang thi khong.
    assert check_drawdown([100.0, 90.0], 10.0)[0] is True
    assert check_drawdown([100.0, 89.9], 10.0)[0] is False


# ---------------- Equity state persistence ----------------

def test_equity_state_save_load_round_trip(tmp_path):
    path = tmp_path / "equity-state.json"
    guard = make_guard()
    guard.record_pnl("forex", -100.0)
    state = {"guard": guard.to_state(), "positions": [make_pos()]}
    save_equity_state(state, path=path)
    loaded = load_equity_state(path=path)
    assert loaded["positions"] == state["positions"]
    restored = DrawdownGuard.from_state(loaded["guard"])
    assert restored.fund_curve == guard.fund_curve


def test_equity_state_missing_file_returns_none(tmp_path):
    assert load_equity_state(path=tmp_path / "khong-co.json") is None


# ---------------- Reconciliation ----------------

def test_reconcile_closes_on_tp(monkeypatch):
    strat = build_strategies(None)["forex"]
    guard = make_guard()
    logged = []
    monkeypatch.setattr("diamondx10.positions.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    positions = [make_pos()]  # BUY 100, SL 98.5, TP 103, 1 don vi
    closed, still = reconcile_positions(
        guard, positions, "forex", "EURUSD",
        [bar(101.0), bar(102.0, high=103.5)], strat, manager="Yuling Pan")
    assert len(closed) == 1 and closed[0]["cause"] == "TP"
    assert closed[0]["exit"] == 103.0
    assert closed[0]["pnl"] == pytest.approx(3.0)
    assert positions == [] and still == []
    assert guard.fund_curve[-1] == pytest.approx(10003.0)
    assert logged[0][0][1] == "CLOSE"
    assert "Dong BUY EURUSD @ 103 P&L 3.00 USD (TP)" in logged[0][0][2]


def test_reconcile_closes_on_sl(monkeypatch):
    strat = build_strategies(None)["forex"]
    guard = make_guard()
    logged = []
    monkeypatch.setattr("diamondx10.positions.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    positions = [make_pos(direction="SELL", entry=100.0, sl=101.5, tp=97.0)]
    closed, _ = reconcile_positions(
        guard, positions, "forex", "EURUSD",
        [bar(100.5, high=101.6)], strat, manager="Yuling Pan")
    assert len(closed) == 1 and closed[0]["cause"] == "SL"
    assert closed[0]["pnl"] == pytest.approx(-1.5)
    assert "P&L -1.50 USD (SL)" in logged[0][0][2]


def test_reconcile_closes_on_trailing(monkeypatch):
    strat = build_strategies(None)["forex"]
    guard = make_guard()
    logged = []
    monkeypatch.setattr("diamondx10.positions.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    positions = [make_pos()]  # BUY 100, SL 98.5, TP 103, ATR 1.0
    bars = [bar(101.5),  # loi 1.5 = khoang SL -> SL doi ve 100 (hoa von)
            bar(102.0),  # SL trailing len 100.5
            bar(101.0, low=100.4)]  # cham SL trailing 100.5
    closed, _ = reconcile_positions(guard, positions, "forex", "EURUSD",
                                    bars, strat, manager="Yuling Pan")
    assert len(closed) == 1 and closed[0]["cause"] == "trailing"
    assert closed[0]["exit"] == pytest.approx(100.5)
    assert closed[0]["pnl"] == pytest.approx(0.5)
    assert "(trailing)" in logged[0][0][2]


def test_reconcile_closes_on_reversal(monkeypatch):
    strat = build_strategies(None)["forex"]
    guard = make_guard()
    logged = []
    monkeypatch.setattr("diamondx10.positions.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    # SL/TP xa de khong cham — chi dao chieu moi dong.
    positions = [make_pos(sl=50.0, tp=200.0)]
    # Xuong dan voi pullback: SMA5 < SMA20, RSI trong 30-50 -> SELL.
    bars = trend_bars([-0.2, -0.2, 0.25], n=30, start=100.0)
    assert strat.signal(bars)[0] == "SELL"
    closed, _ = reconcile_positions(guard, positions, "forex", "EURUSD",
                                    bars, strat, manager="Yuling Pan")
    assert len(closed) == 1 and closed[0]["cause"] == "dao chieu"
    assert closed[0]["exit"] == pytest.approx(bars[-1]["close"])
    assert "P&L" in logged[0][0][2] and "(dao chieu)" in logged[0][0][2]


def test_reconcile_keeps_open_position_with_updated_trailing_sl(monkeypatch):
    strat = build_strategies(None)["forex"]
    guard = make_guard()
    logged = []
    monkeypatch.setattr("diamondx10.positions.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    positions = [make_pos()]
    bars = [bar(101.5), bar(102.0)]  # len nhung chua cham TP 103
    closed, still = reconcile_positions(guard, positions, "forex", "EURUSD",
                                        bars, strat, manager="Yuling Pan")
    assert closed == [] and len(still) == 1
    assert still[0]["sl"] == pytest.approx(100.5)  # trailing theo gia
    assert logged == []  # chua dong thi khong log CLOSE


def test_reconcile_only_matching_desk_symbol():
    strat = build_strategies(None)["forex"]
    guard = make_guard()
    positions = [make_pos(symbol="XAUUSD", desk="xauusd"),
                 make_pos(symbol="EURUSD", desk="forex")]
    closed, _ = reconcile_positions(guard, positions, "forex", "EURUSD",
                                    [bar(102.0, high=103.5)], strat)
    assert len(closed) == 1
    assert len(positions) == 1 and positions[0]["symbol"] == "XAUUSD"


def test_position_pnl_math_and_fee():
    pos = make_pos(volume=0.01, contract_size=100000)  # 1000 don vi
    assert position_pnl(pos, 101.0) == pytest.approx(1000.0)
    assert position_pnl(pos, 99.0) == pytest.approx(-1000.0)
    sell = make_pos(direction="SELL", volume=0.01, contract_size=100000)
    assert position_pnl(sell, 99.0) == pytest.approx(1000.0)
    # Phi 0.1% tren notional luc vao (100 x 1000 = 100.000) = 100 USD.
    assert position_pnl(pos, 101.0, fee_pct=0.1) == pytest.approx(900.0)
    assert position_pnl(pos, 101.0, fee_pct=0.0) == pytest.approx(1000.0)


def test_realize_deals_closes_from_mt5_deal(monkeypatch):
    guard = make_guard()
    logged = []
    monkeypatch.setattr("diamondx10.positions.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    positions = [make_pos(volume=1.0, contract_size=1)]
    deals = [{"symbol": "EURUSD", "type": 1, "price": 105.0,
              "profit": 5.0, "time": int(datetime.now().timestamp())}]
    closed, rest = realize_deals(guard, positions, deals, manager="Yuling Pan")
    assert len(closed) == 1 and closed[0]["pnl"] == pytest.approx(5.0)
    assert closed[0]["cause"] == "MT5 deal"
    assert positions == [] and rest == []
    assert guard.fund_curve[-1] == pytest.approx(10005.0)
    assert "(MT5 deal)" in logged[0][0][2]


def test_realize_deals_ignores_stale_deal_and_wrong_direction():
    guard = make_guard()
    positions = [make_pos(volume=1.0, contract_size=1)]
    stale = {"symbol": "EURUSD", "type": 1, "price": 105.0, "profit": 5.0,
             "time": 1000000000}  # 2001 — truoc ngay mo vi the
    same_dir = {"symbol": "EURUSD", "type": 0, "price": 105.0,
                "profit": 5.0, "time": int(datetime.now().timestamp())}
    closed, rest = realize_deals(guard, positions, [stale, same_dir])
    assert closed == [] and len(positions) == 1 and len(rest) == 2


# ---------------- Margin check ----------------

class FakeMT5Margin:
    """MT5 gia chi de test check_margin / place_demo_order."""
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self, order_check_retcode=0):
        self._retcode = order_check_retcode
        self.sent_orders = []
        self.checked = []

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7", demo=True)

    def order_check(self, request):
        self.checked.append(request)
        return SimpleNamespace(retcode=self._retcode, margin=10.0)

    def order_send(self, request):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009, order=123456, comment="Done")


DEMO_CFG = {"mt5": {"demo_only": True}, "data": {"provider": "mt5"}}


def test_check_margin_pass():
    mt5 = FakeMT5Margin(order_check_retcode=0)
    ok, msg = check_margin(mt5, "EURUSD", 0.01, 1.10, mt5.account_info())
    assert ok is True and mt5.checked
    assert mt5.checked[0]["symbol"] == "EURUSD"


def test_check_margin_fail_includes_retcode():
    mt5 = FakeMT5Margin(order_check_retcode=10013)
    ok, msg = check_margin(mt5, "EURUSD", 0.01, 1.10, mt5.account_info())
    assert ok is False
    assert "10013" in msg


def test_check_margin_skips_when_no_mt5_or_no_order_check():
    ok, msg = check_margin(None, "EURUSD", 0.01, 1.10)
    assert ok is True and "mo phong" in msg
    ok, msg = check_margin(SimpleNamespace(), "EURUSD", 0.01, 1.10)
    assert ok is True and "mo phong" in msg


def test_place_demo_order_refuses_on_insufficient_margin(monkeypatch):
    mt5 = FakeMT5Margin(order_check_retcode=10013)
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    with pytest.raises(RuntimeError, match="ky quy"):
        place_demo_order(mt5, symbol="EURUSD", action="BUY", volume=0.01,
                         price=1.10, sl=1.078, desk="forex",
                         manager="Yuling Pan", cfg=DEMO_CFG,
                         account_info=mt5.account_info(),
                         server="Exness-MT5Trial7")
    assert mt5.sent_orders == [] and logged == []


def test_place_demo_order_sends_when_margin_ok(monkeypatch):
    mt5 = FakeMT5Margin(order_check_retcode=0)
    logged = []
    monkeypatch.setattr("diamondx10.execution.log_decision",
                        lambda *a, **k: logged.append((a, k)))
    result = place_demo_order(mt5, symbol="EURUSD", action="BUY", volume=0.01,
                              price=1.10, sl=1.078, desk="forex",
                              manager="Yuling Pan", cfg=DEMO_CFG,
                              account_info=mt5.account_info(),
                              server="Exness-MT5Trial7")
    assert result["status"] == "SENT" and len(mt5.sent_orders) == 1
    assert result["margin_check"] == "du ky quy"


# ---------------- Daily limit ----------------

def _write_log(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "desk", "symbol", "action", "reason", "manager"])
        w.writerows(rows)


def test_count_trades_today(tmp_path):
    path = tmp_path / "decisions-log.csv"
    today = date.today().isoformat()
    _write_log(path, [
        [today, "forex", "EURUSD", "BUY", "lenh 1", "Yuling Pan"],
        [today, "forex", "EURUSD", "DRY-RUN-BUY", "dry-run khong dem", "Yuling Pan"],
        [today, "forex", "EURUSD", "CLOSE", "dong lenh khong dem", "Yuling Pan"],
        [today, "forex", "EURUSD", "BLOCKED-DAILY-LIMIT", "chan khong dem", "Yuling Pan"],
        ["2026-11-25", "forex", "EURUSD", "BUY", "hom truoc khong dem", "Yuling Pan"],
        [today, "crypto", "BTCUSD", "SELL", "symbol khac khong dem", "Rich"],
    ])
    assert count_trades_today("EURUSD", log_path=path) == 1
    assert count_trades_today("BTCUSD", log_path=path) == 1
    assert count_trades_today("XAUUSD", log_path=path) == 0
    assert count_trades_today("EURUSD", date="2026-11-25", log_path=path) == 1


def test_count_trades_today_missing_log_is_zero(tmp_path):
    assert count_trades_today("EURUSD", log_path=tmp_path / "khong-co.csv") == 0


# ---------------- No-trade window ----------------

EVENTS = [
    {"name": "CPI My", "start": "2026-11-27T14:00:00+07:00", "window_minutes": 60},
    {"name": "NVDA earnings", "start": "2026-11-27T10:00:00+07:00",
     "window_minutes": 120, "symbols": ["NVDA"]},
]


def test_no_trade_window_inside_and_outside():
    assert in_no_trade_window(datetime(2026, 11, 27, 14, 30), EVENTS) == (True, "CPI My")
    assert in_no_trade_window(datetime(2026, 11, 27, 13, 59), EVENTS) == (False, None)
    assert in_no_trade_window(datetime(2026, 11, 27, 15, 0), EVENTS) == (False, None)
    assert in_no_trade_window(datetime(2026, 11, 27, 14, 0), EVENTS) == (True, "CPI My")


def test_no_trade_window_symbol_scoped():
    assert in_no_trade_window(datetime(2026, 11, 27, 10, 30), EVENTS,
                              symbol="NVDA") == (True, "NVDA earnings")
    assert in_no_trade_window(datetime(2026, 11, 27, 10, 30), EVENTS,
                              symbol="AMD") == (False, None)
    assert in_no_trade_window(datetime(2026, 11, 27, 10, 30), EVENTS) == (False, None)


def test_no_trade_window_empty_list():
    assert in_no_trade_window(datetime.now(), []) == (False, None)
    assert in_no_trade_window(datetime.now(), None) == (False, None)


# ---------------- Integration: mt5-trade voi MT5 gia ----------------

class FakeFeed:
    """Feed gia cho main(): bars/lates_price thay doi duoc theo lan chay."""

    def __init__(self, bars_data, latest):
        self.bars_data = bars_data
        self._latest = latest

    def bars(self, n=60):
        return list(self.bars_data[-n:])

    def latest_price(self, symbol=None):
        return self._latest

    def close(self):
        return True


class FakeMT5Trade(FakeMT5Margin):
    def history_deals_get(self, *args, **kwargs):
        return []  # khong co deal dong — doi chieu theo nen


def _run_main(monkeypatch, tmp_path, feed, mt5):
    """Chay main() voi LOG + equity state tam; tra (rc, log_rows, state)."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    account = SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7", demo=True)
    monkeypatch.setattr("diamondx10.__main__._mt5_context",
                        lambda cfg, desk, symbol=None, mt5_module=None:
                        (feed, mt5, account, "Exness-MT5Trial7"))
    from diamondx10.__main__ import main
    rc = main(["mt5-trade", "--desk", "forex", "--symbol", "EURUSD",
               "--volume", "0.01"])
    rows = []
    if log_path.exists():
        with open(log_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    state = load_equity_state(path=state_path)
    return rc, rows, state, mt5


def test_second_trade_same_day_blocked_by_daily_limit(monkeypatch, tmp_path):
    mt5 = FakeMT5Trade(order_check_retcode=0)
    buy_bars = trend_bars([0.2, 0.2, -0.25], n=60, start=100.0)
    feed = FakeFeed(buy_bars, latest=103.0)
    rc, rows, state, _ = _run_main(monkeypatch, tmp_path, feed, mt5)
    assert rc in (None, 0)
    assert len(mt5.sent_orders) == 1
    assert [r for r in rows if r["action"] == "BUY"]
    assert state is not None and len(state["positions"]) == 1
    pos = state["positions"][0]
    assert pos["direction"] == "BUY" and pos["symbol"] == "EURUSD"
    assert pos["entry"] == pytest.approx(103.0)
    assert pos["sl"] == pytest.approx(101.5) and pos["tp"] == pytest.approx(106.0)

    # Lan 2 cung ngay: nen di ngang quanh 103.2 (khong cham SL/TP),
    # vi the van mo — chi gioi han ngay moi chan.
    flat = [{"time": 1700000000 + i * 900, "open": 103.2, "high": 103.7,
             "low": 102.7, "close": 103.2} for i in range(60)]
    feed.bars_data = flat
    feed._latest = 103.2
    rc, rows, state, _ = _run_main(monkeypatch, tmp_path, feed, mt5)
    assert rc in (None, 0)
    assert len(mt5.sent_orders) == 1  # khong gui lenh moi
    blocked = [r for r in rows if r["action"] == "BLOCKED-DAILY-LIMIT"]
    assert len(blocked) == 1 and blocked[0]["symbol"] == "EURUSD"
    assert len(state["positions"]) == 1  # vi the cu van mo


def test_dry_run_reconciles_open_position(monkeypatch, tmp_path):
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    guard = make_guard()
    state = {"guard": guard.to_state(),
             "positions": [make_pos(volume=1.0, contract_size=1)]}
    save_equity_state(state, path=state_path)
    # Nen cham TP 103 — vi the dong ngay trong dry-run, khong dat lenh.
    tp_bars = [bar(104.0, high=104.5, low=103.8, t=1700000000 + i * 900)
               for i in range(5)]
    feed = FakeFeed(tp_bars, latest=104.0)
    mt5 = FakeMT5Trade(order_check_retcode=0)
    account = SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7", demo=True)
    monkeypatch.setattr("diamondx10.__main__._mt5_context",
                        lambda cfg, desk, symbol=None, mt5_module=None:
                        (feed, mt5, account, "Exness-MT5Trial7"))
    from diamondx10.__main__ import main
    rc = main(["mt5-dry-run", "--desk", "forex", "--symbol", "EURUSD"])
    assert rc in (None, 0)
    assert mt5.sent_orders == []
    with open(log_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    closes = [r for r in rows if r["action"] == "CLOSE"]
    assert len(closes) == 1
    # P&L gop 3.00 USD tru phi backtest.fee_pct trong config (mac dinh
    # 0.02% tren notional 100 USD = 0.02 USD) — xem positions.py.
    from diamondx10.config import load_config
    fee_pct = float((load_config().get("backtest") or {}).get("fee_pct", 0) or 0)
    expected_pnl = 3.0 - fee_pct / 100.0 * 100.0
    assert f"P&L {expected_pnl:.2f} USD (TP)" in closes[0]["reason"]
    new_state = load_equity_state(path=state_path)
    assert new_state["positions"] == []
    assert new_state["guard"]["fund_curve"][-1] == pytest.approx(
        10000.0 + expected_pnl)


def test_trade_blocked_when_fund_drawdown_breached(monkeypatch, tmp_path):
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    guard = make_guard()
    guard.record_pnl("forex", -1100.0)  # vuot gioi han quy 10%
    save_equity_state({"guard": guard.to_state(), "positions": []},
                      path=state_path)
    buy_bars = trend_bars([0.2, 0.2, -0.25], n=60, start=100.0)
    feed = FakeFeed(buy_bars, latest=103.0)
    mt5 = FakeMT5Trade(order_check_retcode=0)
    account = SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7", demo=True)
    monkeypatch.setattr("diamondx10.__main__._mt5_context",
                        lambda cfg, desk, symbol=None, mt5_module=None:
                        (feed, mt5, account, "Exness-MT5Trial7"))
    from diamondx10.__main__ import main
    rc = main(["mt5-trade", "--desk", "forex", "--symbol", "EURUSD",
               "--volume", "0.01"])
    assert rc in (None, 0)
    assert mt5.sent_orders == []
    with open(log_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    blocked = [r for r in rows if r["action"] == "BLOCKED-DRAWDOWN-FUND"]
    assert len(blocked) == 1
