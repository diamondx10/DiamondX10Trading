"""Ghi quyet dinh mua/ban vao decisions/decisions-log.csv.
Moi quyet dinh deu duoc thong bao — file nay la ban ghi chinh thuc."""
import csv
from datetime import date
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "decisions" / "decisions-log.csv"
HEADER = ["date", "desk", "symbol", "action", "reason", "manager"]


def log_decision(symbol, action, reason, desk="DEMO", manager=""):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        w.writerow([date.today().isoformat(), desk, symbol, action, reason, manager])
    return LOG
