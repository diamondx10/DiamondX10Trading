"""Test cho EVALUATOR (dx10 TA learning loop): score_signal +
evaluate + CLI evaluate-signals. Chi dung bar gia, khong bao gio
cham MT5. So lieu gia chi la so gia dinh (khong phai tai khoan that).
"""
import json

import diamondx10.__main__ as cli
from diamondx10.__main__ import main
from diamondx10.evaluator import evaluate, score_signal

T0 = 1790000000  # moc thoi gian tin hieu (epoch gia dinh)
STEP = 900  # 15 phut


def _bar(i, open_, high, low, close):
    return {"time": T0 + i * STEP, "open": open_, "high": high,
            "low": low, "close": close, "volume": 0.0}


def _record(**over):
    rec = {"id": "a1b2c3d4", "created_utc": "2026-11-27T00:00:00Z",
           "desk": "forex", "symbol": "EURUSD", "action": "BUY",
           "status": "TRADED", "entry": 100.0, "sl": 95.0, "tp": 105.0,
           "volume": 0.01, "risk_usd": 50.0, "manager": "Yuling Pan",
           "time": T0, "size_scale": 1.0, "pending_id": None,
           "context": {}, "params_hash": "deadbeef"}
    rec.update(over)
    return rec


class FakeStore:
    """Kho bar gia: {symbol: [bar, ...]}; loc theo start nhu HistoryStore."""

    def __init__(self, bars_by_symbol):
        self.bars_by_symbol = bars_by_symbol

    def get_bars(self, symbol, timeframe, start=None, end=None, limit=None):
        bars = list(self.bars_by_symbol.get(symbol) or [])
        if start is not None:
            bars = [b for b in bars if b["time"] >= start]
        if end is not None:
            bars = [b for b in bars if b["time"] <= end]
        if limit is not None:
            bars = bars[:limit]
        return bars

    def close(self):
        pass


# --- score_signal: thang / thua ---

def test_buy_tp_first_is_win():
    bars = [_bar(0, 100, 102, 99, 101), _bar(1, 101, 106, 100, 104)]
    result = score_signal(_record(), bars, window_bars=20)
    assert result["outcome"] == "win"
    assert result["bars_held"] == 2
    assert result["mfe"] == 6.0
    assert result["mae"] == 1.0
    assert result["ret"] == 0.05


def test_buy_sl_first_is_loss():
    bars = [_bar(0, 100, 101, 94, 96)]
    result = score_signal(_record(), bars, window_bars=20)
    assert result["outcome"] == "loss"
    assert result["bars_held"] == 1
    assert result["mfe"] == 1.0
    assert result["mae"] == 6.0
    assert result["ret"] == -0.05


def test_sell_tp_first_is_win():
    rec = _record(action="SELL", sl=105.0, tp=95.0)
    bars = [_bar(0, 100, 101, 96, 98), _bar(1, 98, 99, 94, 95)]
    result = score_signal(rec, bars, window_bars=20)
    assert result["outcome"] == "win"
    assert result["bars_held"] == 2
    assert result["mfe"] == 6.0
    assert result["mae"] == 1.0
    assert result["ret"] == 0.05


def test_sell_sl_first_is_loss():
    rec = _record(action="SELL", sl=105.0, tp=95.0)
    bars = [_bar(0, 100, 106, 99, 103)]
    result = score_signal(rec, bars, window_bars=20)
    assert result["outcome"] == "loss"
    assert result["bars_held"] == 1
    assert result["mfe"] == 1.0
    assert result["mae"] == 6.0
    assert result["ret"] == -0.05


def test_same_bar_tp_and_sl_hit_counts_as_loss():
    # Ca TP va SL deu cham trong cung 1 bar: tinh thua (bao thu).
    bars = [_bar(0, 100, 106, 94, 100)]
    result = score_signal(_record(), bars, window_bars=20)
    assert result["outcome"] == "loss"
    assert result["bars_held"] == 1


# --- score_signal: timeout / khong du bar ---

