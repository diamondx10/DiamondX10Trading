"""Test lop DATA multi-timeframe: fetch_bars_for_timeframes +
HistoryStore theo tung khung + CLI backfill --timeframes /
--all-timeframes + export-bars --timeframe.

Chi dung feed GIA / store TAM, khong can MT5, khong can mang.
"""
import diamondx10.__main__ as cli
from diamondx10.__main__ import main
from diamondx10.data.history import HistoryStore
from diamondx10.data.multitimeframe import (
    configured_stack,
    fetch_bars_for_timeframes,
    parse_timeframes,
    planned_timeframes,
)

BASE = 1795000000


def make_bars(n=60, start=BASE, step=900):
    return [{"time": start + i * step, "open": 100.0 + i,
             "high": 101.0 + i, "low": 99.0 + i, "close": 100.5 + i,
             "volume": 5.0 + i}
            for i in range(n)]


def fake_get_bars(bars_by_tf, calls=None, fail_tf=None):
    """get_bars gia: tra bar theo khung; khung trong fail_tf thi raise."""
    def _get(timeframe, n):
        if calls is not None:
            calls.append((timeframe, n))
        if fail_tf and timeframe in fail_tf:
            raise ConnectionError(f"MT5 loi khung {timeframe}")
        bars = bars_by_tf.get(timeframe) or []
        return list(bars[:n])
    return _get


# --- fetch_bars_for_timeframes ---

