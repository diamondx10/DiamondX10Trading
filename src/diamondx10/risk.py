"""Risk: position sizing theo % rui ro, stop-loss, gioi han drawdown."""
import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path


def position_size(capital_usd, risk_pct, entry, stop_loss):
    """So tien vao lenh sao cho lo toi da = capital * risk_pct."""
    risk_per_unit = abs(entry - stop_loss)
    if risk_per_unit <= 0:
        return 0.0
    max_loss = capital_usd * risk_pct / 100.0
    return max_loss / risk_per_unit


def _percentile(sorted_values, pct):
    """Phan vi kieu numpy percentile (noi suy tuyen tinh). sorted_values
    phai da sap xep tang dan; pct trong [0, 100]."""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_values[0])
    rank = pct / 100.0 * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def value_at_risk(returns, confidence=0.95):
    """Value at Risk lich su (phuong phap giong PortfolioRiskEngine cua
    repo DiamondX10 cu): muc lo (so duong, dang phan so — vd 0,02 la 2%)
    ma voi do tin cay `confidence`, loi nhuan 1 ky se khong te hon muc
    do. Tra 0.0 neu o muc phan vi do khong co khoan lo nao (toan lai),
    khac voi ban goc dung abs() ca khi phan vi duong. Tra None neu
    khong du du lieu (< 2 gia tri). Chi la CHI SO BAO CAO — khong phai
    gioi han chan lenh (gioi han van la drawdown 10%, xem muc 12
    trong trading-principles.md)."""
    vals = sorted(float(r) for r in (returns or []))
    if len(vals) < 2:
        return None
    pct = _percentile(vals, 100 * (1 - confidence))
    if pct is None or pct >= 0:
        return 0.0
    return -pct


def expected_shortfall(returns, confidence=0.95):
    """Expected Shortfall (CVaR) lich su: muc lo trung binh cua cac ky
    te hon VaR o cung do tin cay (giong _calc_cvar cua repo DiamondX10
    cu). Tra 0.0 neu khong co ky nao te hon VaR; None neu khong du
    du lieu. Cung la chi so bao cao, khong phai gioi han chan lenh."""
    var = value_at_risk(returns, confidence)
    if var is None:
        return None
    if var <= 0:
        return 0.0
    tail = [float(r) for r in (returns or []) if float(r) <= -var]
    if not tail:
        return 0.0
    return -sum(tail) / len(tail)


def check_drawdown(equity_curve, max_drawdown_pct=10.0):
    peak = equity_curve[0]
    for v in equity_curve:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100 if peak else 0
        if dd > max_drawdown_pct:
            return False, f"drawdown {dd:.1f}% vuot gioi han {max_drawdown_pct}%"
    return True, "drawdown trong gioi han"


