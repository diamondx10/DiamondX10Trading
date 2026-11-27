"""Dashboard web chi doc (Phase E): xem von, vi the mo, tin hieu moi
nhat, ket qua backtest gan nhat va trang thai rui ro tren 1 trang web.

CHI DOC — khong ghi, khong dat lenh, khong goi MT5:
  - Chi doc decisions/equity-state.json, decisions/decisions-log.csv
    va kho nen local (data/history.db, chi de lay gia dong nen moi
    nhat lam gia tham chieu cho P&L chua thuc hien).
  - Khong tu chay tin hieu moi, khong tu chay backtest khi load trang
    (ca hai deu cham / co tac dung phu); chi hien thi du lieu da co.
  - File thieu hoac hong (JSON/CSV loi) thi muc do hien
    "chua co du lieu", trang van tra 200, khong crash.

Chay (chi local — chua co auth nen KHONG bind 0.0.0.0):
    python -m diamondx10.dashboard [--port 8000] [--host 127.0.0.1]
Mo trinh duyet: http://127.0.0.1:8000/ (tu lam moi moi 60 giay).
"""
import argparse
import csv
import html
import json
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import decisions
from .risk import DrawdownGuard

# Thu muc goc repo (de tim duong dan mac dinh khi khong truyen ro).
REPO_ROOT = Path(__file__).resolve().parents[2]
# File ket qua backtest gan nhat (xem docs/dashboard.md): CLI backtest
# hien chi in ra man hinh, chua tu luu file — nguoi dung luu ket qua
# JSON vao day thi dashboard moi hien duoc muc backtest.
DEFAULT_BACKTEST_RESULT = REPO_ROOT / "results" / "backtest-latest.json"
BACKTEST_RESULTS_DIR = REPO_ROOT / "results"
# So dong tin hieu/lenh gan nhat hien tren trang.
RECENT_SIGNALS_N = 10
# P&L trong reason cua dong CLOSE co dang "P&L 25.00 USD" (xem
# positions.py _close_position).
_CLOSE_PNL_RE = re.compile(r"P&L\s+(-?\d+(?:\.\d+)?)\s*USD")
NO_DATA = "chưa có dữ liệu"


def _safe_load_state(state_path=None):
    """Doc equity state; thieu file hoac JSON hong thi None (muc lien
    quan se hien "chua co du lieu", khong raise)."""
    path = Path(state_path) if state_path is not None else decisions.EQUITY_STATE
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (ValueError, OSError):
        return None
    return state if isinstance(state, dict) else None


def _safe_read_log(log_path=None):
    """Doc decisions log; thieu file hoac CSV loi thi [] (khong raise)."""
    path = Path(log_path) if log_path is not None else decisions.LOG
    if not path.exists():
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error):
        return []


def _max_dd_pct(curve):
    """Drawdown lon nhat (%) cua 1 duong cong von (giong report.py)."""
    peak = None
    worst = 0.0
    for v in curve or []:
        v = float(v)
        peak = v if peak is None else max(peak, v)
        if peak:
            worst = max(worst, (peak - v) / peak * 100)
    return worst


def _latest_close(symbol, history_db_path, timeframe="M15"):
    """Gia dong nen moi nhat cua symbol trong kho lich su local.

    Tra (gia, epoch) hoac (None, None) neu kho thieu / khong co bar /
    loi doc — dashboard khi do ghi "chua co gia", khong crash.
    Khong goi MT5: chi doc SQLite local."""
    if not history_db_path:
        return None, None
    try:
        from .data.history import HistoryStore
        with HistoryStore(str(history_db_path)) as store:
            latest = store.latest_time(symbol, timeframe)
            if latest is None:
                return None, None
            bars = store.get_bars(symbol, timeframe,
                                  start=latest, end=latest)
    except Exception:
        return None, None
    if not bars:
        return None, None
    return float(bars[-1]["close"]), int(bars[-1]["time"])


