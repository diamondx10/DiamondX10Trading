"""Bao cao hang ngay (Phase 5): doc decisions log + equity state.

Doc decisions/decisions-log.csv (nguon ghi chep chinh thuc) va
decisions/equity-state.json (duong cong von cua DrawdownGuard + vi the
dang mo, Phase 4) roi in:
  - von (equity) tung desk va toan quy,
  - drawdown hien tai so voi gioi han (quy 10%, canh bao desk 5%),
  - vi the dang mo,
  - so lenh moi hom nay theo tung symbol,
  - cac hanh dong bi chan (BLOCKED-*) kem ly do.
Khong dat lenh, khong sua log hay state — chi doc va in.
"""
import csv
from datetime import date
from pathlib import Path

from . import audit as audit_mod
from . import decisions
from .killswitch import status as kill_switch_status
from .models.macro import macro_edge
from .risk import (
    DrawdownGuard,
    fund_limits_from_config,
    today_pnl_from_log_rows,
)


def _macro_section(cfg):
    """Macro edge cho XAUUSD + EURUSD neu config co muc "macro" voi du
    4 gia tri snapshot (dxy, us10y, vix, spx) do Yuling cung cap.
    Khong co thi None — bao cao in binh thuong, khong them muc nay.
    Nguon khung: repo DiamondX10 (cu), macro_edge.py."""
    snap = (cfg or {}).get("macro") or {}
    keys = ("dxy", "us10y", "vix", "spx")
    if any(snap.get(k) is None for k in keys):
        return None
    try:
        values = {k: float(snap[k]) for k in keys}
    except (TypeError, ValueError):
        return None
    return {symbol: macro_edge(symbol, **values)
            for symbol in ("XAUUSD", "EURUSD")}


def _read_log_rows(log_path=None):
    path = Path(log_path) if log_path is not None else decisions.LOG
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _max_dd_pct(curve):
    """Drawdown lon nhat (%) cua 1 duong cong von."""
    peak = None
    worst = 0.0
    for v in curve or []:
        v = float(v)
        peak = v if peak is None else max(peak, v)
        if peak:
            worst = max(worst, (peak - v) / peak * 100)
    return worst


def _fund_limits_section(cfg, positions, rows, day):
    """Muc gioi han quy (Phase F) cho bao cao: gia tri cau hinh + trang
    thai hien tai. Lo hom nay cong tu dong CLOSE trong log ngay `day`."""
    limits = fund_limits_from_config(cfg)
    total_cap = float((cfg.get("fund") or {}).get("total_capital_usd") or 0)
    today_pnl = today_pnl_from_log_rows(rows, day)
    loss_limit = total_cap * limits["fund_daily_loss_pct"] / 100.0
    open_by_desk = {}
    for p in positions or []:
        desk = p.get("desk") or ""
        open_by_desk[desk] = open_by_desk.get(desk, 0) + 1
    return {
        "config": limits,
        "today_pnl": today_pnl,
        "daily_loss_limit_usd": loss_limit,
        "daily_loss_blocked": today_pnl < 0 and -today_pnl >= loss_limit,
        "open_positions": len(positions or []),
        "open_by_desk": open_by_desk,
        "fund_blocked": len(positions or [])
        >= limits["max_open_positions_fund"],
        "desk_blocked": {d: n >= limits["max_open_positions_desk"]
                         for d, n in open_by_desk.items()},
    }


