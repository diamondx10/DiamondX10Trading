"""Test cho lop data + features cua mo hinh TA offline (ai/).

Chi dung bar gia + config gia — khong bao gio cham MT5, khong
network, khong torch/numpy. So lieu gia chi la so gia dinh.
"""
import copy
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.ai import (FEATURE_NAMES, FEATURE_VERSION, FEATURE_WINDOW,
                           LABEL_NAMES_DIRECTION, LABEL_NAMES_TP_SL,
                           assert_feature_version, build_dataset,
                           build_features, build_samples, class_counts,
                           label_direction, label_tp_sl, levels_for,
                           samples_from_outcomes)
from diamondx10.ai.dataset import InsufficientHistoryError
from diamondx10.config import DEFAULT
from diamondx10.data.history import HistoryStore

T0 = 1790000000  # moc thoi gian gia dinh (epoch)
STEP = 900  # M15


def _bar(i, open_, high, low, close, volume=100.0):
    return {"time": T0 + i * STEP, "open": open_, "high": high,
            "low": low, "close": close, "volume": volume}


def _walk_bars(n, start=100.0, seed=42, drift=0.0, vol=0.3):
    """Random walk xac dinh (seed co dinh): n bar M15, gia quanh start."""
    rng = random.Random(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(round(closes[-1] + drift + rng.gauss(0, vol), 4))
    bars = []
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        bars.append(_bar(i, prev, max(prev, c) + 0.15,
                         min(prev, c) - 0.15, c,
                         volume=100.0 + (i % 7) * 10.0))
    return bars


def _cfg(symbols=None):
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": symbols or {"forex": ["EURUSD"],
                                          "xauusd": ["XAUUSD"],
                                          "crypto": ["BTCUSD", "ETHUSD",
                                                     "BNBUSD"]}}
    cfg["strategy"] = dict(cfg["strategy"])
    cfg["strategy"]["per_symbol"] = {}
    cfg["learning"] = {"outcome_window_bars": 20,
                       "min_sample_for_proposal": 20}
    return cfg


def _params():
    return {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14,
            "atr_period": 14, "atr_sl_mult": 1.5, "tp_mult": 2.0}


# --- Feature version / ten cot on dinh ---

def test_feature_version_and_names_stable():
    assert FEATURE_VERSION == 1
    assert len(FEATURE_NAMES) == 35
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    assert FEATURE_NAMES[0] == "log_ret_1"
    assert FEATURE_NAMES[-1] == "direction_long"
    assert "pat_hammer" in FEATURE_NAMES
    assert "pat_breakout_up" in FEATURE_NAMES
    assert "regime_trending" in FEATURE_NAMES


def test_assert_feature_version_ok_and_mismatch():
    assert_feature_version(1, FEATURE_NAMES)
    assert_feature_version(1)  # chi version cung duoc
    with pytest.raises(ValueError, match="version khong khop"):
        assert_feature_version(2, FEATURE_NAMES)
    with pytest.raises(ValueError, match="FEATURE_NAMES khong khop"):
        assert_feature_version(1, ["log_ret_1"])


def test_build_features_shape_values_and_determinism():
    bars = _walk_bars(60)
    row = build_features(bars)
    assert len(row) == len(FEATURE_NAMES) == 35
    assert all(isinstance(v, float) for v in row)
    assert all(math.isfinite(v) for v in row)
    # Deterministic: goi lai ra giong het.
    assert build_features(bars) == row
    # Chi dung 50 bar cuoi: them bar cu vao dau khong doi ket qua.
    assert build_features(bars[-50:]) == row
    # rsi / adx da scale ve 0..1; regime one-hot toi da 1 cot bang 1.
    assert 0.0 <= row[FEATURE_NAMES.index("rsi_scaled")] <= 1.0
    assert 0.0 <= row[FEATURE_NAMES.index("adx_scaled")] <= 1.0
    regime_sum = sum(row[FEATURE_NAMES.index(n)] for n in
                     ("regime_trending", "regime_transitional",
                      "regime_ranging"))
    assert regime_sum in (0.0, 1.0)
    # Mac dinh direction_long = 0; BUY/SELL gan +-1.
    assert row[FEATURE_NAMES.index("direction_long")] == 0.0
    assert build_features(bars, direction="BUY")[-1] == 1.0
    assert build_features(bars, direction="SELL")[-1] == -1.0
    with pytest.raises(ValueError, match="direction"):
        build_features(bars, direction="HOLD")