def test_timeout_buy_scored_by_window_end_return():
    bars = [_bar(0, 100, 102, 99, 101), _bar(1, 101, 103, 100, 102),
            _bar(2, 102, 102.5, 100.5, 101.5)]
    result = score_signal(_record(), bars, window_bars=5)
    assert result["outcome"] == "timeout"
    assert result["bars_held"] == 3
    assert result["ret"] == 0.015
    assert result["mfe"] == 3.0
    assert result["mae"] == 1.0


def test_timeout_sell_scored_by_window_end_return():
    rec = _record(action="SELL", sl=105.0, tp=95.0)
    bars = [_bar(0, 100, 101, 98, 99), _bar(1, 99, 100, 97, 98),
            _bar(2, 98, 99.5, 97.5, 98.5)]
    result = score_signal(rec, bars, window_bars=5)
    assert result["outcome"] == "timeout"
    assert result["bars_held"] == 3
    assert result["ret"] == 0.015


def test_timeout_uses_window_end_not_last_bar():
    bars = [_bar(0, 100, 101, 99, 101), _bar(1, 101, 102, 100, 102),
            _bar(2, 102, 108, 101, 107)]
    result = score_signal(_record(), bars, window_bars=2)
    assert result["outcome"] == "timeout"
    assert result["bars_held"] == 2
    assert result["ret"] == 0.02


def test_not_enough_bars_is_timeout_with_available_bars():
    bars = [_bar(0, 100, 101, 99, 101), _bar(1, 101, 102, 100, 100.5)]
    result = score_signal(_record(), bars, window_bars=20)
    assert result["outcome"] == "timeout"
    assert result["bars_held"] == 2
    assert result["ret"] == 0.005


def test_bars_before_signal_time_are_ignored():
    bars = [{"time": T0 - STEP, "open": 100, "high": 101, "low": 90,
             "close": 91},  # cham SL nhung TRUOC tin hieu -> bo qua
            _bar(0, 100, 106, 99, 104)]
    result = score_signal(_record(), bars, window_bars=20)
    assert result["outcome"] == "win"
    assert result["bars_held"] == 1


def test_signal_time_as_iso_string():
    rec = _record(time="2026-11-27T00:00:00Z")
    # T0 = 1790000000 == 2026-09-... khong khop ISO tren; dung bar theo
    # moc ISO that: doi bar ve moc ISO.
    import datetime
    epoch = int(datetime.datetime(2026, 11, 27, tzinfo=datetime.timezone.utc)
                .timestamp())
    bars = [{"time": epoch, "open": 100, "high": 106, "low": 99,
             "close": 104, "volume": 0.0}]
    result = score_signal(rec, bars, window_bars=20)
    assert result["outcome"] == "win"


# --- score_signal: ban ghi hong ---

def test_bad_record_missing_entry_returns_none():
    rec = _record()
    del rec["entry"]
    assert score_signal(rec, [_bar(0, 100, 106, 99, 104)]) is None


def test_bad_record_non_positive_tp_returns_none():
    assert score_signal(_record(tp=0), [_bar(0, 100, 106, 99, 104)]) is None
    assert score_signal(_record(sl=-5), [_bar(0, 100, 106, 99, 104)]) is None


def test_bad_record_unknown_action_returns_none():
    assert score_signal(_record(action="HOLD"),
                         [_bar(0, 100, 106, 99, 104)]) is None