def build_report(cfg, log_path=None, state_path=None, today=None,
                 kill_switch_path=None, audit_path=None):
    """Gom du lieu bao cao thanh dict (de test va de in).

    today: "YYYY-MM-DD", mac dinh hom nay. Neu chua co equity-state.json
    (chua chay lenh nao) thi von lay theo config ban dau va ghi ro
    has_state=False — bao cao van in duoc, khong crash.
    Phase F them: trang thai kill switch, gioi han quy (gia tri cau
    hinh + trang thai hien tai: lo hom nay, so vi the mo) va 5 dong
    audit gan nhat. kill_switch_path/audit_path chi dung cho test
    (mac dinh doc file that trong decisions/).
    """
    day = today or date.today().isoformat()
    rows = _read_log_rows(log_path)
    state = decisions.load_equity_state(state_path)
    desks_cfg = (cfg.get("fund") or {}).get("desks") or {}
    total_cap = float((cfg.get("fund") or {}).get("total_capital_usd") or 0)
    risk_cfg = cfg.get("risk") or {}
    max_dd = float(risk_cfg.get("max_drawdown_pct", 10.0))
    warn = float(risk_cfg.get("desk_warning_pct", 5.0))
    if state and state.get("guard"):
        guard = DrawdownGuard.from_state(state["guard"])
        positions = state.get("positions") or []
        has_state = True
    else:
        guard = DrawdownGuard(
            total_cap,
            {d: float(i.get("capital_usd", 0)) for d, i in desks_cfg.items()},
            max_dd, warn)
        positions = []
        has_state = False
    fund_equity = guard.fund_curve[-1]
    fund_dd = _max_dd_pct(guard.fund_curve)
    per_desk = {}
    for desk, cap in guard.desk_capitals.items():
        curve = guard.desk_curves.get(desk) or [cap]
        dd = _max_dd_pct(curve)
        per_desk[desk] = {
            "capital": cap,
            "equity": curve[-1],
            "pnl": curve[-1] - cap,
            "max_dd_pct": dd,
            "warning_pct": warn,
            "blocked": dd > warn,
        }
    trades_today = {}
    blocked = []
    recommended = []
    n_trades = n_closes = 0
    for row in rows:
        action = row.get("action") or ""
        if action.startswith("BLOCKED-"):
            blocked.append(row)
        if action == "RECOMMENDED":
            # Khuyen nghi cho xac nhan: KHONG phai lenh da dat — khong
            # dem vao trades_today / totals["trades"], khong tinh P&L
            # hay vi the mo; chi liet ke de biet dang cho xac nhan.
            recommended.append(row)
        elif action in ("BUY", "SELL"):
            n_trades += 1
            if row.get("date") == day:
                sym = row.get("symbol") or ""
                trades_today[sym] = trades_today.get(sym, 0) + 1
        elif action == "CLOSE":
            n_closes += 1
    return {
        "date": day,
        "has_state": has_state,
        "macro": _macro_section(cfg),
        "kill_switch": kill_switch_status(kill_switch_path),
        "fund_limits": _fund_limits_section(cfg, positions, rows, day),
        "audit_recent": audit_mod.read_events(limit=5, path=audit_path),
        "fund": {
            "capital": total_cap,
            "equity": fund_equity,
            "pnl": fund_equity - total_cap,
            "max_dd_pct": fund_dd,
            "limit_pct": max_dd,
            "blocked": fund_dd > max_dd,
        },
        "desks": per_desk,
        "open_positions": positions,
        "trades_today": trades_today,
        "blocked": blocked[-10:],
        "recommended": recommended[-10:],
        "recommended_total": len(recommended),
        "totals": {"trades": n_trades, "closes": n_closes,
                   "blocked": len(blocked)},
    }


