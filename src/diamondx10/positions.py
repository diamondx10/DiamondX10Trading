"""Quan ly vi the dang mo (Phase 4): doi chieu vi the theo nen gia moi.

Moi vi the mo luu trong decisions/equity-state.json co dang:
  {desk, symbol, direction ("BUY"/"SELL"), entry, sl, tp, volume (lot),
   contract_size, atr, opened_date}

Doi chieu (reconcile): truoc khi xu ly tin hieu moi, dua tung vi the
qua cac nen gia moi nhat theo thu tu thoi gian:
  1. SL hit (BUY: low <= sl; SELL: high >= sl) -> dong o gia SL.
  2. TP hit (BUY: high >= tp; SELL: low <= tp) -> dong o gia TP.
  3. Trailing SL theo strategy.trailing_stop() voi ATR luc mo lenh.
  4. Sau khi duyet het nen: reversal_exit() -> dong o gia dong nen cuoi.
Vi the nao dong thi tinh P&L, ghi vao DrawdownGuard, log CLOSE.
Vi the con mo giu SL trailing moi trong state.

P&L: pnl = huong x (exit - entry) x units, units = volume x contract_size,
tru phi (fee_pct % tren notional luc vao lenh, tinh 1 chieu). Phi lay tu
config backtest.fee_pct (mac dinh 0,02% — cung gia dinh phi nhu backtest
o Phase 3); __main__ truyen fee_pct nay vao reconcile_positions.
"""
from datetime import date

from .decisions import log_decision

CLOSE_CAUSES = ("TP", "SL", "trailing", "dao chieu")


def position_pnl(position, exit_price, fee_pct=0.0):
    """P&L USD khi dong vi the o exit_price (tru phi neu fee_pct > 0)."""
    direction = 1 if position["direction"] == "BUY" else -1
    units = float(position["volume"]) * float(position["contract_size"])
    pnl = direction * (float(exit_price) - float(position["entry"])) * units
    if fee_pct:
        pnl -= float(fee_pct) / 100.0 * float(position["entry"]) * units
    return pnl


def _close_position(guard, positions, position, exit_price, cause,
                    fee_pct=0.0, manager="", log_fn=None):
    """Dong 1 vi the: tinh P&L, ghi guard, log CLOSE, xoa khoi danh sach."""
    pnl = position_pnl(position, exit_price, fee_pct)
    guard.record_pnl(position["desk"], pnl)
    positions.remove(position)
    (log_fn or log_decision)(
        position["symbol"], "CLOSE",
        f"Dong {position['direction']} {position['symbol']} @ {exit_price:g} "
        f"P&L {pnl:.2f} USD ({cause})",
        desk=position["desk"], manager=manager)
    return {"position": position, "exit": float(exit_price),
            "pnl": pnl, "cause": cause}


def reconcile_positions(guard, positions, desk, symbol, bars, strat,
                        fee_pct=0.0, manager="", log_fn=None):
    """Dua cac vi the mo cua (desk, symbol) qua cac nen `bars` moi.

    Tra (closed, still_open): danh sach dict lenh da dong (moi dict co
    position/exit/pnl/cause) va danh sach vi the con mo (chinh la
    `positions` sau khi da loai lenh dong, voi SL trailing da cap nhat).
    Khong bao gio raise vi du lieu nen thieu — het nen ma khong cham
    SL/TP thi vi the cu mo.
    """
    log = log_fn or log_decision
    mine = [p for p in positions if p["desk"] == desk and p["symbol"] == symbol]
    closed = []
    for position in list(mine):
        direction = position["direction"]
        sl, tp = float(position["sl"]), float(position["tp"])
        original_sl = sl
        atr_value = float(position.get("atr") or 0) or None
        done = False
        for bar in bars:
            if direction == "BUY":
                if float(bar["low"]) <= sl:
                    # SL da doi len nho trailing thi ghi "trailing" de
                    # phan biet voi SL goc.
                    cause = "trailing" if sl != original_sl else "SL"
                    closed.append(_close_position(
                        guard, positions, position, sl, cause,
                        fee_pct, manager, log))
                    done = True
                    break
                if float(bar["high"]) >= tp:
                    closed.append(_close_position(
                        guard, positions, position, tp, "TP",
                        fee_pct, manager, log))
                    done = True
                    break
            else:  # SELL
                if float(bar["high"]) >= sl:
                    cause = "trailing" if sl != original_sl else "SL"
                    closed.append(_close_position(
                        guard, positions, position, sl, cause,
                        fee_pct, manager, log))
                    done = True
                    break
                if float(bar["low"]) <= tp:
                    closed.append(_close_position(
                        guard, positions, position, tp, "TP",
                        fee_pct, manager, log))
                    done = True
                    break
            # Chua cham SL/TP: doi SL trailing theo gia dong nen nay.
            # trailing_stop() tinh theo khoang cach SL GOC nen luon
            # truyen original_sl; ket qua khong bao gio doi SL nguoc
            # lai so voi SL hien tai (max/min voi sl).
            candidate = strat.trailing_stop(position["entry"], original_sl,
                                            direction, float(bar["close"]),
                                            atr_value)
            if direction == "BUY":
                new_sl = max(sl, candidate)
            else:
                new_sl = min(sl, candidate)
            if new_sl != sl:
                sl = new_sl
                position["sl"] = sl
        if done:
            continue
        # Het nen, van mo: kiem tra dao chieu tren toan bo nen.
        if bars and strat.reversal_exit(direction, bars):
            closed.append(_close_position(
                guard, positions, position, float(bars[-1]["close"]),
                "dao chieu", fee_pct, manager, log))
    still_open = [p for p in positions if p["desk"] == desk and p["symbol"] == symbol]
    return closed, still_open


