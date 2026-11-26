"""Khop lenh DEMO qua MT5 (Exness demo) — CHI DEMO, KHONG BAO GIO LENH THAT.

Chan DEMO-ONLY (bat buoc, co test):
1. Config phai noi ro demo_only: true; neu config ghi live/real -> tu choi.
2. Tai khoan dang dang nhap tren MT5 phai la tai khoan demo:
   - trade_mode == ACCOUNT_TRADE_MODE_DEMO (0), HOAC
   - account_info().demo == True, HOAC
   - ten server chua 'Demo' / 'Trial' (vd 'Exness-MT5Trial7').
   Tu choi ngay neu trade_mode == REAL, hoac server chua 'Real',
   hoac khong lay duoc thong tin tai khoan.
3. Chi goi mt5.order_send() sau khi vuot qua chan tren. Che do dry-run
   (chi tinh toan, khong gui lenh) khong goi order_send().

Dinh co (position sizing): lay tu risk.position_size() — so tien vao
lenh sao cho lo toi da = von desk * max_risk_per_trade_pct — roi doi
sang lot MT5 theo contract size cua symbol (mac dinh 1 lot = 100.000
don vi, vd Forex; XAUUSD 1 lot = 100 oz; co the truyen contract_size
rieng cho tung symbol). Lam tron xuong buoc 0.01 lot, toi thieu 0.01.

Moi lenh (ca dry-run) deu ghi vao decisions log theo dinh dang chung
cua decisions.py: date, desk, symbol, action, reason, manager.
"""
from .decisions import log_decision
from .risk import position_size

# Hang cua MetaTrader5 (dung so that de code van chay khi goi chua cai).
MT5_TRADE_MODE_DEMO = 0
MT5_TRADE_MODE_REAL = 1
MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1
MT5_TRADE_RETCODE_DONE = 10009

# Contract size mac dinh theo loai symbol (1 lot = bao nhieu don vi).
CONTRACT_SIZES = {
    "forex": 100000,
    "xauusd": 100,
    "crypto": 1,
    "us_securities": 1,
}
DEFAULT_CONTRACT_SIZE = 100000
MIN_VOLUME = 0.01


class NotDemoAccountError(RuntimeError):
    """Tai khoan khong phai demo (hoac khong xac minh duoc) — tu choi lenh."""


def _trade_mode(mt5, account_info):
    """Doc trade_mode tu account_info; tra None neu khong doc duoc."""
    if account_info is None:
        return None
    mode = getattr(account_info, "trade_mode", None)
    if mode is None and isinstance(account_info, dict):
        mode = account_info.get("trade_mode")
    if isinstance(mode, str):
        return MT5_TRADE_MODE_DEMO if mode.lower() == "demo" else MT5_TRADE_MODE_REAL
    return mode


def _server_name(account_info, server=None):
    if server:
        return str(server)
    if account_info is None:
        return ""
    return str(getattr(account_info, "server", "") or "")


def account_is_demo(mt5, account_info, server=None):
    """True neu chac chan la tai khoan demo; False neu la that hoac mo ho."""
    if account_info is None:
        return False
    mode = _trade_mode(mt5, account_info)
    name = _server_name(account_info, server).lower()
    if mode == MT5_TRADE_MODE_REAL or "real" in name:
        return False
    if mode == MT5_TRADE_MODE_DEMO:
        return True
    if getattr(account_info, "demo", False) is True:
        return True
    if "demo" in name or "trial" in name:
        return True
    return False


def check_demo_only(cfg, mt5, account_info, server=None):
    """Chan DEMO-ONLY. Vuot qua moi cho gui lenh; neu khong -> raise.

    cfg: dict config (load tu config.yaml). mt5: module MetaTrader5
    (de lay hang TRADE_MODE khi co). account_info: ket qua cua
    mt5.account_info().
    """
    mt5_cfg = (cfg or {}).get("mt5") or {}
    if mt5_cfg.get("demo_only") is False:
        raise NotDemoAccountError(
            "Config mt5.demo_only=false — connector nay CHI chay demo, tu choi."
        )
    data_cfg = (cfg or {}).get("data") or {}
    if str(data_cfg.get("provider", "")).lower() in ("live", "real"):
        raise NotDemoAccountError(
            "Config data.provider='live'/'real' — connector nay CHI chay demo, tu choi."
        )
    if account_info is None:
        raise NotDemoAccountError(
            "Khong lay duoc thong tin tai khoan MT5 — khong xac minh duoc "
            "la demo nen tu choi gui lenh."
        )
    if not account_is_demo(mt5, account_info, server):
        raise NotDemoAccountError(
            "Tai khoan MT5 dang dang nhap KHONG phai demo "
            f"(server={_server_name(account_info, server)!r}, "
            f"trade_mode={_trade_mode(mt5, account_info)!r}) — "
            "connector nay CHI chay demo, tu choi gui lenh."
        )