def format_report(rep):
    """In bao cao thanh text tieng Viet."""
    lines = [f"DiamondX10 — BAO CAO NGAY {rep['date']}"]
    if not rep["has_state"]:
        lines.append("(Chua co equity-state.json — chua co lenh nao duoc "
                     "doi chieu; von hien la von ban dau theo config.)")
    f = rep["fund"]
    lines.append(
        f"Quy: von {f['capital']:.0f} USD | equity {f['equity']:.2f} USD | "
        f"P&L {f['pnl']:+.2f} USD | drawdown lon nhat {f['max_dd_pct']:.2f}% "
        f"(gioi han {f['limit_pct']:.0f}%)"
        + (" — CHAN LENH MOI" if f["blocked"] else ""))
    for desk, d in rep["desks"].items():
        lines.append(
            f"  - {desk}: equity {d['equity']:.2f} USD | "
            f"P&L {d['pnl']:+.2f} USD | drawdown {d['max_dd_pct']:.2f}% "
            f"(canh bao {d['warning_pct']:.0f}%)"
            + (" — CHAN LENH MOI" if d["blocked"] else ""))
    lines.append(f"Vi the dang mo: {len(rep['open_positions'])}")
    for p in rep["open_positions"]:
        lines.append(
            f"  - {p['direction']} {p['symbol']} ({p['desk']}): vao "
            f"{float(p['entry']):g}, SL {float(p['sl']):g}, "
            f"TP {float(p['tp']):g}, {float(p['volume']):g} lot, "
            f"mo ngay {p.get('opened_date', '')}")
    lines.append(f"Lenh moi hom nay ({rep['date']}): "
                 + (", ".join(f"{s}: {n}" for s, n in
                              sorted(rep["trades_today"].items()))
                    or "(chua co)"))
    lines.append(f"Tong cong: {rep['totals']['trades']} lenh da dat, "
                 f"{rep['totals']['closes']} lenh da dong, "
                 f"{rep['totals']['blocked']} lan bi chan.")
    if rep.get("recommended"):
        lines.append(
            f"Khuyen nghi cho xac nhan: {rep.get('recommended_total', 0)} "
            "(chua dat lenh, khong tinh vao lenh da dat / P&L / vi the mo):")
        for row in rep["recommended"]:
            lines.append(f"  - {row.get('date')} {row.get('desk')} "
                         f"{row.get('symbol')}: {row.get('reason')}")
    # --- Phase F: kill switch, gioi han quy, audit ---
    ks = rep.get("kill_switch") or {}
    if ks.get("engaged"):
        lines.append(
            "Kill switch: BAT — khong mo lenh moi "
            f"(ly do: {ks.get('reason') or '(khong ghi ly do)'}, "
            f"boi {ks.get('by') or '(khong ro)'}, "
            f"luc {ks.get('engaged_at') or '?'})")
    else:
        lines.append("Kill switch: TAT.")
    fl = rep.get("fund_limits") or {}
    lim = fl.get("config") or {}
    lines.append(
        "Gioi han quy [CẦN CHỐT — cac con so chua duoc Phu duyet, "
        "xem docs/fund-risk-ops.md]:")
    lines.append(
        f"  - Lo trong ngay: {fl.get('today_pnl', 0.0):+.2f} USD / "
        f"gioi han {fl.get('daily_loss_limit_usd', 0.0):.2f} USD "
        f"({lim.get('fund_daily_loss_pct', 0):g}% von quy)"
        + (" — CHAN LENH MOI" if fl.get("daily_loss_blocked") else ""))
    lines.append(
        f"  - Vi the mo: {fl.get('open_positions', 0)} / "
        f"{lim.get('max_open_positions_fund', 0)} toan quy"
        + (" — CHAN LENH MOI" if fl.get("fund_blocked") else ""))
    for desk, n in sorted((fl.get("open_by_desk") or {}).items()):
        lines.append(
            f"    + {desk}: {n} / "
            f"{lim.get('max_open_positions_desk', 0)} vi the"
            + (" — CHAN LENH MOI" if (fl.get("desk_blocked") or {}).get(desk)
               else ""))
    audit_events = rep.get("audit_recent") or []
    lines.append("Audit gan day (5 dong moi nhat):")
    if audit_events:
        for ev in audit_events:
            lines.append(f"  - {ev.get('ts')} {ev.get('actor')} "
                         f"{ev.get('event')}: {ev.get('details')}")
    else:
        lines.append("  - (chua co su kien audit nao)")
    if rep["blocked"]:
        lines.append("Bi chan gan day:")
        for row in rep["blocked"]:
            lines.append(f"  - {row.get('date')} {row.get('desk')} "
                         f"{row.get('symbol')} {row.get('action')}: "
                         f"{row.get('reason')}")
    macro = rep.get("macro")
    if macro:
        lines.append("Vi mo (snapshot trong config — Yuling cung cap, "
                     "chi la boi canh, khong doi tin hieu):")
        for symbol, edge in macro.items():
            lines.append(
                f"  - {symbol}: score {edge['score']:+.3f} "
                f"(DXY {edge['edges']['dxy']:+.3f}, US10Y "
                f"{edge['edges']['us10y']:+.3f}, VIX "
                f"{edge['edges']['vix']:+.3f}, SPX "
                f"{edge['edges']['spx']:+.3f}) — {edge['summary']}")
    return "\n".join(lines)