def test_build_features_returns_match_prices():
    # Gia tang deu 1.0 / bar: log_ret_1 = log(101/100), vol ~ 0.
    closes = [100.0 + i for i in range(60)]
    bars = [_bar(i, c - 0.5, c + 0.5, c - 0.5, c) for i, c in
            enumerate(closes)]
    row = build_features(bars)
    assert row[FEATURE_NAMES.index("log_ret_1")] == pytest.approx(
        math.log(159 / 158))
    assert row[FEATURE_NAMES.index("log_ret_5")] == pytest.approx(
        math.log(159 / 154))
    assert row[FEATURE_NAMES.index("hl_range_t")] == pytest.approx(
        1.0 / 159)
    assert row[FEATURE_NAMES.index("co_move_t")] == pytest.approx(
        0.5 / 159)
    assert row[FEATURE_NAMES.index("sma_cross")] == 1.0


def test_build_features_needs_full_window():
    with pytest.raises(ValueError, match="it nhat 50 bar"):
        build_features(_walk_bars(49))
    with pytest.raises(ValueError, match="it nhat 50 bar"):
        build_features([])


def test_build_features_rejects_bad_params_silently():
    # sma_slow vuot cua so 50 bar -> raise ro ten chi bao, khong dien 0.
    bars = _walk_bars(60)
    with pytest.raises(ValueError, match="SMA\\(60\\)"):
        build_features(bars, params={"sma_slow": 60})


def test_pattern_flag_hammer_at_last_bar():
    bars = _walk_bars(49)
    # Nen hammer o bar cuoi: than 0.5 (19% bien do — vuot nguong doji
    # 10%), bong duoi dai 2.0, bong tren 0.1.
    bars.append(_bar(49, 100.0, 100.6, 98.0, 100.5))
    row = build_features(bars)
    assert row[FEATURE_NAMES.index("pat_hammer")] == 1.0
    assert row[FEATURE_NAMES.index("pat_doji")] == 0.0
    assert row[FEATURE_NAMES.index("pattern_score")] > 0


# --- Label TP/SL-first (giong evaluator) ---

def test_label_tp_sl_buy_tp_first_and_sl_first():
    future_tp = [_bar(1, 100, 101, 99, 100), _bar(2, 100, 104, 99, 103)]
    assert label_tp_sl("BUY", 100.0, 95.0, 103.0, future_tp) == (2, 2)
    future_sl = [_bar(1, 100, 101, 94, 96)]
    assert label_tp_sl("BUY", 100.0, 95.0, 103.0, future_sl) == (0, 1)
    # SELL nguoc lai: TP duoi, SL tren.
    future_sell_tp = [_bar(1, 100, 101, 96, 98)]
    assert label_tp_sl("SELL", 100.0, 105.0, 97.0,
                       future_sell_tp) == (2, 1)


def test_label_tp_sl_timeout_and_same_bar_is_loss():
    future = [_bar(i, 100, 101, 99, 100) for i in range(1, 6)]
    assert label_tp_sl("BUY", 100.0, 95.0, 103.0, future) == (1, 5)
    # Ca TP va SL cham cung bar -> thua (bao thu, giong evaluator).
    both = [_bar(1, 100, 104, 94, 100)]
    assert label_tp_sl("BUY", 100.0, 95.0, 103.0, both) == (0, 1)
    with pytest.raises(ValueError, match="khong co bar tuong lai"):
        label_tp_sl("BUY", 100.0, 95.0, 103.0, [])


def test_label_direction_up_down_flat():
    assert label_direction(100.0, [_bar(i, 100, 101, 99, 100 + i)
                                   for i in range(1, 6)],
                           horizon=5, threshold=0.002) == (2, 5)
    assert label_direction(100.0, [_bar(i, 100, 101, 99, 100 - i)
                                   for i in range(1, 6)],
                           horizon=5, threshold=0.002) == (0, 5)
    assert label_direction(100.0, [_bar(i, 100, 101, 99, 100.1)
                                   for i in range(1, 6)],
                           horizon=5, threshold=0.002) == (1, 5)


def test_levels_for_matches_strategy():
    sl, tp = levels_for("BUY", 100.0, 1.0, 1.5, 2.0)
    assert (sl, tp) == (98.5, 103.0)
    sl, tp = levels_for("SELL", 100.0, 1.0, 1.5, 2.0)
    assert (sl, tp) == (101.5, 97.0)
    with pytest.raises(ValueError, match="ATR"):
        levels_for("BUY", 100.0, 0.0, 1.5, 2.0)


# --- No-lookahead: spike tuong lai doi nhan, khong doi feature ---

