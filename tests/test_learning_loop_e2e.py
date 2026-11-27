"""Test end-to-end vong hoc TA (TA learning loop): ghi log -> cham
diem -> review -> de xuat. Chi dung du lieu gia, khong bao gio
cham MT5 that, khong ghi vao decisions/ that (moi file deu trong
tmp_path). So lieu gia chi la so gia dinh (khong phai tai khoan
that).

Di qua code THAT: evaluator.evaluate (qua CLI cmd_evaluate_signals)
+ ta_review.review / propose / write_proposals (qua CLI
cmd_ta_review + goi truc tiep de lay dict de xuat).

4 ban ghi gia:
- EURUSD BUY thang (TP cham truoc) — PTCB dong thuan (FA buy 0.8).
- EURUSD BUY thua (SL cham truoc) — soft rule scale da kich hoat.
- EURUSD BUY thua (SL cham truoc) — PTCB mau thuan (FA sell 0.4).
- XAUUSD SELL het cua so (timeout) — 1 mau, lat cat "chua du mau".

Muc learning.min_sample_for_proposal mac dinh la 20; test dung 3
de 1 symbol (EURUSD, n=3) vuot cua trong khi cac lat cat khac
(XAUUSD n=1, cac band RSI/ADX it mau) van "chua du mau" — kiem
ca 2 phia cua cua chan mau trong 1 lan chay.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml

import diamondx10.__main__ as cli
from diamondx10 import ta_review
from diamondx10.data.history import HistoryStore

T0 = 1790000000  # moc thoi gian tin hieu (epoch gia dinh)
STEP = 900  # 15 phut = 1 nen M15

CFG = {
    "learning": {"outcome_window_bars": 20, "min_sample_for_proposal": 3},
    "strategy": {"sma_fast": 5, "sma_slow": 20, "rsi_period": 14,
                 "rsi_buy_low": 50, "rsi_buy_high": 70,
                 "rsi_sell_low": 30, "rsi_sell_high": 50,
                 "rsi_extreme_high": 80, "rsi_extreme_low": 20,
                 "atr_period": 14, "atr_sl_mult": 1.5, "tp_mult": 2.0,
                 "trail_mult": 1.5, "adx_min": 0, "min_atr_pct": 0.0},
    "data": {"symbols": {"forex": ["EURUSD"], "xauusd": ["XAUUSD"],
                         "crypto": ["BTCUSD"],
                         "us_securities": ["NVDA"]}},
}


def _context(**over):
    ctx = {"rsi": 60.0, "sma_fast": 5, "sma_slow": 20,
           "sma_relation": "fast>slow", "atr": 1.0, "atr_sl_mult": 1.5,
           "regime": "trending", "adx": 30,
           "patterns": [], "pattern_score": 0.0,
           "strategy_name": "default",
           "resolved_params": {"sma_fast": 5, "sma_slow": 20,
                               "atr_sl_mult": 1.5},
           "soft_rules": [], "fa": None}
    ctx.update(over)
    return ctx


def _record(rid, **over):
    rec = {"id": rid, "created_utc": "2026-11-27T00:00:00Z",
           "desk": "forex", "symbol": "EURUSD", "action": "BUY",
           "status": "TRADED", "entry": 100.0, "sl": 95.0, "tp": 101.0,
           "volume": 0.01, "risk_usd": 50.0, "manager": "Yuling Pan",
           "time": T0, "size_scale": 1.0, "pending_id": None,
           "context": _context(), "params_hash": "deadbeef"}
    rec.update(over)
    return rec


def _eurusd_bars():
    """26 nen M15 gia dinh: TP cham o nen 1, SL cham o nen 11 va 21."""
    bars = []
    for i in range(26):
        bars.append({"time": T0 + i * STEP, "open": 100.0, "high": 100.5,
                     "low": 99.5, "close": 100.0, "volume": 0.0})
    bars[1] = {"time": T0 + 1 * STEP, "open": 100.0, "high": 101.5,
               "low": 99.8, "close": 100.5, "volume": 0.0}
    bars[11] = {"time": T0 + 11 * STEP, "open": 100.0, "high": 100.2,
                "low": 94.5, "close": 99.0, "volume": 0.0}
    bars[21] = {"time": T0 + 21 * STEP, "open": 100.0, "high": 100.2,
                "low": 94.0, "close": 99.0, "volume": 0.0}
    return bars


def _xauusd_bars():
    """20 nen M15 gia dinh: gia dao dong 1995-2005, khong cham TP
    (1990) lan SL (2010) — timeout, close cuoi 1998."""
    bars = []
    for j in range(20):
        bars.append({"time": T0 + j * STEP, "open": 2000.0, "high": 2005.0,
                     "low": 1995.0, "close": 2000.0, "volume": 0.0})
    bars[19]["close"] = 1998.0
    return bars


def _records():
    return [
        # Thang: TP 101 cham o nen 1; PTCB dong thuan.
        _record("e2e-win", created_utc="2026-11-27T00:00:00Z", time=T0,
                context=_context(rsi=60.0, adx=30, patterns=["engulfing"],
                                 pattern_score=0.6,
                                 fa={"direction": "buy",
                                     "confidence": 0.8})),
        # Thua: SL 95 cham o nen 11; soft rule scale da kich hoat.
        _record("e2e-loss-scale", created_utc="2026-11-27T02:30:00Z",
                time=T0 + 10 * STEP, status="RECOMMENDED", size_scale=0.5,
                context=_context(rsi=55.0, adx=28, soft_rules=[
                    {"name": "eurusd-adx-weak-scale", "fired": True,
                     "effect": "scale"}])),
        # Thua: SL 95 cham o nen 21; PTCB mau thuan (FA sell 0.4).
        _record("e2e-loss-fa", created_utc="2026-11-27T05:00:00Z",
                time=T0 + 20 * STEP,
                context=_context(rsi=65.0, adx=35,
                                 fa={"direction": "sell",
                                     "confidence": 0.4})),
        # Timeout: SELL XAUUSD, het 20 nen khong cham TP/SL.
        _record("e2e-timeout", created_utc="2026-11-27T00:00:00Z",
                desk="xauusd", symbol="XAUUSD", action="SELL",
                entry=2000.0, sl=2010.0, tp=1990.0, volume=0.01,
                risk_usd=50.0, manager="Yumi", time=T0,
                context=_context(rsi=45.0, sma_relation="fast<slow",
                                 atr=5.0, atr_sl_mult=2.0,
                                 regime="ranging", adx=18)),
    ]


def _write_outcomes(path):
    with open(path, "w", encoding="utf-8") as f:
        for rec in _records():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_e2e_win_loss_timeout_then_review_and_proposal(tmp_path, capsys):
    outcomes_path = tmp_path / "signal-outcomes.jsonl"
    evaluated_path = tmp_path / "signal-outcomes-evaluated.jsonl"
    proposals_path = tmp_path / "ta-tuning-proposals-20261127.yaml"
    _write_outcomes(outcomes_path)

    store = HistoryStore(tmp_path / "history.db")
    try:
        store.upsert_bars("EURUSD", "M15", _eurusd_bars())
        store.upsert_bars("XAUUSD", "M15", _xauusd_bars())
        rc = cli.cmd_evaluate_signals(
            CFG, outcomes=str(outcomes_path),
            evaluated=str(evaluated_path), window=20, store=store)
    finally:
        store.close()
    assert rc == 0

    with open(evaluated_path, encoding="utf-8") as f:
        evaluated = [json.loads(line) for line in f if line.strip()]
    assert len(evaluated) == 4
    by_id = {rec["id"]: rec for rec in evaluated}
    assert set(by_id) == {"e2e-win", "e2e-loss-scale", "e2e-loss-fa",
                          "e2e-timeout"}
    for rec in evaluated:
        for key in ("outcome", "bars_held", "mfe", "mae", "ret",
                    "evaluated_utc"):
            assert key in rec, f"thieu {key} trong {rec['id']}"

    win = by_id["e2e-win"]
    assert win["outcome"] == "win"
    assert win["bars_held"] == 2
    assert win["ret"] == 0.01
    assert win["mfe"] == 1.5
    assert win["mae"] == 0.5
    loss_scale = by_id["e2e-loss-scale"]
    assert loss_scale["outcome"] == "loss"
    assert loss_scale["bars_held"] == 2
    assert loss_scale["ret"] == -0.05
    assert loss_scale["context"]["soft_rules"][0]["name"] == (
        "eurusd-adx-weak-scale")
    assert by_id["e2e-loss-fa"]["outcome"] == "loss"
    timeout = by_id["e2e-timeout"]
    assert timeout["outcome"] == "timeout"
    assert timeout["bars_held"] == 20
    assert timeout["ret"] == 0.001

    rc = cli.cmd_ta_review(CFG, evaluated=str(evaluated_path),
                           proposals=str(proposals_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "EURUSD: n=3" in out
    assert "XAUUSD: n=1" in out
    assert "chua du mau" in out

    report = ta_review.review(evaluated, CFG)
    assert report["by_symbol"]["EURUSD"]["n"] == 3
    assert report["by_symbol"]["EURUSD"]["status"] == "du mau"
    assert report["by_symbol"]["XAUUSD"]["n"] == 1
    assert report["by_symbol"]["XAUUSD"]["status"] == "chua du mau"
    assert report["breakdowns"]["soft_rule"][
        "eurusd-adx-weak-scale"]["fired"]["n"] == 1
    assert report["breakdowns"]["fa_agreement"]["dong thuan"]["n"] == 1
    assert "chua du mau" in ta_review.format_report(report)

    proposals = ta_review.propose(report, evaluated, CFG, history=None)
    assert len(proposals) >= 1
    proposal = proposals[0]
    assert proposal["symbol"] == "EURUSD"
    assert proposal["validated"] is False
    oos = proposal["oos_validation"]
    assert oos["validated"] is False
    assert oos["reason"] == ta_review.NO_HISTORY_REASON

    assert proposals_path.exists()
    text = proposals_path.read_text(encoding="utf-8")
    assert "EURUSD" in text
    assert "CHUA KIEM CHUNG" in text
    data = yaml.safe_load(text)
    assert data["strategy"]["per_symbol"]["EURUSD"]["atr_sl_mult"] == 2.0


def test_e2e_score_signal_direct_win_loss_timeout():
    """Pin truc tiep ngu nghia cham diem THAT (score_signal):
    win / loss / timeout tren 3 bo nen rieng."""
    from diamondx10.evaluator import score_signal

    base = _record("x", context=_context())
    win_bars = [{"time": T0, "open": 100.0, "high": 100.5, "low": 99.5,
                 "close": 100.0, "volume": 0.0},
                {"time": T0 + STEP, "open": 100.0, "high": 101.5,
                 "low": 99.8, "close": 100.5, "volume": 0.0}]
    assert score_signal(base, win_bars, window_bars=20)["outcome"] == "win"

    loss_bars = [{"time": T0, "open": 100.0, "high": 100.5, "low": 99.5,
                  "close": 100.0, "volume": 0.0},
                 {"time": T0 + STEP, "open": 100.0, "high": 100.2,
                  "low": 94.5, "close": 99.0, "volume": 0.0}]
    assert score_signal(base, loss_bars, window_bars=20)["outcome"] == "loss"

    flat = [{"time": T0 + i * STEP, "open": 100.0, "high": 100.5,
             "low": 99.5, "close": 100.0, "volume": 0.0}
            for i in range(20)]
    timed_out = score_signal(base, flat, window_bars=20)
    assert timed_out["outcome"] == "timeout"
    assert timed_out["bars_held"] == 20
    assert timed_out["ret"] == 0.0
