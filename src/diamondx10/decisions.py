"""Ghi quyet dinh mua/ban vao decisions/decisions-log.csv.
Moi quyet dinh deu duoc thong bao — file nay la ban ghi chinh thuc."""
import csv
import json
from datetime import date
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "decisions" / "decisions-log.csv"
HEADER = ["date", "desk", "symbol", "action", "reason", "manager"]

# Trang thai von + vi the mo (Phase 4): luu duong cong von cua
# DrawdownGuard va danh sach vi the dang mo. File RUNTIME — khong
# commit (da co trong .gitignore).
EQUITY_STATE = Path(__file__).resolve().parents[2] / "decisions" / "equity-state.json"


def log_decision(symbol, action, reason, desk="DEMO", manager=""):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        w.writerow([date.today().isoformat(), desk, symbol, action, reason, manager])
    return LOG


def load_equity_state(path=None):
    """Doc trang thai von/vi the (Phase 4). Tra dict {"guard": ..., "positions": [...]}
    hoac None neu chua co file (chay lan dau)."""
    path = Path(path) if path is not None else EQUITY_STATE
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_equity_state(state, path=None):
    """Ghi trang thai von/vi the (Phase 4) xuong JSON."""
    path = Path(path) if path is not None else EQUITY_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


def count_trades_today(symbol, date=None, log_path=None):
    """So lenh MOI da dat cho `symbol` trong ngay `date` (mac dinh hom nay),
    dem theo decisions log. Chi dem action BUY/SELL that — dry-run
    (DRY-RUN-BUY/...) va cac BLOCKED-*/CLOSE khong dem. Dung cho gioi han
    Q4: toi da 1 lenh moi / symbol / ngay (Phase 4)."""
    day = date
    if day is None:
        from datetime import date as _date_cls
        day = _date_cls.today().isoformat()
    path = Path(log_path) if log_path is not None else LOG
    if not path.exists():
        return 0
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("symbol") == symbol and row.get("date") == day
                    and row.get("action") in ("BUY", "SELL")):
                count += 1
    return count