def _day_start_epoch(date_str):
    """Epoch (giay) luc 0h00 ngay `date_str` (YYYY-MM-DD, gio dia phuong).
    Dung de loai deal cu: deal dong lenh phai xay ra sau ngay mo vi the."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(date_str)).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0


def _deal_field(deal, name):
    if isinstance(deal, dict):
        return deal.get(name)
    return getattr(deal, name, None)


def realize_deals(guard, positions, deals, manager="", log_fn=None):
    """Doi chieu vi the mo voi deal da dong tren MT5 (history_deals_get).

    deals: list dict/object co symbol, type (0=BUY, 1=SELL — chieu cua
    deal DONG lenh, nguoc huong vi the mo), price, profit (neu co),
    time (epoch, neu co — deal phai xay ra tu ngay mo vi the tro di,
    tranh deal cu dong nham vi the moi).
    Moi deal dong khop 1 vi the mo cung symbol, nguoc huong: dong vi the
    o gia deal, P&L lay tu deal.profit neu co, khong thi tinh tu gia.
    Tra (closed, unmatched_deals). Vi the khong khop deal nao thi giu
    nguyen de reconcile theo nen xu ly tiep.
    """
    log = log_fn or log_decision
    closed = []
    remaining = list(deals or [])
    for position in list(positions):
        match = None
        opened_ts = _day_start_epoch(position.get("opened_date", ""))
        for deal in remaining:
            d_symbol = _deal_field(deal, "symbol")
            d_type = _deal_field(deal, "type")
            # Deal dong lenh co type nguoc huong vi the mo.
            opposite = 1 if position["direction"] == "BUY" else 0
            if d_symbol != position["symbol"] or d_type != opposite:
                continue
            d_time = _deal_field(deal, "time")
            if d_time is not None and float(d_time) < opened_ts:
                continue  # deal cu hon ngay mo vi the — khong phai deal nay
            match = deal
            break
        if match is None:
            continue
        remaining.remove(match)
        price = _deal_field(match, "price")
        profit = _deal_field(match, "profit")
        exit_price = float(price) if price is not None else float(position["entry"])
        if profit is not None:
            pnl = float(profit)
        else:
            pnl = position_pnl(position, exit_price)
        guard.record_pnl(position["desk"], pnl)
        positions.remove(position)
        log(position["symbol"], "CLOSE",
            f"Dong {position['direction']} {position['symbol']} @ {exit_price:g} "
            f"P&L {pnl:.2f} USD (MT5 deal)",
            desk=position["desk"], manager=manager)
        closed.append({"position": position, "exit": exit_price,
                       "pnl": pnl, "cause": "MT5 deal"})
    return closed, remaining


def new_position(desk, symbol, direction, entry, sl, tp, volume,
                 contract_size, atr_value):
    """Ban ghi vi the mo moi, dung dinh dang state da chot (Phase 4)."""
    return {
        "desk": desk,
        "symbol": symbol,
        "direction": direction,
        "entry": float(entry),
        "sl": float(sl),
        "tp": float(tp),
        "volume": float(volume),
        "contract_size": float(contract_size),
        "atr": float(atr_value) if atr_value else 0.0,
        "opened_date": date.today().isoformat(),
    }
