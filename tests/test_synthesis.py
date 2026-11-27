"""Test tong hop Yuling + nhan dinh PTCB (synthesis.py).

Khong mang that, khong MT5 that — file dung tmp_path.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.synthesis import (
    cmd_synthesize,
    cmd_verdict,
    load_verdict,
    load_verdicts,
    save_verdict,
    synthesize,
    validate_verdict,
)

CFG = {}
CFG_REQUIRE_FA = {"synthesis": {"require_fa": True}}


def _verdict(**over):
    base = {"desk": "forex", "analyst": "Yuling Pan",
            "direction": "buy", "confidence": 0.8,
            "drivers": ["ECB giu lai suat"], "risks": ["CPI cao"],
            "note": "EUR manh len",
            "created_utc": datetime.now(timezone.utc).isoformat()}
    base.update(over)
    return base


# --- Ma tran tong hop: PTKT BUY ---

def test_buy_fa_buy_high_confidence_full_size():
    out = synthesize("BUY", "buy", 0.8, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "MUA"
    assert out["size"] == 1.0
    assert out["blocked"] is False
    assert out["fa_status"] == "ok"
    assert "PTKT: BUY" in out["rationale"]
    assert "PTCB: buy (tin cay 0.8)" in out["rationale"]


def test_buy_fa_buy_low_confidence_half_size():
    out = synthesize("BUY", "buy", 0.4, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "MUA"
    assert out["size"] == 0.5
    assert out["blocked"] is False


def test_buy_fa_neutral_half_size():
    out = synthesize("BUY", "neutral", 0.5, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "MUA"
    assert out["size"] == 0.5
    assert out["blocked"] is False


def test_buy_fa_sell_high_confidence_blocked():
    out = synthesize("BUY", "sell", 0.9, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "KHONG MUA"
    assert out["size"] == 0.0
    assert out["blocked"] is True
    assert "chan" in out["rationale"]


def test_buy_fa_sell_low_confidence_half_size_warning():
    out = synthesize("BUY", "sell", 0.3, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "MUA"
    assert out["size"] == 0.5
    assert out["blocked"] is False
    assert "canh bao" in out["rationale"]


# --- Ma tran tong hop: PTKT SELL (doi xung) + HOLD ---

def test_sell_fa_sell_high_confidence_full_size():
    out = synthesize("SELL", "sell", 0.8, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "BAN"
    assert out["size"] == 1.0
    assert out["blocked"] is False


def test_sell_fa_sell_low_confidence_half_size():
    out = synthesize("SELL", "sell", 0.4, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "BAN"
    assert out["size"] == 0.5


def test_sell_fa_neutral_half_size():
    out = synthesize("SELL", "neutral", 0.5, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "BAN"
    assert out["size"] == 0.5


def test_sell_fa_buy_high_confidence_blocked():
    out = synthesize("SELL", "buy", 0.9, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "KHONG MUA"
    assert out["size"] == 0.0
    assert out["blocked"] is True


def test_sell_fa_buy_low_confidence_half_size_warning():
    out = synthesize("SELL", "buy", 0.3, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "BAN"
    assert out["size"] == 0.5
    assert "canh bao" in out["rationale"]


def test_hold_fa_buy_never_enters():
    out = synthesize("HOLD", "buy", 0.9, CFG, verdict_age_hours=1)
    assert out["recommendation"] == "CHO"
    assert out["size"] == 0.0
    assert out["blocked"] is False


# --- PTCB thieu / qua han ---

def test_stale_verdict_half_size():
    out = synthesize("BUY", "buy", 0.8, CFG, verdict_age_hours=25)
    assert out["recommendation"] == "MUA"
    assert out["size"] == 0.5
    assert out["fa_status"] == "stale"
    assert "chua co PTCB moi" in out["rationale"]


def test_missing_verdict_half_size():
    out = synthesize("BUY", None, None, CFG, verdict_age_hours=None)
    assert out["recommendation"] == "MUA"
    assert out["size"] == 0.5
    assert out["fa_status"] == "missing"
    assert "chua co PTCB moi" in out["rationale"]


def test_require_fa_missing_verdict_blocked():
    out = synthesize("BUY", None, None, CFG_REQUIRE_FA,
                     verdict_age_hours=None)
    assert out["recommendation"] == "KHONG MUA"
    assert out["size"] == 0.0
    assert out["blocked"] is True


def test_require_fa_stale_verdict_blocked():
    out = synthesize("SELL", "sell", 0.9, CFG_REQUIRE_FA,
                     verdict_age_hours=48)
    assert out["recommendation"] == "KHONG MUA"
    assert out["size"] == 0.0
    assert out["blocked"] is True
    assert out["fa_status"] == "stale"


# --- validate_verdict ---

def test_validate_bad_direction():
    with pytest.raises(ValueError, match="direction"):
        validate_verdict(_verdict(direction="hold"))


def test_validate_confidence_above_one():
    with pytest.raises(ValueError, match="confidence"):
        validate_verdict(_verdict(confidence=1.5))


def test_validate_missing_desk():
    data = _verdict()
    del data["desk"]
    with pytest.raises(ValueError, match="desk"):
        validate_verdict(data)


def test_validate_unknown_desk():
    with pytest.raises(ValueError, match="desk"):
        validate_verdict(_verdict(desk="stocks"))


def test_validate_missing_analyst():
    data = _verdict()
    del data["analyst"]
    with pytest.raises(ValueError, match="analyst"):
        validate_verdict(data)


def test_validate_drivers_not_list():
    with pytest.raises(ValueError, match="drivers"):
        validate_verdict(_verdict(drivers="ECB giu lai suat"))


def test_validate_bad_created_utc():
    with pytest.raises(ValueError, match="created_utc"):
        validate_verdict(_verdict(created_utc="hom qua"))


def test_validate_fills_created_utc_when_missing():
    data = _verdict()
    del data["created_utc"]
    out = validate_verdict(data)
    assert out["created_utc"]
    datetime.fromisoformat(out["created_utc"].replace("Z", "+00:00"))


# --- Luu / doc kho nhan dinh ---

def test_load_verdicts_missing_file_empty(tmp_path):
    assert load_verdicts(tmp_path / "khong-co.json") == {}


def test_verdict_round_trip_keeps_newest_per_desk(tmp_path):
    store = tmp_path / "verdicts.json"
    old = _verdict(
        created_utc=(datetime.now(timezone.utc)
                     - timedelta(hours=5)).isoformat())
    new = _verdict(
        direction="sell", confidence=0.7,
        created_utc=datetime.now(timezone.utc).isoformat())
    save_verdict(old, store)
    save_verdict(new, store)
    assert load_verdict(store, "forex")["direction"] == "sell"
    # Luu lai ban cu hon thi khong ghi de ban moi.
    save_verdict(old, store)
    assert load_verdict(store, "forex")["direction"] == "sell"
    assert load_verdict(store, "crypto") is None
    assert set(load_verdicts(store)) == {"forex"}


# --- cmd_verdict ---

def test_cmd_verdict_stores_valid_file(tmp_path, capsys):
    src = tmp_path / "in.json"
    src.write_text(json.dumps(_verdict()), encoding="utf-8")
    store = tmp_path / "store.json"
    assert cmd_verdict({}, src, store_path=store) == 0
    saved = load_verdict(store, "forex")
    assert saved["analyst"] == "Yuling Pan"
    assert saved["direction"] == "buy"
    out = capsys.readouterr().out
    assert "forex" in out and "Yuling Pan" in out and "buy" in out


def test_cmd_verdict_accepts_verdicts_list(tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"verdicts": [
        _verdict(), _verdict(desk="crypto", analyst="Rich",
                             direction="sell", confidence=0.6)]}),
        encoding="utf-8")
    store = tmp_path / "store.json"
    assert cmd_verdict({}, src, store_path=store) == 0
    assert load_verdict(store, "crypto")["direction"] == "sell"
    assert load_verdict(store, "forex")["direction"] == "buy"


def test_cmd_verdict_rejects_invalid_file(tmp_path, capsys):
    src = tmp_path / "bad.json"
    src.write_text(json.dumps(_verdict(direction="hold")),
                   encoding="utf-8")
    store = tmp_path / "store.json"
    assert cmd_verdict({}, src, store_path=store) == 1
    assert "LOI" in capsys.readouterr().out
    assert not store.exists()


def test_cmd_verdict_missing_file_returns_1(tmp_path, capsys):
    assert cmd_verdict({}, tmp_path / "khong-co.json",
                       store_path=tmp_path / "store.json") == 1
    assert "LOI" in capsys.readouterr().out


# --- cmd_synthesize ---

def _sim_cfg():
    return {"data": {"provider": "simulated",
                     "symbols": {"forex": ["EURUSD"]}}}


def test_cmd_synthesize_simulated(tmp_path):
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(), store)
    out_path = tmp_path / "synthesis.json"
    assert cmd_synthesize(_sim_cfg(), "forex", store_path=store,
                          out_path=out_path) == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["desk"] == "forex"
    assert len(data["results"]) == 1
    row = data["results"][0]
    assert row["symbol"] == "EURUSD"
    assert row["ta_action"] in ("BUY", "SELL", "HOLD")
    assert row["recommendation"] in ("MUA", "BAN", "CHO", "KHONG MUA")
    assert 0.0 <= row["size"] <= 1.0
    assert "PTKT" in row["rationale"] and "PTCB" in row["rationale"]
    assert row["fa_status"] == "ok"


def test_cmd_synthesize_no_mt5_fails_cleanly(tmp_path):
    cfg = {"data": {"provider": "mt5",
                    "symbols": {"forex": ["EURUSD"]}},
           "mt5": {"login": 0, "server": "", "timeframe": "M15"}}
    out_path = tmp_path / "synthesis.json"
    assert cmd_synthesize(cfg, "forex",
                          store_path=tmp_path / "verdicts.json",
                          out_path=out_path) == 1