class DrawdownGuard:
    """Chan drawdown theo quy tac Q1 (Phase 4, [ĐÃ CHỐT — Phu duyet 2026-11-27]):

    - Gioi han 10% TOAN QUY (mac dinh lay tu config risk.max_drawdown_pct):
      cham gioi han thi chan lenh moi toan bo tool.
    - Canh bao 5% moi DESK (risk.desk_warning_pct): cham muc nay thi chi
      chan lenh moi cua desk do.
    - Lenh dang mo chi duoc quan ly, khong bao gio bi dong ep boi quy tac nay.

    Guard giu duong cong von (equity curve) cua quy va cua tung desk,
    bat dau tu von ban dau. Moi P&L da thuc hien (lenh dong) duoc ghi
    bang record_pnl(). Trang thai luu/khoi phuc duoc qua to_state() /
    from_state() de ghi vao decisions/equity-state.json.
    """

    def __init__(self, fund_capital, desk_capitals, max_drawdown_pct=10.0,
                 desk_warning_pct=5.0):
        self.fund_capital = float(fund_capital)
        self.desk_capitals = {d: float(c) for d, c in (desk_capitals or {}).items()}
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.desk_warning_pct = float(desk_warning_pct)
        self.fund_curve = [self.fund_capital]
        self.desk_curves = {d: [c] for d, c in self.desk_capitals.items()}

    def record_pnl(self, desk, pnl):
        """Ghi P&L da thuc hien cua 1 lenh dong: them gia tri von moi
        vao duong cong quy va duong cong desk do."""
        pnl = float(pnl)
        self.fund_curve.append(self.fund_curve[-1] + pnl)
        curve = self.desk_curves.get(desk)
        if curve is None:
            curve = [self.desk_capitals.get(desk, 0.0)]
            self.desk_curves[desk] = curve
        curve.append(curve[-1] + pnl)

    def can_open(self, desk):
        """(ok, reason): co duoc mo lenh moi cho desk nay khong.

        Kiem tra gioi han quy truoc, roi canh bao desk. Khi bi chan,
        reason bat dau bang ma BLOCKED-* theo hop dong log Phase 4/5
        (BLOCKED-DRAWDOWN-FUND / BLOCKED-DRAWDOWN-DESK) de __main__
        dung lam action khi ghi log.
        """
        ok, reason = check_drawdown(self.fund_curve, self.max_drawdown_pct)
        if not ok:
            return False, f"BLOCKED-DRAWDOWN-FUND: {reason}"
        curve = self.desk_curves.get(desk)
        if curve is not None:
            ok, reason = check_drawdown(curve, self.desk_warning_pct)
            if not ok:
                return False, f"BLOCKED-DRAWDOWN-DESK: {reason}"
        return True, "drawdown trong gioi han"

    def to_state(self):
        return {
            "fund_capital": self.fund_capital,
            "desk_capitals": dict(self.desk_capitals),
            "max_drawdown_pct": self.max_drawdown_pct,
            "desk_warning_pct": self.desk_warning_pct,
            "fund_curve": list(self.fund_curve),
            "desk_curves": {d: list(c) for d, c in self.desk_curves.items()},
        }

    @classmethod
    def from_state(cls, state):
        guard = cls(state.get("fund_capital", 0.0),
                    state.get("desk_capitals") or {},
                    state.get("max_drawdown_pct", 10.0),
                    state.get("desk_warning_pct", 5.0))
        fund_curve = state.get("fund_curve")
        if fund_curve:
            guard.fund_curve = [float(v) for v in fund_curve]
        desk_curves = state.get("desk_curves") or {}
        for desk, curve in desk_curves.items():
            if curve:
                guard.desk_curves[desk] = [float(v) for v in curve]
        return guard