def position_size_lots(capital_usd, risk_pct, entry, stop_loss,
                       contract_size=DEFAULT_CONTRACT_SIZE):
    """Doi position sizing (don vi) sang lot MT5, lam tron xuong 0.01.

    Tra 0.0 neu khong tinh duoc (entry == stop_loss, von <= 0, ...).
    """
    if capital_usd <= 0 or contract_size <= 0:
        return 0.0
    units = position_size(capital_usd, risk_pct, entry, stop_loss)
    if units <= 0:
        return 0.0
    lots = int((units / contract_size) * 100) / 100.0  # tron XUONG buoc 0.01
    return lots if lots >= MIN_VOLUME else 0.0


def _order_type(mt5, action):
    if action == "BUY":
        return getattr(mt5, "ORDER_TYPE_BUY", MT5_ORDER_TYPE_BUY)
    return getattr(mt5, "ORDER_TYPE_SELL", MT5_ORDER_TYPE_SELL)


def place_demo_order(mt5, *, symbol, action, volume, price, sl, tp=None,
                     desk, manager, cfg=None, account_info=None, server=None,
                     dry_run=False, comment="DiamondX10 DEMO"):
    """Dat lenh DEMO qua MT5. Tra ve dict ket qua; dry_run thi khong gui lenh.

    - action: 'BUY' / 'SELL' (khong dat lenh khi 'HOLD').
    - volume: lot MT5. price: gia vao lenh. sl: stop loss (bat buoc).
    - cfg/account_info/server: de chay chan DEMO-ONLY truoc khi gui.
    - Moi lenh (ke ca dry-run) deu ghi vao decisions log.
    """
    if action not in ("BUY", "SELL"):
        raise ValueError(f"Khong dat lenh voi action {action!r} (chi BUY/SELL)")
    if volume <= 0:
        raise ValueError(f"Volume phai > 0, nhan duoc {volume}")
    if sl is None or sl <= 0:
        raise ValueError("Stop loss (sl) la bat buoc cho moi lenh demo")
    # Chan DEMO-ONLY: chi bo qua khi dry-run VA khong co account_info de kiem.
    if not dry_run or account_info is not None:
        check_demo_only(cfg or {"mt5": {"demo_only": True}}, mt5, account_info, server)
    request = {
        "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
        "symbol": symbol,
        "volume": float(volume),
        "type": _order_type(mt5, action),
        "price": float(price),
        "sl": float(sl),
        "tp": float(tp) if tp else 0.0,
        "deviation": 20,
        "magic": 20261126,
        "comment": comment,
        "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
        "type_filling": getattr(mt5, "ORDER_FILLING_IOC", 1),
    }
    reason = f"DEMO {action} {symbol} {volume} lot @ {price} (SL {sl}, TP {tp or 0.0})"
    if dry_run:
        log_decision(symbol, f"DRY-RUN-{action}", reason + " [dry-run, khong gui lenh]",
                     desk=desk, manager=manager)
        return {"status": "DRY_RUN", "request": request, "order": None}
    result = mt5.order_send(request)
    if result is None:
        raise RuntimeError(f"MT5 order_send tra ve None. Loi MT5: {mt5.last_error()}")
    retcode = getattr(result, "retcode", None)
    done = getattr(mt5, "TRADE_RETCODE_DONE", MT5_TRADE_RETCODE_DONE)
    if retcode != done:
        raise RuntimeError(
            f"MT5 tu choi lenh demo {symbol} {action}: retcode={retcode}, "
            f"comment={getattr(result, 'comment', '')}"
        )
    log_decision(symbol, action, reason + f" [order {getattr(result, 'order', '')}]",
                 desk=desk, manager=manager)
    return {"status": "SENT", "request": request,
            "order": getattr(result, "order", None), "retcode": retcode}


def check_symbols_available(mt5, symbols):
    """Tra ve (co, thieu): danh sach symbol co / khong co tren server demo."""
    have, missing = [], []
    for symbol in symbols:
        (have if mt5.symbol_info(symbol) is not None else missing).append(symbol)
    return have, missing
