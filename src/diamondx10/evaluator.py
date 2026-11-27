"""Danh gia ket qua tin hieu (TA learning loop — EVALUATOR).

Doc ket qua tin hieu tu decisions/signal-outcomes.jsonl (1 JSON / dong,
xem outcomes.py — ghi boi recorder) va cham vao nen that trong kho
lich su (HistoryStore, lay tu `backfill` truoc) de xac dinh moi tin
hieu thang / thua / het han trong cua so `learning.outcome_window_bars`
bar M15.

- KHONG bao gio goi MT5 live o day: neu kho lich su chua co bar cho
  symbol thi ban ghi do duoc dem vao skipped_no_bars (chay `backfill`
  truoc roi chay lai `evaluate-signals`).
- Chi dung stdlib.
- Ban ghi da co truong `outcome` thi bo qua, khong danh gia lai.
- File da danh gia (decisions/signal-outcomes-evaluated.jsonl) la
  viet lai toan bo, thu tu xac dinh theo created_utc roi id, dedupe
  theo id.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTCOMES = REPO_ROOT / "decisions" / "signal-outcomes.jsonl"
DEFAULT_EVALUATED = (REPO_ROOT / "decisions"
                     / "signal-outcomes-evaluated.jsonl")

DEFAULT_WINDOW_BARS = 20
TIMEFRAME = "M15"


def _parse_time(value):
    """Chuyen gia tri thoi gian cua ban ghi ve epoch UTC (int).

    Chap nhan: epoch int/float, chuoi ISO (co/khong co 'Z'), datetime.
    Tra None neu khong doc duoc.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    return None


def _bar_fields(bar):
    """Lay (time, open, high, low, close) tu 1 bar.

    Bar cua HistoryStore la dict {time, open, high, low, close,
    volume}; chap nhan ca tuple (time, open, high, low, close[, ...]).
    Tra None neu bar khong du truong so.
    """
    try:
        if isinstance(bar, dict):
            time = _parse_time(bar.get("time"))
            values = [float(bar[k]) for k in ("open", "high", "low", "close")]
        else:
            time = _parse_time(bar[0])
            values = [float(v) for v in bar[1:5]]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if time is None:
        return None
    return (time, values[0], values[1], values[2], values[3])