def test_no_lookahead_future_spike_changes_label_not_features():
    # 60 bar phang (close 100, bien do 0.2 -> ATR 0.2, SL 99.7,
    # TP 100.6 cho BUY) + 20 bar tuong lai. 1 ban spike len 101
    # (cham TP BUY), 1 ban di ngang (timeout) — feature tai t = 59
    # phai giong het nhau, nhan BUY phai khac nhau.
    base = [_bar(i, 100.0, 100.1, 99.9, 100.0) for i in range(60)]
    spike = [_bar(60 + i, 100.0, 101.0, 99.9, 100.5) for i in range(20)]
    flat = [_bar(60 + i, 100.0, 100.2, 99.9, 100.0) for i in range(20)]
    X1, y1, m1 = build_samples(base + spike, symbol="EURUSD",
                               params=_params(), outcome_window=20)
    X2, y2, m2 = build_samples(base + flat, symbol="EURUSD",
                               params=_params(), outcome_window=20)
    # Mau tai t = 59 la mau cuoi co du 20 bar tuong lai... lay mau
    # co time = time cua bar 59 (index 59 trong base).
    t_time = base[59]["time"]
    i1 = next(i for i, m in enumerate(m1)
              if m["time"] == t_time and m["direction"] == "BUY")
    i2 = next(i for i, m in enumerate(m2)
              if m["time"] == t_time and m["direction"] == "BUY")
    assert X1[i1] == X2[i2]  # feature khong thay doi
    assert m1[i1]["label_name"] == "tp_first"
    assert m2[i2]["label_name"] == "timeout"
    assert y1[i1] != y2[i2]


# --- build_samples / build_dataset ---

def test_build_samples_shapes_and_meta():
    bars = _walk_bars(200)
    X, y, meta = build_samples(bars, symbol="EURUSD", params=_params(),
                               outcome_window=20)
    # t = 49..179 -> 131 bar t x 2 huong = 262 mau.
    assert len(X) == len(y) == len(meta) == 262
    assert all(len(row) == 35 for row in X)
    assert set(y) <= {0, 1, 2}
    assert sum(class_counts(y, LABEL_NAMES_TP_SL).values()) == 262
    m = meta[0]
    assert m["symbol"] == "EURUSD" and m["source"] == "bars"
    assert m["feature_version"] == FEATURE_VERSION
    assert m["time"] == bars[49]["time"]
    assert m["entry"] == bars[49]["close"]
    assert m["sl"] < m["entry"] < m["tp"]  # mau dau tien la BUY
    assert meta[1]["direction"] == "SELL"
    assert meta[1]["sl"] > meta[1]["entry"] > meta[1]["tp"]


def test_build_samples_direction_mode():
    bars = _walk_bars(120)
    X, y, meta = build_samples(bars, symbol="EURUSD", params=_params(),
                               label_mode="direction", horizon=5,
                               directions=("BUY",))
    assert len(X) == 120 - 50 - 5 + 1  # t = 49..114
    assert set(y) <= {0, 1, 2}
    assert all(m["label_name"] in LABEL_NAMES_DIRECTION for m in meta)
    with pytest.raises(ValueError, match="label_mode"):
        build_samples(bars, symbol="EURUSD", params=_params(),
                      label_mode="random")


def test_build_dataset_from_bars_and_class_counts():
    bars = _walk_bars(200)
    ds = build_dataset(_cfg(), "EURUSD", bars=bars)
    assert ds["symbol"] == "EURUSD" and ds["desk"] == "forex"
    assert ds["feature_version"] == FEATURE_VERSION
    assert ds["feature_names"] == list(FEATURE_NAMES)
    assert ds["label_names"] == list(LABEL_NAMES_TP_SL)
    assert ds["outcome_window_bars"] == 20
    assert ds["n_samples"] == len(ds["X"]) == len(ds["y"]) == 262
    assert sum(ds["class_counts"].values()) == 262
    assert ds["params"]["atr_sl_mult"] == 1.5
    # Moi symbol 1 dataset: XAUUSD dung tham so cua no (mac dinh
    # giong nhau o day, nhung desk khac).
    ds_xau = build_dataset(_cfg(), "XAUUSD", bars=bars)
    assert ds_xau["desk"] == "xauusd"


def test_build_dataset_unknown_symbol_raises():
    with pytest.raises(ValueError, match="Khong biet desk"):
        build_dataset(_cfg(), "FAKEUSD", bars=_walk_bars(200))