def _to_naive(dt):
    """Ve datetime naive: bo mui gio, giu nguyen gio ghi tren dong ho.
    Su kien trong config ghi theo gio dia phuong (vd 14:00+07:00) va
    `now` chay theo gio dia phuong, nen so sanh theo gio dong ho."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _parse_event_start(value):
    if isinstance(value, datetime):
        return _to_naive(value)
    return _to_naive(datetime.fromisoformat(str(value)))


def in_no_trade_window(now, events, symbol=None):
    """(True, ten_su_kien) neu `now` nam trong cua so cam giao dich nao do.

    events: list dict {name, start (ISO datetime — GIO BAT DAU cua so,
    vd 30 phut truoc gio tin), window_minutes, symbols (list tuy chon,
    mac dinh ap cho moi symbol)}. Cua so la [start, start + window_minutes).
    symbol: neu su kien chi dinh symbols rieng ma symbol khong nam trong
    do thi su kien do khong ap dung. Neu khong truyen symbol thi chi cac
    su kien ap cho moi symbol moi duoc tinh.
    Ham thuan — khong doc config, khong ghi log.
    """
    now = _to_naive(now)
    for event in events or []:
        symbols = event.get("symbols")
        if symbols is not None:
            if symbol is None or symbol not in symbols:
                continue
        start = _parse_event_start(event["start"])
        end = start + timedelta(minutes=float(event.get("window_minutes", 0)))
        if start <= now < end:
            return True, event.get("name")
    return False, None


# --- Phase F: gioi han rui ro TOAN QUY (xem docs/fund-risk-ops.md) ---
# Cac con so mac dinh duoi day CHUA DUOC CHOT — gia tri than trong de
# xuat, Phu duyet moi thanh quy tac chinh thuc ([CẦN CHỐT] trong
# trading-principles.md muc 33). Code chi doc chung tu config muc
# `risk:` (fund_daily_loss_pct, max_open_positions_fund,
# max_open_positions_desk); khong co trong config thi dung mac dinh.
DEFAULT_FUND_DAILY_LOSS_PCT = 3.0
DEFAULT_MAX_OPEN_POSITIONS_FUND = 10
DEFAULT_MAX_OPEN_POSITIONS_DESK = 2


def fund_limits_from_config(cfg):
    """3 gioi han quy tu config muc `risk:`, kem gia tri mac dinh."""
    risk_cfg = (cfg or {}).get("risk") or {}
    return {
        "fund_daily_loss_pct": float(risk_cfg.get(
            "fund_daily_loss_pct", DEFAULT_FUND_DAILY_LOSS_PCT)),
        "max_open_positions_fund": int(risk_cfg.get(
            "max_open_positions_fund", DEFAULT_MAX_OPEN_POSITIONS_FUND)),
        "max_open_positions_desk": int(risk_cfg.get(
            "max_open_positions_desk", DEFAULT_MAX_OPEN_POSITIONS_DESK)),
    }


_PNL_RE = re.compile(r"P&L\s+(-?\d+(?:\.\d+)?)\s*USD")


def today_pnl_from_log_rows(rows, day=None):
    """Tong P&L da thuc hien trong ngay `day` (mac dinh hom nay), cong
    tu cac dong CLOSE trong decisions log. Moi dong CLOSE deu ghi
    "P&L {pnl:.2f} USD" trong cot reason (positions._close_position
    va realize_deals) nen chi can boc so do ra. Dong nao khong boc
    duoc thi bo qua — khong crash bao cao. Tra 0.0 neu khong co
    dong CLOSE nao trong ngay."""
    day = day or date.today().isoformat()
    total = 0.0
    for row in rows or []:
        if row.get("action") != "CLOSE" or row.get("date") != day:
            continue
        match = _PNL_RE.search(row.get("reason") or "")
        if match:
            total += float(match.group(1))
    return total


def today_pnl_from_log(log_path=None, day=None):
    """Doc decisions log roi goi today_pnl_from_log_rows. File chua co
    thi tra 0.0. Ham thuan theo file — de test va de live/report dung
    chung 1 cach tinh lo trong ngay."""
    from . import decisions  # import cham: tranh vong tron luc nap module

    path = Path(log_path) if log_path is not None else decisions.LOG
    if not path.exists():
        return 0.0
    with open(path, newline="", encoding="utf-8") as f:
        return today_pnl_from_log_rows(list(csv.DictReader(f)), day)


def check_fund_limits(guard, positions, cfg, today_pnl, desk=None):
    """(ok, reason): co duoc mo lenh moi khong, theo 3 gioi han quy.

    (a) Lo trong ngay: P&L da thuc hien hom nay am qua muc
        fund_daily_loss_pct (% von quy) thi chan mo lenh moi toan quy.
    (b) Tong vi the mo: dat max_open_positions_fund thi chan toan quy.
    (c) Vi the mo theo desk: desk xin mo lenh dat
        max_open_positions_desk thi chi chan desk do (can truyen desk).
    Kiem tra theo thu tu (a) -> (b) -> (c); khi bi chan, reason bat
    dau bang ma BLOCKED-* de live dung lam action khi ghi log.
    Ham thuan — khong doc file, khong ghi log, khong can MT5.
    """
    limits = fund_limits_from_config(cfg)
    fund_capital = float(getattr(guard, "fund_capital", 0) or 0)
    if not fund_capital:
        fund_capital = float((cfg.get("fund") or {}).get(
            "total_capital_usd") or 0)
    today_pnl = float(today_pnl or 0)
    loss_limit = fund_capital * limits["fund_daily_loss_pct"] / 100.0
    if today_pnl < 0 and -today_pnl >= loss_limit:
        return False, (
            "BLOCKED-DAILY-LOSS-FUND: lo hom nay "
            f"{-today_pnl:.2f} USD dat gioi han {loss_limit:.2f} USD "
            f"({limits['fund_daily_loss_pct']:g}% von quy)")
    n_open = len(positions or [])
    if n_open >= limits["max_open_positions_fund"]:
        return False, (
            "BLOCKED-MAX-POSITIONS-FUND: dang mo "
            f"{n_open} vi the, dat gioi han "
            f"{limits['max_open_positions_fund']} vi the toan quy")
    if desk is not None:
        n_desk = sum(1 for p in (positions or [])
                     if p.get("desk") == desk)
        if n_desk >= limits["max_open_positions_desk"]:
            return False, (
                "BLOCKED-MAX-POSITIONS-DESK: desk "
                f"{desk} dang mo {n_desk} vi the, dat gioi han "
                f"{limits['max_open_positions_desk']} vi the/desk")
    return True, "gioi han quy trong muc cho phep"
