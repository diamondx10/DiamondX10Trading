"""Test tich hop MTF v1 vao duong live + CLI compare/sweep + ta-review.

- `_fetch_trend_bars`: lay nen trend tu feed (cung khung -> bars(n);
  khac khung -> bars_for_days; feed khong ho tro -> None lang le).
- `process_symbol`: htf_bars truyen vao hoac lay tu feed khi
  `timeframes.trend_enabled` bat; H1 UP + M15 BUY -> TRADED kem ghi
  chu dong thuan + outcome context htf agreement "agree"; H1 DOWN ->
  HELD kem ghi chu HTF; thieu nen H1 -> chay M15-only kem canh bao;
  feed khong ho tro lay nen khung khac -> chay M15-only lang le.
- `_load_trend_bars_by_symbol`: doc bar trend tu kho lich su, khong
  bao gio raise khi thieu.
- `ta-review`: lat cat theo dong thuan HTF.

Dung feed/MT5 gia + bar gia, khong can terminal that, khong co lenh that.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diamondx10 import decisions
from diamondx10.config import load_config
from diamondx10.data.history import HistoryStore
from diamondx10.live import _fetch_trend_bars, process_symbol
from diamondx10.outcomes import load as load_outcomes
from diamondx10.ta_review import format_report, review
from test_live import FakeLiveFeed, FakeMT5Live, make_guard, trend_bars
from test_outcomes import _call_process_symbol
from test_soft_rules import bars_from_closes
from test_ta_review import _rec

TF_CFG_ON = {"entry": "M15", "trend": "H1", "timing": "M5",
             "trend_enabled": True, "timing_enabled": False,
             "htf_adx_min": 20, "trend_bars": 60}


def _htf_up():
    return bars_from_closes([100 + i * 1.0 for i in range(40)])


def _htf_down():
    return bars_from_closes([140 - i * 1.0 for i in range(40)])


class FakeMTFFeed(FakeLiveFeed):
    """Feed gia co bars_for_days (nhu MT5Feed): tra nen H1 da chuan bi."""

    def __init__(self, bars_data, latest, htf_bars, mt5=None):
        super().__init__(bars_data, latest, mt5=mt5)
        self.timeframe = "M15"
        self._htf_bars = list(htf_bars)

    def bars_for_days(self, timeframe=None, days=30, end=None):
        return list(self._htf_bars)


class FakeRaisingFeed(FakeLiveFeed):
    """Feed gia co bars_for_days nhung goi la loi."""

    def bars_for_days(self, timeframe=None, days=30, end=None):
        raise ConnectionError("mo phong loi lay nen")


@pytest.fixture
def tmp_decisions(monkeypatch, tmp_path):
    """LOG + equity state tam de test khong dong vao decisions/ that."""
    log_path = tmp_path / "decisions-log.csv"
    state_path = tmp_path / "equity-state.json"
    monkeypatch.setattr(decisions, "LOG", log_path)
    monkeypatch.setattr(decisions, "EQUITY_STATE", state_path)
    return log_path, state_path


def _cfg_with_tf():
    cfg = load_config()
    cfg["timeframes"] = dict(TF_CFG_ON)
    return cfg


# ---------------- _fetch_trend_bars ----------------

def test_fetch_same_timeframe_uses_bars():
    feed = FakeLiveFeed(trend_bars(), latest=103.0)
    feed.timeframe = "H1"
    got = _fetch_trend_bars(feed, "H1", 10)
    assert got is not None and len(got) == 10
    assert got[-1]["close"] == trend_bars()[-1]["close"]


def test_fetch_other_timeframe_via_bars_for_days():
    feed = FakeMTFFeed(trend_bars(), 103.0, _htf_up())
    got = _fetch_trend_bars(feed, "H1", 60)
    assert got is not None and len(got) == 40
    assert got[0]["close"] == pytest.approx(100.0)


def test_fetch_other_timeframe_slices_last_n():
    feed = FakeMTFFeed(trend_bars(), 103.0, _htf_up())
    got = _fetch_trend_bars(feed, "H1", 10)
    assert len(got) == 10
    assert got[0]["close"] == pytest.approx(130.0)


def test_fetch_no_capability_returns_none():
    feed = FakeLiveFeed(trend_bars(), latest=103.0)
    assert _fetch_trend_bars(feed, "H1", 60) is None


def test_fetch_error_returns_empty():
    feed = FakeRaisingFeed(trend_bars(), latest=103.0)
    assert _fetch_trend_bars(feed, "H1", 60) == []


# ---------------- process_symbol + HTF ----------------

def test_process_symbol_htf_agree_trades(tmp_decisions, tmp_path):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path,
                                  htf_bars=_htf_up())
    assert result["status"] == "TRADED"
    assert "dong thuan" in result["reason"]
    assert "[HTF H1: trend UP" in result["reason"]
    records = load_outcomes(outcome_path)
    assert len(records) == 1
    htf = records[0]["context"]["htf"]
    assert htf["timeframe"] == "H1"
    assert htf["direction"] == "up"
    assert htf["trusted"] is True
    assert htf["agreement"] == "agree"


def test_process_symbol_htf_block_holds(tmp_decisions, tmp_path):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path,
                                  htf_bars=_htf_down())
    assert result["status"] == "HELD"
    assert "[HTF H1: trend DOWN — khong BUY]" in result["reason"]
    assert mt5.sent_orders == []
    assert load_outcomes(outcome_path) == []


def test_process_symbol_htf_missing_bars_warns_and_runs(
        tmp_decisions, tmp_path, capsys):
    cfg = load_config()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path,
                                  htf_bars=[])
    assert result["status"] == "TRADED"
    assert "[HTF H1: thieu du lieu" in result["reason"]
    assert "Canh bao MTF" in capsys.readouterr().out
    records = load_outcomes(outcome_path)
    assert records[0]["context"]["htf"]["agreement"] == "not_applied"


def test_process_symbol_feed_without_htf_runs_m15_only(
        tmp_decisions, tmp_path):
    cfg = _cfg_with_tf()
    mt5 = FakeMT5Live()
    feed = FakeLiveFeed(trend_bars(), latest=103.0, mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path)
    assert result["status"] == "TRADED"
    assert "HTF" not in result["reason"]


def test_process_symbol_fetches_trend_from_feed(
        tmp_decisions, tmp_path):
    cfg = _cfg_with_tf()
    mt5 = FakeMT5Live()
    feed = FakeMTFFeed(trend_bars(), 103.0, _htf_down(), mt5=mt5)
    outcome_path = tmp_path / "signal-outcomes.jsonl"
    result = _call_process_symbol(cfg, mt5, feed, outcome_path, tmp_path)
    assert result["status"] == "HELD"
    assert "[HTF H1: trend DOWN — khong BUY]" in result["reason"]
    assert mt5.sent_orders == []


# ---------------- _load_trend_bars_by_symbol ----------------

def test_load_trend_bars_by_symbol(monkeypatch, tmp_path):
    import diamondx10.__main__ as cli

    db = tmp_path / "history.db"
    with HistoryStore(str(db)) as store:
        store.upsert_bars("EURUSD", "H1", _htf_up())
    monkeypatch.setattr(cli, "_history_store",
                        lambda cfg: HistoryStore(str(db)))
    cfg = _cfg_with_tf()
    cfg["data"] = {"symbols": {"forex": ["EURUSD", "XAUUSD"]}}
    out = cli._load_trend_bars_by_symbol(cfg, "forex", None)
    assert list(out) == ["EURUSD"]
    assert len(out["EURUSD"]) == 40


def test_load_trend_bars_disabled_returns_empty(monkeypatch, tmp_path):
    import diamondx10.__main__ as cli

    cfg = load_config()
    cfg["data"] = {"symbols": {"forex": ["EURUSD"]}}
    assert cli._load_trend_bars_by_symbol(cfg, "forex", None) == {}


# ---------------- ta-review HTF breakdown ----------------

def _htf_rec(agreement, outcome="win", ret=0.02):
    rec = _rec(outcome=outcome, ret=ret)
    rec["context"]["htf"] = {"timeframe": "H1", "direction": "up",
                             "adx": 30.0, "trusted": True,
                             "agreement": agreement}
    return rec


def test_ta_review_htf_breakdown():
    records = [_htf_rec("agree", "win", 0.02),
               _htf_rec("agree", "win", 0.03),
               _htf_rec("agree", "loss", -0.02),
               _htf_rec("against", "loss", -0.01),
               _htf_rec("not_applied", "timeout", 0.0)]
    cfg = {"learning": {"min_sample_for_proposal": 2}}
    report = review(records, cfg)
    htf = report["breakdowns"]["htf_agreement"]
    assert htf["dong thuan HTF"]["n"] == 3
    assert htf["nguoc HTF"]["n"] == 1
    assert htf["trung lap"]["n"] == 0
    assert htf["khong ap dung HTF"]["n"] == 1
    text = format_report(report)
    assert "THEO DONG THUAN HTF" in text