def _positions_section(state, history_db_path, timeframe):
    """Vi the dang mo tu state + P&L chua thuc hien uoc tinh theo gia
    dong nen moi nhat trong kho (neu lay duoc gia)."""
    positions = (state or {}).get("positions") or []
    out = []
    for p in positions:
        try:
            entry = float(p["entry"])
            volume = float(p["volume"])
            contract = float(p.get("contract_size") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        price, price_time = _latest_close(
            p.get("symbol", ""), history_db_path, timeframe)
        pnl = None
        if price is not None and contract:
            sign = 1 if p.get("direction") == "BUY" else -1
            pnl = sign * (price - entry) * volume * contract
        out.append({
            "desk": p.get("desk", ""),
            "symbol": p.get("symbol", ""),
            "direction": p.get("direction", ""),
            "entry": entry,
            "sl": p.get("sl"),
            "tp": p.get("tp"),
            "volume": volume,
            "opened_date": p.get("opened_date", ""),
            "latest_price": price,
            "latest_price_time": price_time,
            "unrealized_pnl": pnl,
        })
    return out


def _daily_pnl(rows):
    """P&L da thuc hien theo ngay, rut tu cac dong CLOSE trong log
    (reason co dang "... P&L 25.00 USD (TP)"). Tra {date: pnl}."""
    per_day = {}
    for row in rows:
        if (row.get("action") or "") != "CLOSE":
            continue
        m = _CLOSE_PNL_RE.search(row.get("reason") or "")
        if not m:
            continue
        day = row.get("date") or ""
        per_day[day] = per_day.get(day, 0.0) + float(m.group(1))
    return per_day


def _find_backtest_result(path=None):
    """Tim file ket qua backtest: duong dan truyen ro, neu khong thi
    results/backtest-latest.json, neu khong co thi file
    results/backtest-*.json moi nhat theo thoi gian sua. Tra Path hoac
    None. Chi doc — khong tu chay backtest de tao file."""
    if path is not None:
        p = Path(path)
        return p if p.exists() else None
    if DEFAULT_BACKTEST_RESULT.exists():
        return DEFAULT_BACKTEST_RESULT
    if not BACKTEST_RESULTS_DIR.is_dir():
        return None
    candidates = sorted(
        BACKTEST_RESULTS_DIR.glob("backtest-*.json"),
        key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _backtest_section(backtest_result_path=None):
    """Doc file ket qua backtest (dict cua run_backtest /
    run_backtest_from_history, luu dang JSON). Thieu file, JSON hong
    hay sai dinh dang thi None — trang hien huong dan chay backtest
    thay vi so lieu gia."""
    path = _find_backtest_result(backtest_result_path)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
    except (ValueError, OSError):
        return None
    if not isinstance(result, dict) or "metrics" not in result:
        return None
    metrics = result.get("metrics") or {}
    segments = result.get("segments") or {}
    test_m = (segments.get("test") or {}).get("metrics") or {}
    return {
        "path": str(path),
        "desk": result.get("desk"),
        "strategy": result.get("strategy"),
        "simulated": result.get("simulated", True),
        "source": result.get("source"),
        "timeframe": result.get("timeframe"),
        "n_bars": result.get("n_bars"),
        "symbols": result.get("symbols") or [],
        "total_return_pct": metrics.get("total_return_pct"),
        "win_rate": metrics.get("win_rate"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "n_trades": metrics.get("n_trades"),
        "total_pnl": metrics.get("total_pnl"),
        "sharpe": metrics.get("sharpe"),
        "test_return_pct": test_m.get("total_return_pct"),
        "test_n_trades": test_m.get("n_trades"),
    }


def build_dashboard_data(cfg, state_path=None, log_path=None,
                         history_db_path=None, backtest_result_path=None,
                         today=None):
    """Gom du lieu cho trang dashboard thanh dict (de test va de render).

    cfg: dict config (lay von ban dau + gioi han drawdown khi chua co
    state). Cac duong dan truyen ro de test duoc voi file gia trong
    tmp; khong truyen thi dung duong dan mac dinh cua repo.
    today: "YYYY-MM-DD", mac dinh hom nay. Ham CHI DOC — khong ghi
    file, khong dat lenh, khong goi MT5.
    """
    cfg = cfg or {}
    day = today or date.today().isoformat()
    rows = _safe_read_log(log_path)
    state = _safe_load_state(state_path)
    desks_cfg = (cfg.get("fund") or {}).get("desks") or {}
    total_cap = float((cfg.get("fund") or {}).get("total_capital_usd") or 0)
    risk_cfg = cfg.get("risk") or {}
    max_dd = float(risk_cfg.get("max_drawdown_pct", 10.0))
    warn = float(risk_cfg.get("desk_warning_pct", 5.0))
    if state and state.get("guard"):
        try:
            guard = DrawdownGuard.from_state(state["guard"])
        except (KeyError, TypeError, ValueError):
            guard = None
        has_state = guard is not None
    else:
        guard = None
        has_state = False
    if guard is None:
        guard = DrawdownGuard(
            total_cap,
            {d: float(i.get("capital_usd", 0)) for d, i in desks_cfg.items()},
            max_dd, warn)
    hist_cfg = (cfg.get("history") or {})
    if history_db_path is None:
        history_db_path = hist_cfg.get("db_path") or "data/history.db"
    timeframe = hist_cfg.get("default_timeframe") or "M15"
    # Duong dan kho tuong doi thi hieu theo goc repo.
    hist_path = Path(history_db_path)
    if not hist_path.is_absolute():
        hist_path = REPO_ROOT / hist_path

    fund_equity = guard.fund_curve[-1] if guard.fund_curve else total_cap
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
    daily_pnl = _daily_pnl(rows)
    pnl_today = daily_pnl.get(day, 0.0) if daily_pnl else None
    # Tin hieu/lenh gan nhat: doc tu log, KHONG tu chay tin hieu moi.
    recent = list(reversed(rows[-RECENT_SIGNALS_N:])) if rows else []
    # Rui ro tung desk: so lenh moi + so lan bi chan hom nay (tu log).
    risk = {}
    for desk in guard.desk_capitals:
        trades = sum(1 for r in rows
                     if r.get("desk") == desk and r.get("date") == day
                     and (r.get("action") or "") in ("BUY", "SELL"))
        blocked = sum(1 for r in rows
                      if r.get("desk") == desk and r.get("date") == day
                      and (r.get("action") or "").startswith("BLOCKED-"))
        d = per_desk[desk]
        risk[desk] = {
            "equity": d["equity"],
            "max_dd_pct": d["max_dd_pct"],
            "warning_pct": warn,
            "blocked": d["blocked"],
            "trades_today": trades,
            "blocked_today": blocked,
            "can_open": (not d["blocked"]) and fund_dd <= max_dd,
        }
    return {
        "date": day,
        "has_state": has_state,
        "has_log": bool(rows),
        "fund": {
            "capital": total_cap,
            "equity": fund_equity,
            "pnl": fund_equity - total_cap,
            "max_dd_pct": fund_dd,
            "limit_pct": max_dd,
            "blocked": fund_dd > max_dd,
        },
        "desks": per_desk,
        "positions": _positions_section(
            state if has_state else None, hist_path, timeframe),
        "pnl_today": pnl_today,
        "daily_pnl": {d: round(v, 2) for d, v in
                      sorted(daily_pnl.items())},
        "recent_signals": [
            {"date": r.get("date", ""), "desk": r.get("desk", ""),
             "symbol": r.get("symbol", ""), "action": r.get("action", ""),
             "reason": r.get("reason", ""), "manager": r.get("manager", "")}
            for r in recent],
        "backtest": _backtest_section(backtest_result_path),
        "risk": risk,
    }


def _fmt_money(value):
    """So USD: None -> None (de template hien "chua co du lieu")."""
    if value is None:
        return None
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return None


def _fmt_pct(value):
    if value is None:
        return None
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return None


def _esc(value):
    return html.escape("" if value is None else str(value))


def render_dashboard(data):
    """Render dict cua build_dashboard_data() thanh HTML (CSS inline,
    khong JS framework; trang tu lam moi moi 60 giay bang meta refresh)."""
    f = data["fund"]
    rows = []

    def section(title, body):
        rows.append(f"<h2>{_esc(title)}</h2>\n{body}")

    # (a) Vi the dang mo.
    if not data["positions"]:
        pos_body = f"<p>{NO_DATA}</p>"
        if data["has_state"]:
            pos_body = "<p>Không có vị thế nào đang mở.</p>"
    else:
        cells = []
        for p in data["positions"]:
            pnl = _fmt_money(p["unrealized_pnl"])
            price = (_fmt_money(p["latest_price"])
                     if p["latest_price"] is not None else None)
            cells.append(
                "<tr><td>{desk}</td><td>{sym}</td><td>{dir}</td>"
                "<td>{entry}</td><td>{sl}</td><td>{tp}</td>"
                "<td>{vol}</td><td>{price}</td><td>{pnl}</td>"
                "<td>{opened}</td></tr>".format(
                    desk=_esc(p["desk"]), sym=_esc(p["symbol"]),
                    dir=_esc(p["direction"]),
                    entry=_fmt_money(p["entry"]) or NO_DATA,
                    sl=_fmt_money(p["sl"]) or NO_DATA,
                    tp=_fmt_money(p["tp"]) or NO_DATA,
                    vol=_fmt_money(p["volume"]) or NO_DATA,
                    price=price if price is not None else "chưa có giá",
                    pnl=(f"{pnl} USD" if pnl is not None
                         else "chưa có giá"),
                    opened=_esc(p["opened_date"])))
        pos_body = (
            "<table><tr><th>Desk</th><th>Symbol</th><th>Hướng</th>"
            "<th>Giá vào</th><th>SL</th><th>TP</th><th>Volume (lot)</th>"
            "<th>Giá mới nhất</th><th>P&amp;L chưa thực hiện</th>"
            "<th>Mở ngày</th></tr>" + "".join(cells) + "</table>"
            "<p>Giá mới nhất = giá đóng nến mới nhất trong kho lịch sử "
            "local; chưa có giá thì P&amp;L hiện \"chưa có giá\".</p>")
    section("Vị thế đang mở", pos_body)

    # (b) Von + P&L theo ngay (khong bia duong cong: duong cong von
    # trong state khong kem ngay, nen chi hien von hien tai + P&L da
    # thuc hien theo ngay rut tu log CLOSE).
    if data["has_state"] or data["fund"]["capital"]:
        cap_body = (
            f"<p>Toàn quỹ: vốn { _fmt_money(f['capital'])} USD | "
            f"equity {_fmt_money(f['equity'])} USD | "
            f"P&amp;L {_fmt_money(f['pnl'])} USD | drawdown lớn nhất "
            f"{_fmt_pct(f['max_dd_pct'])} (giới hạn {_fmt_pct(f['limit_pct'])})"
            + (" — <b>CHẶN LỆNH MỚI</b>" if f["blocked"] else "")
            + "</p>")
        cap_body += "<table><tr><th>Desk</th><th>Vốn</th><th>Equity</th>"
        cap_body += "<th>P&amp;L</th><th>Drawdown lớn nhất</th></tr>"
        for desk, d in data["desks"].items():
            cap_body += (
                "<tr><td>{desk}</td><td>{cap}</td><td>{eq}</td>"
                "<td>{pnl}</td><td>{dd} (cảnh báo {warn})"
                "{flag}</td></tr>".format(
                    desk=_esc(desk), cap=_fmt_money(d["capital"]),
                    eq=_fmt_money(d["equity"]), pnl=_fmt_money(d["pnl"]),
                    dd=_fmt_pct(d["max_dd_pct"]),
                    warn=_fmt_pct(d["warning_pct"]),
                    flag=" — CHẶN" if d["blocked"] else ""))
        cap_body += "</table>"
        if not data["has_state"]:
            cap_body += ("<p>(Chưa có equity-state.json — vốn hiện là "
                         "vốn ban đầu theo config.)</p>")
        if data["daily_pnl"]:
            pnl_today = _fmt_money(data["pnl_today"])
            cap_body += (f"<p>P&amp;L đã thực hiện hôm nay "
                         f"({ _esc(data['date'])}): {pnl_today} USD.</p>"
                         "<p>P&amp;L đã thực hiện theo ngày (từ log CLOSE): "
                         + ", ".join(
                             f"{_esc(d)}: {v:+,.2f} USD"
                             for d, v in data["daily_pnl"].items())
                         + ".</p>")
        else:
            cap_body += f"<p>P&amp;L hôm nay: {NO_DATA} (chưa có lệnh CLOSE nào trong log).</p>"
    else:
        cap_body = f"<p>{NO_DATA}</p>"
    section("Vốn", cap_body)

    # (c) Tin hieu moi nhat (chi doc log).
    if not data["recent_signals"]:
        sig_body = f"<p>{NO_DATA}</p>"
    else:
        sig_body = ("<table><tr><th>Ngày</th><th>Desk</th><th>Symbol</th>"
                    "<th>Hành động</th><th>Lý do</th></tr>")
        for r in data["recent_signals"]:
            sig_body += (
                "<tr><td>{date}</td><td>{desk}</td><td>{sym}</td>"
                "<td>{act}</td><td>{reason}</td></tr>".format(
                    date=_esc(r["date"]), desk=_esc(r["desk"]),
                    sym=_esc(r["symbol"]), act=_esc(r["action"]),
                    reason=_esc(r["reason"])))
        sig_body += "</table>"
    section("Tín hiệu / lệnh gần nhất (từ decisions log)", sig_body)

    # (d) Ket qua backtest gan nhat.
    bt = data["backtest"]
    if bt is None:
        bt_body = (
            f"<p>{NO_DATA} — chưa có file kết quả backtest. Chạy backtest "
            "rồi lưu kết quả JSON vào <code>results/backtest-latest.json</code> "
            "(xem docs/dashboard.md), ví dụ:<br>"
            "<code>python -m diamondx10 backtest --desk forex --days 30</code>"
            "</p>")
    else:
        src = ("DỮ LIỆU THẬT — MT5 DEMO" if not bt["simulated"]
               else "MÔ PHỎNG — không phải hiệu suất thật")
        bt_body = (
            f"<p>Desk: {_esc(bt['desk'])} | Chiến lược: "
            f"{_esc(bt['strategy'])} | Nguồn: {src}"
            + (f" | Khung: {_esc(bt['timeframe'])}" if bt["timeframe"] else "")
            + (f" | Bars: {bt['n_bars']}" if bt["n_bars"] else "")
            + "</p><table>"
            f"<tr><th>Return</th><th>Win rate</th><th>Max DD</th>"
            f"<th>Số lệnh</th><th>P&amp;L</th><th>Sharpe</th>"
            f"<th>Return test (OOS)</th><th>Lệnh test</th></tr><tr>"
            f"<td>{_fmt_pct(bt['total_return_pct']) or NO_DATA}</td>"
            f"<td>{_fmt_pct(bt['win_rate']) or NO_DATA}</td>"
            f"<td>{_fmt_pct(bt['max_drawdown_pct']) or NO_DATA}</td>"
            f"<td>{bt['n_trades'] if bt['n_trades'] is not None else NO_DATA}</td>"
            f"<td>{_fmt_money(bt['total_pnl']) + ' USD' if bt['total_pnl'] is not None else NO_DATA}</td>"
            f"<td>{bt['sharpe'] if bt['sharpe'] is not None else NO_DATA}</td>"
            f"<td>{_fmt_pct(bt['test_return_pct']) or NO_DATA}</td>"
            f"<td>{bt['test_n_trades'] if bt['test_n_trades'] is not None else NO_DATA}</td>"
            "</tr></table>"
            f"<p>File: <code>{_esc(bt['path'])}</code></p>")
    section("Kết quả backtest gần nhất", bt_body)

    # (e) Trang thai rui ro tung desk.
    if not data["risk"]:
        risk_body = f"<p>{NO_DATA}</p>"
    else:
        risk_body = ("<table><tr><th>Desk</th><th>Equity</th>"
                     "<th>Drawdown lớn nhất</th><th>Cảnh báo desk</th>"
                     "<th>Lệnh mới hôm nay</th><th>Bị chặn hôm nay</th>"
                     "<th>Được mở lệnh mới?</th></tr>")
        for desk, r in data["risk"].items():
            risk_body += (
                "<tr><td>{desk}</td><td>{eq}</td><td>{dd}</td>"
                "<td>{warn}</td><td>{trades}</td><td>{blocked}</td>"
                "<td>{ok}</td></tr>".format(
                    desk=_esc(desk), eq=_fmt_money(r["equity"]),
                    dd=_fmt_pct(r["max_dd_pct"]),
                    warn=_fmt_pct(r["warning_pct"]),
                    trades=r["trades_today"], blocked=r["blocked_today"],
                    ok="Có" if r["can_open"] else "Không — đang bị chặn"))
        risk_body += "</table>"
        risk_body += (f"<p>Giới hạn: drawdown toàn quỹ "
                      f"{_fmt_pct(f['limit_pct'])}; cảnh báo mỗi desk "
                      f"{_fmt_pct(next(iter(data['risk'].values()))['warning_pct'])}."
                      "</p>")
    section("Trạng thái rủi ro từng desk", risk_body)

    return (
        "<!DOCTYPE html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"refresh\" content=\"60\">"
        "<meta name=\"viewport\" content=\"width=device-width, "
        "initial-scale=1\">"
        "<title>DiamondX10 — Dashboard</title>"
        "<style>body{font-family:sans-serif;margin:2em;max-width:1000px}"
        "table{border-collapse:collapse;margin:0.5em 0}"
        "th,td{border:1px solid #999;padding:4px 8px;text-align:left}"
        "th{background:#eee}h1{margin-bottom:0}"
        "code{background:#eee;padding:1px 4px}</style></head><body>"
        f"<h1>DiamondX10 — Dashboard</h1>"
        f"<p>Ngày: {_esc(data['date'])} | Tự làm mới mỗi 60 giây "
        "(<a href=\"/\">Refresh</a>) | Chỉ đọc — không đặt lệnh, "
        "không sửa state.</p>"
        + "".join(rows) +
        "<hr><p>Số liệu chỉ đúng tới lần chạy tool gần nhất "
        "(xem docs/dashboard.md).</p>"
        "</body></html>")


class _DashboardHandler(BaseHTTPRequestHandler):
    """Handler chi phuc vu GET / (doc lai du lieu moi moi request).

    cfg va duong dan lay tu server (gan o create_server); moi request
    doc lai file nen so lieu luon moi toi lan chay tool gan nhat.
    """
    server_version = "DiamondX10Dashboard/1.0"

    def log_message(self, *args):  # giu log sach, khong in moi request
        pass

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404, "Khong tim thay")
            return
        try:
            data = build_dashboard_data(
                self.server.dashboard_cfg,
                state_path=self.server.state_path,
                log_path=self.server.log_path,
                history_db_path=self.server.history_db_path,
                backtest_result_path=self.server.backtest_result_path)
            page = render_dashboard(data)
        except Exception as exc:  # loi bat ngo: trang van 200, bao loi
            page = ("<!DOCTYPE html><html lang=\"vi\"><head>"
                    "<meta charset=\"utf-8\"><title>DiamondX10 — Dashboard"
                    "</title></head><body><h1>DiamondX10 — Dashboard</h1>"
                    f"<p>{NO_DATA} (lỗi đọc dữ liệu: "
                    f"{html.escape(str(exc))})</p></body></html>")
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(host="127.0.0.1", port=8000, cfg=None,
                  state_path=None, log_path=None, history_db_path=None,
                  backtest_result_path=None):
    """Tao HTTP server (chua chay). Dung cho test: khoi dong trong
    thread tren cong tam roi shutdown. Bind mac dinh 127.0.0.1 — chi
    local, chua co auth nen khong bind 0.0.0.0."""
    if cfg is None:
        from .config import load_config
        cfg = load_config()
    server = ThreadingHTTPServer((host, port), _DashboardHandler)
    server.dashboard_cfg = cfg
    server.state_path = state_path
    server.log_path = log_path
    server.history_db_path = history_db_path
    server.backtest_result_path = backtest_result_path
    return server


def start_dashboard(host="127.0.0.1", port=8000, cfg=None, **kwargs):
    """Chay dashboard (chan toi khi Ctrl+C)."""
    server = create_server(host, port, cfg=cfg, **kwargs)
    addr = server.server_address
    print(f"DiamondX10 dashboard: http://{addr[0]}:{addr[1]}/ "
          "(chi local, khong co auth — dung mo cong ra ngoai)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    """Entry: python -m diamondx10.dashboard [--port 8000]
    [--host 127.0.0.1]."""
    parser = argparse.ArgumentParser(
        description="DiamondX10 dashboard web chi doc (Phase E).")
    parser.add_argument("--host", default="127.0.0.1",
                        help="dia chi bind (mac dinh 127.0.0.1 — chi local)")
    parser.add_argument("--port", type=int, default=8000,
                        help="cong (mac dinh 8000)")
    args = parser.parse_args(argv)
    start_dashboard(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