def test_no_bars_at_or_after_signal_returns_none():
    bars = [{"time": T0 - STEP, "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 0.0}]
    assert score_signal(_record(), bars) is None
    assert score_signal(_record(), []) is None


# --- evaluate() end-to-end ---

def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_evaluate_end_to_end_deterministic_order_and_counts(tmp_path):
    outcomes = tmp_path / "signal-outcomes.jsonl"
    evaluated = tmp_path / "signal-outcomes-evaluated.jsonl"
    # Co tinh viet lech thu tu created_utc; ban thu 4 da danh gia roi.
    records = [
        _record(id="cccccccc", created_utc="2026-11-27T02:00:00Z",
                symbol="XAUUSD", action="SELL", entry=100.0, sl=105.0,
                tp=95.0),
        _record(id="aaaaaaaa", created_utc="2026-11-27T00:00:00Z",
                symbol="EURUSD"),
        _record(id="bbbbbbbb", created_utc="2026-11-27T01:00:00Z",
                symbol="EURUSD", entry=100.0, sl=95.0, tp=105.0),
        _record(id="dddddddd", created_utc="2026-11-27T03:00:00Z",
                symbol="BTCUSD", outcome="loss", bars_held=1, mfe=1.0,
                mae=6.0, ret=-0.05),
        _record(id="eeeeeeee", created_utc="2026-11-27T04:00:00Z",
                symbol="ETHUSD"),  # khong co bar -> skipped_no_bars
        _record(id="ffffffff", created_utc="2026-11-27T05:00:00Z",
                symbol="EURUSD", entry=None),  # ban hong -> skipped_bad
    ]
    _write_jsonl(outcomes, records)
    store = FakeStore({
        "EURUSD": [_bar(0, 100, 106, 99, 104)],
        "XAUUSD": [_bar(0, 100, 101, 96, 98),
                   _bar(1, 98, 99, 96.5, 97.5)],
    })
    summary = evaluate(outcomes, store, {}, evaluated_path=evaluated,
                       window_bars=20)
    assert summary == {"evaluated": 3, "skipped_already": 1,
                       "skipped_no_bars": 1, "skipped_bad": 1,
                       "wins": 2, "losses": 0, "timeouts": 1}
    rows = _read_jsonl(evaluated)
    # Chi ban co outcome moi vao file; thu tu xac dinh theo created_utc.
    assert [r["id"] for r in rows] == ["aaaaaaaa", "bbbbbbbb", "cccccccc",
                                       "dddddddd"]
    assert rows[0]["outcome"] == "win"      # aaaaaaaa: EURUSD TP bar 0
    assert rows[1]["outcome"] == "win"      # bbbbbbbb: giong vay
    assert rows[2]["outcome"] == "timeout"  # cccccccc: XAUUSD SELL khong cham TP/SL
    # Ban da danh gia truoc giu nguyen outcome cu, khong danh gia lai.
    assert rows[3]["outcome"] == "loss"
    assert rows[3]["bars_held"] == 1


def test_evaluate_timeout_counts_and_missing_file(tmp_path):
    outcomes = tmp_path / "signal-outcomes.jsonl"
    evaluated = tmp_path / "evaluated.jsonl"
    _write_jsonl(outcomes, [_record(id="a1b2c3d4")])
    store = FakeStore({"EURUSD": [_bar(0, 100, 101, 99, 101),
                                  _bar(1, 101, 102, 100, 100.5)]})
    summary = evaluate(outcomes, store, {}, evaluated_path=evaluated,
                       window_bars=20)
    assert summary["evaluated"] == 1
    assert summary["timeouts"] == 1
    assert summary["wins"] == 0 and summary["losses"] == 0
    assert _read_jsonl(evaluated)[0]["outcome"] == "timeout"
    # File goc thieu -> toan 0, khong ghi file dich.
    missing = tmp_path / "khong-co.jsonl"
    summary = evaluate(missing, store, {},
                       evaluated_path=tmp_path / "khong-ghi.jsonl")
    assert summary == {"evaluated": 0, "skipped_already": 0,
                       "skipped_no_bars": 0, "skipped_bad": 0,
                       "wins": 0, "losses": 0, "timeouts": 0}
    assert not (tmp_path / "khong-ghi.jsonl").exists()
    # File rong -> toan 0.
    empty = tmp_path / "rong.jsonl"
    empty.write_text("", encoding="utf-8")
    summary = evaluate(empty, store, {},
                       evaluated_path=tmp_path / "khong-ghi-2.jsonl")
    assert summary["evaluated"] == 0
    assert not (tmp_path / "khong-ghi-2.jsonl").exists()


def test_evaluate_window_from_config_learning_section(tmp_path):
    outcomes = tmp_path / "signal-outcomes.jsonl"
    evaluated = tmp_path / "evaluated.jsonl"
    _write_jsonl(outcomes, [_record()])
    # TP chi cham o bar thu 3: window mac dinh 20 -> win; window 2 -> timeout.
    store = FakeStore({"EURUSD": [_bar(0, 100, 102, 99, 101),
                                  _bar(1, 101, 103, 100, 102),
                                  _bar(2, 102, 106, 101, 104)]})
    summary = evaluate(outcomes, store,
                       {"learning": {"outcome_window_bars": 2}},
                       evaluated_path=evaluated)
    assert summary["timeouts"] == 1
    assert _read_jsonl(evaluated)[0]["outcome"] == "timeout"
    assert _read_jsonl(evaluated)[0]["bars_held"] == 2


def test_evaluate_missing_learning_section_uses_default_20(tmp_path):
    outcomes = tmp_path / "signal-outcomes.jsonl"
    evaluated = tmp_path / "evaluated.jsonl"
    _write_jsonl(outcomes, [_record()])
    store = FakeStore({"EURUSD": [_bar(0, 100, 102, 99, 101),
                                  _bar(1, 101, 103, 100, 102),
                                  _bar(2, 102, 106, 101, 104)]})
    summary = evaluate(outcomes, store, {}, evaluated_path=evaluated)
    assert summary["wins"] == 1


# --- CLI evaluate-signals ---

def _patch_store(monkeypatch, store):
    monkeypatch.setattr(cli, "_history_store", lambda cfg: store)


def test_cli_no_outcomes_file_exits_1(tmp_path, capsys):
    rc = main(["evaluate-signals", "--outcomes",
               str(tmp_path / "khong-co.jsonl"), "--evaluated",
               str(tmp_path / "ev.jsonl")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Khong co gi de danh gia" in out
    assert "Traceback" not in out


def test_cli_evaluates_then_already_evaluated_exits_0(tmp_path, monkeypatch,
                                                      capsys):
    outcomes = tmp_path / "signal-outcomes.jsonl"
    evaluated = tmp_path / "evaluated.jsonl"
    _write_jsonl(outcomes, [
        _record(id="a1b2c3d4"),
        _record(id="b2c3d4e5", action="SELL", sl=105.0, tp=95.0,
                created_utc="2026-11-27T01:00:00Z"),
        _record(id="c3d4e5f6", time=T0 + 2 * STEP,
                created_utc="2026-11-27T02:00:00Z"),
    ])
    _patch_store(monkeypatch, FakeStore({
        "EURUSD": [_bar(0, 100, 106, 99, 104),
                   _bar(1, 104, 105, 96, 100),
                   _bar(2, 100, 102, 98, 101),
                   _bar(3, 101, 103, 99, 102)],
    }))
    rc = main(["evaluate-signals", "--outcomes", str(outcomes),
               "--evaluated", str(evaluated), "--window", "20"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "thang 1" in out and "thua 1" in out and "het han 1" in out
    rows = _read_jsonl(evaluated)
    assert [r["outcome"] for r in rows] == ["win", "loss", "timeout"]
    # Chay lai tren file DA danh gia -> exit 0, tat ca da danh gia truoc.
    rc = main(["evaluate-signals", "--outcomes", str(evaluated),
               "--evaluated", str(tmp_path / "ev2.jsonl")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "da danh gia truoc 3" in out


def test_cli_no_bars_at_all_exits_1(tmp_path, monkeypatch, capsys):
    outcomes = tmp_path / "signal-outcomes.jsonl"
    _write_jsonl(outcomes, [_record()])
    _patch_store(monkeypatch, FakeStore({}))
    rc = main(["evaluate-signals", "--outcomes", str(outcomes),
               "--evaluated", str(tmp_path / "ev.jsonl")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "backfill" in out
    assert "Traceback" not in out
