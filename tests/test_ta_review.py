"""Test phan tich ket qua + de xuat tinh chinh TA (ta_review.py).

Chi dung ban ghi FAKE (so lieu tu viet tay, khong MT5 / khong kho
lich su that). chat_id / login trong file nay (neu co) deu la so gia.
"""
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import main
from diamondx10.ta_review import (
    NO_HISTORY_REASON,
    apply_proposals,
    format_report,
    propose,
    review,
    write_proposals,
)

# Config gia cho test: chi 1 symbol, mau toi thieu 5 de lat cat nho
# cung du dieu kien sinh de xuat (test rieng phan "chua du mau" o duoi).
CFG = {
    "data": {"symbols": {"forex": ["EURUSD"]}},
    "strategy": {
        "sma_fast": 5, "sma_slow": 20, "rsi_period": 14,
        "rsi_buy_low": 50, "rsi_buy_high": 70,
        "rsi_sell_low": 30, "rsi_sell_high": 50,
        "rsi_extreme_high": 80, "rsi_extreme_low": 20,
        "atr_period": 14, "atr_sl_mult": 1.5,
        "tp_mult": 2.0, "trail_mult": 1.5, "adx_min": 0,
    },
    "learning": {"min_sample_for_proposal": 5},
}
CFG_DEFAULT_MIN = {"data": {"symbols": {"forex": ["EURUSD"]}}}


def _rec(symbol="EURUSD", outcome="win", ret=0.02, rsi=60.0, adx=30.0,
         patterns=None, fa_dir=None, fa_conf=None, size_scale=1.0,
         time="2026-11-27T10:00:00Z", desk="forex", action="BUY",
         soft_rules=None):
    ctx = {"rsi": rsi, "adx": adx, "patterns": patterns or []}
    if fa_dir is not None:
        ctx["fa"] = {"direction": fa_dir, "confidence": fa_conf}
    if soft_rules is not None:
        ctx["soft_rules"] = soft_rules
    return {"id": f"{symbol}-{outcome}-{ret}-{rsi}-{adx}",
            "desk": desk, "symbol": symbol, "action": action,
            "status": "TRADED", "entry": 1.0, "sl": 0.95, "tp": 1.1,
            "volume": 0.01, "risk_usd": 10.0, "manager": "Yuling Pan",
            "time": time, "size_scale": size_scale, "context": ctx,
            "params_hash": "fake", "outcome": outcome, "bars_held": 5,
            "mfe": 0.03, "mae": -0.01, "ret": ret,
            "evaluated_utc": "2026-11-27T12:00:00Z"}


def _hand_computed_records():
    """7 ban ghi EURUSD: 4 thang (0.02, 0.04, 0.01, 0.03), 2 thua
    (-0.02, -0.04), 1 timeout (0.0)."""
    return [
        _rec(outcome="win", ret=0.02),
        _rec(outcome="win", ret=0.04),
        _rec(outcome="win", ret=0.01),
        _rec(outcome="win", ret=0.03),
        _rec(outcome="loss", ret=-0.02),
        _rec(outcome="loss", ret=-0.04),
        _rec(outcome="timeout", ret=0.0),
    ]


def _proposal_records():
    """20 ban ghi EURUSD: RSI 50-70 thang 8/10, RSI 30-50 thang 2/10;
    ADX <20 thang 2/10, ADX 25+ thang 8/10 (2 lat cat trung nhau de
    ca 2 de xuat RSI + ADX deu du mau)."""
    records = []
    for i in range(8):
        records.append(_rec(outcome="win", ret=0.02, rsi=60.0, adx=30.0,
                            time=f"2026-11-27T10:{i:02d}:00Z"))
    for i in range(2):
        records.append(_rec(outcome="loss", ret=-0.01, rsi=60.0, adx=30.0,
                            time=f"2026-11-27T11:{i:02d}:00Z"))
    for i in range(2):
        records.append(_rec(outcome="win", ret=0.02, rsi=40.0, adx=10.0,
                            time=f"2026-11-27T12:{i:02d}:00Z"))
    for i in range(8):
        records.append(_rec(outcome="loss", ret=-0.01, rsi=40.0, adx=10.0,
                            time=f"2026-11-27T13:{i:02d}:00Z"))
    return records


# --- Metrics: tinh tay ---------------------------------------------------