def test_build_dataset_short_history_raises_clear_error():
    bars = _walk_bars(60)  # can 50 + 20 + 10 - 1 = 79
    with pytest.raises(InsufficientHistoryError) as exc:
        build_dataset(_cfg(), "EURUSD", bars=bars)
    assert "79 bar" in str(exc.value) and "60 bar" in str(exc.value)
    with pytest.raises(InsufficientHistoryError) as exc:
        build_dataset(_cfg(), "EURUSD", bars=[])
    assert "backfill" in str(exc.value)


def test_build_dataset_from_empty_store_raises(tmp_path):
    store = HistoryStore(tmp_path / "empty.db")
    try:
        with pytest.raises(InsufficientHistoryError,
                           match="backfill"):
            build_dataset(_cfg(), "EURUSD", store=store)
    finally:
        store.close()


def test_build_dataset_from_store(tmp_path):
    bars = _walk_bars(200)
    store = HistoryStore(tmp_path / "hist.db")
    try:
        assert store.upsert_bars("EURUSD", "M15", bars) == 200
        ds = build_dataset(_cfg(), "EURUSD", store=store)
        assert ds["n_samples"] == 262
        assert ds["meta"][0]["time"] == bars[49]["time"]
    finally:
        store.close()


def test_build_dataset_min_samples_changes_requirement():
    bars = _walk_bars(75)
    # min_samples=1 -> can 50 + 20 + 0 = 70 bar: du.
    ds = build_dataset(_cfg(), "EURUSD", bars=bars, min_samples=1)
    assert ds["n_samples"] == (75 - 50 - 20 + 1) * 2
    # min_samples=10 -> can 79 bar: thieu.
    with pytest.raises(InsufficientHistoryError):
        build_dataset(_cfg(), "EURUSD", bars=bars, min_samples=10)


# --- Nguon log outcome ---

def _outcome_record(**over):
    rec = {"id": "a1b2c3d4", "created_utc": "2026-11-27T00:00:00Z",
           "desk": "forex", "symbol": "EURUSD", "action": "BUY",
           "status": "TRADED", "entry": 100.0, "sl": 95.0, "tp": 105.0,
           "volume": 0.01, "time": T0 + 60 * STEP,
           "context": {}, "params_hash": "deadbeef",
           "outcome": "win"}
    rec.update(over)
    return rec


def test_samples_from_outcomes_mapping():
    bars = _walk_bars(120)
    records = [_outcome_record(outcome="win"),
               _outcome_record(id="b2c3d4e5", outcome="loss",
                               action="SELL"),
               _outcome_record(id="c3d4e5f6", outcome="timeout"),
               _outcome_record(id="d4e5f6a7", outcome=None),  # chua dg
               _outcome_record(id="e5f6a7b8", outcome="win",
                               action="HOLD")]  # action sai
    X, y, meta, stats = samples_from_outcomes(
        records, bars_by_symbol={"EURUSD": bars},
        params_by_symbol={"EURUSD": _params()})
    assert stats == {"included": 3, "skipped_unevaluated": 1,
                     "skipped_bad": 1, "skipped_no_bars": 0,
                     "skipped_no_params": 0}
    assert y == [2, 0, 1]  # win -> tp_first, loss -> sl_first, timeout
    assert [m["label_name"] for m in meta] == ["tp_first", "sl_first",
                                               "timeout"]
    assert all(m["source"] == "outcomes-log" for m in meta)
    assert all(len(row) == 35 for row in X)
    assert meta[0]["outcome_id"] == "a1b2c3d4"
    assert meta[0]["rule_status"] == "TRADED"


def test_samples_from_outcomes_short_history_skipped():
    bars = _walk_bars(30)  # < 50 bar truoc tin hieu
    X, y, meta, stats = samples_from_outcomes(
        [_outcome_record()], bars_by_symbol={"EURUSD": bars},
        params_by_symbol={"EURUSD": _params()})
    assert X == [] and stats["skipped_no_bars"] == 1


def test_build_dataset_include_outcomes_dedupes():
    bars = _walk_bars(200)
    # Ban ghi trung mau bar tai (EURUSD, time bar 59, BUY) -> bi bo.
    rec = _outcome_record(time=T0 + 59 * STEP)
    ds = build_dataset(_cfg(), "EURUSD", bars=bars,
                       include_outcomes=True, outcomes_records=[rec])
    assert ds["outcomes_stats"]["included"] == 1
    assert ds["outcomes_stats"]["skipped_duplicate"] == 1
    assert ds["n_samples"] == 262  # khong them mau trung