def _positive_number(value):
    """So thuc > 0, hoac None. Bool / chuoi / None deu khong hop le."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _signal_time(record):
    """Epoch cua tin hieu: truong `time`, fallback `created_utc`."""
    epoch = _parse_time(record.get("time"))
    if epoch is None:
        epoch = _parse_time(record.get("created_utc"))
    return epoch


def score_signal(record, bars, window_bars=20):
    """Cham 1 tin hieu tren cac bar SAU thoi diem tin hieu.

    bars: list bar (dict hoac tuple) theo thu tu thoi gian; bar 0 la
    bar dau tien co time >= thoi diem tin hieu. window_bars: so bar
    toi da xet (mac dinh 20 bar M15).

    BUY: thang neu high >= tp truoc khi low <= sl; thua neu low <= sl
    truoc. SELL: nguoc lai. Neu ca TP va SL deu cham trong CUNG 1 bar
    (khong biet thu tu trong bar) thi tinh la thua — cach tinh bao thu.

    Het window ma chua cham TP/SL: outcome "timeout", ret tinh theo
    gia dong cua bar cuoi cua so. Neu khong du bar (it hon window):
    van la "timeout", bars_held = so bar co san, ret theo close cuoi
    cung co san.

    Tra dict {outcome, bars_held, mfe, mae, ret} hoac None khi:
    - ban ghi thieu / sai entry, sl, tp (thieu hoac khong phai so > 0),
      action khong phai BUY/SELL, hoac khong doc duoc thoi diem tin hieu;
    - khong co bar nao o / sau thoi diem tin hieu.
    mfe/mae tinh theo don vi gia (>= 0). ret la phan tram dang phan so,
    duong = co loi theo huong tin hieu.
    """
    try:
        window = max(1, int(window_bars))
    except (TypeError, ValueError):
        window = DEFAULT_WINDOW_BARS
    action = (record.get("action") or "")
    if isinstance(action, str):
        action = action.strip().upper()
    if action not in ("BUY", "SELL"):
        return None
    entry = _positive_number(record.get("entry"))
    sl = _positive_number(record.get("sl"))
    tp = _positive_number(record.get("tp"))
    if entry is None or sl is None or tp is None:
        return None
    signal_epoch = _signal_time(record)
    if signal_epoch is None:
        return None
    is_buy = action == "BUY"
    # Chi xet bar tu thoi diem tin hieu tro di, theo thu tu thoi gian.
    usable = []
    for bar in bars or []:
        fields = _bar_fields(bar)
        if fields is None:
            continue
        if fields[0] >= signal_epoch:
            usable.append(fields)
    usable.sort(key=lambda b: b[0])
    if not usable:
        return None
    window_bars_list = usable[:window]
    mfe = 0.0
    mae = 0.0
    for idx, (_time, _open, high, low, _close) in enumerate(window_bars_list):
        if is_buy:
            mfe = max(mfe, high - entry)
            mae = max(mae, entry - low)
            hit_tp = high >= tp
            hit_sl = low <= sl
        else:
            mfe = max(mfe, entry - low)
            mae = max(mae, high - entry)
            hit_tp = low <= tp
            hit_sl = high >= sl
        if hit_tp or hit_sl:
            # Ca 2 cham cung bar -> tinh thua (bao thu).
            won = hit_tp and not hit_sl
            if won:
                ret = (tp - entry) / entry if is_buy else (entry - tp) / entry
                outcome = "win"
            else:
                ret = (sl - entry) / entry if is_buy else (entry - sl) / entry
                outcome = "loss"
            return {"outcome": outcome, "bars_held": idx + 1,
                    "mfe": max(0.0, float(mfe)),
                    "mae": max(0.0, float(mae)), "ret": float(ret)}
    last_close = window_bars_list[-1][4]
    if is_buy:
        ret = (last_close - entry) / entry
    else:
        ret = (entry - last_close) / entry
    return {"outcome": "timeout", "bars_held": len(window_bars_list),
            "mfe": max(0.0, float(mfe)), "mae": max(0.0, float(mae)),
            "ret": float(ret)}


def _learning_window(cfg, window_bars):
    """Cua so danh gia: --window > config learning.outcome_window_bars > 20."""
    if window_bars is not None:
        try:
            return max(1, int(window_bars))
        except (TypeError, ValueError):
            pass
    learning = (cfg or {}).get("learning") or {}
    try:
        return max(1, int(learning.get("outcome_window_bars")
                           or DEFAULT_WINDOW_BARS))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_BARS


def _load_outcomes(path):
    """Doc file JSONL. Tra (records, bad_lines): dong JSON hong dem
    vao bad_lines, khong lam hong ca file."""
    records = []
    bad_lines = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                bad_lines += 1
                continue
            if not isinstance(record, dict):
                bad_lines += 1
                continue
            records.append(record)
    return records, bad_lines


def evaluate(outcomes_path, store, cfg, *, evaluated_path=None,
             window_bars=None):
    """Danh gia cac ban ghi tin hieu chua co outcome.

    outcomes_path: file JSONL goc (mac dinh
    decisions/signal-outcomes.jsonl). store: HistoryStore (co the la
    None — khi do moi ban ghi deu thieu bar). evaluated_path: file
    dich (mac dinh decisions/signal-outcomes-evaluated.jsonl), viet
    lai toan bo chi voi cac ban ghi DA CO outcome, thu tu xac dinh
    theo created_utc roi id, dedupe theo id.

    Khong bao gio raise vi 1 ban ghi hong hay thieu lich su cua 1
    symbol — dem vao skipped_bad / skipped_no_bars va chay tiep.
    File goc thieu / rong -> tra toan 0, khong ghi file dich.

    Tra {evaluated, skipped_already, skipped_no_bars, skipped_bad,
    wins, losses, timeouts} (wins/losses/timeouts chi dem cac ban ghi
    MOI danh gia trong lan chay nay).
    """
    summary = {"evaluated": 0, "skipped_already": 0, "skipped_no_bars": 0,
               "skipped_bad": 0, "wins": 0, "losses": 0, "timeouts": 0}
    path = Path(outcomes_path) if outcomes_path is not None else DEFAULT_OUTCOMES
    if not path.exists():
        return summary
    try:
        records, bad_lines = _load_outcomes(path)
    except (OSError, ValueError):
        return summary
    summary["skipped_bad"] += bad_lines
    if not records:
        return summary
    window = _learning_window(cfg, window_bars)
    # Dedupe theo id (giua lai ban dau tien); ban ghi khong co id thi
    # giu nguyen (khoa rieng theo vi tri).
    seen_ids = set()
    unique = []
    for idx, record in enumerate(records):
        rid = record.get("id")
        key = rid if rid else f"__noid_{idx}"
        if key in seen_ids:
            continue
        seen_ids.add(key)
        unique.append(record)
    evaluated_records = []
    for record in unique:
        if record.get("outcome"):
            summary["skipped_already"] += 1
            evaluated_records.append(record)
            continue
        try:
            symbol = record.get("symbol")
            if not symbol or not isinstance(symbol, str):
                summary["skipped_bad"] += 1
                continue
            signal_epoch = _signal_time(record)
            if signal_epoch is None:
                summary["skipped_bad"] += 1
                continue
            bars = None
            if store is not None:
                try:
                    bars = store.get_bars(symbol, TIMEFRAME,
                                          start=signal_epoch)
                except Exception:  # noqa: BLE001 — loi kho thi dem thieu bar
                    bars = None
            if not bars:
                summary["skipped_no_bars"] += 1
                continue
            result = score_signal(record, bars, window_bars=window)
        except Exception:  # noqa: BLE001 — ban ghi hong thi dem, khong crash
            summary["skipped_bad"] += 1
            continue
        if result is None:
            summary["skipped_bad"] += 1
            continue
        scored = dict(record)
        scored.update(result)
        scored["evaluated_utc"] = datetime.now(timezone.utc).isoformat()
        evaluated_records.append(scored)
        summary["evaluated"] += 1
        if result["outcome"] == "win":
            summary["wins"] += 1
        elif result["outcome"] == "loss":
            summary["losses"] += 1
        else:
            summary["timeouts"] += 1
    evaluated_records.sort(
        key=lambda r: (str(r.get("created_utc") or ""), str(r.get("id") or "")))
    out_path = (Path(evaluated_path) if evaluated_path is not None
                else DEFAULT_EVALUATED)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in evaluated_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return summary