def test_metrics_hand_computed():
    report = review(_hand_computed_records(), CFG_DEFAULT_MIN)
    overall = report["overall"]
    assert report["n"] == 7
    assert overall["wins"] == 4
    assert overall["losses"] == 2
    assert overall["timeouts"] == 1
    # Win rate = thang / (thang + thua), timeout LOAI khoi mau so.
    assert overall["win_rate"] == pytest.approx(4 / 6)
    # avg thang = (0.02+0.04+0.01+0.03)/4 = 0.025
    assert overall["avg_win"] == pytest.approx(0.025)
    # avg thua = (-0.02-0.04)/2 = -0.03
    assert overall["avg_loss"] == pytest.approx(-0.03)
    # Profit factor = tong thang / tong thua = 0.10 / 0.06
    assert overall["profit_factor"] == pytest.approx(0.10 / 0.06)
    # Expectancy = (0.10 - 0.06) / 6 lenh da dong
    assert overall["expectancy"] == pytest.approx(0.04 / 6)
    assert report["by_symbol"]["EURUSD"]["n"] == 7
    assert report["by_desk"]["forex"]["n"] == 7


def test_win_rate_none_and_profit_factor_none_without_losses():
    records = [_rec(outcome="win", ret=0.02), _rec(outcome="timeout", ret=0.0)]
    overall = review(records, CFG_DEFAULT_MIN)["overall"]
    assert overall["win_rate"] == pytest.approx(1.0)
    assert overall["profit_factor"] is None  # khong co lenh thua
    assert overall["avg_loss"] is None


def test_missing_context_keys_never_crash():
    records = [{"symbol": "EURUSD", "desk": "forex", "action": "BUY",
                "outcome": "win", "ret": 0.01, "time": None},
               {"symbol": "EURUSD", "outcome": "loss", "ret": -0.01}]
    report = review(records, CFG_DEFAULT_MIN)
    assert report["n"] == 2
    assert report["overall"]["wins"] == 1
    assert format_report(report)  # in duoc, khong crash


def test_min_sample_default_20_when_learning_section_missing():
    report = review(_hand_computed_records(), {})
    assert report["min_sample"] == 20
    assert report["overall"]["status"] == "chua du mau"


# --- Lat cat: n nao cung co, nho thi "chua du mau", khong de xuat -------

def test_every_slice_carries_n():
    report = review(_hand_computed_records(), CFG_DEFAULT_MIN)
    bd = report["breakdowns"]
    for section in ("rsi_band", "adx_regime", "pattern", "fa_agreement",
                    "session_hour"):
        for label, metrics in bd[section].items():
            assert "n" in metrics, (section, label)
            assert metrics["n"] >= 0
    for name, pair in bd["soft_rule"].items():
        assert pair["fired"]["n"] + pair["not_fired"]["n"] == report["n"]
    for section in ("size_scale", "fa_confidence"):
        for label, metrics in report["calibration"][section].items():
            assert "n" in metrics


def test_small_slice_labelled_chua_du_mau_and_yields_no_proposal():
    # Lat cat RSI 50-70 chi co 4 ban ghi thang 100%, RSI 30-50 co 8
    # ban ghi thua het — chenh lech lon NHUNG lat cat tot n=4 < 5
    # nen khong duoc sinh de xuat RSI. ADX dong nhat (30) nen khong
    # co lat cat yeu; thang trung binh > thua trung binh nen khong
    # co de xuat ATR.
    records = ([_rec(outcome="win", ret=0.05, rsi=60.0, adx=30.0)
                for _ in range(4)]
               + [_rec(outcome="loss", ret=-0.01, rsi=40.0, adx=30.0)
                  for _ in range(8)])
    report = review(records, CFG)
    assert report["breakdowns"]["rsi_band"]["50-70"]["n"] == 4
    assert report["breakdowns"]["rsi_band"]["50-70"]["status"] == "chua du mau"
    assert report["breakdowns"]["rsi_band"]["30-50"]["status"] == "du mau"
    assert propose(report, records, CFG) == []
    text = format_report(report)
    assert "chua du mau" in text


def test_soft_rule_fired_vs_not_fired_slices():
    rule = {"name": "test-rule", "fired": True, "effect": "block"}
    records = ([_rec(outcome="win", ret=0.02, soft_rules=[rule])
                for _ in range(3)]
               + [_rec(outcome="loss", ret=-0.01,
                       soft_rules=[{"name": "test-rule", "fired": False,
                                    "effect": "block"}])
                  for _ in range(3)])
    bd = review(records, CFG)["breakdowns"]
    assert bd["soft_rule"]["test-rule"]["fired"]["n"] == 3
    assert bd["soft_rule"]["test-rule"]["not_fired"]["n"] == 3


