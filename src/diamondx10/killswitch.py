"""Kill switch (Phase F): nut dung khan cap cho toan bo giao dich.

Trang thai luu file JSON decisions/kill-switch.json:
  {engaged: bool, engaged_at: ISO UTC, reason: str, by: str}
File chua co = chua bat. File hong (doc khong duoc) thi coi nhu chua
bat — khong bao gio crash vong live vi file trang thai.

Khi bat:
  - run_live_cycle chi doi chieu/dong vi the mo theo SL/TP da co,
    KHONG mo lenh moi (process_symbol tra BLOCKED-KILL-SWITCH).
  - mt5-trade dung chung process_symbol nen cung bi chan theo.
Bat/tat deu ghi audit (KILL_SWITCH_ON/OFF) va in ro o CLI.
Ai cung bat duoc bang lenh `kill-switch on` — nguoi bat ghi ten vao
`by` de truy vet (xem docs/fund-risk-ops.md).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

KILL_SWITCH_FILE = (Path(__file__).resolve().parents[2] / "decisions"
                    / "kill-switch.json")


def _path(path=None):
    return Path(path) if path is not None else KILL_SWITCH_FILE


def _audit_path(path, audit_path):
    """Duong dan audit log: truyen ro thi dung; khong thi cung thu muc
    voi file trang thai (de test dung thu muc tam)."""
    if audit_path is not None:
        return audit_path
    if path is not None:
        return Path(path).parent / "audit-log.jsonl"
    return None


def status(path=None):
    """Trang thai hien tai dang dict; file chua co thi tra mac dinh tat."""
    file_path = _path(path)
    if not file_path.exists():
        return {"engaged": False, "engaged_at": None, "reason": "",
                "by": ""}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"engaged": False, "engaged_at": None, "reason": "",
                "by": ""}
    return {"engaged": bool(data.get("engaged", False)),
            "engaged_at": data.get("engaged_at"),
            "reason": data.get("reason") or "",
            "by": data.get("by") or ""}


def is_engaged(path=None):
    """True neu kill switch dang bat."""
    return status(path)["engaged"]


def _write(state, path):
    file_path = _path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return state


def engage(reason, by="operator", path=None, audit_path=None):
    """Bat kill switch; ghi audit KILL_SWITCH_ON. Tra trang thai moi."""
    state = {"engaged": True,
             "engaged_at": datetime.now(timezone.utc).isoformat(),
             "reason": reason or "",
             "by": by or "operator"}
    _write(state, path)
    from . import audit as audit_mod  # import cham: tranh vong tron

    audit_mod.log_event("KILL_SWITCH_ON",
                        {"reason": state["reason"], "by": state["by"]},
                        actor=state["by"],
                        path=_audit_path(path, audit_path))
    return state


def disengage(by="operator", path=None, audit_path=None):
    """Tat kill switch; ghi audit KILL_SWITCH_OFF. Tra trang thai moi."""
    state = {"engaged": False, "engaged_at": None, "reason": "",
             "by": by or "operator"}
    _write(state, path)
    from . import audit as audit_mod  # import cham: tranh vong tron

    audit_mod.log_event("KILL_SWITCH_OFF", {"by": state["by"]},
                        actor=state["by"],
                        path=_audit_path(path, audit_path))
    return state
