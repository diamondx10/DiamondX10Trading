"""Test Phase F — audit log (audit.py + kill switch ghi audit).

Append-only JSONL, doc nguoc (moi nhat len dau), file thieu -> [].
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import audit, killswitch


def test_read_events_missing_file_returns_empty(tmp_path):
    assert audit.read_events(path=tmp_path / "audit-log.jsonl") == []


def test_log_and_read_newest_first(tmp_path):
    path = tmp_path / "audit-log.jsonl"
    audit.log_event("A", {"n": 1}, actor="tester", path=path)
    audit.log_event("B", {"n": 2}, actor="tester", path=path)
    audit.log_event("C", {"n": 3}, actor="tester", path=path)
    events = audit.read_events(path=path)
    assert [e["event"] for e in events] == ["C", "B", "A"]
    assert events[0]["details"] == {"n": 3}
    assert events[0]["actor"] == "tester"
    assert events[0]["ts"]  # co moc thoi gian ISO
    # Moi dong 1 JSON hop le (append-only JSONL).
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    assert json.loads(lines[0])["event"] == "A"


def test_read_events_limit(tmp_path):
    path = tmp_path / "audit-log.jsonl"
    for i in range(5):
        audit.log_event(f"E{i}", path=path)
    events = audit.read_events(limit=2, path=path)
    assert [e["event"] for e in events] == ["E4", "E3"]


def test_read_events_skips_bad_lines(tmp_path):
    path = tmp_path / "audit-log.jsonl"
    path.write_text('{"event": "OK"}\nkhong phai json\n{"event": "OK2"}\n',
                    encoding="utf-8")
    events = audit.read_events(path=path)
    assert [e["event"] for e in events] == ["OK2", "OK"]


def test_kill_switch_engage_writes_audit(tmp_path, monkeypatch):
    ks_path = tmp_path / "kill-switch.json"
    audit_path = tmp_path / "audit-log.jsonl"
    monkeypatch.setattr(killswitch, "KILL_SWITCH_FILE", ks_path)
    monkeypatch.setattr(audit, "AUDIT_LOG", audit_path)
    killswitch.engage("test bat", by="Phu")
    killswitch.disengage(by="Phu")
    events = audit.read_events(path=audit_path)
    assert [e["event"] for e in events] == [
        "KILL_SWITCH_OFF", "KILL_SWITCH_ON"]
    assert events[1]["details"] == {"reason": "test bat", "by": "Phu"}
    assert events[1]["actor"] == "Phu"