def test_fa_agreement_and_session_hour_slices():
    records = [
        _rec(outcome="win", ret=0.02, fa_dir="buy", fa_conf=0.8,
             time="2026-11-27T02:00:00Z"),
        _rec(outcome="loss", ret=-0.01, fa_dir="sell", fa_conf=0.4,
             time="2026-11-27T10:00:00Z"),
        _rec(outcome="win", ret=0.02, time="2026-11-27T20:00:00Z"),
    ]
    bd = review(records, CFG)["breakdowns"]
    assert bd["fa_agreement"]["dong thuan"]["n"] == 1
    assert bd["fa_agreement"]["mau thuan"]["n"] == 1
    assert bd["fa_agreement"]["khong co FA"]["n"] == 1
    assert bd["session_hour"]["0-7"]["n"] == 1
    assert bd["session_hour"]["8-15"]["n"] == 1
    assert bd["session_hour"]["16-23"]["n"] == 1
    cal = review(records, CFG)["calibration"]
    assert cal["fa_confidence"]["cao >=0.6"]["n"] == 1
    assert cal["fa_confidence"]["thap <0.6"]["n"] == 1


# --- Bao cao in ----------------------------------------------------------

def test_overfitting_warning_always_present():
    text = format_report(review(_hand_computed_records(), CFG_DEFAULT_MIN))
    assert "CANH BAO OVERFITTING" in text
    assert "khong dam bao ket qua tuong lai" in text
    assert "n=7" in text
    assert "EURUSD" in text
    assert "forex" in text


# --- De xuat --------------------------------------------------------------

def test_proposals_carry_evidence_and_unvalidated_without_history():
    records = _proposal_records()
    report = review(records, CFG)
    proposals = propose(report, records, CFG)
    assert len(proposals) == 2  # toi da 2 / symbol
    params = {p["param_or_rule"] for p in proposals}
    assert "rsi_buy_low" in params
    assert "soft_rule:adx>=20" in params
    for proposal in proposals:
        assert proposal["symbol"] == "EURUSD"
        assert "current_value" in proposal
        assert "proposed_value" in proposal
        assert proposal["rationale"]
        ev = proposal["evidence"]
        assert set(ev) >= {"metric", "before", "after", "n"}
        assert ev["n"] >= 5
        assert ev["metric"] == "win_rate"
        assert proposal["validated"] is False
        assert proposal["ready"] is False
        oos = proposal["oos_validation"]
        assert oos["validated"] is False
        assert oos["reason"] == NO_HISTORY_REASON
        assert oos["oos_n"] == 0
    rsi_proposal = next(p for p in proposals
                        if p["param_or_rule"] == "rsi_buy_low")
    assert rsi_proposal["current_value"] == 50
    assert rsi_proposal["proposed_value"] == 55
    # Evidence: truoc = win rate RSI 30-50 (0.2), sau = RSI 50-70 (0.8).
    assert rsi_proposal["evidence"]["before"] == pytest.approx(0.2)
    assert rsi_proposal["evidence"]["after"] == pytest.approx(0.8)


def test_propose_at_most_two_per_symbol_and_symbol_below_min_skipped():
    records = _proposal_records()
    small = [_rec(symbol="XAUUSD", outcome="win", ret=0.02)
             for _ in range(3)]
    all_records = records + small
    report = review(all_records, CFG)
    assert report["by_symbol"]["XAUUSD"]["status"] == "chua du mau"
    proposals = propose(report, all_records, CFG)
    assert all(p["symbol"] == "EURUSD" for p in proposals)
    assert len(proposals) <= 2


def test_propose_with_history_returns_oos_validation_shape():
    # Bar gia (khong phai MT5 / kho that): xu huong len deu + dao
    # dong nhe, du chay walk-forward. Chi kiem tra hinh dang ket
    # qua OOS (validated la bool, co oos_n), khong khang dinh thang.
    bars = []
    price = 1.0
    for i in range(120):
        price += 0.0008 if i % 2 == 0 else -0.0003
        bars.append({"time": 1700000000 + i * 900, "open": price,
                     "high": price + 0.0005, "low": price - 0.0005,
                     "close": price, "volume": 0.0})
    records = _proposal_records()
    report = review(records, CFG)
    proposals = propose(report, records, CFG,
                        history={"EURUSD": bars})
    assert proposals
    for proposal in proposals:
        oos = proposal["oos_validation"]
        assert set(oos) >= {"oos_win_rate", "oos_return", "oos_n",
                            "validated"}
        assert isinstance(oos["validated"], bool)
        assert isinstance(oos["oos_n"], int)


# --- Ghi / ap de xuat ------------------------------------------------------

def test_write_proposals_yaml_roundtrip(tmp_path):
    records = _proposal_records()
    proposals = propose(review(records, CFG), records, CFG)
    path = write_proposals(proposals, tmp_path / "props.yaml")
    text = Path(path).read_text(encoding="utf-8")
    assert "CHUA KIEM CHUNG" in text
    data = yaml.safe_load(text)
    assert data["strategy"]["per_symbol"]["EURUSD"]["rsi_buy_low"] == 55
    rules = data["strategy"]["soft_rules"]
    assert rules[0]["name"] == "eurusd-adx-yeu-block"
    assert rules[0]["condition"] == {"type": "adx_max", "value": 20}
    assert rules[0]["effect"] == "block"


