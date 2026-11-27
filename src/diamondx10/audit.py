"""Audit log (Phase F): nhat ky append-only cho cac su kien van hanh.

File decisions/audit-log.jsonl — moi dong 1 JSON:
  {ts (ISO UTC), actor, event, details}
Chi ghi them (append), khong sua/xoa dong cu. File chua co thi doc
tra [] — khong crash. Dong hong (khong phai JSON) thi bo qua khi doc.

Su kien duoc ghi (xem docs/fund-risk-ops.md):
  KILL_SWITCH_ON / KILL_SWITCH_OFF, FUND_LIMIT_BLOCKED,
  LIVE_CYCLE_STARTED / LIVE_CYCLE_STOPPED, REPORT_GENERATED.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG = (Path(__file__).resolve().parents[2] / "decisions"
             / "audit-log.jsonl")


def _path(path=None):
    return Path(path) if path is not None else AUDIT_LOG


def log_event(event, details=None, actor="system", path=None):
    """Ghi them 1 su kien vao audit log. Tra dict su kien vua ghi."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(),
             "actor": actor, "event": event, "details": details or {}}
    file_path = _path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_events(limit=None, path=None):
    """Doc cac su kien, MOI NHAT LEN DAU. File chua co thi []. Dong
    hong thi bo qua. limit=None thi doc het."""
    file_path = _path(path)
    if not file_path.exists():
        return []
    events = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    events.reverse()
    if limit is not None:
        return events[:int(limit)]
    return events
