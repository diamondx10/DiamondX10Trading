"""Test kho nen OHLC local (HistoryStore) — dung SQLite that tren
thu muc tam, khong cham data/history.db that."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.data.history import HistoryStore

BASE = 1795000000  # epoch UTC co dinh de test lap lai duoc


def make_bars(n=5, start=BASE, step=900, symbol_close=100.0):
    """n bar M15 lien tiep, gia tang dan de de kiem tra thu tu."""
    return [{"time": start + i * step,
             "open": symbol_close + i, "high": symbol_close + i + 0.5,
             "low": symbol_close + i - 0.5, "close": symbol_close + i + 0.2,
             "volume": 10.0 + i}
            for i in range(n)]


def test_upsert_and_get_bars_in_time_order(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    bars = make_bars(5)
    assert store.upsert_bars("EURUSD", "M15", bars) == 5
    got = store.get_bars("EURUSD", "M15")
    assert [b["time"] for b in got] == [b["time"] for b in bars]
    assert got[0]["close"] == pytest.approx(100.2)
    assert got[0]["volume"] == pytest.approx(10.0)
    store.close()


def test_upsert_duplicate_does_not_double(tmp_path):
    # Backfill lap lai cung khoang thoi gian: bar trung (symbol,
    # timeframe, time) chi ghi de, khong nhan doi so bar.
    store = HistoryStore(tmp_path / "history.db")
    bars = make_bars(5)
    store.upsert_bars("EURUSD", "M15", bars)
    assert store.upsert_bars("EURUSD", "M15", bars) == 5
    assert store.count("EURUSD", "M15") == 5
    # Ghi de 1 bar voi gia moi: van 5 bar, gia moi thang.
    changed = [dict(bars[0], close=999.0)]
    store.upsert_bars("EURUSD", "M15", changed)
    assert store.count("EURUSD", "M15") == 5
    assert store.get_bars("EURUSD", "M15")[0]["close"] == pytest.approx(999.0)
    store.close()


def test_get_bars_range_and_limit(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.upsert_bars("EURUSD", "M15", make_bars(10))
    # Lay 3 bar giua khoang.
    got = store.get_bars("EURUSD", "M15",
                         start=BASE + 2 * 900, end=BASE + 4 * 900)
    assert len(got) == 3
    assert got[0]["time"] == BASE + 2 * 900
    assert got[-1]["time"] == BASE + 4 * 900
    # Limit lay N bar dau tien theo thoi gian.
    assert len(store.get_bars("EURUSD", "M15", limit=2)) == 2
    # Khoang khong co bar nao thi tra [].
    assert store.get_bars("EURUSD", "M15",
                          start=BASE + 100 * 900) == []
    store.close()


def test_latest_time_count_coverage(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    assert store.latest_time("EURUSD", "M15") is None
    assert store.count("EURUSD", "M15") == 0
    assert store.coverage("EURUSD", "M15") == {"count": 0, "start": None,
                                               "end": None}
    store.upsert_bars("EURUSD", "M15", make_bars(4))
    assert store.latest_time("EURUSD", "M15") == BASE + 3 * 900
    assert store.count("EURUSD", "M15") == 4
    assert store.coverage("EURUSD", "M15") == {
        "count": 4, "start": BASE, "end": BASE + 3 * 900}
    # Symbol / khung khac la kho rieng.
    assert store.count("EURUSD", "H1") == 0
    assert store.count("BTCUSD", "M15") == 0
    store.close()


def test_volume_defaults_to_zero_and_context_manager(tmp_path):
    path = tmp_path / "sub" / "history.db"  # thu muc chua co cung tu tao
    with HistoryStore(path) as store:
        # Bar khong co volume thi luu 0.0 (nguon MT5 cu / mo phong).
        store.upsert_bars("XAUUSD", "H1", [{"time": BASE, "open": 4000.0,
                                            "high": 4010.0, "low": 3990.0,
                                            "close": 4005.0}])
        assert store.get_bars("XAUUSD", "H1")[0]["volume"] == 0.0
    # Du lieu van con sau khi dong (mo lai doc duoc).
    with HistoryStore(path) as store:
        assert store.count("XAUUSD", "H1") == 1


def test_upsert_empty_and_bad_args(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    assert store.upsert_bars("EURUSD", "M15", []) == 0
    with pytest.raises(ValueError):
        store.upsert_bars("", "M15", make_bars(1))
    with pytest.raises(ValueError):
        store.upsert_bars("EURUSD", "", make_bars(1))
    store.close()
