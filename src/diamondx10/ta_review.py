"""Phan tich ket qua tin hieu + de xuat tinh chinh TA (TA learning loop).

Doc cac ban ghi DA DANH GIA (decisions/signal-outcomes-evaluated.jsonl
— ghi boi evaluator.py) roi rut ra bai hoc + de xuat tinh chinh tham
so / soft rule. Chi dung stdlib (+ pyyaml chi de doc/ghi YAML config,
da co san trong requirements).

NGUYEN TAC:
- De xuat chi la DE XUAT: ham nay KHONG BAO GIO tu doi config.
  Chi `apply_proposals()` moi doi config.yaml LOCAL, va chi khi
  user go dung chu "APPLY".
- Lat cat nao co n < learning.min_sample_for_proposal thi ghi
  "chua du mau" va KHONG sinh de xuat tu lat cat do.
- De xuat chua kiem chung OOS thi KHONG BAO GIO duoc trinh bay
  nhu da san sang ap dung (validated: false + ly do ro rang).
- Kiem chung OOS dung DUONG CO SAN: run_walk_forward /
  run_walk_forward_from_history trong backtest.py — khong viet
  backtester moi.
- Ban ghi co the thieu khoa context — thieu thi coi nhu None,
  khong bao gio crash.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVALUATED = REPO_ROOT / "decisions" / "signal-outcomes-evaluated.jsonl"
DEFAULT_DECISIONS_DIR = REPO_ROOT / "decisions"

DEFAULT_MIN_SAMPLE = 20
NO_HISTORY_REASON = "chua co du lieu lich su de kiem chung OOS"
OVERFITTING_WARNING = (
    "CANH BAO OVERFITTING: mau nho, nhieu lat cat — ket qua qua khu "
    "khong dam bao ket qua tuong lai. Mot de xuat thang tren mau nay "
    "co the chi la ngau nhien; chi ap dung sau khi kiem chung "
    "out-of-sample tren du lieu that va duoc Phu/Yuling duyet. "
    "De xuat chua kiem chung OOS thi KHONG san sang ap dung."
)

# Nguong chenh lech win rate toi thieu giua 2 lat cat moi xet de xuat.
_MIN_WIN_RATE_GAP = 0.20
# Win rate toi da cua lat cat "yeu" moi xet chan/gioi han no.
_MAX_WEAK_WIN_RATE = 0.30


def min_sample_for_proposal(cfg):
    """So mau toi thieu moi duoc de xuat (learning.min_sample_for_proposal).

    Thieu muc learning thi mac dinh 20; gia tri khong hop le thi
    cung ve 20. Khong bao gio raise."""
    try:
        learning = (cfg or {}).get("learning") or {}
        value = int(learning.get("min_sample_for_proposal")
                    or DEFAULT_MIN_SAMPLE)
        return value if value > 0 else DEFAULT_MIN_SAMPLE
    except (TypeError, ValueError):
        return DEFAULT_MIN_SAMPLE


def _num(value):
    """float(value) neu duoc, khong thi None — khong bao gio raise."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value):
    """Chuyen gia tri `time` cua ban ghi ve datetime UTC (aware).

    Chap nhan epoch int/float, chuoi ISO (co/khong co 'Z'), datetime.
    Tra None neu khong doc duoc."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromtimestamp(int(float(text)),
                                          tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _context(record):
    ctx = (record or {}).get("context")
    return ctx if isinstance(ctx, dict) else {}


def _metrics(records, min_sample):
    """Chi so cua 1 tap ban ghi: n, wins, losses, timeouts, win_rate
    (wins / (wins+losses) — timeout LOAI khoi mau so), avg_win,
    avg_loss (trung binh `ret` cua lenh thang/thua), profit_factor
    (tong thang / tong thua, None neu khong co lenh thua),
    expectancy (trung binh `ret` cua lenh da dong thang/thua)."""
    wins = [r for r in records if (r or {}).get("outcome") == "win"]
    losses = [r for r in records if (r or {}).get("outcome") == "loss"]
    timeouts = [r for r in records if (r or {}).get("outcome") == "timeout"]
    closed = wins + losses
    win_rets = [_num(r.get("ret")) for r in wins]
    win_rets = [v for v in win_rets if v is not None]
    loss_rets = [_num(r.get("ret")) for r in losses]
    loss_rets = [v for v in loss_rets if v is not None]
    gross_win = sum(win_rets)
    gross_loss = -sum(loss_rets)
    n = len(records)
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate": (len(wins) / len(closed) if closed else None),
        "avg_win": (sum(win_rets) / len(win_rets) if win_rets else None),
        "avg_loss": (sum(loss_rets) / len(loss_rets) if loss_rets else None),
        "profit_factor": (gross_win / gross_loss
                          if gross_loss > 0 else None),
        "expectancy": (
            (sum(win_rets) + sum(loss_rets)) / len(closed)
            if closed else None),
        "status": ("chua du mau" if n < min_sample else "du mau"),
    }


def _slice_metrics(records, key_fn, labels, min_sample):
    """Chia records theo key_fn -> {label: metrics}. Moi lat cat
    deu co n + status ('chua du mau' khi n < min_sample)."""
    buckets = {label: [] for label in labels}
    for record in records:
        label = key_fn(record)
        if label not in buckets:
            buckets[label] = []
        buckets[label].append(record)
    return {label: _metrics(bucket, min_sample)
            for label, bucket in buckets.items()}


def _rsi_band(record):
    rsi = _num(_context(record).get("rsi"))
    if rsi is None:
        return "thieu RSI"
    if rsi < 30:
        return "rsi <30"
    if rsi < 50:
        return "30-50"
    if rsi < 70:
        return "50-70"
    return "70+"


def _adx_regime(record):
    adx = _num(_context(record).get("adx"))
    if adx is None:
        return "thieu ADX"
    if adx < 20:
        return "adx <20"
    if adx < 25:
        return "20-25"
    return "25+"


def _pattern_slice(record):
    patterns = _context(record).get("patterns")
    if isinstance(patterns, list) and patterns:
        return "co mau hinh"
    if isinstance(patterns, dict) and patterns:
        return "co mau hinh"
    return "khong co mau hinh"


def _fa_agreement(record):
    fa = _context(record).get("fa")
    if not isinstance(fa, dict):
        return "khong co FA"
    direction = (fa.get("direction") or "")
    if isinstance(direction, str):
        direction = direction.strip().lower()
    else:
        direction = ""
    if direction not in ("buy", "sell"):
        return "khong co FA"
    action = (record.get("action") or "").strip().upper()
    fa_action = "BUY" if direction == "buy" else "SELL"
    if action == fa_action:
        return "dong thuan"
    if action in ("BUY", "SELL"):
        return "mau thuan"
    return "khong co FA"


def _htf_agreement(record):
    """Lat cat theo dong thuan HTF (MTF v1 — muc 64)."""
    htf = _context(record).get("htf")
    if not isinstance(htf, dict):
        return "khong ap dung HTF"
    return {"agree": "dong thuan HTF",
            "against": "nguoc HTF",
            "neutral": "trung lap"}.get(htf.get("agreement"),
                                         "khong ap dung HTF")


def _session_hour(record):
    moment = _parse_time(record.get("time"))
    if moment is None:
        return "khong ro gio"
    hour = moment.hour
    if hour < 8:
        return "0-7"
    if hour < 16:
        return "8-15"
    return "16-23"


def _soft_rule_names(records):
    """Tat ca ten soft rule xuat hien trong cac ban ghi (thu tu on dinh)."""
    names = []
    for record in records:
        rules = _context(record).get("soft_rules")
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict):
                    name = rule.get("name")
                    if name and name not in names:
                        names.append(name)
    return names


def _breakdowns(records, min_sample):
    """Tat ca lat cat cua 1 tap ban ghi (moi lat cat co n + status)."""
    out = {
        "rsi_band": _slice_metrics(
            records, _rsi_band,
            ["rsi <30", "30-50", "50-70", "70+", "thieu RSI"], min_sample),
        "adx_regime": _slice_metrics(
            records, _adx_regime,
            ["adx <20", "20-25", "25+", "thieu ADX"], min_sample),
        "pattern": _slice_metrics(
            records, _pattern_slice,
            ["co mau hinh", "khong co mau hinh"], min_sample),
        "fa_agreement": _slice_metrics(
            records, _fa_agreement,
            ["dong thuan", "mau thuan", "khong co FA"], min_sample),
        "htf_agreement": _slice_metrics(
            records, _htf_agreement,
            ["dong thuan HTF", "nguoc HTF", "trung lap",
             "khong ap dung HTF"], min_sample),
        "session_hour": _slice_metrics(
            records, _session_hour,
            ["0-7", "8-15", "16-23", "khong ro gio"], min_sample),
    }
    soft = {}
    for name in _soft_rule_names(records):
        def _fired(record, _name=name):
            rules = _context(record).get("soft_rules")
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict) and rule.get("name") == _name:
                        return bool(rule.get("fired"))
            return False
        soft[name] = {
            "fired": _metrics([r for r in records if _fired(r)],
                              min_sample),
            "not_fired": _metrics([r for r in records if not _fired(r)],
                                  min_sample),
        }
    out["soft_rule"] = soft
    return out


def _calibration(records, min_sample):
    """Win rate theo proxy tin cay (tool khong co diem tin cay
    rieng tung tin hieu): size_scale (1.0 vs <1.0) va tin cay FA
    (cao >=0.6 vs thap <0.6)."""
    def _size_bucket(record):
        scale = _num(record.get("size_scale"))
        if scale is None:
            scale = _num(_context(record).get("size_scale"))
        if scale is None or scale >= 1.0:
            return "1.0"
        return "<1.0"

    def _fa_conf_bucket(record):
        fa = _context(record).get("fa")
        if not isinstance(fa, dict):
            return "khong co FA"
        conf = _num(fa.get("confidence"))
        if conf is None:
            return "khong co FA"
        return "cao >=0.6" if conf >= 0.6 else "thap <0.6"

    return {
        "size_scale": _slice_metrics(records, _size_bucket,
                                     ["1.0", "<1.0"], min_sample),
        "fa_confidence": _slice_metrics(records, _fa_conf_bucket,
                                        ["cao >=0.6", "thap <0.6",
                                         "khong co FA"], min_sample),
    }


def review(evaluated_records, cfg):
    """Phan tich cac ban ghi da danh gia thanh bao cao dict.

    evaluated_records: list dict (moi ban ghi co `outcome`,
    `ret`, `context`, ...). cfg: config (doc learning.
    min_sample_for_proposal, mac dinh 20)."""
    records = [r for r in (evaluated_records or []) if isinstance(r, dict)]
    min_sample = min_sample_for_proposal(cfg)
    moments = [_parse_time(r.get("time")) for r in records]
    moments = [m for m in moments if m is not None]
    by_symbol = {}
    for symbol in sorted({str(r.get("symbol") or "khong ro")
                          for r in records}):
        by_symbol[symbol] = _metrics(
            [r for r in records
             if str(r.get("symbol") or "khong ro") == symbol], min_sample)
    by_desk = {}
    for desk in sorted({str(r.get("desk") or "khong ro")
                        for r in records}):
        by_desk[desk] = _metrics(
            [r for r in records
             if str(r.get("desk") or "khong ro") == desk], min_sample)
    return {
        "n": len(records),
        "min_sample": min_sample,
        "date_range": {
            "start": min(moments).isoformat() if moments else None,
            "end": max(moments).isoformat() if moments else None,
        },
        "overall": _metrics(records, min_sample),
        "by_symbol": by_symbol,
        "by_desk": by_desk,
        "breakdowns": _breakdowns(records, min_sample),
        "calibration": _calibration(records, min_sample),
    }


def _fmt_pct(value):
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_ret(value):
    if value is None:
        return "n/a"
    return f"{value * 100:+.2f}%"


def _fmt_num(value):
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _metrics_line(label, metrics):
    """1 dong bang: ten lat cat + n + win rate + profit factor +
    expectancy; ghi ro 'chua du mau' khi n < min_sample."""
    status = (f" — {metrics['status']}" if metrics.get("status")
              == "chua du mau" else "")
    return (f"  {label}: n={metrics['n']} thang {metrics['wins']} "
            f"thua {metrics['losses']} timeout {metrics['timeouts']} | "
            f"win rate {_fmt_pct(metrics['win_rate'])} "
            f"(timeout loai khoi mau so) | avg thang "
            f"{_fmt_ret(metrics['avg_win'])} | avg thua "
            f"{_fmt_ret(metrics['avg_loss'])} | profit factor "
            f"{_fmt_num(metrics['profit_factor'])} | expectancy "
            f"{_fmt_ret(metrics['expectancy'])}{status}")


def _breakdown_block(title, slices):
    lines = [f"== {title} =="]
    for label, metrics in slices.items():
        lines.append(_metrics_line(label, metrics))
    return lines


def format_report(report):
    """In bao cao thanh van ban (tieng Viet khong dau, theo phong
    cach CLI cua repo). Luon co doan CANH BAO OVERFITTING."""
    overall = report["overall"]
    date_range = report.get("date_range") or {}
    start = date_range.get("start") or "?"
    end = date_range.get("end") or "?"
    lines = [
        "DiamondX10 TA REVIEW — bai hoc tu ket qua tin hieu da danh gia",
        f"Tong so tin hieu: n={report['n']} | tu {start} den {end} "
        f"(UTC) | mau toi thieu/lat cat: {report['min_sample']}",
        "",
        "== TONG QUAN ==",
        _metrics_line("tat ca", overall),
        "",
        "== THEO SYMBOL ==",
    ]
    for symbol in sorted(report["by_symbol"]):
        lines.append(_metrics_line(symbol, report["by_symbol"][symbol]))
    lines += ["", "== THEO DESK =="]
    for desk in sorted(report["by_desk"]):
        lines.append(_metrics_line(desk, report["by_desk"][desk]))
    lines.append("")
    bd = report["breakdowns"]
    lines += _breakdown_block("THEO RSI BAND", bd["rsi_band"])
    lines.append("")
    lines += _breakdown_block("THEO ADX REGIME", bd["adx_regime"])
    lines.append("")
    lines += _breakdown_block("THEO MAU HINH", bd["pattern"])
    lines.append("")
    lines.append("== THEO SOFT RULE (fired vs khong fired) ==")
    if not bd["soft_rule"]:
        lines.append("  (khong co soft rule nao trong cac ban ghi)")
    for name in sorted(bd["soft_rule"]):
        lines.append(f"  Rule {name}:")
        lines.append(_metrics_line("    fired", bd["soft_rule"][name]["fired"]))
        lines.append(_metrics_line("    khong fired",
                                   bd["soft_rule"][name]["not_fired"]))
    lines.append("")
    lines += _breakdown_block("THEO DONG THUAN PTCB", bd["fa_agreement"])
    lines.append("")
    lines += _breakdown_block("THEO DONG THUAN HTF", bd["htf_agreement"])
    lines.append("")
    lines += _breakdown_block("THEO PHIEN (gio UTC)", bd["session_hour"])
    lines.append("")
    lines.append("== HIEU CHUAN (calibration — proxy tin cay) ==")
    lines.append("Tool khong co diem tin cay rieng tung tin hieu nen "
                 "dung size_scale va tin cay FA lam proxy.")
    lines += _breakdown_block("Theo size_scale", report["calibration"]["size_scale"])
    lines += _breakdown_block("Theo tin cay FA", report["calibration"]["fa_confidence"])
    lines.append("")
    lines.append(OVERFITTING_WARNING)
    return "\n".join(lines)


# --- De xuat tinh chinh -------------------------------------------------

def _desk_for_symbol(cfg, symbol):
    symbols = ((cfg or {}).get("data") or {}).get("symbols") or {}
    if isinstance(symbols, dict):
        for desk, desk_symbols in symbols.items():
            if symbol in (desk_symbols or []):
                return desk
    return None


def _current_param(cfg, desk, symbol, param):
    """Gia tri hien tai cua 1 tham so cho (desk, symbol): resolve
    dung thu tu uu tien (mac dinh < chung < desk < symbol); loi
    resolve thi doc thang muc strategy (khong bao gio raise)."""
    try:
        from .strategies.registry import resolve_strategy_params
        resolved = resolve_strategy_params(cfg, desk, symbol)
        if param in resolved:
            return resolved[param]
    except Exception:  # noqa: BLE001 — fallback doc thang muc strategy
        pass
    section = ((cfg or {}).get("strategy") or {})
    per_symbol = section.get("per_symbol") or {}
    if isinstance(per_symbol, dict) and symbol in per_symbol:
        value = (per_symbol.get(symbol) or {}).get(param)
        if value is not None:
            return value
    return section.get(param)


def _cfg_with_proposal(cfg, symbol, proposal):
    """Ban sao config da ap 1 de xuat (chi de chay kiem chung OOS)."""
    new_cfg = copy.deepcopy(cfg or {})
    new_cfg.setdefault("strategy", {})
    strategy = new_cfg["strategy"]
    if proposal.get("kind") == "soft_rule":
        rule = proposal["proposed_value"]
        rules = list(strategy.get("soft_rules") or [])
        rules = [r for r in rules
                 if not (isinstance(r, dict)
                         and r.get("name") == rule.get("name"))]
        rules.append(copy.deepcopy(rule))
        strategy["soft_rules"] = rules
    else:
        param = proposal["param_or_rule"]
        strategy.setdefault("per_symbol", {})
        per_symbol = dict(strategy["per_symbol"])
        entry = dict(per_symbol.get(symbol) or {})
        entry[param] = proposal["proposed_value"]
        per_symbol[symbol] = entry
        strategy["per_symbol"] = per_symbol
    return new_cfg


def _validate_oos(proposal, symbol, cfg, history):
    """Kiem chung OOS 1 de xuat bang duong walk-forward CO SAN.

    history: HistoryStore hoac dict {symbol: [bars]} (bars dict
    {time, open, high, low, close, volume?}) hoac list bars cua
    chinh symbol do. Tra dict {oos_win_rate, oos_return, oos_n,
    validated, reason?} (+ baseline_oos_return de so sanh)."""
    if history is None:
        return {"oos_win_rate": None, "oos_return": None, "oos_n": 0,
                "validated": False, "reason": NO_HISTORY_REASON}
    desk = _desk_for_symbol(cfg, symbol)
    if desk is None:
        return {"oos_win_rate": None, "oos_return": None, "oos_n": 0,
                "validated": False,
                "reason": "khong tim thay desk cho symbol "
                          f"{symbol} trong config — khong kiem chung duoc"}
    try:
        from .backtest import (
            run_walk_forward,
            run_walk_forward_from_history,
        )
        cfg_try = _cfg_with_proposal(cfg, symbol, proposal)
        if isinstance(history, dict):
            bars = history.get(symbol)
            if bars is None and len(history) == 1:
                bars = next(iter(history.values()))
            if not bars:
                return {"oos_win_rate": None, "oos_return": None,
                        "oos_n": 0, "validated": False,
                        "reason": "khong co bar lich su cho "
                                  f"{symbol} — khong kiem chung duoc"}
            bars = list(bars)
            if len(bars) < 15:
                return {"oos_win_rate": None, "oos_return": None,
                        "oos_n": 0, "validated": False,
                        "reason": f"chi co {len(bars)} bar lich su, "
                                  "khong du chay walk-forward"}
            if len(bars) >= 60:
                train_bars, test_bars, step_bars = 30, 10, 10
            elif len(bars) >= 40:
                train_bars, test_bars, step_bars = 20, 10, 10
            else:
                train_bars, test_bars, step_bars = 10, 5, 5
            bars_by_symbol = {symbol: bars}
            base = run_walk_forward(
                desk, 0, cfg=cfg, symbols=[symbol],
                train_bars=train_bars, test_bars=test_bars,
                step_bars=step_bars, bars_by_symbol=bars_by_symbol)
            tried = run_walk_forward(
                desk, 0, cfg=cfg_try, symbols=[symbol],
                train_bars=train_bars, test_bars=test_bars,
                step_bars=step_bars, bars_by_symbol=bars_by_symbol)
        elif isinstance(history, list):
            bars = list(history)
            if len(bars) < 15:
                return {"oos_win_rate": None, "oos_return": None,
                        "oos_n": 0, "validated": False,
                        "reason": f"chi co {len(bars)} bar lich su, "
                                  "khong du chay walk-forward"}
            train_bars, test_bars, step_bars = (30, 10, 10) if len(bars) >= 60 else (20, 10, 10) if len(bars) >= 40 else (10, 5, 5)
            base = run_walk_forward(
                desk, 0, cfg=cfg, symbols=[symbol],
                train_bars=train_bars, test_bars=test_bars,
                step_bars=step_bars, bars_by_symbol={symbol: bars})
            tried = run_walk_forward(
                desk, 0, cfg=cfg_try, symbols=[symbol],
                train_bars=train_bars, test_bars=test_bars,
                step_bars=step_bars, bars_by_symbol={symbol: bars})
        else:
            # HistoryStore (co get_bars) — dung duong lich su that.
            base = run_walk_forward_from_history(
                desk, cfg, symbols=[symbol], timeframe="M15",
                train_bars=30, test_bars=10, step_bars=10, store=history)
            tried = run_walk_forward_from_history(
                desk, cfg_try, symbols=[symbol], timeframe="M15",
                train_bars=30, test_bars=10, step_bars=10, store=history)
        agg = tried["aggregated"]
        base_agg = base["aggregated"]
        oos_n = int(agg.get("n_trades") or 0)
        oos_return = agg.get("total_return_pct")
        validated = bool(oos_n > 0 and oos_return is not None
                         and base_agg.get("total_return_pct") is not None
                         and oos_return > base_agg["total_return_pct"])
        result = {"oos_win_rate": agg.get("win_rate"),
                  "oos_return": oos_return, "oos_n": oos_n,
                  "validated": validated,
                  "baseline_oos_return": base_agg.get("total_return_pct"),
                  "baseline_oos_n": int(base_agg.get("n_trades") or 0)}
        if not validated:
            result["reason"] = (
                "de xuat khong thang baseline tren OOS "
                f"(de xuat {oos_return}%, baseline "
                f"{base_agg.get('total_return_pct')}%, lenh OOS {oos_n})"
                if oos_n > 0 else
                "walk-forward OOS khong co lenh nao — khong ket luan duoc")
        return result
    except Exception as exc:  # noqa: BLE001 — kiem chung loi thi ghi ly do
        return {"oos_win_rate": None, "oos_return": None, "oos_n": 0,
                "validated": False,
                "reason": f"kiem chung OOS loi: {exc}"}


def _wr(metrics):
    return metrics.get("win_rate")


def _candidates_for_symbol(symbol, records, cfg, min_sample):
    """Cac de xuat ung vien cho 1 symbol (toi da 2, theo thu tu
    uu tien RSI -> ADX -> ATR stop). Lat cat nao n < min_sample
    thi khong sinh de xuat tu lat cat do."""
    desk = _desk_for_symbol(cfg, symbol)
    bd = _breakdowns(records, min_sample)
    overall = _metrics(records, min_sample)
    candidates = []

    # (1) RSI: vung 50-70 thang hon han vung 30-50 -> thu hep
    # vung mua (tang rsi_buy_low them 5, khong vuot rsi_buy_high - 5).
    rsi = bd["rsi_band"]
    good = rsi.get("50-70") or {}
    bad = rsi.get("30-50") or {}
    if (good.get("n", 0) >= min_sample and bad.get("n", 0) >= min_sample
            and _wr(good) is not None and _wr(bad) is not None
            and _wr(good) - _wr(bad) >= _MIN_WIN_RATE_GAP):
        current_low = _current_param(cfg, desk, symbol, "rsi_buy_low")
        current_high = _current_param(cfg, desk, symbol, "rsi_buy_high")
        try:
            current_low = int(current_low) if current_low is not None else 50
            current_high = int(current_high) if current_high is not None else 70
        except (TypeError, ValueError):
            current_low, current_high = 50, 70
        proposed_low = min(current_low + 5, current_high - 5)
        if proposed_low > current_low:
            candidates.append({
                "symbol": symbol, "kind": "param",
                "param_or_rule": "rsi_buy_low",
                "current_value": current_low,
                "proposed_value": proposed_low,
                "evidence": {"metric": "win_rate",
                             "before": _wr(bad), "after": _wr(good),
                             "n": good["n"]},
                "rationale": (f"RSI 50-70 thang {_wr(good):.0%} vs RSI "
                              f"30-50 thang {_wr(bad):.0%} — thu hep "
                              "vung mua ve phia RSI cao hon."),
            })

    # (2) ADX: lo tap trung khi adx <20 (win rate thap) trong khi
    # adx 25+ thang hon han -> them soft rule chan khi ADX <= 20.
    adx = bd["adx_regime"]
    weak = adx.get("adx <20") or {}
    strong = adx.get("25+") or {}
    if (weak.get("n", 0) >= min_sample and strong.get("n", 0) >= min_sample
            and _wr(weak) is not None and _wr(strong) is not None
            and _wr(weak) <= _MAX_WEAK_WIN_RATE
            and _wr(strong) - _wr(weak) >= _MIN_WIN_RATE_GAP):
        rule_name = f"{symbol.lower()}-adx-yeu-block"
        rule = {"name": rule_name, "scope": {"symbol": symbol},
                "condition": {"type": "adx_max", "value": 20},
                "effect": "block"}
        candidates.append({
            "symbol": symbol, "kind": "soft_rule",
            "param_or_rule": "soft_rule:adx>=20",
            "current_value": None,
            "proposed_value": rule,
            "evidence": {"metric": "win_rate",
                         "before": _wr(weak), "after": _wr(strong),
                         "n": weak["n"]},
            "rationale": (f"ADX <20 thang {_wr(weak):.0%} vs ADX 25+ "
                          f"thang {_wr(strong):.0%} — chan lenh moi "
                          "khi xu huong yeu (ADX <= 20)."),
        })

    # (3) ATR stop: lenh thua chiem da so va muc lo trung binh lon
    # hon muc thang trung binh -> tang he so stop ATR them 0.5.
    if (overall.get("n", 0) >= min_sample
            and overall.get("win_rate") is not None
            and overall["win_rate"] < 0.4
            and overall.get("avg_win") is not None
            and overall.get("avg_loss") is not None
            and abs(overall["avg_loss"]) > overall["avg_win"]):
        current_mult = _current_param(cfg, desk, symbol, "atr_sl_mult")
        try:
            current_mult = float(current_mult) if current_mult is not None else 1.5
        except (TypeError, ValueError):
            current_mult = 1.5
        proposed_mult = min(round(current_mult + 0.5, 2), 3.0)
        if proposed_mult > current_mult:
            candidates.append({
                "symbol": symbol, "kind": "param",
                "param_or_rule": "atr_sl_mult",
                "current_value": current_mult,
                "proposed_value": proposed_mult,
                "evidence": {"metric": "win_rate",
                             "before": overall["win_rate"],
                             "after": None,
                             "n": overall["n"]},
                "rationale": (f"Thang {overall['win_rate']:.0%}, lo trung "
                              f"binh {abs(overall['avg_loss']):.1%} lon hon "
                              f"thang trung binh {overall['avg_win']:.1%} "
                              "— stop ATR co the qua chat, thu rong stop."),
            })
    return candidates[:2]


def propose(report, evaluated_records, cfg, *, history=None):
    """Sinh de xuat tinh chinh tu bao cao + ban ghi da danh gia.

    Moi symbol co n >= min_sample_for_proposal thi toi da 2 de xuat.
    Moi de xuat deu co evidence + oos_validation (validated false
    + ly do khi khong co du lieu lich su). Ham nay KHONG ghi config.
    """
    records = [r for r in (evaluated_records or []) if isinstance(r, dict)]
    min_sample = (report or {}).get("min_sample")
    if min_sample is None:
        min_sample = min_sample_for_proposal(cfg)
    by_symbol = (report or {}).get("by_symbol") or {}
    proposals = []
    symbols = sorted(by_symbol) if by_symbol else sorted(
        {str(r.get("symbol") or "khong ro") for r in records})
    for symbol in symbols:
        metrics = by_symbol.get(symbol)
        if metrics is not None and metrics.get("n", 0) < min_sample:
            continue
        symbol_records = [r for r in records
                          if str(r.get("symbol") or "khong ro") == symbol]
        if len(symbol_records) < min_sample:
            continue
        for candidate in _candidates_for_symbol(symbol, symbol_records,
                                                cfg, min_sample):
            oos = _validate_oos(candidate, symbol, cfg, history)
            candidate["oos_validation"] = oos
            candidate["validated"] = bool(oos.get("validated"))
            candidate["ready"] = bool(oos.get("validated"))
            proposals.append(candidate)
    return proposals


# --- Ghi / ap de xuat ----------------------------------------------------

def _yaml_scalar(value):
    """1 gia tri YAML don gian (so / chuoi / bool / None)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if text in ("", "null", "true", "false") or any(
            ch in text for ch in ":#{}[],&*?|>@`\"'"):
        return json.dumps(text, ensure_ascii=False)
    return text