def test_fetch_entry_plus_trend_and_stores_both(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    get_bars = fake_get_bars({"M15": make_bars(60),
                              "H1": make_bars(60, step=3600)})
    out = fetch_bars_for_timeframes(get_bars, "EURUSD", {},
                                    store=store)
    assert set(out["bars"]) == {"M15", "H1"}
    assert out["missing"] == []
    assert len(out["bars"]["M15"]) == 60
    assert len(out["bars"]["H1"]) == 60
    assert store.count("EURUSD", "M15") == 60
    assert store.count("EURUSD", "H1") == 60
    assert store.get_bars("EURUSD", "H1")[0]["time"] == BASE
    store.close()


def test_fetch_failing_trend_is_missing_entry_survives(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    get_bars = fake_get_bars({"M15": make_bars(60),
                              "H1": make_bars(60, step=3600)},
                             fail_tf={"H1"})
    out = fetch_bars_for_timeframes(get_bars, "EURUSD", {},
                                    store=store)
    assert set(out["bars"]) == {"M15"}
    assert out["missing"] == ["H1"]
    assert store.count("EURUSD", "M15") == 60
    assert store.count("EURUSD", "H1") == 0
    store.close()


def test_fetch_too_few_bars_counts_as_missing():
    get_bars = fake_get_bars({"M15": make_bars(60),
                              "H1": make_bars(5, step=3600)})
    out = fetch_bars_for_timeframes(get_bars, "EURUSD", {})
    assert set(out["bars"]) == {"M15"}
    assert out["missing"] == ["H1"]


def test_fetch_none_bars_counts_as_missing():
    def _get(timeframe, n):
        return make_bars(60) if timeframe == "M15" else None

    out = fetch_bars_for_timeframes(_get, "EURUSD", {})
    assert set(out["bars"]) == {"M15"}
    assert out["missing"] == ["H1"]


def test_fetch_timing_only_when_enabled():
    calls = []
    get_bars = fake_get_bars({"M15": make_bars(60),
                              "H1": make_bars(60, step=3600),
                              "M5": make_bars(60, step=300)},
                             calls=calls)
    # Mac dinh: timing tat -> chi entry + trend.
    out = fetch_bars_for_timeframes(get_bars, "EURUSD", {})
    assert set(out["bars"]) == {"M15", "H1"}
    assert [tf for tf, _n in calls] == ["M15", "H1"]
    # Bat timing -> them M5.
    calls.clear()
    out = fetch_bars_for_timeframes(
        get_bars, "EURUSD", {"timeframes": {"timing_enabled": True}})
    assert set(out["bars"]) == {"M15", "H1", "M5"}
    assert [tf for tf, _n in calls] == ["M15", "H1", "M5"]


def test_fetch_trend_disabled_is_m15_only():
    calls = []
    get_bars = fake_get_bars({"M15": make_bars(60)}, calls=calls)
    out = fetch_bars_for_timeframes(
        get_bars, "EURUSD", {"timeframes": {"trend_enabled": False}})
    assert set(out["bars"]) == {"M15"}
    assert out["missing"] == []
    assert calls == [("M15", 60)]


def test_fetch_trend_bars_from_config():
    calls = []
    get_bars = fake_get_bars({"M15": make_bars(60),
                              "H1": make_bars(100, step=3600)},
                             calls=calls)
    out = fetch_bars_for_timeframes(
        get_bars, "EURUSD", {"timeframes": {"trend_bars": 100}})
    assert len(out["bars"]["H1"]) == 100
    assert ("H1", 100) in calls


def test_fetch_store_failure_never_raises():
    class BrokenStore:
        def upsert_bars(self, symbol, timeframe, bars):
            raise RuntimeError("disk loi")

    get_bars = fake_get_bars({"M15": make_bars(60),
                              "H1": make_bars(60, step=3600)})
    out = fetch_bars_for_timeframes(get_bars, "EURUSD", {},
                                    store=BrokenStore())
    assert set(out["bars"]) == {"M15", "H1"}
    assert out["missing"] == []


def test_fetch_duplicate_timeframe_fetched_once():
    calls = []
    get_bars = fake_get_bars({"M15": make_bars(60)}, calls=calls)
    out = fetch_bars_for_timeframes(
        get_bars, "EURUSD",
        {"timeframes": {"entry": "M15", "trend": "M15"}})
    assert set(out["bars"]) == {"M15"}
    assert calls == [("M15", 60)]


# --- parse / plan helpers ---

def test_parse_timeframes_ok_and_dedupes():
    assert parse_timeframes("M15,H1") == ["M15", "H1"]
    assert parse_timeframes("m15, H1 ,M15") == ["M15", "H1"]
    assert parse_timeframes("D1") == ["D1"]


def test_parse_timeframes_bad_value_names_it():
    try:
        parse_timeframes("M15,H4")
    except ValueError as exc:
        assert "H4" in str(exc)
    else:
        raise AssertionError("cho doi ValueError cho khung H4")


def test_parse_timeframes_empty_errors():
    for bad in ("", "   ", ","):
        try:
            parse_timeframes(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"cho doi ValueError cho {bad!r}")


def test_planned_timeframes_defaults():
    assert planned_timeframes({}) == [("M15", 60), ("H1", 60)]
    assert configured_stack({}) == ["M15", "H1"]
    assert configured_stack({"timeframes": {"trend_enabled": False}}) == ["M15"]
    assert configured_stack(
        {"timeframes": {"timing_enabled": True}}) == ["M15", "H1", "M5"]


# --- HistoryStore theo tung khung (khong doi schema) ---

def test_history_store_per_timeframe(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    m15 = make_bars(10, start=BASE, step=900)
    h1 = make_bars(5, start=BASE, step=3600)
    assert store.upsert_bars("EURUSD", "M15", m15) == 10
    assert store.upsert_bars("EURUSD", "H1", h1) == 5
    # Lay rieng tung khung, khong lan nhau.
    got_m15 = store.get_bars("EURUSD", "M15")
    got_h1 = store.get_bars("EURUSD", "H1")
    assert len(got_m15) == 10 and len(got_h1) == 5
    assert got_m15[0]["time"] == BASE and got_h1[-1]["time"] == BASE + 4 * 3600
    assert store.count("EURUSD", "M15") == 10
    assert store.count("EURUSD", "H1") == 5
    cov_m15 = store.coverage("EURUSD", "M15")
    cov_h1 = store.coverage("EURUSD", "H1")
    assert cov_m15 == {"count": 10, "start": BASE, "end": BASE + 9 * 900}
    assert cov_h1 == {"count": 5, "start": BASE, "end": BASE + 4 * 3600}
    assert store.latest_time("EURUSD", "M15") == BASE + 9 * 900
    assert store.latest_time("EURUSD", "H1") == BASE + 4 * 3600
    # Upsert lap khong nhan doi bar (khoa chinh symbol, timeframe, time).
    assert store.upsert_bars("EURUSD", "M15", m15) == 10
    assert store.count("EURUSD", "M15") == 10
    store.close()


# --- CLI backfill --timeframes / --all-timeframes ---

def _patch_run_backfill(monkeypatch):
    calls = []

    def _fake(cfg, symbols, timeframe, days, **kwargs):
        calls.append((symbols, timeframe, days))
        return {"results": [{"symbol": s} for s in symbols],
                "total_bars": 60, "failed": 0}

    monkeypatch.setattr(cli, "run_backfill", _fake)
    return calls


def test_cli_backfill_timeframes(monkeypatch, capsys):
    calls = _patch_run_backfill(monkeypatch)
    rc = main(["backfill", "--symbol", "EURUSD",
               "--timeframes", "M15,H1", "--days", "7"])
    assert rc in (0, None)
    assert [tf for _s, tf, _d in calls] == ["M15", "H1"]
    out = capsys.readouterr().out
    assert "M15, H1" in out
    assert "120 bar" in out  # 60 bar / khung x 2 khung


def test_cli_backfill_timeframes_bad_value(monkeypatch, capsys):
    calls = _patch_run_backfill(monkeypatch)
    rc = main(["backfill", "--symbol", "EURUSD",
               "--timeframes", "M15,H4"])
    assert rc == 1
    assert calls == []  # chua goi run_backfill lan nao
    out = capsys.readouterr().out
    assert "LOI" in out and "H4" in out


def test_cli_backfill_all_timeframes_uses_configured_stack(monkeypatch):
    calls = _patch_run_backfill(monkeypatch)
    rc = main(["backfill", "--symbol", "EURUSD",
               "--all-timeframes", "--days", "7"])
    assert rc in (0, None)
    # Config repo hien chua co muc timeframes -> stack mac dinh M15+H1.
    assert [tf for _s, tf, _d in calls] == ["M15", "H1"]


def test_cli_backfill_single_timeframe_unchanged(monkeypatch, capsys):
    calls = _patch_run_backfill(monkeypatch)
    rc = main(["backfill", "--symbol", "EURUSD", "--days", "7"])
    assert rc in (0, None)
    assert len(calls) == 1
    assert calls[0][1] == "M15"  # history.default_timeframe trong config
    out = capsys.readouterr().out
    assert "60 bar da luu, 1/1 symbol OK." in out


def test_cli_backfill_timeframes_overrides_timeframe(monkeypatch):
    calls = _patch_run_backfill(monkeypatch)
    rc = main(["backfill", "--symbol", "EURUSD",
               "--timeframe", "D1", "--timeframes", "H1", "--days", "7"])
    assert rc in (0, None)
    assert [tf for _s, tf, _d in calls] == ["H1"]


# --- CLI export-bars --timeframe (da co san, kiem tra van chay) ---

def test_cli_export_bars_timeframe(tmp_path):
    out_dir = tmp_path / "exports"
    rc = main(["export-bars", "--desk", "forex", "--from", "simulated",
               "--timeframe", "H1", "--out", str(out_dir)])
    assert rc in (0, None)
    assert (out_dir / "EURUSD_H1.csv").exists()
