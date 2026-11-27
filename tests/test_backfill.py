"""Test backfill tu MT5 — dung MT5 GIA + feed GIA, khong can terminal
that, khong can mang."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import main, run_backfill
from diamondx10.data.history import HistoryStore
from diamondx10.data.mt5_feed import MT5Feed, _rate_to_bar

NOW = datetime(2026, 11, 27, 0, 0, 0, tzinfo=timezone.utc)
BASE = 1795000000


def make_bars(n=10, start=BASE, step=900):
    return [{"time": start + i * step, "open": 100.0 + i,
             "high": 101.0 + i, "low": 99.0 + i, "close": 100.5 + i,
             "volume": 5.0 + i}
            for i in range(n)]


class FakeFeed:
    """Feed gia: bars_range loc theo khoang start/end, ghi lai loi goi."""

    def __init__(self, bars):
        self._bars = list(bars)
        self.calls = []
        self.closed = False

    def bars_range(self, timeframe, start, end):
        self.calls.append((timeframe, start, end))
        lo, hi = int(start.timestamp()), int(end.timestamp())
        return [b for b in self._bars if lo <= b["time"] <= hi]

    def close(self):
        self.closed = True


class FakeMT5Range:
    """MT5 gia co copy_rates_range (FakeMT5 o test_mt5.py chua co)."""

    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_D1 = 1440

    def __init__(self):
        self._rates = [{"time": BASE + i * 900, "open": 100.0 + i,
                        "high": 101.0 + i, "low": 99.0 + i,
                        "close": 100.5 + i, "tick_volume": 7 + i}
                       for i in range(20)]

    def initialize(self, path=None):
        return True

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol) if symbol == "EURUSD" else None

    def symbol_select(self, symbol, enable):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return list(self._rates[-count:])

    def copy_rates_range(self, symbol, timeframe, start, end):
        lo, hi = int(start.timestamp()), int(end.timestamp())
        return [r for r in self._rates if lo <= r["time"] <= hi]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=101.5, ask=101.6)

    def account_info(self):
        return SimpleNamespace(trade_mode=0, server="Exness-MT5Trial7")

    def shutdown(self):
        return True


def _cfg(tmp_path, days=30):
    return {"data": {"provider": "mt5",
                     "symbols": {"forex": ["EURUSD"],
                                 "crypto": ["BTCUSD"]}},
            "mt5": {"login": 123, "server": "Exness-MT5Trial7"},
            "history": {"db_path": str(tmp_path / "history.db"),
                        "default_timeframe": "M15", "backfill_days": days}}


def test_mt5feed_bars_range_with_volume():
    feed = MT5Feed("EURUSD", login=123, password="demo-pass",
                   server="Exness-MT5Trial7", mt5_module=FakeMT5Range())
    start = datetime.fromtimestamp(BASE + 2 * 900, tz=timezone.utc)
    end = datetime.fromtimestamp(BASE + 5 * 900, tz=timezone.utc)
    bars = feed.bars_range("M15", start, end)
    assert [b["time"] for b in bars] == [BASE + i * 900 for i in range(2, 6)]
    assert bars[0]["volume"] == pytest.approx(9.0)  # tick_volume cua bar 2
    # bars_for_days: N ngay tinh den end cho truoc.
    bars = feed.bars_for_days("M15", days=1,
                              end=datetime.fromtimestamp(BASE + 5 * 900,
                                                       tz=timezone.utc))
    assert bars[0]["time"] == BASE  # khoang 1 ngay bao het 20 bar gia
    assert bars[-1]["time"] == BASE + 5 * 900


def test_rate_to_bar_volume_opt_in():
    rate = {"time": BASE, "open": 100.0, "high": 101.0, "low": 99.0,
            "close": 100.5, "tick_volume": 42}
    assert _rate_to_bar(rate) == {"time": BASE, "open": 100.0,
                                  "high": 101.0, "low": 99.0,
                                  "close": 100.5}
    assert _rate_to_bar(rate, include_volume=True)["volume"] == 42.0


def test_run_backfill_saves_to_store(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    feed = FakeFeed(make_bars(10))
    with HistoryStore(tmp_path / "history.db") as store:
        result = run_backfill(cfg, ["EURUSD"], "M15", 30, store=store,
                              feed_factory=lambda s: feed, now=NOW)
    assert result["failed"] == 0
    assert result["total_bars"] == 10
    assert result["results"][0]["symbol"] == "EURUSD"
    assert feed.calls[0][0] == "M15"  # khung truyen xuong feed
    assert feed.closed is True
    out = capsys.readouterr().out
    assert "EURUSD: lay 10 bar M15" in out and "luu 10 bar" in out
    with HistoryStore(tmp_path / "history.db") as store:
        assert store.count("EURUSD", "M15") == 10


def test_run_backfill_repeat_does_not_duplicate(tmp_path):
    cfg = _cfg(tmp_path)
    bars = make_bars(10)
    with HistoryStore(tmp_path / "history.db") as store:
        run_backfill(cfg, ["EURUSD"], "M15", 30, store=store,
                     feed_factory=lambda s: FakeFeed(bars), now=NOW)
        result = run_backfill(cfg, ["EURUSD"], "M15", 30, store=store,
                              feed_factory=lambda s: FakeFeed(bars), now=NOW)
    assert result["total_bars"] == 10
    with HistoryStore(tmp_path / "history.db") as store:
        assert store.count("EURUSD", "M15") == 10


def test_run_backfill_bad_timeframe_and_days(tmp_path):
    cfg = _cfg(tmp_path)
    with HistoryStore(tmp_path / "history.db") as store:
        with pytest.raises(ValueError, match="W1"):
            run_backfill(cfg, ["EURUSD"], "W1", 30, store=store,
                         feed_factory=lambda s: FakeFeed([]), now=NOW)
        with pytest.raises(ValueError, match="--days"):
            run_backfill(cfg, ["EURUSD"], "M15", 0, store=store,
                         feed_factory=lambda s: FakeFeed([]), now=NOW)


def test_run_backfill_one_symbol_fails_others_continue(tmp_path, capsys):
    cfg = _cfg(tmp_path)

    def factory(symbol):
        if symbol == "BTCUSD":
            raise ConnectionError("mat ket noi MT5")
        return FakeFeed(make_bars(3))

    with HistoryStore(tmp_path / "history.db") as store:
        result = run_backfill(cfg, ["EURUSD", "BTCUSD"], "M15", 30,
                              store=store, feed_factory=factory, now=NOW)
    assert result["failed"] == 1
    assert result["total_bars"] == 3
    assert "LOI (BTCUSD)" in capsys.readouterr().out


def test_main_backfill_without_mt5_reports_clean_error(tmp_path, monkeypatch,
                                                       capsys):
    # Tren Linux khong co goi MetaTrader5: lenh phai in LOI ro rang,
    # return 1, KHONG in traceback dai.
    monkeypatch.setattr("diamondx10.__main__.load_config",
                        lambda: _cfg(tmp_path))
    assert main(["backfill", "--symbol", "EURUSD", "--days", "1"]) == 1
    out = capsys.readouterr().out
    assert "LOI" in out and "MetaTrader5" in out
    assert "Traceback" not in out


def test_main_backfill_bad_timeframe(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("diamondx10.__main__.load_config",
                        lambda: _cfg(tmp_path))
    assert main(["backfill", "--symbol", "EURUSD",
                 "--timeframe", "W1"]) == 1
    assert "LOI" in capsys.readouterr().out