def write_proposals(proposals, path):
    """Ghi de xuat ra file YAML dang strategy.per_symbol /
    soft_rules (kem comment chung cu + ket qua OOS tung de xuat).

    Tra ve duong dan (str). File chi la de xuat — khong tu dong
    doi config khi ghi."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    per_symbol = {}
    soft_rules = []
    for proposal in (proposals or []):
        if proposal.get("kind") == "soft_rule":
            rule = proposal.get("proposed_value")
            if isinstance(rule, dict):
                soft_rules.append((proposal, rule))
        else:
            per_symbol.setdefault(proposal["symbol"], {})[
                proposal["param_or_rule"]] = proposal["proposed_value"]
    lines = [
        "# De xuat tinh chinh TA — CHUA AP DUNG, chi la de xuat.",
        "# Ap bang: python -m diamondx10 ta-review --apply <file> "
        "(go dung chu APPLY moi doi config.yaml local).",
        "# " + OVERFITTING_WARNING,
    ]
    for proposal in (proposals or []):
        oos = proposal.get("oos_validation") or {}
        ev = proposal.get("evidence") or {}
        status = ("DA KIEM CHUNG OOS" if oos.get("validated")
                  else "CHUA KIEM CHUNG — KHONG SAN SANG AP DUNG")
        lines.append(
            f"# - {proposal['symbol']} {proposal['param_or_rule']}: "
            f"{proposal.get('current_value')} -> "
            f"{proposal.get('proposed_value')} | {status} | "
            f"evidence {ev.get('metric')}: truoc {ev.get('before')} "
            f"sau {ev.get('after')} (n={ev.get('n')}) | "
            f"OOS: {oos}")
        lines.append(f"#   Ly do: {proposal.get('rationale')}")
    if not proposals:
        lines.append("# (khong co de xuat nao du mau de sinh)")
    lines.append("strategy:")
    lines.append("  per_symbol:")
    if per_symbol:
        for symbol in sorted(per_symbol):
            lines.append(f"    {symbol}:")
            for param in sorted(per_symbol[symbol]):
                lines.append(f"      {param}: "
                             f"{_yaml_scalar(per_symbol[symbol][param])}")
    else:
        lines.append("    {}")
    if soft_rules:
        lines.append("  soft_rules:")
        for _proposal, rule in soft_rules:
            lines.append(f"    - name: {_yaml_scalar(rule.get('name'))}")
            scope = rule.get("scope") or {}
            if scope:
                scope_txt = ", ".join(
                    f"{k}: {_yaml_scalar(v)}" for k, v in scope.items())
                lines.append(f"      scope: {{{scope_txt}}}")
            cond = rule.get("condition") or {}
            if cond:
                cond_txt = ", ".join(
                    f"{k}: {_yaml_scalar(v)}" for k, v in cond.items())
                lines.append(f"      condition: {{{cond_txt}}}")
            lines.append(f"      effect: {_yaml_scalar(rule.get('effect'))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def apply_proposals(path, config_path, *, confirm=None):
    """Ap file de xuat vao config.yaml LOCAL.

    Xac nhan: caller truyen confirm="APPLY", hoac (confirm=None)
    ham hoi truc tiep qua input() — go dung "APPLY" moi doi.
    Khong xac nhan thi KHONG doi gi va tra ([], skipped).
    Chi ap duoc strategy.per_symbol + soft_rules (them moi);
    cai khac bi bo qua kem ly do. KHONG BAO GIO ap vao
    config.example.yaml — gap duong dan do thi raise ValueError.

    Tra (changed_keys, skipped): changed_keys la list chuoi khoa
    da doi; skipped la list {key, reason}."""
    config_path = Path(config_path)
    if str(config_path).replace("\\", "/").endswith("config.example.yaml"):
        raise ValueError(
            "TU CHOI: khong ap de xuat vao config.example.yaml — "
            "chi ap vao config.yaml LOCAL.")
    if not Path(path).exists():
        raise FileNotFoundError(f"Khong tim thay file de xuat: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("File de xuat phai la YAML dict o cap cao nhat.")
    if not config_path.exists():
        raise FileNotFoundError(
            f"Khong tim thay config: {config_path} — chay o goc repo "
            "(noi co config.yaml local).")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ValueError("config.yaml khong phai YAML dict.")

    # Thu thap thay doi dinh ap + cac muc bi bo qua.
    changes = []  # (key, old, new, applier)
    skipped = []

    def _skip(key, reason):
        skipped.append({"key": key, "reason": reason})

    strategy = data.get("strategy")
    if isinstance(strategy, dict):
        per_symbol = strategy.get("per_symbol")
        if isinstance(per_symbol, dict):
            for symbol, params in per_symbol.items():
                if not isinstance(params, dict):
                    _skip(f"strategy.per_symbol.{symbol}",
                          "gia tri phai la dict tham so")
                    continue
                for param, new_value in params.items():
                    key = f"strategy.per_symbol.{symbol}.{param}"
                    try:
                        from .strategies.registry import (
                            validate_strategy_params,
                        )
                        validate_strategy_params({param: new_value})
                    except Exception as exc:  # noqa: BLE001 — bo qua kem ly do
                        _skip(key, f"tham so khong hop le: {exc}")
                        continue
                    old = ((config.get("strategy") or {})
                           .get("per_symbol") or {}).get(symbol, {})
                    old = old.get(param) if isinstance(old, dict) else None
                    changes.append((key, old, new_value,
                                    ("per_symbol", symbol, param)))
        elif per_symbol is not None:
            _skip("strategy.per_symbol", "gia tri phai la dict")
        soft = strategy.get("soft_rules")
        if isinstance(soft, list):
            existing = ((config.get("strategy") or {})
                        .get("soft_rules") or [])
            existing_names = {r.get("name") for r in existing
                              if isinstance(r, dict)}
            for rule in soft:
                if not isinstance(rule, dict) or not rule.get("name"):
                    _skip("strategy.soft_rules",
                          "rule phai la dict co 'name'")
                    continue
                key = f"strategy.soft_rules.{rule['name']}"
                if rule["name"] in existing_names:
                    _skip(key, "da co rule cung ten trong config — bo qua")
                    continue
                try:
                    from .strategies.soft_rules import validate_soft_rules
                    validate_soft_rules([rule])
                except Exception as exc:  # noqa: BLE001
                    _skip(key, f"rule khong hop le: {exc}")
                    continue
                changes.append((key, None, rule,
                                ("soft_rule", rule["name"])))
        elif soft is not None:
            _skip("strategy.soft_rules", "gia tri phai la list")
        for key in strategy:
            if key not in ("per_symbol", "soft_rules"):
                _skip(f"strategy.{key}",
                      "chi ap strategy.per_symbol va soft_rules")
    if isinstance(data.get("soft_rules"), list):
        existing = ((config.get("strategy") or {}).get("soft_rules") or [])
        existing_names = {r.get("name") for r in existing
                          if isinstance(r, dict)}
        for rule in data["soft_rules"]:
            if not isinstance(rule, dict) or not rule.get("name"):
                _skip("soft_rules", "rule phai la dict co 'name'")
                continue
            key = f"strategy.soft_rules.{rule['name']}"
            if rule["name"] in existing_names:
                _skip(key, "da co rule cung ten trong config — bo qua")
                continue
            try:
                from .strategies.soft_rules import validate_soft_rules
                validate_soft_rules([rule])
            except Exception as exc:  # noqa: BLE001
                _skip(key, f"rule khong hop le: {exc}")
                continue
            changes.append((key, None, rule, ("soft_rule", rule["name"])))
    for key in data:
        if key not in ("strategy", "soft_rules"):
            _skip(key, "chi ap strategy.per_symbol va soft_rules")

    # In diff truoc khi hoi xac nhan (user thay ro se doi gi).
    if changes:
        print("De xuat se doi config:")
        for key, old, new, _applier in changes:
            print(f"  {key}: {old} -> {new}")
    else:
        print("Khong co thay doi nao ap duoc tu file de xuat.")
    if skipped:
        for item in skipped:
            print(f"  Bo qua {item['key']}: {item['reason']}")

    if confirm is None:
        try:
            confirm = input(
                "Go dung chu APPLY de ap cac thay doi tren vao "
                "config.yaml (go bat ky thu gi khac de huy): ").strip()
        except EOFError:
            confirm = ""
    if confirm != "APPLY":
        print("Huy — khong doi gi trong config.")
        for key, _old, _new, _applier in changes:
            skipped.append({"key": key,
                            "reason": "chua xac nhan APPLY — khong doi gi"})
        return [], skipped

    # Ap that: chi sua 2 muc cho phep, giu nguyen cac khoa khac.
    config.setdefault("strategy", {})
    for key, _old, new, applier in changes:
        if applier[0] == "per_symbol":
            _kind, symbol, param = applier
            config["strategy"].setdefault("per_symbol", {})
            config["strategy"]["per_symbol"].setdefault(symbol, {})
            config["strategy"]["per_symbol"][symbol][param] = new
        else:
            _kind, _name = applier
            config["strategy"].setdefault("soft_rules", [])
            config["strategy"]["soft_rules"].append(
                copy.deepcopy(new))
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    changed_keys = [key for key, _old, _new, _applier in changes]
    for key in changed_keys:
        print(f"Da doi: {key}")
    return changed_keys, skipped


def load_evaluated_records(path):
    """Doc file JSONL da danh gia -> list dict (dong loi bo qua,
    dem vao bad_lines). Tra (records, bad_lines)."""
    path = Path(path)
    records, bad_lines = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                bad_lines += 1
    return records, bad_lines