def _local_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "fund:\n  name: DiamondX10\nrisk:\n  max_risk_per_trade_pct: 1.0\n"
        "strategy:\n  rsi_buy_low: 50\n  rsi_buy_high: 70\n"
        "  atr_sl_mult: 1.5\n  tp_mult: 2.0\n"
        "  per_symbol:\n    EURUSD: {rsi_buy_low: 50}\n",
        encoding="utf-8")
    return path


def _proposals_file(tmp_path):
    records = _proposal_records()
    proposals = propose(review(records, CFG), records, CFG)
    return write_proposals(proposals, tmp_path / "props.yaml")


def test_apply_refuses_without_confirmation(tmp_path):
    config_path = _local_config(tmp_path)
    props = _proposals_file(tmp_path)
    changed, skipped = apply_proposals(props, config_path, confirm="NO")
    assert changed == []
    assert skipped  # ly do chua xac nhan
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["strategy"]["per_symbol"]["EURUSD"]["rsi_buy_low"] == 50
    assert "soft_rules" not in data["strategy"]


def test_apply_refuses_config_example_yaml(tmp_path):
    props = _proposals_file(tmp_path)
    example = tmp_path / "config.example.yaml"
    example.write_text("strategy: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="config.example.yaml"):
        apply_proposals(props, example, confirm="APPLY")
    assert yaml.safe_load(example.read_text(encoding="utf-8")) == {
        "strategy": {}}


def test_apply_with_confirmation_patches_only_allowed(tmp_path):
    config_path = _local_config(tmp_path)
    props_path = tmp_path / "props.yaml"
    props_path.write_text(
        "# de xuat gia\n"
        "strategy:\n"
        "  per_symbol:\n"
        "    EURUSD: {rsi_buy_low: 55}\n"
        "  soft_rules:\n"
        "    - {name: eurusd-adx-yeu-block, scope: {symbol: EURUSD},"
        " condition: {type: adx_max, value: 20}, effect: block}\n"
        "  tp_mult: 9.9\n"
        "risk:\n  max_risk_per_trade_pct: 99.0\n",
        encoding="utf-8")
    changed, skipped = apply_proposals(props_path, config_path,
                                       confirm="APPLY")
    assert "strategy.per_symbol.EURUSD.rsi_buy_low" in changed
    assert "strategy.soft_rules.eurusd-adx-yeu-block" in changed
    assert any("risk" in s["key"] for s in skipped)
    assert any("tp_mult" in s["key"] for s in skipped)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["strategy"]["per_symbol"]["EURUSD"]["rsi_buy_low"] == 55
    assert data["strategy"]["soft_rules"][0]["name"] == "eurusd-adx-yeu-block"
    # Khoa khong lien quan giu nguyen.
    assert data["strategy"]["tp_mult"] == 2.0
    assert data["risk"]["max_risk_per_trade_pct"] == 1.0
    assert data["fund"]["name"] == "DiamondX10"


# --- CLI ------------------------------------------------------------------

def _write_evaluated_jsonl(tmp_path):
    path = tmp_path / "signal-outcomes-evaluated.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in _proposal_records():
            f.write(json.dumps(record) + "\n")
    return path


def test_cli_exits_1_on_missing_evaluated_file(tmp_path):
    assert main(["ta-review", "--evaluated",
                 str(tmp_path / "khong-co.jsonl")]) == 1


def test_cli_exits_1_on_empty_evaluated_file(tmp_path):
    empty = tmp_path / "rong.jsonl"
    empty.write_text("", encoding="utf-8")
    assert main(["ta-review", "--evaluated", str(empty)]) == 1


def test_cli_prints_report_and_writes_proposals(tmp_path, capsys):
    evaluated = _write_evaluated_jsonl(tmp_path)
    props = tmp_path / "ta-tuning-proposals-test.yaml"
    rc = main(["ta-review", "--evaluated", str(evaluated),
               "--proposals", str(props)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TA REVIEW" in out
    assert "EURUSD" in out
    assert "CANH BAO OVERFITTING" in out
    assert props.exists()
    data = yaml.safe_load(props.read_text(encoding="utf-8"))
    assert "strategy" in data


def test_cli_no_proposals_prints_report_only(tmp_path, capsys):
    evaluated = _write_evaluated_jsonl(tmp_path)
    rc = main(["ta-review", "--evaluated", str(evaluated),
               "--no-proposals"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TA REVIEW" in out
    assert "De xuat tinh chinh" not in out
